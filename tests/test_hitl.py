import asyncio
from typing import Any, TypedDict

import pytest

from src.agent_core import Agent, MessageType
from src.deepagents_backend.controller_graph import build_controller_graph


class _InterruptState(TypedDict, total=False):
    messages: list[Any]


def _make_interrupt_graph():
    """A minimal graph that interrupts once, then returns an assistant message on resume."""

    pytest.importorskip("langgraph")

    from langgraph.checkpoint.memory import InMemorySaver  # type: ignore
    from langgraph.constants import END, START  # type: ignore
    from langgraph.graph import StateGraph  # type: ignore
    from langgraph.types import interrupt  # type: ignore

    def node(state: _InterruptState):
        _ = interrupt(
            {
                "action_requests": [
                    {
                        "name": "execute",
                        "args": {"command": "echo hi"},
                        "description": "Tool execution requires approval\n\nTool: execute\nArgs: {'command': 'echo hi'}",
                    }
                ],
                "review_configs": [
                    {
                        "action_name": "execute",
                        "allowed_decisions": ["approve", "edit", "reject"],
                    }
                ],
            }
        )
        msgs = list(state.get("messages") or [])
        msgs.append({"role": "assistant", "content": "resumed"})
        return {"messages": msgs}

    g = StateGraph(_InterruptState)
    g.add_node("n", node)
    g.add_edge(START, "n")
    g.add_edge("n", END)
    return g.compile(checkpointer=InMemorySaver())


def test_controller_graph_supports_resume_with_checkpointer():
    pytest.importorskip("langgraph")

    from langgraph.checkpoint.memory import InMemorySaver  # type: ignore
    from langgraph.types import Command  # type: ignore

    inner = _make_interrupt_graph()
    controller = build_controller_graph(
        deep_agent_runnable=inner,
        get_backend=lambda _tid: None,
        qa_enabled=False,
        checkpointer=InMemorySaver(),
    )

    config = {"configurable": {"thread_id": "t1"}}
    chunks = list(
        controller.stream({"messages": [("user", "hi")], "attempt": 0}, config=config)
    )
    assert any("__interrupt__" in (c or {}) for c in chunks)

    resumed = list(
        controller.stream(
            Command(resume={"decisions": [{"type": "approve"}]}), config=config
        )
    )
    assert resumed  # should complete without raising


def test_agent_emits_hitl_request_and_can_resume():
    graph = _make_interrupt_graph()
    agent = Agent()

    session_id = "sess-1"
    # Bypass sandbox init.
    agent.session_data[session_id] = {"exists": True}
    # Bypass deepagents imports.
    agent._deep_agent = object()
    agent._deep_controller = graph
    agent._session_manager = object()

    async def run_feedback():
        out = []
        async for m in agent.send_feedback(
            session_id=session_id, feedback="do something"
        ):
            out.append(m)
        return out

    msgs = asyncio.run(run_feedback())
    types = [m.get("type") for m in msgs]
    assert MessageType.UPDATE_IN_PROGRESS.value in types
    assert MessageType.HITL_REQUEST.value in types
    assert MessageType.UPDATE_COMPLETED.value not in types
    assert agent.has_pending_hitl(session_id)

    pending = agent.get_pending_hitl(session_id)
    assert pending and isinstance(pending.get("interrupt_id"), str)

    async def run_resume():
        out = []
        async for m in agent.resume_hitl(
            session_id=session_id,
            interrupt_id=pending["interrupt_id"],
            response={"decisions": [{"type": "approve"}]},
        ):
            out.append(m)
        return out

    resumed = asyncio.run(run_resume())
    resumed_types = [m.get("type") for m in resumed]
    assert MessageType.UPDATE_COMPLETED.value in resumed_types
    assert not agent.has_pending_hitl(session_id)
