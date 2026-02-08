import { useMemo } from "react";
import { useAgentAuth } from "../hooks/useAgentAuth";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";

function initials(nameOrEmail: string | undefined): string {
  if (!nameOrEmail) return "?";
  const parts = nameOrEmail.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return nameOrEmail.slice(0, 2).toUpperCase();
}

export function AgentAuthStatus() {
  const { loading, mode, user, loginUrl, logoutUrl } = useAgentAuth();

  const label = useMemo(() => user?.name || user?.email || undefined, [user]);

  if (loading) return null;
  if (mode !== "google") return null;

  if (!user) {
    return (
      <Button asChild size="sm" variant="secondary">
        <a href={loginUrl}>Sign in with Google</a>
      </Button>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <Avatar className="size-7">
        <AvatarImage src={user.picture} alt={label || "User"} />
        <AvatarFallback>{initials(label)}</AvatarFallback>
      </Avatar>
      <span className="text-sm text-muted-foreground truncate max-w-40">
        {label}
      </span>
      <Button asChild size="sm" variant="ghost">
        <a href={logoutUrl}>Sign out</a>
      </Button>
    </div>
  );
}
