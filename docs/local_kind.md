# Local Development On kind (Kubernetes)

This repo is designed to run the full Amicable stack on Kubernetes:

- **Agent** (FastAPI WebSocket server) provisions a per-session sandbox and drives DeepAgents editing.
- **Sandboxes** (agent-sandbox `SandboxClaim` + `SandboxTemplate`) run the workspace and expose:
  - runtime API on `:8888`
  - preview server on `:3000` (Vite/Next/etc)
- **Preview router** (nginx) provides `http(s)://<sandbox-id>.<PREVIEW_BASE_DOMAIN>/` for the iframe preview.
- **Editor** is a React SPA (optional; can also run locally via Vite).

For local development we use **kind**, because the system depends on Kubernetes CRDs (`SandboxTemplate`, `SandboxClaim`) from `kubernetes-sigs/agent-sandbox`.

## What You Can Run Locally

Two useful modes:

1. **All-in-kind (recommended)**: agent + preview-router + editor + sandboxes all run in the cluster. This matches production the most closely.
2. **Hybrid**: run the editor and/or agent locally, but still provision sandboxes in kind. This is useful for debugging with local IDE tooling.

Isolation options for sandboxes:

- **Plain runc**: simplest and works everywhere.
- **gVisor**: realistic local isolation and supported by agent-sandbox via `runtimeClassName: gvisor`. The agent-sandbox docs include a gVisor guide and use `RuntimeClass` to select it.
- **Kata containers**: possible in some environments but usually not practical with kind on macOS/Windows; the agent-sandbox Kata guide assumes a VM-based setup with nested virtualization.

References:

- agent-sandbox install + extensions: `manifest.yaml` and `extensions.yaml` in releases on GitHub.
- agent-sandbox gVisor guide shows using `runtimeClassName: gvisor`.
- gVisor docs show how to install `runsc` and configure containerd, and how to create a `RuntimeClass` with handler `runsc`.

## Prerequisites

- `docker` (Docker Desktop is fine)
- `kind`, `kubectl`, `helm`
- A local ingress controller (recommended: `ingress-nginx`)

Important: Amicable preview URLs do not include a port, so the easiest local setup maps host port **80** to your ingress controller.

## 1) Create a kind Cluster (with port 80/443 mapped)

Create `kind-config.yaml`:

```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    extraPortMappings:
      - containerPort: 80
        hostPort: 80
        protocol: TCP
      - containerPort: 443
        hostPort: 443
        protocol: TCP
```

Create the cluster:

```bash
kind create cluster --name amicable --config kind-config.yaml
kubectl cluster-info
```

If binding to port 80 is not possible on your machine, you can still proceed, but you will need to change how preview URLs are routed (code change) or add a host-level proxy that listens on `:80` and forwards to your chosen port.

## 2) Install an Ingress Controller

Install `ingress-nginx` (example):

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
kubectl -n ingress-nginx rollout status deploy/ingress-nginx-controller
```

## 3) Install agent-sandbox (CRDs + controller + extensions)

Install from an agent-sandbox release (recommended). You need **both** core and extensions:

```bash
export VERSION="vX.Y.Z"   # pick a real tag from kubernetes-sigs/agent-sandbox releases
kubectl apply -f https://github.com/kubernetes-sigs/agent-sandbox/releases/download/${VERSION}/manifest.yaml
kubectl apply -f https://github.com/kubernetes-sigs/agent-sandbox/releases/download/${VERSION}/extensions.yaml
```

Verify the CRDs exist:

```bash
kubectl get crd | rg -i 'sandbox|sandboxclaim|sandboxtemplate' || true
```

## 4) (Optional) Enable gVisor for sandbox pods

Amicable can run with the default runtime, but if you want sandbox isolation closer to production you can use gVisor.

What needs to happen:

1. Install `runsc` and `containerd-shim-runsc-v1` into each kind node.
2. Configure containerd in the node to add a `runsc` runtime handler.
3. Create a `RuntimeClass` named `gvisor` that uses handler `runsc`.
4. Set `runtimeClassName: gvisor` in your SandboxTemplate(s).

Notes:

- On kind, “nodes” are Docker containers, so you typically install gVisor by `docker exec` into each node container and updating `/etc/containerd/config.toml`, then restarting containerd.
- Kata containers typically require nested virtualization (`/dev/kvm`) and are therefore not a good fit for Docker Desktop based kind clusters.

### 4.1 Create RuntimeClass

After containerd is configured with a `runsc` handler, apply:

```yaml
apiVersion: node.k8s.io/v1
kind: RuntimeClass
metadata:
  name: gvisor
