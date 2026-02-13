from __future__ import annotations

import logging
import os
import posixpath
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_IMPORT_RE = re.compile(r"^\s*@(?P<path>[^\s#]+)\s*$")
_CODE_FENCE_RE = re.compile(r"^\s*```")


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return int(default)
    try:
        return int(raw)
    except Exception:
        return int(default)


def prompt_import_max_depth() -> int:
    return max(1, _env_int("AMICABLE_PROMPT_IMPORT_MAX_DEPTH", 5))


def prompt_max_chars() -> int:
    return max(4_000, _env_int("AMICABLE_PROMPT_MAX_CHARS", 24_000))


def _normalize_text(text: str) -> str:
    out_lines: list[str] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if _CODE_FENCE_RE.match(line):
            continue
        out_lines.append(line.rstrip())

    out = "\n".join(out_lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def _read_file_text(backend: Any, path: str, *, limit: int = 200_000) -> str | None:
    try:
        text = backend.read(path, offset=0, limit=limit)
    except Exception:
        return None
    if not isinstance(text, str):
        text = str(text or "")
    if len(text) > limit:
        text = text[:limit]
    return text


def _resolve_import_path(import_path: str, *, current_path: str) -> str:
    if import_path.startswith("/"):
        return posixpath.normpath(import_path)
    base_dir = posixpath.dirname(current_path) or "/"
    joined = posixpath.join(base_dir, import_path)
    normalized = posixpath.normpath(joined)
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    return normalized


@dataclass(frozen=True)
class InstructionComposeResult:
    prompt: str
    included_paths: list[str]
    missing_paths: list[str]
    truncated: bool


def compose_instruction_prompt(
    *,
    base_prompt: str,
    backend: Any,
    sources: list[str] | None = None,
    local_override_path: str = "/memories/agent.local.md",
    max_chars: int | None = None,
    max_depth: int | None = None,
) -> InstructionComposeResult:
    """Compose layered instructions for one sandbox session.

    Precedence/order is deterministic:
    1. base_prompt
    2. /AGENTS.md
    3. /.deepagents/AGENTS.md
    4. /memories/agent.local.md

    `@path/to/file.md` import directives are expanded recursively.
    """

    srcs = sources or ["/AGENTS.md", "/.deepagents/AGENTS.md", local_override_path]
    max_chars_eff = int(max_chars or prompt_max_chars())
    max_depth_eff = int(max_depth or prompt_import_max_depth())

    included_paths: list[str] = []
    missing_paths: list[str] = []
    visited_stack: set[str] = set()
    cache: dict[str, list[str]] = {}

    def _expand(path: str, *, depth: int) -> list[str]:
        if depth > max_depth_eff:
            missing_paths.append(f"{path} (max_depth)")
            return []
        if path in visited_stack:
            missing_paths.append(f"{path} (cycle)")
            return []
        if path in cache:
            return list(cache[path])

        visited_stack.add(path)
        try:
            raw = _read_file_text(backend, path)
            if raw is None:
                missing_paths.append(path)
                cache[path] = []
                return []

            if path not in included_paths:
                included_paths.append(path)

            out_lines: list[str] = []
            for line in raw.splitlines():
                m = _IMPORT_RE.match(line)
                if not m:
                    out_lines.append(line)
                    continue

                import_path = m.group("path")
                resolved = _resolve_import_path(import_path, current_path=path)
                nested = _expand(resolved, depth=depth + 1)
                if nested:
                    out_lines.append(f"# imported: {resolved}")
                    out_lines.extend(nested)

            cache[path] = out_lines
            return list(out_lines)
        finally:
            visited_stack.discard(path)

    sections: list[str] = [_normalize_text(base_prompt)]

    for src in srcs:
        p = str(src or "").strip()
        if not p:
            continue
        expanded = _expand(p, depth=1)
        if not expanded:
            continue
        body = _normalize_text("\n".join(expanded))
        if not body:
            continue
        sections.append(f"Workspace instructions ({p}):\n{body}")

    merged = _normalize_text("\n\n".join(s for s in sections if s.strip()))

    truncated = len(merged) > max_chars_eff
    if truncated:
        merged = merged[:max_chars_eff].rstrip() + "\n\n[...instructions truncated...]"

    if missing_paths:
        logger.debug("instruction compose missing paths: %s", missing_paths)

    return InstructionComposeResult(
        prompt=merged,
        included_paths=included_paths,
        missing_paths=missing_paths,
        truncated=truncated,
    )
