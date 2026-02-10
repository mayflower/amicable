# Developer Guide (Amicable)

This document explains how Amicable works end-to-end, where it runs, and how to develop it.

For production/runbook debugging, see: `docs/debugging.md`.

## What Amicable Is

Amicable is an AI-powered web app builder:

- The user interacts with a **web editor UI**.
- The UI sends prompts to an **agent service** over WebSockets.
- The agent edits a **sandboxed workspace** (per session) and the user sees the result in a **live preview** (Vite dev server).

## High-Level Architecture

Components:

1. **Editor** (static SPA)
   - Vite/React build served via nginx (optional to deploy in-cluster; Mayflower deploy does).
   - Code: `frontend/`

2. **Agent** (FastAPI + Uvicorn)
   - WebSocket server that streams responses and applies edits to sandboxes.
   - Code: `src/runtimes/ws_server.py`, `src/agent_core.py`

3. **Sandbox** (per session)
   - A per-session Kubernetes SandboxClaim (CRD) creates an isolated Pod.
   - The sandbox pod runs:
     - Vite dev server on `:3000` for preview.
     - A small runtime API on `:8888` for file I/O + command execution.
   - Code/runtime API: `k8s/images/amicable-sandbox/runtime.py`

4. **Preview Router** (nginx)
   - Routes `https://<sandbox-id>.amicable-preview.data.mayflower.zone/` to the correct sandbox pod's Vite server.
   - Code: `deploy/helm/amicable/templates/preview-router/*`

## Where It Runs (Mayflower "data-cluster")

In the Mayflower setup the public endpoints are:

- Editor: `https://amicable.data.mayflower.zone/`
- Agent: `https://amicable-agent.data.mayflower.zone/`
- Preview wildcard: `https://<sandbox-id>.amicable-preview.data.mayflower.zone/`

Deploy flow:

- Application manifests are managed by ArgoCD (see `argocd` repo).
- Helm chart lives here: `deploy/helm/amicable/`.
- Mayflower values live in the `data-cluster` repo (SOPS + values).

## Web Editor (Frontend)

The editor is a Vite/React SPA under `frontend/`.

Key behaviors:

- On load, the UI checks agent auth by calling `GET /auth/me` on the agent host:
  - Code: `frontend/src/hooks/useAgentAuth.ts`
- If `AUTH_MODE=google` and the user is not authenticated, the UI redirects to:
  - `GET /auth/login?redirect=<current-url>`
  - The agent performs Google OAuth and sets a session cookie (see below).
- The UI connects to the agent via WebSocket and uses a small message protocol:
  - Code: `frontend/src/screens/Create/index.tsx`

### Runtime Configuration

In Kubernetes deployments, the editor reads runtime config from a served `/config.js` file.

- `frontend/public/config.js` defines `window.__AMICABLE_CONFIG__`
- Helm renders `deploy/helm/amicable/templates/editor/configmap.yaml` which mounts `/config.js` into the nginx editor container.
- The frontend reads `window.__AMICABLE_CONFIG__` first, then falls back to Vite build-time env vars:
  - `frontend/src/config/agent.ts`

Key runtime keys:
- `VITE_AGENT_WS_URL` (WebSocket URL of the agent)
- `VITE_AGENT_HTTP_URL` (optional; derived from WS URL if unset)

### WS Protocol Summary

Messages are JSON of the shape:

```json
{ "type": "<message_type>", "data": { ... }, "id": "...", "session_id": "..." }
```

Important message types:

- `init`: initialize (or resume) a session; agent returns `url` (preview) + `sandbox_id`.
- `user`: user prompt
- `agent_partial`: streaming text
- `agent_final`: final text
- `update_file`: status line (e.g. "Editing /src/App.tsx", "Running npm run build")
- `update_in_progress` / `update_completed`
- `trace_event`: structured tool trace events.
  - Always includes a sidecar `reasoning_summary` event (based on observable actions, not chain-of-thought).
  - May include `tool_explain` events when the sidecar narrator is enabled.
- `hitl_request`: server pauses execution and requests human approval/modification for tool calls
- `hitl_response`: client provides decisions and the server resumes execution

The UI expects stable `id` values for `agent_partial/agent_final` and `update_file` so it can update messages in-place.

Generative UI (optional):
- Assistant messages may contain fenced UI payloads (```` ```ui {json} ``` ````).
- The editor parses these blocks client-side and renders them above the assistant bubble. The `ui` blocks are not a separate WS message type.

## Agent Service (FastAPI + WebSockets)

Entrypoint:

- `src/runtimes/ws_server.py`
  - `GET /healthz` for readiness.
  - `GET /auth/*` for auth (optional).
  - WebSockets at `/` and `/ws`.

