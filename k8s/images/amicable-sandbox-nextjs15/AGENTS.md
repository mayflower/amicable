# Production (Next.js 15) Sandbox

This workspace is a Next.js 15 (App Router) + TypeScript (strict) starter.

## File Editing

- **`write_file` overwrites the target file.** Never use `rm` or `unlink` to delete a file before rewriting it — just call `write_file` directly.
- Prefer `write_file` over `edit_file` when replacing most or all of a file's content.
## Commands (from /app)
- `npm install`
- `npm run dev` (preview runs on port 3000)
- `npm run lint` / `npm run build` (if present)

## Hasura / DB Proxy
- If configured, the agent injects `/public/amicable-db.js` and ensures the app includes a script tag for `/amicable-db.js`.
- The browser can read `window.__AMICABLE_DB__` for `{ appId, graphqlUrl, appKey, previewOrigin }`.

## Notes
- Next.js builds can be memory heavy; allocate at least 2Gi RAM for this sandbox template.
