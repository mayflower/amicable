# Debugging and Operations (Amicable)

This is a pragmatic runbook for debugging Amicable in production (Mayflower data-cluster) and during development.

## Quick Facts

- **Agent URL** (HTTP): `https://amicable-agent.data.mayflower.tech/`
- **Editor URL**: `https://amicable.data.mayflower.tech/`
- **Preview wildcard**: `https://<sandbox-id>.amicable-preview.data.mayflower.tech/`
- **ArgoCD app name**: `amicable`
- **Kubernetes namespace**: `amicable`
- **SandboxClaim naming**: `amicable-<sha256(session_id)[:8]>`

## Check Deployment State (ArgoCD)

```bash
argocd app get amicable
argocd app get amicable --refresh
```

To see image tags ArgoCD thinks are deployed:

```bash
argocd app get amicable --refresh -o json | jq '.status.summary.images'
```

## Agent Logs (ArgoCD)

The Helm chart names the agent container `agent` (not `amicable-agent`).

Tail agent logs:

```bash
argocd app logs amicable \
  --kind Deployment --name amicable-agent --namespace amicable \
  -c agent --tail 200
```

Follow logs:

```bash
argocd app logs amicable \
  --kind Deployment --name amicable-agent --namespace amicable \
  -c agent -f --since-seconds 3600
```

Filter for audit/tool usage (DeepAgents policy wrapper logs):

```bash
argocd app logs amicable \
  --kind Deployment --name amicable-agent --namespace amicable \
  -c agent -f --since-seconds 3600 --filter "[audit]"
```

## Preview Router Logs (ArgoCD)

```bash
argocd app logs amicable \
  --kind Deployment --name amicable-preview-router --namespace amicable \
  --tail 200
```

## Editor Logs (ArgoCD)

```bash
argocd app logs amicable \
  --kind Deployment --name amicable-editor --namespace amicable \
  --tail 200
```

## Health and Auth Sanity Checks

Agent health:

```bash
curl -fsS https://amicable-agent.data.mayflower.tech/healthz
```

Auth status:

```bash
curl -fsS https://amicable-agent.data.mayflower.tech/auth/me
```

OAuth redirect sanity (should 302 to Google when configured):

```bash
curl -sS -D- -o /dev/null \
  "https://amicable-agent.data.mayflower.tech/auth/login?redirect=https%3A%2F%2Famicable.data.mayflower.tech%2F" \
  | sed -n '1,30p'
```

## Mapping `session_id` -> SandboxClaim Name

SandboxClaim is deterministic:

```text
claim_name = "amicable-" + sha256(session_id).hexdigest()[:8]
```

Helper snippet:

```bash
python3 - <<'PY'
import hashlib,sys
sid = sys.argv[1]
print("amicable-" + hashlib.sha256(sid.encode("utf-8")).hexdigest()[:8])
PY "PUT_SESSION_ID_HERE"
```

You can also infer the claim name from the preview URL:

```text
https://<claim_name>.amicable-preview.data.mayflower.tech/
```

## DeepAgents QA + Self-Healing: What to Expect in Logs

When a task runs:

1. DeepAgents edits files and runs sandbox commands (logged as `[audit] execute ...` etc).
2. The controller graph runs deterministic QA:
   - reads `/app/package.json`
   - runs `npm run -s lint`, `npm run -s typecheck`, `npm run -s build` if those scripts exist
3. On QA failure:
   - the controller injects a new message containing the failing command output
   - DeepAgents tries a fix and QA runs again
4. After `DEEPAGENTS_SELF_HEAL_MAX_ROUNDS` failures, it returns a final failure summary.

Env vars (agent):
- `DEEPAGENTS_QA` (defaults to `DEEPAGENTS_VALIDATE` for backwards compatibility)
- `DEEPAGENTS_QA_TIMEOUT_S` (default `600`)
- `DEEPAGENTS_QA_RUN_TESTS` (default `0`)
- `DEEPAGENTS_QA_COMMANDS` (CSV override)
- `DEEPAGENTS_SELF_HEAL_MAX_ROUNDS` (default `2`)

## Common Failure Modes

### 0) HITL approval pending

Symptoms:
- UI shows an approval panel
- sending a new user message returns an error: "HITL approval pending"

What to check:
- approve/reject/edit the pending tool call in the UI
- if you refreshed and lost UI state, reconnecting should re-surface `hitl_pending` from the server

### 0.5) Tool trace / Actions tab is empty

Symptoms:
- chat replies appear, but you do not see any tool calls

What to check:
- the agent should emit `trace_event` messages for tool start/end/error
- ensure the frontend build includes the Actions tab updates (image tag matches expected sha)
- note: the agent should also emit a `trace_event` with `phase=reasoning_summary`
- optional: enable short tool explanations by setting `AMICABLE_TRACE_NARRATOR_ENABLED=true` on the agent (`phase=tool_explain`)

### 1) Editor is stuck / no final response

Symptoms:
- you see `update_in_progress` and/or `update_file` messages but no `agent_final`

What to check:
- agent logs for exceptions (ArgoCD logs above)
- ensure the DeepAgents controller is deployed (image tag in ArgoCD includes the expected sha)

### 2) Preview URL 404

Likely causes:
- wildcard DNS not pointing at ingress
- ingress wildcard host misconfigured
- preview router nginx map does not match the host pattern

Checks:
- ArgoCD app resources show `amicable-preview-router` ingress is healthy
- preview router logs show host parsing and proxying attempts

### 3) QA loops repeatedly

Symptoms:
- you see repeated “QA failed, attempting self-heal...”

Checks:
- audit logs show `npm run -s build` output
- set `DEEPAGENTS_QA_COMMANDS` to a smaller set temporarily for faster iteration (e.g. just build)

### 4) DB proxy returns 403/401

If DB is enabled, browser GraphQL calls go to the agent:
- `POST /db/apps/<app_id>/graphql`

Common causes:
- missing `Origin` header (non-browser client)
- origin does not match the expected preview host for that app
- missing/invalid `x-amicable-app-key` (sandbox injection failed or key rotated)

Checks:
- confirm the app preview origin matches `https://amicable-<sha8(app_id)>.<PREVIEW_BASE_DOMAIN>`
- confirm the sandbox has `/app/amicable-db.js`
- check agent env vars: `HASURA_BASE_URL`, `HASURA_GRAPHQL_ADMIN_SECRET`, `HASURA_GRAPHQL_JWT_SECRET`

### 5) GitLab sync fails (best-effort)

Symptoms:
- the run completes normally, but you do not see new commits in GitLab
- agent logs show errors around `git_sync` / snapshot export / `git push`

What to check:
- `GITLAB_TOKEN` is set and has permission to create/push repos in the target group
- GitLab is reachable from the agent pods
- cache dir is writable: `AMICABLE_GIT_SYNC_CACHE_DIR` (default `/tmp/amicable-git-cache`)

Quick toggles:
- disable sync temporarily: `AMICABLE_GIT_SYNC_ENABLED=false`
- change target group/base URL: `GITLAB_GROUP_PATH`, `GITLAB_BASE_URL`

## When You Need `kubectl`

ArgoCD logs cover Deployments managed by the app.

To inspect per-session sandbox pods (created by SandboxClaims), you need Kubernetes cluster access and `kubectl` configured for the cluster (not just local `docker-desktop`):

```bash
kubectl -n amicable get sandboxclaims
kubectl -n amicable get sandboxes
kubectl -n amicable describe sandboxclaim <claim>
kubectl -n amicable describe sandbox <claim>
```
