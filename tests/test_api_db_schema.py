from __future__ import annotations

from dataclasses import dataclass


@dataclass
class _FakeProject:
    project_id: str
    slug: str
    template_id: str


@dataclass
class _FakeApp:
    app_id: str
    schema_name: str
    role_name: str


class _FakeSessionManager:
    def get_backend(self, _session_id: str):
        return object()


class _FakeAgent:
    def __init__(self) -> None:
        self._session_manager = _FakeSessionManager()

    async def init(
        self,
        session_id: str,
        template_id: str | None = None,
        slug: str | None = None,
    ) -> bool:
        _ = session_id, template_id, slug
        return True


def test_api_db_schema_get_success(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    import src.runtimes.ws_server as ws_server

    monkeypatch.setattr(
        ws_server,
        "_ensure_project_access",
        lambda _request, project_id: _FakeProject(project_id=project_id, slug="proj", template_id="vite"),
    )

    import src.db.provisioning as provisioning
    import src.db.schema_diff as schema_diff
    import src.db.schema_introspection as schema_introspection

    monkeypatch.setattr(provisioning, "hasura_client_from_env", lambda: object())
    monkeypatch.setattr(
        provisioning,
        "ensure_app",
        lambda _client, app_id: _FakeApp(
            app_id=app_id,
            schema_name="app_deadbeef1234",
            role_name="app_deadbeef1234",
        ),
    )
    monkeypatch.setattr(
        schema_introspection,
        "introspect_schema",
        lambda _client, app_id, schema_name: {
            "app_id": app_id,
            "schema_name": schema_name,
            "tables": [],
            "relationships": [],
        },
    )
    monkeypatch.setattr(schema_diff, "compute_schema_version", lambda _schema: "ver123")

    client = TestClient(ws_server.app)
    res = client.get("/api/db/p1/schema")
    assert res.status_code == 200
    data = res.json()
    assert data["version"] == "ver123"
    assert data["schema"]["schema_name"] == "app_deadbeef1234"


def test_api_db_schema_review_version_conflict(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    import src.runtimes.ws_server as ws_server

    monkeypatch.setattr(
        ws_server,
        "_ensure_project_access",
        lambda _request, project_id: _FakeProject(project_id=project_id, slug="proj", template_id="vite"),
    )

    import src.db.provisioning as provisioning
    import src.db.schema_diff as schema_diff
    import src.db.schema_introspection as schema_introspection

    monkeypatch.setattr(provisioning, "hasura_client_from_env", lambda: object())
    monkeypatch.setattr(
        provisioning,
        "ensure_app",
        lambda _client, app_id: _FakeApp(
            app_id=app_id,
            schema_name="app_deadbeef1234",
            role_name="app_deadbeef1234",
        ),
    )
    monkeypatch.setattr(
        schema_introspection,
        "introspect_schema",
        lambda _client, app_id, schema_name: {
            "app_id": app_id,
            "schema_name": schema_name,
            "tables": [],
            "relationships": [],
        },
    )
    monkeypatch.setattr(schema_diff, "compute_schema_version", lambda _schema: "current-v")

    client = TestClient(ws_server.app)
    res = client.post(
        "/api/db/p1/schema/review",
        json={"base_version": "old-v", "draft": {"tables": [], "relationships": []}},
    )
    assert res.status_code == 409
    assert res.json()["error"] == "version_conflict"


def test_api_db_schema_apply_requires_destructive_confirmation(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    import src.runtimes.ws_server as ws_server

    monkeypatch.setattr(ws_server, "_hasura_enabled", lambda: True)
    monkeypatch.setattr(ws_server, "_get_owner_from_request", lambda _request: ("local", "local@example.com"))
    monkeypatch.setattr(ws_server, "_get_agent", lambda: _FakeAgent())

    import src.db.provisioning as provisioning
    import src.db.schema_ai_review as schema_ai_review
    import src.db.schema_diff as schema_diff
    import src.db.schema_introspection as schema_introspection
    import src.projects.store as projects_store

    monkeypatch.setattr(provisioning, "hasura_client_from_env", lambda: object())
    monkeypatch.setattr(
        provisioning,
        "ensure_app",
        lambda _client, app_id: _FakeApp(
            app_id=app_id,
            schema_name="app_deadbeef1234",
            role_name="app_deadbeef1234",
        ),
    )
    def _get_project_by_id(_client, owner, project_id):
        _ = owner
        return _FakeProject(project_id=project_id, slug="proj", template_id="vite")

    monkeypatch.setattr(
        projects_store,
        "get_project_by_id",
        _get_project_by_id,
    )
    monkeypatch.setattr(
        schema_introspection,
        "introspect_schema",
        lambda _client, app_id, schema_name: {
            "app_id": app_id,
            "schema_name": schema_name,
            "tables": [],
            "relationships": [],
        },
    )
    monkeypatch.setattr(schema_diff, "compute_schema_version", lambda _schema: "v1")
    monkeypatch.setattr(
        schema_diff,
        "build_schema_diff",
        lambda _current, _draft: {
            "destructive": True,
            "destructive_details": ["drop table users"],
            "operations": [{"type": "drop_table", "table": "users"}],
            "warnings": [],
        },
    )
    def _review(current, diff):
        _ = current, diff
        return {
            "summary": "This will drop data.",
            "destructive": True,
            "destructive_details": ["drop table users"],
            "warnings": [],
        }

    monkeypatch.setattr(schema_ai_review, "generate_schema_review", _review)

    client = TestClient(ws_server.app)
    res = client.post(
        "/api/db/p1/schema/apply",
        json={
            "base_version": "v1",
            "confirm_destructive": False,
            "draft": {"tables": [], "relationships": []},
        },
    )
    assert res.status_code == 409
    data = res.json()
    assert data["error"] == "destructive_confirmation_required"
    assert data["destructive"] is True


def test_api_db_schema_apply_success_without_git_sync(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    import src.runtimes.ws_server as ws_server

    monkeypatch.setattr(ws_server, "_hasura_enabled", lambda: True)
    monkeypatch.setattr(ws_server, "_get_owner_from_request", lambda _request: ("local", "local@example.com"))
    monkeypatch.setattr(ws_server, "_get_agent", lambda: _FakeAgent())

    import src.db.provisioning as provisioning
    import src.db.schema_apply as schema_apply
    import src.db.schema_diff as schema_diff
    import src.db.schema_introspection as schema_introspection
    import src.gitlab.config as gitlab_config
    import src.projects.store as projects_store

    monkeypatch.setattr(provisioning, "hasura_client_from_env", lambda: object())
    monkeypatch.setattr(
        provisioning,
        "ensure_app",
        lambda _client, app_id: _FakeApp(
            app_id=app_id,
            schema_name="app_deadbeef1234",
            role_name="app_deadbeef1234",
        ),
    )
    def _get_project_by_id(_client, owner, project_id):
        _ = owner
        return _FakeProject(project_id=project_id, slug="proj", template_id="vite")

    monkeypatch.setattr(
        projects_store,
        "get_project_by_id",
        _get_project_by_id,
    )

    schemas = [
        {
            "app_id": "p1",
            "schema_name": "app_deadbeef1234",
            "tables": [],
            "relationships": [],
        },
        {
            "app_id": "p1",
            "schema_name": "app_deadbeef1234",
            "tables": [{"name": "customers", "label": "Customers", "position": {"x": 0, "y": 0}, "columns": []}],
            "relationships": [],
        },
    ]

    def _introspect(_client, app_id, schema_name):
        _ = app_id, schema_name
        if schemas:
            return schemas.pop(0)
        return {
            "app_id": "p1",
            "schema_name": "app_deadbeef1234",
            "tables": [],
            "relationships": [],
        }

    versions = ["v1", "v2"]

    def _version(_schema):
        if versions:
            return versions.pop(0)
        return "v2"

    monkeypatch.setattr(schema_introspection, "introspect_schema", _introspect)
    monkeypatch.setattr(schema_diff, "compute_schema_version", _version)
    monkeypatch.setattr(
        schema_diff,
        "build_schema_diff",
        lambda _current, _draft: {
            "destructive": False,
            "destructive_details": [],
            "operations": [],
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        schema_apply,
        "apply_schema_changes",
        lambda *_args, **_kwargs: {
            "migration_files": [
                "/db/migrations/20260211T120000Z__schema_editor.sql",
                "/db/migrations/20260211T120000Z__schema_editor.plan.json",
            ],
            "warnings": [],
            "summary": {"operation_count": 1},
            "diff": {"operations": [{"type": "add_table", "table": "customers"}], "sql": ["CREATE TABLE ..."]},
        },
    )
    monkeypatch.setattr(gitlab_config, "git_sync_enabled", lambda: False)
    monkeypatch.setattr(gitlab_config, "git_sync_required", lambda: False)

    client = TestClient(ws_server.app)
    res = client.post(
        "/api/db/p1/schema/apply",
        json={
            "base_version": "v1",
            "confirm_destructive": True,
            "draft": {"tables": [], "relationships": []},
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["applied"] is True
    assert data["version"] == "v2"
    assert len(data["migration_files"]) == 2
    assert data["git_sync"]["attempted"] is False
