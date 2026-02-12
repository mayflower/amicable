from __future__ import annotations

import logging
import re
import threading
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from src.db.hasura_client import HasuraClient


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """Convert a name into a URL-safe slug.

    - lowercase
    - replace non [a-z0-9] with '-'
    - collapse/trim '-'
    - limit to 50 chars (suffix may be added later)
    """
    s = (name or "").strip().lower()
    s = _SLUG_RE.sub("-", s)
    s = s.strip("-")
    s = re.sub(r"-{2,}", "-", s)
    if not s:
        s = "project"
    return s[:50].rstrip("-")


def _sql_str(value: str) -> str:
    return "'" + (value or "").replace("'", "''") + "'"


_schema_ready = False
_schema_lock = threading.Lock()
_log = logging.getLogger(__name__)


def ensure_projects_schema(client: HasuraClient) -> None:
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        _log.info("Running projects schema migration (once per process)")
        client.run_sql(
            """
            CREATE SCHEMA IF NOT EXISTS amicable_meta;
            CREATE TABLE IF NOT EXISTS amicable_meta.projects (
              project_id text PRIMARY KEY,
              owner_sub text NOT NULL,
              owner_email text NOT NULL,
              name text NOT NULL,
              slug text NOT NULL UNIQUE,
              sandbox_id text NULL,
              template_id text NULL,
              gitlab_project_id bigint NULL,
              gitlab_path text NULL,
              gitlab_web_url text NULL,
              locked_by_sub text NULL,
              locked_at timestamptz NULL,
              created_at timestamptz NOT NULL DEFAULT now(),
              updated_at timestamptz NOT NULL DEFAULT now(),
              deleted_at timestamptz NULL
            );
            ALTER TABLE amicable_meta.projects
              ADD COLUMN IF NOT EXISTS sandbox_id text NULL;
            ALTER TABLE amicable_meta.projects
              ADD COLUMN IF NOT EXISTS template_id text NULL;
            ALTER TABLE amicable_meta.projects
              ADD COLUMN IF NOT EXISTS gitlab_project_id bigint NULL;
            ALTER TABLE amicable_meta.projects
              ADD COLUMN IF NOT EXISTS gitlab_path text NULL;
            ALTER TABLE amicable_meta.projects
              ADD COLUMN IF NOT EXISTS gitlab_web_url text NULL;
            ALTER TABLE amicable_meta.projects
              ADD COLUMN IF NOT EXISTS locked_by_sub text NULL;
            ALTER TABLE amicable_meta.projects
              ADD COLUMN IF NOT EXISTS locked_at timestamptz NULL;

            CREATE TABLE IF NOT EXISTS amicable_meta.project_members (
              project_id text NOT NULL REFERENCES amicable_meta.projects(project_id) ON DELETE CASCADE,
              user_sub text NOT NULL,
              user_email text NOT NULL,
              added_at timestamptz NOT NULL DEFAULT now(),
              added_by_sub text NULL,
              PRIMARY KEY (project_id, user_sub)
            );
            CREATE INDEX IF NOT EXISTS idx_project_members_user
              ON amicable_meta.project_members(user_sub);
            CREATE INDEX IF NOT EXISTS idx_project_members_email
              ON amicable_meta.project_members(user_email);
            """.strip()
        )
        _schema_ready = True


@dataclass(frozen=True)
class ProjectOwner:
    sub: str
    email: str


@dataclass(frozen=True)
class Project:
    project_id: str
    owner_sub: str
    owner_email: str
    name: str
    slug: str
    sandbox_id: str | None = None
    template_id: str | None = None
    gitlab_project_id: int | None = None
    gitlab_path: str | None = None
    gitlab_web_url: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class ProjectMember:
    project_id: str
    user_sub: str | None  # None if invited by email but not yet logged in
    user_email: str
    added_at: str | None = None
    added_by_sub: str | None = None


@dataclass(frozen=True)
class ProjectLock:
    project_id: str
    locked_by_sub: str
    locked_by_email: str
    locked_at: str


