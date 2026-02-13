---
name: tanstack-query
description: Practical guidance for TanStack Query in generated React sandbox apps.
license: MIT
---

# TanStack Query

## When To Use
- You need caching, retries, loading states, or mutation invalidation for API/GraphQL calls.

## Implementation Rules
- Create one `QueryClient` at app root and wrap with `QueryClientProvider`.
- Use stable, scoped query keys.
- Keep query functions pure and throw on HTTP/GraphQL errors.
- Invalidate only affected queries after successful mutations.

## Verify
- Confirm query loading/error/success states render correctly.
- Confirm mutations update UI via invalidation or optimistic updates.
- Run template QA scripts (lint/typecheck/build) after data-layer changes.