Agent core:

- `src/agent_core.py` contains the `Agent` class and is responsible for:
  - creating/ensuring a sandbox session exists
  - running the DeepAgents engine
  - streaming WS messages back to the frontend

### Auth (Google OAuth)

If `AUTH_MODE=google` the agent:

- uses `Authlib` for OAuth
- uses Starlette `SessionMiddleware` to store the logged-in user in a signed session cookie

Important env vars (agent):

- `AUTH_MODE=google`
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
- `SESSION_SECRET` (stable secret for cookie signing)
- `PUBLIC_BASE_URL` (used to compute callback URL)
- `CORS_ALLOW_ORIGINS` and `AUTH_REDIRECT_ALLOW_ORIGINS` (redirect allowlist to prevent open redirects)

WebSocket access is blocked unless the session contains a user:

- Code: `_require_auth()` in `src/runtimes/ws_server.py`

### Key Env Vars

- `DEEPAGENTS_MODEL`: model string (default is an Anthropic model string)
- `DEEPAGENTS_MEMORY_SOURCES`: CSV of memory files (default `"/AGENTS.md,/.deepagents/AGENTS.md"`)
- `DEEPAGENTS_SKILLS_SOURCES`: CSV of skills directories (default `"/.deepagents/skills,/skills"`)
- `DEEPAGENTS_MODEL_RETRY_MAX_RETRIES`: model retry middleware retries (default `2`)
- `DEEPAGENTS_TOOL_RETRY_MAX_RETRIES`: tool retry middleware retries (default `2`)
- `DEEPAGENTS_HITL_INTERRUPT_ON_JSON`: JSON mapping tool -> interrupt config (default `{}`)
- `AUTH_MODE`: `google` / `none`
- `PUBLIC_BASE_URL`: used for OAuth callback URL generation
- `CORS_ALLOW_ORIGINS`, `AUTH_REDIRECT_ALLOW_ORIGINS`: allowlists
- `K8S_SANDBOX_NAMESPACE`, `K8S_SANDBOX_TEMPLATE_NAME`
- `PREVIEW_BASE_DOMAIN`, `PREVIEW_SCHEME`, `SANDBOX_RUNTIME_PORT`, `SANDBOX_PREVIEW_PORT`

### Optional: Per-App Database (Hasura)

When configured, the agent provisions and exposes a per-app database schema via Hasura.

- On `init`, the agent ensures an app row exists in `amicable_meta.apps`, creates a Postgres schema `app_<sha12(app_id)>`, and injects:
  - `/app/amicable-db.js` containing `window.__AMICABLE_DB__ = { appId, graphqlUrl, appKey }`
  - `<script src="/amicable-db.js"></script>` into `/app/index.html` (idempotent)
- The browser calls the agent proxy endpoint:
  - `POST /db/apps/<app_id>/graphql`
  - headers:
    - `Origin: https://amicable-<sha8(app_id)>.<PREVIEW_BASE_DOMAIN>`
    - `x-amicable-app-key: <app_key>`
- The agent validates origin + key, mints a short-lived Hasura JWT, and forwards the GraphQL request to Hasura.

Agent env vars for DB:
- `HASURA_BASE_URL`
- `HASURA_GRAPHQL_ADMIN_SECRET` (admin secret for metadata + run_sql)
- `HASURA_GRAPHQL_JWT_SECRET` (Hasura JWT signing config JSON, HS256)
- `HASURA_SOURCE_NAME` (default `default`)
- `AMICABLE_PUBLIC_BASE_URL` (defaults to `PUBLIC_BASE_URL` if not set)
- `AMICABLE_DB_PROXY_ORIGIN_MODE` (default `strict_preview`)

## DeepAgents + Controller Graph (QA + Self-Healing)

Amicable runs a DeepAgents (LangGraph-based) agent that can:

- read and write files in the sandbox workspace
- run shell commands in the sandbox

This is implemented by adapting the sandbox runtime API to DeepAgents' backend protocol:

- `src/deepagents_backend/k8s_runtime_backend.py`
- `src/deepagents_backend/policy.py` (deny-list policy wrapper)

### Deterministic QA and Self-Healing

Amicable wraps the DeepAgents agent with an **outer controller LangGraph**:

- `src/deepagents_backend/controller_graph.py`
- `src/deepagents_backend/qa.py`

Graph flow:

1. `deepagents_edit`: run DeepAgents to implement the user request.
2. `qa_validate`: run lint/typecheck/build deterministically in the sandbox.
3. If QA fails, `self_heal_message` injects the QA failure (command + output) as a new user message and loops back to `deepagents_edit`.
4. After N rounds, it ends with a failure summary.

### Optional: GitLab Persistence (Repo Per Project + Auto Snapshot Commits)

