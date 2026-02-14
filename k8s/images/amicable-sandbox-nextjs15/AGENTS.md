# Production (Next.js 15) Sandbox

This workspace is a Next.js 15 (App Router) + TypeScript (strict) starter.

## File Editing

- **`write_file` creates a new file.** It will fail if the file already exists. Use it only for brand-new files.
- **Always prefer `edit_file`** for modifying existing files. Use `edit_file` even when replacing most or all of a file's content.
- Never delete a file and re-create it with `write_file` — use `edit_file` to rewrite it in place.
## Commands (from /app)
- `npm install`
- `npm run dev` (preview runs on port 3000)
- `npm run lint` / `npm run build` (if present)

## Hasura / DB Proxy
- If configured, the agent injects `/public/amicable-db.js` and ensures the app includes a script tag for `/amicable-db.js`.
- The browser can read `window.__AMICABLE_DB__` for `{ appId, graphqlUrl, appKey, previewOrigin }`.

## Notes
- Next.js builds can be memory heavy; allocate at least 2Gi RAM for this sandbox template.
