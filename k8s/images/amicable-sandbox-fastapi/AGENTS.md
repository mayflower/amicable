# AI Agent Backend (FastAPI) Sandbox

This workspace is a Python FastAPI service intended for Hasura Actions and Event Triggers.

## File Editing

- **`write_file` creates a new file.** It will fail if the file already exists. Use it only for brand-new files.
- **Always prefer `edit_file`** for modifying existing files. Use `edit_file` even when replacing most or all of a file's content.
- Never delete a file and re-create it with `write_file` — use `edit_file` to rewrite it in place.
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
