import React, { useCallback, useEffect, useMemo, useState } from "react";

import { AGENT_CONFIG } from "@/config/agent";
import { AgentAuthStatus } from "@/components/AgentAuthStatus";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useAgentAuth } from "@/hooks/useAgentAuth";
import { useNavigate } from "react-router-dom";
import { TEMPLATES, type TemplateId, templateLabel } from "@/templates/registry";

type Project = {
  project_id: string;
  name: string;
  slug: string;
  template_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

function apiUrl(path: string): string {
  return new URL(path, AGENT_CONFIG.HTTP_URL).toString();
}

const NewScreen: React.FC = () => {
  const navigate = useNavigate();
  const { loading: authLoading, mode: authMode, user: authUser, loginUrl } =
    useAgentAuth();

  const [prompt, setPrompt] = useState("");
  const [name, setName] = useState("");
  const [templateId, setTemplateId] = useState<TemplateId>("lovable_vite");
  const [projects, setProjects] = useState<Project[]>([]);
  const [loadingProjects, setLoadingProjects] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<Set<string>>(new Set());
  const [promptTouched, setPromptTouched] = useState(false);

  useEffect(() => {
    if (authLoading) return;
    if (authMode === "google" && !authUser) {
      window.location.href = loginUrl;
    }
  }, [authLoading, authMode, authUser, loginUrl]);

  const canUseApi = useMemo(() => {
    if (authLoading) return false;
    if (authMode === "google" && !authUser) return false;
    return true;
  }, [authLoading, authMode, authUser]);

  const refresh = useCallback(async () => {
    if (!canUseApi) return;
    setLoadingProjects(true);
    setError(null);
    try {
      const res = await fetch(apiUrl("/api/projects"), {
        credentials: "include",
      });
      const data = (await res.json()) as { projects?: Project[]; error?: string };
      if (!res.ok) {
        setError(data?.error || `failed to load projects (${res.status})`);
        setProjects([]);
        return;
      }
      setProjects(Array.isArray(data.projects) ? data.projects : []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load projects");
      setProjects([]);
    } finally {
      setLoadingProjects(false);
    }
  }, [canUseApi]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleCreate = useCallback(async () => {
    if (!canUseApi) return;
    const p = prompt.trim();
    const n = name.trim();
    if (p.length < 15) {
      setPromptTouched(true);
      return;
    }
    setError(null);
    try {
      const res = await fetch(apiUrl("/api/projects"), {
        method: "POST",
        headers: { "content-type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ name: n || undefined, prompt: p, template_id: templateId }),
      });
      const data = (await res.json()) as {
        project_id?: string;
        name?: string;
        slug?: string;
        template_id?: string;
        error?: string;
      };
      if (!res.ok) {
        setError(data?.error || `failed to create project (${res.status})`);
        return;
      }
      if (!data.slug || !data.project_id) {
        setError("invalid create response");
        return;
      }
      navigate(`/p/${data.slug}`, {
        state: { initialPrompt: p, project_id: data.project_id },
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to create project");
    }
  }, [canUseApi, name, navigate, prompt, templateId]);

  const handleRename = useCallback(
    async (proj: Project) => {
      if (!canUseApi) return;
      const next = window.prompt("Project name:", proj.name);
      if (!next || !next.trim()) return;
      setError(null);
      try {
        const res = await fetch(apiUrl(`/api/projects/${proj.project_id}`), {
          method: "PATCH",
          headers: { "content-type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ name: next.trim() }),
        });
        const data = (await res.json()) as {
          project_id?: string;
          name?: string;
          slug?: string;
          error?: string;
        };
        if (!res.ok) {
          setError(data?.error || `failed to rename (${res.status})`);
          return;
        }
        await refresh();
      } catch (e) {
        setError(e instanceof Error ? e.message : "failed to rename project");
      }
    },
    [canUseApi, refresh]
  );

  const handleDelete = useCallback(
    async (proj: Project) => {
      if (!canUseApi) return;
      const ok = window.confirm(
        `Delete project "${proj.name}"?\n\nThis will delete its sandbox and database schema.`
      );
      if (!ok) return;

      setDeleting((prev) => new Set(prev).add(proj.project_id));
      setError(null);
      try {
        const res = await fetch(apiUrl(`/api/projects/${proj.project_id}`), {
          method: "DELETE",
          credentials: "include",
        });
        const data = (await res.json()) as { status?: string; error?: string };
        if (!res.ok && res.status !== 202) {
          setError(data?.error || `failed to delete (${res.status})`);
          return;
        }
        // Hide immediately; backend marks deleted then cleans up async.
        setProjects((prev) => prev.filter((p) => p.project_id !== proj.project_id));
      } catch (e) {
        setError(e instanceof Error ? e.message : "failed to delete project");
      } finally {
        setDeleting((prev) => {
          const next = new Set(prev);
          next.delete(proj.project_id);
          return next;
        });
      }
    },
    [canUseApi]
  );

  return (
    <div className="min-h-screen w-screen flex flex-row items-center relative p-6">
      <div className="absolute top-4 right-4">
        <AgentAuthStatus />
      </div>

      <div className="flex flex-col items-center w-full max-w-[980px] mx-auto gap-10">
        <div className="flex flex-col md:flex-row items-center md:items-start gap-4 md:gap-8 w-full">
          <img
            className="w-32 h-32 md:w-40 md:h-40 object-contain shrink-0"
            src="/amicable-logo.svg"
            alt="Amicable"
            loading="eager"
            decoding="async"
          />
          <div className="flex flex-col gap-2 text-center md:text-left">
            <h1 className="text-2xl font-bold">
              Ship internal tools without skipping controls.
            </h1>
            <p className="text-lg font-normal max-w-[60ch]">
              Amicable helps non-engineers and teams build real apps on sanctioned stacks. Choose a
              template, write a short prompt, and get a sandboxed project that can plug into your
              org’s QA, security, and observability practices.
            </p>
          </div>
        </div>

        <div className="w-full rounded-2xl p-4 border border-border bg-background/5">
          <h2 className="text-base font-semibold" style={{ marginBottom: 10 }}>
            New project
          </h2>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div className="grid gap-2 [grid-template-columns:repeat(auto-fill,minmax(220px,1fr))]">
              {TEMPLATES.map((t) => {
                const active = templateId === t.id;
                return (
                  <button
                    key={t.id}
                    type="button"
                    disabled={!canUseApi}
                    onClick={() => setTemplateId(t.id)}
                    className={[
                      "text-left rounded-md border p-3 transition",
                      active ? "border-blue-600 bg-blue-600/10" : "border-border bg-black/5 hover:bg-black/10",
                      !canUseApi ? "opacity-60 cursor-not-allowed" : "",
                    ].join(" ")}
                  >
                    <div style={{ fontWeight: 700 }}>{t.title}</div>
                    <div className="text-xs text-muted-foreground" style={{ marginTop: 4 }}>
                      {t.description}
                    </div>
                  </button>
                );
              })}
            </div>
            <Input
              placeholder="Project name (optional)"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={!canUseApi}
            />
            <div>
              <Textarea
                rows={4}
                placeholder="Describe what you want to build..."
                value={prompt}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => {
                  setPrompt(e.target.value);
                  if (promptTouched && e.target.value.trim().length >= 15) setPromptTouched(false);
                }}
                onKeyDown={(e: React.KeyboardEvent<HTMLTextAreaElement>) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleCreate();
                  }
                }}
                onBlur={() => { if (prompt.trim().length < 15) setPromptTouched(true); }}
                disabled={!canUseApi}
                className={promptTouched && prompt.trim().length < 15 ? "border-red-500 focus-visible:ring-red-500" : ""}
              />
              {promptTouched && prompt.trim().length < 15 && (
                <p className="text-sm text-red-500 mt-1">
                  {!prompt.trim()
                    ? "Please enter a prompt to get started."
                    : `Prompt must be at least 15 characters (${prompt.trim().length}/15).`}
                </p>
              )}
            </div>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <Button
                onClick={handleCreate}
                disabled={!canUseApi || prompt.trim().length < 15}
              >
                Create
              </Button>
            </div>
          </div>
        </div>

        <div className="w-full rounded-2xl p-4 border border-border bg-background/5">
          <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
            <h2 className="text-base font-semibold">Existing projects</h2>
            <Button variant="outline" onClick={refresh} disabled={!canUseApi}>
              Refresh
            </Button>
          </div>

          {error ? (
            <div className="text-sm text-red-600" style={{ marginTop: 10 }}>
              {error}
            </div>
          ) : null}

          {loadingProjects ? (
            <div className="text-sm text-muted-foreground" style={{ marginTop: 10 }}>
              Loading...
            </div>
          ) : projects.length === 0 ? (
            <div className="text-sm text-muted-foreground" style={{ marginTop: 10 }}>
              No projects yet.
            </div>
          ) : (
            <div
              className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(260px,1fr))]"
              style={{ marginTop: 12 }}
            >
              {projects.map((p) => {
                const isDeleting = deleting.has(p.project_id);
                return (
                  <div
                    key={p.project_id}
                    className="border rounded-md p-3 bg-black/5"
                  >
                    <div style={{ fontWeight: 600 }}>{p.name}</div>
                    <div className="text-xs text-muted-foreground">/{p.slug}</div>
                    <div className="text-xs text-muted-foreground" style={{ marginTop: 6 }}>
                      Template: {templateLabel(p.template_id)}
                    </div>
                    <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                      <Button
                        onClick={() => navigate(`/p/${p.slug}`)}
                        disabled={!canUseApi || isDeleting}
                      >
                        Open
                      </Button>
                      <Button
                        variant="secondary"
                        onClick={() => handleRename(p)}
                        disabled={!canUseApi || isDeleting}
                      >
                        Rename
                      </Button>
                      <Button
                        variant="destructive"
                        onClick={() => handleDelete(p)}
                        disabled={!canUseApi || isDeleting}
                      >
                        {isDeleting ? "Deleting..." : "Delete"}
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default NewScreen;
