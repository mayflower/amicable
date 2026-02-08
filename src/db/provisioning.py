from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from typing import Any

from src.db.hasura_client import HasuraClient, HasuraConfig
from src.db.naming import role_name_for_app, schema_name_for_app


def _env(name: str) -> str | None:
    v = (os.environ.get(name) or "").strip()
    return v or None


def db_enabled_from_env() -> bool:
    return bool(_env("HASURA_BASE_URL") and _env("HASURA_GRAPHQL_ADMIN_SECRET"))


def hasura_client_from_env() -> HasuraClient:
    base = _env("HASURA_BASE_URL")
    secret = _env("HASURA_GRAPHQL_ADMIN_SECRET")
    if not base or not secret:
        raise RuntimeError(
            "Hasura not configured (missing HASURA_BASE_URL or HASURA_GRAPHQL_ADMIN_SECRET)"
        )
    source = (_env("HASURA_SOURCE_NAME") or "default").strip()
    return HasuraClient(
        HasuraConfig(base_url=base, admin_secret=secret, source_name=source)
    )


def _sql_str(value: str) -> str:
    """Return a single-quoted SQL string literal (escaping internal single quotes)."""
    return "'" + value.replace("'", "''") + "'"


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _hash_app_key(app_key: str) -> str:
    # Stable hash for DB row; use constant-time compare on validation.
    return _sha256_hex(app_key)


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest((a or "").encode("utf-8"), (b or "").encode("utf-8"))


@dataclass(frozen=True)
class AppDbInfo:
    app_id: str
    schema_name: str
    role_name: str
    app_key_sha256: str
    # Only set on create/rotate (so we don't need to store plaintext server-side).
    app_key: str | None = None


def ensure_meta_schema(client: HasuraClient) -> None:
    client.run_sql(
        """
        CREATE SCHEMA IF NOT EXISTS amicable_meta;
        CREATE TABLE IF NOT EXISTS amicable_meta.apps (
          app_id text PRIMARY KEY,
          schema_name text NOT NULL,
          role_name text NOT NULL,
          app_key_sha256 text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        );
        """.strip()
    )


def _select_app_row(client: HasuraClient, *, app_id: str) -> dict[str, Any] | None:
    # Using run_sql keeps this self-contained; result format: {"result_type":"TuplesOk","result":[header,row...]}
    res = client.run_sql(
        f"""
        SELECT app_id, schema_name, role_name, app_key_sha256
        FROM amicable_meta.apps
        WHERE app_id = {_sql_str(app_id)};
        """.strip(),
        read_only=True,
    )
    rows = res.get("result")
    if not isinstance(rows, list) or len(rows) < 2:
        return None
    header = rows[0]
    data = rows[1]
    if not (isinstance(header, list) and isinstance(data, list)):
        return None
    out: dict[str, Any] = {}
    for idx, col in enumerate(header):
        if isinstance(col, str) and idx < len(data):
            out[col] = data[idx]
    return out if out.get("app_id") else None


def get_app(client: HasuraClient, *, app_id: str) -> AppDbInfo | None:
    ensure_meta_schema(client)
    row = _select_app_row(client, app_id=app_id)
    if not row:
        return None
    return AppDbInfo(
        app_id=str(row["app_id"]),
        schema_name=str(row["schema_name"]),
        role_name=str(row["role_name"]),
        app_key_sha256=str(row["app_key_sha256"]),
        app_key=None,
    )


def verify_app_key(*, app: AppDbInfo, app_key: str) -> bool:
    if not app_key:
        return False
    got = _hash_app_key(app_key)
    return constant_time_equals(got, app.app_key_sha256)


def ensure_app(client: HasuraClient, *, app_id: str) -> AppDbInfo:
    ensure_meta_schema(client)

    schema_name = schema_name_for_app(app_id)
    role_name = role_name_for_app(app_id)

    # Ensure schema exists (idempotent).
    client.run_sql(f"CREATE SCHEMA IF NOT EXISTS {schema_name};")

    row = _select_app_row(client, app_id=app_id)
    if row:
        return AppDbInfo(
            app_id=app_id,
            schema_name=str(row["schema_name"]),
            role_name=str(row["role_name"]),
            app_key_sha256=str(row["app_key_sha256"]),
            app_key=None,
        )

    app_key = secrets.token_urlsafe(32)
    app_key_sha = _hash_app_key(app_key)
    client.run_sql(
        f"""
        INSERT INTO amicable_meta.apps (app_id, schema_name, role_name, app_key_sha256)
        VALUES ({_sql_str(app_id)}, {_sql_str(schema_name)}, {_sql_str(role_name)}, {_sql_str(app_key_sha)})
        ON CONFLICT (app_id) DO NOTHING;
        """.strip()
    )
    # Re-select to pick up any race winner.
    row2 = _select_app_row(client, app_id=app_id)
    if row2 and str(row2.get("app_key_sha256")) != app_key_sha:
        # Someone else created it; don't leak our generated key.
        return AppDbInfo(
            app_id=app_id,
            schema_name=str(row2["schema_name"]),
            role_name=str(row2["role_name"]),
            app_key_sha256=str(row2["app_key_sha256"]),
            app_key=None,
        )

    return AppDbInfo(
        app_id=app_id,
        schema_name=schema_name,
        role_name=role_name,
        app_key_sha256=app_key_sha,
        app_key=app_key,
    )


def rotate_app_key(client: HasuraClient, *, app_id: str) -> AppDbInfo:
    ensure_meta_schema(client)
    row = _select_app_row(client, app_id=app_id)
    if not row:
        # Ensure_app handles schema creation too.
        return ensure_app(client, app_id=app_id)

    app_key = secrets.token_urlsafe(32)
    app_key_sha = _hash_app_key(app_key)
    client.run_sql(
        f"""
        UPDATE amicable_meta.apps
        SET app_key_sha256 = {_sql_str(app_key_sha)}, updated_at = now()
        WHERE app_id = {_sql_str(app_id)};
        """.strip()
    )
    return AppDbInfo(
        app_id=app_id,
        schema_name=str(row["schema_name"]),
        role_name=str(row["role_name"]),
        app_key_sha256=app_key_sha,
        app_key=app_key,
    )
