---
name: hasura-db-proxy
description: Building DB-backed features in Amicable using Hasura via the DB proxy (Laravel template).
license: MIT
---

# Hasura DB Proxy (Laravel)

## When To Use
- The user asks for database-backed features (CRUD, lists, search, dashboards).
- You need persistence across refreshes and sessions.

## Key Rules
- Read DB config from `window.__AMICABLE_DB__`.
- Never hardcode Hasura admin credentials in app code.
- Send GraphQL requests to `graphqlUrl` with header `x-amicable-app-key`.
- Prefer DB tools for table creation/permissions before wiring UI calls.

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

## Verify
- Confirm `window.__AMICABLE_DB__` exists in preview.
- Run a smoke query (`__typename`) and confirm 200 response.
- Verify at least one read and one mutation path end-to-end.
