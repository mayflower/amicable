from __future__ import annotations

from typing import Any


def get_db_tools() -> list[Any]:
    """Return LangChain tool objects for DeepAgents.

    Imports are inside to keep local/dev env minimal (deepagents isn't installed locally).
    """

    from langchain_core.tools import tool  # type: ignore

    from src.db.context import get_current_app_id
    from src.db.hasura_client import HasuraError
    from src.db.naming import validate_pg_ident
    from src.db.provisioning import ensure_app, hasura_client_from_env

    allowed_types = {
        "text",
        "boolean",
        "int",
        "integer",
        "bigint",
        "real",
        "double precision",
        "numeric",
        "jsonb",
        "timestamptz",
        "timestamp with time zone",
        "date",
        "uuid",
    }

    def _normalize_type(t: str) -> str:
        tt = (t or "").strip().lower()
        # Normalize common aliases.
        if tt == "int":
            return "integer"
        if tt == "timestamptz":
            return "timestamp with time zone"
        return tt

    def _sql_literal(v: Any) -> str:
        if v is None:
            return "NULL"
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return str(v)
        if isinstance(v, str):
            # Basic SQL string literal escaping.
            return "'" + v.replace("'", "''") + "'"
        if isinstance(v, dict) and isinstance(v.get("raw"), str):
            raw = v["raw"].strip().lower()
            if raw == "now()":
                return "now()"
        raise ValueError(
            "unsupported default value; use bool/int/float/string or {raw:'now()'}"
        )

    def _ignore_already_exists(err: Exception) -> bool:
        msg = str(err).lower()
        return "already tracked" in msg or "already exists" in msg or "exists" in msg

    def _track_table(client, *, schema: str, table: str) -> None:
        try:
            client.metadata(
                {
                    "type": "pg_track_table",
                    "args": {
                        "source": client.cfg.source_name,
                        "table": {"schema": schema, "name": table},
                    },
                }
            )
        except HasuraError as e:
            if not _ignore_already_exists(e):
                raise

    def _untrack_table(client, *, schema: str, table: str) -> None:
        try:
            client.metadata(
                {
                    "type": "pg_untrack_table",
                    "args": {
                        "source": client.cfg.source_name,
                        "table": {"schema": schema, "name": table},
                        "cascade": True,
                    },
                }
            )
        except HasuraError as e:
            # Treat missing/untracked as ok.
            if (
                "not tracked" not in str(e).lower()
                and "cannot untrack" not in str(e).lower()
            ):
                raise

    def _ensure_crud_permissions(client, *, schema: str, table: str, role: str) -> None:
        # These metadata calls are idempotent-ish (we ignore "already exists").
        perms = [
            (
                "pg_create_select_permission",
                {
                    "columns": "*",
                    "filter": {},
                    "allow_aggregations": True,
                },
            ),
            (
                "pg_create_insert_permission",
                {
                    "columns": "*",
                    "check": {},
                    "set": {},
                },
            ),
            (
                "pg_create_update_permission",
                {
                    "columns": "*",
                    "filter": {},
                    "check": {},
                    "set": {},
                },
            ),
            (
                "pg_create_delete_permission",
                {
                    "filter": {},
                },
            ),
        ]
        for typ, permission in perms:
            try:
                client.metadata(
                    {
                        "type": typ,
                        "args": {
                            "source": client.cfg.source_name,
                            "table": {"schema": schema, "name": table},
                            "role": role,
                            "permission": permission,
                        },
                    }
                )
            except HasuraError as e:
                if not _ignore_already_exists(e):
                    raise

    @tool
    def db_create_table(table: str, columns: list[dict[str, Any]] | None = None) -> str:
        """Create a new table in this app's database schema and expose it in Hasura.

        Args:
          table: Table name (snake_case).
          columns: List of columns. Each item:
            - name: column name
            - type: postgres type (text, boolean, integer, bigint, numeric, jsonb, timestamp with time zone, date, uuid)
            - nullable: bool (default true)
            - default: bool/int/float/string or {raw:"now()"}
        """
        app_id = get_current_app_id()
        client = hasura_client_from_env()
        app = ensure_app(client, app_id=app_id)

        tname = validate_pg_ident(table)
        col_specs = columns or []
        if not isinstance(col_specs, list):
            raise ValueError("columns must be a list")

        seen: set[str] = set()
        col_sql: list[str] = ["id bigserial primary key"]
        for c in col_specs:
            if not isinstance(c, dict):
                raise ValueError("each column must be an object")
            name = validate_pg_ident(str(c.get("name") or ""))
            if name == "id":
                raise ValueError("do not specify 'id'; it is created automatically")
            if name in seen:
                raise ValueError(f"duplicate column: {name}")
            seen.add(name)

            typ_raw = str(c.get("type") or "")
            typ = _normalize_type(typ_raw)
            if typ not in {_normalize_type(t) for t in allowed_types}:
                raise ValueError(f"unsupported column type: {typ_raw!r}")

            nullable = c.get("nullable")
            not_null = nullable is False
            default = c.get("default", None)

            piece = f"{name} {typ}"
            if not_null:
                piece += " NOT NULL"
            if "default" in c:
                piece += f" DEFAULT {_sql_literal(default)}"
            col_sql.append(piece)

        sql = f"CREATE TABLE IF NOT EXISTS {app.schema_name}.{tname} ({', '.join(col_sql)});"
        client.run_sql(sql)

        _track_table(client, schema=app.schema_name, table=tname)
        _ensure_crud_permissions(
            client, schema=app.schema_name, table=tname, role=app.role_name
        )

        return f"created table {app.schema_name}.{tname} and granted CRUD permissions to role {app.role_name}"

    @tool
    def db_truncate_table(table: str) -> str:
        """TRUNCATE a table in this app's schema (destructive)."""
        app_id = get_current_app_id()
        client = hasura_client_from_env()
        app = ensure_app(client, app_id=app_id)
        tname = validate_pg_ident(table)
        client.run_sql(f"TRUNCATE TABLE {app.schema_name}.{tname};")
        return f"truncated {app.schema_name}.{tname}"

    @tool
    def db_drop_table(table: str) -> str:
        """DROP a table in this app's schema (destructive)."""
        app_id = get_current_app_id()
        client = hasura_client_from_env()
        app = ensure_app(client, app_id=app_id)
        tname = validate_pg_ident(table)
        _untrack_table(client, schema=app.schema_name, table=tname)
        client.run_sql(f"DROP TABLE IF EXISTS {app.schema_name}.{tname} CASCADE;")
        return f"dropped {app.schema_name}.{tname}"

    return [db_create_table, db_truncate_table, db_drop_table]
