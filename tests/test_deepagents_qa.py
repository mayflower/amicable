import unittest

from src.deepagents_backend.qa import (
    detect_qa_commands,
    python_project_present,
    python_qa_commands,
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
