import React from "react";
import { amicableGraphql, getAmicableDb } from "./lib/amicableDb";

type SmokeResult = {
  data?: unknown;
  errors?: unknown;
};

export default function App() {
  const [status, setStatus] = React.useState<
    "disabled" | "running" | "connected" | "error"
  >("running");
  const [detail, setDetail] = React.useState<string>("");
  const [payload, setPayload] = React.useState<SmokeResult | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    async function run() {
      const db = getAmicableDb();
      if (!db) {
        if (!cancelled) {
          setStatus("disabled");
          setDetail(
            "DB proxy not configured for this sandbox (missing window.__AMICABLE_DB__)."
          );
        }
        return;
      }
      if (!cancelled) setStatus("running");
      try {
        const json = await amicableGraphql<SmokeResult>({
          query: "query Smoke { __typename }",
        });
        if (!cancelled) {
          setStatus("connected");
          setPayload(json);
        }
      } catch (e: any) {
        if (!cancelled) {
          setStatus("error");
          setDetail(String(e?.message || e));
        }
      }
    }
    run();
    return () => {
      cancelled = true;
    };
  }, []);

  const db = getAmicableDb();

  return (
    <div style={{ padding: 24, maxWidth: 980, margin: "0 auto" }}>
      <h1 style={{ margin: "0 0 8px" }}>Sandbox DB Wiring</h1>
      <p style={{ margin: "0 0 16px", opacity: 0.8 }}>
        This app is pre-wired to call Hasura through the agent DB proxy.
      </p>

      <div
        style={{
          border: "1px solid #00000020",
          borderRadius: 12,
          padding: 16,
          background: "white",
        }}
      >
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <span style={{ fontWeight: 600 }}>Status:</span>
          {status === "running" && <span>running smoke query...</span>}
          {status === "connected" && (
            <span style={{ color: "#0a7a2f" }}>connected</span>
          )}
          {status === "disabled" && (
            <span style={{ color: "#8a5a00" }}>disabled</span>
          )}
          {status === "error" && (
            <span style={{ color: "#b00020" }}>error</span>
          )}
        </div>

        <div style={{ marginTop: 12, fontSize: 13, opacity: 0.85 }}>
          <div>
            <code>appId</code>: {db?.appId || "(none)"}
          </div>
          <div>
            <code>graphqlUrl</code>: {db?.graphqlUrl || "(none)"}
          </div>
        </div>

        {payload && (
          <pre
            style={{
              marginTop: 12,
              padding: 12,
              background: "#00000008",
              borderRadius: 10,
              overflow: "auto",
            }}
          >
            {JSON.stringify(payload, null, 2)}
          </pre>
        )}

        {(status === "disabled" || status === "error") && (
          <p style={{ marginTop: 12, color: status === "error" ? "#b00020" : "" }}>
            {detail}
          </p>
        )}
      </div>
    </div>
  );
}

