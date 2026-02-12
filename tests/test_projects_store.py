from __future__ import annotations

import re

import pytest

from src.projects.store import (
    ProjectOwner,
    create_project,
    ensure_project_for_id,
    get_project_by_id,
    get_project_by_slug,
    hard_delete_project_row,
    list_projects,
    mark_project_deleted,
    rename_project,
    slugify,
)


class FakeHasuraClient:
    def __init__(self) -> None:
        self.projects: dict[str, dict] = {}
        self.members: dict[tuple[str, str], dict] = {}  # (project_id, user_key) -> member
        self.schema_created_tables: dict[str, bool] = {}

        class _Cfg:
            source_name = "default"

        self.cfg = _Cfg()

    def run_sql(self, sql: str, *, read_only: bool = False):
        _ = read_only
        sql = sql.strip()
        sql_l = sql.lower()

        # Schema creation: track tables and ignore.
        # Handle multi-statement SQL for schema migration
        if "create schema" in sql_l or "create table" in sql_l or "alter table" in sql_l or "create index" in sql_l:
            if "create table" in sql_l and "project_members" in sql_l:
                self.schema_created_tables["project_members"] = True
            if "create table" in sql_l and "amicable_meta.projects" in sql_l:
                self.schema_created_tables["projects"] = True
            return {"result_type": "CommandOk", "result": []}

        # SELECT by project_id.
        m = re.search(r"where project_id\s*=\s*'([^']+)'", sql, flags=re.I)
        if m and sql_l.startswith("select") and "from amicable_meta.projects" in sql_l:
            pid = m.group(1)
            row = self.projects.get(pid)
            if not row or row.get("deleted_at"):
                return {
                    "result_type": "TuplesOk",
                    "result": [
                        ["project_id"],
                    ],
                }
            header = [
                "project_id",
                "owner_sub",
                "owner_email",
                "name",
                "slug",
                "template_id",
                "created_at",
                "updated_at",
            ]
            data = [
                row["project_id"],
                row["owner_sub"],
                row["owner_email"],
                row["name"],
                row["slug"],
                row.get("template_id"),
                row.get("created_at"),
                row.get("updated_at"),
            ]
            return {"result_type": "TuplesOk", "result": [header, data]}

        # SELECT by slug.
        m = re.search(r"where slug\s*=\s*'([^']+)'", sql, flags=re.I)
        if m and "from amicable_meta.projects" in sql_l:
            slug = m.group(1)
            row = next(
                (
                    r
                    for r in self.projects.values()
                    if r.get("slug") == slug and not r.get("deleted_at")
                ),
                None,
            )
            if not row:
                return {
                    "result_type": "TuplesOk",
                    "result": [
                        ["project_id"],
                    ],
                }
            if sql_l.startswith("select 1"):
                return {"result_type": "TuplesOk", "result": [["1"], [1]]}
            header = [
                "project_id",
                "owner_sub",
                "owner_email",
                "name",
                "slug",
                "template_id",
                "created_at",
                "updated_at",
            ]
            data = [
                row["project_id"],
                row["owner_sub"],
                row["owner_email"],
                row["name"],
                row["slug"],
                row.get("template_id"),
                row.get("created_at"),
                row.get("updated_at"),
            ]
            return {"result_type": "TuplesOk", "result": [header, data]}

        # List projects with JOIN on members (new membership-based query)
        if "join amicable_meta.project_members" in sql_l and "order by" in sql_l:
            sub_match = re.search(r"pm\.user_sub\s*=\s*'([^']+)'", sql, flags=re.I)
            email_match = re.search(r"pm\.user_email\s*=\s*'([^']+)'", sql, flags=re.I)
            sub = sub_match.group(1) if sub_match else None
            email = email_match.group(1).lower() if email_match else None

            # Find projects where user is a member
            member_project_ids = set()
            for m in self.members.values():
                if m.get("user_sub") == sub or m.get("user_email") == email:
                    member_project_ids.add(m["project_id"])

            rows = [
                p
                for p in self.projects.values()
                if p["project_id"] in member_project_ids and not p.get("deleted_at")
            ]

            header = [
                "project_id",
                "owner_sub",
                "owner_email",
                "name",
                "slug",
                "sandbox_id",
                "template_id",
                "gitlab_project_id",
                "gitlab_path",
                "gitlab_web_url",
                "created_at",
                "updated_at",
            ]
            out = [header]
            for r in rows:
                out.append(
                    [
                        r["project_id"],
                        r["owner_sub"],
                        r["owner_email"],
                        r["name"],
                        r["slug"],
                        r.get("sandbox_id"),
                        r.get("template_id"),
                        r.get("gitlab_project_id"),
                        r.get("gitlab_path"),
                        r.get("gitlab_web_url"),
                        r.get("created_at"),
                        r.get("updated_at"),
                    ]
                )
            return {"result_type": "TuplesOk", "result": out}

        # List by owner_sub (legacy - but still needed for backward compatibility in tests).
        m = re.search(r"where owner_sub\s*=\s*'([^']+)'", sql, flags=re.I)
        if m and "order by updated_at" in sql_l:
            sub = m.group(1)
            rows = [
                r
                for r in self.projects.values()
                if r.get("owner_sub") == sub and not r.get("deleted_at")
            ]
            header = [
                "project_id",
                "owner_sub",
                "owner_email",
                "name",
                "slug",
                "template_id",
                "created_at",
                "updated_at",
            ]
            out = [header]
            for r in rows:
                out.append(
                    [
                        r["project_id"],
                        r["owner_sub"],
                        r["owner_email"],
                        r["name"],
                        r["slug"],
                        r.get("template_id"),
                        r.get("created_at"),
                        r.get("updated_at"),
                    ]
                )
            return {"result_type": "TuplesOk", "result": out}

        # INSERT project.
        if sql_l.startswith("insert into amicable_meta.projects"):
            vals = re.search(r"values\s*\((.*)\)\s*on conflict", sql, flags=re.I | re.S)
            assert vals
            parts = [p.strip() for p in vals.group(1).split(",")]
            pid = parts[0].strip("'")
            owner_sub = parts[1].strip("'")
            owner_email = parts[2].strip("'")
            name = parts[3].strip("'")
            slug = parts[4].strip("'")
            template_id = (
                parts[5].strip("'") if len(parts) > 5 and parts[5] != "NULL" else None
            )
            # Enforce uniqueness on slug unless deleted.
            if any(
                (r.get("slug") == slug and not r.get("deleted_at"))
                for r in self.projects.values()
            ):
                return {"result_type": "CommandOk", "result": []}
            if pid in self.projects:
                return {"result_type": "CommandOk", "result": []}
            self.projects[pid] = {
                "project_id": pid,
                "owner_sub": owner_sub,
                "owner_email": owner_email,
                "name": name,
                "slug": slug,
                "template_id": template_id,
                "created_at": "t0",
                "updated_at": "t0",
                "deleted_at": None,
            }
            return {"result_type": "CommandOk", "result": []}

        # UPDATE rename.
        if sql_l.startswith("update amicable_meta.projects") and "set name" in sql_l:
            pid = re.search(r"where project_id\s*=\s*'([^']+)'", sql, flags=re.I).group(
                1
            )  # type: ignore[union-attr]
            sub = re.search(r"and owner_sub\s*=\s*'([^']+)'", sql, flags=re.I).group(1)  # type: ignore[union-attr]
            name = re.search(r"set name\s*=\s*'([^']*)'", sql, flags=re.I).group(1)  # type: ignore[union-attr]
            slug = re.search(r"slug\s*=\s*'([^']*)'", sql, flags=re.I).group(1)  # type: ignore[union-attr]
            row = self.projects.get(pid)
            if row and row["owner_sub"] == sub and not row.get("deleted_at"):
                # enforce slug uniqueness
                if any(
                    (
                        r.get("slug") == slug
                        and r.get("project_id") != pid
                        and not r.get("deleted_at")
                    )
                    for r in self.projects.values()
                ):
                    return {"result_type": "CommandOk", "result": []}
                row["name"] = name
                row["slug"] = slug
                row["updated_at"] = "t1"
            return {"result_type": "CommandOk", "result": []}

        # UPDATE mark deleted.
        if (
            sql_l.startswith("update amicable_meta.projects")
            and "set deleted_at" in sql_l
        ):
            pid = re.search(r"where project_id\s*=\s*'([^']+)'", sql, flags=re.I).group(
                1
            )  # type: ignore[union-attr]
            sub = re.search(r"and owner_sub\s*=\s*'([^']+)'", sql, flags=re.I).group(1)  # type: ignore[union-attr]
            row = self.projects.get(pid)
            if row and row["owner_sub"] == sub and not row.get("deleted_at"):
                row["deleted_at"] = "t_del"
                row["updated_at"] = "t_del"
            return {"result_type": "CommandOk", "result": []}

        # DELETE project.
        if sql_l.startswith("delete from amicable_meta.projects"):
            pid = re.search(r"where project_id\s*=\s*'([^']+)'", sql, flags=re.I).group(
                1
            )  # type: ignore[union-attr]
            sub = re.search(r"and owner_sub\s*=\s*'([^']+)'", sql, flags=re.I).group(1)  # type: ignore[union-attr]
            row = self.projects.get(pid)
            if row and row["owner_sub"] == sub:
                self.projects.pop(pid, None)
            return {"result_type": "CommandOk", "result": []}

        # ---------------------------------------------------------------
        # Project Members
        # ---------------------------------------------------------------

        # INSERT member
        if sql_l.startswith("insert into amicable_meta.project_members"):
            vals = re.search(r"values\s*\((.*)\)\s*on conflict", sql, flags=re.I | re.S)
            if vals:
                parts = [p.strip() for p in vals.group(1).split(",")]
                pid = parts[0].strip("'")
                user_sub = parts[1].strip("'") if parts[1].strip() != "NULL" else None
                user_email = parts[2].strip("'").lower()
                added_by = (
                    parts[3].strip("'")
                    if len(parts) > 3 and parts[3].strip() != "NULL"
                    else None
                )
                # Use user_sub as key if available, else email
                key = (pid, user_sub or user_email)
                if key not in self.members:
                    self.members[key] = {
                        "project_id": pid,
                        "user_sub": user_sub,
                        "user_email": user_email,
                        "added_at": "t0",
                        "added_by_sub": added_by,
                    }
            return {"result_type": "CommandOk", "result": []}

        # SELECT members by project_id
        if "from amicable_meta.project_members" in sql_l and sql_l.startswith("select"):
            pid_match = re.search(r"where project_id\s*=\s*'([^']+)'", sql, flags=re.I)
            if pid_match:
                pid = pid_match.group(1)

                # Check for is_project_member query (SELECT 1 with user_sub/email OR)
                if sql_l.startswith("select 1") and "(user_sub" in sql_l:
                    # Parse the user_sub and user_email from the OR clause
                    sub_match = re.search(r"user_sub\s*=\s*'([^']+)'", sql, flags=re.I)
                    email_or_match = re.search(
                        r"or user_email\s*=\s*'([^']+)'", sql, flags=re.I
                    )
                    user_sub = sub_match.group(1) if sub_match else None
                    user_email = email_or_match.group(1).lower() if email_or_match else None

                    # Check if user is a member (by sub or email)
                    is_member = any(
                        m["project_id"] == pid
                        and (m.get("user_sub") == user_sub or m.get("user_email") == user_email)
                        for m in self.members.values()
                    )
                    if is_member:
                        return {"result_type": "TuplesOk", "result": [["1"], [1]]}
                    return {"result_type": "TuplesOk", "result": [["1"]]}

                # Check for email filter (for _get_member_by_email)
                email_match = re.search(
                    r"and user_email\s*=\s*'([^']+)'", sql, flags=re.I
                )
                if email_match:
                    email = email_match.group(1).lower()
                    rows = [
                        m
                        for m in self.members.values()
                        if m["project_id"] == pid and m["user_email"] == email
                    ]
                else:
                    rows = [m for m in self.members.values() if m["project_id"] == pid]

                # SELECT 1 without complex filter (simple membership check)
                if sql_l.startswith("select 1"):
                    if rows:
                        return {"result_type": "TuplesOk", "result": [["1"], [1]]}
                    return {"result_type": "TuplesOk", "result": [["1"]]}

                header = [
                    "project_id",
                    "user_sub",
                    "user_email",
                    "added_at",
                    "added_by_sub",
                ]
                out = [header]
                for m in rows:
                    out.append(
                        [
                            m["project_id"],
                            m["user_sub"],
                            m["user_email"],
                            m["added_at"],
                            m["added_by_sub"],
                        ]
                    )
                return {"result_type": "TuplesOk", "result": out}

        # DELETE member
        if sql_l.startswith("delete from amicable_meta.project_members"):
            pid_match = re.search(r"where project_id\s*=\s*'([^']+)'", sql, flags=re.I)
            sub_match = re.search(r"and user_sub\s*=\s*'([^']+)'", sql, flags=re.I)
            if pid_match and sub_match:
                key = (pid_match.group(1), sub_match.group(1))
                self.members.pop(key, None)
            return {"result_type": "CommandOk", "result": []}

        raise AssertionError(f"Unhandled SQL in test fake: {sql}")

    def metadata(self, payload: dict):
        _ = payload
        raise AssertionError("metadata() not expected in these tests")


