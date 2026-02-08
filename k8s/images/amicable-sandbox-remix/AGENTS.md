# Enterprise Dashboard (Remix) Sandbox

Note: Remix v2 is upstreamed into React Router. This template is scaffolded via `create-react-router` using a Remix-style full-stack template.

## Commands (from /app)
- `npm install`
- `npm run dev` (preview runs on port 3000)
- `npm run build` (if present)

## Hasura / DB Proxy
- If configured, the agent injects `/public/amicable-db.js` and ensures the app includes a script tag for `/amicable-db.js`.
- The browser can read `window.__AMICABLE_DB__` for `{ appId, graphqlUrl, appKey, previewOrigin }`.
