from __future__ import annotations

import asyncio
import inspect

import pytest

from src.agent_core import Agent


class _FailingBackend:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, _command: str):
        self.calls += 1
        raise RuntimeError("boom")


def test_runtime_probe_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"t": 0.0}

    def _monotonic() -> float:
        return clock["t"]

    def _sleep(delta_s: float) -> None:
        clock["t"] += float(delta_s)

    monkeypatch.setenv("K8S_RUNTIME_READY_TIMEOUT_S", "1")
    monkeypatch.setenv("K8S_RUNTIME_READY_POLL_MS", "250")
    monkeypatch.setattr("src.agent_core.time.monotonic", _monotonic)
    monkeypatch.setattr("src.agent_core.time.sleep", _sleep)

    agent = Agent()
    backend = _FailingBackend()
    with pytest.raises(RuntimeError, match="timeout_s=1"):
        agent._probe_runtime_or_raise(
            backend=backend, session_id="s1", sandbox_id="sb1"
        )
    assert backend.calls == 5


def test_cleanup_session_state_clears_agent_maps() -> None:
    agent = Agent()
    sid = "session-1"
    agent.session_data[sid] = {"k": "v"}
    agent._hitl_pending[sid] = {"interrupt_id": "i"}
    agent._ensure_env_lock_by_session[sid] = asyncio.Lock()

    agent.cleanup_session_state(sid)

    assert sid not in agent.session_data
    assert sid not in agent._hitl_pending
    assert sid not in agent._ensure_env_lock_by_session


def test_no_default_thread_backend_bootstrap_call() -> None:
    src = inspect.getsource(Agent._ensure_deep_agent)
    assert 'get_backend("default-thread")' not in src


def test_restore_pending_hitl_from_checkpoint_rehydrates() -> None:
    agent = Agent()

    async def _fake_checkpointer():
        return object()

    async def _fake_snapshot(_session_id: str):
        return {
            "values": {
                "__interrupt__": [
                    {"id": "intr-1", "value": {"action_requests": [], "review_configs": []}}
                ]
            }
        }

    agent._get_langgraph_checkpointer = _fake_checkpointer  # type: ignore[method-assign]
    agent._controller_state_snapshot = _fake_snapshot  # type: ignore[method-assign]

    out = asyncio.run(agent.restore_pending_hitl_from_checkpoint("sess-1"))
    assert out is not None
    assert out.get("interrupt_id") == "intr-1"
