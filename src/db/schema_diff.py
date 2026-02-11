from __future__ import annotations

import hashlib
import json
from typing import Any

from src.db.naming import dedupe_identifier, identifier_from_label, validate_pg_ident

_ALLOWED_COLUMN_TYPES = {
    "text",
    "boolean",
    "integer",
    "bigint",
    "real",
    "double precision",
    "numeric",
    "jsonb",
    "timestamp with time zone",
    "date",
    "uuid",
    "bigserial",
    "serial",
}

_TYPE_ALIASES = {
    "string": "text",
    "text": "text",
    "number": "integer",
    "int": "integer",
    "integer": "integer",
    "bool": "boolean",
    "boolean": "boolean",
    "json": "jsonb",
    "jsonb": "jsonb",
    "date": "date",
    "uuid": "uuid",
    "timestamp": "timestamp with time zone",
    "timestamptz": "timestamp with time zone",
    "bigint": "bigint",
    "numeric": "numeric",
    "float": "real",
    "real": "real",
    "double": "double precision",
    "double precision": "double precision",
    "serial": "serial",
    "bigserial": "bigserial",
}

_FK_RULES = {"NO ACTION", "RESTRICT", "CASCADE", "SET NULL", "SET DEFAULT"}


class SchemaValidationError(ValueError):
    pass


def quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _q_table(schema_name: str, table_name: str) -> str:
    return f"{quote_ident(schema_name)}.{quote_ident(table_name)}"


def _canonical_default(v: Any) -> str:
    try:
        return json.dumps(v, sort_keys=True, separators=(",", ":"), default=str)
    except Exception:
        return str(v)


def _normalize_column_type(raw: str) -> str:
    t = (raw or "").strip().lower()
    t = _TYPE_ALIASES.get(t, t)
    if t not in _ALLOWED_COLUMN_TYPES:
        raise SchemaValidationError(f"unsupported column type: {raw!r}")
    return t


def _sql_literal(v: Any) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, dict) and isinstance(v.get("raw"), str):
        return str(v["raw"])
    if isinstance(v, str):
        return "'" + v.replace("'", "''") + "'"
    raise SchemaValidationError(
        "unsupported default value; use bool/int/float/string or {raw:'...'}"
    )


def _humanize_ident(name: str) -> str:
    return str(name).replace("_", " ").strip().title()


