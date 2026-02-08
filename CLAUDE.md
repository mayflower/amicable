# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Summary

Amicable is an AI-powered web app builder. Users interact with a React editor UI that communicates over WebSockets with a Python agent service. The agent edits files in an isolated Kubernetes sandbox and the user sees live previews via a Vite dev server.

## Build & Run Commands

### Python backend
```bash
pip install -r requirements.txt
pytest                              # run all tests
pytest tests/test_deepagents_qa.py  # run a single test file
pytest -k test_name                 # run a single test by name
python3 -m compileall -q src        # quick syntax check
ruff check src/                     # lint
ruff format src/                    # format (black-compatible)
```

### Frontend
```bash
cd frontend
npm install
npm run dev                         # Vite dev server (localhost:5173)
npm run build                       # TypeScript + Vite production build
npm run lint                        # ESLint
```

### Docker images (CI builds via GitHub Actions)
Three images: `amicable-agent`, `amicable-sandbox`, `amicable-editor`. Dockerfiles are in `k8s/images/`. CI workflow: `.github/workflows/build-images.yml`.

## Architecture

```
Browser (Editor SPA)
    ↓ WebSocket
Agent (FastAPI/Uvicorn)
    ↓ HTTP (cluster DNS)
Sandbox Pod (K8s SandboxClaim)
    ├─ Runtime API :8888 (file I/O + shell exec)
    └─ Vite Dev Server :3000 (live preview)
```

### Key source paths

- `src/runtimes/ws_server.py` — FastAPI app, WebSocket endpoints (`/`, `/ws`), health (`/healthz`), OAuth (`/auth/*`)
- `src/agent_core.py` — `Agent` class: session lifecycle, message streaming
- `src/deepagents_backend/controller_graph.py` — outer LangGraph: DeepAgents edit → QA validate → self-heal loop
- `src/deepagents_backend/qa.py` — deterministic QA (lint/typecheck/build in sandbox)
- `src/deepagents_backend/k8s_runtime_backend.py` — adapts sandbox runtime API to DeepAgents backend protocol
- `src/deepagents_backend/policy.py` — deny-list security wrapper (path + command filtering, audit logs)
- `src/deepagents_backend/dangerous_ops_hitl.py` — HITL for destructive shell deletes
- `src/deepagents_backend/dangerous_db_hitl.py` — HITL for destructive DB operations (drop/truncate)
- `src/sandbox_backends/k8s_backend.py` — K8s SandboxClaim lifecycle (create/wait/URL)
- `k8s/images/amicable-sandbox/runtime.py` — sandbox runtime API (POST /exec, POST /write_b64, GET /download)
- `frontend/src/screens/Create/index.tsx` — main editor screen
- `frontend/src/hooks/useMessageBus.ts` — WebSocket connection management
- `frontend/src/services/websocketBus.ts` — WebSocket transport
- `frontend/src/types/messages.ts` — message protocol types
- `src/db/*` — Hasura integration: provisioning, JWT minting, proxy helpers, sandbox injection, DeepAgents DB tools

### Agent engine

The agent uses DeepAgents (LangGraph-based) with filesystem + shell tools. Wrapped by a controller graph that runs deterministic QA and self-heals on failures (up to `DEEPAGENTS_SELF_HEAL_MAX_ROUNDS`).

### Controller graph (QA + self-healing)

The outer LangGraph in `controller_graph.py` orchestrates:
1. `deepagents_edit` — runs DeepAgents to implement changes
2. `qa_validate` — reads `/app/package.json` from sandbox, runs available npm scripts (`lint`, `typecheck`, `build`)
3. On failure: `self_heal_message` injects QA output as a new prompt, loops back to step 1
4. Exits after max rounds with failure summary

### WebSocket message protocol

Messages are JSON: `{ "type": "<type>", "data": {...}, "id": "...", "session_id": "..." }`.
Key types: `init`, `user`, `agent_partial`, `agent_final`, `update_file`, `update_in_progress`, `update_completed`, `load_code`, `ping`.
Trace types: `trace_event` (tool start/end/error, optional tool explanations, and a sidecar reasoning summary).
HITL types: `hitl_request`, `hitl_response`.

### Sandbox naming

SandboxClaim names are deterministic: `amicable-<sha256(session_id)[:8]>`. Preview URLs: `https://<claim>.<PREVIEW_BASE_DOMAIN>/`.

## Configuration

