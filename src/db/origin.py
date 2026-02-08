from __future__ import annotations

import hashlib
from urllib.parse import urlparse


def _claim_name_for_app_id(app_id: str, *, prefix: str = "amicable") -> str:
    # Must match src/sandbox_backends/k8s_backend.py _dns_safe_claim_name logic.
    digest = hashlib.sha256(app_id.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}-{digest}"


def expected_preview_origin(
    *,
    app_id: str,
    preview_base_domain: str,
    preview_scheme: str,
) -> str:
    scheme = (preview_scheme or "https").strip() or "https"
    base = (preview_base_domain or "").strip().lstrip(".")
    if not base:
        raise ValueError("missing PREVIEW_BASE_DOMAIN")
    host = f"{_claim_name_for_app_id(app_id)}.{base}"
    return f"{scheme}://{host}"


def origin_matches_expected(
    origin: str,
    *,
    app_id: str,
    preview_base_domain: str,
    preview_scheme: str,
) -> bool:
    if not origin:
        return False
    try:
        parsed = urlparse(origin)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False
    expected = expected_preview_origin(
        app_id=app_id,
        preview_base_domain=preview_base_domain,
        preview_scheme=preview_scheme,
    )
    return origin.rstrip("/") == expected.rstrip("/")
