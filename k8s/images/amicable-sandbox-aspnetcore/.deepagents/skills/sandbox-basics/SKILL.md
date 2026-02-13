---
name: sandbox-basics
description: Quick reference for ASP.NET Core sandbox workflow.
license: MIT
---

# Sandbox Basics

## When To Use
- You are editing the ASP.NET Core sandbox template.
- You need a deterministic check sequence before finishing.

## Checklist
- Restore packages when needed: `dotnet restore`.
- Use deterministic QA commands: `dotnet build` and `dotnet test`.
- Keep preview compatibility: `dotnet watch run --urls http://0.0.0.0:3000`.

## Verify
- Run `dotnet build` and ensure zero errors.
- Run `dotnet test` when tests exist.
- Confirm preview remains reachable at `0.0.0.0:3000`.
