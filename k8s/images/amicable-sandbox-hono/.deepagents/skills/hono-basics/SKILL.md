---
name: hono-basics
description: Building Hasura webhook handlers with Hono.
license: MIT
---

# Hono Basics

## When To Use
- You are editing the Hono + TypeScript template.

## Conventions
- Validate inputs (Hasura sends JSON bodies).
- Return JSON with explicit status codes.
- Keep handlers small and pure; push shared logic into `src/lib/*`.

## Local Preview
- The sandbox preview runs the Hono server on port 3000.
