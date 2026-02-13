---
name: nextjs-basics
description: Execution-ready guidance for Next.js 15 App Router projects in Amicable.
license: MIT
---

# Next.js Basics

## When To Use
- You are editing the Next.js 15 template.
- You are adding routes, server data loading, or client interactivity.

## Implementation Rules
- Use App Router conventions under `src/app/`.
- Default to Server Components; add `"use client"` only when browser APIs/state/effects are required.
- Keep server-only logic out of client components.
- Use Route Handlers (`app/**/route.ts`) for HTTP endpoints when needed.

## Data and Boundaries
- For browser-side DB calls, use `window.__AMICABLE_DB__` helper logic in client components only.
- For server-side data fetching, use standard `fetch` in Server Components/Route Handlers.

## Verify
- Run `npm run -s lint`.
- Run `npm run -s build`.
- Confirm affected route(s) render in preview and no client/server boundary errors appear.
