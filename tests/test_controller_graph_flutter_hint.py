from __future__ import annotations

from typing import Any

import pytest

from src.deepagents_backend.controller_graph import build_controller_graph


class _FlutterFailingBackend:
    def execute(self, command: str) -> dict[str, Any]:
        if "test -e package.json" in command:
            return {"exit_code": 1, "output": "", "truncated": False}
        if "test -e pyproject.toml" in command:
            return {"exit_code": 1, "output": "", "truncated": False}
        if "test -e requirements.txt" in command:
            return {"exit_code": 1, "output": "", "truncated": False}
        if "test -e pubspec.yaml" in command:
            return {"exit_code": 0, "output": "", "truncated": False}
        if "flutter pub get" in command:
            return {"exit_code": 1, "output": "pub get failed", "truncated": False}
        return {"exit_code": 0, "output": "", "truncated": False}


def _message_content(msg: Any) -> str:
    if isinstance(msg, tuple) and len(msg) >= 2:
        return str(msg[1])
    content = getattr(msg, "content", "")
    return str(content) if isinstance(content, str) else ""


def test_self_heal_hint_uses_flutter_guidance(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("langgraph")

    from langchain_core.runnables import RunnableLambda

    monkeypatch.setenv("DEEPAGENTS_SELF_HEAL_MAX_ROUNDS", "1")

    backend = _FlutterFailingBackend()
    deep_agent = RunnableLambda(lambda state: {"messages": state.get("messages", [])})
    controller = build_controller_graph(
        deep_agent_runnable=deep_agent,
        get_backend=lambda _tid: backend,
        qa_enabled=True,
    )

    out = controller.invoke(
        {"messages": [("user", "fix app")], "attempt": 0},
        config={"configurable": {"thread_id": "thread-1"}},
    )

    contents = [_message_content(m) for m in (out.get("messages") or [])]
    joined = "\n".join(c for c in contents if c)
    assert "flutter pub get" in joined
    assert "flutter analyze" in joined


def test_environment_qa_failure_skips_self_heal(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("langgraph")

    from langchain_core.runnables import RunnableLambda

    monkeypatch.setenv("DEEPAGENTS_SELF_HEAL_MAX_ROUNDS", "3")

    backend = _FlutterFailingBackend()
    calls = {"count": 0}

    def _deep_agent(state: dict[str, Any]) -> dict[str, Any]:
        calls["count"] += 1
        return {"messages": state.get("messages", [])}

    orig_execute = backend.execute

    def _backend_execute(command: str) -> dict[str, Any]:
        if "flutter pub get" in command:
            return {
                "exit_code": 127,
                "output": "sh: 1: flutter: not found",
                "truncated": False,
            }
        return orig_execute(command)

    backend.execute = _backend_execute  # type: ignore[method-assign]

    controller = build_controller_graph(
        deep_agent_runnable=RunnableLambda(_deep_agent),
        get_backend=lambda _tid: backend,
        qa_enabled=True,
    )

    out = controller.invoke(
        {"messages": [("user", "fix app")], "attempt": 0},
        config={"configurable": {"thread_id": "thread-2"}},
    )

    contents = [_message_content(m) for m in (out.get("messages") or [])]
    joined = "\n".join(c for c in contents if c)
    assert "sandbox environment/setup issue" in joined
    assert calls["count"] == 1
