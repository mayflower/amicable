# Vue Full-Stack App (Nuxt 3) Sandbox

This workspace is a Nuxt 3 starter (Vue + Vite) intended for AI-driven editing.

## Commands (from /app)
- `npm install`
- `npm run dev` (preview runs on port 3000)
- `npm run build` (if present)

## Hasura / DB Proxy
- If configured, the agent injects `/public/amicable-db.js` and patches `nuxt.config.ts` to include a `<script src="/amicable-db.js">` tag.
- The browser can read `window.__AMICABLE_DB__` for `{ appId, graphqlUrl, appKey, previewOrigin }`.