def _tuples_to_dicts(res: dict[str, Any]) -> list[dict[str, Any]]:
    rows = res.get("result")
    if not isinstance(rows, list) or len(rows) < 2:
        return []
    header = rows[0]
    if not isinstance(header, list):
        return []
    out: list[dict[str, Any]] = []
    for r in rows[1:]:
        if not isinstance(r, list):
            continue
        d: dict[str, Any] = {}
        for idx, col in enumerate(header):
            if isinstance(col, str) and idx < len(r):
                val = r[idx]
                # Hasura run_sql returns SQL NULL as the string "NULL".
                d[col] = None if val == "NULL" else val
        out.append(d)
    return out


def _get_project_by_id_any_owner(
    client: HasuraClient, *, project_id: str
) -> Project | None:
    ensure_projects_schema(client)
    # Note: this helper intentionally filters out soft-deleted projects.
    res = client.run_sql(
        f"""
        SELECT project_id, owner_sub, owner_email, name, slug, sandbox_id, template_id,
               gitlab_project_id, gitlab_path, gitlab_web_url,
               created_at, updated_at
        FROM amicable_meta.projects
        WHERE project_id = {_sql_str(project_id)} AND deleted_at IS NULL
        LIMIT 1;
        """.strip(),
        read_only=True,
    )
    rows = _tuples_to_dicts(res)
    if not rows:
        return None
    r = rows[0]
    return Project(
        project_id=str(r["project_id"]),
        owner_sub=str(r["owner_sub"]),
        owner_email=str(r["owner_email"]),
        name=str(r["name"]),
        slug=str(r["slug"]),
        sandbox_id=str(r.get("sandbox_id"))
        if r.get("sandbox_id") is not None
        else None,
        template_id=str(r.get("template_id"))
        if r.get("template_id") is not None
        else None,
        gitlab_project_id=int(r["gitlab_project_id"])
        if r.get("gitlab_project_id") is not None
        else None,
        gitlab_path=str(r.get("gitlab_path"))
        if r.get("gitlab_path") is not None
        else None,
        gitlab_web_url=str(r.get("gitlab_web_url"))
        if r.get("gitlab_web_url") is not None
        else None,
        created_at=str(r.get("created_at"))
        if r.get("created_at") is not None
        else None,
        updated_at=str(r.get("updated_at"))
        if r.get("updated_at") is not None
        else None,
    )


def _project_row_by_id_including_deleted(
    client: HasuraClient, *, project_id: str
) -> dict[str, Any] | None:
    """Return raw project row (including deleted rows) for internal recovery logic."""
    ensure_projects_schema(client)
    res = client.run_sql(
        f"""
        SELECT project_id, owner_sub, owner_email, name, slug, deleted_at
        FROM amicable_meta.projects
        WHERE project_id = {_sql_str(project_id)}
        LIMIT 1;
        """.strip(),
        read_only=True,
    )
    rows = _tuples_to_dicts(res)
    return rows[0] if rows else None


def get_project_any_owner(client: HasuraClient, *, project_id: str) -> Project | None:
    """Return project metadata without enforcing ownership.

    This is used by internal services (agent/runtime) after authentication and
    authorization have already been enforced upstream.
    """
    return _get_project_by_id_any_owner(client, project_id=project_id)


def get_project_template_id_any_owner(
    client: HasuraClient, *, project_id: str
) -> str | None:
    """Return template_id for a project_id without enforcing ownership.

    This is used by the agent runtime after upstream request/WS handlers have
    already enforced access control.
    """
    ensure_projects_schema(client)
    res = client.run_sql(
        f"""
        SELECT template_id
        FROM amicable_meta.projects
        WHERE project_id = {_sql_str(project_id)} AND deleted_at IS NULL
        LIMIT 1;
        """.strip(),
        read_only=True,
    )
    rows = _tuples_to_dicts(res)
    if not rows:
        return None
    tid = rows[0].get("template_id")
    return str(tid) if tid is not None else None


def get_project_by_id(
    client: HasuraClient, *, owner: ProjectOwner, project_id: str
) -> Project | None:
    p = _get_project_by_id_any_owner(client, project_id=project_id)
    if not p:
        return None
    if not is_project_member(
        client, project_id=project_id, user_sub=owner.sub, user_email=owner.email
    ):
        return None
    return p


