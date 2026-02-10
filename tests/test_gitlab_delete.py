from __future__ import annotations

import pytest

# `src.gitlab.*` depends on `requests` (installed in production/CI). When running
# tests in a minimal local environment without dependencies, skip gracefully.
pytest.importorskip("requests")

from src.gitlab.integration import delete_gitlab_repo_for_project
from src.projects.store import Project, ProjectOwner


def test_delete_gitlab_repo_noop_when_git_sync_disabled(monkeypatch) -> None:
    # Even if Git sync is marked "required" by default env settings, deletion should
    # be a no-op when Git sync is disabled (e.g. no token configured in dev).
    monkeypatch.setenv("AMICABLE_GIT_SYNC_REQUIRED", "1")
    monkeypatch.delenv("AMICABLE_GIT_SYNC_ENABLED", raising=False)
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)

    owner = ProjectOwner(sub="sub", email="user@example.com")
    project = Project(
        project_id="p1",
        owner_sub=owner.sub,
        owner_email=owner.email,
        name="Test",
        slug="test",
        gitlab_project_id=123,
        gitlab_path="test",
        gitlab_web_url="https://example.invalid",
    )

    # Should not raise (and must not attempt network I/O).
    delete_gitlab_repo_for_project(None, owner=owner, project=project)
