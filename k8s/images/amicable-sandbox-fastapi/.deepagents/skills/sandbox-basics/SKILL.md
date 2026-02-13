---
name: sandbox-basics
description: Quick reference for Python/FastAPI sandbox workflow.
license: MIT
---

# Sandbox Basics

## When To Use
- You are editing the FastAPI sandbox template.
- You need deterministic command order for reliable feedback.

## Checklist
- Install dependencies first when required: `pip install -r requirements.txt`.
- Prefer deterministic QA commands: `python -m compileall -q .`, `ruff check .`.
- Run `pytest` when tests are present or explicitly requested.

## Verify
- Run compile + lint in order and ensure both succeed.
- Run tests when requested and confirm no regressions.
- Confirm preview still responds on port `3000`.
