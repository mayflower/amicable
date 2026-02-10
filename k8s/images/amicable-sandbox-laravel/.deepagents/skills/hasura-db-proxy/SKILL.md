---
name: hasura-db-proxy
description: How to build database-backed features in Amicable using Hasura via the DB proxy (Laravel template).
license: MIT
---

# Hasura DB Proxy (Laravel)

## When To Use
- The user asks for a database-backed feature (CRUD, todo list, users, etc).
- You need persistence across refreshes/sessions.

## Key Facts
- The browser should call Hasura through the agent DB proxy URL found in `window.__AMICABLE_DB__`.
- Never hardcode Hasura admin secrets in the sandbox.
- Prefer the DB tools (e.g. `db_create_table`) to create/track tables and grant CRUD permissions.

## Browser GraphQL Call

```js
const db = window.__AMICABLE_DB__;
if (!db?.graphqlUrl || !db?.appKey) throw new Error("DB not configured");

const res = await fetch(db.graphqlUrl, {
  method: "POST",
  headers: {
    "content-type": "application/json",
    "x-amicable-app-key": db.appKey,
  },
  body: JSON.stringify({ query: "{ __typename }" }),
});
console.log(await res.json());
```

## Todo List Shape (Suggested)
- Table: `todos`
- Columns: `title` (text, not null), `completed` (boolean, not null, default false), `created_at` (timestamptz, default now())

Typical queries/mutations (Hasura auto-generated):
- Query: `todos { id title completed created_at }`
- Insert: `insert_todos_one(object: { title: $title }) { id ... }`
- Update: `update_todos_by_pk(pk_columns: { id: $id }, _set: { completed: $completed }) { id completed }`
- Delete: `delete_todos_by_pk(id: $id) { id }`