def get_project_by_slug(
    client: HasuraClient, *, owner: ProjectOwner, slug: str
) -> Project | None:
    ensure_projects_schema(client)
    res = client.run_sql(
        f"""
        SELECT project_id, owner_sub, owner_email, name, slug, sandbox_id, template_id,
               gitlab_project_id, gitlab_path, gitlab_web_url,
               created_at, updated_at
        FROM amicable_meta.projects
        WHERE slug = {_sql_str(slug)} AND deleted_at IS NULL
        LIMIT 1;
        """.strip(),
        read_only=True,
    )
    rows = _tuples_to_dicts(res)
    if not rows:
        return None
    r = rows[0]
    project_id = str(r["project_id"])
    if not is_project_member(
        client, project_id=project_id, user_sub=owner.sub, user_email=owner.email
    ):
        return None
    return Project(
        project_id=project_id,
        owner_sub=str(r["owner_sub"]),
        owner_email=str(r["owner_email"]),
        name=str(r["name"]),
        slug=str(r["slug"]),
        sandbox_id=str(r.get("sandbox_id"))
        if r.get("sandbox_id") is not None
        else None,
        template_id=str(r.get("template_id"))
        if r.get("template_id") is not None
        else None,
        gitlab_project_id=int(r["gitlab_project_id"])
        if r.get("gitlab_project_id") is not None
        else None,
        gitlab_path=str(r.get("gitlab_path"))
        if r.get("gitlab_path") is not None
        else None,
        gitlab_web_url=str(r.get("gitlab_web_url"))
        if r.get("gitlab_web_url") is not None
        else None,
        created_at=str(r.get("created_at"))
        if r.get("created_at") is not None
        else None,
        updated_at=str(r.get("updated_at"))
        if r.get("updated_at") is not None
        else None,
    )


def get_project_by_slug_any_owner(client: HasuraClient, *, slug: str) -> Project | None:
    """Return a project by slug without enforcing ownership.

    This is intended for internal services (e.g. preview routing) where access
    control is handled elsewhere (ingress/network policies).
    """
    ensure_projects_schema(client)
    res = client.run_sql(
        f"""
        SELECT project_id, owner_sub, owner_email, name, slug, sandbox_id, template_id,
               gitlab_project_id, gitlab_path, gitlab_web_url,
               created_at, updated_at
        FROM amicable_meta.projects
        WHERE slug = {_sql_str(slug)} AND deleted_at IS NULL
        LIMIT 1;
        """.strip(),
        read_only=True,
    )
    rows = _tuples_to_dicts(res)
    if not rows:
        return None
    r = rows[0]
    return Project(
        project_id=str(r["project_id"]),
        owner_sub=str(r["owner_sub"]),
        owner_email=str(r["owner_email"]),
        name=str(r["name"]),
        slug=str(r["slug"]),
        sandbox_id=str(r.get("sandbox_id"))
        if r.get("sandbox_id") is not None
        else None,
        template_id=str(r.get("template_id"))
        if r.get("template_id") is not None
        else None,
        gitlab_project_id=int(r["gitlab_project_id"])
        if r.get("gitlab_project_id") is not None
        else None,
        gitlab_path=str(r.get("gitlab_path"))
        if r.get("gitlab_path") is not None
        else None,
        gitlab_web_url=str(r.get("gitlab_web_url"))
        if r.get("gitlab_web_url") is not None
        else None,
        created_at=str(r.get("created_at"))
        if r.get("created_at") is not None
        else None,
        updated_at=str(r.get("updated_at"))
        if r.get("updated_at") is not None
        else None,
    )


def set_project_sandbox_id_any_owner(
    client: HasuraClient, *, project_id: str, sandbox_id: str
) -> None:
    ensure_projects_schema(client)
    client.run_sql(
        f"""
        UPDATE amicable_meta.projects
        SET sandbox_id = {_sql_str(sandbox_id)}, updated_at = now()
        WHERE project_id = {_sql_str(project_id)} AND deleted_at IS NULL;
        """.strip()
    )


