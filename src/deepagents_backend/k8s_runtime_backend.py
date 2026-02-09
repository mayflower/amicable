from __future__ import annotations

import asyncio
import base64
import logging
import posixpath
import shlex
from dataclasses import dataclass
from pathlib import PurePosixPath

import requests

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
        "deepagents is required to use the Amicable DeepAgents backend adapter"
    ) from exc

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _ExecResult:
    stdout: str
    stderr: str
    exit_code: int


def _shell_wrap(command: str) -> str:
    # Our sandbox runtime executes argv, not a shell. Wrap everything in sh -lc.
    return f"sh -lc {shlex.quote(command)}"


class K8sSandboxRuntimeBackend(SandboxBackendProtocol):
    """DeepAgents SandboxBackendProtocol adapter for Amicable sandbox runtime.

    This backend talks directly to the sandbox runtime service:
      http://<claim>.<namespace>.svc.cluster.local:8888

    It uses the runtime API endpoints:
      - POST /exec (and /execute as an alias)
      - GET  /download/{path}
      - POST /write_b64
    """

    def __init__(
        self,
        *,
        sandbox_id: str,
        base_url: str,
        root_dir: str = "/app",
        session: requests.Session | None = None,
        request_timeout_s: int = 60,
        exec_timeout_s: int = 600,
    ) -> None:
        if not root_dir.startswith("/"):
            raise ValueError(f"root_dir must be absolute, got: {root_dir}")
        self._sandbox_id = sandbox_id
        self._base_url = base_url.rstrip("/")
        self._root_dir = posixpath.normpath(root_dir)
        self._http = session or requests.Session()
        self._request_timeout_s = request_timeout_s
        self._exec_timeout_s = exec_timeout_s

    @property
    def id(self) -> str:  # SandboxBackendProtocol
        return self._sandbox_id

    def execute(self, command: str) -> ExecuteResponse:  # SandboxBackendProtocol
        res = self._exec_shell(command, timeout_s=self._exec_timeout_s)
        combined = res.stdout
        if res.stderr:
            combined = f"{combined}\n{res.stderr}" if combined else res.stderr
        return ExecuteResponse(
            output=combined, exit_code=res.exit_code, truncated=False
        )

    async def aexecute(self, command: str) -> ExecuteResponse:
        return await asyncio.to_thread(self.execute, command)

    def manifest(self, dir: str = "/") -> list[dict[str, object]]:
        """Return a recursive file manifest rooted at `dir` (public path).

        Requires sandbox runtime support for GET /manifest.
        """
        rel = self._to_relative(dir or "/")
        # Runtime expects a path relative to /app.
        payload_dir = "." if rel == "." else rel
        resp = self._request(
            "GET",
            "manifest",
            params={"dir": payload_dir, "include_hidden": 1},
            timeout=self._request_timeout_s,
        )
        data = resp.json()
        entries = data.get("entries")
        if not isinstance(entries, list):
            return []
        out: list[dict[str, object]] = []
        for e in entries:
            if not isinstance(e, dict):
                continue
            path = e.get("path")
            kind = e.get("kind")
            if not isinstance(path, str) or not path:
                continue
            if not isinstance(kind, str) or kind not in ("file", "dir", "symlink"):
                continue
            out.append(e)
        return out

    def ls_info(self, path: str) -> list[FileInfo]:
        internal_path = self._to_internal(path)
        # List direct children only.
        cmd = shlex.join(["ls", "-a", "-p", internal_path])
        res = self._exec_shell(cmd)
        if res.exit_code != 0:
            logger.warning(
                "ls_info failed for path=%r exit_code=%d stderr=%r",
                path,
                res.exit_code,
                res.stderr,
            )
            return []

        public_dir = self._normalize_public_dir(path)
        entries: list[FileInfo] = []
        for entry in res.stdout.splitlines():
            if entry in (".", ".."):
                continue
            is_dir = entry.endswith("/")
            name = entry[:-1] if is_dir else entry
            public_path = self._join_public(public_dir, name)
            entries.append(FileInfo(path=public_path, is_dir=is_dir))

        entries.sort(key=lambda item: item["path"])
        return entries

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        internal_path = self._to_internal(file_path)
        if not self._exists(internal_path):
            return f"Error: File '{file_path}' not found"

        raw = self._download(self._to_relative(file_path))
        decoded = raw.decode("utf-8", errors="replace")
        lines = decoded.splitlines()

        start = max(0, offset)
        end = min(len(lines), start + max(0, limit))
        numbered = [
            f"{idx + 1}: {self._truncate_line(lines[idx])}" for idx in range(start, end)
        ]
        return "\n".join(numbered)

    def grep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        base_path = path or "/"
        internal_path = self._to_internal(base_path)
        if not self._exists(internal_path):
            return f"Error: Path '{base_path}' not found"

        grep_opts = "-rHnF"
        glob_part = f"--include={shlex.quote(glob)}" if glob else ""
        cmd = (
            f"grep {grep_opts} {glob_part} -e {shlex.quote(pattern)} {shlex.quote(internal_path)} "
            "2>/dev/null || true"
        ).strip()
        res = self._exec_shell(cmd)
        if not res.stdout.strip():
            return []

        matches: list[GrepMatch] = []
        for line in res.stdout.splitlines():
            parts = line.split(":", 2)
            if len(parts) != 3:
                continue
            raw_path, line_no, text = parts
            public_path = self._to_public(raw_path)
            try:
                line_int = int(line_no)
            except ValueError:
                continue
            matches.append(GrepMatch(path=public_path, line=line_int, text=text))

        return matches

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        internal_path = self._to_internal(path)
        # We intentionally avoid find/glob usage guidance for the model; this is internal.
        cmd = shlex.join(["find", internal_path, "-mindepth", "1", "-print"])
        res = self._exec_shell(cmd)
        if res.exit_code != 0:
            logger.warning(
                "glob_info failed for path=%r exit_code=%d stderr=%r",
                path,
                res.exit_code,
                res.stderr,
            )
            return []

        normalized_pattern = pattern.lstrip("/")
        base_internal = self._to_internal(path)
        entries: list[FileInfo] = []
        for raw in res.stdout.splitlines():
            rel_path = posixpath.relpath(raw, base_internal)
            if PurePosixPath(rel_path).match(normalized_pattern):
                entries.append(
                    FileInfo(path=self._to_public(raw), is_dir=self._is_dir(raw))
                )

        entries.sort(key=lambda item: item["path"])
        return entries

    def write(self, file_path: str, content: str) -> WriteResult:
        internal_path = self._to_internal(file_path)
        if self._exists(internal_path):
            return WriteResult(
                error=f"File '{file_path}' already exists",
                path=file_path,
                files_update=None,
            )

        self._ensure_parent_dir(internal_path)
        payload = content.encode("utf-8") if isinstance(content, str) else content
        self._write_bytes(self._to_relative(file_path), payload)
        return WriteResult(error=None, path=file_path, files_update=None)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        internal_path = self._to_internal(file_path)
        if not self._exists(internal_path):
            return EditResult(
                error=f"Error: File '{file_path}' not found",
                path=file_path,
                files_update=None,
                occurrences=0,
            )

        content = self._download(self._to_relative(file_path)).decode(
            "utf-8", errors="replace"
        )
        occurrences = content.count(old_string)
        if occurrences == 0:
            return EditResult(
                error=f"Error: String not found in file: '{old_string}'",
                path=file_path,
                files_update=None,
                occurrences=0,
            )
        if not replace_all and occurrences > 1:
            return EditResult(
                error=(
                    f"Error: String '{old_string}' appears multiple times. "
                    "Use replace_all=True to replace all occurrences."
                ),
                path=file_path,
                files_update=None,
                occurrences=occurrences,
            )

        updated = (
            content.replace(old_string, new_string)
            if replace_all
            else content.replace(old_string, new_string, 1)
        )
        self._write_bytes(self._to_relative(file_path), updated.encode("utf-8"))
        return EditResult(
            error=None,
            path=file_path,
            files_update=None,
            occurrences=occurrences if replace_all else 1,
        )

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        responses: list[FileUploadResponse] = []
        for path, payload in files:
            try:
                internal_path = self._to_internal(path)
            except ValueError:
                responses.append(FileUploadResponse(path=path, error="invalid_path"))
                continue

            state = self._file_state(internal_path)
            if state == "dir":
                responses.append(FileUploadResponse(path=path, error="is_directory"))
                continue
            if state == "denied":
                responses.append(
                    FileUploadResponse(path=path, error="permission_denied")
                )
                continue

            parent_state = self._dir_state(posixpath.dirname(internal_path))
            if parent_state in ("missing", "not_dir"):
                responses.append(FileUploadResponse(path=path, error="invalid_path"))
                continue
            if parent_state == "denied":
                responses.append(
                    FileUploadResponse(path=path, error="permission_denied")
                )
                continue

            try:
                self._ensure_parent_dir(internal_path)
                self._write_bytes(self._to_relative(path), payload)
                responses.append(FileUploadResponse(path=path, error=None))
            except Exception:
                responses.append(FileUploadResponse(path=path, error="invalid_path"))
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        # Prefer a batch endpoint when available to avoid N HTTP round-trips.
        # Fall back to per-file download for older sandbox images.
        normalized: list[tuple[str, str] | tuple[str, None]] = []
        for p in paths:
            try:
                _ = self._to_internal(p)
                normalized.append((p, self._to_relative(p)))
            except ValueError:
                normalized.append((p, None))

        # If everything is invalid, short-circuit.
        if all(rel is None for _p, rel in normalized):
            return [
                FileDownloadResponse(path=p, content=None, error="invalid_path")
                for p, _rel in normalized
            ]

        try:
            batch_map = self._download_many([rel for _p, rel in normalized if rel is not None])
        except Exception:
            batch_map = None

        if batch_map is not None:
            out: list[FileDownloadResponse] = []
            for public_path, rel in normalized:
                if rel is None:
                    out.append(FileDownloadResponse(path=public_path, content=None, error="invalid_path"))
                    continue
                item = batch_map.get(rel)
                if not isinstance(item, dict):
                    out.append(FileDownloadResponse(path=public_path, content=None, error="file_not_found"))
                    continue
                err = item.get("error")
                if isinstance(err, str) and err:
                    out.append(FileDownloadResponse(path=public_path, content=None, error=err))
                    continue
                b64 = item.get("content_b64")
                if not isinstance(b64, str):
                    out.append(FileDownloadResponse(path=public_path, content=None, error="file_not_found"))
                    continue
                try:
                    content = base64.b64decode(b64.encode("ascii"), validate=True)
                except Exception:
                    out.append(FileDownloadResponse(path=public_path, content=None, error="file_not_found"))
                    continue
                out.append(FileDownloadResponse(path=public_path, content=content, error=None))
            return out

        # Fallback: original behavior (per-file state check + GET /download).
        responses: list[FileDownloadResponse] = []
        for path in paths:
            try:
                internal_path = self._to_internal(path)
            except ValueError:
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="invalid_path")
                )
                continue

            state = self._file_state(internal_path)
            if state == "missing":
                responses.append(
                    FileDownloadResponse(
                        path=path, content=None, error="file_not_found"
                    )
                )
                continue
            if state == "dir":
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="is_directory")
                )
                continue
            if state == "denied":
                responses.append(
                    FileDownloadResponse(
                        path=path, content=None, error="permission_denied"
                    )
                )
                continue

            try:
                content = self._download(self._to_relative(path))
                responses.append(
                    FileDownloadResponse(path=path, content=content, error=None)
                )
            except Exception:
                responses.append(
                    FileDownloadResponse(
                        path=path, content=None, error="file_not_found"
                    )
                )
        return responses

    # ---- Runtime API helpers

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = f"{self._base_url.rstrip('/')}/{path.lstrip('/')}"
        timeout = kwargs.pop("timeout", self._request_timeout_s)
        resp = self._http.request(method, url, timeout=timeout, **kwargs)
        resp.raise_for_status()
        return resp

    def _exec_raw(self, command: str, *, timeout_s: int) -> _ExecResult:
        # Prefer /execute (newer), fall back to /exec (older).
        payload = {"command": command}
        try:
            resp = self._request("POST", "execute", json=payload, timeout=timeout_s)
        except Exception:
            resp = self._request("POST", "exec", json=payload, timeout=timeout_s)
        data = resp.json()
        return _ExecResult(
            stdout=str(data.get("stdout") or ""),
            stderr=str(data.get("stderr") or ""),
            exit_code=int(
                data.get("exit_code") if data.get("exit_code") is not None else -1
            ),
        )

    def _exec_shell(self, command: str, *, timeout_s: int | None = None) -> _ExecResult:
        return self._exec_raw(
            _shell_wrap(command), timeout_s=timeout_s or self._request_timeout_s
        )

    def _download(self, rel_path: str) -> bytes:
        rel = rel_path.lstrip("/")
        resp = self._request("GET", f"download/{rel}")
        return resp.content

    def _download_many(self, rel_paths: list[str]) -> dict[str, dict[str, object]] | None:
        # Newer sandbox images provide POST /download_many. If the endpoint is missing,
        # allow callers to fall back to per-file downloads.
        rels = [p.lstrip("/") for p in rel_paths if isinstance(p, str) and p.strip()]
        if not rels:
            return {}
        try:
            resp = self._request("POST", "download_many", json={"paths": rels})
        except requests.HTTPError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 405):
                return None
            raise
        data = resp.json()
        files = data.get("files")
        if not isinstance(files, list):
            return {}
        out: dict[str, dict[str, object]] = {}
        for item in files:
            if not isinstance(item, dict):
                continue
            p = item.get("path")
            if isinstance(p, str) and p:
                out[p.lstrip("/")] = item
        return out

    def _write_bytes(self, rel_path: str, payload: bytes) -> None:
        rel = rel_path.lstrip("/")
        content_b64 = base64.b64encode(payload).decode("ascii")
        self._request(
            "POST", "write_b64", json={"path": rel, "content_b64": content_b64}
        )

    def _exists(self, internal_path: str) -> bool:
        cmd = f"test -e {shlex.quote(internal_path)}"
        res = self._exec_shell(cmd)
        return res.exit_code == 0

    def _is_dir(self, internal_path: str) -> bool:
        cmd = f"test -d {shlex.quote(internal_path)}"
        res = self._exec_shell(cmd)
        return res.exit_code == 0

    def _ensure_parent_dir(self, internal_path: str) -> None:
        parent = posixpath.dirname(internal_path)
        cmd = shlex.join(["mkdir", "-p", parent])
        res = self._exec_shell(cmd)
        if res.exit_code != 0:
            detail = res.stderr.strip() or f"exit code {res.exit_code}"
            raise RuntimeError(f"Cannot create parent directory '{parent}': {detail}")

    def _file_state(self, internal_path: str) -> str:
        check = (
            f"if [ ! -e {shlex.quote(internal_path)} ]; then echo missing; exit 0; fi; "
            f"if [ -d {shlex.quote(internal_path)} ]; then echo dir; exit 0; fi; "
            f"if [ -r {shlex.quote(internal_path)} ]; then echo file; else echo denied; fi"
        )
        res = self._exec_shell(check)
        out = res.stdout.strip()
        return out or "missing"

    def _dir_state(self, internal_path: str) -> str:
        check = (
            f"if [ ! -e {shlex.quote(internal_path)} ]; then echo missing; exit 0; fi; "
            f"if [ -d {shlex.quote(internal_path)} ]; then "
            f"if [ -w {shlex.quote(internal_path)} ]; then echo writable; else echo denied; fi; "
            f"exit 0; fi; "
            f"echo not_dir"
        )
        res = self._exec_shell(check)
        out = res.stdout.strip()
        return out or "missing"

    # ---- Path mapping helpers (public virtual FS -> sandbox FS)

    def _to_internal(self, path: str) -> str:
        normalized = path.strip() or "/"
        if normalized.startswith(self._root_dir):
            normalized = normalized[len(self._root_dir) :]
            normalized = normalized.lstrip("/")
        normalized = normalized.lstrip("/")
        internal_path = posixpath.normpath(posixpath.join(self._root_dir, normalized))
        if internal_path != self._root_dir and not internal_path.startswith(
            self._root_dir + "/"
        ):
            raise ValueError(f"Path '{path}' escapes root_dir '{self._root_dir}'")
        return internal_path

    def _to_relative(self, path: str) -> str:
        internal_path = self._to_internal(path)
        rel = posixpath.relpath(internal_path, self._root_dir)
        return "." if rel == "." else rel

    def _to_public(self, internal_path: str) -> str:
        rel = posixpath.relpath(internal_path, self._root_dir)
        if rel == ".":
            return "/"
        return "/" + rel

    def _normalize_public_dir(self, path: str) -> str:
        if not path or path == "/":
            return "/"
        if path.startswith(self._root_dir):
            path = path[len(self._root_dir) :]
        return "/" + path.strip("/")

    def _join_public(self, base: str, name: str) -> str:
        if base == "/":
            return "/" + name
        return posixpath.join(base, name)

    def _truncate_line(self, line: str, max_len: int = 2000) -> str:
        return line if len(line) <= max_len else line[:max_len]
