from __future__ import annotations

import json
import os
import re
from typing import Any

from src.db.naming import dedupe_identifier, identifier_from_label
from src.db.schema_diff import (
    SchemaValidationError,
    build_schema_diff,
    normalize_schema_model,
)

_REL_TYPES = {"one_to_many", "one_to_one"}
_DEFAULT_CLARIFICATION_OPTIONS = [
    "Track customers",
    "Track orders",
    "Track products and prices",
]

# Shared with frontend: business-oriented field presets.
FIELD_PRESETS: dict[str, dict[str, Any]] = {
    "name": {"type": "text", "nullable": False},
    "email": {"type": "text", "nullable": False},
    "phone": {"type": "text", "nullable": True},
    "price": {"type": "numeric", "nullable": False},
    "date": {"type": "date", "nullable": False},
    "status": {"type": "text", "nullable": False, "default": "new"},
    "active": {"type": "boolean", "nullable": False, "default": True},
    "notes": {"type": "text", "nullable": True},
    "custom": {"type": "text", "nullable": True},
}

_PRESET_ALIASES: dict[str, str] = {
    "full_name": "name",
    "customer_name": "name",
    "mail": "email",
    "telephone": "phone",
    "amount": "price",
    "total": "price",
    "created_at": "date",
    "state": "status",
    "enabled": "active",
}

_JSON_OBJ_RE = re.compile(r"\{.*\}", flags=re.DOTALL)


def _intent_model() -> str:
    return (
        os.environ.get("AMICABLE_SCHEMA_INTENT_MODEL")
        or os.environ.get("AMICABLE_TRACE_NARRATOR_MODEL")
        or "anthropic:claude-haiku-4-5"
    ).strip()


def _norm_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _humanize_ident(name: str) -> str:
    return str(name).replace("_", " ").strip().title()


def _singularize(ident: str) -> str:
    v = str(ident).strip().lower()
    if v.endswith("ies") and len(v) > 3:
        return f"{v[:-3]}y"
    if v.endswith("s") and len(v) > 1:
        return v[:-1]
    return v


def _clone_json(value: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(value))


def _ensure_table(
    draft: dict[str, Any], *, label: str, used_tables: set[str]
) -> dict[str, Any]:
    tables = list(draft.get("tables") or [])
    key = _norm_key(label)
    for t in tables:
        if not isinstance(t, dict):
            continue
        if _norm_key(str(t.get("label") or "")) == key:
            return t
        if _norm_key(str(t.get("name") or "")) == key:
            return t

    name = dedupe_identifier(
        identifier_from_label(label, fallback_prefix="table"),
        used_tables,
    )
    table = {
        "name": name,
        "label": _humanize_ident(label or name),
        "position": {"x": 96 + len(tables) * 40, "y": 96 + len(tables) * 28},
        "columns": [
            {
                "name": "id",
                "label": "Id",
                "type": "bigserial",
                "nullable": False,
                "is_primary": True,
            }
        ],
    }
    tables.append(table)
    draft["tables"] = tables
    return table


def _normalize_preset(raw: str) -> str:
    p = _norm_key(raw)
    if p in FIELD_PRESETS:
        return p
    aliased = _PRESET_ALIASES.get(p)
    if aliased and aliased in FIELD_PRESETS:
        return aliased
    return "custom"


def _ensure_field(
    table: dict[str, Any],
    *,
    label: str,
    preset: str,
) -> dict[str, Any]:
    columns = list(table.get("columns") or [])
    key = _norm_key(label)
    for c in columns:
        if not isinstance(c, dict):
            continue
        if _norm_key(str(c.get("label") or "")) == key:
            return c
        if _norm_key(str(c.get("name") or "")) == key:
            return c

    used_cols = {
        str(c.get("name") or "")
        for c in columns
        if isinstance(c, dict) and str(c.get("name") or "")
    }
    spec = FIELD_PRESETS[_normalize_preset(preset)]
    name = dedupe_identifier(
        identifier_from_label(label, fallback_prefix="col"),
        used_cols,
    )
    col = {
        "name": name,
        "label": _humanize_ident(label or name),
        "type": spec["type"],
        "nullable": bool(spec.get("nullable", True)),
    }
    if "default" in spec:
        col["default"] = spec["default"]
    columns.append(col)
    table["columns"] = columns
    return col


