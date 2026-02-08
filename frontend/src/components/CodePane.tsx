import Editor from "@monaco-editor/react";
import { FilePlus2, FolderPlus, RefreshCcw, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Tree, type NodeApi, type NodeRendererProps } from "react-arborist";

import { Button } from "@/components/ui/button";
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
}: {
  projectId: string;
  onOpenFile?: (path: string) => void;
  agentTouchedPath?: string | null;
}) => {
  const [treeData, setTreeData] = useState<FileNode[]>([]);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);

  const [fileSha, setFileSha] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string>("");
  const [fileBinary, setFileBinary] = useState<boolean>(false);
  const [dirty, setDirty] = useState<boolean>(false);
  const [saveStatus, setSaveStatus] = useState<string>("");
  const [conflict, setConflict] = useState<boolean>(false);

  const { ref: treeWrapRef, height: treeHeight } = useElementHeight();

  const [memoriesEnabled, setMemoriesEnabled] = useState<boolean>(false);

  const rootNodes = useMemo(() => {
    const base: FileNode[] = [{ id: "/", name: "/", isDir: true, loaded: false, children: [] }];
    if (memoriesEnabled) {
      base.unshift({
        id: "/memories",
        name: "/memories",
        isDir: true,
        loaded: false,
        children: [],
      });
    }
    return base;
  }, [memoriesEnabled]);

  useEffect(() => {
    setTreeData(rootNodes);
  }, [rootNodes]);

  const refreshRoots = async () => {
    setSaveStatus("");
    setConflict(false);
    // Detect whether /memories is available (503 -> disabled).
    try {
      await sandboxLs(projectId, "/memories");
      setMemoriesEnabled(true);
    } catch (e: unknown) {
      if (asErrorWithStatus(e).status === 503) setMemoriesEnabled(false);
    }

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const loadChildren = async (dirPath: string) => {
    const { entries } = await sandboxLs(projectId, dirPath);
    const kids = entries.map(nodeFromEntry);
    setTreeData((prev) =>
      updateNode(prev, dirPath, (n) => ({ ...n, loaded: true, children: kids }))
    );
  };

  const openFile = async (path: string) => {
    setSaveStatus("Loading...");
    setConflict(false);
    const r = await sandboxRead(projectId, path);
    setSelectedPath(r.path);
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
  };

  const debouncedSaveRef = useRef<number | null>(null);
  useEffect(() => {
    if (!dirty) return;
    if (!selectedPath) return;
    if (fileBinary) return;

    if (debouncedSaveRef.current != null) {
      window.clearTimeout(debouncedSaveRef.current);
    }
    debouncedSaveRef.current = window.setTimeout(async () => {
      try {
        setSaveStatus("Saving...");
        const res = await sandboxWrite(projectId, {
          path: selectedPath,
          content: fileContent,
          expected_sha256: fileSha || undefined,
        });
        setFileSha(res.sha256);
        setDirty(false);
        setSaveStatus("Saved");
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
  }, [dirty, selectedPath, fileBinary, fileContent, fileSha, projectId]);

  useEffect(() => {
    if (!agentTouchedPath) return;
    if (!selectedPath) return;
    if (agentTouchedPath === selectedPath) {
      setSaveStatus("Changed by agent; reload?");
    }
  }, [agentTouchedPath, selectedPath]);

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
    if (!selectedPath) return;
    const parts = selectedPath.split("/");
    const cur = parts[parts.length - 1] || "";
    const next = window.prompt("Rename to:", cur);
    if (!next || !next.trim()) return;
    const parent = selectedPath.split("/").slice(0, -1).join("/") || "/";
    const to = (parent === "/" ? "" : parent) + "/" + next.trim();
    await sandboxRename(projectId, { from: selectedPath, to });
    setSelectedPath(to);
    setSaveStatus("Renamed");
    // Refresh parent listing.
    await loadChildren(parent);
  };

  const deleteSelected = async () => {
    if (!selectedPath) return;
    const ok = window.confirm(`Delete ${selectedPath}?`);
    if (!ok) return;
    const recursive = window.confirm("Recursive delete? (OK = recursive, Cancel = non-recursive)");
    await sandboxRm(projectId, { path: selectedPath, recursive });
    setSelectedPath(null);
    setFileContent("");
    setFileSha(null);
    setDirty(false);
    setSaveStatus("Deleted");
    const parent = selectedPath.split("/").slice(0, -1).join("/") || "/";
    await loadChildren(parent);
  };

  const Node = ({ node, style }: NodeRendererProps<FileNode>) => {
    const data = node.data;
    const isDir = !!data.isDir;
    return (
      <div
        style={{
          ...style,
          display: "flex",
          alignItems: "center",
          gap: 6,
          paddingLeft: 6,
          cursor: "default",
          userSelect: "none",
          fontSize: 12,
        }}
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
            try {
              await openFile(data.id);
            } catch {
              // ignore
            }
          }
        }}
        title={data.id}
      >
        <span style={{ width: 14, opacity: 0.8 }}>
          {isDir ? (node.isOpen ? "▾" : "▸") : "•"}
        </span>
        <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {data.name}
        </span>
      </div>
    );
  };

  const selectedDirForCreate = useMemo(() => {
    if (!selectedPath) return "/";
    // If a dir is selected, create inside it; otherwise create next to the file.
    const node = findNode(treeData, selectedPath);
    if (node?.isDir) return node.id;
    return selectedPath.split("/").slice(0, -1).join("/") || "/";
  }, [selectedPath, treeData]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
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
            disabled={!selectedPath}
            title="Rename"
          >
            Rename
          </Button>
          <Button
            size="sm"
            variant="destructive"
            onClick={() => deleteSelected()}
            disabled={!selectedPath}
            title="Delete"
          >
            <Trash2 size={14} />
          </Button>
        </div>

        <div style={{ fontSize: 12, opacity: 0.85, whiteSpace: "nowrap" }}>
          {saveStatus}
        </div>
      </div>

      {conflict && selectedPath ? (
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
                await openFile(selectedPath);
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
                    path: selectedPath,
                    content: fileContent,
                  });
                  setFileSha(res.sha256);
                  setDirty(false);
                  setConflict(false);
                  setSaveStatus("Saved");
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

      <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
        <div
          ref={treeWrapRef}
          style={{
            width: 260,
            borderRight: "1px solid rgba(255,255,255,0.08)",
            minHeight: 0,
          }}
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
              setSelectedPath(n.data.id);
            }}
          >
            {Node}
          </Tree>
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          {!selectedPath ? (
            <div style={{ padding: 12, fontSize: 12, opacity: 0.8 }}>
              Select a file to edit.
            </div>
          ) : fileBinary ? (
            <div style={{ padding: 12, fontSize: 12, opacity: 0.8 }}>
              This file is binary or too large to edit in the browser.
            </div>
          ) : (
            <Editor
              path={selectedPath}
              defaultLanguage={inferLanguage(selectedPath)}
              language={inferLanguage(selectedPath)}
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
