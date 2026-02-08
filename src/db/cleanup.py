from __future__ import annotations

from typing import Any

from src.db.hasura_client import HasuraClient, HasuraError


def _sql_str(value: str) -> str:
    return "'" + (value or "").replace("'", "''") + "'"


def _tuples_to_dicts(res: dict[str, Any]) -> list[dict[str, Any]]:
    rows = res.get("result")
    if not isinstance(rows, list) or len(rows) < 2:
        return []
    header = rows[0]
    if not isinstance(header, list):
        return []
    out: list[dict[str, Any]] = []
    for r in rows[1:]:
        if not isinstance(r, list):
            continue
        d: dict[str, Any] = {}
        for idx, col in enumerate(header):
            if isinstance(col, str) and idx < len(r):
                val = r[idx]
                d[col] = None if val == "NULL" else val
        out.append(d)
    return out


def _ignore_untrack_error(e: Exception) -> bool:
    msg = str(e).lower()
    return "not tracked" in msg or "cannot untrack" in msg or "not found" in msg


def cleanup_app_db(client: HasuraClient, *, app_id: str) -> None:
    """Best-effort cleanup of per-app schema + Hasura metadata + meta rows."""
    # Read app row.
    res = client.run_sql(
        f"""
        SELECT schema_name, role_name
        FROM amicable_meta.apps
        WHERE app_id = {_sql_str(app_id)}
        LIMIT 1;
        """.strip(),
        read_only=True,
    )
    rows = _tuples_to_dicts(res)
    if not rows:
        return
    schema = str(rows[0].get("schema_name") or "")
    if not schema:
        return

    # List tables in schema.
    tables_res = client.run_sql(
        f"""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = {_sql_str(schema)} AND table_type = 'BASE TABLE';
        """.strip(),
        read_only=True,
    )
    tables = [str(r.get("table_name")) for r in _tuples_to_dicts(tables_res) if r.get("table_name")]

    # Untrack each table (ignore if not tracked).
    for t in tables:
        try:
            client.metadata(
                {
                    "type": "pg_untrack_table",
                    "args": {
                        "source": client.cfg.source_name,
                        "table": {"schema": schema, "name": t},
                        "cascade": True,
                    },
                }
            )
        except HasuraError as e:
            if not _ignore_untrack_error(e):
                raise

    # Drop schema and meta row.
    client.run_sql(f"DROP SCHEMA IF EXISTS {schema} CASCADE;")
    client.run_sql(
        f"DELETE FROM amicable_meta.apps WHERE app_id = {_sql_str(app_id)};"
    )

