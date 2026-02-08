from __future__ import annotations

import os


def gitlab_base_url() -> str:
    return (os.environ.get("GITLAB_BASE_URL") or "https://git.mayflower.de").strip().rstrip(
        "/"
    )


def gitlab_group_path() -> str:
    return (os.environ.get("GITLAB_GROUP_PATH") or "amicable").strip().strip("/")


def gitlab_token() -> str:
    return (os.environ.get("GITLAB_TOKEN") or "").strip()


def git_sync_enabled() -> bool:
    raw = (os.environ.get("AMICABLE_GIT_SYNC_ENABLED") or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    # Default: enabled iff token is present.
    return bool(gitlab_token())


def git_sync_branch() -> str:
    return (os.environ.get("AMICABLE_GIT_SYNC_BRANCH") or "main").strip() or "main"


def git_sync_cache_dir() -> str:
    return (os.environ.get("AMICABLE_GIT_SYNC_CACHE_DIR") or "/tmp/amicable-git-cache").strip() or "/tmp/amicable-git-cache"


_DEFAULT_EXCLUDES = [
    "node_modules/",
    ".git/",
    "dist/",
    "build/",
    ".vite/",
    ".cache/",
    ".turbo/",
    "coverage/",
    ".amicable_snapshot.tgz",
    ".env",
    ".env.*",
]


def git_sync_excludes() -> list[str]:
    raw = (os.environ.get("AMICABLE_GIT_SYNC_EXCLUDES") or "").strip()
    if not raw:
        return list(_DEFAULT_EXCLUDES)
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return parts or list(_DEFAULT_EXCLUDES)


def git_commit_author_name() -> str:
    return (os.environ.get("AMICABLE_GIT_COMMIT_AUTHOR_NAME") or "amicable-bot").strip() or "amicable-bot"


def git_commit_author_email() -> str:
    return (
        os.environ.get("AMICABLE_GIT_COMMIT_AUTHOR_EMAIL")
        or "amicable@mayflower.de"
    ).strip() or "amicable@mayflower.de"


def gitlab_repo_visibility() -> str:
    # GitLab values: private/internal/public
    v = (os.environ.get("AMICABLE_GITLAB_REPO_VISIBILITY") or "internal").strip().lower()
    return v if v in ("private", "internal", "public") else "internal"
