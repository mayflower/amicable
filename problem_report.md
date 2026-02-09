# Problem Report: WebSocket Connection Failure on `/p/weather-dashboard`

## Summary

After deploying `sha-375917f` (which fixed the Hasura DDL race condition), WebSocket connections on the deployed Amicable instance appear broken. Server logs show hundreds of rapid "connection open" / "connection closed" cycles with zero error messages in between. The test project at `/p/weather-dashboard` cannot connect.

## Environment

- **Deployed image tag**: `sha-375917f`
- **Agent replicas**: 2 (`amicable-agent-744b8c58f4-knp7g`, `amicable-agent-744b8c58f4-rjn6n`)
- **Editor URL**: `https://amicable.data.mayflower.zone`
- **Agent URL**: `https://amicable-agent.data.mayflower.zone`
- **Auth mode**: `google` (Google OAuth via Starlette SessionMiddleware)
- **Hasura**: enabled (for project metadata persistence)
- **GitLab sync**: enabled

## Observed Symptoms

### 1. Server-side: Rapid open/close loop (no errors)

Both agent pods show the same pattern, hundreds of times:

```
INFO:     10.42.13.88:51120 - "WebSocket /" [accepted]
INFO:     connection open
INFO:     connection closed
INFO:     10.42.13.88:51126 - "WebSocket /" [accepted]
INFO:     connection open
INFO:     connection closed
```

No error, warning, or application log appears between "connection open" and "connection closed". The cycle repeats every ~1-2 seconds. Interleaved with normal health checks (`GET /healthz 200 OK`).

### 2. Client-side: `/p/weather-dashboard` shows "Connect to start building"

The page loads, user is authenticated (name/avatar visible), but the UI shows the pre-connection state with a Connect button. Clicking Connect has no visible effect.

### 3. Slug resolution returns 404

```
GET /api/projects/by-slug/weather-dashboard → {"error": "not_found"}
GET /api/projects                           → {"projects": []}
```

The projects table is **empty** for this user. No projects exist at all.

### 4. Sandbox pod IS running

```
NAME                  READY   STATUS    AGE
weather-dashboard     1/1     Running   32m
```

The K8s sandbox was created successfully. Only the Hasura project metadata is missing.

## Root Cause Analysis

There are **two separate issues** interacting:

### Issue A: Missing project metadata (primary blocker)

The project "Weather Dashboard" was created during a session when the Hasura DDL race condition was active (pre-`375917f`). The creation flow is:

1. `POST /api/projects` (from `/new` page) → calls `create_project()` in `store.py`
2. `create_project()` calls `ensure_projects_schema()` which runs DDL
3. The DDL triggered Hasura metadata version conflicts (409) between the 2 replicas
4. The project row was likely **never inserted** because the DDL call failed before the INSERT

The frontend navigated to `/p/weather-dashboard` via React Router `navigate()` with `routeState` containing the `project_id`. This worked for the initial page load (because `routeState` passed the `project_id` directly). But:

- On any subsequent visit or page refresh, `routeState` is lost
- The frontend falls back to slug resolution: `GET /api/projects/by-slug/weather-dashboard`
- Since the project row doesn't exist, this returns 404
- `resolvedSessionId` stays `null`
- The auto-connect `useEffect` never fires (guarded by `resolvedSessionId` truthy check)
- The Connect button is disabled (`disabled={!resolvedSessionId}`)

**The project was never persisted to the database. The sandbox was created (K8s), but the metadata row in Hasura is missing.**

### Issue B: Silent reconnect loop (secondary / separate clients)

The rapid open/close cycles in server logs come from a **different source** — likely an old browser tab from the earlier debugging session that was stuck in a reconnect loop. The current tab at `/p/weather-dashboard` never attempts a WebSocket connection at all (because `resolvedSessionId` is null).

However, the reconnect behavior reveals a gap in the WebSocket handler's error reporting. When the INIT message processing fails:

```python
# ws_server.py lines 1081-1093
except PermissionError:
    await ws.close(code=1008)       # ← no logging, no error message sent
    return
except Exception as e:
    await ws.send_json(...)          # sends error JSON
    await ws.close(code=1011)
    return
```

The `PermissionError` path closes the connection **silently** — no log, no error message to the client. If a client connects with a session_id that resolves to a project owned by a different user, `ensure_project_for_id()` raises `PermissionError("project belongs to a different user")`, and the connection closes with 1008 and zero diagnostics.

## Recommended Fixes

### Fix 1: Add logging to WebSocket error paths

In `ws_server.py` `_handle_ws()`, add logging before closing:

