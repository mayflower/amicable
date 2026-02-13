from __future__ import annotations

import pytest

pytest.importorskip("langchain_core")

from langchain_core.messages import AIMessage

from src.deepagents_backend.dangerous_db_hitl import DangerousDbHitlMiddleware
from src.deepagents_backend.dangerous_ops_hitl import DangerousExecuteHitlMiddleware


def test_dangerous_execute_hitl_can_be_bypassed() -> None:
    mw = DangerousExecuteHitlMiddleware(should_interrupt=lambda _tid: False)
    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "execute",
                        "id": "1",
                        "args": {"command": "rm -rf tmp"},
                    }
                ],
            )
        ]
    }
    assert mw.after_model(state) is None


def test_dangerous_db_hitl_can_be_bypassed() -> None:
    mw = DangerousDbHitlMiddleware(should_interrupt=lambda _tid: False)
    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "db_drop_table",
                        "id": "1",
                        "args": {"table": "users"},
                    }
                ],
            )
        ]
    }
    assert mw.after_model(state) is None
