# Amicable Editor (Frontend)

This folder contains the Amicable editor single-page app (React + Vite).

## Development

```bash
cd frontend
npm install
npm run dev
```

## Build / Lint

```bash
cd frontend
npm run build
npm run lint
```

## Configuration

The editor connects to the agent service via WebSocket/HTTP.

Environment variables:
- `VITE_AGENT_WS_URL`
- `VITE_AGENT_HTTP_URL` (optional; derived from WS URL if unset)

Runtime overrides (for Kubernetes/static deploys):
- `frontend/public/config.js` sets `window.__AMICABLE_CONFIG__`

## Routes

- `/` project list + create
- `/create` legacy create route
- `/p/:slug` project editor route
