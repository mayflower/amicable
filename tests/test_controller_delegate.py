from __future__ import annotations

from src.deepagents_backend.controller_graph import _delegate_target_from_qa_results


def test_delegate_target_prefers_db_migrator_for_db_failures() -> None:
    target = _delegate_target_from_qa_results(
        [{"command": "npm run -s build", "output": "GraphQL relation users does not exist"}]
    )
    assert target == "db_migrator"


def test_delegate_target_defaults_to_qa_fixer() -> None:
    target = _delegate_target_from_qa_results(
        [{"command": "npm run -s lint", "output": "unused variable in component"}]
    )
    assert target == "qa_fixer"