def _ensure_fk_relationship(
    draft: dict[str, Any],
    *,
    from_table: dict[str, Any],
    to_table: dict[str, Any],
    relation_type: str,
    used_rels: set[str],
) -> tuple[str, list[str]]:
    warnings: list[str] = []
    rel_type = relation_type if relation_type in _REL_TYPES else "one_to_many"

    parent_base = _singularize(str(to_table.get("name") or "parent"))
    fk_name = identifier_from_label(f"{parent_base}_id", fallback_prefix="parent_id")
    fk_col: dict[str, Any] | None = None
    for col in list(from_table.get("columns") or []):
        if isinstance(col, dict) and str(col.get("name") or "") == fk_name:
            fk_col = col
            break
    if fk_col is None:
        fk_col = _ensure_field(
            from_table,
            label=f"{_humanize_ident(parent_base)} Id",
            preset="custom",
        )
    fk_col["name"] = fk_name
    fk_col["type"] = "bigint"
    fk_col["nullable"] = False

    rels = list(draft.get("relationships") or [])
    for rel in rels:
        if not isinstance(rel, dict):
            continue
        if (
            str(rel.get("from_table") or "") == str(from_table.get("name") or "")
            and str(rel.get("from_column") or "") == fk_name
            and str(rel.get("to_table") or "") == str(to_table.get("name") or "")
            and str(rel.get("to_column") or "") == "id"
        ):
            return str(rel.get("name") or ""), warnings

    rel_name = dedupe_identifier(
        identifier_from_label(
            f"{from_table.get('name')}_{fk_name}_to_{to_table.get('name')}",
            fallback_prefix="fk",
        ),
        used_rels,
    )
    rels.append(
        {
            "name": rel_name,
            "from_table": str(from_table.get("name") or ""),
            "from_column": fk_name,
            "to_table": str(to_table.get("name") or ""),
            "to_column": "id",
            "on_delete": "NO ACTION",
            "on_update": "NO ACTION",
        }
    )
    draft["relationships"] = rels
    if rel_type == "one_to_one":
        warnings.append(
            "One-to-one was interpreted as a single link. Unique constraints are not auto-added."
        )
    return rel_name, warnings


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    with_context = raw
    match = _JSON_OBJ_RE.search(raw)
    if match:
        with_context = match.group(0)
    try:
        obj = json.loads(with_context)
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def _invoke_intent_llm(
    *,
    current: dict[str, Any],
    draft: dict[str, Any],
    intent_text: str,
) -> dict[str, Any] | None:
    try:
        from langchain.chat_models import init_chat_model
    except Exception:
        return None

    try:
        llm = init_chat_model(_intent_model())
    except Exception:
        return None

    current_labels = [
        str(t.get("label") or t.get("name") or "")
        for t in list(current.get("tables") or [])
        if isinstance(t, dict)
    ]
    draft_labels = [
        str(t.get("label") or t.get("name") or "")
        for t in list(draft.get("tables") or [])
        if isinstance(t, dict)
    ]

    prompt = (
        "You design database schema drafts for non-programmers.\n"
        "Return JSON only (no markdown) with this exact shape:\n"
        "{\n"
        '  "tables": [{"label": "Customers", "fields": [{"label":"Email","preset":"email"}]}],\n'
        '  "relationships": [{"from_table":"Orders","to_table":"Customers","type":"one_to_many"}],\n'
        '  "clarification_question": "",\n'
        '  "clarification_options": []\n'
        "}\n"
        "Allowed field presets: "
        f"{sorted(FIELD_PRESETS.keys())}.\n"
        "Allowed relationship types: one_to_many, one_to_one.\n"
        "Use friendly labels only in proposal values.\n"
        "If intent is ambiguous, fill clarification_question and options, leave tables/relationships empty.\n\n"
        f"Current tables: {current_labels or ['<none>']}\n"
        f"Draft tables: {draft_labels or ['<none>']}\n"
        f"User intent: {intent_text.strip()[:800]}\n"
    )

    msg = llm.invoke(prompt)
    text = getattr(msg, "content", "") if msg is not None else ""
    if not isinstance(text, str):
        return None
    return _extract_json_object(text)


