from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from src.db.hasura_client import HasuraClient


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


def ensure_schema_editor_meta_tables(client: HasuraClient) -> None:
    client.run_sql(
        """
        CREATE SCHEMA IF NOT EXISTS amicable_meta;

        CREATE TABLE IF NOT EXISTS amicable_meta.schema_labels (
          app_id text NOT NULL,
          object_kind text NOT NULL,
          table_name text NOT NULL,
          column_name text NULL,
          label text NOT NULL,
          updated_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (app_id, object_kind, table_name, column_name)
        );

        CREATE TABLE IF NOT EXISTS amicable_meta.schema_layout (
          app_id text NOT NULL,
          table_name text NOT NULL,
          pos_x double precision NOT NULL,
          pos_y double precision NOT NULL,
          updated_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (app_id, table_name)
        );
        """.strip()
    )


def load_labels_and_layout(client: HasuraClient, *, app_id: str) -> dict[str, Any]:
    ensure_schema_editor_meta_tables(client)

    labels_res = client.run_sql(
        f"""
        SELECT object_kind, table_name, column_name, label
        FROM amicable_meta.schema_labels
        WHERE app_id = {_sql_str(app_id)};
        """.strip(),
        read_only=True,
    )
    layout_res = client.run_sql(
        f"""
        SELECT table_name, pos_x, pos_y
        FROM amicable_meta.schema_layout
        WHERE app_id = {_sql_str(app_id)};
        """.strip(),
        read_only=True,
    )

    table_labels: dict[str, str] = {}
    column_labels: dict[tuple[str, str], str] = {}
    for row in _rows_from_tuples(labels_res):
        kind = str(row.get("object_kind") or "")
        tname = str(row.get("table_name") or "")
        cname = row.get("column_name")
        label = str(row.get("label") or "")
        if not tname or not label:
            continue
        if kind == "table":
            table_labels[tname] = label
            continue
        if kind == "column" and isinstance(cname, str) and cname:
            column_labels[(tname, cname)] = label

    layout: dict[str, dict[str, float]] = {}
    for row in _rows_from_tuples(layout_res):
        tname = str(row.get("table_name") or "")
        if not tname:
            continue
        try:
            x = float(row.get("pos_x") or 0.0)
            y = float(row.get("pos_y") or 0.0)
        except Exception:
            x, y = 0.0, 0.0
        layout[tname] = {"x": x, "y": y}

    return {
        "table_labels": table_labels,
        "column_labels": column_labels,
        "layout": layout,
    }


def persist_draft_ui_state(client: HasuraClient, *, app_id: str, draft: dict[str, Any]) -> None:
    ensure_schema_editor_meta_tables(client)

    tables = draft.get("tables")
    if not isinstance(tables, list):
        tables = []

    # Replace old state for this app to avoid stale entries after renames/deletes.
    client.run_sql(
        f"""
        DELETE FROM amicable_meta.schema_labels WHERE app_id = {_sql_str(app_id)};
        DELETE FROM amicable_meta.schema_layout WHERE app_id = {_sql_str(app_id)};
        """.strip()
    )

    for table in tables:
        if not isinstance(table, dict):
            continue
        tname = str(table.get("name") or "")
        tlabel = str(table.get("label") or "")
        if not tname:
            continue
        if tlabel:
            client.run_sql(
                f"""
                INSERT INTO amicable_meta.schema_labels (
                  app_id, object_kind, table_name, column_name, label, updated_at
                ) VALUES (
                  {_sql_str(app_id)}, 'table', {_sql_str(tname)}, NULL, {_sql_str(tlabel)}, now()
                );
                """.strip()
            )

        pos = table.get("position")
        if isinstance(pos, dict):
            try:
                x = float(pos.get("x") or 0.0)
                y = float(pos.get("y") or 0.0)
                client.run_sql(
                    f"""
                    INSERT INTO amicable_meta.schema_layout (
                      app_id, table_name, pos_x, pos_y, updated_at
                    ) VALUES (
                      {_sql_str(app_id)}, {_sql_str(tname)}, {x}, {y}, now()
                    );
                    """.strip()
                )
            except Exception:
                pass

        cols = table.get("columns")
        if not isinstance(cols, list):
            continue
        for col in cols:
            if not isinstance(col, dict):
                continue
            cname = str(col.get("name") or "")
            clabel = str(col.get("label") or "")
            if not cname or not clabel:
                continue
            client.run_sql(
                f"""
                INSERT INTO amicable_meta.schema_labels (
                  app_id, object_kind, table_name, column_name, label, updated_at
                ) VALUES (
                  {_sql_str(app_id)}, 'column', {_sql_str(tname)}, {_sql_str(cname)}, {_sql_str(clabel)}, now()
                );
                """.strip()
            )
