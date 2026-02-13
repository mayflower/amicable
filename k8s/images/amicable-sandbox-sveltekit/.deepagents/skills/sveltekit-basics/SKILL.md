---
name: sveltekit-basics
description: Execution-ready guidance for SvelteKit routing and data workflows in Amicable.
license: MIT
---

# SvelteKit Basics

## When To Use
- You are editing the SvelteKit template.
- You are adding route data loading or form mutations.

## Implementation Rules
- Keep routes under `src/routes/`.
- Use `+page.server.ts`/`+layout.server.ts` for server-only load/actions.
- Keep browser-only logic in Svelte components and guard `window` access.
- Keep server-side mutation and validation logic deterministic.

## Data Notes
- Browser DB calls use `window.__AMICABLE_DB__` and `x-amicable-app-key`.
- Favor explicit load/action return shapes to simplify UI states.

## Verify
- Run `npm run -s build`.
- Run `npm run -s typecheck` if available.
- Confirm load data and form actions behave correctly in preview.
