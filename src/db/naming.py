from __future__ import annotations

import hashlib
import re

_IDENT_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


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
