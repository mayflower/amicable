from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

from src.gitlab.sync import sync_repo_tree_to_sandbox


@dataclass
class _DL:
    content: bytes | None
    error: str | None = None


class _Backend:
    def __init__(self, *, files: dict[str, bytes] | None = None) -> None:
        # public path ("/a.txt") -> bytes
        self._files: dict[str, bytes] = dict(files or {})

    def download_files(self, paths):
        out: list[_DL] = []
        for p in paths:
            sp = str(p)
            if sp not in self._files:
                out.append(_DL(None, "file_not_found"))
            else:
                out.append(_DL(self._files[sp], None))
        return out

    def upload_files(self, files):
        # Accept public paths like "/a.txt".
        out = []
        for p, payload in files:
            sp = str(p)
            self._files[sp] = bytes(payload)
            out.append({"path": sp, "error": None})
        return out

    def execute(self, command: str):
        # Minimal emulation for "cd /app && rm -f -- <path>".
        cmd = str(command)
        if "rm -f" in cmd:
            # last token is the path
            parts = cmd.split()
            target = parts[-1].strip("'\"")
            if not target.startswith("/"):
                target = "/" + target
            self._files.pop(target, None)
        return {"output": "", "exit_code": 0}


def _git(args: list[str], *, cwd: str) -> str:
    cp = subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=True
    )
    return (cp.stdout or "").strip()


def _make_remote_with_base(tmp_path) -> tuple[str, str, str]:
    """Return (repo_url, workdir, base_sha)."""
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)

    work = tmp_path / "work"
    subprocess.run(["git", "init", str(work)], check=True, capture_output=True)
    _git(["checkout", "-b", "main"], cwd=str(work))
    (work / "a.txt").write_text("a1\n", encoding="utf-8")
    _git(["add", "a.txt"], cwd=str(work))
    _git(["-c", "user.name=t", "-c", "user.email=t@e", "commit", "-m", "base"], cwd=str(work))
    _git(["remote", "add", "origin", str(bare)], cwd=str(work))
    _git(["push", "-u", "origin", "main"], cwd=str(work))
    base_sha = _git(["rev-parse", "HEAD"], cwd=str(work))
    return str(bare), str(work), base_sha


def _write_state(backend: _Backend, *, sha: str) -> None:
    backend.upload_files(
        [
            (
                "/.amicable/git_state.json",
                json.dumps(
                    {
                        "branch": "main",
                        "remote_head_sha": sha,
                        "updated_at_unix": 0,
                        "conflicts": [],
                    }
                ).encode("utf-8"),
            )
        ]
    )


def test_pull_requires_baseline(monkeypatch, tmp_path):
    monkeypatch.setenv("GITLAB_TOKEN", "dummy")
    repo_url, _work, _base = _make_remote_with_base(tmp_path)

    b = _Backend(files={})
    res = sync_repo_tree_to_sandbox(
        b,
        repo_http_url=repo_url,
        project_slug="proj",
        cache_dir=str(tmp_path / "cache"),
    )
    assert res["error"] == "git_pull_no_baseline"
    assert isinstance(res.get("remote_sha"), str) and res["remote_sha"]


def test_pull_applies_clean_modification(monkeypatch, tmp_path):
    monkeypatch.setenv("GITLAB_TOKEN", "dummy")
    repo_url, workdir, base_sha = _make_remote_with_base(tmp_path)

    b = _Backend(files={"/a.txt": b"a1\n"})
    _write_state(b, sha=base_sha)

    # Remote change.
    (tmp_path / "work" / "a.txt").write_text("a2\n", encoding="utf-8")
    _git(["add", "a.txt"], cwd=workdir)
    _git(["-c", "user.name=t", "-c", "user.email=t@e", "commit", "-m", "c2"], cwd=workdir)
    _git(["push"], cwd=workdir)
    remote_sha = _git(["rev-parse", "HEAD"], cwd=workdir)

    res = sync_repo_tree_to_sandbox(
        b,
        repo_http_url=repo_url,
        project_slug="proj",
        cache_dir=str(tmp_path / "cache"),
    )
    assert res["updated"] is True
    assert res["remote_sha"] == remote_sha
    assert "/a.txt" in res["applied"]["modified"]
    assert b._files["/a.txt"] == b"a2\n"

    st = json.loads(b._files["/.amicable/git_state.json"].decode("utf-8"))
    assert st["remote_head_sha"] == remote_sha


def test_pull_writes_shadow_on_conflict(monkeypatch, tmp_path):
    monkeypatch.setenv("GITLAB_TOKEN", "dummy")
    repo_url, workdir, base_sha = _make_remote_with_base(tmp_path)

    # Local sandbox diverged from base.
    b = _Backend(files={"/a.txt": b"local\n"})
    _write_state(b, sha=base_sha)

    # Remote change.
    (tmp_path / "work" / "a.txt").write_text("a2\n", encoding="utf-8")
    _git(["add", "a.txt"], cwd=workdir)
    _git(["-c", "user.name=t", "-c", "user.email=t@e", "commit", "-m", "c2"], cwd=workdir)
    _git(["push"], cwd=workdir)
    remote_sha = _git(["rev-parse", "HEAD"], cwd=workdir)

    res = sync_repo_tree_to_sandbox(
        b,
        repo_http_url=repo_url,
        project_slug="proj",
        cache_dir=str(tmp_path / "cache"),
    )
    assert res["updated"] is True
    assert res["remote_sha"] == remote_sha
    assert res["applied"]["modified"] == []
    assert len(res["conflicts"]) == 1
    c = res["conflicts"][0]
    assert c["path"] == "/a.txt"
    assert c["remote_sha"] == remote_sha
    shadow = c["remote_shadow_path"]
    assert shadow in b._files
    assert b._files[shadow] == b"a2\n"
    assert b._files["/a.txt"] == b"local\n"
