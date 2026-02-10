import os
import subprocess
from dataclasses import dataclass

import pytest

from src.gitlab.sync import bootstrap_repo_if_empty, sync_sandbox_tree_to_repo


@dataclass
class _DL:
    content: bytes | None
    error: str | None = None


class _Backend:
    def __init__(self, *, entries: list[dict], files: dict[str, bytes]):
        self._entries = entries
        self._files = files

    def manifest(self, _dir: str = "/"):
        return list(self._entries)

    def download_files(self, paths):
        out: list[_DL] = []
        for p in paths:
            rel = str(p).lstrip("/")
            if rel not in self._files:
                out.append(_DL(None, "file_not_found"))
            else:
                out.append(_DL(self._files[rel], None))
        return out


def _git(args: list[str], *, cwd: str) -> str:
    cp = subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=True
    )
    return (cp.stdout or "").strip()


def test_sync_tree_requires_token(monkeypatch, tmp_path):
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    b = _Backend(entries=[], files={})
    with pytest.raises(RuntimeError):
        sync_sandbox_tree_to_repo(
            b,
            repo_http_url="https://git.example/a/b.git",
            project_slug="p",
            cache_dir=str(tmp_path),
            commit_message="x",
        )


def test_sync_tree_excludes_and_writes_files(monkeypatch, tmp_path):
    monkeypatch.setenv("GITLAB_TOKEN", "dummy")

    bare = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", str(bare)], check=True, capture_output=True
    )

    entries = [
        {"path": "README.md", "kind": "file", "mode": 0o644},
        {"path": ".env", "kind": "file", "mode": 0o600},
        {"path": "node_modules/x.js", "kind": "file", "mode": 0o644},
        {"path": "bin/run.sh", "kind": "file", "mode": 0o755},
        {"path": "link", "kind": "symlink", "link_target": "README.md", "mode": 0o777},
    ]
    files = {
        "README.md": b"hello\n",
        ".env": b"SECRET=1\n",
        "node_modules/x.js": b"ignored\n",
        "bin/run.sh": b"#!/bin/sh\necho ok\n",
    }
    b = _Backend(entries=entries, files=files)

    pushed, sha, diff_stat, name_status = sync_sandbox_tree_to_repo(
        b,
        repo_http_url=str(bare),
        project_slug="proj",
        cache_dir=str(tmp_path / "cache"),
        excludes=["node_modules/", ".env", ".env.*"],
        commit_message="Bootstrap sandbox template\n\nTest\n",
    )
    assert pushed is True
    assert sha
    assert "README.md" in name_status
    assert "bin/run.sh" in name_status
    assert ".env" not in name_status
    assert "node_modules" not in name_status

    # Clone and validate results.
    work = tmp_path / "work"
    subprocess.run(
        ["git", "clone", str(bare), str(work)], check=True, capture_output=True
    )
    assert (work / "README.md").read_bytes() == b"hello\n"
    assert not (work / ".env").exists()
    assert not (work / "node_modules").exists()
    assert (work / "link").is_symlink()
    assert os.readlink(work / "link") == "README.md"
    st = os.stat(work / "bin" / "run.sh")
    assert st.st_mode & 0o111
    assert "README.md" in diff_stat


def test_bootstrap_repo_if_empty_noops_on_existing_branch(monkeypatch, tmp_path):
    monkeypatch.setenv("GITLAB_TOKEN", "dummy")

    bare = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", str(bare)], check=True, capture_output=True
    )

    b = _Backend(
        entries=[{"path": "a.txt", "kind": "file", "mode": 0o644}],
        files={"a.txt": b"a"},
    )
    booted, sha = bootstrap_repo_if_empty(
        b,
        repo_http_url=str(bare),
        project_slug="proj",
        cache_dir=str(tmp_path / "cache"),
        commit_message="Bootstrap sandbox template\n\nTest\n",
    )
    assert booted is True
    assert sha

    # Second call should no-op because branch exists remotely.
    booted2, sha2 = bootstrap_repo_if_empty(
        b,
        repo_http_url=str(bare),
        project_slug="proj",
        cache_dir=str(tmp_path / "cache"),
        commit_message="Bootstrap sandbox template\n\nTest\n",
    )
    assert booted2 is False
    assert sha2 is None


def test_sync_tree_deletes_removed_files(monkeypatch, tmp_path):
    monkeypatch.setenv("GITLAB_TOKEN", "dummy")

    bare = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", str(bare)], check=True, capture_output=True
    )

    cache = str(tmp_path / "cache")
    b1 = _Backend(
        entries=[
            {"path": "a.txt", "kind": "file", "mode": 0o644},
            {"path": "b.txt", "kind": "file", "mode": 0o644},
        ],
        files={"a.txt": b"a", "b.txt": b"b"},
    )
    sync_sandbox_tree_to_repo(
        b1,
        repo_http_url=str(bare),
        project_slug="proj",
        cache_dir=cache,
        commit_message="c1",
    )

    b2 = _Backend(
        entries=[{"path": "a.txt", "kind": "file", "mode": 0o644}],
        files={"a.txt": b"a2"},
    )
    sync_sandbox_tree_to_repo(
        b2,
        repo_http_url=str(bare),
        project_slug="proj",
        cache_dir=cache,
        commit_message="c2",
    )

    work = tmp_path / "work"
    subprocess.run(
        ["git", "clone", str(bare), str(work)], check=True, capture_output=True
    )
    # default branch may not be checked out depending on git version; force main.
    _git(["checkout", "main"], cwd=str(work))
    assert (work / "a.txt").read_bytes() == b"a2"
    assert not (work / "b.txt").exists()