handler: runsc
```

### 4.2 Use it from SandboxTemplate

Set `runtimeClassName: gvisor` in the sandbox pod spec.

In this repo:

- Helm: `deploy/helm/amicable/values.yaml` supports `sandboxTemplate.runtimeClassName` and per-template `runtimeClassName`.
- Raw YAML: add `runtimeClassName: gvisor` under the SandboxTemplate pod spec in `k8s/sandbox-template.yaml`.

## 5) Build images and load them into kind

Build (pick what you need; below is the minimal “Vite sandbox” path):

```bash
docker build -t amicable-agent:dev k8s/images/amicable-agent
docker build -t amicable-editor:dev k8s/images/amicable-editor
docker build -t amicable-sandbox-lovable-vite:dev k8s/images/amicable-sandbox-lovable-vite
```

Load into kind:

```bash
kind load docker-image amicable-agent:dev amicable-editor:dev amicable-sandbox-lovable-vite:dev --name amicable
```

On Apple Silicon you may need `docker buildx` to ensure your images match the kind node architecture.

## 6) Deploy Amicable via Helm (kind values)

This repo provides `deploy/helm/amicable/values.kind.yaml`, which:

- uses `*.127.0.0.1.nip.io` hostnames (no `/etc/hosts` edits)
- disables TLS
- disables GitLab sync requirement
- deploys only the Vite sandbox template by default

Create the agent secret (dummy values are OK for local dev if you are not using those providers):

```bash
kubectl create namespace amicable
kubectl -n amicable create secret generic amicable-agent-secrets \
  --from-literal=OPENAI_API_KEY="dummy" \
  --from-literal=GITLAB_TOKEN="dummy" \
  --dry-run=client -o yaml | kubectl apply -f -
```

Install:

```bash
helm upgrade --install amicable ./deploy/helm/amicable \
  -n amicable --create-namespace \
  -f ./deploy/helm/amicable/values.kind.yaml
```

## 7) Use the stack locally

With the defaults in `values.kind.yaml`:

- Editor: `http://editor.127.0.0.1.nip.io/`
- Agent (WS): `ws://agent.127.0.0.1.nip.io/`
- Preview URL format: `http://<sandbox-id>.preview.127.0.0.1.nip.io/`

If you create a project, the agent will provision a SandboxClaim and return the preview URL for the iframe.

## Hybrid dev (optional)

### Run the editor locally (faster UI iteration)

Run:

```bash
cd frontend
VITE_AGENT_WS_URL="ws://agent.127.0.0.1.nip.io/" npm run dev
```

### Run the agent locally (debugging)

You can run the agent on your host and still provision sandboxes in kind, because the K8s backend loads kubeconfig when not in-cluster.

Set:

```bash
export SANDBOX_BACKEND=k8s
export K8S_SANDBOX_NAMESPACE=amicable
export PREVIEW_BASE_DOMAIN=preview.127.0.0.1.nip.io
export PREVIEW_SCHEME=http
export K8S_SANDBOX_TEMPLATE_NAME=amicable-sandbox-lovable-vite
```

Then start the agent (see `docs/kubernetes.md` and `CLAUDE.md` for run commands). You still need the preview-router ingress in kind so the browser can reach the sandbox preview servers via wildcard hosts.

## Troubleshooting

- Preview is blank / 404:
  - Check the preview-router ingress and that host matches `*.preview.127.0.0.1.nip.io`.
  - Ensure `PREVIEW_BASE_DOMAIN` matches the preview-router config (Helm uses `agent.env.previewBaseDomain`).
- SandboxClaim stuck:
  - `kubectl -n amicable get sandboxclaims,sandboxes`
  - `kubectl -n amicable describe sandboxclaim <id>`
  - `kubectl -n amicable describe sandbox <id>`
- WebSocket issues (HMR / Vite):
  - Ensure SandboxTemplate sets `__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS` to include your preview base domain (leading dot).
- gVisor pods fail to start:
  - Validate containerd has a `runsc` runtime handler and the `RuntimeClass gvisor` exists.
  - Try running a test pod with `runtimeClassName: gvisor` outside agent-sandbox first.

## References

- agent-sandbox releases (install `manifest.yaml` + `extensions.yaml`): https://github.com/kubernetes-sigs/agent-sandbox/releases
- agent-sandbox gVisor guide: https://docs.agentsandbox.dev/guides/gvisor/
- agent-sandbox Kata guide: https://docs.agentsandbox.dev/guides/kata/
- gVisor installation (binaries + `containerd-shim-runsc-v1`): https://gvisor.dev/docs/user_guide/install/
- gVisor with containerd (add `runsc` runtime + create RuntimeClass): https://gvisor.dev/docs/user_guide/containerd/quick_start/
