# Kubernetes Installation (agent-sandbox)

This guide installs Amicable on Kubernetes using the **kubernetes-sigs/agent-sandbox** CRDs.

For a kind-based local development setup, see `docs/local_kind.md`.

At a high level:
- The **editor UI** is a static React app (built from `frontend/`) served by `amicable-editor`.
- The **agent** is a FastAPI WebSocket server (`src/runtimes/ws_server.py`) that the editor connects to.
- Each editor session provisions a **SandboxClaim** (agent-sandbox) that runs a workspace container.
- A **preview-router** (nginx) provides `https://<sandbox-id>.<PREVIEW_BASE_DOMAIN>/` and proxies HTTP + WebSockets to the sandbox’s Vite dev server.

Without the editor UI, the system is still usable (the agent websocket protocol is public), but the intended usage is: users open the editor in a browser, the editor talks to the agent, and the editor embeds the preview URL returned by the agent.

## 1. Prerequisites

### Cluster
- A Kubernetes cluster where you can install CRDs/controllers.
- `kubectl` configured to point at the cluster.

### agent-sandbox controller + extensions
You must install agent-sandbox **core** and **extensions** (SandboxTemplate/SandboxClaim).

Option A: install from a published release (recommended for remote clusters):

```bash
# In the agent-sandbox repo (or anywhere)
export VERSION="vX.Y.Z"  # pick a real release tag

kubectl apply -f https://github.com/kubernetes-sigs/agent-sandbox/releases/download/${VERSION}/manifest.yaml
kubectl apply -f https://github.com/kubernetes-sigs/agent-sandbox/releases/download/${VERSION}/extensions.yaml
```

Option B: install from source (good for local dev with kind):

```bash
cd ../agent-sandbox
make deploy-kind

kubectl get pods -n agent-sandbox-system
```

### Ingress with wildcard host support
You need an ingress controller that supports:
- wildcard hosts (e.g. `*.preview.example.com`)
- WebSocket proxying (needed for Vite HMR and the agent websocket)

`ingress-nginx` works well.
Traefik also works well (and is used in Mayflower `data-cluster`).

Note (Traefik + TLS + browser WebSockets):
If your Traefik TLS config negotiates **h2-only** via ALPN for the agent host, browser `new WebSocket(wss://...)`
can fail before reaching the agent. Ensure `http/1.1` is offered (or force it per-host with a `TLSOption`).

### DNS + TLS
You need DNS records pointing to your ingress load balancer:
- `editor.<DOMAIN>` (or any chosen host) -> ingress
- `agent.<DOMAIN>` -> ingress (WebSocket)
- `*.preview.<DOMAIN>` -> ingress

For HTTPS, provision TLS certs:
- `editor.<DOMAIN>`
- `agent.<DOMAIN>`
- `*.preview.<DOMAIN>` (wildcard certificate)

If you do not want TLS at first, set `PREVIEW_SCHEME=http` and use an `http://` agent WS URL (development only).
The example ingress YAMLs in `k8s/agent/ingress.yaml` and `k8s/preview-router/ingress.yaml` do not include a `tls:` section; add one for your cluster/issuer.

## 2. Choose Names

Pick these values up front:
- `DOMAIN`: e.g. `example.com`
- `AGENT_HOST`: e.g. `agent.example.com`
- `PREVIEW_BASE_DOMAIN`: e.g. `preview.example.com`
- `SANDBOX_NAMESPACE`: where SandboxClaim/Sandbox objects will be created (default: `default`)

Important: the preview URL returned by the agent will be:

```
https://<sandbox-id>.preview.example.com/
```

## 3. Build and Publish Images

There are three images:

1) Workspace sandbox image (Vite dev server + runtime file API):

```bash
docker build -t <REGISTRY>/amicable-sandbox:<TAG> k8s/images/amicable-sandbox
```

2) Agent image (WebSocket server that provisions SandboxClaims):

```bash
docker build -t <REGISTRY>/amicable-agent:<TAG> k8s/images/amicable-agent
```

3) Editor image (static UI served by nginx):

```bash
docker build -t <REGISTRY>/amicable-editor:<TAG> k8s/images/amicable-editor
```

Push them to a registry your cluster can pull from:

```bash
docker push <REGISTRY>/amicable-sandbox:<TAG>
docker push <REGISTRY>/amicable-agent:<TAG>
docker push <REGISTRY>/amicable-editor:<TAG>
```

