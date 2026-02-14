# SvelteKit Full-Stack App Sandbox

This workspace is a SvelteKit starter (Svelte + Vite) intended for AI-driven editing.

## File Editing

- **`write_file` overwrites the target file.** Never use `rm` or `unlink` to delete a file before rewriting it — just call `write_file` directly.
- Prefer `write_file` over `edit_file` when replacing most or all of a file's content.
## Commands (from /app)
- `npm install`
- `npm run dev -- --host 0.0.0.0 --port 3000`
- `npm run build` (if present)

## Hasura / DB Proxy
- If configured, the agent injects `/static/amicable-db.js` and patches `src/app.html` to include `<script src="/amicable-db.js">`.
- The browser can read `window.__AMICABLE_DB__`.
