import { useCallback, useEffect, useMemo, useState } from "react";
import { AGENT_CONFIG } from "../config/agent";

export type AgentUser = {
  sub?: string;
  email?: string;
  name?: string;
  picture?: string;
};

type AuthMeResponse =
  | { authenticated: true; mode: "google"; user: AgentUser }
  | { authenticated: false; mode: string; user?: never };

export function useAgentAuth() {
  const [loading, setLoading] = useState(true);
  const [user, setUser] = useState<AgentUser | null>(null);
  const [mode, setMode] = useState<string | null>(null);

  const httpBaseUrl = AGENT_CONFIG.HTTP_URL;
  const meUrl = new URL("/auth/me", httpBaseUrl).toString();

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(meUrl, { credentials: "include" });
      const data = (await res.json()) as AuthMeResponse;
      setMode(data.mode);
      setUser(data.authenticated ? data.user : null);
    } catch {
      setMode(null);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, [meUrl]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const loginUrl = useMemo(() => {
    const u = new URL("/auth/login", httpBaseUrl);
    u.searchParams.set("redirect", window.location.href);
    return u.toString();
  }, [httpBaseUrl]);

  const logoutUrl = useMemo(() => {
    const u = new URL("/auth/logout", httpBaseUrl);
    u.searchParams.set("redirect", window.location.href);
    return u.toString();
  }, [httpBaseUrl]);

  return { loading, mode, user, refresh, loginUrl, logoutUrl };
}
