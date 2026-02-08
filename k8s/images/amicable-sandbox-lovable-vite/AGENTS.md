# Lovable Native (React + Vite) Sandbox

This workspace is a Vite + React + Tailwind + shadcn/ui starter intended for AI-driven editing.

## Commands (from /app)
- `npm install`
- `npm run dev` (preview runs on port 3000)
- `npm run lint` / `npm run typecheck` / `npm run build` (if present)

## Hasura / DB Proxy
- If configured, the agent injects `/amicable-db.js` and ensures it is included in `/index.html`.
- The browser can read `window.__AMICABLE_DB__` for `{ appId, graphqlUrl, appKey, previewOrigin }`.

## Vite HMR Note
If HMR feels slow in gVisor, enable polling in `vite.config.ts`:
- `server.watch.usePolling = true`

