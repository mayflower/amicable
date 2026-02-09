from __future__ import annotations

import re
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


def ensure_projects_schema(client: HasuraClient) -> None:
    client.run_sql(
        """
        CREATE SCHEMA IF NOT EXISTS amicable_meta;
        CREATE TABLE IF NOT EXISTS amicable_meta.projects (
          project_id text PRIMARY KEY,
          owner_sub text NOT NULL,
          owner_email text NOT NULL,
          name text NOT NULL,
          slug text NOT NULL UNIQUE,
          template_id text NULL,
          gitlab_project_id bigint NULL,
          gitlab_path text NULL,
          gitlab_web_url text NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          deleted_at timestamptz NULL
        );
        ALTER TABLE amicable_meta.projects
          ADD COLUMN IF NOT EXISTS template_id text NULL;
        ALTER TABLE amicable_meta.projects
          ADD COLUMN IF NOT EXISTS gitlab_project_id bigint NULL;
        ALTER TABLE amicable_meta.projects
          ADD COLUMN IF NOT EXISTS gitlab_path text NULL;
        ALTER TABLE amicable_meta.projects
          ADD COLUMN IF NOT EXISTS gitlab_web_url text NULL;
        """.strip()
    )


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
    template_id: str | None = None
    gitlab_project_id: int | None = None
    gitlab_path: str | None = None
    gitlab_web_url: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


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


def _get_project_by_id_any_owner(client: HasuraClient, *, project_id: str) -> Project | None:
    ensure_projects_schema(client)
    res = client.run_sql(
        f"""
        SELECT project_id, owner_sub, owner_email, name, slug, template_id,
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
        template_id=str(r.get("template_id")) if r.get("template_id") is not None else None,
        gitlab_project_id=int(r["gitlab_project_id"]) if r.get("gitlab_project_id") is not None else None,
        gitlab_path=str(r.get("gitlab_path")) if r.get("gitlab_path") is not None else None,
        gitlab_web_url=str(r.get("gitlab_web_url")) if r.get("gitlab_web_url") is not None else None,
        created_at=str(r.get("created_at")) if r.get("created_at") is not None else None,
        updated_at=str(r.get("updated_at")) if r.get("updated_at") is not None else None,
    )


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


def get_project_by_id(client: HasuraClient, *, owner: ProjectOwner, project_id: str) -> Project | None:
    p = _get_project_by_id_any_owner(client, project_id=project_id)
    if not p:
        return None
    if p.owner_sub != owner.sub:
        return None
    return p


def get_project_by_slug(client: HasuraClient, *, owner: ProjectOwner, slug: str) -> Project | None:
    ensure_projects_schema(client)
    res = client.run_sql(
        f"""
        SELECT project_id, owner_sub, owner_email, name, slug, template_id,
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
    if str(r.get("owner_sub")) != owner.sub:
        return None
    return Project(
        project_id=str(r["project_id"]),
        owner_sub=str(r["owner_sub"]),
        owner_email=str(r["owner_email"]),
        name=str(r["name"]),
        slug=str(r["slug"]),
        template_id=str(r.get("template_id")) if r.get("template_id") is not None else None,
        gitlab_project_id=int(r["gitlab_project_id"]) if r.get("gitlab_project_id") is not None else None,
        gitlab_path=str(r.get("gitlab_path")) if r.get("gitlab_path") is not None else None,
        gitlab_web_url=str(r.get("gitlab_web_url")) if r.get("gitlab_web_url") is not None else None,
        created_at=str(r.get("created_at")) if r.get("created_at") is not None else None,
        updated_at=str(r.get("updated_at")) if r.get("updated_at") is not None else None,
    )


def list_projects(client: HasuraClient, *, owner: ProjectOwner) -> list[Project]:
    ensure_projects_schema(client)
    res = client.run_sql(
        f"""
        SELECT project_id, owner_sub, owner_email, name, slug, template_id,
               gitlab_project_id, gitlab_path, gitlab_web_url,
               created_at, updated_at
        FROM amicable_meta.projects
        WHERE owner_sub = {_sql_str(owner.sub)} AND deleted_at IS NULL
        ORDER BY updated_at DESC;
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
                template_id=str(r.get("template_id")) if r.get("template_id") is not None else None,
                gitlab_project_id=int(r["gitlab_project_id"]) if r.get("gitlab_project_id") is not None else None,
                gitlab_path=str(r.get("gitlab_path")) if r.get("gitlab_path") is not None else None,
                gitlab_web_url=str(r.get("gitlab_web_url")) if r.get("gitlab_web_url") is not None else None,
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
        SET gitlab_project_id = {str(int(gitlab_project_id)) if gitlab_project_id is not None else 'NULL'},
            gitlab_path = {_sql_str(gitlab_path) if gitlab_path is not None else 'NULL'},
            gitlab_web_url = {_sql_str(gitlab_web_url) if gitlab_web_url is not None else 'NULL'},
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
        suffix = None if attempt == 0 else project_id.replace("-", "")[: (4 + attempt // 3)]
        slug = _candidate_slug(base, suffix=suffix)
        if not _slug_available(client, slug=slug):
            continue

        client.run_sql(
            f"""
            INSERT INTO amicable_meta.projects (project_id, owner_sub, owner_email, name, slug, template_id)
            VALUES ({_sql_str(project_id)}, {_sql_str(owner.sub)}, {_sql_str(owner.email)}, {_sql_str(name)}, {_sql_str(slug)}, {_sql_str(template_id) if template_id is not None else 'NULL'})
            ON CONFLICT DO NOTHING;
            """.strip()
        )
        p = _get_project_by_id_any_owner(client, project_id=project_id)
        if p and p.owner_sub == owner.sub:
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
        suffix = None if attempt == 0 else project_id.replace("-", "")[: (4 + attempt // 3)]
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


def mark_project_deleted(client: HasuraClient, *, owner: ProjectOwner, project_id: str) -> None:
    ensure_projects_schema(client)
    # Mark deleted first so it disappears from lists immediately.
    client.run_sql(
        f"""
        UPDATE amicable_meta.projects
        SET deleted_at = now(), updated_at = now()
        WHERE project_id = {_sql_str(project_id)} AND owner_sub = {_sql_str(owner.sub)} AND deleted_at IS NULL;
        """.strip()
    )


def hard_delete_project_row(client: HasuraClient, *, owner: ProjectOwner, project_id: str) -> None:
    ensure_projects_schema(client)
    client.run_sql(
        f"""
        DELETE FROM amicable_meta.projects
        WHERE project_id = {_sql_str(project_id)} AND owner_sub = {_sql_str(owner.sub)};
        """.strip()
    )
