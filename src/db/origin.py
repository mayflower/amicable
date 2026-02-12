from __future__ import annotations

import hashlib
from urllib.parse import urlparse


def _claim_name_for_app_id(
    app_id: str, *, slug: str | None = None, prefix: str = "amicable"
) -> str:
    # Must match src/sandbox_backends/k8s_backend.py _dns_safe_claim_name logic.
    if slug and isinstance(slug, str) and slug.strip():
        import re

        name = re.sub(r"[^a-z0-9-]", "-", slug.strip().lower()).strip("-")
        if name and len(name) <= 63:
            return name
    digest = hashlib.sha256(app_id.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}-{digest}"


def expected_preview_origin(
    *,
    app_id: str,
    slug: str | None = None,
    preview_base_domain: str,
    preview_scheme: str,
) -> str:
    scheme = (preview_scheme or "https").strip() or "https"
    base = (preview_base_domain or "").strip().lstrip(".")
    if not base:
        raise ValueError("missing PREVIEW_BASE_DOMAIN")
    host = f"{_claim_name_for_app_id(app_id, slug=slug)}.{base}"
    return f"{scheme}://{host}"


def origin_matches_expected(
    origin: str,
    *,
    app_id: str,
    slug: str | None = None,
    preview_base_domain: str,
    preview_scheme: str,
) -> bool:
    # Kept for backwards compatible signature (callers may pass these as keywords).
    del app_id, slug
    if not origin:
        return False
    try:
        parsed = urlparse(origin)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False
    # Accept any single-level subdomain of the preview base domain.
    # The app_key already authenticates per-app; this just ensures the
    # request comes from *some* preview sandbox, not an arbitrary site.
    scheme = (preview_scheme or "https").strip() or "https"
    base = (preview_base_domain or "").strip().lstrip(".")
    if not base:
        return False
    if parsed.scheme != scheme:
        return False
    host = parsed.hostname or ""
    return host.endswith(f".{base}") and "." not in host[: -(len(base) + 1)]