def test_slugify() -> None:
    assert slugify("My Cool Project!") == "my-cool-project"
    assert slugify("   ") == "project"
    assert slugify("Hello___World") == "hello-world"


def test_create_list_get_rename_delete() -> None:
    c = FakeHasuraClient()
    owner = ProjectOwner(sub="u1", email="u1@example.com")

    p1 = create_project(c, owner=owner, name="Todo App", template_id="vite")
    p2 = create_project(c, owner=owner, name="Todo App")
    assert p1.slug != p2.slug
    assert p1.template_id == "vite"
    assert p2.template_id is None

    got = get_project_by_slug(c, owner=owner, slug=p1.slug)
    assert got and got.project_id == p1.project_id

    lst = list_projects(c, owner=owner)
    assert {p.project_id for p in lst} == {p1.project_id, p2.project_id}

    renamed = rename_project(
        c, owner=owner, project_id=p1.project_id, new_name="New Name"
    )
    assert renamed.name == "New Name"
    assert renamed.slug.startswith("new-name")

    mark_project_deleted(c, owner=owner, project_id=p2.project_id)
    assert get_project_by_id(c, owner=owner, project_id=p2.project_id) is None

    hard_delete_project_row(c, owner=owner, project_id=p2.project_id)
    assert p2.project_id not in c.projects


