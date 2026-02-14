from __future__ import annotations

import logging
import re
import shlex
from collections.abc import Callable

try:
    from deepagents.backends.protocol import (
        EditResult,
        ExecuteResponse,
        FileDownloadResponse,
        FileInfo,
        FileUploadResponse,
        GrepMatch,
        SandboxBackendProtocol,
        WriteResult,
    )
except (ImportError, ModuleNotFoundError) as exc:  # pragma: no cover
    raise ImportError(
        "deepagents is required to use the Amicable policy wrapper"
    ) from exc

logger = logging.getLogger(__name__)


AuditLog = Callable[[str, str, dict], None]


class SandboxPolicyWrapper(SandboxBackendProtocol):
    """Wrap a sandbox backend with basic policy enforcement.

    We use this to prevent foot-guns (e.g., editing /src/main.tsx) while keeping
    the overall DeepAgents flow unchanged.
    """

    def __init__(
        self,
        backend: SandboxBackendProtocol,
        *,
        deny_write_paths: list[str] | None = None,
        deny_write_prefixes: list[str] | None = None,
        deny_commands: list[str] | None = None,
        audit_log: AuditLog | None = None,
    ) -> None:
        self._backend = backend
        self._deny_write_paths = set(deny_write_paths or [])
        self._deny_write_prefixes = [
            p.rstrip("/") + "/" for p in (deny_write_prefixes or [])
        ]
        self._deny_commands = deny_commands or []
        self._deny_command_rules = self._build_deny_command_rules(self._deny_commands)
        self._audit_log = audit_log

    @property
    def id(self) -> str:
        return self._backend.id

    def _is_denied_path(self, path: str) -> bool:
        if path in self._deny_write_paths:
            return True
        normalized = path.rstrip("/") + "/" if path != "/" else "/"
        return any(normalized.startswith(p) for p in self._deny_write_prefixes)

    def _normalize_command(self, cmd: str) -> str:
        normalized = " ".join(str(cmd or "").strip().split()).lower()
        return normalized

    def _build_deny_command_rules(
        self, deny_commands: list[str]
    ) -> list[tuple[str, re.Pattern[str], str]]:
        rules: list[tuple[str, re.Pattern[str], str]] = []
        for idx, raw in enumerate(deny_commands):
            normalized = self._normalize_command(raw)
            if not normalized:
                continue
            try:
                tokens = shlex.split(normalized)
            except Exception:
                tokens = normalized.split()
            if not tokens:
                continue

            # Match shell-like token sequences with flexible whitespace.
            token_pat = r"\s+".join(re.escape(t) for t in tokens)
            regex = re.compile(
                rf"(^|[;&|()]\s*|\s+){token_pat}(\s|$)",
                re.IGNORECASE,
            )
            rules.append((f"cmd_rule_{idx}", regex, raw))
        return rules

    def _matching_denied_command_rule(self, cmd: str) -> str | None:
        normalized = self._normalize_command(cmd)
        for rule_id, rule_re, _raw in self._deny_command_rules:
            if rule_re.search(normalized):
                return rule_id
        return None

    def _audit(self, operation: str, target: str, metadata: dict) -> None:
        if self._audit_log:
            try:
                self._audit_log(operation, target, metadata)
            except Exception:
                logger.exception("audit_log callback failed")
            return
        logger.info("[audit] %s target=%r meta=%r", operation, target, metadata)

    # ---- Read-only operations

    def ls_info(self, path: str) -> list[FileInfo]:
        return self._backend.ls_info(path)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        return self._backend.read(file_path, offset=offset, limit=limit)

    def grep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        return self._backend.grep_raw(pattern, path=path, glob=glob)

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        return self._backend.glob_info(pattern, path=path)

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return self._backend.download_files(paths)

    # ---- Guarded operations

    def execute(self, command: str) -> ExecuteResponse:
        denied_rule = self._matching_denied_command_rule(command)
        if denied_rule is not None:
            self._audit("execute_denied", command, {"rule_id": denied_rule})
            return ExecuteResponse(
                output="Policy denied: command contains a forbidden pattern",
                exit_code=126,
                truncated=False,
            )
        self._audit("execute", command, {})
        return self._backend.execute(command)

    def write(self, file_path: str, content: str) -> WriteResult:
        if self._is_denied_path(file_path):
            self._audit("write_denied", file_path, {"size": len(content or "")})
            return WriteResult(
                error=f"Policy denied: writes not allowed for '{file_path}'",
                path=file_path,
                files_update=None,
            )
        self._audit("write", file_path, {"size": len(content or "")})
        return self._backend.write(file_path, content)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        if self._is_denied_path(file_path):
            self._audit("edit_denied", file_path, {"replace_all": replace_all})
            return EditResult(
                error=f"Policy denied: edits not allowed for '{file_path}'",
                path=file_path,
                files_update=None,
                occurrences=0,
            )
        self._audit("edit", file_path, {"replace_all": replace_all})
        return self._backend.edit(
            file_path, old_string, new_string, replace_all=replace_all
        )

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        out: list[tuple[str, bytes]] = []
        responses: list[FileUploadResponse] = []
        for path, payload in files:
            if self._is_denied_path(path):
                self._audit("upload_denied", path, {"size": len(payload or b"")})
                responses.append(
                    FileUploadResponse(path=path, error="permission_denied")
                )
            else:
                out.append((path, payload))
        if out:
            self._audit("upload", "<batch>", {"count": len(out)})
            responses.extend(self._backend.upload_files(out))
        return responses
