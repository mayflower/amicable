import { Hono } from "hono";
import { serve } from "@hono/node-server";

const app = new Hono();

app.get("/healthz", (c) => c.json({ status: "ok" }));

app.get("/", (c) => {
  return c.html(`<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>Amicable Hono Template</title>
    <style>
      body { font-family: ui-sans-serif, system-ui; padding: 24px; }
      code { background: #00000010; padding: 2px 6px; border-radius: 6px; }
      .card { border: 1px solid #00000020; border-radius: 12px; padding: 16px; max-width: 820px; }
    </style>
  </head>
  <body>
    <h1>Hono Webhook Service</h1>
    <div class="card">
      <p>This sandbox runs a Hono server on <code>:3000</code>.</p>
      <ul>
        <li><code>GET /healthz</code></li>
        <li><code>POST /actions/echo</code> (Hasura Action example)</li>
        <li><code>POST /events/log</code> (Hasura Event Trigger example)</li>
      </ul>
    </div>
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
