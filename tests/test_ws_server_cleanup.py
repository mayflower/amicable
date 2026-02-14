from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("dotenv")
pytest.importorskip("fastapi")

from src.runtimes import ws_server


def test_cleanup_project_runtime_state_clears_in_memory_maps() -> None:
    sid = "project-1"
    ws_server._bootstrap_lock_by_project[sid] = asyncio.Lock()
    ws_server._git_pull_lock_by_project[sid] = asyncio.Lock()
    ws_server._agent_run_lock_by_project[sid] = asyncio.Lock()
    ws_server._runtime_autoheal_state_by_project[sid] = {"x": 1}

    ws_server._cleanup_project_runtime_state(sid)

    assert sid not in ws_server._bootstrap_lock_by_project
    assert sid not in ws_server._git_pull_lock_by_project
    assert sid not in ws_server._agent_run_lock_by_project
    assert sid not in ws_server._runtime_autoheal_state_by_project
