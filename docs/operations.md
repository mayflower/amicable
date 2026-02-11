# Operations Runbook

## Health Checks

- Agent health endpoint: `GET /healthz`
- Auth status endpoint: `GET /auth/me`
- Editor availability: frontend ingress serves the app shell.
- Preview routing: wildcard host resolves to active sandbox previews.

## Standard Operational Checks

1. Confirm deployment status in GitOps/ArgoCD.
2. Inspect agent logs for runtime errors.
3. Inspect preview-router logs for host-routing failures.
4. Validate sandbox claim and sandbox readiness.

## Common Incident Categories

- Session initialization failures.
- WebSocket disconnects/timeouts.
- Preview 404 or unreachable sandbox host.
- Repeated QA/self-heal loops.
- Optional integration failures (GitLab sync, Hasura proxy).

## First-Response Procedure

1. Capture failing `session_id`, project slug, and timestamp.
2. Map `session_id` to sandbox claim and inspect claim/sandbox resources.
3. Check agent logs around initialization and tool execution.
4. Check preview router ingress and wildcard DNS behavior.
5. Identify whether failure is platform, config, or project-code specific.

## Safety and Change Control

- Keep destructive operations behind HITL where needed.
- Restrict CORS and auth redirect allowlists.
- Rotate provider and OAuth secrets through secure channels.
- Keep deployment values and chart changes under code review.

## Related Docs

- [Debugging Deep Dive](debugging.md)
- [Deployment](deployment.md)
- [Configuration](configuration.md)
