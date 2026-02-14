# Lightweight Logic (Hono) Sandbox

This workspace is a small TypeScript Hono service intended for Hasura Actions and Event Triggers.

## File Editing

- **`write_file` creates a new file.** It will fail if the file already exists. Use it only for brand-new files.
- **Always prefer `edit_file`** for modifying existing files. Use `edit_file` even when replacing most or all of a file's content.
- Never delete a file and re-create it with `write_file` — use `edit_file` to rewrite it in place.
## Commands (from /app)
- `npm install`
- `npm run dev` (preview runs on port 3000)
- `npm run lint` / `npm run typecheck` / `npm run build`

## Browser Testing (Recommended)
- Open `GET /docs` for Swagger UI (tries endpoints in-browser).
- Open `GET /openapi.json` for the OpenAPI document.

## Hasura
- Implement webhook handlers as HTTP routes.
- For Actions: typically a `POST /actions/<name>` route returning JSON.
- For Event Triggers: typically a `POST /events/<name>` route.
