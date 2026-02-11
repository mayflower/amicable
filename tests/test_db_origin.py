from __future__ import annotations

from src.db.origin import expected_preview_origin, origin_matches_expected


def test_expected_preview_origin_matches_claim_naming() -> None:
    origin = expected_preview_origin(
        app_id="00000000-0000-0000-0000-000000000000",
        preview_base_domain="amicable-preview.data.mayflower.tech",
        preview_scheme="https",
    )
    assert origin.startswith("https://amicable-")
    assert origin.endswith(".amicable-preview.data.mayflower.tech")


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


def test_origin_matches_slug_and_hash() -> None:
    """Both slug-based and hash-based origins should be accepted."""
    app_id = "d0fda4fa-b437-4ff6-88cd-8f86d66134b4"
    slug = "todo-list"
    base = "amicable-preview.data.mayflower.tech"

    slug_origin = expected_preview_origin(
        app_id=app_id, slug=slug, preview_base_domain=base, preview_scheme="https",
    )
    hash_origin = expected_preview_origin(
        app_id=app_id, slug=None, preview_base_domain=base, preview_scheme="https",
    )
    assert slug_origin != hash_origin

    # Slug-based origin should match when slug is provided.
    assert origin_matches_expected(
        slug_origin, app_id=app_id, slug=slug,
        preview_base_domain=base, preview_scheme="https",
    )
    # Hash-based origin should also match even when slug is provided.
    assert origin_matches_expected(
        hash_origin, app_id=app_id, slug=slug,
        preview_base_domain=base, preview_scheme="https",
    )
    # Hash-based origin should match when slug is NOT provided.
    assert origin_matches_expected(
        hash_origin, app_id=app_id, slug=None,
        preview_base_domain=base, preview_scheme="https",
    )
    # Slug-based origin should NOT match when slug is NOT provided.
    assert not origin_matches_expected(
        slug_origin, app_id=app_id, slug=None,
        preview_base_domain=base, preview_scheme="https",
    )
