from __future__ import annotations

import hashlib
import shlex
from dataclasses import dataclass
from typing import Any

from src.sandbox_files.policy import (
    DEFAULT_POLICY,
    normalize_public_path,
    require_mutation_allowed,
    require_read_allowed,
)

_MAX_TEXT_BYTES = 500_000


@dataclass(frozen=True)
class ReadResult:
    path: str
    content: str | None
    sha256: str
    is_binary: bool


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _looks_binary(data: bytes) -> bool:
    if b"\x00" in data:
        return True
    try:
        data.decode("utf-8")
        return False
    except Exception:
        return True


def _rel(path: str) -> str:
    # Commands run with /app as root; public paths are rooted at "/".
    return normalize_public_path(path).lstrip("/")


class SandboxFs:
    """Sandbox filesystem operations via a DeepAgents backend."""

    def __init__(self, backend: Any) -> None:
        self._backend = backend

    def ls(self, path: str) -> list[dict[str, Any]]:
        require_read_allowed(path, policy=DEFAULT_POLICY)
        p = normalize_public_path(path)
        infos = self._backend.ls_info(p)
        out: list[dict[str, Any]] = []
        for info in infos:
            ipath = str(info.get("path") or "")
            is_dir = bool(info.get("is_dir"))
            name = ipath.rstrip("/").split("/")[-1] if ipath and ipath != "/" else "/"
            out.append({"path": ipath, "name": name, "is_dir": is_dir})
        return out

    def read(self, path: str) -> ReadResult:
        require_read_allowed(path, policy=DEFAULT_POLICY)
        p = normalize_public_path(path)
        res = self._backend.download_files([p])
        if not res:
            raise FileNotFoundError("file_not_found")

        # Backend implementations may return dict-like or attribute-like objects.
        item = res[0]
        if isinstance(item, dict):
            err = item.get("error")
            data = item.get("content")
        else:
            err = getattr(item, "error", None)
            data = getattr(item, "content", None)

        if err is not None:
            err_str = str(err) if err else "file_not_found"
            raise FileNotFoundError(err_str)
        if data is None:
            raise FileNotFoundError("file_not_found")

        payload = data
        if not isinstance(payload, (bytes, bytearray)):
            payload = str(payload).encode("utf-8", errors="replace")

        sha = _sha256_bytes(bytes(payload))
        if len(payload) > _MAX_TEXT_BYTES or _looks_binary(bytes(payload)):
            return ReadResult(path=p, content=None, sha256=sha, is_binary=True)

        text = bytes(payload).decode("utf-8", errors="strict")
        return ReadResult(path=p, content=text, sha256=sha, is_binary=False)

    def write(
        self,
        *,
        path: str,
        content: str,
        expected_sha256: str | None = None,
    ) -> str:
        require_mutation_allowed(path, policy=DEFAULT_POLICY)
        p = normalize_public_path(path)

        if expected_sha256:
            try:
                cur = self.read(p)
            except FileNotFoundError:
                cur = None
            if cur is None:
                raise FileNotFoundError("file_not_found")
            if cur.sha256 != expected_sha256:
                raise RuntimeError("conflict")

        # Ensure parent exists (upload_files rejects missing parent dirs).
        parent = p.rsplit("/", 1)[0] or "/"
        if parent != "/":
            self._backend.execute(f"mkdir -p -- {shlex.quote(_rel(parent))}")

        payload = (content or "").encode("utf-8")
        up = self._backend.upload_files([(p, payload)])
        if not up or up[0].get("error") is not None:
            err = (up[0].get("error") if up else "invalid_path") or "invalid_path"
            raise RuntimeError(str(err))

        return _sha256_bytes(payload)

    def mkdir(self, path: str) -> None:
        require_mutation_allowed(path, policy=DEFAULT_POLICY)
        p = normalize_public_path(path)
        self._backend.execute(f"mkdir -p -- {shlex.quote(_rel(p))}")

    def create_file(self, *, path: str, content: str = "") -> str:
        require_mutation_allowed(path, policy=DEFAULT_POLICY)
        p = normalize_public_path(path)
        parent = p.rsplit("/", 1)[0] or "/"
        if parent != "/":
            self._backend.execute(f"mkdir -p -- {shlex.quote(_rel(parent))}")
        payload = (content or "").encode("utf-8")
        up = self._backend.upload_files([(p, payload)])
        if not up or up[0].get("error") is not None:
            err = (up[0].get("error") if up else "invalid_path") or "invalid_path"
            raise RuntimeError(str(err))
        return _sha256_bytes(payload)

    def rename(self, *, src: str, dst: str) -> None:
        require_mutation_allowed(src, policy=DEFAULT_POLICY)
        require_mutation_allowed(dst, policy=DEFAULT_POLICY)
        s = normalize_public_path(src)
        d = normalize_public_path(dst)
        self._backend.execute(f"mv -- {shlex.quote(_rel(s))} {shlex.quote(_rel(d))}")

    def rm(self, *, path: str, recursive: bool) -> None:
        require_mutation_allowed(path, policy=DEFAULT_POLICY)
        p = normalize_public_path(path)
        if p == "/":
            raise ValueError("refusing to delete root")
        flag = "-rf" if recursive else "-f"
        self._backend.execute(f"rm {flag} -- {shlex.quote(_rel(p))}")
