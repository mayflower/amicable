---
name: sandbox-basics
description: Quick reference for Phoenix sandbox workflow.
license: MIT
---

# Sandbox Basics

## When To Use
- You are editing the Phoenix sandbox template.
- You need deterministic compile/test checks before finishing.

## Checklist
- Fetch deps when needed: `mix deps.get`.
- Use deterministic checks: `mix compile` and `mix test`.
- Keep preview compatibility with `mix phx.server` on port `3000`.

## Verify
- Run `mix compile` and ensure zero compilation errors.
- Run `mix test` when tests exist.
- Confirm preview remains reachable on port `3000`.
