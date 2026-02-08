from __future__ import annotations

import posixpath
from dataclasses import dataclass

DENY_WRITE_PATHS = {"/src/main.tsx"}
DENY_WRITE_PREFIXES = ("/node_modules/", "/.git/")


@dataclass(frozen=True)
class Policy:
    deny_write_paths: set[str]
    deny_write_prefixes: tuple[str, ...]


DEFAULT_POLICY = Policy(
    deny_write_paths=set(DENY_WRITE_PATHS),
    deny_write_prefixes=DENY_WRITE_PREFIXES,
)


def normalize_public_path(path: str) -> str:
    """Normalize a public (sandbox-rooted) POSIX path like '/src/App.tsx'."""
    raw = (path or "").strip()
    if not raw:
        raise ValueError("empty path")
    if "\x00" in raw:
        raise ValueError("invalid path")

    # Allow callers to pass paths like "src/App.tsx".
    if not raw.startswith("/"):
        raw = "/" + raw

    norm = posixpath.normpath(raw)
    if not norm.startswith("/"):
        norm = "/" + norm

    # Reject traversal attempts and ambiguous paths.
    # NOTE: normpath collapses "..", so also reject any original segments.
    if "/../" in raw or raw.endswith("/..") or raw == "/..":
        raise ValueError("path traversal not allowed")
    if norm == ".":
        raise ValueError("invalid path")

    return norm


def is_denied_path(path: str, *, policy: Policy = DEFAULT_POLICY) -> bool:
    if path in policy.deny_write_paths:
        return True
    normalized = path.rstrip("/") + "/" if path != "/" else "/"
    return any(normalized.startswith(p) for p in policy.deny_write_prefixes)


def require_mutation_allowed(path: str, *, policy: Policy = DEFAULT_POLICY) -> None:
    p = normalize_public_path(path)
    if p == "/":
        raise ValueError("refusing to modify root")
    if is_denied_path(p, policy=policy):
        raise PermissionError(f"writes not allowed for '{p}'")


def require_read_allowed(path: str, *, policy: Policy = DEFAULT_POLICY) -> None:
    # For now we allow reads broadly, but keep traversal/root validation consistent.
    _ = policy
    normalize_public_path(path)
