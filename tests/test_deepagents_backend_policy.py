import importlib.util
import unittest

import pytest

if importlib.util.find_spec("deepagents") is None:
    pytest.skip("deepagents not installed in this environment", allow_module_level=True)

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

from src.deepagents_backend.policy import SandboxPolicyWrapper


class _FakeBackend(SandboxBackendProtocol):
    @property
    def id(self) -> str:
        return "fake"

    def execute(self, command: str) -> ExecuteResponse:
        return ExecuteResponse(output=f"ran: {command}", exit_code=0, truncated=False)

    def ls_info(self, _path: str) -> list[FileInfo]:
        return []

    def read(self, _file_path: str, _offset: int = 0, _limit: int = 2000) -> str:
        return ""

    def grep_raw(
        self, _pattern: str, _path: str | None = None, _glob: str | None = None
    ) -> list[GrepMatch] | str:
        return []

    def glob_info(self, _pattern: str, _path: str = "/") -> list[FileInfo]:
        return []

    def write(self, file_path: str, _content: str) -> WriteResult:
        return WriteResult(error=None, path=file_path, files_update=None)

    def edit(
        self,
        file_path: str,
        _old_string: str,
        _new_string: str,
        _replace_all: bool = False,
    ) -> EditResult:
        return EditResult(error=None, path=file_path, files_update=None, occurrences=1)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return [FileUploadResponse(path=p, error=None) for p, _ in files]

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return [FileDownloadResponse(path=p, content=b"", error=None) for p in paths]


class TestSandboxPolicyWrapper(unittest.TestCase):
    def test_denies_main_tsx_edits(self):
        wrapped = SandboxPolicyWrapper(
            _FakeBackend(), deny_write_paths=["/src/main.tsx"]
        )
        res = wrapped.edit("/src/main.tsx", "a", "b")
        self.assertIsNotNone(res.error)
        self.assertEqual(res.occurrences, 0)

    def test_denies_main_tsx_writes(self):
        wrapped = SandboxPolicyWrapper(
            _FakeBackend(), deny_write_paths=["/src/main.tsx"]
        )
        res = wrapped.write("/src/main.tsx", "x")
        self.assertIsNotNone(res.error)

    def test_denies_dangerous_commands(self):
        wrapped = SandboxPolicyWrapper(_FakeBackend(), deny_commands=["rm -rf"])
        res = wrapped.execute("rm -rf /app")
        self.assertEqual(res.exit_code, 126)
        self.assertIn("Policy denied", res.output)

    def test_denies_normalized_dangerous_commands(self):
        wrapped = SandboxPolicyWrapper(_FakeBackend(), deny_commands=["rm -rf /"])
        res = wrapped.execute("  RM   -RF   /   ")
        self.assertEqual(res.exit_code, 126)
        self.assertIn("Policy denied", res.output)

    def test_denies_upload(self):
        wrapped = SandboxPolicyWrapper(
            _FakeBackend(), deny_write_paths=["/src/main.tsx"]
        )
        res = wrapped.upload_files([("/src/main.tsx", b"")])
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].error, "permission_denied")


if __name__ == "__main__":
    unittest.main()
