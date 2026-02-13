from __future__ import annotations

from src.gitlab.commit_message import (
    deterministic_bootstrap_commit_message,
    evaluate_agent_readme_policy,
)


def test_readme_policy_warns_for_non_doc_changes_without_readme_updates() -> None:
    warnings = evaluate_agent_readme_policy("M\tsrc/main.ts\nA\tpackage.json\n")
    assert warnings
    assert "README policy" in warnings[0]


def test_readme_policy_passes_when_root_readme_is_updated() -> None:
    warnings = evaluate_agent_readme_policy("M\tsrc/main.ts\nM\tREADME.md\n")
    assert warnings == []


def test_readme_policy_passes_when_docs_index_is_updated() -> None:
    warnings = evaluate_agent_readme_policy("M\tsrc/main.ts\nM\tdocs/index.md\n")
    assert warnings == []


def test_readme_policy_ignores_docs_only_changes() -> None:
    warnings = evaluate_agent_readme_policy("M\tdocs/architecture.md\nM\tdocs/runbook.md\n")
    assert warnings == []


def test_readme_policy_handles_rename_records() -> None:
    warnings = evaluate_agent_readme_policy("R100\tsrc/old.ts\tsrc/new.ts\n")
    assert warnings


def test_bootstrap_commit_message_includes_prompt_based_about() -> None:
    msg = deterministic_bootstrap_commit_message(
        project_slug="todo-app",
        template_id="vite",
        project_name="Todo App",
        project_prompt="Build a todo app.\n\nTrack due dates and tags.",
    )
    assert "Project Name: Todo App" in msg
    assert "Project: todo-app" in msg
    assert "Template: vite" in msg
    assert "About: Build a todo app. Track due dates and tags." in msg
