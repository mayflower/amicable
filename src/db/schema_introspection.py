from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from src.db.hasura_client import HasuraClient
from src.db.schema_meta import load_labels_and_layout


def _sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _rows_from_tuples(res: dict[str, Any]) -> list[dict[str, Any]]:
    rows = res.get("result")
    if not isinstance(rows, list) or len(rows) < 2:
        return []
    header = rows[0]
    if not isinstance(header, list):
        return []
    out: list[dict[str, Any]] = []
    for raw in rows[1:]:
        if not isinstance(raw, list):
            continue
        row: dict[str, Any] = {}
        for idx, col in enumerate(header):
            if isinstance(col, str) and idx < len(raw):
                row[col] = raw[idx]
        out.append(row)
    return out


def _humanize_ident(name: str) -> str:
    return str(name).replace("_", " ").strip().title()


def introspect_schema(
    client: HasuraClient,
    *,
    app_id: str,
    schema_name: str,
) -> dict[str, Any]:
    tables_res = client.run_sql(
        f"""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = {_sql_str(schema_name)}
          AND table_type = 'BASE TABLE'
        ORDER BY table_name;
        """.strip(),
        read_only=True,
    )

    cols_res = client.run_sql(
        f"""
        SELECT
          table_name,
          column_name,
          data_type,
          is_nullable,
          column_default,
          ordinal_position,
          udt_name
        FROM information_schema.columns
        WHERE table_schema = {_sql_str(schema_name)}
        ORDER BY table_name, ordinal_position;
        """.strip(),
        read_only=True,
    )

    pks_res = client.run_sql(
        f"""
        SELECT kcu.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        WHERE tc.table_schema = {_sql_str(schema_name)}
          AND tc.constraint_type = 'PRIMARY KEY';
        """.strip(),
        read_only=True,
    )

    fks_res = client.run_sql(
        f"""
        SELECT
          tc.constraint_name,
          kcu.table_name AS from_table,
          kcu.column_name AS from_column,
          ccu.table_name AS to_table,
          ccu.column_name AS to_column,
          rc.update_rule,
          rc.delete_rule
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name = tc.constraint_name
         AND ccu.constraint_schema = tc.table_schema
        JOIN information_schema.referential_constraints rc
          ON rc.constraint_name = tc.constraint_name
         AND rc.constraint_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = {_sql_str(schema_name)}
        ORDER BY tc.constraint_name;
        """.strip(),
        read_only=True,
    )

    labels_layout = load_labels_and_layout(client, app_id=app_id)
    table_labels: dict[str, str] = labels_layout.get("table_labels") or {}
    column_labels: dict[tuple[str, str], str] = labels_layout.get("column_labels") or {}
    layout: dict[str, dict[str, float]] = labels_layout.get("layout") or {}

    table_names = [str(r.get("table_name") or "") for r in _rows_from_tuples(tables_res)]
    table_names = [n for n in table_names if n]

    pk_set = {
        (str(r.get("table_name") or ""), str(r.get("column_name") or ""))
        for r in _rows_from_tuples(pks_res)
    }

    cols_by_table: dict[str, list[dict[str, Any]]] = {n: [] for n in table_names}
    for row in _rows_from_tuples(cols_res):
        t = str(row.get("table_name") or "")
        c = str(row.get("column_name") or "")
        if not t or not c:
            continue
        data_type = str(row.get("data_type") or "text").lower()
        udt_name = str(row.get("udt_name") or "").lower()
        if data_type == "ARRAY".lower() and udt_name:
            data_type = udt_name
        if data_type == "timestamp with time zone":
            data_type = "timestamp with time zone"
        col = {
            "name": c,
            "label": column_labels.get((t, c), _humanize_ident(c)),
            "type": data_type,
            "nullable": str(row.get("is_nullable") or "YES").upper() == "YES",
            "default": row.get("column_default"),
            "is_primary": (t, c) in pk_set,
        }
        cols_by_table.setdefault(t, []).append(col)

    tables: list[dict[str, Any]] = []
    for idx, t in enumerate(table_names):
        pos = layout.get(t) or {"x": 64.0 + idx * 48.0, "y": 64.0 + idx * 32.0}
        tables.append(
            {
                "name": t,
                "label": table_labels.get(t, _humanize_ident(t)),
                "position": {
                    "x": float(pos.get("x") or 0.0),
                    "y": float(pos.get("y") or 0.0),
                },
                "columns": cols_by_table.get(t, []),
            }
        )

    relationships: list[dict[str, Any]] = []
    for row in _rows_from_tuples(fks_res):
        name = str(row.get("constraint_name") or "")
        from_table = str(row.get("from_table") or "")
        from_col = str(row.get("from_column") or "")
        to_table = str(row.get("to_table") or "")
        to_col = str(row.get("to_column") or "")
        if not (name and from_table and from_col and to_table and to_col):
            continue
        relationships.append(
            {
                "name": name,
                "from_table": from_table,
                "from_column": from_col,
                "to_table": to_table,
                "to_column": to_col,
                "on_update": str(row.get("update_rule") or "NO ACTION").upper(),
                "on_delete": str(row.get("delete_rule") or "NO ACTION").upper(),
            }
        )

    return {
        "app_id": app_id,
        "schema_name": schema_name,
        "tables": tables,
        "relationships": relationships,
    }
