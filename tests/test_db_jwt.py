from __future__ import annotations

from src.db.jwt import mint_hasura_jwt, verify_hs256_signature


def test_mint_hasura_jwt_hs256_signature_and_exp() -> None:
    secret = '{"type":"HS256","key":"test-secret-123"}'
    token = mint_hasura_jwt(
        jwt_secret_json=secret,
        role_name="app_abcdef123456",
        app_id="app-1",
        ttl_s=300,
        now_s=1_700_000_000,
    )
    assert token.count(".") == 2
    assert verify_hs256_signature(token, jwt_secret_json=secret)
