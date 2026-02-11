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


BASE = "amicable-preview.data.mayflower.tech"
APP_ID = "d0fda4fa-b437-4ff6-88cd-8f86d66134b4"


def test_origin_matches_any_preview_subdomain() -> None:
    """Any single-level subdomain of the preview base domain is accepted."""
    assert origin_matches_expected(
        "https://todolist.amicable-preview.data.mayflower.tech",
        app_id=APP_ID, preview_base_domain=BASE, preview_scheme="https",
    )
    assert origin_matches_expected(
        "https://my-app.amicable-preview.data.mayflower.tech",
        app_id=APP_ID, preview_base_domain=BASE, preview_scheme="https",
    )


def test_origin_rejects_wrong_scheme() -> None:
    assert not origin_matches_expected(
        "http://todolist.amicable-preview.data.mayflower.tech",
        app_id=APP_ID, preview_base_domain=BASE, preview_scheme="https",
    )


def test_origin_rejects_non_preview_domain() -> None:
    assert not origin_matches_expected(
        "https://evil.example.com",
        app_id=APP_ID, preview_base_domain=BASE, preview_scheme="https",
    )


def test_origin_rejects_bare_base_domain() -> None:
    """The base domain itself (no subdomain) should be rejected."""
    assert not origin_matches_expected(
        "https://amicable-preview.data.mayflower.tech",
        app_id=APP_ID, preview_base_domain=BASE, preview_scheme="https",
    )


def test_origin_rejects_nested_subdomain() -> None:
    """Only single-level subdomains, not nested ones like a.b.base."""
    assert not origin_matches_expected(
        "https://a.b.amicable-preview.data.mayflower.tech",
        app_id=APP_ID, preview_base_domain=BASE, preview_scheme="https",
    )


def test_origin_rejects_empty() -> None:
    assert not origin_matches_expected(
        "", app_id=APP_ID, preview_base_domain=BASE, preview_scheme="https",
    )
