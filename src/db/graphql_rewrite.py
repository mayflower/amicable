"""
GraphQL query rewriting for Amicable's per-app Postgres schemas.

Hasura exposes non-`public` schema tables as `<schema>_<table>` root fields by
default (for example `app_deadbeef1234_todos`). Our frontend skills and many
generated apps naturally write queries against logical table names like `todos`.

This module rewrites *top-level* root fields for query/mutation operations so
`todos` becomes `app_<hex12>_todos`, and `insert_todos_one` becomes
`insert_app_<hex12>_todos_one`, etc.

Only top-level fields are rewritten; nested selections are left untouched.
Introspection fields (`__schema`, `__type`) are never rewritten.
"""

from __future__ import annotations


def _rewrite_query_root_field(name: str, *, schema: str) -> str:
    if not name or name.startswith("__"):
        return name
    prefix = f"{schema}_"
    if name.startswith(prefix):
        return name
    return prefix + name


def _rewrite_mutation_root_field(name: str, *, schema: str) -> str:
    if not name or name.startswith("__"):
        return name
    for op in ("insert_", "update_", "delete_"):
        if name.startswith(op):
            rest = name[len(op) :]
            prefix = f"{schema}_"
            if rest.startswith(prefix):
                return name
            return op + prefix + rest
    return name


def rewrite_hasura_query_for_app_schema(query: str, *, schema: str) -> str:
    """Rewrite a GraphQL document string to target Hasura's schema-prefixed root fields."""
    q = (query or "").strip()
    if not q:
        return query

    # Lazy import: graphql-core is only needed for the DB proxy path.
    try:
        from graphql import parse, print_ast  # type: ignore
        from graphql.language.ast import (  # type: ignore
            DocumentNode,
            FieldNode,
            NameNode,
            OperationDefinitionNode,
            SelectionSetNode,
        )
    except Exception:
        # If parsing isn't available, fall back to the original query (better to
        # return a Hasura validation error than to corrupt the query).
        return query

    try:
        doc = parse(q)
    except Exception:
        return query

    def rewrite_top_level_fields(
        op: str, selection_set: SelectionSetNode
    ) -> SelectionSetNode:
        if not selection_set or not getattr(selection_set, "selections", None):
            return selection_set

        if op == "mutation":
            def f_rewrite(n: str) -> str:
                return _rewrite_mutation_root_field(n, schema=schema)
        else:
            def f_rewrite(n: str) -> str:
                return _rewrite_query_root_field(n, schema=schema)

        changed = False
        new_selections = []
        for sel in selection_set.selections:
            if isinstance(sel, FieldNode) and sel.name and getattr(sel.name, "value", None):
                new_name = f_rewrite(sel.name.value)
                if new_name != sel.name.value:
                    changed = True
                    # Preserve the original field name as a GraphQL alias so the
                    # response JSON key matches what the client expects.
                    original_alias = sel.alias or NameNode(value=sel.name.value)
                    sel = FieldNode(
                        alias=original_alias,
                        name=type(sel.name)(value=new_name),
                        arguments=sel.arguments,
                        directives=sel.directives,
                        selection_set=sel.selection_set,
                    )
            new_selections.append(sel)

        if not changed:
            return selection_set
        return SelectionSetNode(selections=tuple(new_selections))

    # Rebuild a new DocumentNode with rewritten top-level field names.
    changed_any = False
    new_defs = []
    for d in doc.definitions:
        if isinstance(d, OperationDefinitionNode) and d.selection_set:
            # graphql-core uses an enum OperationType with `.value` in {"query","mutation","subscription"}.
            op_obj = getattr(d, "operation", None)
            op = str(getattr(op_obj, "value", op_obj) or "")
            new_ss = rewrite_top_level_fields(op, d.selection_set)
            if new_ss is not d.selection_set:
                changed_any = True
                d = OperationDefinitionNode(
                    operation=d.operation,
                    name=d.name,
                    variable_definitions=d.variable_definitions,
                    directives=d.directives,
                    selection_set=new_ss,
                )
        new_defs.append(d)

    if not changed_any:
        return query
    new_doc = DocumentNode(definitions=tuple(new_defs))
    try:
        return print_ast(new_doc)
    except Exception:
        return query
