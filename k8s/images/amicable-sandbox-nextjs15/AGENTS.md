# Production (Next.js 15) Sandbox

This workspace is a Next.js 15 (App Router) + TypeScript (strict) starter.

## Commands (from /app)
- `npm install`
- `npm run dev` (preview runs on port 3000)
- `npm run lint` / `npm run build` (if present)

## Hasura / DB Proxy
- If configured, the agent injects `/public/amicable-db.js` and ensures the app includes a script tag for `/amicable-db.js`.
- The browser can read `window.__AMICABLE_DB__` for `{ appId, graphqlUrl, appKey, previewOrigin }`.

## Notes
- Next.js builds can be memory heavy; allocate at least 2Gi RAM for this sandbox template.
