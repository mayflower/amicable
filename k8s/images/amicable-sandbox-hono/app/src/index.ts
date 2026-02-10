import { Hono } from "hono";
import { serve } from "@hono/node-server";
import { readFileSync } from "node:fs";

const app = new Hono();

app.get("/healthz", (c) => c.json({ status: "ok" }));

app.get("/amicable-db.js", (c) => {
  // Serve the injected file if present; otherwise serve a safe stub so the
  // container is "pre-wired" even before injection runs.
  try {
    const js = readFileSync("./amicable-db.js", "utf8");
    return c.body(js, 200, { "content-type": "application/javascript" });
  } catch {
    return c.body("window.__AMICABLE_DB__ = window.__AMICABLE_DB__ || null;\n", 200, {
      "content-type": "application/javascript",
    });
  }
});

app.get("/", (c) => {
  return c.html(`<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>Amicable Hono Template</title>
    <script src="/amicable-db.js"></script>
    <style>
      body { font-family: ui-sans-serif, system-ui; padding: 24px; }
      code { background: #00000010; padding: 2px 6px; border-radius: 6px; }
      .card { border: 1px solid #00000020; border-radius: 12px; padding: 16px; max-width: 820px; }
      .ok { color: #0a7a26; font-weight: 600; }
      .bad { color: #b42318; font-weight: 600; }
      pre { background: #00000008; padding: 12px; border-radius: 10px; overflow: auto; }
    </style>
  </head>
  <body>
    <h1>Hono Sandbox</h1>
    <div class="card">
      <p>This sandbox runs a Hono server on <code>:3000</code>.</p>
      <p>Hasura DB proxy status: <span id="db-status">checking...</span></p>
      <pre id="db-details"></pre>
      <ul>
        <li><code>GET /healthz</code></li>
        <li><code>POST /actions/echo</code> (Hasura Action example)</li>
        <li><code>POST /events/log</code> (Hasura Event Trigger example)</li>
      </ul>
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
</html>`);
});

app.post("/actions/echo", async (c) => {
  const body = await c.req.json().catch(() => ({}));
  return c.json({ ok: true, input: body });
});

app.post("/events/log", async (c) => {
  const body = await c.req.json().catch(() => ({}));
  // In real code you would validate the Hasura event trigger payload.
  console.log("hasura_event", JSON.stringify(body).slice(0, 2000));
  return c.json({ ok: true });
});

const port = Number(process.env.PORT || 3000);
const host = process.env.HOST || "0.0.0.0";

console.log(`Starting Hono server on http://${host}:${port}`);

serve({ fetch: app.fetch, port, hostname: host });
