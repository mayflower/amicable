from __future__ import annotations

import asyncio

from src.agent_hooks import AgentHookBus


def test_hook_bus_no_handlers_returns_called_false() -> None:
    bus = AgentHookBus(timeout_ms=200)
    out = asyncio.run(bus.emit("session_start", {"session_id": "s1"}))
    assert out["called"] is False
    assert out["results"] == []


def test_hook_bus_runs_sync_and_async_handlers() -> None:
    bus = AgentHookBus(timeout_ms=200)

    def sync_handler(payload: dict):
        return {"sync": payload.get("session_id")}

    async def async_handler(payload: dict):
        await asyncio.sleep(0)
        return {"async": payload.get("session_id")}

    bus.on("session_start", sync_handler)
    bus.on("session_start", async_handler)

    out = asyncio.run(bus.emit("session_start", {"session_id": "s2"}))
    assert out["called"] is True
    assert len(out["results"]) == 2
    assert all(r.get("status") == "ok" for r in out["results"])


def test_hook_bus_fail_open_on_errors_and_timeouts() -> None:
    bus = AgentHookBus(timeout_ms=20)

    async def slow_handler(_payload: dict):
        await asyncio.sleep(0.2)
        return {"slow": True}

    def boom_handler(_payload: dict):
        raise RuntimeError("boom")

    bus.on("stop", slow_handler)
    bus.on("stop", boom_handler)

    out = asyncio.run(bus.emit("stop", {"session_id": "s3"}))
    statuses = {str(r.get("status")) for r in out["results"]}
    assert "timeout" in statuses
    assert "error" in statuses
