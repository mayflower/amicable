# Deployment Guide

## Deployment Targets

- Local Kubernetes development with kind.
- Generic Kubernetes clusters with wildcard ingress.
- Mayflower data-cluster (ArgoCD-managed setup).

## Required Platform Capabilities

- Kubernetes cluster with `agent-sandbox` core + extensions.
- Wildcard DNS and ingress for preview hosts.
- TLS certificates for agent/editor/preview domains (recommended).
- Container registry access for agent/editor/sandbox images.

## Container Images

Images are built from `k8s/images/`:

- `amicable-agent`
- `amicable-editor`
- `amicable-sandbox` and template-specific sandbox images

CI workflow:

- `.github/workflows/build-images.yml`

## Helm Deployment (Recommended)

Primary chart:

- `deploy/helm/amicable/`

Key components deployed:

- Agent deployment/service/ingress
- Editor deployment/service/ingress (optional)
- Preview router deployment/service/ingress
- SandboxTemplate resources

## High-Level Rollout Sequence

1. Publish or reference valid image tags.
2. Create namespace and required secrets.
3. Configure values (`agent host`, `preview base domain`, template names, auth settings).
4. Deploy with `helm upgrade --install`.
5. Verify:
   - `/healthz` responds
   - editor can open a session
   - sandbox preview URL resolves

## Production Considerations

- Enable OAuth if multi-user access is required.
- Use explicit CORS and redirect allowlists.
- Store secrets in cluster secret manager or encrypted manifests.
- Decide whether Git sync is required (`AMICABLE_GIT_SYNC_REQUIRED`).
- Keep preview domain routing and TLS wildcard certs aligned.

## Existing Detailed Guides

- [Kubernetes Installation](kubernetes.md)
- [Local kind Setup](local_kind.md)
- [Data-Cluster Notes](data-cluster.md)
