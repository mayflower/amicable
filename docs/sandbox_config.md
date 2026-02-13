# Sandbox Configuration (Templates, Skills, Instructions)

This document explains how Amicable creates Kubernetes sandboxes (agent-sandbox), how templates map to sandbox images, and how the DeepAgents-based agent loads **instructions**, **memory**, and **skills** from inside the sandbox workspace.

If you are looking for a full cluster install guide, start with `docs/kubernetes.md`. This file focuses on the knobs that affect sandbox creation and in-sandbox agent behavior.

## Terms

- **Sandbox**: a per-session Kubernetes workload created by `kubernetes-sigs/agent-sandbox`.
- **SandboxTemplate**: a CRD describing the pod spec to run for a sandbox.
- **SandboxClaim**: a CRD that requests a sandbox from a SandboxTemplate.
- **Preview URL**: `https://<sandbox-id>.<PREVIEW_BASE_DOMAIN>/` (proxies to port `3000` in the sandbox).
- **Runtime API**: `http://<sandbox-id>.<namespace>.svc.cluster.local:8888` (file I/O + `exec`).

## Sandbox Creation Flow (Runtime)

At runtime the agent server creates/uses sandboxes via:

- `src/deepagents_backend/session_sandbox_manager.py`
- `src/sandbox_backends/k8s_backend.py`

High-level flow:

1. Browser connects to the agent (`src/runtimes/ws_server.py`).
2. The agent calls `Agent.init(...)` which calls `_ensure_app_environment(...)` (`src/agent_core.py`).
3. The agent chooses a **template id** (from the request, DB, or a default), maps it to a **Kubernetes SandboxTemplate name**, and calls `SessionSandboxManager.ensure_session(...)`.
4. `K8sAgentSandboxBackend.create_app_environment(...)` creates a `SandboxClaim` (if it doesn’t exist yet) and waits until the corresponding `Sandbox` is `Ready`.
5. The agent returns:
   - `preview_url` (for iframe preview)
   - `runtime_base_url` (internal-only service DNS for DeepAgents tools)

### SandboxClaim naming

SandboxClaim names are deterministic and must be valid K8s DNS labels (`[a-z0-9]([-a-z0-9]*[a-z0-9])?`, max 63 chars).

Implementation: `_dns_safe_claim_name(...)` in `src/sandbox_backends/k8s_backend.py`.

- If a `slug` is provided, it is lowercased and sanitized.
- Otherwise the name falls back to a stable hash:
  - `amicable-<sha256(session_id)[:8]>`

### Preview URL construction

Implementation: `_preview_url(...)` in `src/sandbox_backends/k8s_backend.py`.

The preview URL returned to the frontend is:

```text
<PREVIEW_SCHEME>://<sandbox_id>.<PREVIEW_BASE_DOMAIN>/
```

This must match your preview-router wildcard DNS + ingress configuration (see `docs/kubernetes.md`).

### Runtime API (in-sandbox)

The sandbox container runs a small FastAPI service exposing:

- `POST /exec` (and alias `POST /execute`)
- `GET /list?dir=src`
- `GET /download/<path>`
- `POST /write_b64` (base64 file write)

Reference implementation: `k8s/images/amicable-sandbox/runtime.py` (each template image includes an equivalent `runtime.py`).

Important constraints:

- File access is restricted to `/app` (the runtime rejects path traversal outside `/app`).
- `/exec` executes argv (no shell). The DeepAgents adapter wraps tool commands in `sh -lc ...` so common shell patterns (pipes, `cd`, env var expansion) work as expected (`src/deepagents_backend/k8s_runtime_backend.py`).
- Preview server is started in the background on container start. Default command is `npm run dev ...`, overridable via `AMICABLE_PREVIEW_CMD`.

## Key Environment Variables

### Agent container (K8s backend + preview)

These are consumed by `src/sandbox_backends/k8s_backend.py` and `src/deepagents_backend/session_sandbox_manager.py`:

- `SANDBOX_BACKEND=k8s` (set by Helm)
- `K8S_SANDBOX_NAMESPACE` (namespace for SandboxClaim/Sandbox resources)
- `K8S_SANDBOX_TEMPLATE_NAME` (fallback SandboxTemplate name)
- `PREVIEW_BASE_DOMAIN` (required; used to generate the iframe URL)
- `PREVIEW_SCHEME` (default `https`)
- `SANDBOX_RUNTIME_PORT` (default `8888`)
- `SANDBOX_PREVIEW_PORT` (default `3000`)
- `K8S_SANDBOX_READY_TIMEOUT` (default `180` seconds; sandbox ready wait)

DeepAgents runtime adapter (timeouts and root mapping):