If you’re using kind, you can also `kind load docker-image ...` instead of pushing.

### GitHub Actions + GHCR (recommended)

This repo includes a GitHub Actions workflow that builds and publishes all images to GHCR on pushes to `main`:

- `ghcr.io/<org>/amicable-agent:main`
- `ghcr.io/<org>/amicable-sandbox:main`
- `ghcr.io/<org>/amicable-editor:main`

It also publishes immutable tags per commit:

- `ghcr.io/<org>/amicable-agent:sha-<shortsha>`
- `ghcr.io/<org>/amicable-sandbox:sha-<shortsha>`
- `ghcr.io/<org>/amicable-editor:sha-<shortsha>`

If your packages are private, configure an `imagePullSecret` in the namespace where you deploy.

## 4. Install With Helm (recommended)

The Helm chart deploys the full stack:
- `SandboxTemplate` (agent-sandbox extension)
- `amicable-preview-router` (nginx wildcard router for previews)
- `amicable-agent` (WebSocket server) + RBAC
- `amicable-editor` (optional) as a static nginx deployment with runtime config in `/config.js`

1) Create namespace and agent secret:

```bash
kubectl create namespace amicable
kubectl -n amicable create secret generic amicable-agent-secrets \
  --from-literal=ANTHROPIC_API_KEY="..." \
  --from-literal=OPENAI_API_KEY="..." \
  --dry-run=client -o yaml | kubectl apply -f -
```

Notes:
- `ANTHROPIC_API_KEY` is required for the Kubernetes/DeepAgents default model.
- `OPENAI_API_KEY` is only needed if you use OpenAI models. The Helm chart currently wires it by default; setting it to a placeholder value is acceptable if you never use OpenAI providers.

2) Install (agent + preview-router + SandboxTemplate):

```bash
helm upgrade --install amicable ./deploy/helm/amicable \
  --namespace amicable --create-namespace \
  --set sandboxNamespace=amicable \
  --set sandboxTemplate.additionalAllowedHosts=.preview.example.com \
  --set agent.ingress.host=agent.example.com \
  --set agent.env.previewBaseDomain=preview.example.com \
  --set previewRouter.ingress.wildcardHost=\"*.preview.example.com\"
```

3) Enable the editor (optional, but usually what you want):

```bash
helm upgrade --install amicable ./deploy/helm/amicable \
  --namespace amicable --create-namespace --reuse-values \
  --set editor.enabled=true \
  --set editor.ingress.host=editor.example.com \
  --set editor.runtimeConfig.VITE_AGENT_WS_URL=wss://agent.example.com/
```

For more control, prefer a values file instead of many `--set` flags.

## 5. Install With Raw Manifests (optional)

This repo ships example manifests under `k8s/`.

You MUST update these placeholders:

### 5.1 SandboxTemplate
File: `k8s/sandbox-template.yaml`
- set the image to your published workspace sandbox image
- set `__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS` to your wildcard preview domain (leading dot is important)

Note: depending on the agent-sandbox version, `SandboxTemplate` may be under the extensions API group
(`extensions.agents.x-k8s.io/v1alpha1`). The manifests in this repo assume that API group.
Example edits:
- `image: <REGISTRY>/amicable-sandbox:<TAG>`
- `value: ".preview.example.com"`

Apply it:

```bash
kubectl apply -f k8s/sandbox-template.yaml
```

### 5.2 Preview Router
The preview router proxies requests based on the hostname.

Files:
- `k8s/preview-router/deployment.yaml` (contains nginx config)
- `k8s/preview-router/ingress.yaml`

Update:
- `preview.example.com` occurrences to your `PREVIEW_BASE_DOMAIN`
- if your sandboxes are NOT in namespace `default`, update the nginx config map section:
  - change `default default;` mapping to your namespace

Apply:

```bash
kubectl apply -f k8s/preview-router/deployment.yaml
kubectl apply -f k8s/preview-router/service.yaml
kubectl apply -f k8s/preview-router/ingress.yaml
```

### 5.3 Agent
Files:
- `k8s/agent/rbac.yaml`
- `k8s/agent/deployment.yaml`
- `k8s/agent/service.yaml`
- `k8s/agent/ingress.yaml`

Update in `k8s/agent/deployment.yaml`:
- `image: <REGISTRY>/amicable-agent:<TAG>`
- `K8S_SANDBOX_NAMESPACE`
- `PREVIEW_BASE_DOMAIN`
- `PREVIEW_SCHEME` (usually `https`)

