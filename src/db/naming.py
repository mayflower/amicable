from __future__ import annotations

import hashlib
import re

_IDENT_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _hex12(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def schema_name_for_app(app_id: str) -> str:
    # Fits in Postgres identifier limit (63 chars).
    return f"app_{_hex12(app_id)}"


def role_name_for_app(app_id: str) -> str:
    return f"app_{_hex12(app_id)}"


def validate_pg_ident(name: str) -> str:
    n = (name or "").strip().lower()
    if not _IDENT_RE.match(n):
        raise ValueError("invalid identifier; must match ^[a-z][a-z0-9_]{0,62}$")
    return n


def identifier_from_label(label: str, *, fallback_prefix: str = "item") -> str:
    """Derive a safe snake_case Postgres identifier from a user-friendly label."""
    raw = (label or "").strip().lower()
    if raw:
        raw = _NON_ALNUM_RE.sub("_", raw).strip("_")
    if not raw:
        raw = fallback_prefix
    if not raw[0].isalpha():
        raw = f"{fallback_prefix}_{raw}"
    raw = re.sub(r"_+", "_", raw)
    if len(raw) > 63:
        raw = raw[:63].rstrip("_")
    if not raw:
        raw = fallback_prefix
    if not raw[0].isalpha():
        raw = f"{fallback_prefix}_{raw}"
    return validate_pg_ident(raw)


def dedupe_identifier(base: str, used: set[str]) -> str:
    """Return a unique identifier, appending numeric suffixes when needed."""
    base_norm = validate_pg_ident(base)
    if base_norm not in used:
        used.add(base_norm)
        return base_norm

    idx = 2
    while True:
        suffix = f"_{idx}"
        head_len = 63 - len(suffix)
        candidate = f"{base_norm[:head_len].rstrip('_')}{suffix}"
        candidate = validate_pg_ident(candidate)
        if candidate not in used:
            used.add(candidate)
            return candidate
        idx += 1
