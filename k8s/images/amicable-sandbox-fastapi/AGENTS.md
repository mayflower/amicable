# AI Agent Backend (FastAPI) Sandbox

This workspace is a Python FastAPI service intended for Hasura Actions and Event Triggers.

## Commands (from /app)
- `pip install -r requirements.txt`
- `uvicorn app.main:app --host 0.0.0.0 --port 3000 --reload`

## QA
- `python -m compileall -q .`
- `ruff check .`
- `pytest` (if present and enabled)

## Hasura
- Implement webhook handlers as HTTP routes.
- For Actions: typically a `POST /actions/<name>` endpoint returning JSON.
