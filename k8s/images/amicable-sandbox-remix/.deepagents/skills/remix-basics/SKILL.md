---
name: remix-basics
description: Execution-ready guidance for Remix-style React Router data workflows.
license: MIT
---

# Remix-Style (React Router) Basics

## When To Use
- You are editing the Remix-style template scaffolded with `create-react-router`.
- You are implementing data loading and mutations.

## Implementation Rules
- Use loaders for reads and actions for writes.
- Keep validation close to each action.
- Keep route modules focused; move shared logic to `app/lib/*`.
- Use fetchers/forms for granular mutations instead of full-page reload flows.

## Data Notes
- For browser GraphQL calls, use injected DB config from `window.__AMICABLE_DB__`.
- Keep query and mutation payloads explicit and type-safe where possible.

## Verify
- Run `npm run -s build`.
- Run `npm run -s typecheck` when script exists.
- Confirm loader-rendered data and action mutations both work in preview.
