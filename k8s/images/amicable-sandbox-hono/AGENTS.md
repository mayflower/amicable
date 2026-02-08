# Lightweight Logic (Hono) Sandbox

This workspace is a small TypeScript Hono service intended for Hasura Actions and Event Triggers.

## Commands (from /app)
- `npm install`
- `npm run dev` (preview runs on port 3000)
- `npm run lint` / `npm run typecheck` / `npm run build`

## Hasura
- Implement webhook handlers as HTTP routes.
- For Actions: typically a `POST /actions/<name>` route returning JSON.
- For Event Triggers: typically a `POST /events/<name>` route.
