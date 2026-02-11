from __future__ import annotations

from typing import Any

from src.db.schema_introspection import introspect_schema


class FakeHasuraClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def run_sql(self, sql: str, *, read_only: bool = False, **_kwargs: Any):
        _ = read_only
        self.calls.append(sql)
        s = sql.lower()

        if "create schema if not exists amicable_meta" in s:
            return {"result_type": "CommandOk", "result": []}

        if "from amicable_meta.schema_labels" in s:
            return {
                "result": [
                    ["object_kind", "table_name", "column_name", "label"],
                    ["table", "customers", None, "Customers"],
                    ["column", "customers", "id", "Id"],
                    ["column", "customers", "full_name", "Full Name"],
                ]
            }

        if "from amicable_meta.schema_layout" in s:
            return {
                "result": [
                    ["table_name", "pos_x", "pos_y"],
                    ["customers", "120", "250"],
                ]
            }

        if "from information_schema.tables" in s:
            return {
                "result": [
                    ["table_name"],
                    ["customers"],
                ]
            }

        if "from information_schema.columns" in s:
            return {
                "result": [
                    [
                        "table_name",
                        "column_name",
                        "data_type",
                        "is_nullable",
                        "column_default",
                        "ordinal_position",
                        "udt_name",
                    ],
                    [
                        "customers",
                        "id",
                        "bigint",
                        "NO",
                        "nextval('customers_id_seq'::regclass)",
                        1,
                        "int8",
                    ],
                    ["customers", "full_name", "text", "YES", None, 2, "text"],
                ]
            }

        if "constraint_type = 'primary key'" in s:
            return {
                "result": [
                    ["table_name", "column_name"],
                    ["customers", "id"],
                ]
            }

        if "constraint_type = 'foreign key'" in s:
            return {"result": [["constraint_name", "from_table", "from_column", "to_table", "to_column", "update_rule", "delete_rule"]]}

        raise AssertionError(f"Unexpected SQL: {sql}")


def test_introspect_schema_maps_labels_layout_columns_and_pk() -> None:
    c = FakeHasuraClient()
    out = introspect_schema(c, app_id="p1", schema_name="app_deadbeef1234")

    assert out["app_id"] == "p1"
    assert out["schema_name"] == "app_deadbeef1234"
    assert len(out["tables"]) == 1

    t = out["tables"][0]
    assert t["name"] == "customers"
    assert t["label"] == "Customers"
    assert t["position"] == {"x": 120.0, "y": 250.0}

    cols = {c["name"]: c for c in t["columns"]}
    assert cols["id"]["is_primary"] is True
    assert cols["id"]["nullable"] is False
    assert cols["full_name"]["label"] == "Full Name"
    assert out["relationships"] == []
