import unittest

from src.deepagents_backend.qa import (
    PackageJsonReadResult,
    QaCommandResult,
    aspnetcore_project_present,
    aspnetcore_qa_commands,
    classify_qa_failure,
    detect_qa_commands,
    effective_qa_commands_for_backend,
    flutter_project_present,
    flutter_qa_commands,
    phoenix_project_present,
    phoenix_qa_commands,
    python_project_present,
    python_qa_commands,
    qa_enabled_from_env,
    quarkus_project_present,
    quarkus_qa_commands,
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

    def test_flutter_project_present_detects_pubspec(self):
        class _ExistsBackend:
            def execute(self, command: str):
                if "test -e pubspec.yaml" in command:
                    return {"exit_code": 0, "output": "", "truncated": False}
                return {"exit_code": 1, "output": "", "truncated": False}

        self.assertTrue(flutter_project_present(_ExistsBackend()))

    def test_flutter_qa_commands(self):
        self.assertEqual(
            flutter_qa_commands(run_tests=False),
            ["flutter pub get", "flutter analyze"],
        )
        self.assertEqual(
            flutter_qa_commands(run_tests=True),
            ["flutter pub get", "flutter analyze", "flutter test"],
        )

    def test_effective_qa_commands_detects_flutter_when_no_package_json(self):
        import os

        old = os.environ.get("DEEPAGENTS_QA_RUN_TESTS")
        try:
            os.environ["DEEPAGENTS_QA_RUN_TESTS"] = "0"

            class _Backend:
                def execute(self, command: str):
                    if "test -e package.json" in command:
                        return {"exit_code": 1, "output": "", "truncated": False}
                    if "*.csproj" in command or "*.sln" in command:
                        return {"exit_code": 1, "output": "", "truncated": False}
                    if "test -e pom.xml" in command:
                        return {"exit_code": 1, "output": "", "truncated": False}
                    if "test -e mix.exs" in command:
                        return {"exit_code": 1, "output": "", "truncated": False}
                    if "test -e pubspec.yaml" in command:
                        return {"exit_code": 0, "output": "", "truncated": False}
                    return {"exit_code": 1, "output": "", "truncated": False}

            pkg = PackageJsonReadResult(exists=False, data=None, error=None)
            cmds = effective_qa_commands_for_backend(_Backend(), pkg)
            self.assertEqual(cmds, ["flutter pub get", "flutter analyze"])
        finally:
            if old is None:
                os.environ.pop("DEEPAGENTS_QA_RUN_TESTS", None)
            else:
                os.environ["DEEPAGENTS_QA_RUN_TESTS"] = old

    def test_effective_qa_commands_override_takes_precedence_for_flutter(self):
        import os

        old_override = os.environ.get("DEEPAGENTS_QA_COMMANDS")
        old_run_tests = os.environ.get("DEEPAGENTS_QA_RUN_TESTS")
        try:
            os.environ["DEEPAGENTS_QA_COMMANDS"] = "echo one,echo two"
            os.environ["DEEPAGENTS_QA_RUN_TESTS"] = "1"

            class _Backend:
                def execute(self, command: str):
                    if "test -e pubspec.yaml" in command:
                        return {"exit_code": 0, "output": "", "truncated": False}
                    return {"exit_code": 1, "output": "", "truncated": False}

            pkg = PackageJsonReadResult(exists=False, data=None, error=None)
            cmds = effective_qa_commands_for_backend(_Backend(), pkg)
            self.assertEqual(cmds, ["echo one", "echo two"])
        finally:
            if old_override is None:
                os.environ.pop("DEEPAGENTS_QA_COMMANDS", None)
            else:
                os.environ["DEEPAGENTS_QA_COMMANDS"] = old_override
            if old_run_tests is None:
                os.environ.pop("DEEPAGENTS_QA_RUN_TESTS", None)
            else:
                os.environ["DEEPAGENTS_QA_RUN_TESTS"] = old_run_tests

    def test_classify_qa_failure_marks_missing_flutter_binary_as_environment(self):
        results = [
            QaCommandResult(
                command="flutter pub get",
                exit_code=127,
                output="sh: 1: flutter: not found",
                truncated=False,
            )
        ]
        self.assertEqual(classify_qa_failure(results), "environment")

    def test_classify_qa_failure_keeps_code_errors_as_code(self):
        results = [
            QaCommandResult(
                command="flutter analyze",
                exit_code=1,
                output="lib/main.dart:10:1: Error: Expected ';'",
                truncated=False,
            )
        ]
        self.assertEqual(classify_qa_failure(results), "code")

    def test_aspnetcore_project_present_detects_csproj(self):
        class _ExistsBackend:
            def execute(self, command: str):
                if "*.csproj" in command:
                    return {"exit_code": 0, "output": "app.csproj", "truncated": False}
                return {"exit_code": 1, "output": "", "truncated": False}

        self.assertTrue(aspnetcore_project_present(_ExistsBackend()))

    def test_aspnetcore_qa_commands(self):
        self.assertEqual(aspnetcore_qa_commands(run_tests=False), ["dotnet build"])
        self.assertEqual(
            aspnetcore_qa_commands(run_tests=True),
            ["dotnet build", "dotnet test"],
        )

    def test_quarkus_project_present_detects_pom_marker(self):
        class _ExistsBackend:
            def execute(self, command: str):
                if "test -e pom.xml" in command:
                    return {"exit_code": 0, "output": "", "truncated": False}
                if "grep -q" in command and "io.quarkus" in command:
                    return {"exit_code": 0, "output": "", "truncated": False}
                return {"exit_code": 1, "output": "", "truncated": False}

        self.assertTrue(quarkus_project_present(_ExistsBackend()))

    def test_quarkus_qa_commands(self):
        self.assertEqual(
            quarkus_qa_commands(run_tests=False),
            ["./mvnw -q -DskipTests compile"],
        )
        self.assertEqual(
            quarkus_qa_commands(run_tests=True),
            ["./mvnw -q -DskipTests compile", "./mvnw -q test"],
        )

    def test_phoenix_project_present_detects_mix_marker(self):
        class _ExistsBackend:
            def execute(self, command: str):
                if "test -e mix.exs" in command:
                    return {"exit_code": 0, "output": "", "truncated": False}
                if "grep -q" in command and "phoenix" in command:
                    return {"exit_code": 0, "output": "", "truncated": False}
                return {"exit_code": 1, "output": "", "truncated": False}

        self.assertTrue(phoenix_project_present(_ExistsBackend()))

    def test_phoenix_qa_commands(self):
        self.assertEqual(phoenix_qa_commands(run_tests=False), ["mix compile"])
        self.assertEqual(
            phoenix_qa_commands(run_tests=True),
            ["mix compile", "mix test"],
        )

    def test_effective_qa_commands_detects_aspnetcore_when_no_package_json(self):
        class _Backend:
            def execute(self, command: str):
                if "test -e package.json" in command:
                    return {"exit_code": 1, "output": "", "truncated": False}
                if "*.csproj" in command:
                    return {"exit_code": 0, "output": "app.csproj", "truncated": False}
                return {"exit_code": 1, "output": "", "truncated": False}

        pkg = PackageJsonReadResult(exists=False, data=None, error=None)
        cmds = effective_qa_commands_for_backend(_Backend(), pkg)
        self.assertEqual(cmds, ["dotnet build"])

    def test_effective_qa_commands_detects_quarkus_when_no_package_json(self):
        class _Backend:
            def execute(self, command: str):
                if "test -e package.json" in command:
                    return {"exit_code": 1, "output": "", "truncated": False}
                if "*.csproj" in command or "*.sln" in command:
                    return {"exit_code": 1, "output": "", "truncated": False}
                if "test -e pom.xml" in command:
                    return {"exit_code": 0, "output": "", "truncated": False}
                if "grep -q" in command and "io.quarkus" in command:
                    return {"exit_code": 0, "output": "", "truncated": False}
                return {"exit_code": 1, "output": "", "truncated": False}

        pkg = PackageJsonReadResult(exists=False, data=None, error=None)
        cmds = effective_qa_commands_for_backend(_Backend(), pkg)
        self.assertEqual(cmds, ["./mvnw -q -DskipTests compile"])

    def test_effective_qa_commands_detects_phoenix_when_no_package_json(self):
        class _Backend:
            def execute(self, command: str):
                if "test -e package.json" in command:
                    return {"exit_code": 1, "output": "", "truncated": False}
                if "*.csproj" in command or "*.sln" in command:
                    return {"exit_code": 1, "output": "", "truncated": False}
                if "test -e pom.xml" in command:
                    return {"exit_code": 1, "output": "", "truncated": False}
                if "test -e mix.exs" in command:
                    return {"exit_code": 0, "output": "", "truncated": False}
                if "grep -q" in command and "phoenix" in command:
                    return {"exit_code": 0, "output": "", "truncated": False}
                return {"exit_code": 1, "output": "", "truncated": False}

        pkg = PackageJsonReadResult(exists=False, data=None, error=None)
        cmds = effective_qa_commands_for_backend(_Backend(), pkg)
        self.assertEqual(cmds, ["mix compile"])


if __name__ == "__main__":
    unittest.main()