def test_ensure_project_for_id_owner_mismatch() -> None:
    c = FakeHasuraClient()
    owner1 = ProjectOwner(sub="u1", email="u1@example.com")
    owner2 = ProjectOwner(sub="u2", email="u2@example.com")

    p = ensure_project_for_id(c, owner=owner1, project_id="abc-123")
    assert p.project_id == "abc-123"

    with pytest.raises(PermissionError):
        ensure_project_for_id(c, owner=owner2, project_id="abc-123")


def test_project_members_table_created() -> None:
    """Verify project_members table is created during schema migration."""
    from src.projects import store

    # Reset schema state for this test
    store._schema_ready = False

    c = FakeHasuraClient()
    from src.projects.store import ensure_projects_schema

    ensure_projects_schema(c)
    # The fake client should have received CREATE TABLE for project_members
    assert c.schema_created_tables.get("project_members") is True


def test_add_and_list_project_members() -> None:
    """Test adding and listing project members."""
    c = FakeHasuraClient()
    owner = ProjectOwner(sub="u1", email="u1@example.com")
    p = create_project(c, owner=owner, name="Shared Project")

    from src.projects.store import add_project_member, list_project_members

    # Creator should already be a member
    members = list_project_members(c, project_id=p.project_id)
    assert len(members) == 1
    assert members[0].user_sub == "u1"

    # Add another member
    add_project_member(
        c, project_id=p.project_id, user_email="u2@example.com", added_by_sub="u1"
    )
    members = list_project_members(c, project_id=p.project_id)
    assert len(members) == 2
    emails = {m.user_email for m in members}
    assert emails == {"u1@example.com", "u2@example.com"}


def test_shared_project_access() -> None:
    """Users can access projects they're members of, even if not the creator."""
    c = FakeHasuraClient()
    owner = ProjectOwner(sub="u1", email="u1@example.com")
    other = ProjectOwner(sub="u2", email="u2@example.com")

    p = create_project(c, owner=owner, name="Shared Project")

    # Other user cannot access yet
    assert get_project_by_id(c, owner=other, project_id=p.project_id) is None

    # Add other as member
    from src.projects.store import add_project_member

    add_project_member(
        c,
        project_id=p.project_id,
        user_sub="u2",
        user_email="u2@example.com",
        added_by_sub="u1",
    )

    # Now other can access
    got = get_project_by_id(c, owner=other, project_id=p.project_id)
    assert got is not None
    assert got.project_id == p.project_id

    # And it appears in their list
    lst = list_projects(c, owner=other)
    assert any(proj.project_id == p.project_id for proj in lst)
