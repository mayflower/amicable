import Editor from "@monaco-editor/react";
import {
  ChevronDown,
  ChevronRight,
  FileCode2,
  FilePlus2,
  FileText,
  Folder,
  FolderPlus,
  RefreshCcw,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Tree, type NodeApi, type NodeRendererProps } from "react-arborist";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  projectGitPull,
  projectGitStatus,
  projectGitSync,
  type GitPullResponse,
  type GitStatusResponse,
} from "@/services/gitSync";
import {
  sandboxCreate,
  sandboxLs,
  sandboxRead,
  sandboxRename,
  sandboxRm,
  sandboxWrite,
  type SandboxEntry,
} from "@/services/sandboxFs";

const asErrorWithStatus = (e: unknown): { status?: number } => {
  if (e && typeof e === "object") {
    const r = e as Record<string, unknown>;
    const s = r.status;
    if (typeof s === "number") return { status: s };
  }
  return {};
};

type FileNode = {
  id: string; // absolute public path
  name: string;
  isDir: boolean;
  loaded?: boolean;
  children?: FileNode[];
};

const inferLanguage = (path: string): string => {
  const p = path.toLowerCase();
  if (p.endsWith(".tsx")) return "typescript";
  if (p.endsWith(".ts")) return "typescript";
  if (p.endsWith(".jsx")) return "javascript";
  if (p.endsWith(".js")) return "javascript";
  if (p.endsWith(".json")) return "json";
  if (p.endsWith(".css")) return "css";
  if (p.endsWith(".html")) return "html";
  if (p.endsWith(".md")) return "markdown";
  if (p.endsWith(".yml") || p.endsWith(".yaml")) return "yaml";
  return "plaintext";
};

const fileIconForPath = (path: string) => {
  const p = path.toLowerCase();
  if (
    p.endsWith(".ts") ||
    p.endsWith(".tsx") ||
    p.endsWith(".js") ||
    p.endsWith(".jsx") ||
    p.endsWith(".json") ||
    p.endsWith(".css") ||
    p.endsWith(".html")
  ) {
    return FileCode2;
  }
  return FileText;
};

const useElementHeight = () => {
  const ref = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState<number>(400);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      setHeight(Math.max(120, el.clientHeight));
    });
    ro.observe(el);
    setHeight(Math.max(120, el.clientHeight));
    return () => ro.disconnect();
  }, []);

  return { ref, height };
};

const nodeFromEntry = (e: SandboxEntry): FileNode => ({
  id: e.path,
  name: e.name,
  isDir: !!e.is_dir,
  loaded: false,
  children: e.is_dir ? [] : undefined,
});

const updateNode = (
  nodes: FileNode[],
  id: string,
  fn: (n: FileNode) => FileNode
): FileNode[] => {
  return nodes.map((n) => {
    if (n.id === id) return fn(n);
    if (n.children && n.children.length) {
      return { ...n, children: updateNode(n.children, id, fn) };
    }
    return n;
  });
};

