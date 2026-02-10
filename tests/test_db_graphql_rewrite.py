from __future__ import annotations

from src.db.graphql_rewrite import rewrite_hasura_query_for_app_schema


def test_rewrite_query_root_field() -> None:
    q = """
      query FetchTodos {
        todos(order_by: {created_at: asc}) { id text }
      }
    """
    out = rewrite_hasura_query_for_app_schema(q, schema="app_deadbeef1234")
    assert "app_deadbeef1234_todos" in out
    assert " todos(" not in out


def test_rewrite_mutation_root_field() -> None:
    q = """
      mutation Add($text: String!) {
        insert_todos_one(object: {text: $text}) { id }
      }
    """
    out = rewrite_hasura_query_for_app_schema(q, schema="app_deadbeef1234")
    assert "insert_app_deadbeef1234_todos_one" in out


def test_dont_double_prefix() -> None:
    q = "query { app_deadbeef1234_todos { id } }"
    out = rewrite_hasura_query_for_app_schema(q, schema="app_deadbeef1234")
    assert out.count("app_deadbeef1234_todos") == 1


def test_keep_alias() -> None:
    q = "query { items: todos { id } }"
    out = rewrite_hasura_query_for_app_schema(q, schema="app_deadbeef1234")
    assert "items:" in out
    assert "app_deadbeef1234_todos" in out


def test_leave_introspection_fields() -> None:
    q = "query { __schema { queryType { name } } }"
    out = rewrite_hasura_query_for_app_schema(q, schema="app_deadbeef1234")
    assert "__schema" in out
    assert "app_deadbeef1234___schema" not in out