def list_projects(client: HasuraClient, *, owner: ProjectOwner) -> list[Project]:
    ensure_projects_schema(client)
    res = client.run_sql(
        f"""
        SELECT p.project_id, p.owner_sub, p.owner_email, p.name, p.slug, p.sandbox_id, p.template_id,
               p.gitlab_project_id, p.gitlab_path, p.gitlab_web_url,
               p.created_at, p.updated_at
        FROM amicable_meta.projects p
        JOIN amicable_meta.project_members pm ON pm.project_id = p.project_id
        WHERE (pm.user_sub = {_sql_str(owner.sub)} OR pm.user_email = {_sql_str(owner.email.lower())})
          AND p.deleted_at IS NULL
        ORDER BY p.updated_at DESC;
        """.strip(),
        read_only=True,
    )
    out: list[Project] = []
    for r in _tuples_to_dicts(res):
        out.append(
            Project(
                project_id=str(r["project_id"]),
                owner_sub=str(r["owner_sub"]),
                owner_email=str(r["owner_email"]),
                name=str(r["name"]),
                slug=str(r["slug"]),
                sandbox_id=str(r.get("sandbox_id"))
                if r.get("sandbox_id") is not None
                else None,
                template_id=str(r.get("template_id"))
                if r.get("template_id") is not None
                else None,
                gitlab_project_id=int(r["gitlab_project_id"])
                if r.get("gitlab_project_id") is not None
                else None,
                gitlab_path=str(r.get("gitlab_path"))
                if r.get("gitlab_path") is not None
                else None,
                gitlab_web_url=str(r.get("gitlab_web_url"))
                if r.get("gitlab_web_url") is not None
                else None,
                created_at=str(r.get("created_at"))
                if r.get("created_at") is not None
                else None,
                updated_at=str(r.get("updated_at"))
                if r.get("updated_at") is not None
                else None,
            )
        )
    return out


def set_project_slug(
    client: HasuraClient,
    *,
    owner: ProjectOwner,
    project_id: str,
    new_slug: str,
) -> Project:
    ensure_projects_schema(client)
    client.run_sql(
        f"""
        UPDATE amicable_meta.projects
        SET slug = {_sql_str(new_slug)}, updated_at = now()
        WHERE project_id = {_sql_str(project_id)} AND owner_sub = {_sql_str(owner.sub)} AND deleted_at IS NULL;
        """.strip()
    )
    p = get_project_by_id(client, owner=owner, project_id=project_id)
    if not p:
        raise PermissionError("project not found")
    return p


def set_gitlab_metadata(
    client: HasuraClient,
    *,
    owner: ProjectOwner,
    project_id: str,
    gitlab_project_id: int | None,
    gitlab_path: str | None,
    gitlab_web_url: str | None,
) -> Project:
    ensure_projects_schema(client)
    client.run_sql(
        f"""
        UPDATE amicable_meta.projects
        SET gitlab_project_id = {str(int(gitlab_project_id)) if gitlab_project_id is not None else "NULL"},
            gitlab_path = {_sql_str(gitlab_path) if gitlab_path is not None else "NULL"},
            gitlab_web_url = {_sql_str(gitlab_web_url) if gitlab_web_url is not None else "NULL"},
            updated_at = now()
        WHERE project_id = {_sql_str(project_id)} AND owner_sub = {_sql_str(owner.sub)} AND deleted_at IS NULL;
        """.strip()
    )
    p = get_project_by_id(client, owner=owner, project_id=project_id)
    if not p:
        raise PermissionError("project not found")
    return p


def _candidate_slug(base: str, *, suffix: str | None = None) -> str:
    if not suffix:
        return base
    # Keep slugs under 63 chars for sanity (k8s-like), while remaining readable.
    base_max = max(1, 63 - (1 + len(suffix)))
    return f"{base[:base_max].rstrip('-')}-{suffix}"


def _slug_available(client: HasuraClient, *, slug: str) -> bool:
    res = client.run_sql(
        f"""
        SELECT 1
        FROM amicable_meta.projects
        WHERE slug = {_sql_str(slug)} AND deleted_at IS NULL
        LIMIT 1;
        """.strip(),
        read_only=True,
    )
    rows = _tuples_to_dicts(res)
    return not bool(rows)


