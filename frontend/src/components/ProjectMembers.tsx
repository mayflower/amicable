import { useState, useCallback, useEffect, type FormEvent } from "react";
import { Loader2, UserPlus, X, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AGENT_CONFIG } from "../config/agent";
import { cn } from "@/lib/utils";

interface ProjectMember {
  user_sub: string | null;
  user_email: string;
  added_at: string | null;
}

interface ProjectMembersProps {
  projectId: string;
  className?: string;
}

export function ProjectMembers({ projectId, className }: ProjectMembersProps) {
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newEmail, setNewEmail] = useState("");
  const [adding, setAdding] = useState(false);
  const [removingEmail, setRemovingEmail] = useState<string | null>(null);

  const fetchMembers = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch(
        `${AGENT_CONFIG.HTTP_URL}api/projects/${projectId}/members`,
        { credentials: "include" }
      );
      if (!res.ok) {
        throw new Error("Failed to load members");
      }
      const data = await res.json();
      setMembers(data.members || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load members");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchMembers();
  }, [fetchMembers]);

  const handleAddMember = async (e: FormEvent) => {
    e.preventDefault();
    const email = newEmail.trim().toLowerCase();
    if (!email || !email.includes("@")) return;

    try {
      setAdding(true);
      setError(null);
      const res = await fetch(
        `${AGENT_CONFIG.HTTP_URL}api/projects/${projectId}/members`,
        {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email }),
        }
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || "Failed to add member");
      }
      setNewEmail("");
      await fetchMembers();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add member");
    } finally {
      setAdding(false);
    }
  };

  const handleRemoveMember = async (userSub: string | null, userEmail: string) => {
    if (members.length <= 1) return;

    try {
      setRemovingEmail(userEmail);
      setError(null);
      // Use by-email endpoint for pending members (null user_sub), otherwise by user_sub
      const endpoint = userSub
        ? `${AGENT_CONFIG.HTTP_URL}api/projects/${projectId}/members/${encodeURIComponent(userSub)}`
        : `${AGENT_CONFIG.HTTP_URL}api/projects/${projectId}/members/by-email/${encodeURIComponent(userEmail)}`;
      const res = await fetch(endpoint, {
        method: "DELETE",
        credentials: "include",
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || "Failed to remove member");
      }
      await fetchMembers();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to remove member");
    } finally {
      setRemovingEmail(null);
    }
  };

  const canRemove = members.length > 1;

  return (
    <div className={cn("space-y-4", className)}>
      <div className="flex items-center gap-2 text-sm font-medium text-gray-700">
        <Users className="w-4 h-4" />
        <span>People with access</span>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-6">
          <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
        </div>
      ) : (
        <>
          {/* Member list */}
          <div className="space-y-2">
            {members.map((member) => (
              <div
                key={member.user_email}
                className="flex items-center justify-between gap-3 px-3 py-2 bg-gray-50 rounded-md border border-gray-200"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-8 h-8 rounded-full bg-gray-300 flex items-center justify-center text-sm font-medium text-gray-600 shrink-0">
                    {member.user_email.charAt(0).toUpperCase()}
                  </div>
                  <span className="text-sm text-gray-700 truncate">
                    {member.user_email}
                  </span>
                  {!member.user_sub && (
                    <span className="text-xs text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">
                      Pending
                    </span>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() =>
                    handleRemoveMember(member.user_sub, member.user_email)
                  }
                  disabled={!canRemove || removingEmail === member.user_email}
                  className={cn(
                    "p-1.5 rounded-md transition-colors shrink-0",
                    canRemove
                      ? "hover:bg-red-100 text-gray-400 hover:text-red-600"
                      : "text-gray-300 cursor-not-allowed"
                  )}
                  title={
                    !canRemove
                      ? "Cannot remove the last member"
                      : "Remove member"
                  }
                >
                  {removingEmail === member.user_email ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <X className="w-4 h-4" />
                  )}
                </button>
              </div>
            ))}
          </div>

          {/* Add member form */}
          <form onSubmit={handleAddMember} className="flex gap-2">
            <Input
              type="email"
              placeholder="Add by email..."
              value={newEmail}
              onChange={(e) => setNewEmail(e.target.value)}
              disabled={adding}
              className="flex-1"
            />
            <Button
              type="submit"
              disabled={adding || !newEmail.trim() || !newEmail.includes("@")}
              size="default"
            >
              {adding ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <UserPlus className="w-4 h-4" />
              )}
              <span className="sr-only sm:not-sr-only sm:ml-1">Add</span>
            </Button>
          </form>

          {/* Error message */}
          {error && (
            <p className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded-md">
              {error}
            </p>
          )}
        </>
      )}
    </div>
  );
}