def _normalize_proposal(raw: dict[str, Any]) -> dict[str, Any]:
    out_tables: list[dict[str, Any]] = []
    out_relationships: list[dict[str, str]] = []

    tables_raw = raw.get("tables") if isinstance(raw.get("tables"), list) else []
    for t in tables_raw:
        if not isinstance(t, dict):
            continue
        label = str(t.get("label") or "").strip()
        if not label:
            continue
        fields: list[dict[str, str]] = []
        for f in t.get("fields") if isinstance(t.get("fields"), list) else []:
            if not isinstance(f, dict):
                continue
            field_label = str(f.get("label") or "").strip()
            if not field_label:
                continue
            field_preset = _normalize_preset(str(f.get("preset") or "custom"))
            fields.append({"label": field_label, "preset": field_preset})
        out_tables.append({"label": label, "fields": fields})

    rels_raw = (
        raw.get("relationships") if isinstance(raw.get("relationships"), list) else []
    )
    for rel in rels_raw:
        if not isinstance(rel, dict):
            continue
        from_table = str(rel.get("from_table") or "").strip()
        to_table = str(rel.get("to_table") or "").strip()
        rel_type = str(rel.get("type") or "").strip().lower()
        if not from_table or not to_table:
            continue
        if rel_type not in _REL_TYPES:
            rel_type = "one_to_many"
        out_relationships.append(
            {"from_table": from_table, "to_table": to_table, "type": rel_type}
        )

    clarification_question = str(raw.get("clarification_question") or "").strip()
    clarification_options = []
    opts_raw = (
        raw.get("clarification_options")
        if isinstance(raw.get("clarification_options"), list)
        else []
    )
    for item in opts_raw:
        s = str(item or "").strip()
        if s:
            clarification_options.append(s[:80])

    return {
        "tables": out_tables,
        "relationships": out_relationships,
        "clarification_question": clarification_question,
        "clarification_options": clarification_options[:4],
    }


def _deterministic_probe(intent_text: str) -> dict[str, Any] | None:
    text = str(intent_text or "").strip().lower()
    if not text:
        return None

    tables: list[dict[str, Any]] = []
    relationships: list[dict[str, str]] = []

    has_customer = "customer" in text
    has_order = "order" in text

    if has_customer:
        tables.append(
            {
                "label": "Customers",
                "fields": [
                    {"label": "Name", "preset": "name"},
                    {"label": "Email", "preset": "email"},
                ],
            }
        )

    if has_order:
        tables.append(
            {
                "label": "Orders",
                "fields": [
                    {"label": "Order Date", "preset": "date"},
                    {"label": "Status", "preset": "status"},
                ],
            }
        )

    if has_customer and has_order and (
        "link" in text or "belong" in text or "and" in text
    ):
        relationships.append(
            {
                "from_table": "Orders",
                "to_table": "Customers",
                "type": "one_to_many",
            }
        )

    if "track order status" in text and not any(
        _norm_key(t.get("label") or "") == "orders" for t in tables
    ):
        tables.append(
            {
                "label": "Orders",
                "fields": [{"label": "Status", "preset": "status"}],
            }
        )

    if not tables and not relationships:
        return None

    return {
        "tables": tables,
        "relationships": relationships,
        "clarification_question": "",
        "clarification_options": [],
    }


