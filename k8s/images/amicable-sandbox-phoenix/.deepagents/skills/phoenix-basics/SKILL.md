---
name: phoenix-basics
description: Execution-ready guidance for Phoenix contexts, routes, and LiveView pages.
license: MIT
---

# Phoenix Basics

## When To Use
- You are editing the Phoenix template.
- You are adding routes, controllers, contexts, or LiveView features.

## Implementation Rules
- Keep controllers thin and push domain logic into contexts.
- Use explicit route naming and small modules with clear responsibilities.
- Keep LiveView event handlers focused and deterministic.
- Avoid mixing persistence/business rules into presentation code.

## Sandbox Notes
- Preview runs with `mix phx.server` on port `3000`.
- Template already uses fs polling for better live reload in containerized environments.

## Verify
- Run `mix compile`.
- Run `mix test` when tests exist.
- Confirm updated routes/pages render and interactive flows behave correctly.
