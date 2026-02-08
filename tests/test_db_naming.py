from __future__ import annotations

from src.db.naming import role_name_for_app, schema_name_for_app, validate_pg_ident


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
