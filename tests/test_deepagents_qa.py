import unittest

from src.deepagents_backend.qa import (
    PackageJsonReadResult,
    detect_qa_commands,
    effective_qa_commands_for_backend,
    python_project_present,
    python_qa_commands,
    qa_enabled_from_env,
    read_package_json,
    run_qa,
)


class _FakeBackend:
    def __init__(self, outputs):
        # outputs: list[tuple[exit_code, output]]
        self._outputs = list(outputs)
        self.commands = []

    def execute(self, command: str):
        self.commands.append(command)
        if not self._outputs:
            return {"exit_code": 0, "output": "", "truncated": False}
        code, out = self._outputs.pop(0)
        return {"exit_code": code, "output": out, "truncated": False}


class TestDeepAgentsQa(unittest.TestCase):
    def test_qa_enabled_default_on(self):
        # Default behavior: QA enabled unless explicitly disabled.
        import os

        old = os.environ.get("DEEPAGENTS_QA")
        try:
            if "DEEPAGENTS_QA" in os.environ:
                del os.environ["DEEPAGENTS_QA"]
            self.assertTrue(qa_enabled_from_env(legacy_validate_env=False))
        finally:
            if old is None:
                os.environ.pop("DEEPAGENTS_QA", None)
            else:
                os.environ["DEEPAGENTS_QA"] = old

    def test_qa_enabled_can_be_disabled(self):
        import os

        old = os.environ.get("DEEPAGENTS_QA")
        try:
            os.environ["DEEPAGENTS_QA"] = "0"
            self.assertFalse(qa_enabled_from_env(legacy_validate_env=True))
            self.assertFalse(qa_enabled_from_env(legacy_validate_env=False))
        finally:
            if old is None:
                os.environ.pop("DEEPAGENTS_QA", None)
            else:
                os.environ["DEEPAGENTS_QA"] = old

    def test_detects_commands_from_scripts(self):
        pkg = {
            "scripts": {
                "lint": "eslint .",
                "typecheck": "tsc -b",
                "build": "vite build",
            }
        }
        cmds = detect_qa_commands(pkg)
        self.assertEqual(
            cmds, ["npm run -s lint", "npm run -s typecheck", "npm run -s build"]
        )

    def test_run_qa_runs_in_app_dir(self):
        b = _FakeBackend([(0, "ok")])
        passed, results = run_qa(b, ["npm run -s lint"])
        self.assertTrue(passed)
        self.assertEqual(len(results), 1)
        self.assertTrue(b.commands[0].startswith("cd /app && "))

    def test_run_qa_fails_fast(self):
        b = _FakeBackend([(0, "lint ok"), (1, "build fail"), (0, "should not run")])
        passed, results = run_qa(
            b, ["npm run -s lint", "npm run -s build", "npm run -s typecheck"]
        )
        self.assertFalse(passed)
        self.assertEqual(
            [r.command for r in results], ["npm run -s lint", "npm run -s build"]
        )

    def test_read_package_json_invalid_json_is_error(self):
        class _Backend:
            def execute(self, command: str):
                if "test -e package.json" in command:
                    return {"exit_code": 0, "output": "", "truncated": False}
                if "cat package.json" in command:
                    return {"exit_code": 0, "output": "{not json", "truncated": False}
                return {"exit_code": 1, "output": "", "truncated": False}

        res = read_package_json(_Backend())
        self.assertTrue(res.exists)
        self.assertIsNone(res.data)
        self.assertIsInstance(res.error, str)
        self.assertTrue("not valid JSON" in (res.error or ""))

    def test_effective_qa_commands_falls_back_for_tsconfig(self):
        class _Backend:
            def execute(self, command: str):
                if "test -e package.json" in command:
                    return {"exit_code": 0, "output": "", "truncated": False}
                if "cat package.json" in command:
                    return {"exit_code": 0, "output": "{}", "truncated": False}
                if "test -e tsconfig.json" in command:
                    return {"exit_code": 0, "output": "", "truncated": False}
                if "test -e vite.config" in command:
                    return {"exit_code": 1, "output": "", "truncated": False}
                return {"exit_code": 1, "output": "", "truncated": False}

        pkg = PackageJsonReadResult(exists=True, data={}, error=None)
        cmds = effective_qa_commands_for_backend(_Backend(), pkg)
        self.assertEqual(cmds, ["npx --no-install tsc --noEmit"])

    def test_python_project_present_detects_markers(self):
        class _ExistsBackend:
            def execute(self, command: str):
                if "test -e pyproject.toml" in command:
                    return {"exit_code": 0, "output": "", "truncated": False}
                return {"exit_code": 1, "output": "", "truncated": False}

        self.assertTrue(python_project_present(_ExistsBackend()))

    def test_python_qa_commands(self):
        self.assertEqual(
            python_qa_commands(run_tests=False),
            ["python -m compileall -q .", "ruff check ."],
        )
        self.assertEqual(
            python_qa_commands(run_tests=True),
            ["python -m compileall -q .", "ruff check .", "pytest"],
        )


if __name__ == "__main__":
    unittest.main()
