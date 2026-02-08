import { AGENT_CONFIG } from "@/config/agent";

export type SandboxEntry = {
  path: string;
  name: string;
  is_dir: boolean;
};

export type SandboxRead = {
  path: string;
  content: string | null;
  sha256: string;
  is_binary: boolean;
};

const agentUrl = (path: string) => new URL(path, AGENT_CONFIG.HTTP_URL).toString();

const readJson = async (res: Response): Promise<unknown> => {
  try {
    return (await res.json()) as unknown;
  } catch {
    return null;
  }
};

export const sandboxLs = async (
  projectId: string,
  path: string
): Promise<{ path: string; entries: SandboxEntry[] }> => {
  const url = agentUrl(
    `/api/sandbox/${encodeURIComponent(projectId)}/ls?path=${encodeURIComponent(path)}`
  );
  const res = await fetch(url, { credentials: "include" });
  const data = await readJson(res);
  if (!res.ok)
    throw Object.assign(new Error("ls_failed"), { status: res.status, data });
  return data as { path: string; entries: SandboxEntry[] };
};

export const sandboxRead = async (
  projectId: string,
  path: string
): Promise<SandboxRead> => {
  const url = agentUrl(
    `/api/sandbox/${encodeURIComponent(projectId)}/read?path=${encodeURIComponent(path)}`
  );
  const res = await fetch(url, { credentials: "include" });
  const data = await readJson(res);
  if (!res.ok)
    throw Object.assign(new Error("read_failed"), { status: res.status, data });
  return data as SandboxRead;
};

export const sandboxWrite = async (
  projectId: string,
  args: { path: string; content: string; expected_sha256?: string }
): Promise<{ path: string; sha256: string }> => {
  const url = agentUrl(`/api/sandbox/${encodeURIComponent(projectId)}/write`);
  const res = await fetch(url, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    credentials: "include",
    body: JSON.stringify(args),
  });
  const data = await readJson(res);
  if (!res.ok)
    throw Object.assign(new Error("write_failed"), { status: res.status, data });
  return data as { path: string; sha256: string };
};

export const sandboxMkdir = async (
  projectId: string,
  path: string
): Promise<void> => {
  const url = agentUrl(`/api/sandbox/${encodeURIComponent(projectId)}/mkdir`);
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ path }),
  });
  if (!res.ok) throw Object.assign(new Error("mkdir_failed"), { status: res.status });
};

export const sandboxCreate = async (
  projectId: string,
  args: { path: string; kind: "file" | "dir"; content?: string }
): Promise<{ path: string; sha256?: string }> => {
  const url = agentUrl(`/api/sandbox/${encodeURIComponent(projectId)}/create`);
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "include",
    body: JSON.stringify(args),
  });
  const data = await readJson(res);
  if (!res.ok)
    throw Object.assign(new Error("create_failed"), { status: res.status, data });
  return data as { path: string; sha256?: string };
};

export const sandboxRename = async (
  projectId: string,
  args: { from: string; to: string }
): Promise<void> => {
  const url = agentUrl(`/api/sandbox/${encodeURIComponent(projectId)}/rename`);
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "include",
    body: JSON.stringify(args),
  });
  if (!res.ok) throw Object.assign(new Error("rename_failed"), { status: res.status });
};

export const sandboxRm = async (
  projectId: string,
  args: { path: string; recursive: boolean }
): Promise<void> => {
  const url = agentUrl(
    `/api/sandbox/${encodeURIComponent(projectId)}/rm?path=${encodeURIComponent(
      args.path
    )}&recursive=${args.recursive ? 1 : 0}`
  );
  const res = await fetch(url, { method: "DELETE", credentials: "include" });
  if (!res.ok) throw Object.assign(new Error("rm_failed"), { status: res.status });
};
