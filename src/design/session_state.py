from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.design.types import DesignState

_state_by_project: dict[str, DesignState] = {}
_lock_by_project: dict[str, asyncio.Lock] = {}


def _project_key(project_id: str) -> str:
    return str(project_id or "").strip()


def get_lock(project_id: str) -> asyncio.Lock:
    key = _project_key(project_id)
    lock = _lock_by_project.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _lock_by_project[key] = lock
    return lock


def get_state(project_id: str) -> DesignState | None:
    key = _project_key(project_id)
    st = _state_by_project.get(key)
    if st is None:
        return None
    return replace(st, approaches=list(st.approaches))


def set_state(state: DesignState) -> DesignState:
    key = _project_key(state.project_id)
    next_state = replace(
        state,
        project_id=key,
        approaches=list(state.approaches),
        updated_at_ms=int(time.time() * 1000),
    )
    _state_by_project[key] = next_state
    return replace(next_state, approaches=list(next_state.approaches))


def update_state(project_id: str, **changes: object) -> DesignState | None:
    current = _state_by_project.get(_project_key(project_id))
    if current is None:
        return None
    if "approaches" in changes and isinstance(changes["approaches"], list):
        changes["approaches"] = list(changes["approaches"])
    next_state = replace(current, **changes, updated_at_ms=int(time.time() * 1000))
    _state_by_project[_project_key(project_id)] = next_state
    return replace(next_state, approaches=list(next_state.approaches))


def clear_state(project_id: str) -> None:
    _state_by_project.pop(_project_key(project_id), None)