- `SANDBOX_ROOT_DIR` (default `/app`; DeepAgents “public” `/` maps to this)
- `SANDBOX_REQUEST_TIMEOUT_S` (default `60`)
- `SANDBOX_EXEC_TIMEOUT_S` (default `600`)

### Sandbox container (preview process)

- `AMICABLE_PREVIEW_CMD`
  - If set, `runtime.py` uses it to start the preview server.
  - If unset, defaults to `npm run dev -- --host 0.0.0.0 --port 3000`.

For Vite-based templates, the SandboxTemplate typically also sets:

- `__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS=".your-preview-domain.tld"`

This must include your preview base domain (usually with a leading dot) to keep HMR and host checks working through the wildcard router.

## Templates

Templates are defined in two places and must stay in sync:

- Backend: `src/templates/registry.py`
- Frontend: `frontend/src/templates/registry.ts`

### Template ids and default

Backend template ids (and default):

- `vite` (default; renamed from `lovable_vite`)
- `nextjs15`
- `fastapi`
- `hono`
- `remix`
- `nuxt3`
- `sveltekit`
- `laravel`
- `flutter`
- `phoenix`
- `aspnetcore`
- `quarkus`

The backend default is `DEFAULT_TEMPLATE_ID = "vite"` in `src/templates/registry.py`.

### Mapping template id -> SandboxTemplate name

Backend mapping is implemented by `k8s_template_name_for(template_id)` in `src/templates/registry.py`.

- Each template id has a default Kubernetes `SandboxTemplate` name (for example `amicable-sandbox-lovable-vite`).
- You can override mappings without code changes via:

```bash
export AMICABLE_TEMPLATE_K8S_TEMPLATE_MAP_JSON='{"vite":"my-sandbox-template-name"}'
```

This is useful if you want to swap the underlying sandbox image for an existing template id.

Note: the backend still accepts `lovable_vite` as an alias for `vite` for backwards compatibility with existing stored projects and older clients.

### DB injection kind (template behavior)

Each backend `TemplateSpec` also defines a `db_inject_kind` which controls how the agent injects `/amicable-db.js` into the project when Hasura/DB is enabled (see `_ensure_app_environment(...)` in `src/agent_core.py`).

If you add a new template that needs DB injection, you must add a new `db_inject_kind` handler and implement the corresponding injection function(s) in `src/db/sandbox_inject.py`.

## Skills and Instructions (DeepAgents)

Amicable uses DeepAgents to edit the sandbox workspace. The agent is created in `_ensure_deep_agent()` in `src/agent_core.py`.

### Virtual filesystem mapping

DeepAgents tools operate on a “public” filesystem where:

- Public path `/` maps to `SANDBOX_ROOT_DIR` (default `/app`) inside the sandbox container.

So:

- `/src/App.tsx` means `/app/src/App.tsx`
- `/memories/notes.md` means `/app/memories/notes.md`

This mapping is implemented in `src/deepagents_backend/k8s_runtime_backend.py` (`_to_internal(...)`).

### Memory sources (instructions/notes)

The agent loads “memory” from sandbox files (DeepAgents feature):

- Env var: `DEEPAGENTS_MEMORY_SOURCES` (CSV)
- Default: `/AGENTS.md,/.deepagents/AGENTS.md` (see `_deepagents_memory_sources()` in `src/agent_core.py`)

Those files are baked into each sandbox image (see the Dockerfiles in `k8s/images/amicable-sandbox-*/Dockerfile`).

Example (Lovable Vite template):

- `k8s/images/amicable-sandbox-lovable-vite/AGENTS.md` -> `/app/AGENTS.md`
- `k8s/images/amicable-sandbox-lovable-vite/.deepagents/AGENTS.md` -> `/app/.deepagents/AGENTS.md`

Additionally, Amicable ensures a writable project memory directory exists:

- On session init the agent runs: `cd /app && mkdir -p memories`
- This corresponds to `/memories/` in the public FS.

### Skills sources

The agent loads “skills” from directories inside the sandbox (DeepAgents feature):

- Env var: `DEEPAGENTS_SKILLS_SOURCES` (CSV)
- Default: `/.deepagents/skills,/skills` (see `_deepagents_skills_sources()` in `src/agent_core.py`)

Skills are Markdown documents with YAML frontmatter, typically stored as:

```text
/.deepagents/skills/<skill-name>/SKILL.md
```

Example skills shipped in the Lovable Vite sandbox image:

- `k8s/images/amicable-sandbox-lovable-vite/.deepagents/skills/sandbox-basics/SKILL.md`
- `k8s/images/amicable-sandbox-lovable-vite/.deepagents/skills/react-vite-basics/SKILL.md`
- `k8s/images/amicable-sandbox-lovable-vite/.deepagents/skills/hasura-graphql-client/SKILL.md`

