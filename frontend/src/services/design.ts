import { AGENT_CONFIG } from "@/config/agent";
import type {
  DesignGeneratePayload,
  DesignSnapshotResponse,
  DesignState,
} from "@/types/design";

const agentUrl = (path: string) => new URL(path, AGENT_CONFIG.HTTP_URL).toString();

const readJson = async (res: Response): Promise<unknown> => {
  try {
    return (await res.json()) as unknown;
  } catch {
    return null;
  }
};

export const designCreateApproaches = async (
  projectId: string,
  payload: DesignGeneratePayload
): Promise<DesignState> => {
  const url = agentUrl(`/api/design/${encodeURIComponent(projectId)}/approaches`);
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "include",
    body: JSON.stringify(payload || {}),
  });
  const data = await readJson(res);
  if (!res.ok)
    throw Object.assign(new Error("design_approaches_failed"), {
      status: res.status,
      data,
    });
  return data as DesignState;
};

export const designRegenerateApproaches = async (
  projectId: string,
  payload: DesignGeneratePayload
): Promise<DesignState> => {
  const url = agentUrl(
    `/api/design/${encodeURIComponent(projectId)}/approaches/regenerate`
  );
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "include",
    body: JSON.stringify(payload || {}),
  });
  const data = await readJson(res);
  if (!res.ok)
    throw Object.assign(new Error("design_regenerate_failed"), {
      status: res.status,
      data,
    });
  return data as DesignState;
};

export const designSelectApproach = async (
  projectId: string,
  payload: {
    approach_id: string;
    total_iterations?: number;
    pending_continue_decision?: boolean;
  }
): Promise<DesignState> => {
  const url = agentUrl(`/api/design/${encodeURIComponent(projectId)}/select`);
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "include",
    body: JSON.stringify(payload || {}),
  });
  const data = await readJson(res);
  if (!res.ok)
    throw Object.assign(new Error("design_select_failed"), {
      status: res.status,
      data,
    });
  return data as DesignState;
};

export const designGetState = async (projectId: string): Promise<DesignState> => {
  const url = agentUrl(`/api/design/${encodeURIComponent(projectId)}/state`);
  const res = await fetch(url, { credentials: "include" });
  const data = await readJson(res);
  if (!res.ok)
    throw Object.assign(new Error("design_state_failed"), {
      status: res.status,
      data,
    });
  return data as DesignState;
};

export const designCaptureSnapshot = async (
  projectId: string,
  payload: {
    path?: string;
    viewport_width?: number;
    viewport_height?: number;
    full_page?: boolean;
    device_type?: "mobile" | "tablet" | "desktop";
  }
): Promise<DesignSnapshotResponse> => {
  const url = agentUrl(`/api/design/${encodeURIComponent(projectId)}/snapshot`);
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "include",
    body: JSON.stringify(payload || {}),
  });
  const data = await readJson(res);
  if (!res.ok)
    throw Object.assign(new Error("design_snapshot_failed"), {
      status: res.status,
      data,
    });
  return data as DesignSnapshotResponse;
};
