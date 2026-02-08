declare global {
  interface Window {
    __AMICABLE_CONFIG__?: {
      VITE_AGENT_HTTP_URL?: string;
      VITE_AGENT_WS_URL?: string;
      VITE_AGENT_TOKEN?: string;
    };
  }
}

const runtime =
  typeof window !== "undefined" ? window.__AMICABLE_CONFIG__ : undefined;

function deriveHttpBaseUrlFromWs(wsUrl: string): string {
  const u = new URL(wsUrl);
  u.protocol = u.protocol === "wss:" ? "https:" : "http:";
  u.pathname = "/";
  u.search = "";
  u.hash = "";
  return u.toString();
}

const WS_URL =
  runtime?.VITE_AGENT_WS_URL ?? import.meta.env.VITE_AGENT_WS_URL;

const TOKEN =
  runtime?.VITE_AGENT_TOKEN ?? import.meta.env.VITE_AGENT_TOKEN;

export const AGENT_CONFIG = {
  WS_URL,
  TOKEN,
  HTTP_URL:
    runtime?.VITE_AGENT_HTTP_URL ??
    import.meta.env.VITE_AGENT_HTTP_URL ??
    deriveHttpBaseUrlFromWs(WS_URL),
} as const;
