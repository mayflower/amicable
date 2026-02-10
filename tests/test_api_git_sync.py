from __future__ import annotations

from dataclasses import dataclass


@dataclass
class _FakeProject:
    project_id: str
    slug: str
    template_id: str


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


def test_api_git_sync_success(monkeypatch) -> None:
    # Import lazily so environments without optional deps can skip running this test.
    from fastapi.testclient import TestClient

    import src.runtimes.ws_server as ws_server

    monkeypatch.setattr(ws_server, "_hasura_enabled", lambda: True)
    monkeypatch.setattr(ws_server, "_get_agent", lambda: _FakeAgent())

    import src.db.provisioning as provisioning
    import src.gitlab.config as gitlab_config
    import src.gitlab.integration as gitlab_integration
    import src.gitlab.sync as gitlab_sync
    import src.projects.store as projects_store

    monkeypatch.setattr(provisioning, "hasura_client_from_env", lambda: object())
    monkeypatch.setattr(gitlab_config, "git_sync_enabled", lambda: True)
    monkeypatch.setattr(gitlab_config, "git_sync_required", lambda: True)

    proj = _FakeProject(project_id="p1", slug="my-proj", template_id="lovable-vite")

    def _get_project_by_id(*_args, **_kwargs):
        return proj

    def _ensure_gitlab_repo_for_project(*_args, **_kwargs):
        project = _kwargs.get("project")
        return project, {"http_url_to_repo": "http://example/repo.git"}

    monkeypatch.setattr(
        projects_store,
        "get_project_by_id",
        _get_project_by_id,
    )
    monkeypatch.setattr(
        gitlab_integration,
        "ensure_gitlab_repo_for_project",
        _ensure_gitlab_repo_for_project,
    )
    monkeypatch.setattr(
        gitlab_sync,
        "sync_sandbox_tree_to_repo",
        lambda _backend, **_kwargs: (True, "deadbeef", "stat", "name-status"),
    )

    client = TestClient(ws_server.app)
    res = client.post("/api/projects/p1/git/sync", json={"commit_message": "msg"})
    assert res.status_code == 200
    data = res.json()
    assert data["pushed"] is True
    assert data["commit_sha"] == "deadbeef"


def test_api_git_sync_disabled(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    import src.runtimes.ws_server as ws_server

    monkeypatch.setattr(ws_server, "_hasura_enabled", lambda: True)
    monkeypatch.setattr(ws_server, "_get_agent", lambda: _FakeAgent())

    import src.gitlab.config as gitlab_config

    monkeypatch.setattr(gitlab_config, "git_sync_enabled", lambda: False)

    client = TestClient(ws_server.app)
    res = client.post("/api/projects/p1/git/sync", json={})
    assert res.status_code == 409


def test_api_git_sync_missing_repo_url(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    import src.runtimes.ws_server as ws_server

    monkeypatch.setattr(ws_server, "_hasura_enabled", lambda: True)
    monkeypatch.setattr(ws_server, "_get_agent", lambda: _FakeAgent())

    import src.db.provisioning as provisioning
    import src.gitlab.config as gitlab_config
    import src.gitlab.integration as gitlab_integration
    import src.projects.store as projects_store

    monkeypatch.setattr(provisioning, "hasura_client_from_env", lambda: object())
    monkeypatch.setattr(gitlab_config, "git_sync_enabled", lambda: True)
    monkeypatch.setattr(gitlab_config, "git_sync_required", lambda: True)

    proj = _FakeProject(project_id="p1", slug="my-proj", template_id="lovable-vite")

    def _get_project_by_id(*_args, **_kwargs):
        return proj

    def _ensure_gitlab_repo_for_project(*_args, **_kwargs):
        project = _kwargs.get("project")
        return project, {}

    monkeypatch.setattr(
        projects_store,
        "get_project_by_id",
        _get_project_by_id,
    )
    monkeypatch.setattr(
        gitlab_integration,
        "ensure_gitlab_repo_for_project",
        _ensure_gitlab_repo_for_project,
    )

    client = TestClient(ws_server.app)
    res = client.post("/api/projects/p1/git/sync", json={})
    assert res.status_code == 400