Update in `k8s/agent/ingress.yaml`:
- `agent.example.com` -> your `AGENT_HOST`

### 5.4 Editor UI (optional, but recommended)

The editor is the user-facing UI and should usually be deployed in-cluster.

This repo does not ship a raw-manifest editor under `k8s/` yet; the recommended way is Helm (see below).

## 6. Create Secrets

For Kubernetes / DeepAgents mode, the agent uses `ANTHROPIC_API_KEY` by default.
`OPENAI_API_KEY` is optional and only required if you configure models to use OpenAI providers.

Start from the example:
- `k8s/agent/secret.example.yaml`

Apply a real secret:

```bash
# Option A (file): edit the file first to set ANTHROPIC_API_KEY / OPENAI_API_KEY, then:
kubectl apply -f k8s/agent/secret.example.yaml

# Option B (command):
kubectl create secret generic amicable-agent-secrets \\
  --from-literal=ANTHROPIC_API_KEY=\"...\" \\
  --from-literal=OPENAI_API_KEY=\"...\" \\
  --dry-run=client -o yaml | kubectl apply -f -
```

## 7. Optional: Hasura Database Integration

Amicable can expose a per-app database via Hasura through the agent service:

- Browser calls the agent proxy:
  - `POST /db/apps/<app_id>/graphql`
- Agent validates `Origin` and `x-amicable-app-key` and mints short-lived Hasura JWTs.

To enable, set agent env vars:
- `HASURA_BASE_URL`
- `HASURA_SOURCE_NAME` (default `default`)
- `HASURA_GRAPHQL_ADMIN_SECRET` (secret)
- `HASURA_GRAPHQL_JWT_SECRET` (secret JSON, HS256)

And ensure Hasura is configured with the same `HASURA_GRAPHQL_JWT_SECRET`.

## 7. Deploy the Agent

```bash
kubectl apply -f k8s/agent/rbac.yaml
kubectl apply -f k8s/agent/deployment.yaml
kubectl apply -f k8s/agent/service.yaml
kubectl apply -f k8s/agent/ingress.yaml
```

Verify:

```bash
kubectl get pods
kubectl logs deploy/amicable-agent
```

## 8. Deploy the Editor UI (Frontend)

The editor is a static React app built from `frontend/` and served by nginx (in-cluster deployments use the `amicable-editor` image).

There are two supported ways to run the editor:

### 7.1 Deploy the editor in Kubernetes (recommended)

Deploy the Helm chart `deploy/helm/amicable` and enable the editor.

The editor is built as static files and served by nginx. In Kubernetes we inject runtime configuration via a file `/config.js`:
- `frontend/index.html` includes `<script src="/config.js">`
- `frontend/src/config/agent.ts` reads `window.__AMICABLE_CONFIG__` first, then falls back to Vite build-time env vars

Helm renders a ConfigMap `amicable-editor-config` that mounts `config.js` into the nginx container.

Minimal Helm example:

```bash
helm upgrade --install amicable ./deploy/helm/amicable \\
  --namespace amicable --create-namespace \\
  --set sandboxNamespace=amicable \\
  --set agent.ingress.host=agent.example.com \\
  --set agent.env.previewBaseDomain=preview.example.com \\
  --set previewRouter.ingress.wildcardHost=\"*.preview.example.com\" \\
  --set editor.enabled=true \\
  --set editor.ingress.host=editor.example.com \\
  --set editor.runtimeConfig.VITE_AGENT_WS_URL=wss://agent.example.com/
```

Then open:
- `https://editor.example.com/` (editor UI)

### 7.2 Run the editor locally (development)

Set in `frontend/.env`:

```bash
VITE_AGENT_WS_URL=wss://agent.example.com/
```

Then:

```bash
cd frontend
npm install
npm run dev
```

## 9. How It Works (Operational Notes)

### Session -> SandboxClaim
On `INIT`, the agent creates or reconnects to a deterministic SandboxClaim name derived from `session_id`.

### Preview routing
The agent returns:

```
https://<sandbox-id>.<PREVIEW_BASE_DOMAIN>/
```

The preview-router extracts `<sandbox-id>` from the `Host` header and proxies to:

```
http://<sandbox-id>.<SANDBOX_NAMESPACE>.svc.cluster.local:3000
```

