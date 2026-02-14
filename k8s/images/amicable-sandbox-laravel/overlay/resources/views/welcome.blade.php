<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Amicable Starter</title>
    <style>
      body {
        font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto,
          Helvetica, Arial;
        padding: 24px;
        max-width: 980px;
        margin: 0 auto;
        line-height: 1.4;
      }
      code {
        background: #00000010;
        padding: 2px 6px;
        border-radius: 6px;
      }
      pre {
        background: #00000008;
        padding: 12px;
        border-radius: 10px;
        overflow: auto;
      }
      .card {
        border: 1px solid #00000020;
        border-radius: 12px;
        padding: 16px;
        background: white;
      }
      .ok {
        color: #0a7a2f;
      }
      .warn {
        color: #8a5a00;
      }
      .err {
        color: #b00020;
      }
    </style>
      <script src="/amicable-db.js"></script>
  </head>
  <body>
    <h1 style="margin: 0 0 8px">Build something great</h1>
    <p style="margin: 0 0 16px; opacity: 0.8">
      Start from this scaffold and build your app. Changes appear live in preview.
    </p>

    <details class="card">
      <summary style="cursor: pointer; font-weight: 600">Diagnostics</summary>
      <section style="margin-top: 12px">
        <div><strong>Status:</strong> <span id="status">running</span></div>
        <div style="margin-top: 12px; font-size: 13px; opacity: 0.85">
          <div><code>appId</code>: <span id="appId">(none)</span></div>
          <div><code>graphqlUrl</code>: <span id="graphqlUrl">(none)</span></div>
        </div>
        <pre id="out" style="margin-top: 12px; display: none"></pre>
        <p id="detail" style="margin-top: 12px; display: none"></p>
      </section>
    </details>

    <script>
      (async () => {
        const setText = (id, t) =>
          (document.getElementById(id).textContent = String(t || ""));
        const setClass = (id, cls) =>
          (document.getElementById(id).className = cls || "");
        const show = (id) => (document.getElementById(id).style.display = "");

        const db = window.__AMICABLE_DB__;
        if (!db || !db.graphqlUrl || !db.appKey) {
          setText("status", "disabled");
          setClass("status", "warn");
          setText(
            "detail",
            "DB proxy not configured for this sandbox (missing window.__AMICABLE_DB__)."
          );
          show("detail");
          return;
        }

        setText("appId", db.appId);
        setText("graphqlUrl", db.graphqlUrl);

        try {
          const res = await fetch(db.graphqlUrl, {
            method: "POST",
            headers: {
              "content-type": "application/json",
              "x-amicable-app-key": db.appKey,
            },
            body: JSON.stringify({ query: "query Smoke { __typename }" }),
          });
          const json = await res.json().catch(() => ({ error: "invalid_json" }));
          if (!res.ok) throw new Error("HTTP " + res.status + ": " + JSON.stringify(json));

          setText("status", "connected");
          setClass("status", "ok");
          setText("out", JSON.stringify(json, null, 2));
          show("out");
        } catch (e) {
          setText("status", "error");
          setClass("status", "err");
          setText("detail", String(e && e.message ? e.message : e));
          show("detail");
        }
      })();
    </script>
  </body>
</html>
