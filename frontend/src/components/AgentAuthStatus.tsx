import { useMemo } from "react";
import { Moon, Sun } from "lucide-react";
import { useAgentAuth } from "../hooks/useAgentAuth";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/components/theme-provider";

function initials(nameOrEmail: string | undefined): string {
  if (!nameOrEmail) return "?";
  const parts = nameOrEmail.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return nameOrEmail.slice(0, 2).toUpperCase();
}

function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const isDark =
    theme === "dark" ||
    (theme === "system" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches);

  return (
    <Button
      size="icon"
      variant="ghost"
      className="size-7"
      onClick={() => setTheme(isDark ? "light" : "dark")}
      title={isDark ? "Switch to light mode" : "Switch to dark mode"}
    >
      {isDark ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </Button>
  );
}

export function AgentAuthStatus() {
  const { loading, mode, user, loginUrl, logoutUrl } = useAgentAuth();

  const label = useMemo(() => user?.name || user?.email || undefined, [user]);

  if (loading) return null;
  if (mode !== "google") return null;

  if (!user) {
    return (
      <div className="flex items-center gap-2">
        <ThemeToggle />
        <Button asChild size="sm" variant="secondary">
          <a href={loginUrl}>Sign in with Google</a>
        </Button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <Avatar className="size-7">
        <AvatarImage src={user.picture} alt={label || "User"} />
        <AvatarFallback>{initials(label)}</AvatarFallback>
      </Avatar>
      <div className="flex flex-col items-end">
        <span className="text-sm text-muted-foreground truncate max-w-40">
          {label}
        </span>
        <a
          href={logoutUrl}
          className="text-xs text-muted-foreground/60 hover:text-muted-foreground transition-colors"
        >
          Sign out
        </a>
      </div>
      <ThemeToggle />
    </div>
  );
}
