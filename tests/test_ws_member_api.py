from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("dotenv")


def _patch_auth_rejected():
    """Patch _get_owner_from_request to always reject, regardless of AUTH_MODE."""
    return patch(
        "src.runtimes.ws_server._get_owner_from_request",
        side_effect=PermissionError("not authenticated"),
    )


def test_list_members_requires_auth():
    """GET /api/projects/{id}/members requires authentication."""
    from fastapi.testclient import TestClient

    from src.runtimes.ws_server import app

    with patch("src.runtimes.ws_server._require_hasura"), _patch_auth_rejected():
        client = TestClient(app)
        resp = client.get("/api/projects/test-id/members")
        assert resp.status_code == 401


def test_add_member_requires_auth():
    """POST /api/projects/{id}/members requires authentication."""
    from fastapi.testclient import TestClient

    from src.runtimes.ws_server import app

    with patch("src.runtimes.ws_server._require_hasura"), _patch_auth_rejected():
        client = TestClient(app)
        resp = client.post("/api/projects/test-id/members", json={"email": "test@example.com"})
        assert resp.status_code == 401


def test_remove_member_requires_auth():
    """DELETE /api/projects/{id}/members/{sub} requires authentication."""
    from fastapi.testclient import TestClient

    from src.runtimes.ws_server import app

    with patch("src.runtimes.ws_server._require_hasura"), _patch_auth_rejected():
        client = TestClient(app)
        resp = client.delete("/api/projects/test-id/members/some-sub")
        assert resp.status_code == 401
