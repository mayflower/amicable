---
name: tanstack-query
description: Notes for using TanStack Query in generated React apps.
license: MIT
---

# TanStack Query

## When To Use
- You need caching/retries/loading states for API or GraphQL calls.

## Guidelines
- Create a single `QueryClient` in the root and use `QueryClientProvider`.
- Prefer `useQuery`/`useMutation` with small query keys.
- Keep query functions pure and throw on errors.
