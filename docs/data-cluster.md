# Deploying on Mayflower data-cluster (Traefik + ArgoCD)

This note is specific to the existing Mayflower Kubernetes setup in `../data-cluster` and ArgoCD app definitions in `../argocd`.

## Existing cluster facts (from `../data-cluster`)

- Ingress controller: **Traefik** (`ingressClassName: traefik`)
- Cert-manager cluster issuers:
  - Internal: `letsencrypt-intern-dns` (typically for `*.data.mayflower.zone`)
  - Public: `letsencrypt` (typically for `*.data.mayflower.tech`)
- agent-sandbox is already installed via ArgoCD from `data-cluster/agent-sandbox`.
  - Core CRD: `agents.x-k8s.io/v1alpha1` (`Sandbox`)
  - Extensions: `extensions.agents.x-k8s.io/v1alpha1` (`SandboxClaim`, `SandboxTemplate`)

## Recommended integration approach

1. Do **not** install agent-sandbox from this repo.
2. Deploy Amicable as a separate ArgoCD Application.
3. Keep sandboxes in a dedicated namespace (recommended: `amicable`) so claims/templates and service DNS are predictable.

## What you need in the cluster

- DNS records:
  - `amicable-agent.data.mayflower.zone` -> Traefik
  - `*.amicable-preview.data.mayflower.zone` -> Traefik
  - `amicable.data.mayflower.zone` -> Traefik (editor UI)
- TLS certificates via cert-manager.

## Manifests to deploy

Amicable is deployed via Helm charts (source repo: `github.com/mayflower/amicable.git`):

- Main chart: `deploy/helm/amicable`
- Pre-setup (secrets) chart: `../data-cluster/amicable/charts/pre-setup`

Cluster-specific configuration lives in the `data-cluster` repo:

- Non-secret values: `../data-cluster/amicable/values.yaml`
- Secrets (SOPS-encrypted): `../data-cluster/amicable/charts/pre-setup/values.sops.yaml`

Default assumptions in those values:
- namespace: `amicable`
- agent host: `amicable-agent.data.mayflower.zone`
- preview base domain: `amicable-preview.data.mayflower.zone` (wildcard)
- cert-manager issuer: `letsencrypt-intern-dns`

If you want the public domain (`*.data.mayflower.tech`), adjust the values and the issuer to `letsencrypt`.

## Container images (GHCR)

Images are built by GitHub Actions and published to GHCR:

- `ghcr.io/mayflower/amicable-agent:<tag>`
- `ghcr.io/mayflower/amicable-sandbox:<tag>`
- `ghcr.io/mayflower/amicable-editor:<tag>`

The current data-cluster values default to `:main`.

## Secrets

Create the agent secret in the `amicable` namespace:

- `ANTHROPIC_API_KEY` (required for Kubernetes / DeepAgents default model)
- `OPENAI_API_KEY` (optional; required only if you use OpenAI models)
- Google OAuth (if enabled):
  - `GOOGLE_CLIENT_ID`
  - `GOOGLE_CLIENT_SECRET`
  - `SESSION_SECRET`
- `AGENT_AUTH_TOKEN` (optional; legacy token mode, not recommended for browser-based editor)
- `GITLAB_TOKEN` (optional; enables GitLab-backed project persistence)
- Hasura DB integration (optional):
  - `HASURA_GRAPHQL_ADMIN_SECRET` (Hasura admin secret for metadata + run_sql)
  - `HASURA_GRAPHQL_JWT_SECRET` (Hasura JWT secret JSON, HS256, shared with the agent for signing)

In the data-cluster setup, secrets are managed via SOPS in:
- `../data-cluster/amicable/charts/pre-setup/values.sops.yaml`

Note: the editor’s `VITE_AGENT_*` configuration is not a secret. In Kubernetes we inject it via a mounted `/config.js` file (ConfigMap) so you can change the agent URL without rebuilding the image.

## ArgoCD integration

Your ArgoCD apps in `../argocd` currently reference `../data-cluster` as the source repo.
There are two options:

Option A:
- Mirror the main chart into the `data-cluster` repo and deploy from there (keeps everything in one repo).

Option B (implemented):
- Deploy the main Helm chart directly from GitHub, but keep secrets and environment-specific values in the `data-cluster` repo via SOPS.

This has been implemented in `../argocd` as:
- `../argocd/data-muc/platform-apps/amicable.yaml`

It tracks `main`. For staging/testing, temporarily point `targetRevision` to a branch.