export const CodePane = ({
  projectId,
  onOpenFile,
  agentTouchedPath,
  onSendUserMessage,
}: {
  projectId: string;
  onOpenFile?: (path: string) => void;
  agentTouchedPath?: string | null;
  onSendUserMessage?: (text: string) => void;
}) => {
  const [treeData, setTreeData] = useState<FileNode[]>([]);
  const [treeSelectedPath, setTreeSelectedPath] = useState<string | null>(null);

  const [openPath, setOpenPath] = useState<string | null>(null);
  const [activePath, setActivePath] = useState<string | null>(null);
  const [openState, setOpenState] = useState<
    "idle" | "loading" | "ready" | "error"
  >("idle");
  const [openError, setOpenError] = useState<{
    message: string;
    status?: number;
    data?: unknown;
  } | null>(null);

  const [fileSha, setFileSha] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string>("");
  const [fileBinary, setFileBinary] = useState<boolean>(false);
  const [dirty, setDirty] = useState<boolean>(false);
  const [saveStatus, setSaveStatus] = useState<string>("");
  const [gitStatus, setGitStatus] = useState<string>("");
  const [gitRemoteSha, setGitRemoteSha] = useState<string | null>(null);
  const [gitLocalSha, setGitLocalSha] = useState<string | null>(null);
  const [gitAhead, setGitAhead] = useState<boolean>(false);
  const [gitBaselinePresent, setGitBaselinePresent] = useState<boolean>(false);
  const [gitConflictsPending, setGitConflictsPending] = useState<boolean>(false);
  const [gitPullResult, setGitPullResult] = useState<GitPullResponse | null>(null);
  const [conflict, setConflict] = useState<boolean>(false);

  const { ref: treeWrapRef, height: treeHeight } = useElementHeight();

  const rootNodes = useMemo((): FileNode[] => {
    return [{ id: "/", name: "/", isDir: true, loaded: false, children: [] }];
  }, []);

  useEffect(() => {
    setTreeData(rootNodes);
  }, [rootNodes]);

  const refreshRoots = async () => {
    setSaveStatus("");
    setGitStatus("");
    setConflict(false);
    setOpenError(null);
    setOpenState("idle");
    setOpenPath(null);
    setActivePath(null);
    setTreeSelectedPath(null);
    setFileSha(null);
    setFileContent("");
    setFileBinary(false);
    setDirty(false);
    // Mark roots as unloaded; children are lazy-loaded.
    setTreeData((prev) =>
      prev.map((n) => ({
        ...n,
        loaded: false,
        children: n.isDir ? [] : undefined,
      }))
    );
  };

  useEffect(() => {
    refreshRoots();
  }, [projectId]);

  const loadChildren = async (dirPath: string) => {
    const { entries } = await sandboxLs(projectId, dirPath);
    const kids = entries.map(nodeFromEntry);
    setTreeData((prev) =>
      updateNode(prev, dirPath, (n) => ({ ...n, loaded: true, children: kids }))
    );
  };

  const openReqIdRef = useRef(0);
  const openFile = async (path: string) => {
    const reqId = ++openReqIdRef.current;
    setSaveStatus("Loading...");
    setConflict(false);
    setOpenError(null);
    setOpenState("loading");
    setOpenPath(path);
    try {
      const r = await sandboxRead(projectId, path);
      if (reqId !== openReqIdRef.current) return;

      setTreeSelectedPath(r.path);
      setOpenPath(r.path);
      setActivePath(r.path);
      setOpenState("ready");
      setFileSha(r.sha256);
      setFileBinary(!!r.is_binary);
      setDirty(false);
      if (r.is_binary || r.content == null) {
        setFileContent("");
      } else {
        setFileContent(r.content);
      }
      setSaveStatus("");
      onOpenFile?.(r.path);
    } catch (e: unknown) {
      if (reqId !== openReqIdRef.current) return;
      const status = asErrorWithStatus(e).status;
      const data =
        e && typeof e === "object" && "data" in (e as Record<string, unknown>)
          ? (e as Record<string, unknown>).data
          : undefined;
      setOpenState("error");
      setOpenError({
        message: `Failed to open ${path}${status ? ` (HTTP ${status})` : ""}`,
        status,
        data,
      });
      setSaveStatus("Open failed");
    }
  };

  const debouncedSaveRef = useRef<number | null>(null);
  const syncRunningRef = useRef(false);
  const syncPendingRef = useRef(false);
  const syncPendingCommitMsgRef = useRef<string | null>(null);

  useEffect(() => {
    syncRunningRef.current = false;
    syncPendingRef.current = false;
    syncPendingCommitMsgRef.current = null;
    setGitStatus("");
    setGitRemoteSha(null);
    setGitLocalSha(null);
    setGitAhead(false);
    setGitBaselinePresent(false);
    setGitConflictsPending(false);
    setGitPullResult(null);
  }, [projectId]);

  const gitStatusReqIdRef = useRef(0);
  const refreshGitStatus = useCallback(async () => {
    const reqId = ++gitStatusReqIdRef.current;
    try {
      const r: GitStatusResponse = await projectGitStatus(projectId);
      if (reqId !== gitStatusReqIdRef.current) return;
      setGitRemoteSha(typeof r.remote_sha === "string" ? r.remote_sha : null);
      setGitLocalSha(typeof r.local_sha === "string" ? r.local_sha : null);
      setGitAhead(!!r.ahead);
      setGitBaselinePresent(!!r.baseline_present);
      setGitConflictsPending(!!r.conflicts_pending);
    } catch {
      // Best-effort only; status endpoint may be unavailable in dev setups.
    }
  }, [projectId]);

  useEffect(() => {
    void refreshGitStatus();
  }, [refreshGitStatus]);

  const startGitSync = useCallback(async (commitMessage?: string) => {
    if (syncRunningRef.current) {
      syncPendingRef.current = true;
      syncPendingCommitMsgRef.current = commitMessage || null;
      return;
    }
    syncRunningRef.current = true;
    setGitStatus("Syncing to Git...");
    try {
      const r = await projectGitSync(projectId, {
        commit_message: commitMessage,
      });
      const shaShort =
        typeof r.commit_sha === "string" && r.commit_sha
          ? r.commit_sha.slice(0, 8)
          : null;
      setGitStatus(shaShort ? `Synced (${shaShort})` : "Synced");
      setTimeout(() => setGitStatus(""), 2500);
      void refreshGitStatus();
    } catch (e: unknown) {
      const status = asErrorWithStatus(e).status;
      setGitStatus(
        `Git sync failed${status ? ` (HTTP ${status})` : ""}`
      );
    } finally {
      syncRunningRef.current = false;
      if (syncPendingRef.current) {
        syncPendingRef.current = false;
        const msg = syncPendingCommitMsgRef.current || undefined;
        syncPendingCommitMsgRef.current = null;
        void startGitSync(msg);
      }
    }
  }, [projectId, refreshGitStatus]);

  const softRefreshTree = useCallback(() => {
    // Keep editor state; only reset the lazy-loaded tree so users see new files.
    setTreeData(rootNodes);
  }, [rootNodes]);

  const updateFromGit = useCallback(async () => {
    setGitPullResult(null);
    setGitStatus("Updating from Git...");
    try {
      const r = await projectGitPull(projectId);
      setGitPullResult(r);
      const shaShort =
        typeof r.remote_sha === "string" && r.remote_sha
          ? r.remote_sha.slice(0, 8)
          : null;
      if (!r.updated) {
        setGitStatus("Already up to date");
        setTimeout(() => setGitStatus(""), 2000);
      } else {
        setGitStatus(shaShort ? `Updated (${shaShort})` : "Updated");
        setTimeout(() => setGitStatus(""), 2500);
      }
      softRefreshTree();

      // If the active file was updated from git and the user has no local edits,
      // reload it so they see the new version.
      const modified = r?.applied?.modified || [];
      if (!dirty && activePath && modified.includes(activePath)) {
        await openFile(activePath);
      }
      void refreshGitStatus();
    } catch (e: unknown) {
      const status = asErrorWithStatus(e).status;
      if (status === 409) {
        setGitStatus("Cannot update yet: baseline missing. Sync to Git once first.");
        return;
      }
      setGitStatus(`Git update failed${status ? ` (HTTP ${status})` : ""}`);
    }
  }, [projectId, softRefreshTree, dirty, activePath, openFile, refreshGitStatus]);

  useEffect(() => {
    if (!dirty) return;
    if (openState !== "ready") return;
    if (!activePath) return;
    if (openPath !== activePath) return;
    if (fileBinary) return;
    if (!fileSha) return;

    if (debouncedSaveRef.current != null) {
      window.clearTimeout(debouncedSaveRef.current);
    }
    debouncedSaveRef.current = window.setTimeout(async () => {
      try {
        setSaveStatus("Saving...");
        const res = await sandboxWrite(projectId, {
          path: activePath,
          content: fileContent,
          expected_sha256: fileSha || undefined,
        });
        setFileSha(res.sha256);
        setDirty(false);
        setSaveStatus("Saved");
        void startGitSync(`UI save: ${activePath}`);
        setTimeout(() => setSaveStatus(""), 1200);
      } catch (e: unknown) {
        if (asErrorWithStatus(e).status === 409) {
          setConflict(true);
          setSaveStatus("Conflict");
          return;
        }
        setSaveStatus("Save failed");
      }
    }, 750);

    return () => {
      if (debouncedSaveRef.current != null) {
        window.clearTimeout(debouncedSaveRef.current);
      }
    };
  }, [
    dirty,
    openState,
    openPath,
    activePath,
    fileBinary,
    fileContent,
    fileSha,
    projectId,
    startGitSync,
  ]);

  useEffect(() => {
    if (!agentTouchedPath) return;
    if (!activePath) return;
    if (agentTouchedPath === activePath) {
      setSaveStatus("Changed by agent; reload?");
    }
  }, [agentTouchedPath, activePath]);

  const createInDir = async (dir: string, kind: "file" | "dir") => {
    const name = window.prompt(kind === "file" ? "New file name:" : "New folder name:");
    if (!name || !name.trim()) return;
    const base = dir === "/" ? "" : dir;
    const p = `${base}/${name.trim()}`.replace(/\/+/g, "/");
    await sandboxCreate(projectId, { path: p, kind, content: kind === "file" ? "" : undefined });
    await loadChildren(dir);
    if (kind === "file") await openFile(p);
  };

  const renameSelected = async () => {
    if (!treeSelectedPath || treeSelectedPath === "/") return;
    const parts = treeSelectedPath.split("/");
    const cur = parts[parts.length - 1] || "";
    const next = window.prompt("Rename to:", cur);
    if (!next || !next.trim()) return;
    const parent = treeSelectedPath.split("/").slice(0, -1).join("/") || "/";
    const to = (parent === "/" ? "" : parent) + "/" + next.trim();
    await sandboxRename(projectId, { from: treeSelectedPath, to });
    setTreeSelectedPath(to);
    if (activePath === treeSelectedPath) {
      setActivePath(to);
      setOpenPath(to);
    }
    setSaveStatus("Renamed");
    // Refresh parent listing.
    await loadChildren(parent);
  };

  const deleteSelected = async () => {
    if (!treeSelectedPath || treeSelectedPath === "/") return;
    const ok = window.confirm(`Delete ${treeSelectedPath}?`);
    if (!ok) return;
    const recursive = window.confirm("Recursive delete? (OK = recursive, Cancel = non-recursive)");
    await sandboxRm(projectId, { path: treeSelectedPath, recursive });
    const wasActive = activePath === treeSelectedPath;
    setTreeSelectedPath(null);
    if (wasActive) {
      setOpenState("idle");
      setOpenPath(null);
      setActivePath(null);
      setFileContent("");
      setFileSha(null);
      setDirty(false);
      setFileBinary(false);
      setConflict(false);
    }
    setSaveStatus("Deleted");
    const parent = treeSelectedPath.split("/").slice(0, -1).join("/") || "/";
    await loadChildren(parent);
  };

  const Node = ({ node, style }: NodeRendererProps<FileNode>) => {
    const data = node.data;
    const isDir = !!data.isDir;
    // react-arborist provides indentation via style.paddingLeft; don't clobber it.
    const basePadding =
      typeof style.paddingLeft === "number" ? style.paddingLeft : 0;
    const FileIcon = fileIconForPath(data.id);
    return (
      <div
        style={{
          ...style,
          display: "flex",
          alignItems: "center",
          gap: 6,
          paddingLeft: basePadding + 8,
        }}
        className={cn(
          "h-6 pr-2 text-xs select-none rounded-sm",
          "flex items-center",
          "cursor-default",
          node.isSelected ? "bg-muted text-foreground" : "hover:bg-muted/60"
        )}
        onClick={async () => {
          node.select();
          if (isDir) {
            node.toggle();
            if (!data.loaded && node.isOpen) {
              try {
                await loadChildren(data.id);
              } catch {
                // ignore
              }
            }
          } else {
            await openFile(data.id);
          }
        }}
        title={data.id}
      >
        <span className="w-4 flex items-center justify-center opacity-80">
          {isDir ? (
            node.isOpen ? (
              <ChevronDown size={14} />
            ) : (
              <ChevronRight size={14} />
            )
          ) : (
            <span className="inline-block w-3" />
          )}
        </span>
        <span className="w-4 flex items-center justify-center opacity-80">
          {isDir ? <Folder size={14} /> : <FileIcon size={14} />}
        </span>
        <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {data.name}
        </span>
      </div>
    );
  };

  const selectedDirForCreate = useMemo(() => {
    if (!treeSelectedPath) return "/";
    // If a dir is selected, create inside it; otherwise create next to the file.
    const node = findNode(treeData, treeSelectedPath);
    if (node?.isDir) return node.id;
    return treeSelectedPath.split("/").slice(0, -1).join("/") || "/";
  }, [treeSelectedPath, treeData]);

  const canMutateSelected =
    !!treeSelectedPath && treeSelectedPath !== "/";

  return (
    <div className="flex flex-col h-full min-h-0">
      <div
        className="border-b"
        style={{
          padding: "8px 10px",
          display: "flex",
          gap: 8,
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <Button
            size="sm"
            variant="outline"
            onClick={() => refreshRoots()}
            title="Refresh tree"
          >
            <RefreshCcw size={14} />
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => void updateFromGit()}
            title={
              [
                gitBaselinePresent
                  ? gitAhead
                    ? "Remote has new commits"
                    : "Up to date"
                  : "Baseline missing (sync to Git once first)",
                gitRemoteSha ? `remote: ${gitRemoteSha.slice(0, 8)}` : null,
                gitLocalSha ? `local: ${gitLocalSha.slice(0, 8)}` : null,
              ]
                .filter(Boolean)
                .join(" • ")
            }
          >
            Update from Git{gitAhead ? " *" : ""}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => createInDir(selectedDirForCreate, "file")}
            title="New file"
          >
            <FilePlus2 size={14} />
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => createInDir(selectedDirForCreate, "dir")}
            title="New folder"
          >
            <FolderPlus size={14} />
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => renameSelected()}
            disabled={!canMutateSelected}
            title="Rename"
          >
            Rename
          </Button>
          <Button
            size="sm"
            variant="destructive"
            onClick={() => deleteSelected()}
            disabled={!canMutateSelected}
            title="Delete"
          >
            <Trash2 size={14} />
          </Button>
        </div>

        <div style={{ fontSize: 12, opacity: 0.85, whiteSpace: "nowrap" }}>
          {saveStatus}
          {saveStatus && gitStatus ? " \u2022 " : ""}
          {gitStatus}
        </div>
      </div>

      {gitConflictsPending || (gitPullResult?.conflicts?.length ?? 0) > 0 ? (
        <div
          className="border-b"
          style={{
            padding: "8px 10px",
            display: "flex",
            gap: 10,
            alignItems: "center",
            justifyContent: "space-between",
            background: "rgba(255, 165, 0, 0.08)",
          }}
        >
          <div style={{ fontSize: 12, overflow: "hidden" }}>
            Git conflicts pending
            {(gitPullResult?.remote_sha && typeof gitPullResult.remote_sha === "string")
              ? ` (remote ${gitPullResult.remote_sha.slice(0, 8)})`
              : ""}
            :{" "}
            {(gitPullResult?.conflicts || [])
              .slice(0, 3)
              .map((c) => c.path)
              .join(", ")}
            {(gitPullResult?.conflicts || []).length > 3 ? "…" : ""}
          </div>
          <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                const conflicts = gitPullResult?.conflicts || [];
                const remoteSha = gitPullResult?.remote_sha || gitRemoteSha;
                if (!remoteSha || !conflicts.length) {
                  setGitStatus("No conflict details available yet. Click Update from Git.");
                  return;
                }
                const lines = conflicts
                  .map(
                    (c) =>
                      `- ${c.path} (remote: ${c.remote_shadow_path})`
                  )
                  .join("\n");
                const prompt = [
                  `I pulled commit ${remoteSha} from Git, but these files conflict with local sandbox changes.`,
                  "",
                  "For each path, compare the current sandbox file with the remote shadow file and merge:",
                  lines,
                  "",
                  "Write the merged result back to the original path, then sync to Git.",
                ].join("\n");
                onSendUserMessage?.(prompt);
              }}
              disabled={!onSendUserMessage}
              title={
                onSendUserMessage
                  ? "Ask the agent to merge the conflicted files"
                  : "Unavailable (missing chat callback)"
              }
            >
              Ask agent to merge conflicts
            </Button>
          </div>
        </div>
      ) : null}

      {conflict && activePath ? (
        <div
          className="border-b"
          style={{
            padding: "8px 10px",
            display: "flex",
            gap: 10,
            alignItems: "center",
            justifyContent: "space-between",
            background: "rgba(255, 0, 0, 0.06)",
          }}
        >
          <div style={{ fontSize: 12 }}>
            Conflict: file changed on disk. Reload or overwrite.
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <Button
              size="sm"
              variant="outline"
              onClick={async () => {
                await openFile(activePath);
                setConflict(false);
              }}
            >
              Reload
            </Button>
            <Button
              size="sm"
              variant="destructive"
              onClick={async () => {
                try {
                  setSaveStatus("Overwriting...");
                  const res = await sandboxWrite(projectId, {
                    path: activePath,
                    content: fileContent,
                  });
                  setFileSha(res.sha256);
                  setDirty(false);
                  setConflict(false);
                  setSaveStatus("Saved");
                  void startGitSync(`UI save: ${activePath}`);
                  setTimeout(() => setSaveStatus(""), 1200);
                } catch {
                  setSaveStatus("Overwrite failed");
                }
              }}
            >
              Overwrite
            </Button>
          </div>
        </div>
      ) : null}

      <div className="flex flex-1 min-h-0">
        <div
          ref={treeWrapRef}
          className="w-[260px] border-r min-h-0 bg-background"
        >
          <Tree<FileNode>
            data={treeData}
            idAccessor="id"
            childrenAccessor="children"
            width={"100%"}
            height={treeHeight}
            indent={16}
            rowHeight={24}
            openByDefault={false}
            onSelect={(nodes: NodeApi<FileNode>[]) => {
              const n = nodes[0];
              if (!n) return;
              setTreeSelectedPath(n.data.id);
            }}
          >
            {Node}
          </Tree>
        </div>

        <div className="flex-1 min-w-0">
          {openState === "idle" ? (
            <div style={{ padding: 12, fontSize: 12, opacity: 0.8 }}>
              Select a file to edit.
            </div>
          ) : openState === "loading" ? (
            <div style={{ padding: 12, fontSize: 12, opacity: 0.8 }}>
              Loading{openPath ? `: ${openPath}` : "..."}
            </div>
          ) : openState === "error" ? (
            <div style={{ padding: 12, fontSize: 12, opacity: 0.85 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>
                {openError?.message || "Failed to open file."}
              </div>
              {openError?.data ? (
                <details style={{ marginTop: 8 }}>
                  <summary style={{ cursor: "pointer" }}>Details</summary>
                  <pre style={{ marginTop: 8, whiteSpace: "pre-wrap", fontSize: 11, opacity: 0.85 }}>
                    {JSON.stringify(openError.data, null, 2)}
                  </pre>
                </details>
              ) : null}
              <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={async () => {
                    if (openPath) await openFile(openPath);
                  }}
                  disabled={!openPath}
                >
                  Retry
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    if (!activePath) return;
                    setOpenPath(activePath);
                    setOpenState("ready");
                    setOpenError(null);
                    setSaveStatus("");
                  }}
                  disabled={!activePath}
                >
                  Back to opened file
                </Button>
              </div>
            </div>
          ) : !activePath ? (
            <div style={{ padding: 12, fontSize: 12, opacity: 0.8 }}>
              Select a file to edit.
            </div>
          ) : fileBinary ? (
            <div style={{ padding: 12, fontSize: 12, opacity: 0.8 }}>
              This file is binary or too large to edit in the browser.
            </div>
          ) : (
            <Editor
              path={activePath}
              defaultLanguage={inferLanguage(activePath)}
              language={inferLanguage(activePath)}
              theme="vs-dark"
              value={fileContent}
              onChange={(v) => {
                setFileContent(v ?? "");
                setDirty(true);
                setSaveStatus("");
              }}
              options={{
                minimap: { enabled: false },
                fontSize: 13,
                wordWrap: "on",
                scrollBeyondLastLine: false,
                automaticLayout: true,
              }}
              height="100%"
            />
          )}
        </div>
      </div>
    </div>
  );
};

const findNode = (nodes: FileNode[], id: string): FileNode | null => {
  for (const n of nodes) {
    if (n.id === id) return n;
    if (n.children && n.children.length) {
      const hit = findNode(n.children, id);
      if (hit) return hit;
    }
  }
  return null;
};
