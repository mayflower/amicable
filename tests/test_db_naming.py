from __future__ import annotations

from src.db.naming import (
    dedupe_identifier,
    identifier_from_label,
    role_name_for_app,
    schema_name_for_app,
    validate_pg_ident,
)


def test_schema_and_role_are_deterministic_and_valid() -> None:
    app_id = "app-123"
    s1 = schema_name_for_app(app_id)
    r1 = role_name_for_app(app_id)
    s2 = schema_name_for_app(app_id)
    r2 = role_name_for_app(app_id)
    assert s1 == s2
    assert r1 == r2
    assert validate_pg_ident(s1) == s1
    assert validate_pg_ident(r1) == r1


def test_validate_pg_ident_rejects_bad_names() -> None:
    for bad in ["", "1abc", "a-b", "a;drop", "a" * 100, "A B"]:
        try:
            validate_pg_ident(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for {bad!r}")


def test_identifier_from_label_normalizes_to_valid_ident() -> None:
    out = identifier_from_label("Customer Orders (2026)!")
    assert out == "customer_orders_2026"
    assert validate_pg_ident(out) == out


def test_dedupe_identifier_appends_numeric_suffix() -> None:
    used: set[str] = set()
    assert dedupe_identifier("orders", used) == "orders"
    assert dedupe_identifier("orders", used) == "orders_2"
    assert dedupe_identifier("orders", used) == "orders_3"
