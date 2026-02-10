<script setup lang="ts">
import { onMounted, ref } from "vue";

type AmicableDb = {
  appId: string;
  graphqlUrl: string;
  appKey: string;
  previewOrigin: string;
};

const status = ref<"disabled" | "running" | "connected" | "error">("running");
const detail = ref<string>("");
const payload = ref<any>(null);
const db = ref<AmicableDb | null>(null);

onMounted(async () => {
  const wdb = (window as any).__AMICABLE_DB__ as AmicableDb | null | undefined;
  if (!wdb || !wdb.graphqlUrl || !wdb.appKey) {
    status.value = "disabled";
    detail.value =
      "DB proxy not configured for this sandbox (missing window.__AMICABLE_DB__).";
    return;
  }
  db.value = wdb;
  status.value = "running";
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
    status.value = "connected";
    payload.value = json;
  } catch (e: any) {
    status.value = "error";
    detail.value = String(e?.message || e);
  }
});
</script>

<template>
  <main
    style="
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica,
        Arial;
      padding: 24px;
      max-width: 980px;
      margin: 0 auto;
      line-height: 1.4;
    "
  >
    <h1 style="margin: 0 0 8px">Sandbox DB Wiring</h1>
    <p style="margin: 0 0 16px; opacity: 0.8">
      This app is pre-wired to call Hasura through the agent DB proxy.
    </p>

    <section
      style="
        border: 1px solid #00000020;
        border-radius: 12px;
        padding: 16px;
        background: white;
      "
    >
      <div style="display: flex; gap: 12px; flex-wrap: wrap">
        <span style="font-weight: 600">Status:</span>
        <span v-if="status === 'running'">running smoke query...</span>
        <span v-else-if="status === 'connected'" style="color: #0a7a2f"
          >connected</span
        >
        <span v-else-if="status === 'disabled'" style="color: #8a5a00"
          >disabled</span
        >
        <span v-else style="color: #b00020">error</span>
      </div>

      <div style="margin-top: 12px; font-size: 13px; opacity: 0.85">
        <div><code>appId</code>: {{ db?.appId || "(none)" }}</div>
        <div><code>graphqlUrl</code>: {{ db?.graphqlUrl || "(none)" }}</div>
      </div>

      <pre
        v-if="payload"
        style="
          margin-top: 12px;
          padding: 12px;
          background: #00000008;
          border-radius: 10px;
          overflow: auto;
        "
      >{{ JSON.stringify(payload, null, 2) }}</pre>

      <p
        v-if="status === 'disabled' || status === 'error'"
        style="margin-top: 12px"
        :style="{ color: status === 'error' ? '#b00020' : '' }"
      >
        {{ detail }}
      </p>
    </section>
  </main>
</template>