### Agent env vars
- `DEEPAGENTS_MODEL` — LLM model string
- `AUTH_MODE` — `none`, `token`, or `google`
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SESSION_SECRET` — for OAuth
- `PUBLIC_BASE_URL` — OAuth callback URL base
- `CORS_ALLOW_ORIGINS`, `AUTH_REDIRECT_ALLOW_ORIGINS` — allowlists
- `K8S_SANDBOX_NAMESPACE`, `K8S_SANDBOX_TEMPLATE_NAME`
- `PREVIEW_BASE_DOMAIN`, `PREVIEW_SCHEME`
- `DEEPAGENTS_QA`, `DEEPAGENTS_QA_TIMEOUT_S`, `DEEPAGENTS_QA_COMMANDS`, `DEEPAGENTS_QA_RUN_TESTS`
- `DEEPAGENTS_SELF_HEAL_MAX_ROUNDS` (default 2)
- `DEEPAGENTS_MEMORY_SOURCES` (default `"/AGENTS.md,/.deepagents/AGENTS.md"`)
- `DEEPAGENTS_SKILLS_SOURCES` (default `"/.deepagents/skills,/skills"`)
- `DEEPAGENTS_MODEL_RETRY_MAX_RETRIES` (default `2`)
- `DEEPAGENTS_TOOL_RETRY_MAX_RETRIES` (default `2`)
- `DEEPAGENTS_HITL_INTERRUPT_ON_JSON` (default `{}`)
- `AMICABLE_TRACE_NARRATOR_ENABLED` (default `false`) — enable short tool explanations (sidecar)
- `AMICABLE_TRACE_NARRATOR_MODEL` (default `anthropic:claude-haiku-4-5`)
- `AMICABLE_TRACE_NARRATOR_MAX_CHARS` (default `280`)
- `AMICABLE_LANGGRAPH_DATABASE_URL` — Postgres DSN for LangGraph `PostgresStore` (DeepAgents long-term memory via `/memories/`). Falls back to `LANGGRAPH_DATABASE_URL` or `DATABASE_URL`.
  - Also used for LangGraph Postgres checkpointing (HITL resume across agent restarts) when `langgraph-checkpoint-postgres` is installed.

### Hasura DB (optional)
- `HASURA_BASE_URL`
- `HASURA_SOURCE_NAME` (default `default`)
- `HASURA_GRAPHQL_ADMIN_SECRET`
- `HASURA_GRAPHQL_JWT_SECRET` (HS256 config JSON)
- `AMICABLE_PUBLIC_BASE_URL` (defaults to `PUBLIC_BASE_URL` if unset)
- `AMICABLE_DB_PROXY_ORIGIN_MODE` (default `strict_preview`)

### Frontend env vars
- `VITE_AGENT_WS_URL` — agent WebSocket URL
- `VITE_AGENT_TOKEN` — auth token (optional; not needed with Google OAuth)
- Runtime override via `window.__AMICABLE_CONFIG__` in `frontend/public/config.js`

### GitLab Persistence (optional)
- `GITLAB_BASE_URL` (default `https://git.mayflower.de`)
- `GITLAB_GROUP_PATH` (default `amicable`)
- `GITLAB_TOKEN` (required)
- `AMICABLE_GIT_SYNC_ENABLED` (default: enabled iff `GITLAB_TOKEN` is set)
- `AMICABLE_GIT_SYNC_BRANCH` (default `main`)
- `AMICABLE_GIT_SYNC_CACHE_DIR` (default `/tmp/amicable-git-cache`)
- `AMICABLE_GIT_SYNC_EXCLUDES` (CSV override; defaults include `node_modules/`, `.env*`, build caches)
- `AMICABLE_GITLAB_REPO_VISIBILITY` (default `internal`)
- `AMICABLE_GIT_COMMIT_AUTHOR_NAME` (default `amicable-bot`)
- `AMICABLE_GIT_COMMIT_AUTHOR_EMAIL` (default `amicable@mayflower.de`)

## Code Style

- **Python**: ruff (line-length 88, rules: E/F/I/W/B/C4/UP/N/ARG/SIM/TCH/Q/RUF). Config in `pyproject.toml`.
- **Frontend**: ESLint + TypeScript. Tailwind CSS + shadcn/ui components. Path alias `@/*` for imports.
- **Python 3.12+**, **Node 20+**, **React 19**, **Vite 7**.

## Testing

Python tests are in `tests/`. The `conftest.py` adds the repo root to `sys.path` so tests can import `src/`. Some tests are skipped if `deepagents` isn't installed locally (production image includes it).

## Deployment

- Helm chart: `deploy/helm/amicable/`
- ArgoCD manages deploys to the Mayflower data-cluster
- Mayflower-specific values live in the separate `data-cluster` repo
- Debugging runbook: `docs/debugging.md`

## GitLab Integration (source paths)

- `src/gitlab/config.py` — env var parsing/defaults
- `src/gitlab/client.py` — GitLab REST API client
- `src/gitlab/integration.py` — ensure repo exists + rename/move repo on project rename
- `src/gitlab/sync.py` — sandbox snapshot export + git commit/push logic
