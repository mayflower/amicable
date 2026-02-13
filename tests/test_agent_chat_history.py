from __future__ import annotations

import asyncio

import pytest

from src.agent_core import Agent, ChatHistoryPersistenceError


class _MsgObj:
    def __init__(self, role: str, content):
        self.role = role
        self.content = content


class _ControllerWithState:
    def __init__(self, state):
        self._state = state

    async def aget_state(self, config=None):  # noqa: ARG002
        return self._state


def test_ws_history_requires_persistent_checkpointer() -> None:
    agent = Agent()

    async def _no_checkpointer():
        return None

    agent._get_langgraph_checkpointer = _no_checkpointer  # type: ignore[method-assign]

    with pytest.raises(ChatHistoryPersistenceError) as exc:
        asyncio.run(agent.ensure_ws_chat_history_ready("sess-history"))

    assert exc.value.code == "chat_history_persistence_required"


def test_ws_history_restores_from_checkpoint_and_sanitizes() -> None:
    agent = Agent()
    session_id = "sess-restore"

    async def _checkpointer_ok():
        return object()

    async def _noop():
        return None

    agent._get_langgraph_checkpointer = _checkpointer_ok  # type: ignore[method-assign]
    agent._ensure_deep_agent = _noop  # type: ignore[method-assign]
    agent._deep_controller = _ControllerWithState(
        {
            "values": {
                "messages": [
                    (
                        "human",
                        (
                            "Thinking level: think_hard\n\n"
                            "Workspace instruction context:\nctx\n\n"
                            "User request:\n"
                            "Compacted conversation context:\nold\n\n"
                            "Current request:\n"
                            "Please add a navbar"
                        ),
                    ),
                    {"role": "assistant", "content": "Sure, adding one now."},
                    {
                        "type": "human",
                        "content": (
                            "QA failed on `npm run -s build` (exit 1). Output:\n\nboom\n\n"
                            "Please fix the cause, then make QA pass. "
                            "If dependencies are missing, run `npm install`. "
                            "After edits, ensure `npm run -s build` succeeds."
                        ),
                    },
                    _MsgObj("ai", [{"type": "text", "text": "Done."}]),
                    {"role": "user", "text": "Thanks"},
                    {"role": "system", "content": "ignored"},
                ]
            }
        }
    )

    out = asyncio.run(agent.ensure_ws_chat_history_ready(session_id))

    assert out == [
        {"role": "user", "text": "Please add a navbar"},
        {"role": "assistant", "text": "Sure, adding one now."},
        {"role": "assistant", "text": "Done."},
        {"role": "user", "text": "Thanks"},
    ]
    stored = agent.session_data[session_id]["_conversation_history"]
    assert stored == out
    assert all("Workspace instruction context:" not in row["text"] for row in out)


def test_ws_history_returns_last_twenty_messages_in_order() -> None:
    agent = Agent()
    session_id = "sess-last-20"

    async def _checkpointer_ok():
        return object()

    async def _noop():
        return None

    msgs = []
    for i in range(30):
        if i % 2 == 0:
            msgs.append({"role": "user", "content": f"user-{i}"})
        else:
            msgs.append({"role": "assistant", "content": f"assistant-{i}"})

    agent._get_langgraph_checkpointer = _checkpointer_ok  # type: ignore[method-assign]
    agent._ensure_deep_agent = _noop  # type: ignore[method-assign]
    agent._deep_controller = _ControllerWithState({"values": {"messages": msgs}})

    out = asyncio.run(agent.ensure_ws_chat_history_ready(session_id))

    assert len(out) == 20
    assert out[0] == {"role": "user", "text": "user-10"}
    assert out[-1] == {"role": "assistant", "text": "assistant-29"}

    stored = agent.session_data[session_id]["_conversation_history"]
    assert len(stored) == 30
    assert stored[0] == {"role": "user", "text": "user-0"}


def test_ws_history_uses_existing_in_memory_history_without_checkpoint_fetch() -> None:
    agent = Agent()
    session_id = "sess-memory"
    agent.session_data[session_id] = {
        "_conversation_history": [
            {"role": "user", "text": "hello"},
            {"role": "assistant", "text": "hi"},
            {"role": "system", "text": "ignored"},
        ]
    }

    async def _checkpointer_ok():
        return object()

    async def _should_not_run():
        raise AssertionError("_ensure_deep_agent should not run with in-memory history")

    agent._get_langgraph_checkpointer = _checkpointer_ok  # type: ignore[method-assign]
    agent._ensure_deep_agent = _should_not_run  # type: ignore[method-assign]

    out = asyncio.run(agent.ensure_ws_chat_history_ready(session_id))

    assert out == [
        {"role": "user", "text": "hello"},
        {"role": "assistant", "text": "hi"},
    ]
