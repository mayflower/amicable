from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.db.hasura_client import HasuraClient
    from src.design.types import DesignState

_state_by_project: dict[str, DesignState] = {}
_lock_by_project: dict[str, asyncio.Lock] = {}

_log = logging.getLogger(__name__)

# ── Postgres persistence helpers ──────────────────────────────────────

_schema_ready = False
_schema_lock = threading.Lock()


def ensure_design_schema(client: HasuraClient) -> None:
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        _log.info("Running design_states schema migration (once per process)")
        client.run_sql(
            """
            CREATE SCHEMA IF NOT EXISTS amicable_meta;
            CREATE TABLE IF NOT EXISTS amicable_meta.design_states (
              project_id text PRIMARY KEY,
              state_json jsonb NOT NULL,
              updated_at timestamptz NOT NULL DEFAULT now()
            );
            """.strip()
        )
        _schema_ready = True


def _get_client() -> HasuraClient | None:
    """Return a HasuraClient if Hasura is configured, else None."""
    import os

    if not os.environ.get("HASURA_BASE_URL") or not os.environ.get(
        "HASURA_GRAPHQL_ADMIN_SECRET"
    ):
        return None
    try:
        from src.db.provisioning import hasura_client_from_env

        return hasura_client_from_env()
    except Exception:
        _log.debug("Hasura not available for design state persistence", exc_info=True)
        return None


def _sql_str(value: str) -> str:
    return "'" + (value or "").replace("'", "''") + "'"


def _save_to_db(state: DesignState) -> None:
    client = _get_client()
    if client is None:
        return
    try:
        ensure_design_schema(client)
        state_json = json.dumps(state.to_dict(), ensure_ascii=False)
        client.run_sql(
            f"""
            INSERT INTO amicable_meta.design_states (project_id, state_json, updated_at)
            VALUES ({_sql_str(state.project_id)}, {_sql_str(state_json)}::jsonb, now())
            ON CONFLICT (project_id) DO UPDATE
              SET state_json = EXCLUDED.state_json, updated_at = now();
            """.strip()
        )
    except Exception:
        _log.warning("Failed to persist design state to DB", exc_info=True)


def _load_from_db(project_id: str) -> DesignState | None:
    client = _get_client()
    if client is None:
        return None
    try:
        ensure_design_schema(client)
        res = client.run_sql(
            f"""
            SELECT state_json
            FROM amicable_meta.design_states
            WHERE project_id = {_sql_str(project_id)}
            LIMIT 1;
            """.strip(),
            read_only=True,
        )
        rows = res.get("result")
        if not isinstance(rows, list) or len(rows) < 2:
            return None
        raw = rows[1][0]
        if raw is None or raw == "NULL":
            return None
        d = json.loads(raw) if isinstance(raw, str) else raw
        from src.design.types import DesignState as DesignStateType

        return DesignStateType.from_dict(d)
    except Exception:
        _log.warning("Failed to load design state from DB", exc_info=True)
        return None


def _delete_from_db(project_id: str) -> None:
    client = _get_client()
    if client is None:
        return
    try:
        ensure_design_schema(client)
        client.run_sql(
            f"""
            DELETE FROM amicable_meta.design_states
            WHERE project_id = {_sql_str(project_id)};
            """.strip()
        )
    except Exception:
        _log.warning("Failed to delete design state from DB", exc_info=True)


# ── Public API (unchanged signatures) ────────────────────────────────


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
        # Cache miss — try Postgres
        st = _load_from_db(key)
        if st is None:
            return None
        _state_by_project[key] = st
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
    _save_to_db(next_state)
    return replace(next_state, approaches=list(next_state.approaches))


def update_state(project_id: str, **changes: object) -> DesignState | None:
    key = _project_key(project_id)
    current = _state_by_project.get(key)
    if current is None:
        # Cache miss — try Postgres before giving up
        current = _load_from_db(key)
        if current is None:
            return None
        _state_by_project[key] = current
    if "approaches" in changes and isinstance(changes["approaches"], list):
        changes["approaches"] = list(changes["approaches"])
    next_state = replace(current, **changes, updated_at_ms=int(time.time() * 1000))
    _state_by_project[key] = next_state
    _save_to_db(next_state)
    return replace(next_state, approaches=list(next_state.approaches))


def clear_state(project_id: str) -> None:
    _state_by_project.pop(_project_key(project_id), None)
    _delete_from_db(_project_key(project_id))
