# WebSocket Connection Failure: Browser → Agent

## Summary

The Amicable editor frontend cannot establish a WebSocket connection to the agent backend. HTTP requests (REST API) to the same agent host work perfectly. The WebSocket connection attempt never reaches the agent server — it silently hangs until the client-side 10s timeout fires.

## Architecture

```
Browser (editor SPA at https://amicable.data.mayflower.zone)
    ↓ fetch() — works ✅
    ↓ new WebSocket() — fails ❌
Agent (FastAPI/Uvicorn at https://amicable-agent.data.mayflower.zone)
    ↓
Traefik v3.3.3 (ingress controller, TLS termination)
    ↓
K8s Service → 2 agent pods (amicable-agent-7d76cfb95c-{5flg9,m599s})
```

## What works

- `GET /healthz` → 200 OK
- `POST /api/projects` → 200 OK (project creation via fetch)
- `GET /api/projects/by-slug/<slug>` → 200 OK
- `GET /auth/me` → 200 OK (Google OAuth session cookie, `credentials: "include"`)
- curl WebSocket upgrade with `--http1.1` through external Traefik → reaches agent (gets 403 without session cookie, as expected)

## What fails

- `new WebSocket('wss://amicable-agent.data.mayflower.zone/')` from the browser
- Connection hangs — no `onopen`, no `onerror`, no `onclose` until the app's 10s timeout fires
- Then `onclose` fires with code 1006 (abnormal closure, no close frame)
- **Zero WebSocket connection attempts appear in agent pod logs** during the failure window
- Agent pods only show healthz checks — no `"WebSocket /" [accepted]` entries

## Key observations

1. **curl with `--http1.1` works**: Forcing HTTP/1.1 via ALPN, the WebSocket upgrade handshake reaches the agent through Traefik and gets a proper response (403 without auth, as expected).

2. **curl without `--http1.1` does NOT do WebSocket**: Default curl negotiates HTTP/2 via ALPN. Over HTTP/2, the `Connection: Upgrade` headers are hop-by-hop and ignored. The request becomes a regular GET that returns `{"status":"ok"}` (the healthz response) with HTTP 200.

3. **Browser uses HTTP/2**: The browser negotiates HTTP/2 with Traefik for `amicable-agent.data.mayflower.zone`. HTTP fetch requests work fine over h2. But `new WebSocket()` requires the HTTP/1.1 upgrade mechanism (`Connection: Upgrade, Upgrade: websocket`), which doesn't exist in HTTP/2.

4. **Agent logs confirm WebSocket worked before**: Earlier in the pod's lifetime (from previous browser sessions, possibly before the pods were restarted), there are hundreds of `"WebSocket /" [accepted]` entries. So the server code is correct.

5. **Attempted TLSOption fix**: Created a Traefik `TLSOption` with `alpnProtocols: [http/1.1]` to force HTTP/1.1 negotiation. curl confirmed it worked (`ALPN: server accepted http/1.1`). But Chrome cached its existing HTTP/2 connection and continued using it. One connection DID get through to the agent during this period (visible in agent logs as `[accepted]` + `connection open`), suggesting the fix is correct but Chrome's HTTP/2 connection pool needs to be flushed.

## Environment

- **Traefik**: v3.3.3 (single pod, handles all ingress)
- **Ingress**: Standard `networking.k8s.io/v1` Ingress with `ingressClassName: traefik`
- **Ingress annotations**: Only `traefik.ingress.kubernetes.io/router.entrypoints: websecure` and `cert-manager.io/cluster-issuer`
- **TLS**: Let's Encrypt cert, TLS 1.3
- **Agent**: FastAPI/Uvicorn, WebSocket endpoints at `/` and `/ws`
- **Browser**: Chrome (current version)
- **Auth**: Google OAuth, session cookie with `SameSite=None; Secure=true`

## Ingress YAML (agent)

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: amicable-agent
  namespace: amicable
  annotations:
    traefik.ingress.kubernetes.io/router.entrypoints: websecure
    cert-manager.io/cluster-issuer: letsencrypt-intern-dns
spec:
  ingressClassName: traefik
  tls:
    - hosts:
        - amicable-agent.data.mayflower.zone
      secretName: amicable-agent-tls
  rules:
    - host: amicable-agent.data.mayflower.zone
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: amicable-agent
                port:
                  number: 80
```

## Questions

1. Does Traefik v3.3.3 support WebSocket over HTTP/2 (RFC 8441 Extended CONNECT)?
2. If not, what's the correct way to force HTTP/1.1 for a specific ingress route so WebSocket works?
3. Why did WebSocket work earlier with the same Traefik config? (Pod restarts? Browser state? TLS session resumption?)
4. Is the TLSOption approach (`alpnProtocols: [http/1.1]`) the right fix, and is Chrome connection pool caching the only reason it appeared to not work?
