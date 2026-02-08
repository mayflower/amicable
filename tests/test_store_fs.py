from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.sandbox_files.store_fs import StoreFs


@dataclass
class _Item:
    key: str
    value: dict


class FakeStore:
    def __init__(self) -> None:
        self._d: dict[tuple[tuple[str, ...], str], dict] = {}

    def get(self, namespace: tuple[str, ...], key: str):
        v = self._d.get((namespace, key))
        return None if v is None else _Item(key=key, value=v)

    def put(self, namespace: tuple[str, ...], key: str, value: dict) -> None:
        self._d[(namespace, key)] = value

    def delete(self, namespace: tuple[str, ...], key: str) -> None:
        self._d.pop((namespace, key), None)

    def search(self, namespace: tuple[str, ...], *, limit: int = 200, offset: int = 0):
        keys = [k for (ns, k) in self._d if ns == namespace]
        keys.sort()
        page = keys[offset : offset + limit]
        return [_Item(key=k, value=self._d[(namespace, k)]) for k in page]


def test_store_fs_create_read_write_conflict() -> None:
    store = FakeStore()
    fs = StoreFs(store=store, namespace=("p1", "filesystem"))

    sha1 = fs.create_file(path="/memories/AGENTS.md", content="hello")
    r1 = fs.read("/memories/AGENTS.md")
    assert r1.content == "hello"
    assert r1.sha256 == sha1

    sha2 = fs.write(path="/memories/AGENTS.md", content="hello2", expected_sha256=sha1)
    assert sha2 != sha1

    with pytest.raises(RuntimeError):
        fs.write(path="/memories/AGENTS.md", content="oops", expected_sha256="bad")


def test_store_fs_ls_and_rm_recursive() -> None:
    store = FakeStore()
    fs = StoreFs(store=store, namespace=("p1", "filesystem"))

    fs.create_file(path="/memories/a.txt", content="a")
    fs.create_file(path="/memories/dir/b.txt", content="b")

    root = fs.ls("/memories")
    assert any(e["path"] == "/memories/a.txt" for e in root)
    assert any(e["path"] == "/memories/dir" for e in root)

    fs.rm(path="/memories/dir", recursive=True)
    root2 = fs.ls("/memories")
    assert any(e["path"] == "/memories/a.txt" for e in root2)
    assert not any(e["path"] == "/memories/dir" for e in root2)
