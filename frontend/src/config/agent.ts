import type { PermissionMode, ThinkingLevel } from "@/types/messages";

declare global {
  interface Window {
    __AMICABLE_CONFIG__?: {
      VITE_AGENT_HTTP_URL?: string;
      VITE_AGENT_WS_URL?: string;
      VITE_AGENT_PERMISSION_MODE?: PermissionMode;
      VITE_AGENT_THINKING_LEVEL?: ThinkingLevel;
    };
  }
}

const runtime =
  typeof window !== "undefined" ? window.__AMICABLE_CONFIG__ : undefined;

function normalizePermissionMode(raw: unknown): PermissionMode | undefined {
  if (raw === "default" || raw === "accept_edits" || raw === "bypass") {
    return raw;
  }
  return undefined;
}

function normalizeThinkingLevel(raw: unknown): ThinkingLevel | undefined {
  if (
    raw === "none" ||
    raw === "think" ||
    raw === "think_hard" ||
    raw === "ultrathink"
  ) {
    return raw;
  }
  return undefined;
}

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

export const AGENT_CONFIG = {
  WS_URL,
  HTTP_URL:
    runtime?.VITE_AGENT_HTTP_URL ??
    import.meta.env.VITE_AGENT_HTTP_URL ??
    deriveHttpBaseUrlFromWs(WS_URL),
  PERMISSION_MODE:
    normalizePermissionMode(runtime?.VITE_AGENT_PERMISSION_MODE) ??
    normalizePermissionMode(import.meta.env.VITE_AGENT_PERMISSION_MODE),
  THINKING_LEVEL:
    normalizeThinkingLevel(runtime?.VITE_AGENT_THINKING_LEVEL) ??
    normalizeThinkingLevel(import.meta.env.VITE_AGENT_THINKING_LEVEL),
} as const;