def _change_cards_from_diff(
    *, diff: dict[str, Any], draft: dict[str, Any]
) -> list[dict[str, str]]:
    table_labels = {
        str(t.get("name") or ""): str(t.get("label") or t.get("name") or "")
        for t in list(draft.get("tables") or [])
        if isinstance(t, dict)
    }
    col_labels = {
        (
            str(t.get("name") or ""),
            str(c.get("name") or ""),
        ): str(c.get("label") or c.get("name") or "")
        for t in list(draft.get("tables") or [])
        if isinstance(t, dict)
        for c in list(t.get("columns") or [])
        if isinstance(c, dict)
    }

    cards: list[dict[str, str]] = []
    for idx, op in enumerate(list(diff.get("operations") or [])):
        if not isinstance(op, dict):
            continue
        typ = str(op.get("type") or "")
        title = "Schema update"
        desc = "Database model updated."
        risk = "low"

        if typ == "add_table":
            tname = str(op.get("table") or "")
            title = "Add table"
            desc = f"Create {table_labels.get(tname, _humanize_ident(tname))}."
        elif typ == "add_column":
            tname = str(op.get("table") or "")
            col = op.get("column") if isinstance(op.get("column"), dict) else {}
            cname = str(col.get("name") or "")
            title = "Add field"
            desc = (
                f"Add {col_labels.get((tname, cname), _humanize_ident(cname))} to "
                f"{table_labels.get(tname, _humanize_ident(tname))}."
            )
        elif typ == "add_relationship":
            ft = str(op.get("from_table") or "")
            tt = str(op.get("to_table") or "")
            title = "Link tables"
            desc = (
                f"{table_labels.get(ft, _humanize_ident(ft))} belong to "
                f"{table_labels.get(tt, _humanize_ident(tt))}."
            )
        elif typ in {"drop_table", "drop_column", "drop_relationship"}:
            title = "Remove data structure"
            desc = "A structure is being removed. Existing data may be affected."
            risk = "high"
        elif typ == "alter_column":
            tname = str(op.get("table") or "")
            cname = str(op.get("column") or "")
            title = "Update field"
            desc = (
                f"Update {col_labels.get((tname, cname), _humanize_ident(cname))} in "
                f"{table_labels.get(tname, _humanize_ident(tname))}."
            )
            risk = "medium"

        cards.append(
            {
                "id": f"card_{idx + 1}",
                "title": title,
                "description": desc,
                "kind": typ or "update",
                "risk": risk,
            }
        )
    return cards


def _fallback_result(
    *,
    draft: dict[str, Any],
    intent_text: str,
    warning: str,
) -> dict[str, Any]:
    _ = intent_text
    return {
        "draft": draft,
        "assistant_message": (
            "I could not turn that into schema changes automatically. "
            "Try naming the tables and fields you need, for example: "
            "'Add customers with name and email'."
        ),
        "change_cards": [],
        "needs_clarification": True,
        "clarification_question": "What data should we track first?",
        "clarification_options": list(_DEFAULT_CLARIFICATION_OPTIONS),
        "warnings": [warning],
    }


