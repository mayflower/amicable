---
name: fastapi-basics
description: Building Hasura webhook handlers with FastAPI.
license: MIT
---

# FastAPI Basics

## When To Use
- You are editing the FastAPI template.

## Conventions
- Use pydantic models for request/response bodies.
- Validate incoming payloads; return structured errors.
- Keep routes thin; move logic into `app/services/*`.

## Preview
- The sandbox preview runs `uvicorn` on port 3000.
- Visit `/docs` for Swagger UI.
