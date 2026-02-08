from __future__ import annotations

from src.db.origin import expected_preview_origin, origin_matches_expected


def test_expected_preview_origin_matches_claim_naming() -> None:
    origin = expected_preview_origin(
        app_id="00000000-0000-0000-0000-000000000000",
        preview_base_domain="amicable-preview.data.mayflower.zone",
        preview_scheme="https",
    )
    assert origin.startswith("https://amicable-")
    assert origin.endswith(".amicable-preview.data.mayflower.zone")


def test_origin_matches_expected() -> None:
    app_id = "app-xyz"
    expected = expected_preview_origin(
        app_id=app_id,
        preview_base_domain="example.com",
        preview_scheme="https",
    )
    assert origin_matches_expected(
        expected,
        app_id=app_id,
        preview_base_domain="example.com",
        preview_scheme="https",
    )
    assert not origin_matches_expected(
        "https://other.example.com",
        app_id=app_id,
        preview_base_domain="example.com",
        preview_scheme="https",
    )
