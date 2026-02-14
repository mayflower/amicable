export type AmicableDb = {
  appId: string;
  graphqlUrl: string;
  appKey: string;
  previewOrigin: string;
};

declare global {
  interface Window {
    __AMICABLE_DB__?: AmicableDb | null;
  }
}

export function getAmicableDb(): AmicableDb | null {
  if (typeof window === "undefined") return null;
  const db = window.__AMICABLE_DB__;
  if (!db || typeof db !== "object") return null;
  if (!db.graphqlUrl || !db.appKey) return null;
  return db;
}

export async function amicableGraphql<T = unknown>(args: {
  query: string;
  variables?: Record<string, unknown>;
}): Promise<T> {
  const db = getAmicableDb();
  if (!db) throw new Error("AMICABLE_DB_NOT_CONFIGURED");

  const res = await fetch(db.graphqlUrl, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-amicable-app-key": db.appKey,
    },
    body: JSON.stringify({
      query: args.query,
      variables: args.variables ?? undefined,
    }),
  });

  const json = (await res.json().catch(() => ({ error: "invalid_json" }))) as any;
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${JSON.stringify(json)}`);
  return json as T;
}