def generate_schema_intent(
    *,
    current: dict[str, Any],
    draft: dict[str, Any],
    intent_text: str,
) -> dict[str, Any]:
    current_norm = normalize_schema_model(current, generate_missing_names=False)
    draft_seed = dict(draft)
    draft_seed.setdefault("app_id", current_norm.get("app_id") or "")
    draft_seed.setdefault("schema_name", current_norm.get("schema_name") or "")
    draft_norm = normalize_schema_model(draft_seed, generate_missing_names=True)

    text = str(intent_text or "").strip()
    if not text:
        return {
            "draft": draft_norm,
            "assistant_message": "Tell me what data your app should store.",
            "change_cards": [],
            "needs_clarification": True,
            "clarification_question": "What should we model first?",
            "clarification_options": list(_DEFAULT_CLARIFICATION_OPTIONS),
            "warnings": [],
        }

    proposal = _deterministic_probe(text)
    llm_failed = False
    if proposal is None:
        try:
            llm_raw = _invoke_intent_llm(
                current=current_norm,
                draft=draft_norm,
                intent_text=text,
            )
            proposal = _normalize_proposal(llm_raw or {})
        except Exception:
            llm_failed = True
            proposal = None

    if not proposal:
        warning = (
            "AI intent parsing unavailable; no draft changes were made."
            if llm_failed
            else "Intent not specific enough for a safe draft update."
        )
        return _fallback_result(draft=draft_norm, intent_text=text, warning=warning)

    if (
        str(proposal.get("clarification_question") or "").strip()
        and not list(proposal.get("tables") or [])
        and not list(proposal.get("relationships") or [])
    ):
        return {
            "draft": draft_norm,
            "assistant_message": str(proposal.get("clarification_question") or ""),
            "change_cards": [],
            "needs_clarification": True,
            "clarification_question": str(proposal.get("clarification_question") or ""),
            "clarification_options": list(proposal.get("clarification_options") or []),
            "warnings": [],
        }

    next_draft = _clone_json(draft_norm)
    used_tables = {
        str(t.get("name") or "")
        for t in list(next_draft.get("tables") or [])
        if isinstance(t, dict) and str(t.get("name") or "")
    }
    used_rels = {
        str(r.get("name") or "")
        for r in list(next_draft.get("relationships") or [])
        if isinstance(r, dict) and str(r.get("name") or "")
    }
    warnings: list[str] = []

    for t in list(proposal.get("tables") or []):
        if not isinstance(t, dict):
            continue
        table = _ensure_table(
            next_draft,
            label=str(t.get("label") or "").strip() or "Table",
            used_tables=used_tables,
        )
        for f in list(t.get("fields") or []):
            if not isinstance(f, dict):
                continue
            field_label = str(f.get("label") or "").strip()
            if not field_label:
                continue
            _ensure_field(
                table,
                label=field_label,
                preset=str(f.get("preset") or "custom"),
            )

    table_lookup = {
        _norm_key(str(t.get("label") or t.get("name") or "")): t
        for t in list(next_draft.get("tables") or [])
        if isinstance(t, dict)
    }
    for rel in list(proposal.get("relationships") or []):
        if not isinstance(rel, dict):
            continue
        from_label = str(rel.get("from_table") or "").strip()
        to_label = str(rel.get("to_table") or "").strip()
        if not from_label or not to_label:
            continue

        from_table = table_lookup.get(_norm_key(from_label))
        if from_table is None:
            from_table = _ensure_table(
                next_draft,
                label=from_label,
                used_tables=used_tables,
            )
            table_lookup[_norm_key(from_label)] = from_table

        to_table = table_lookup.get(_norm_key(to_label))
        if to_table is None:
            to_table = _ensure_table(
                next_draft,
                label=to_label,
                used_tables=used_tables,
            )
            table_lookup[_norm_key(to_label)] = to_table

        _rel_name, rel_warnings = _ensure_fk_relationship(
            next_draft,
            from_table=from_table,
            to_table=to_table,
            relation_type=str(rel.get("type") or "one_to_many"),
            used_rels=used_rels,
        )
        warnings.extend(rel_warnings)

    try:
        diff = build_schema_diff(draft_norm, next_draft)
    except SchemaValidationError:
        return _fallback_result(
            draft=draft_norm,
            intent_text=text,
            warning="Generated draft was invalid; no changes were applied.",
        )

    cards = _change_cards_from_diff(diff=diff, draft=next_draft)
    ops = len(list(diff.get("operations") or []))
    if ops == 0:
        return {
            "draft": draft_norm,
            "assistant_message": (
                "I understood your request, but it does not require schema changes."
            ),
            "change_cards": [],
            "needs_clarification": False,
            "clarification_question": "",
            "clarification_options": [],
            "warnings": warnings,
        }

    assistant_message = (
        f"I prepared {ops} draft change{'s' if ops != 1 else ''}. "
        "Review the changes and click Apply when ready."
    )
    if warnings:
        assistant_message += " A few details need attention in Advanced settings."

    return {
        "draft": next_draft,
        "assistant_message": assistant_message,
        "change_cards": cards,
        "needs_clarification": False,
        "clarification_question": "",
        "clarification_options": [],
        "warnings": warnings,
    }