```python
except PermissionError as e:
    logger.warning("WS INIT PermissionError: %s (session_id=%s)", e, session_id)
    await ws.close(code=1008)
    return
except Exception as e:
    logger.error("WS INIT error: %s (session_id=%s)", e, session_id, exc_info=True)
    await ws.send_json(...)
    await ws.close(code=1011)
    return
```

Also add logging in the bootstrap commit exception handler (lines 1137-1155), which currently has a bare `except Exception: pass` fallback.

### Fix 2: Handle missing project gracefully in `/p/:slug` route

The frontend should show a clear "Project not found" message when the slug resolution returns 404, instead of showing the Connect screen with a silently-disabled button. Currently the `catch` block at line 1114 silently ignores the error.

### Fix 3: Verify project creation atomicity

In `store.py` `create_project()`, the `ensure_projects_schema()` call happens inside the function. If the DDL fails, the INSERT never runs. With the run-once guard now in place (sha-375917f), this should no longer be an issue for new projects. But verify by:

1. Creating a new project from `/new`
2. Checking that `/api/projects` returns it
3. Refreshing the `/p/:slug` page and confirming it reconnects

### Fix 4: Investigate the reconnect loop source

The rapid open/close pattern in server logs should be investigated:

- Check if there are other browser tabs open to the amicable editor
- The WebSocketBus `scheduleReconnect()` will retry up to `maxReconnectAttempts=5` times with exponential backoff. After exhaustion, it stops. But the React auto-connect `useEffect` in `Create/index.tsx` (line 1026-1047) will fire again whenever its dependencies change, potentially restarting the cycle.
- The `useEffect` that initializes the MessageBus (in `useMessageBus.ts` lines 52-98) depends on `[onConnect, onDisconnect, onError]`. These are **inline arrow functions** in `Create/index.tsx` (lines 732-749), creating new references on every render. This causes the MessageBus to be recreated on every render. The `clear()` method only wipes per-type handlers (not config callbacks), so `setConnected()` still reaches React state — but the WebSocketBus holds a reference to an old MessageBus instance after recreation, which could cause state desynchronization.

## Key Files

| File | Relevance |
|------|-----------|
| `src/runtimes/ws_server.py:1028-1167` | WebSocket handler (`_handle_ws`), INIT processing, error handling |
| `src/runtimes/ws_server.py:1004-1025` | `_require_auth` — pre-accept auth check |
| `src/runtimes/ws_server.py:90-101` | `_get_owner_from_ws` — post-accept owner extraction (can raise PermissionError) |
| `src/projects/store.py:338-366` | `create_project()` — project creation with slug allocation |
| `src/projects/store.py:369-401` | `ensure_project_for_id()` — can raise PermissionError for wrong owner |
| `src/projects/store.py:43-78` | `ensure_projects_schema()` — run-once DDL guard (fixed in 375917f) |
| `frontend/src/screens/Create/index.tsx:1093-1119` | Slug resolution effect |
| `frontend/src/screens/Create/index.tsx:1025-1047` | Auto-connect effect |
| `frontend/src/screens/Create/index.tsx:727-750` | useMessageBus call with inline callbacks |
| `frontend/src/hooks/useMessageBus.ts:52-98` | MessageBus initialization effect (dependency issue) |
| `frontend/src/hooks/useMessageBus.ts:100-141` | `connect()` function |
| `frontend/src/services/websocketBus.ts:36-131` | WebSocketBus.connect() — WS lifecycle |
| `frontend/src/services/messageBus.ts:84-87` | `clear()` — only clears handlers map, not config |
| `frontend/src/config/agent.ts` | Runtime config: WS URL from `window.__AMICABLE_CONFIG__` |

## Runtime Config (verified from browser)

```js
window.__AMICABLE_CONFIG__ = {
  VITE_AGENT_WS_URL: "wss://amicable-agent.data.mayflower.zone/",
  VITE_AGENT_TOKEN: ""
}
```

## Immediate Test Plan

1. Navigate to `https://amicable.data.mayflower.zone/` (home/new page)
2. Create a new project — this should work now that the Hasura DDL race is fixed
3. Verify the project appears in `GET /api/projects`
4. Navigate away and back to `/p/:slug` to confirm slug resolution works
5. Verify WebSocket connects and INIT completes
6. Send a prompt and verify agent response

## Previously Fixed (for context)

- **sha-375917f**: Fixed Hasura DDL race condition — `ensure_projects_schema()` now runs once per process with a threading lock, instead of running CREATE TABLE/ALTER TABLE on every database call. This eliminated the 409 metadata version conflicts between replicas.
