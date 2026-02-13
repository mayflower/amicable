from __future__ import annotations

import json
import os
import shlex
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QaCommandResult:
    command: str
    exit_code: int
    output: str
    truncated: bool


@dataclass(frozen=True)
class PackageJsonReadResult:
    exists: bool
    data: dict[str, Any] | None
    error: str | None


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _truncate(text: str, *, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def _execute_result_exit_code(res: Any) -> int:
    # Supports both attribute- and dict-style ExecuteResponse.
    code = getattr(res, "exit_code", None)
    if isinstance(code, int):
        return code
    if isinstance(res, dict):
        try:
            return int(res.get("exit_code", -1))
        except Exception:
            return -1
    return -1


def _execute_result_output(res: Any) -> str:
    out = getattr(res, "output", None)
    if isinstance(out, str):
        return out
    if isinstance(res, dict):
        v = res.get("output")
        return v if isinstance(v, str) else ""
    return ""


def read_package_json(backend: Any) -> PackageJsonReadResult:
    # Use execute so we don't depend on deepagents protocol types in this module.
    # Backend already wraps in sh -lc; keep command simple.
    exists = _exists_in_app(backend, "package.json")
    if not exists:
        return PackageJsonReadResult(exists=False, data=None, error=None)

    res = backend.execute("cd /app && cat package.json")
    if _execute_result_exit_code(res) != 0:
        return PackageJsonReadResult(
            exists=True,
            data=None,
            error="package.json exists but could not be read",
        )

    raw = _execute_result_output(res)
    try:
        data = json.loads(raw)
    except Exception:
        return PackageJsonReadResult(
            exists=True,
            data=None,
            error="package.json exists but is not valid JSON",
        )

    if not isinstance(data, dict):
        return PackageJsonReadResult(
            exists=True,
            data=None,
            error="package.json exists but did not parse to a JSON object",
        )
    return PackageJsonReadResult(exists=True, data=data, error=None)


def detect_qa_commands(package_json: dict[str, Any]) -> list[str]:
    scripts = package_json.get("scripts")
    if not isinstance(scripts, dict):
        return []

    cmds: list[str] = []
    if isinstance(scripts.get("lint"), str):
        cmds.append("npm run -s lint")
    if isinstance(scripts.get("typecheck"), str):
        cmds.append("npm run -s typecheck")

    # Tests can be expensive; default off unless explicitly enabled.
    if _env_bool("DEEPAGENTS_QA_RUN_TESTS", False) and isinstance(
        scripts.get("test"), str
    ):
        cmds.append("npm run -s test")

    if isinstance(scripts.get("build"), str):
        cmds.append("npm run -s build")
    return cmds


def effective_qa_commands(package_json: dict[str, Any] | None) -> list[str]:
    # Override: explicit commands (CSV). Example:
    #   DEEPAGENTS_QA_COMMANDS="npm run -s lint,npm run -s build"
    override = (os.environ.get("DEEPAGENTS_QA_COMMANDS") or "").strip()
    if override:
        return [c.strip() for c in override.split(",") if c.strip()]
    if package_json is None:
        return []
    return detect_qa_commands(package_json)


def _exists_in_app(backend: Any, rel_path: str) -> bool:
    res = backend.execute(f"cd /app && test -e {rel_path}")
    return _execute_result_exit_code(res) == 0


def _find_pattern_in_app(backend: Any, pattern: str) -> bool:
    q = shlex.quote(pattern)
    res = backend.execute(
        f"cd /app && find . -maxdepth 4 -name {q} -print -quit | grep -q ."
    )
    return _execute_result_exit_code(res) == 0


def _file_contains_in_app(backend: Any, rel_path: str, pattern: str) -> bool:
    rp = shlex.quote(rel_path)
    pat = shlex.quote(pattern)
    res = backend.execute(f"cd /app && grep -q {pat} {rp}")
    return _execute_result_exit_code(res) == 0


def python_project_present(backend: Any) -> bool:
    return _exists_in_app(backend, "pyproject.toml") or _exists_in_app(
        backend, "requirements.txt"
    )


def python_tests_present(backend: Any) -> bool:
    return _exists_in_app(backend, "tests")


def python_qa_commands(*, run_tests: bool) -> list[str]:
    cmds = [
        "python -m compileall -q .",
        "ruff check .",
    ]
    if run_tests:
        cmds.append("pytest")
    return cmds


def flutter_project_present(backend: Any) -> bool:
    return _exists_in_app(backend, "pubspec.yaml")


def flutter_qa_commands(*, run_tests: bool) -> list[str]:
    cmds = [
        "flutter pub get",
        "flutter analyze",
    ]
    if run_tests:
        cmds.append("flutter test")
    return cmds


def aspnetcore_project_present(backend: Any) -> bool:
    return _find_pattern_in_app(backend, "*.csproj") or _find_pattern_in_app(
        backend, "*.sln"
    )


def aspnetcore_qa_commands(*, run_tests: bool) -> list[str]:
    cmds = ["dotnet build"]
    if run_tests:
        cmds.append("dotnet test")
    return cmds


def quarkus_project_present(backend: Any) -> bool:
    if not _exists_in_app(backend, "pom.xml"):
        return False
    return _file_contains_in_app(backend, "pom.xml", "io.quarkus")


def quarkus_qa_commands(*, run_tests: bool) -> list[str]:
    cmds = ["./mvnw -q -DskipTests compile"]
    if run_tests:
        cmds.append("./mvnw -q test")
    return cmds


def phoenix_project_present(backend: Any) -> bool:
    if not _exists_in_app(backend, "mix.exs"):
        return False
    return _file_contains_in_app(backend, "mix.exs", "phoenix")


def phoenix_qa_commands(*, run_tests: bool) -> list[str]:
    cmds = ["mix compile"]
    if run_tests:
        cmds.append("mix test")
    return cmds


def _tsconfig_present(backend: Any) -> bool:
    return _exists_in_app(backend, "tsconfig.json")


def _vite_present(backend: Any, package_json: dict[str, Any] | None) -> bool:
    # Prefer an explicit dependency check, but allow config-file hints for minimal projects.
    if isinstance(package_json, dict):
        for key in ("dependencies", "devDependencies"):
            deps = package_json.get(key)
            if isinstance(deps, dict) and isinstance(deps.get("vite"), str):
                return True
    return any(
        _exists_in_app(backend, fp)
        for fp in (
            "vite.config.ts",
            "vite.config.js",
            "vite.config.mjs",
            "vite.config.cjs",
        )
    )


def fallback_qa_commands(
    backend: Any, *, package_json: dict[str, Any] | None
) -> list[str]:
    cmds: list[str] = []
    if _tsconfig_present(backend):
        cmds.append("npx --no-install tsc --noEmit")
    if _vite_present(backend, package_json):
        cmds.append("npx --no-install vite build")
    return cmds


def effective_qa_commands_for_backend(
    backend: Any, pkg: PackageJsonReadResult
) -> list[str]:
    # package.json parse errors should be treated as QA failures by the caller,
    # not silently ignored.
    if pkg.exists and pkg.error:
        return []

    override = (os.environ.get("DEEPAGENTS_QA_COMMANDS") or "").strip()
    if override:
        return [c.strip() for c in override.split(",") if c.strip()]

    cmds = detect_qa_commands(pkg.data or {})
    if cmds:
        return cmds

    # package.json exists but provides no scripts; attempt a minimal fallback to
    # catch syntax/type/build errors in common stacks.
    if pkg.exists:
        return fallback_qa_commands(backend, package_json=pkg.data)

    if aspnetcore_project_present(backend):
        return aspnetcore_qa_commands(run_tests=qa_run_tests_enabled())

    if quarkus_project_present(backend):
        return quarkus_qa_commands(run_tests=qa_run_tests_enabled())

    if phoenix_project_present(backend):
        return phoenix_qa_commands(run_tests=qa_run_tests_enabled())

    if flutter_project_present(backend):
        return flutter_qa_commands(run_tests=qa_run_tests_enabled())

    return []


def run_qa(
    backend: Any,
    commands: list[str],
    *,
    max_output_chars: int = 50_000,
) -> tuple[bool, list[QaCommandResult]]:
    results: list[QaCommandResult] = []
    for cmd in commands:
        # Always run from /app so relative paths and tooling behave as expected.
        res = backend.execute(f"cd /app && {cmd}")
        exit_code = _execute_result_exit_code(res)
        output = _execute_result_output(res) or ""
        output, truncated = _truncate(output, max_chars=max_output_chars)
        results.append(
            QaCommandResult(
                command=cmd,
                exit_code=exit_code,
                output=output,
                truncated=truncated,
            )
        )
        if exit_code != 0:
            return False, results
    return True, results


def qa_enabled_from_env(*, legacy_validate_env: bool) -> bool:
    # Backwards compatible: existing clusters set DEEPAGENTS_VALIDATE=1.
    raw = (os.environ.get("DEEPAGENTS_QA") or "").strip()
    if raw:
        return _env_bool("DEEPAGENTS_QA", default=True)
    if legacy_validate_env:
        return True
    return True


def qa_run_tests_enabled() -> bool:
    return _env_bool("DEEPAGENTS_QA_RUN_TESTS", False)


def qa_timeout_s() -> int:
    return _env_int("DEEPAGENTS_QA_TIMEOUT_S", 600)


def self_heal_max_rounds() -> int:
    return _env_int("DEEPAGENTS_SELF_HEAL_MAX_ROUNDS", 2)