This proxy supports WebSockets so Vite HMR works.

### Cleanup
There is no TTL/garbage-collector for sandbox claims.

If Hasura/projects are enabled and you delete a project via the API/UI, the agent performs best-effort sandbox deletion in the background (along with best-effort DB cleanup). Orphans can still exist (agent crash, manual SandboxClaims, etc.).

To clean up manually:

```bash
kubectl get sandboxclaims -A
kubectl delete sandboxclaim -n <namespace> <claim-name>
```

## GitLab Persistence (Optional)

If configured, the agent persists each project to GitLab as a repository and pushes snapshot commits after each controller run.

Behavior:
- Repository: `<GITLAB_BASE_URL>/<GITLAB_GROUP_PATH>/<project-slug>`
- Timing: after QA success or QA failure (end of the controller run)
- Location: git operations run in the **agent container** (not the sandbox)
- Excludes: `node_modules/`, `.env*`, build outputs and common caches (override via `AMICABLE_GIT_SYNC_EXCLUDES`)
- Failure mode: best-effort; failures do **not** block edits or session completion

Required env vars (agent):
- `GITLAB_TOKEN`

Common optional env vars:
- `GITLAB_BASE_URL` (default `https://git.mayflower.de`)
- `GITLAB_GROUP_PATH` (default `amicable`)
- `AMICABLE_GIT_SYNC_BRANCH` (default `main`)
- `AMICABLE_GIT_SYNC_ENABLED` (default: enabled iff token present)

## 10. Troubleshooting

### Agent websocket connects but INIT fails
- Check agent logs: `kubectl logs deploy/amicable-agent`
- RBAC errors mean `k8s/agent/rbac.yaml` wasn’t applied or namespace mismatch.

### Agent websocket never reaches the agent (Traefik + h2-only)
Symptom: `new WebSocket("wss://<agent-host>/")` hangs and times out (e.g. code `1006`), and the agent pod logs show
no `WebSocket / [accepted]` entries during the attempt.

Fix (Traefik): force `http/1.1` ALPN on the agent host.

- Helm: set `agent.ingress.traefik.forceHttp1.enabled=true` (creates a `TLSOption` and annotates the agent `Ingress`).
- Raw YAML: create a `TLSOption` with `spec.alpnProtocols: ["http/1.1"]` and set
  `traefik.ingress.kubernetes.io/router.tls.options: "<tlsoption-name>@kubernetescrd"` on the agent ingress.

### SandboxClaim exists but sandbox never becomes Ready
- Check resources:

```bash
kubectl get sandboxclaims -n <ns>
kubectl get sandboxes -n <ns>
kubectl describe sandboxclaim -n <ns> <name>
kubectl describe sandbox -n <ns> <name>
```

- Confirm your `SandboxTemplate` image is pullable by the cluster and the pod can start.

### Preview URL returns 404
- Verify wildcard DNS and ingress host matches `*.preview.<DOMAIN>`.
- Ensure you updated `k8s/preview-router/deployment.yaml` and `k8s/preview-router/ingress.yaml` to your domain.

### Preview loads but HMR/WebSockets fail
- Ensure your ingress controller supports WebSockets.
- Ensure the preview router nginx config sets `Upgrade`/`Connection` headers (it does by default).
- Ensure the sandbox Vite server allows the host:
  - `__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS` in `k8s/sandbox-template.yaml` should be `".preview.<DOMAIN>"`.

### File edits don’t apply
- The agent talks to the sandbox runtime API at `http://<sandbox-id>.<ns>.svc.cluster.local:8888`.
- Check the sandbox container logs to confirm the runtime API is running.

## 11. QA + Self-Healing (DeepAgents)

In Kubernetes mode the agent can run deterministic QA and self-heal loops after applying edits.

Env vars (agent):
- `DEEPAGENTS_QA`: enable QA (defaults to `DEEPAGENTS_VALIDATE` for backwards compatibility)
- `DEEPAGENTS_QA_TIMEOUT_S`: timeout for the QA step (default `600`)
- `DEEPAGENTS_QA_RUN_TESTS`: enable running `npm test` if a script exists (default `0`)
- `DEEPAGENTS_QA_COMMANDS`: override QA commands (CSV), e.g. `npm run -s lint,npm run -s build`
- `DEEPAGENTS_SELF_HEAL_MAX_ROUNDS`: number of self-heal retries (default `2`)
