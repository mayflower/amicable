---
name: fastapi-basics
description: Execution-ready guidance for FastAPI Hasura webhook handlers.
license: MIT
---

# FastAPI Basics

## When To Use
- You are editing the FastAPI template.
- You are implementing Actions/Event Trigger webhooks or API endpoints.

## Implementation Rules
- Use Pydantic models for request and response contracts.
- Keep route handlers thin; move logic into service modules when complexity grows.
- Use dependencies for shared concerns (auth/context/validation helpers).
- Return structured JSON errors and explicit status codes.

## Sandbox Notes
- Keep the preview command compatible with `uvicorn ... --host 0.0.0.0 --port 3000 --reload`.
- Use `/docs` to quickly validate endpoint contracts.

## Verify
- Run `python -m compileall -q .`.
- Run `ruff check .`.
- Run `pytest` when tests exist or are requested.
- Confirm key webhook endpoints return expected JSON shapes.