def create_project(
    client: HasuraClient,
    *,
    owner: ProjectOwner,
    name: str,
    template_id: str | None = None,
) -> Project:
    ensure_projects_schema(client)
    project_id = str(uuid.uuid4())
    base = slugify(name)

    for attempt in range(20):
        suffix = (
            None if attempt == 0 else project_id.replace("-", "")[: (4 + attempt // 3)]
        )
        slug = _candidate_slug(base, suffix=suffix)
        if not _slug_available(client, slug=slug):
            continue

        client.run_sql(
            f"""
            INSERT INTO amicable_meta.projects (project_id, owner_sub, owner_email, name, slug, template_id)
            VALUES ({_sql_str(project_id)}, {_sql_str(owner.sub)}, {_sql_str(owner.email)}, {_sql_str(name)}, {_sql_str(slug)}, {_sql_str(template_id) if template_id is not None else "NULL"})
            ON CONFLICT DO NOTHING;
            """.strip()
        )
        p = _get_project_by_id_any_owner(client, project_id=project_id)
        if p and p.owner_sub == owner.sub:
            # Add creator as first member
            add_project_member(
                client,
                project_id=project_id,
                user_sub=owner.sub,
                user_email=owner.email,
                added_by_sub=None,
            )
            return p

    raise RuntimeError("failed to allocate unique project slug")


def ensure_project_for_id(
    client: HasuraClient, *, owner: ProjectOwner, project_id: str
) -> Project:
    """Ensure a project exists for a specific project_id (used for WS init back-compat)."""
    ensure_projects_schema(client)
    existing = _get_project_by_id_any_owner(client, project_id=project_id)
    if existing:
        if existing.owner_sub != owner.sub:
            raise PermissionError("project belongs to a different user")
        return existing

    # If a project row exists but was soft-deleted, resurrect it instead of failing
    # with a misleading "failed to auto-create project" error.
    row = _project_row_by_id_including_deleted(client, project_id=project_id)
    if (
        row
        and str(row.get("owner_sub") or "") == owner.sub
        and row.get("deleted_at") is not None
    ):
        client.run_sql(
            f"""
            UPDATE amicable_meta.projects
            SET deleted_at = NULL, updated_at = now()
            WHERE project_id = {_sql_str(project_id)} AND owner_sub = {_sql_str(owner.sub)};
            """.strip()
        )
        revived = _get_project_by_id_any_owner(client, project_id=project_id)
        if revived:
            return revived

    short = project_id.replace("-", "")[:8]
    name = f"Untitled {short}"
    base = f"project-{short}"

    # base should already be unique, but loop defensively.
    for attempt in range(10):
        suffix = None if attempt == 0 else short[: (4 + attempt)]
        slug = _candidate_slug(base, suffix=suffix)
        if not _slug_available(client, slug=slug):
            continue
        client.run_sql(
            f"""
            INSERT INTO amicable_meta.projects (project_id, owner_sub, owner_email, name, slug, template_id)
            VALUES ({_sql_str(project_id)}, {_sql_str(owner.sub)}, {_sql_str(owner.email)}, {_sql_str(name)}, {_sql_str(slug)}, NULL)
            ON CONFLICT DO NOTHING;
            """.strip()
        )
        created = _get_project_by_id_any_owner(client, project_id=project_id)
        if created and created.owner_sub == owner.sub:
            return created

    raise RuntimeError("failed to auto-create project")


def rename_project(
    client: HasuraClient, *, owner: ProjectOwner, project_id: str, new_name: str
) -> Project:
    ensure_projects_schema(client)
    base = slugify(new_name)

    # Ensure project exists and is owned.
    existing = get_project_by_id(client, owner=owner, project_id=project_id)
    if not existing:
        raise PermissionError("project not found")

    for attempt in range(20):
        suffix = (
            None if attempt == 0 else project_id.replace("-", "")[: (4 + attempt // 3)]
        )
        slug = _candidate_slug(base, suffix=suffix)
        if slug != existing.slug and not _slug_available(client, slug=slug):
            continue
        client.run_sql(
            f"""
            UPDATE amicable_meta.projects
            SET name = {_sql_str(new_name)}, slug = {_sql_str(slug)}, updated_at = now()
            WHERE project_id = {_sql_str(project_id)} AND owner_sub = {_sql_str(owner.sub)} AND deleted_at IS NULL;
            """.strip()
        )
        updated = get_project_by_id(client, owner=owner, project_id=project_id)
        if updated:
            return updated

    raise RuntimeError("failed to allocate unique project slug for rename")


def mark_project_deleted(
    client: HasuraClient, *, owner: ProjectOwner, project_id: str
) -> None:
    ensure_projects_schema(client)
    # Mark deleted first so it disappears from lists immediately.
    client.run_sql(
        f"""
        UPDATE amicable_meta.projects
        SET deleted_at = now(), updated_at = now()
        WHERE project_id = {_sql_str(project_id)} AND owner_sub = {_sql_str(owner.sub)} AND deleted_at IS NULL;
        """.strip()
    )


def hard_delete_project_row(
    client: HasuraClient, *, owner: ProjectOwner, project_id: str
) -> None:
    ensure_projects_schema(client)
    client.run_sql(
        f"""
        DELETE FROM amicable_meta.projects
        WHERE project_id = {_sql_str(project_id)} AND owner_sub = {_sql_str(owner.sub)};
        """.strip()
    )


# ---------------------------------------------------------------------------
# Project Members
# ---------------------------------------------------------------------------


def _get_member_by_email(
    client: HasuraClient, *, project_id: str, user_email: str
) -> ProjectMember | None:
    res = client.run_sql(
        f"""
        SELECT project_id, user_sub, user_email, added_at, added_by_sub
        FROM amicable_meta.project_members
        WHERE project_id = {_sql_str(project_id)} AND user_email = {_sql_str(user_email.lower())}
        LIMIT 1;
        """.strip(),
        read_only=True,
    )
    rows = _tuples_to_dicts(res)
    if not rows:
        return None
    r = rows[0]
    return ProjectMember(
        project_id=str(r["project_id"]),
        user_sub=str(r["user_sub"]) if r.get("user_sub") else None,
        user_email=str(r["user_email"]),
        added_at=str(r.get("added_at")) if r.get("added_at") else None,
        added_by_sub=str(r.get("added_by_sub")) if r.get("added_by_sub") else None,
    )


def add_project_member(
    client: HasuraClient,
    *,
    project_id: str,
    user_email: str,
    user_sub: str | None = None,
    added_by_sub: str | None = None,
) -> ProjectMember:
    """Add a member to a project. If user_sub is None, they'll be matched on first login."""
    ensure_projects_schema(client)
    user_email = user_email.strip().lower()

    # Check if already a member by email
    existing = _get_member_by_email(client, project_id=project_id, user_email=user_email)
    if existing:
        return existing

    sub_sql = _sql_str(user_sub) if user_sub else "NULL"
    added_by_sql = _sql_str(added_by_sub) if added_by_sub else "NULL"

    client.run_sql(
        f"""
        INSERT INTO amicable_meta.project_members (project_id, user_sub, user_email, added_by_sub)
        VALUES ({_sql_str(project_id)}, {sub_sql}, {_sql_str(user_email)}, {added_by_sql})
        ON CONFLICT (project_id, user_sub) DO NOTHING;
        """.strip()
    )
    return ProjectMember(
        project_id=project_id,
        user_sub=user_sub,
        user_email=user_email,
        added_by_sub=added_by_sub,
    )


def list_project_members(client: HasuraClient, *, project_id: str) -> list[ProjectMember]:
    """List all members of a project."""
    ensure_projects_schema(client)
    res = client.run_sql(
        f"""
        SELECT project_id, user_sub, user_email, added_at, added_by_sub
        FROM amicable_meta.project_members
        WHERE project_id = {_sql_str(project_id)}
        ORDER BY added_at ASC;
        """.strip(),
        read_only=True,
    )
    out: list[ProjectMember] = []
    for r in _tuples_to_dicts(res):
        out.append(
            ProjectMember(
                project_id=str(r["project_id"]),
                user_sub=str(r["user_sub"]) if r.get("user_sub") else None,
                user_email=str(r["user_email"]),
                added_at=str(r.get("added_at")) if r.get("added_at") else None,
                added_by_sub=str(r.get("added_by_sub")) if r.get("added_by_sub") else None,
            )
        )
    return out


def remove_project_member(
    client: HasuraClient, *, project_id: str, user_sub: str
) -> bool:
    """Remove a member from a project. Returns False if they were the last member."""
    ensure_projects_schema(client)
    members = list_project_members(client, project_id=project_id)
    if len(members) <= 1:
        return False
    client.run_sql(
        f"""
        DELETE FROM amicable_meta.project_members
        WHERE project_id = {_sql_str(project_id)} AND user_sub = {_sql_str(user_sub)};
        """.strip()
    )
    return True


def is_project_member(
    client: HasuraClient, *, project_id: str, user_sub: str, user_email: str
) -> bool:
    """Check if a user is a member of a project (by sub or email)."""
    ensure_projects_schema(client)
    res = client.run_sql(
        f"""
        SELECT 1 FROM amicable_meta.project_members
        WHERE project_id = {_sql_str(project_id)}
          AND (user_sub = {_sql_str(user_sub)} OR user_email = {_sql_str(user_email.lower())})
        LIMIT 1;
        """.strip(),
        read_only=True,
    )
    rows = _tuples_to_dicts(res)
    return bool(rows)


# ---------------------------------------------------------------------------
# Session Locking
# ---------------------------------------------------------------------------


def get_project_lock(client: HasuraClient, *, project_id: str) -> ProjectLock | None:
    """Get current lock info for a project."""
    ensure_projects_schema(client)
    res = client.run_sql(
        f"""
        SELECT locked_by_sub, locked_at
        FROM amicable_meta.projects
        WHERE project_id = {_sql_str(project_id)} AND deleted_at IS NULL AND locked_by_sub IS NOT NULL
        LIMIT 1;
        """.strip(),
        read_only=True,
    )
    rows = _tuples_to_dicts(res)
    if not rows or not rows[0].get("locked_by_sub"):
        return None
    r = rows[0]
    # Get email from members table
    email_res = client.run_sql(
        f"""
        SELECT user_email FROM amicable_meta.project_members
        WHERE project_id = {_sql_str(project_id)} AND user_sub = {_sql_str(str(r["locked_by_sub"]))}
        LIMIT 1;
        """.strip(),
        read_only=True,
    )
    email_rows = _tuples_to_dicts(email_res)
    email = str(email_rows[0]["user_email"]) if email_rows else ""
    return ProjectLock(
        project_id=project_id,
        locked_by_sub=str(r["locked_by_sub"]),
        locked_by_email=email,
        locked_at=str(r.get("locked_at") or ""),
    )


def acquire_project_lock(
    client: HasuraClient,
    *,
    project_id: str,
    user_sub: str,
    user_email: str,
    force: bool = False,
) -> ProjectLock | None:
    """Try to acquire lock. Returns None if locked by someone else (unless force=True)."""
    ensure_projects_schema(client)
    current = get_project_lock(client, project_id=project_id)
    if current and current.locked_by_sub != user_sub and not force:
        return None

    client.run_sql(
        f"""
        UPDATE amicable_meta.projects
        SET locked_by_sub = {_sql_str(user_sub)}, locked_at = now(), updated_at = now()
        WHERE project_id = {_sql_str(project_id)} AND deleted_at IS NULL;
        """.strip()
    )
    return ProjectLock(
        project_id=project_id,
        locked_by_sub=user_sub,
        locked_by_email=user_email,
        locked_at="now",
    )


def release_project_lock(
    client: HasuraClient, *, project_id: str, user_sub: str
) -> None:
    """Release lock if held by user_sub."""
    ensure_projects_schema(client)
    client.run_sql(
        f"""
        UPDATE amicable_meta.projects
        SET locked_by_sub = NULL, locked_at = NULL, updated_at = now()
        WHERE project_id = {_sql_str(project_id)} AND locked_by_sub = {_sql_str(user_sub)} AND deleted_at IS NULL;
        """.strip()
    )
