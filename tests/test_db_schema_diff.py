from __future__ import annotations

from src.db.schema_diff import (
    build_schema_diff,
    compute_schema_version,
    normalize_schema_model,
)


def test_build_schema_diff_add_table_column_and_relationship_sql() -> None:
    current = {
        "app_id": "p1",
        "schema_name": "app_deadbeef1234",
        "tables": [],
        "relationships": [],
    }
    draft = {
        "app_id": "p1",
        "schema_name": "app_deadbeef1234",
        "tables": [
            {
                "label": "Customers",
                "name": "customers",
                "position": {"x": 100, "y": 200},
                "columns": [
                    {
                        "name": "email",
                        "label": "Email",
                        "type": "text",
                        "nullable": False,
                    }
                ],
            },
            {
                "label": "Orders",
                "name": "orders",
                "position": {"x": 400, "y": 200},
                "columns": [
                    {
                        "name": "customer_id",
                        "label": "Customer",
                        "type": "bigint",
                        "nullable": False,
                    }
                ],
            },
        ],
        "relationships": [
            {
                "name": "fk_orders_customer",
                "from_table": "orders",
                "from_column": "customer_id",
                "to_table": "customers",
                "to_column": "id",
                "on_delete": "CASCADE",
                "on_update": "NO ACTION",
            }
        ],
    }

    out = build_schema_diff(current, draft)
    assert out["destructive"] is False
    sql = "\n".join(out["sql"])
    assert "CREATE TABLE IF NOT EXISTS" in sql
    assert "ADD CONSTRAINT" in sql
    assert "FOREIGN KEY" in sql


def test_build_schema_diff_marks_destructive_when_dropping_table_and_column() -> None:
    current = {
        "app_id": "p1",
        "schema_name": "app_deadbeef1234",
        "tables": [
            {
                "name": "customers",
                "label": "Customers",
                "position": {"x": 0, "y": 0},
                "columns": [
                    {
                        "name": "id",
                        "label": "Id",
                        "type": "bigserial",
                        "nullable": False,
                        "is_primary": True,
                        "default": None,
                    },
                    {
                        "name": "email",
                        "label": "Email",
                        "type": "text",
                        "nullable": False,
                        "default": None,
                    },
                ],
            }
        ],
        "relationships": [],
    }
    draft = {
        "app_id": "p1",
        "schema_name": "app_deadbeef1234",
        "tables": [],
        "relationships": [],
    }

    out = build_schema_diff(current, draft)
    assert out["destructive"] is True
    assert any("drop table customers" in x for x in out["destructive_details"])
    assert any("DROP TABLE" in s for s in out["sql"])


def test_compute_schema_version_is_stable_for_logically_equal_models() -> None:
    schema_a = {
        "app_id": "p1",
        "schema_name": "app_deadbeef1234",
        "tables": [
            {
                "name": "orders",
                "label": "Orders",
                "position": {"x": 10, "y": 20},
                "columns": [
                    {
                        "name": "id",
                        "label": "Id",
                        "type": "bigserial",
                        "nullable": False,
                        "is_primary": True,
                    },
                    {
                        "name": "total",
                        "label": "Total",
                        "type": "numeric",
                        "nullable": False,
                    },
                ],
            }
        ],
        "relationships": [],
    }
    schema_b = normalize_schema_model(
        {
            "app_id": "p1",
            "schema_name": "app_deadbeef1234",
            "tables": [
                {
                    "label": "Orders",
                    "name": "orders",
                    "position": {"x": 10, "y": 20},
                    "columns": [
                        {
                            "label": "Total",
                            "name": "total",
                            "type": "numeric",
                            "nullable": False,
                        },
                        {
                            "label": "Id",
                            "name": "id",
                            "type": "bigserial",
                            "nullable": False,
                            "is_primary": True,
                        },
                    ],
                }
            ],
            "relationships": [],
        },
        generate_missing_names=False,
    )

    assert compute_schema_version(schema_a) == compute_schema_version(schema_b)
