from __future__ import annotations

import os


def _env_bool(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    v = raw.strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return default


def gitlab_base_url() -> str:
    return (
        (os.environ.get("GITLAB_BASE_URL") or "https://git.mayflower.de")
        .strip()
        .rstrip("/")
    )


def gitlab_group_path() -> str:
    return (os.environ.get("GITLAB_GROUP_PATH") or "amicable").strip().strip("/")


def gitlab_token() -> str:
    return (os.environ.get("GITLAB_TOKEN") or "").strip()


def git_sync_enabled() -> bool:
    # Explicit override, otherwise enabled iff token is present.
    if "AMICABLE_GIT_SYNC_ENABLED" in os.environ:
        return _env_bool("AMICABLE_GIT_SYNC_ENABLED", default=True)
    return bool(gitlab_token())


def git_sync_required() -> bool:
    # Default to required in production deployments; tests/dev can disable explicitly.
    return _env_bool("AMICABLE_GIT_SYNC_REQUIRED", default=True)


def ensure_git_sync_configured() -> None:
    """Raise if Git sync is required but not configured."""
    if not git_sync_enabled():
        if git_sync_required():
            raise RuntimeError("GitLab sync required but disabled or not configured")
        return
    if not gitlab_token():
        # AMICABLE_GIT_SYNC_ENABLED can force-enable even when token is missing.
        raise RuntimeError("GITLAB_TOKEN is not set")


def git_sync_branch() -> str:
    return (os.environ.get("AMICABLE_GIT_SYNC_BRANCH") or "main").strip() or "main"


def git_sync_cache_dir() -> str:
    return (
        os.environ.get("AMICABLE_GIT_SYNC_CACHE_DIR") or "/tmp/amicable-git-cache"
    ).strip() or "/tmp/amicable-git-cache"


_DEFAULT_EXCLUDES = [
    "node_modules/",
    # PHP/Laravel dependencies are large and should not be committed.
    "vendor/",
    ".git/",
    # Sandbox-local state (not part of the repo).
    ".amicable/",
    "dist/",
    "build/",
    ".vite/",
    ".cache/",
    ".turbo/",
    "coverage/",
    # Laravel runtime artifacts (logs, caches, uploaded files).
    "storage/",
    "bootstrap/cache/",
    ".env",
    ".env.*",
]


def git_sync_excludes() -> list[str]:
    raw = (os.environ.get("AMICABLE_GIT_SYNC_EXCLUDES") or "").strip()
    if not raw:
        return list(_DEFAULT_EXCLUDES)
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    out = parts or list(_DEFAULT_EXCLUDES)

    # Always exclude sandbox-local state even if AMICABLE_GIT_SYNC_EXCLUDES is set.
    if not any(p.rstrip("/").lstrip("/") == ".amicable" for p in out):
        out.append(".amicable/")
    return out


def git_commit_author_name() -> str:
    return (
        os.environ.get("AMICABLE_GIT_COMMIT_AUTHOR_NAME") or "amicable-bot"
    ).strip() or "amicable-bot"


def git_commit_author_email() -> str:
    return (
        os.environ.get("AMICABLE_GIT_COMMIT_AUTHOR_EMAIL") or "amicable@mayflower.de"
    ).strip() or "amicable@mayflower.de"


def gitlab_repo_visibility() -> str:
    # GitLab values: private/internal/public
    v = (
        (os.environ.get("AMICABLE_GITLAB_REPO_VISIBILITY") or "internal")
        .strip()
        .lower()
    )
    return v if v in ("private", "internal", "public") else "internal"
