from __future__ import annotations

from dataclasses import dataclass


@dataclass
class _FakeProject:
    project_id: str
    slug: str
    template_id: str


class _FakeSessionManager:
    def __init__(self, backend_obj: object) -> None:
        self._backend = backend_obj

    def get_backend(self, _session_id: str):
        return self._backend


class _FakeAgent:
    def __init__(self, backend_obj: object) -> None:
        self._session_manager = _FakeSessionManager(backend_obj)

    async def init(
        self,
        session_id: str,
        template_id: str | None = None,
        slug: str | None = None,
    ) -> bool:
        _ = session_id, template_id, slug
        return True


def test_api_git_pull_success(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    import src.runtimes.ws_server as ws_server

    monkeypatch.setattr(ws_server, "_hasura_enabled", lambda: True)
    monkeypatch.setattr(ws_server, "_get_agent", lambda: _FakeAgent(object()))

    import src.db.provisioning as provisioning
    import src.gitlab.config as gitlab_config
    import src.gitlab.integration as gitlab_integration
    import src.gitlab.sync as gitlab_sync
    import src.projects.store as projects_store

    monkeypatch.setattr(provisioning, "hasura_client_from_env", lambda: object())
    monkeypatch.setattr(gitlab_config, "git_sync_enabled", lambda: True)

    proj = _FakeProject(project_id="p1", slug="my-proj", template_id="vite")

    monkeypatch.setattr(projects_store, "get_project_by_id", lambda *_a, **_k: proj)
    monkeypatch.setattr(
        gitlab_integration,
        "ensure_gitlab_repo_for_project",
        lambda *_a, **_k: (proj, {"http_url_to_repo": "http://example/repo.git"}),
    )
    monkeypatch.setattr(
        gitlab_sync,
        "sync_repo_tree_to_sandbox",
        lambda _backend, **_kwargs: {
            "updated": False,
            "remote_sha": "deadbeef",
            "applied": {"added": [], "modified": [], "deleted": []},
            "conflicts": [],
        },
    )

    client = TestClient(ws_server.app)
    res = client.post("/api/projects/p1/git/pull", json={})
    assert res.status_code == 200
    data = res.json()
    assert data["updated"] is False
    assert data["remote_sha"] == "deadbeef"


def test_api_git_pull_baseline_missing(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    import src.runtimes.ws_server as ws_server

    monkeypatch.setattr(ws_server, "_hasura_enabled", lambda: True)
    monkeypatch.setattr(ws_server, "_get_agent", lambda: _FakeAgent(object()))

    import src.db.provisioning as provisioning
    import src.gitlab.config as gitlab_config
    import src.gitlab.integration as gitlab_integration
    import src.gitlab.sync as gitlab_sync
    import src.projects.store as projects_store

    monkeypatch.setattr(provisioning, "hasura_client_from_env", lambda: object())
    monkeypatch.setattr(gitlab_config, "git_sync_enabled", lambda: True)

    proj = _FakeProject(project_id="p1", slug="my-proj", template_id="vite")

    monkeypatch.setattr(projects_store, "get_project_by_id", lambda *_a, **_k: proj)
    monkeypatch.setattr(
        gitlab_integration,
        "ensure_gitlab_repo_for_project",
        lambda *_a, **_k: (proj, {"http_url_to_repo": "http://example/repo.git"}),
    )
    monkeypatch.setattr(
        gitlab_sync,
        "sync_repo_tree_to_sandbox",
        lambda _backend, **_kwargs: {
            "error": "git_pull_no_baseline",
            "remote_sha": "abc123",
        },
    )

    client = TestClient(ws_server.app)
    res = client.post("/api/projects/p1/git/pull", json={})
    assert res.status_code == 409
    assert res.json()["error"] == "git_pull_no_baseline"


def test_api_git_pull_disabled(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    import src.runtimes.ws_server as ws_server

    monkeypatch.setattr(ws_server, "_hasura_enabled", lambda: True)
    monkeypatch.setattr(ws_server, "_get_agent", lambda: _FakeAgent(object()))

    import src.gitlab.config as gitlab_config

    monkeypatch.setattr(gitlab_config, "git_sync_enabled", lambda: False)

    client = TestClient(ws_server.app)
    res = client.post("/api/projects/p1/git/pull", json={})
    assert res.status_code == 409


def test_api_git_pull_missing_repo_url(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    import src.runtimes.ws_server as ws_server

    monkeypatch.setattr(ws_server, "_hasura_enabled", lambda: True)
    monkeypatch.setattr(ws_server, "_get_agent", lambda: _FakeAgent(object()))

    import src.db.provisioning as provisioning
    import src.gitlab.config as gitlab_config
    import src.gitlab.integration as gitlab_integration
    import src.projects.store as projects_store

    monkeypatch.setattr(provisioning, "hasura_client_from_env", lambda: object())
    monkeypatch.setattr(gitlab_config, "git_sync_enabled", lambda: True)

    proj = _FakeProject(project_id="p1", slug="my-proj", template_id="vite")

    monkeypatch.setattr(projects_store, "get_project_by_id", lambda *_a, **_k: proj)
    monkeypatch.setattr(
        gitlab_integration,
        "ensure_gitlab_repo_for_project",
        lambda *_a, **_k: (proj, {}),
    )

    client = TestClient(ws_server.app)
    res = client.post("/api/projects/p1/git/pull", json={})
    assert res.status_code == 400