def normalize_schema_model(
    model: dict[str, Any],
    *,
    generate_missing_names: bool,
) -> dict[str, Any]:
    if not isinstance(model, dict):
        raise SchemaValidationError("schema model must be an object")

    tables_raw = model.get("tables")
    rels_raw = model.get("relationships")

    if tables_raw is None:
        tables_raw = []
    if rels_raw is None:
        rels_raw = []
    if not isinstance(tables_raw, list):
        raise SchemaValidationError("tables must be a list")
    if not isinstance(rels_raw, list):
        raise SchemaValidationError("relationships must be a list")

    used_tables: set[str] = set()
    tables_out: list[dict[str, Any]] = []

    for idx, table in enumerate(tables_raw):
        if not isinstance(table, dict):
            raise SchemaValidationError("each table must be an object")

        label = str(table.get("label") or "").strip()
        tname_raw = str(table.get("name") or "").strip().lower()
        if not tname_raw:
            if not generate_missing_names:
                raise SchemaValidationError("table.name is required")
            tname_raw = identifier_from_label(
                label or f"table {idx + 1}", fallback_prefix="table"
            )
        else:
            tname_raw = validate_pg_ident(tname_raw)

        tname = dedupe_identifier(tname_raw, used_tables)
        if not label:
            label = _humanize_ident(tname)

        pos = table.get("position")
        px = 64.0 + idx * 48.0
        py = 64.0 + idx * 32.0
        if isinstance(pos, dict):
            try:
                px = float(pos.get("x") or px)
                py = float(pos.get("y") or py)
            except Exception:
                pass

        cols_raw = table.get("columns")
        if cols_raw is None:
            cols_raw = []
        if not isinstance(cols_raw, list):
            raise SchemaValidationError(f"table.columns must be a list for {tname}")

        used_cols: set[str] = set()
        cols_out: list[dict[str, Any]] = []
        for cidx, col in enumerate(cols_raw):
            if not isinstance(col, dict):
                raise SchemaValidationError("each column must be an object")

            clabel = str(col.get("label") or "").strip()
            cname_raw = str(col.get("name") or "").strip().lower()
            if not cname_raw:
                if not generate_missing_names:
                    raise SchemaValidationError(
                        f"column.name is required ({tname} column #{cidx + 1})"
                    )
                cname_raw = identifier_from_label(
                    clabel or f"column {cidx + 1}", fallback_prefix="col"
                )
            else:
                cname_raw = validate_pg_ident(cname_raw)

            cname = dedupe_identifier(cname_raw, used_cols)
            if not clabel:
                clabel = _humanize_ident(cname)

            ctype = _normalize_column_type(str(col.get("type") or "text"))
            nullable = bool(col.get("nullable", True))
            is_primary = bool(col.get("is_primary", False))
            default = col.get("default") if "default" in col else None

            cols_out.append(
                {
                    "name": cname,
                    "label": clabel,
                    "type": ctype,
                    "nullable": bool(nullable),
                    "is_primary": bool(is_primary),
                    "default": default,
                }
            )

        tables_out.append(
            {
                "name": tname,
                "label": label,
                "position": {"x": px, "y": py},
                "columns": cols_out,
            }
        )

    table_names = {t["name"] for t in tables_out}
    cols_by_table = {
        t["name"]: {c["name"] for c in t.get("columns", [])}
        for t in tables_out
    }
    if generate_missing_names:
        for t in tables_out:
            tname = str(t.get("name") or "")
            if not tname:
                continue
            cols = cols_by_table.setdefault(tname, set())
            if "id" not in cols:
                cols.add("id")

    rels_out: list[dict[str, Any]] = []
    used_rel_names: set[str] = set()
    for rel in rels_raw:
        if not isinstance(rel, dict):
            raise SchemaValidationError("each relationship must be an object")

        from_table = validate_pg_ident(str(rel.get("from_table") or "").strip().lower())
        from_col = validate_pg_ident(str(rel.get("from_column") or "").strip().lower())
        to_table = validate_pg_ident(str(rel.get("to_table") or "").strip().lower())
        to_col = validate_pg_ident(str(rel.get("to_column") or "").strip().lower())

        if from_table not in table_names:
            raise SchemaValidationError(f"relationship source table not found: {from_table}")
        if to_table not in table_names:
            raise SchemaValidationError(f"relationship target table not found: {to_table}")
        if from_col not in cols_by_table.get(from_table, set()):
            raise SchemaValidationError(
                f"relationship source column not found: {from_table}.{from_col}"
            )
        if to_col not in cols_by_table.get(to_table, set()):
            raise SchemaValidationError(
                f"relationship target column not found: {to_table}.{to_col}"
            )

        rname_raw = str(rel.get("name") or "").strip().lower()
        if not rname_raw:
            rname_raw = identifier_from_label(
                f"{from_table}_{from_col}_to_{to_table}", fallback_prefix="fk"
            )
        else:
            rname_raw = validate_pg_ident(rname_raw)

        rname = dedupe_identifier(rname_raw, used_rel_names)

        on_delete = str(rel.get("on_delete") or "NO ACTION").upper().strip()
        on_update = str(rel.get("on_update") or "NO ACTION").upper().strip()
        if on_delete not in _FK_RULES:
            on_delete = "NO ACTION"
        if on_update not in _FK_RULES:
            on_update = "NO ACTION"

        rels_out.append(
            {
                "name": rname,
                "from_table": from_table,
                "from_column": from_col,
                "to_table": to_table,
                "to_column": to_col,
                "on_delete": on_delete,
                "on_update": on_update,
            }
        )

    return {
        "app_id": str(model.get("app_id") or ""),
        "schema_name": str(model.get("schema_name") or ""),
        "tables": tables_out,
        "relationships": rels_out,
    }


def canonical_schema(schema: dict[str, Any]) -> dict[str, Any]:
    norm = normalize_schema_model(schema, generate_missing_names=False)

    tables = []
    for t in sorted(norm.get("tables", []), key=lambda x: str(x.get("name") or "")):
        cols = sorted(t.get("columns", []), key=lambda x: str(x.get("name") or ""))
        tables.append(
            {
                "name": t.get("name"),
                "label": t.get("label"),
                "position": t.get("position"),
                "columns": [
                    {
                        "name": c.get("name"),
                        "label": c.get("label"),
                        "type": c.get("type"),
                        "nullable": bool(c.get("nullable", True)),
                        "is_primary": bool(c.get("is_primary", False)),
                        "default": c.get("default") if "default" in c else None,
                    }
                    for c in cols
                ],
            }
        )

    rels = sorted(
        norm.get("relationships", []),
        key=lambda x: (
            str(x.get("name") or ""),
            str(x.get("from_table") or ""),
            str(x.get("from_column") or ""),
            str(x.get("to_table") or ""),
            str(x.get("to_column") or ""),
        ),
    )

    return {
        "app_id": norm.get("app_id") or "",
        "schema_name": norm.get("schema_name") or "",
        "tables": tables,
        "relationships": rels,
    }


