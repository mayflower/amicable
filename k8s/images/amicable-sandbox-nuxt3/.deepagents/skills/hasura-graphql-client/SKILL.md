---
name: hasura-graphql-client
description: How to call the Amicable Hasura GraphQL proxy from browser code.
license: MIT
---

# Hasura GraphQL Client (Browser)

## When To Use
- You need persistent data in a DB-enabled Amicable web template.
- You are implementing CRUD features from browser code.

## How It Works
- Amicable injects DB runtime config at `window.__AMICABLE_DB__`.
- Use `graphqlUrl` and `appKey` from that object.
- Always send header `x-amicable-app-key`.
- Query logical table names (for example `todos`); the proxy rewrites top-level Hasura fields to app-schema-prefixed names.

## Minimal Fetch Helper
```ts
type GraphQLResponse<T> = { data?: T; errors?: Array<{ message: string }> };

export async function gql<T>(query: string, variables?: Record<string, unknown>): Promise<T> {
  const cfg = (window as any).__AMICABLE_DB__;
  if (!cfg?.graphqlUrl || !cfg?.appKey) throw new Error("DB not configured");

  const res = await fetch(cfg.graphqlUrl, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-amicable-app-key": cfg.appKey,
    },
    body: JSON.stringify({ query, variables: variables ?? {} }),
  });

  const json = (await res.json()) as GraphQLResponse<T>;
  if (!res.ok || json.errors?.length) {
    throw new Error(json.errors?.[0]?.message || `GraphQL error (${res.status})`);
  }
  return json.data as T;
}
```

## Verify
- Confirm `window.__AMICABLE_DB__` exists in the browser.
- Run a smoke query: `query Smoke { __typename }`.
- Verify CRUD operations work using logical table root fields (`todos`, `insert_todos_one`, etc.).
