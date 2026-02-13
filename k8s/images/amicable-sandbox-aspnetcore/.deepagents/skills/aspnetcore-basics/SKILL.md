---
name: aspnetcore-basics
description: Execution-ready guidance for ASP.NET Core minimal API and service design.
license: MIT
---

# ASP.NET Core Basics

## When To Use
- You are editing the ASP.NET Core template.
- You are adding endpoints, request models, or service-layer logic.

## Implementation Rules
- Keep endpoint handlers focused on transport concerns.
- Move business logic into dedicated classes/services.
- Prefer typed responses and explicit status codes.
- Validate request data before invoking domain logic.

## Sandbox Notes
- Preview runs `dotnet watch run` on `0.0.0.0:3000`.
- Polling file watcher is enabled for container-friendly reloads.

## Verify
- Run `dotnet build`.
- Run `dotnet test` when tests exist.
- Confirm changed endpoints/pages behave as expected in preview.
