from __future__ import annotations

from src.db.schema_diff import compute_schema_version, normalize_schema_model


def _empty_schema() -> dict:
    return {
        "app_id": "p1",
        "schema_name": "app_deadbeef1234",
        "tables": [],
        "relationships": [],
    }


def test_generate_schema_intent_customers_orders_deterministic_probe() -> None:
    from src.db.schema_ai_intent import generate_schema_intent

    out = generate_schema_intent(
        current=_empty_schema(),
        draft=_empty_schema(),
        intent_text="I need customers and orders, and link orders to customers.",
    )

    assert out["needs_clarification"] is False
    draft = out["draft"]
    tables = {str(t.get("name") or "") for t in draft["tables"]}
    assert "customers" in tables
    assert "orders" in tables
    assert any(
        str(r.get("from_table") or "") == "orders"
        and str(r.get("to_table") or "") == "customers"
        for r in draft["relationships"]
    )
    assert len(out["change_cards"]) >= 1


def test_generate_schema_intent_ai_failure_keeps_draft_unchanged(monkeypatch) -> None:
    import src.db.schema_ai_intent as schema_ai_intent

    def _boom(**_kwargs):
        raise RuntimeError("llm unavailable")

    monkeypatch.setattr(schema_ai_intent, "_invoke_intent_llm", _boom)

    draft = {
        "app_id": "p1",
        "schema_name": "app_deadbeef1234",
        "tables": [
            {
                "name": "customers",
                "label": "Customers",
                "position": {"x": 0, "y": 0},
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
        ],
        "relationships": [],
    }
    normalized_before = normalize_schema_model(draft, generate_missing_names=True)
    version_before = compute_schema_version(normalized_before)

    out = schema_ai_intent.generate_schema_intent(
        current=normalized_before,
        draft=draft,
        intent_text="Make this better for me",
    )

    version_after = compute_schema_version(out["draft"])
    assert version_after == version_before
    assert out["needs_clarification"] is True
    assert len(out["change_cards"]) == 0
    assert any("no draft changes were made" in str(w).lower() for w in out["warnings"])

