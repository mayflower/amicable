from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from src.sandbox_files.policy import normalize_public_path, require_mutation_allowed


@dataclass(frozen=True)
class StoreReadResult:
    path: str
    content: str | None
    sha256: str
    is_binary: bool


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _file_data_from_text(text: str, *, created_at: str | None = None) -> dict[str, Any]:
    now = _now_iso()
    return {
        "content": (text or "").split("\n"),
        "created_at": created_at or now,
        "modified_at": now,
    }


def _text_from_file_data(v: Any) -> str:
    if not isinstance(v, dict):
        return ""
    content = v.get("content")
    if isinstance(content, list):
        return "\n".join(str(x) for x in content)
    if isinstance(content, str):
        return content
    return ""


def _all_items(store: Any, namespace: tuple[str, ...]) -> list[Any]:
    out: list[Any] = []
    offset = 0
    while True:
        items = store.search(namespace, limit=200, offset=offset)
        if not items:
            break
        out.extend(items)
        if len(items) < 200:
            break
        offset += 200
    return out


class StoreFs:
    """A tiny FS abstraction over LangGraph Store for /memories/*."""

    def __init__(self, *, store: Any, namespace: tuple[str, ...]) -> None:
        self._store = store
        self._ns = namespace

    def ls(self, path: str) -> list[dict[str, Any]]:
        p = normalize_public_path(path)
        prefix = "/memories/" if p == "/memories" else p.rstrip("/") + "/"

        items = _all_items(self._store, self._ns)
        files: set[str] = set()
        dirs: set[str] = set()

        for it in items:
            key = str(getattr(it, "key", None) or "")
            if not key.startswith(prefix):
                continue
            rel = key[len(prefix) :]
            if not rel:
                continue
            if "/" in rel:
                d = rel.split("/", 1)[0]
                dirs.add(prefix + d + "/")
            else:
                files.add(prefix + rel)

        entries: list[dict[str, Any]] = []
        for d in sorted(dirs):
            name = d.rstrip("/").split("/")[-1]
            entries.append({"path": d.rstrip("/"), "name": name, "is_dir": True})
        for f in sorted(files):
            name = f.split("/")[-1]
            entries.append({"path": f, "name": name, "is_dir": False})
        return entries

    def read(self, path: str) -> StoreReadResult:
        p = normalize_public_path(path)
        it = self._store.get(self._ns, p)
        if it is None:
            raise FileNotFoundError("file_not_found")
        v = getattr(it, "value", None)
        text = _text_from_file_data(v)
        sha = _sha256_text(text)
        return StoreReadResult(path=p, content=text, sha256=sha, is_binary=False)

    def write(
        self, *, path: str, content: str, expected_sha256: str | None = None
    ) -> str:
        require_mutation_allowed(path)
        p = normalize_public_path(path)
        existing = self._store.get(self._ns, p)
        created_at: str | None = None
        if existing is not None:
            v = getattr(existing, "value", None)
            if isinstance(v, dict):
                created_at = (
                    v.get("created_at")
                    if isinstance(v.get("created_at"), str)
                    else None
                )
            if expected_sha256:
                cur_text = _text_from_file_data(v)
                if _sha256_text(cur_text) != expected_sha256:
                    raise RuntimeError("conflict")
        else:
            if expected_sha256:
                raise FileNotFoundError("file_not_found")

        file_data = _file_data_from_text(content, created_at=created_at)
        self._store.put(self._ns, p, file_data)
        return _sha256_text(content or "")

    def mkdir(self, path: str) -> None:
        # Directories are virtual in StoreFs; nothing to do.
        require_mutation_allowed(path)
        normalize_public_path(path)

    def create_file(self, *, path: str, content: str = "") -> str:
        require_mutation_allowed(path)
        p = normalize_public_path(path)
        file_data = _file_data_from_text(content)
        self._store.put(self._ns, p, file_data)
        return _sha256_text(content or "")

    def rename(self, *, src: str, dst: str) -> None:
        require_mutation_allowed(src)
        require_mutation_allowed(dst)
        s = normalize_public_path(src)
        d = normalize_public_path(dst)
        it = self._store.get(self._ns, s)
        if it is None:
            raise FileNotFoundError("file_not_found")
        self._store.put(self._ns, d, getattr(it, "value", None))
        self._store.delete(self._ns, s)

    def rm(self, *, path: str, recursive: bool) -> None:
        require_mutation_allowed(path)
        p = normalize_public_path(path)
        if not recursive and p.endswith("/"):
            raise ValueError("invalid path")

        # If it's a file, delete directly.
        if not recursive:
            self._store.delete(self._ns, p)
            return

        # Recursive: delete matching subtree keys.
        prefix = p.rstrip("/") + "/"
        items = _all_items(self._store, self._ns)
        for it in items:
            key = str(getattr(it, "key", None) or "")
            if key == p or key.startswith(prefix):
                self._store.delete(self._ns, key)