def compute_schema_version(schema: dict[str, Any]) -> str:
    can = canonical_schema(schema)
    encoded = json.dumps(can, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _col_def_sql(col: dict[str, Any]) -> str:
    parts = [f"{quote_ident(str(col['name']))} {col['type']}"]
    if col.get("is_primary"):
        parts.append("PRIMARY KEY")
    if not bool(col.get("nullable", True)) and not col.get("is_primary"):
        parts.append("NOT NULL")
    if "default" in col and col.get("default") is not None:
        parts.append(f"DEFAULT {_sql_literal(col.get('default'))}")
    return " ".join(parts)


def _sql_for_operation(op: dict[str, Any], *, schema_name: str) -> list[str]:
    t = str(op.get("type") or "")
    if t == "add_table":
        table = str(op["table"])
        cols = list(op.get("columns") or [])
        if not cols:
            cols = [{"name": "id", "type": "bigserial", "nullable": False, "is_primary": True}]
        col_defs = [_col_def_sql(c) for c in cols]

        # Add table-level PK if multiple columns are marked primary.
        pk_cols = [quote_ident(str(c.get("name"))) for c in cols if c.get("is_primary")]
        if len(pk_cols) > 1:
            col_defs.append(f"PRIMARY KEY ({', '.join(pk_cols)})")

        return [f"CREATE TABLE IF NOT EXISTS {_q_table(schema_name, table)} ({', '.join(col_defs)});"]

    if t == "drop_table":
        return [f"DROP TABLE IF EXISTS {_q_table(schema_name, str(op['table']))} CASCADE;"]

    if t == "add_column":
        col = op["column"]
        return [
            f"ALTER TABLE {_q_table(schema_name, str(op['table']))} "
            f"ADD COLUMN IF NOT EXISTS {_col_def_sql(col)};"
        ]

    if t == "drop_column":
        return [
            f"ALTER TABLE {_q_table(schema_name, str(op['table']))} "
            f"DROP COLUMN IF EXISTS {quote_ident(str(op['column']))} CASCADE;"
        ]

    if t == "alter_column":
        table = str(op["table"])
        col = quote_ident(str(op["column"]))
        sql: list[str] = []
        if "new_type" in op:
            sql.append(
                f"ALTER TABLE {_q_table(schema_name, table)} ALTER COLUMN {col} TYPE {op['new_type']!s};"
            )
        if "new_nullable" in op:
            if bool(op["new_nullable"]):
                sql.append(
                    f"ALTER TABLE {_q_table(schema_name, table)} ALTER COLUMN {col} DROP NOT NULL;"
                )
            else:
                sql.append(
                    f"ALTER TABLE {_q_table(schema_name, table)} ALTER COLUMN {col} SET NOT NULL;"
                )
        if "new_default" in op:
            d = op["new_default"]
            if d is None:
                sql.append(
                    f"ALTER TABLE {_q_table(schema_name, table)} ALTER COLUMN {col} DROP DEFAULT;"
                )
            else:
                sql.append(
                    f"ALTER TABLE {_q_table(schema_name, table)} ALTER COLUMN {col} SET DEFAULT {_sql_literal(d)};"
                )
        return sql

    if t == "add_relationship":
        return [
            f"ALTER TABLE {_q_table(schema_name, str(op['from_table']))} "
            f"ADD CONSTRAINT {quote_ident(str(op['name']))} "
            f"FOREIGN KEY ({quote_ident(str(op['from_column']))}) "
            f"REFERENCES {_q_table(schema_name, str(op['to_table']))} ({quote_ident(str(op['to_column']))}) "
            f"ON UPDATE {(op.get('on_update') or 'NO ACTION')!s} "
            f"ON DELETE {(op.get('on_delete') or 'NO ACTION')!s};"
        ]

    if t == "drop_relationship":
        return [
            f"ALTER TABLE {_q_table(schema_name, str(op['from_table']))} "
            f"DROP CONSTRAINT IF EXISTS {quote_ident(str(op['name']))};"
        ]

    return []


def build_schema_diff(
    current_schema: dict[str, Any],
    draft_schema: dict[str, Any],
) -> dict[str, Any]:
    current = normalize_schema_model(current_schema, generate_missing_names=False)
    draft = normalize_schema_model(draft_schema, generate_missing_names=True)

    schema_name = str(draft.get("schema_name") or current.get("schema_name") or "")
    if not schema_name:
        raise SchemaValidationError("schema_name is required")

    current_tables = {t["name"]: t for t in current.get("tables", [])}
    draft_tables = {t["name"]: t for t in draft.get("tables", [])}

    current_rels = {
        (
            r["name"],
            r["from_table"],
            r["from_column"],
            r["to_table"],
            r["to_column"],
        ): r
        for r in current.get("relationships", [])
    }
    draft_rels = {
        (
            r["name"],
            r["from_table"],
            r["from_column"],
            r["to_table"],
            r["to_column"],
        ): r
        for r in draft.get("relationships", [])
    }

    operations: list[dict[str, Any]] = []
    warnings: list[str] = []
    destructive_details: list[str] = []

    # Drop removed relationships first.
    for key, rel in current_rels.items():
        if key in draft_rels:
            continue
        operations.append(
            {
                "type": "drop_relationship",
                "name": rel["name"],
                "from_table": rel["from_table"],
            }
        )

    # Drop removed columns/tables.
    for tname in sorted(current_tables.keys() - draft_tables.keys()):
        operations.append({"type": "drop_table", "table": tname})
        destructive_details.append(f"drop table {tname}")

    for tname in sorted(current_tables.keys() & draft_tables.keys()):
        ccols = {c["name"]: c for c in current_tables[tname].get("columns", [])}
        dcols = {c["name"]: c for c in draft_tables[tname].get("columns", [])}

        for cname in sorted(ccols.keys() - dcols.keys()):
            operations.append({"type": "drop_column", "table": tname, "column": cname})
            destructive_details.append(f"drop column {tname}.{cname}")

    # Add new tables.
    for tname in sorted(draft_tables.keys() - current_tables.keys()):
        cols = list(draft_tables[tname].get("columns", []))
        if not any(str(c.get("name") or "") == "id" for c in cols):
            cols = [
                {
                    "name": "id",
                    "label": "Id",
                    "type": "bigserial",
                    "nullable": False,
                    "is_primary": True,
                },
                *cols,
            ]
        operations.append({"type": "add_table", "table": tname, "columns": cols})

    # Add and alter columns in existing tables.
    for tname in sorted(current_tables.keys() & draft_tables.keys()):
        ccols = {c["name"]: c for c in current_tables[tname].get("columns", [])}
        dcols = {c["name"]: c for c in draft_tables[tname].get("columns", [])}

        for cname in sorted(dcols.keys() - ccols.keys()):
            operations.append(
                {
                    "type": "add_column",
                    "table": tname,
                    "column": dcols[cname],
                }
            )

        for cname in sorted(ccols.keys() & dcols.keys()):
            before = ccols[cname]
            after = dcols[cname]
            op: dict[str, Any] = {"type": "alter_column", "table": tname, "column": cname}
            changed = False

            if str(before.get("type") or "") != str(after.get("type") or ""):
                op["new_type"] = str(after.get("type") or "text")
                changed = True
            if bool(before.get("nullable", True)) != bool(after.get("nullable", True)):
                op["new_nullable"] = bool(after.get("nullable", True))
                changed = True
            if _canonical_default(before.get("default")) != _canonical_default(after.get("default")):
                op["new_default"] = after.get("default") if "default" in after else None
                changed = True

            if bool(before.get("is_primary", False)) != bool(after.get("is_primary", False)):
                warnings.append(
                    f"primary key changes are not applied automatically ({tname}.{cname})"
                )

            if changed:
                operations.append(op)

    # Add new relationships last.
    for key, rel in sorted(draft_rels.items()):
        if key in current_rels:
            continue
        operations.append(
            {
                "type": "add_relationship",
                "name": rel["name"],
                "from_table": rel["from_table"],
                "from_column": rel["from_column"],
                "to_table": rel["to_table"],
                "to_column": rel["to_column"],
                "on_delete": rel.get("on_delete") or "NO ACTION",
                "on_update": rel.get("on_update") or "NO ACTION",
            }
        )

    sql_statements: list[str] = []
    for op in operations:
        sql_statements.extend(_sql_for_operation(op, schema_name=schema_name))

    return {
        "current": current,
        "draft": draft,
        "operations": operations,
        "sql": sql_statements,
        "warnings": warnings,
        "destructive": bool(destructive_details),
        "destructive_details": destructive_details,
        "schema_name": schema_name,
    }
