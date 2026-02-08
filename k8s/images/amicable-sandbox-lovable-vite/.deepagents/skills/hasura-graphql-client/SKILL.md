---
name: hasura-graphql-client
description: How to call the Amicable Hasura GraphQL proxy from the browser.
license: MIT
---

# Hasura GraphQL Client (Browser)

## When To Use
- You need to read/write Hasura data from the frontend.

## How It Works
- The agent injects a small config object into the browser at `window.__AMICABLE_DB__`.
- Use `graphqlUrl` and `appKey` to call the proxy.

## Minimal Fetch Example
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
