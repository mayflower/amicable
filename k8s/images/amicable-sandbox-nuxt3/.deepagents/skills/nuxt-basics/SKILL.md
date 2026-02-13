---
name: nuxt-basics
description: Execution-ready guidance for Nuxt 3 full-stack workflows in Amicable.
license: MIT
---

# Nuxt 3 Basics

## When To Use
- You are editing the Nuxt 3 template.
- You are adding pages, composables, or server API endpoints.

## Implementation Rules
- Keep pages under `pages/` and server endpoints under `server/api/`.
- Place reusable data logic in `composables/`.
- Keep server-only concerns inside server routes or Nitro server utilities.
- Avoid leaking secrets/config to client bundles.

## Data Notes
- Browser DB calls must use `window.__AMICABLE_DB__` and `x-amicable-app-key`.
- Use clear error handling paths in composables and page logic.

## Verify
- Run `npm run -s build`.
- Run `npm run -s typecheck` if available.
- Confirm changed page routes and server endpoints work in preview.
