# Vue Full-Stack App (Nuxt 3) Sandbox

This workspace is a Nuxt 3 starter (Vue + Vite) intended for AI-driven editing.

## File Editing

- **`write_file` creates a new file.** It will fail if the file already exists. Use it only for brand-new files.
- **Always prefer `edit_file`** for modifying existing files. Use `edit_file` even when replacing most or all of a file's content.
- Never delete a file and re-create it with `write_file` — use `edit_file` to rewrite it in place.
## Commands (from /app)
- `npm install`
- `npm run dev` (preview runs on port 3000)
- `npm run build` (if present)

## Hasura / DB Proxy
- If configured, the agent injects `/public/amicable-db.js` and patches `nuxt.config.ts` to include a `<script src="/amicable-db.js">` tag.
- The browser can read `window.__AMICABLE_DB__` for `{ appId, graphqlUrl, appKey, previewOrigin }`.
