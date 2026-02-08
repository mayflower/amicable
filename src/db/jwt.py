from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

_HASURA_CLAIMS_NS = "https://hasura.io/jwt/claims"


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(seg: str) -> bytes:
    pad = "=" * ((4 - (len(seg) % 4)) % 4)
    return base64.urlsafe_b64decode((seg + pad).encode("ascii"))


@dataclass(frozen=True)
class HasuraJwtConfig:
    alg: str
    key: bytes


def parse_hasura_jwt_secret(raw: str) -> HasuraJwtConfig:
    """Parse HASURA_GRAPHQL_JWT_SECRET.

    We support the standard Hasura JSON format for HS256:
      {"type":"HS256","key":"..."}
    """
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("missing HASURA_GRAPHQL_JWT_SECRET")

    try:
        data = json.loads(raw)
    except Exception as exc:
        raise ValueError("HASURA_GRAPHQL_JWT_SECRET must be JSON") from exc

    if not isinstance(data, dict):
        raise ValueError("HASURA_GRAPHQL_JWT_SECRET must be a JSON object")

    alg = str(data.get("type") or "").strip().upper()
    key = data.get("key")
    if alg != "HS256":
        raise ValueError(f"unsupported jwt type: {alg!r} (expected 'HS256')")
    if not isinstance(key, str) or not key:
        raise ValueError("HASURA_GRAPHQL_JWT_SECRET missing key")

    return HasuraJwtConfig(alg="HS256", key=key.encode("utf-8"))


def mint_hasura_jwt(
    *,
    jwt_secret_json: str,
    role_name: str,
    app_id: str,
    ttl_s: int = 300,
    now_s: int | None = None,
) -> str:
    cfg = parse_hasura_jwt_secret(jwt_secret_json)
    if cfg.alg != "HS256":
        raise ValueError("only HS256 supported")

    now = int(time.time() if now_s is None else now_s)
    exp = now + max(1, int(ttl_s))

    header = {"alg": "HS256", "typ": "JWT"}
    payload: dict[str, Any] = {
        "iat": now,
        "exp": exp,
        _HASURA_CLAIMS_NS: {
            "x-hasura-default-role": role_name,
            "x-hasura-allowed-roles": [role_name],
            "x-hasura-app-id": app_id,
        },
    }

    signing_input = ".".join(
        [
            _b64url_encode(
                json.dumps(header, separators=(",", ":"), sort_keys=True).encode(
                    "utf-8"
                )
            ),
            _b64url_encode(
                json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
                    "utf-8"
                )
            ),
        ]
    ).encode("ascii")

    sig = hmac.new(cfg.key, signing_input, hashlib.sha256).digest()
    return signing_input.decode("ascii") + "." + _b64url_encode(sig)


def verify_hs256_signature(token: str, *, jwt_secret_json: str) -> bool:
    """Test helper: verify HS256 signature only (no claim validation)."""
    cfg = parse_hasura_jwt_secret(jwt_secret_json)
    parts = token.split(".")
    if len(parts) != 3:
        return False
    signing_input = ".".join(parts[:2]).encode("ascii")
    expected = hmac.new(cfg.key, signing_input, hashlib.sha256).digest()
    try:
        got = _b64url_decode(parts[2])
    except Exception:
        return False
    return hmac.compare_digest(expected, got)
