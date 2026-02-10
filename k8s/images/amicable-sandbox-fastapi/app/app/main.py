from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.responses import Response
from pydantic import BaseModel

app = FastAPI(title="Amicable FastAPI Template", version="1.0.0")


@app.get("/")
async def root() -> HTMLResponse:
    # Keep this "always works" without relying on any prompting. The agent will
    # inject real DB proxy credentials by overwriting /app/amicable-db.js.
    html = """<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>Amicable FastAPI Template</title>
    <script src="/amicable-db.js"></script>
    <style>
      body { font-family: ui-sans-serif, system-ui; padding: 24px; }
      code { background: #00000010; padding: 2px 6px; border-radius: 6px; }
      .card { border: 1px solid #00000020; border-radius: 12px; padding: 16px; max-width: 900px; }
      .ok { color: #0a7a26; font-weight: 600; }
      .bad { color: #b42318; font-weight: 600; }
      pre { background: #00000008; padding: 12px; border-radius: 10px; overflow: auto; }
      a { color: inherit; }
    </style>
  </head>
  <body>
    <h1>FastAPI Sandbox</h1>
    <div class="card">
      <p>Preview server runs on <code>:3000</code>. API docs at <a href="/docs"><code>/docs</code></a>.</p>
      <p>Hasura DB proxy status: <span id="db-status">checking...</span></p>
      <pre id="db-details"></pre>
    </div>
    <script>
      (async () => {
        const statusEl = document.getElementById("db-status");
        const detailsEl = document.getElementById("db-details");
        const db = window.__AMICABLE_DB__;
        if (!db || !db.graphqlUrl || !db.appKey) {
          statusEl.textContent = "NOT CONFIGURED (missing window.__AMICABLE_DB__)";
          statusEl.className = "bad";
          detailsEl.textContent = "Expected /amicable-db.js to set window.__AMICABLE_DB__.";
          return;
        }

        try {
          const resp = await fetch(db.graphqlUrl, {
            method: "POST",
            headers: {
              "content-type": "application/json",
              "x-amicable-app-key": db.appKey,
            },
            body: JSON.stringify({
              query: "query Introspect { __schema { queryType { name } } }",
            }),
          });
          const text = await resp.text();
          statusEl.textContent = resp.ok ? "OK" : ("ERROR (" + resp.status + ")");
          statusEl.className = resp.ok ? "ok" : "bad";
          detailsEl.textContent = text.slice(0, 4000);
        } catch (e) {
          statusEl.textContent = "ERROR";
          statusEl.className = "bad";
          detailsEl.textContent = String(e);
        }
      })();
    </script>
  </body>
</html>
"""
    return HTMLResponse(content=html, status_code=200)


@app.get("/amicable-db.js")
async def amicable_db_js() -> Response:
    # Serve the injected file if present; otherwise serve a safe stub so the
    # container is "pre-wired" even before injection runs.
    try:
        from pathlib import Path

        p = Path("/app/amicable-db.js")
        if p.exists():
            return Response(
                content=p.read_text(encoding="utf-8", errors="replace"),
                media_type="application/javascript",
            )
    except Exception:
        pass
    return Response(
        content="window.__AMICABLE_DB__ = window.__AMICABLE_DB__ || null;\n",
        media_type="application/javascript",
    )


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


class EchoRequest(BaseModel):
    input: dict | list | str | int | float | bool | None = None


@app.post("/actions/echo")
async def action_echo(req: EchoRequest) -> dict:
    # Hasura Actions typically send JSON; adapt this handler as needed.
    return {"ok": True, "echo": req.input}


class EventTriggerPayload(BaseModel):
    event: dict


@app.post("/events/log")
async def event_log(payload: EventTriggerPayload) -> dict:
    # Hasura Event Triggers post a structured payload.
    # In real code you would validate shape and act accordingly.
    return {"ok": True}
