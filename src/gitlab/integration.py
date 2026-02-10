from __future__ import annotations

import logging

from src.gitlab.client import GitLabClient, GitLabError, GitLabProject
from src.gitlab.config import (
    ensure_git_sync_configured,
    git_sync_enabled,
    git_sync_required,
    gitlab_group_path,
    gitlab_repo_visibility,
)
from src.projects import store as projects_store

logger = logging.getLogger(__name__)


def _candidate_slug(base: str, *, suffix: str | None = None) -> str:
    if not suffix:
        return base
    base_max = max(1, 63 - (1 + len(suffix)))
    return f"{base[:base_max].rstrip('-')}-{suffix}"


def _fallback_slug(project_id: str, base: str, attempt: int) -> str:
    short = project_id.replace("-", "")
    suffix = short[: (4 + attempt // 3)]
    return _candidate_slug(base, suffix=suffix)


def _path_taken(err: GitLabError) -> bool:
    payload = err.payload
    if not isinstance(payload, dict):
        return False
    msg = payload.get("message")
    if isinstance(msg, dict):
        v = msg.get("path")
        if isinstance(v, list) and any("taken" in str(x).lower() for x in v):
            return True
    return "already been taken" in str(payload).lower()


def ensure_gitlab_repo_for_project(
    client,
    *,
    owner: projects_store.ProjectOwner,
    project: projects_store.Project,
) -> tuple[projects_store.Project, dict | None]:
    """Ensure GitLab repo exists for this project.

    Returns (updated_project, git_dto_or_none).
    """

    ensure_git_sync_configured()
    required = git_sync_required()
    if not git_sync_enabled():
        return project, None

    gl = GitLabClient.from_env()

    group = gitlab_group_path()

    def _persist(p: GitLabProject, *, slug_for_db: str) -> projects_store.Project:
        return projects_store.set_gitlab_metadata(
            client,
            owner=owner,
            project_id=project.project_id,
            gitlab_project_id=p.id,
            gitlab_path=slug_for_db,
            gitlab_web_url=p.web_url,
        )

    def _git_dto(p: GitLabProject) -> dict:
        return {
            "web_url": p.web_url,
            "path_with_namespace": p.path_with_namespace,
            "gitlab_project_id": p.id,
            "http_url_to_repo": p.http_url_to_repo,
        }

    desired = (project.slug or "").strip()
    if desired:
        try:
            existing = gl.get_project_by_path(f"{group}/{desired}")
            if existing is not None:
                updated = _persist(existing, slug_for_db=desired)
                return updated, _git_dto(existing)
        except Exception:
            logger.exception("gitlab lookup failed")
            if required:
                raise
            return project, None

        # Try create with the desired slug.
        try:
            ns_id = gl.get_group_id(group)
            created = gl.create_project(
                namespace_id=ns_id,
                name=project.name,
                path=desired,
                visibility=gitlab_repo_visibility(),
            )
            updated = _persist(created, slug_for_db=desired)
            return updated, _git_dto(created)
        except GitLabError as e:
            if not _path_taken(e):
                logger.warning("gitlab create failed: %s", e)
                if required:
                    raise
                return project, None
            # collision: fall through to fallback logic.
        except Exception:
            logger.exception("gitlab create failed")
            if required:
                raise
            return project, None

    base = projects_store.slugify(project.name)

    # Collision resolution: pick fallback slug, update DB slug, then create repo.
    # We only do this for 'path taken' errors.
    try:
        ns_id = gl.get_group_id(group)
    except Exception:
        logger.exception("gitlab group lookup failed")
        if required:
            raise
        return project, None

    for attempt in range(1, 20):
        candidate = _fallback_slug(project.project_id, base, attempt)
        try:
            # Update project slug first so UI routes match repo path.
            updated_p = projects_store.set_project_slug(
                client,
                owner=owner,
                project_id=project.project_id,
                new_slug=candidate,
            )
        except Exception:
            # Likely DB unique collision; try another.
            continue

        try:
            created = gl.create_project(
                namespace_id=ns_id,
                name=project.name,
                path=candidate,
                visibility=gitlab_repo_visibility(),
            )
            updated = projects_store.set_gitlab_metadata(
                client,
                owner=owner,
                project_id=project.project_id,
                gitlab_project_id=created.id,
                gitlab_path=candidate,
                gitlab_web_url=created.web_url,
            )
            return updated, _git_dto(created)
        except GitLabError as e:
            if _path_taken(e):
                # try next candidate
                project = updated_p
                continue
            logger.warning("gitlab create failed: %s", e)
            if required:
                raise
            return updated_p, None
        except Exception:
            logger.exception("gitlab create failed")
            if required:
                raise
            return updated_p, None

    msg = "Failed to allocate a unique GitLab project path after multiple attempts"
    if required:
        raise RuntimeError(msg)
    logger.warning(msg)
    return project, None


def rename_gitlab_repo_to_match_project_slug(
    client,
    *,
    owner: projects_store.ProjectOwner,
    project: projects_store.Project,
    new_name: str,
) -> tuple[projects_store.Project, dict | None]:
    """Rename/move the GitLab repo path to match project.slug.

    If metadata is missing, we will first ensure repo exists.

    Returns (updated_project, git_dto_or_none). Best-effort.
    """

    ensure_git_sync_configured()
    required = git_sync_required()
    if not git_sync_enabled():
        return project, None

    project, git_dto = ensure_gitlab_repo_for_project(
        client, owner=owner, project=project
    )

    gitlab_id = project.gitlab_project_id
    if not isinstance(gitlab_id, int):
        return project, git_dto

    gl = GitLabClient.from_env()
    base = projects_store.slugify(new_name)

    def _git_dto_from_proj(p: GitLabProject) -> dict:
        return {
            "web_url": p.web_url,
            "path_with_namespace": p.path_with_namespace,
            "gitlab_project_id": p.id,
            "http_url_to_repo": p.http_url_to_repo,
        }

    desired = (project.slug or "").strip()
    if not desired:
        return project, git_dto

    # Attempt rename; if path taken, update DB slug to fallback and retry.
    for attempt in range(0, 20):
        candidate = (
            desired
            if attempt == 0
            else _fallback_slug(project.project_id, base, attempt)
        )
        if attempt > 0:
            try:
                project = projects_store.set_project_slug(
                    client,
                    owner=owner,
                    project_id=project.project_id,
                    new_slug=candidate,
                )
            except Exception:
                continue

        try:
            updated = gl.update_project(gitlab_id, name=new_name, path=candidate)
            project = projects_store.set_gitlab_metadata(
                client,
                owner=owner,
                project_id=project.project_id,
                gitlab_project_id=updated.id,
                gitlab_path=candidate,
                gitlab_web_url=updated.web_url,
            )
            return project, _git_dto_from_proj(updated)
        except GitLabError as e:
            if _path_taken(e):
                continue
            logger.warning("gitlab rename failed: %s", e)
            if required:
                raise
            return project, git_dto
        except Exception:
            logger.exception("gitlab rename failed")
            if required:
                raise
            return project, git_dto

    return project, git_dto


def delete_gitlab_repo_for_project(
    client,
    *,
    owner: projects_store.ProjectOwner,
    project: projects_store.Project,
) -> None:
    """Delete the GitLab repo for a project.

    Behavior:
    - If Git sync is disabled: no-op.
    - If required and deletion fails: raise.
    - 404 is treated as already deleted.
    """
    # Metadata deletion is best-effort and does not require Hasura access.
    del client, owner
    required = git_sync_required()
    if not git_sync_enabled():
        return
    # Only validate configuration (token, requiredness) if Git sync is enabled.
    ensure_git_sync_configured()

    gl = GitLabClient.from_env()

    gitlab_id = project.gitlab_project_id
    if isinstance(gitlab_id, int):
        try:
            gl.delete_project(gitlab_id)
            return
        except Exception:
            logger.exception("gitlab delete failed")
            if required:
                raise
            return

    # Fallback: try lookup by stored path/slug.
    group = gitlab_group_path()
    slug = (project.gitlab_path or project.slug or "").strip()
    if not slug:
        return

    try:
        existing = gl.get_project_by_path(f"{group}/{slug}")
        if existing is None:
            return
        gl.delete_project(existing.id)
    except Exception:
        logger.exception("gitlab delete failed")
        if required:
            raise
