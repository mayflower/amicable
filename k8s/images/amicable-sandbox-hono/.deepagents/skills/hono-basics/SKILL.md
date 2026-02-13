---
name: hono-basics
description: Execution-ready guidance for Hono TypeScript webhook handlers.
license: MIT
---

# Hono Basics

## When To Use
- You are editing the Hono + TypeScript template.
- You are implementing JSON endpoints for Hasura Actions/Event Triggers.

## Implementation Rules
- Validate incoming payloads and fail with explicit status codes.
- Keep handlers small and move reusable logic to `src/lib/*`.
- Keep OpenAPI docs (`/openapi.json`) aligned with route behavior.
- Return predictable JSON contracts from every endpoint.

## Sandbox Notes
- The preview runtime expects the service on port `3000`.
- Swagger UI at `/docs` is the fastest in-sandbox endpoint sanity check.

## Verify
- Run `npm run -s typecheck`.
- Run `npm run -s build`.
- Run `npm run -s lint`.
- Confirm `/docs`, `/openapi.json`, and changed endpoints work in preview.
