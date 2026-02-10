import { AGENT_CONFIG } from "@/config/agent";

const agentUrl = (path: string) => new URL(path, AGENT_CONFIG.HTTP_URL).toString();

const readJson = async (res: Response): Promise<unknown> => {
  try {
    return (await res.json()) as unknown;
  } catch {
    return null;
  }
};

export type GitSyncResponse = {
  pushed: boolean;
  commit_sha: string | null;
  diff_stat: string;
  name_status: string;
  error?: string;
  detail?: string;
};

export const projectGitSync = async (
  projectId: string,
  args?: { commit_message?: string }
): Promise<GitSyncResponse> => {
  const url = agentUrl(`/api/projects/${encodeURIComponent(projectId)}/git/sync`);
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ commit_message: args?.commit_message ?? null }),
  });
  const data = await readJson(res);
  if (!res.ok)
    throw Object.assign(new Error("git_sync_failed"), { status: res.status, data });
  return data as GitSyncResponse;
};

