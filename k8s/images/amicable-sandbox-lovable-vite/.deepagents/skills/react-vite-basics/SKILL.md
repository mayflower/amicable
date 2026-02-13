---
name: react-vite-basics
description: Execution-ready guidance for React + Vite sandbox projects.
license: MIT
---

# React + Vite Basics

## When To Use
- You are editing the Lovable Native (React + Vite) template.
- You need client-side routes, stateful UI, or browser data fetching.

## Implementation Rules
- Prefer function components and hooks.
- Keep route-level screens in route files and move reusable UI to `src/components/`.
- Use shared helpers (`src/lib/*`) for API/GraphQL calls.
- Keep UI responsive and avoid blocking renders with heavy synchronous logic.

## Sandbox Notes
- Keep Vite dev server compatible with reverse-proxied preview (`0.0.0.0:3000`).
- If file watch/HMR is flaky in containerized runtimes, use polling as documented in `/AGENTS.md`.

## Verify
- Run `npm run -s lint`.
- Run `npm run -s typecheck`.
- Run `npm run -s build`.
- Confirm the main route renders and modified interactions work in preview.
