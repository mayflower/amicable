import tarfile
from io import BytesIO

import pytest

from src.gitlab.sync import _build_tar_command, export_sandbox_snapshot, sync_snapshot_to_repo


class _ExecRes:
    def __init__(self, exit_code=0, output=""):
        self.exit_code = exit_code
        self.output = output


class _DL:
    def __init__(self, content: bytes | None, error=None):
        self.content = content
        self.error = error


class _Backend:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.executed = []
        self.downloaded = []

    def execute(self, command: str):
        self.executed.append(command)
        return _ExecRes(0, "ok")

    def download_files(self, paths):
        self.downloaded.append(paths)
        return [_DL(self.payload, None)]


def _make_tgz(files: dict[str, bytes]) -> bytes:
    b = BytesIO()
    with tarfile.open(fileobj=b, mode="w:gz") as tf:
        for path, data in files.items():
            ti = tarfile.TarInfo(name=path)
            ti.size = len(data)
            tf.addfile(ti, BytesIO(data))
    return b.getvalue()


def test_build_tar_command_includes_excludes():
    cmd = _build_tar_command(out_name=".amicable_snapshot.tgz", excludes=["node_modules/", "dist/"])
    assert "--exclude=./node_modules" in cmd
    assert "--exclude=./dist" in cmd


def test_export_sandbox_snapshot_downloads_and_deletes():
    tgz = _make_tgz({"package.json": b"{}"})
    b = _Backend(tgz)
    out = export_sandbox_snapshot(b, excludes=["node_modules/"])
    assert out == tgz
    assert any("tar -czf .amicable_snapshot.tgz" in c for c in b.executed)
    assert any(c.startswith("rm -f .amicable_snapshot.tgz") for c in b.executed)


def test_sync_snapshot_to_repo_requires_token(monkeypatch, tmp_path):
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    with pytest.raises(RuntimeError):
        sync_snapshot_to_repo(b"x", repo_http_url="https://git.example/a/b.git", project_slug="p", cache_dir=str(tmp_path))