If enabled, the controller graph runs a `git_sync` step after the controller run finishes (after QA success **or** QA failure). This exports a snapshot of `/app` from the sandbox (with excludes like `node_modules/`), commits it, and pushes it to a GitLab repo named after the project slug.

- Controller hook: `src/deepagents_backend/controller_graph.py` (`git_sync` node)
- GitLab integration: `src/gitlab/config.py`, `src/gitlab/client.py`, `src/gitlab/integration.py`, `src/gitlab/sync.py`
- Git runs in the **agent container**, not in the sandbox (token stays out of the sandbox)
- Local clones are cached under `AMICABLE_GIT_SYNC_CACHE_DIR` (default `/tmp/amicable-git-cache`)

QA command selection:

- Reads `/app/package.json` from the sandbox.
- Runs scripts if present:
  - `npm run -s lint` (if script exists)
  - `npm run -s typecheck`
  - `npm run -s build`
  - tests are off by default (opt-in via env)

Relevant env vars:

- `DEEPAGENTS_QA` (enable/disable; defaults to `DEEPAGENTS_VALIDATE` for backwards compatibility)
- `DEEPAGENTS_QA_COMMANDS` (CSV override)
- `DEEPAGENTS_QA_TIMEOUT_S` (default `600`)
- `DEEPAGENTS_QA_RUN_TESTS` (default `0`)
- `DEEPAGENTS_SELF_HEAL_MAX_ROUNDS` (default `2`)

### HITL (Human-in-the-loop)

The DeepAgents controller graph is compiled with a checkpointer, so HITL pauses can be resumed.

Default guards:
- destructive shell deletes (e.g. `rm`, `git clean`, `find -delete`) require approval
- destructive DB ops (`db_drop_table`, `db_truncate_table`) require approval

You can additionally enable HITL for arbitrary tools by setting:
- `DEEPAGENTS_HITL_INTERRUPT_ON_JSON='{"execute": true, "write_file": true}'`

### How QA Works

The QA node runs inside the sandbox after DeepAgents applies changes:

1. Read `/app/package.json`
2. If scripts exist, run (in order):
   - `npm run -s lint`
   - `npm run -s typecheck`
   - `npm run -s build`
   - `npm run -s test` only when `DEEPAGENTS_QA_RUN_TESTS=1`

You can override the command list with:

- `DEEPAGENTS_QA_COMMANDS="npm run -s lint,npm run -s build"`

## Kubernetes Sandbox (agent-sandbox)

Sandbox lifecycle is handled by the agent via the SandboxClaim CRD:

- `src/sandbox_backends/k8s_backend.py`
  - deterministic claim name: `amicable-<sha8(session_id)>`
  - waits for the `Sandbox` resource to become Ready
  - constructs preview URL: `https://<claim>.<PREVIEW_BASE_DOMAIN>/`

The sandbox pod runs `k8s/images/amicable-sandbox/runtime.py`, which exposes:

- `POST /exec` and `POST /execute`: run commands (argv via `shlex.split`)
- `GET /download/{path}`: fetch file bytes
- `POST /write_b64`: write file bytes
- `GET /list`: list project files

The agent talks to the sandbox runtime directly over cluster DNS:

- `http://<claim>.<namespace>.svc.cluster.local:8888`

## Preview Routing

The preview-router is nginx with a wildcard ingress:

- It extracts the `<sandbox-id>` from the hostname and proxies to:
  - `http://<sandbox-id>.<namespace>.svc.cluster.local:3000`

Config:

- `deploy/helm/amicable/templates/preview-router/configmap.yaml`

## Deploy / Helm Layout

Helm chart:

- `deploy/helm/amicable/`

Templates include:

- agent Deployment + Service + Ingress
- preview-router Deployment + Service + Ingress + ConfigMap
- sandbox SandboxTemplate CRD
- optional editor Deployment + Service + Ingress + ConfigMap

## Local Development

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend reads runtime config from `frontend/public/config.js` (or the injected `/config.js` in nginx deployments).

### Agent (local)

Local agent dev is possible, but requires:

- access to the cluster (kubeconfig/in-cluster)
- SandboxClaim/Sandbox CRDs installed

For quick iteration on Python code, you can run unit tests:

```bash
pytest
python3 -m compileall -q src
```

Note: some tests are skipped if `deepagents` isn't installed in your local Python environment; the production image includes it.

## Security Notes

- The browser must not receive real secrets; only public runtime config is injected into the editor.
- When Google OAuth is enabled, WS access is gated by the session cookie.
- The DeepAgents backend is wrapped by a deny-list policy (e.g., deny editing `/src/main.tsx`, deny dangerous shell patterns).
