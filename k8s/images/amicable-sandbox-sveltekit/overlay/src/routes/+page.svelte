<script lang="ts">
  import { onMount } from "svelte";

  type AmicableDb = {
    appId: string;
    graphqlUrl: string;
    appKey: string;
    previewOrigin: string;
  };

  let status: "disabled" | "running" | "connected" | "error" = "running";
  let detail = "";
  let payload: any = null;
  let db: AmicableDb | null = null;

  onMount(async () => {
    const wdb = (window as any).__AMICABLE_DB__ as AmicableDb | null | undefined;
    if (!wdb || !wdb.graphqlUrl || !wdb.appKey) {
      status = "disabled";
      detail =
        "DB proxy not configured for this sandbox (missing window.__AMICABLE_DB__).";
      return;
    }
    db = wdb;
    status = "running";
    try {
      const res = await fetch(wdb.graphqlUrl, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-amicable-app-key": wdb.appKey,
        },
        body: JSON.stringify({ query: "query Smoke { __typename }" }),
      });
      const json = await res.json().catch(() => ({ error: "invalid_json" }));
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${JSON.stringify(json)}`);
      status = "connected";
      payload = json;
    } catch (e: any) {
      status = "error";
      detail = String(e?.message || e);
    }
  });
</script>

<main
  style="font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial; padding: 24px; max-width: 980px; margin: 0 auto; line-height: 1.4"
>
  <h1 style="margin: 0 0 8px">Sandbox DB Wiring</h1>
  <p style="margin: 0 0 16px; opacity: 0.8">
    This app is pre-wired to call Hasura through the agent DB proxy.
  </p>

  <section
    style="border: 1px solid #00000020; border-radius: 12px; padding: 16px; background: white"
  >
    <div style="display: flex; gap: 12px; flex-wrap: wrap">
      <span style="font-weight: 600">Status:</span>
      {#if status === "running"}
        <span>running smoke query...</span>
      {:else if status === "connected"}
        <span style="color: #0a7a2f">connected</span>
      {:else if status === "disabled"}
        <span style="color: #8a5a00">disabled</span>
      {:else}
        <span style="color: #b00020">error</span>
      {/if}
    </div>

    <div style="margin-top: 12px; font-size: 13px; opacity: 0.85">
      <div><code>appId</code>: {db?.appId || "(none)"}</div>
      <div><code>graphqlUrl</code>: {db?.graphqlUrl || "(none)"}</div>
    </div>

    {#if payload}
      <pre
        style="margin-top: 12px; padding: 12px; background: #00000008; border-radius: 10px; overflow: auto"
      >{JSON.stringify(payload, null, 2)}</pre>
    {/if}

    {#if status === "disabled" || status === "error"}
      <p style="margin-top: 12px; color: {status === 'error' ? '#b00020' : ''}">
        {detail}
      </p>
    {/if}
  </section>
</main>

