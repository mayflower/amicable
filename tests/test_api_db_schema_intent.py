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


def test_api_db_schema_intent_version_conflict(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    import src.runtimes.ws_server as ws_server

    monkeypatch.setattr(
        ws_server,
        "_ensure_project_access",
        lambda _request, project_id: _FakeProject(
            project_id=project_id, slug="proj", template_id="lovable-vite"
        ),
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
        "/api/db/p1/schema/intent",
        json={
            "base_version": "old-v",
            "draft": {"tables": [], "relationships": []},
            "intent_text": "Add customers",
        },
    )
    assert res.status_code == 409
    assert res.json()["error"] == "version_conflict"


def test_api_db_schema_intent_success(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    import src.runtimes.ws_server as ws_server

    monkeypatch.setattr(
        ws_server,
        "_ensure_project_access",
        lambda _request, project_id: _FakeProject(
            project_id=project_id, slug="proj", template_id="lovable-vite"
        ),
    )

    import src.db.provisioning as provisioning
    import src.db.schema_ai_intent as schema_ai_intent
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
    monkeypatch.setattr(schema_diff, "compute_schema_version", lambda _schema: "v1")
    monkeypatch.setattr(
        schema_ai_intent,
        "generate_schema_intent",
        lambda **_kwargs: {
            "draft": {
                "app_id": "p1",
                "schema_name": "app_deadbeef1234",
                "tables": [
                    {
                        "name": "customers",
                        "label": "Customers",
                        "position": {"x": 0, "y": 0},
                        "columns": [],
                    }
                ],
                "relationships": [],
            },
            "assistant_message": "Added customers table.",
            "change_cards": [
                {
                    "id": "card_1",
                    "title": "Add table",
                    "description": "Create Customers.",
                    "kind": "add_table",
                    "risk": "low",
                }
            ],
            "needs_clarification": False,
            "clarification_question": "",
            "clarification_options": [],
            "warnings": [],
        },
    )

    client = TestClient(ws_server.app)
    res = client.post(
        "/api/db/p1/schema/intent",
        json={
            "base_version": "v1",
            "draft": {"tables": [], "relationships": []},
            "intent_text": "Add customers",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["assistant_message"] == "Added customers table."
    assert data["base_version"] == "v1"
    assert len(data["change_cards"]) == 1
    assert data["draft"]["tables"][0]["name"] == "customers"

