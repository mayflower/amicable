import { Hono } from "hono";
import { serve } from "@hono/node-server";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
const app = new Hono();
// Swagger UI assets are served from the locally installed `swagger-ui-dist`
// package so the sandbox doesn't depend on outbound internet access.
const require = createRequire(import.meta.url);
const swaggerUiDist = require("swagger-ui-dist");
const swaggerUiDistDir = swaggerUiDist.getAbsoluteFSPath();
function serveSwaggerAsset(filename, contentType) {
    return (c) => {
        const p = path.join(swaggerUiDistDir, filename);
        const buf = readFileSync(p);
        return c.body(buf, 200, { "content-type": contentType });
    };
}
const openapi = {
    openapi: "3.0.3",
    info: {
        title: "Amicable Hono Sandbox API",
        version: "1.0.0",
        description: "OpenAPI for the Hono sandbox. Update /openapi.json when you add new routes.",
    },
    paths: {
        "/healthz": {
            get: {
                summary: "Health check",
                responses: {
                    "200": {
                        description: "OK",
                        content: {
                            "application/json": {
                                schema: {
                                    type: "object",
                                    properties: { status: { type: "string" } },
                                    required: ["status"],
                                },
                            },
                        },
                    },
                },
            },
        },
        "/actions/echo": {
            post: {
                summary: "Example Hasura Action: echo request body",
                requestBody: {
                    required: false,
                    content: {
                        "application/json": {
                            schema: { type: "object", additionalProperties: true },
                        },
                    },
                },
                responses: {
                    "200": {
                        description: "Echo response",
                        content: {
                            "application/json": {
                                schema: {
                                    type: "object",
                                    properties: {
                                        ok: { type: "boolean" },
                                        input: { type: "object", additionalProperties: true },
                                    },
                                    required: ["ok", "input"],
                                },
                            },
                        },
                    },
                },
            },
        },
        "/events/log": {
            post: {
                summary: "Example Hasura Event Trigger: log request body",
                requestBody: {
                    required: false,
                    content: {
                        "application/json": {
                            schema: { type: "object", additionalProperties: true },
                        },
                    },
                },
                responses: {
                    "200": {
                        description: "OK",
                        content: {
                            "application/json": {
                                schema: {
                                    type: "object",
                                    properties: { ok: { type: "boolean" } },
                                    required: ["ok"],
                                },
                            },
                        },
                    },
                },
            },
        },
    },
};
app.get("/healthz", (c) => c.json({ status: "ok" }));
app.get("/openapi.json", (c) => c.json(openapi));
app.get("/docs", (c) => {
    return c.html(`<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>API Docs (Swagger UI)</title>
    <link rel="stylesheet" href="/docs/swagger-ui.css" />
    <style>
      body { margin: 0; }
      .topbar-wrapper img { display: none; }
    </style>
  </head>
  <body>
    <div id="swagger-ui"></div>
    <script src="/docs/swagger-ui-bundle.js"></script>
    <script src="/docs/swagger-ui-standalone-preset.js"></script>
    <script>
      window.onload = () => {
        window.ui = SwaggerUIBundle({
          url: "/openapi.json",
          dom_id: "#swagger-ui",
          presets: [
            SwaggerUIBundle.presets.apis,
            SwaggerUIStandalonePreset
          ],
          layout: "StandaloneLayout",
        });
      };
    </script>
  </body>
</html>`);
});
// Support both `/docs` and `/docs/` (some routers/proxies normalize differently).
app.get("/docs/", (c) => c.redirect("/docs"));
// Minimal Swagger UI static assets.
app.get("/docs/swagger-ui.css", serveSwaggerAsset("swagger-ui.css", "text/css; charset=utf-8"));
app.get("/docs/swagger-ui-bundle.js", serveSwaggerAsset("swagger-ui-bundle.js", "application/javascript; charset=utf-8"));
app.get("/docs/swagger-ui-standalone-preset.js", serveSwaggerAsset("swagger-ui-standalone-preset.js", "application/javascript; charset=utf-8"));
// Optional but some Swagger UI builds reference this.
app.get("/docs/oauth2-redirect.html", serveSwaggerAsset("oauth2-redirect.html", "text/html; charset=utf-8"));
app.get("/amicable-db.js", (c) => {
    // Serve the injected file if present; otherwise serve a safe stub so the
    // container is "pre-wired" even before injection runs.
    try {
        const js = readFileSync("./amicable-db.js", "utf8");
        return c.body(js, 200, { "content-type": "application/javascript" });
    }
    catch {
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
      <p>API docs: <a href="/docs"><code>/docs</code></a> (Swagger UI)</p>
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
