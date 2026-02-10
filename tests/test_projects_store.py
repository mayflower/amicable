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

        class _Cfg:
            source_name = "default"

        self.cfg = _Cfg()

    def run_sql(self, sql: str, *, read_only: bool = False):
        _ = read_only
        sql = sql.strip()
        sql_l = sql.lower()

        # Schema creation: ignore.
        if sql.lower().startswith("create schema") or sql.lower().startswith(
            "create table"
        ):
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

        # List by owner_sub.
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

        # DELETE.
        if sql_l.startswith("delete from amicable_meta.projects"):
            pid = re.search(r"where project_id\s*=\s*'([^']+)'", sql, flags=re.I).group(
                1
            )  # type: ignore[union-attr]
            sub = re.search(r"and owner_sub\s*=\s*'([^']+)'", sql, flags=re.I).group(1)  # type: ignore[union-attr]
            row = self.projects.get(pid)
            if row and row["owner_sub"] == sub:
                self.projects.pop(pid, None)
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