Operationally:

- Put template-wide skills into the sandbox image under `/app/.deepagents/skills/`.
- Put project-specific skills into the project workspace under `/app/skills/` (if you persist the repo to Git).
- Override `DEEPAGENTS_SKILLS_SOURCES` if you want different lookup locations.

### System prompt (“agent personality”)

The system prompt that governs model behavior is defined in `src/agent_core.py` as `_DEEPAGENTS_SYSTEM_PROMPT`.

If you want to change global editing rules (format, dependency policy, Tailwind/shadcn preference, etc.), change that prompt.

### Safety: policy + HITL

Before DeepAgents can execute tools against a sandbox, the backend is wrapped by:

- `src/deepagents_backend/policy.py` (`SandboxPolicyWrapper`)
  - Denies writes to certain prefixes by default: `/node_modules/`, `/.git/` (see `_ensure_deep_agent()` in `src/agent_core.py`)
  - Denies commands containing forbidden patterns (catastrophic deletes, reboot, etc.)

In addition, two HITL middlewares can interrupt execution:

- `src/deepagents_backend/dangerous_ops_hitl.py`
  - Intercepts destructive shell operations (`rm`, `unlink`, `git clean`, `find ... -delete`) and requires approval.
- `src/deepagents_backend/dangerous_db_hitl.py`
  - Intercepts destructive DB tool calls (`db_drop_table`, `db_truncate_table`) and requires approval.

## Adding a New Sandbox Template

To add a new project template end-to-end (UI -> sandbox -> agent behavior):

1. Create a sandbox image directory under `k8s/images/amicable-sandbox-<your-template>/`.
2. Ensure the image:
   - has the workspace at `/app`
   - exposes `8888` (runtime API) and `3000` (preview)
   - runs the runtime API on `0.0.0.0:8888`
   - starts the preview server bound to `0.0.0.0:3000` (usually via `AMICABLE_PREVIEW_CMD`)
   - includes default memory/skill files:
     - `/app/AGENTS.md`
     - `/app/.deepagents/AGENTS.md`
     - `/app/.deepagents/skills/**`
3. Deploy a corresponding `SandboxTemplate` in your cluster:
   - via Helm: `deploy/helm/amicable/values.yaml` (`sandboxTemplates:` list)
   - or raw YAML: `k8s/sandbox-template.yaml`
   - Note: the SandboxTemplate CRD schema has differed across agent-sandbox versions (`podTemplate` vs `podTemplateSpec`). Use the examples in this repo as the starting point that matches the expected API group `extensions.agents.x-k8s.io/v1alpha1`.
4. Update backend registry:
   - `src/templates/registry.py` (add `TemplateId` + `TemplateSpec`)
5. Update frontend registry:
   - `frontend/src/templates/registry.ts` (add id + label/description)
6. (Optional) If the template needs DB injection:
   - Update `TemplateSpec.db_inject_kind`
   - Implement injection hooks in `src/db/sandbox_inject.py`

If you only want to change which image a template id uses, prefer `AMICABLE_TEMPLATE_K8S_TEMPLATE_MAP_JSON` (no code change).

## Troubleshooting Checklist

- Sandbox never becomes ready:
  - Check `SandboxClaim` and `Sandbox` objects and their conditions/events.
  - Ensure the agent has RBAC to create/read/watch the CRDs in `K8S_SANDBOX_NAMESPACE`.
  - Increase `K8S_SANDBOX_READY_TIMEOUT` if image pulls/build steps are slow.
- Preview URL shows 404 or wrong app:
  - Ensure wildcard DNS and ingress route to preview-router.
  - Ensure preview-router’s host parsing matches `PREVIEW_BASE_DOMAIN` and the namespace matches `K8S_SANDBOX_NAMESPACE`.
  - Ensure the sandbox’s preview server is actually listening on `0.0.0.0:3000`.
- HMR / websocket issues:
  - Set `__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS` in the SandboxTemplate to include your preview base domain (leading dot).
  - Confirm your ingress supports WebSocket upgrade.
- Agent can’t read/write files:
  - Verify runtime API health: `GET /healthz` on port `8888` inside the cluster.
  - Confirm `SANDBOX_ROOT_DIR` matches the sandbox image’s workspace root (`/app` by default).

## Note: Repo-level vs Sandbox-level “AGENTS.md”

This repository also contains `AGENTS.md` and `CLAUDE.md` at the repo root for local coding assistants.

Those are separate from the sandbox image files copied to `/app/AGENTS.md` and `/app/.deepagents/AGENTS.md`.
Only the in-sandbox paths listed in `DEEPAGENTS_MEMORY_SOURCES` are loaded by the running Amicable agent.
