import { AGENT_CONFIG } from "@/config/agent";
import type {
  DbSchemaApplyResponse,
  DbSchema,
  DbSchemaGetResponse,
  DbSchemaIntentResponse,
  DbSchemaReviewResponse,
} from "@/types/dbSchema";

const agentUrl = (path: string) => new URL(path, AGENT_CONFIG.HTTP_URL).toString();

const readJson = async (res: Response): Promise<unknown> => {
  try {
    return (await res.json()) as unknown;
  } catch {
    return null;
  }
};

export const dbSchemaGet = async (projectId: string): Promise<DbSchemaGetResponse> => {
  const url = agentUrl(`/api/db/${encodeURIComponent(projectId)}/schema`);
  const res = await fetch(url, { credentials: "include" });
  const data = await readJson(res);
  if (!res.ok)
    throw Object.assign(new Error("db_schema_get_failed"), {
      status: res.status,
      data,
    });
  return data as DbSchemaGetResponse;
};

export const dbSchemaReview = async (
  projectId: string,
  payload: { base_version?: string; draft: DbSchema }
): Promise<DbSchemaReviewResponse> => {
  const url = agentUrl(`/api/db/${encodeURIComponent(projectId)}/schema/review`);
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "include",
    body: JSON.stringify(payload),
  });
  const data = await readJson(res);
  if (!res.ok)
    throw Object.assign(new Error("db_schema_review_failed"), {
      status: res.status,
      data,
    });
  return data as DbSchemaReviewResponse;
};

export const dbSchemaIntent = async (
  projectId: string,
  payload: { base_version?: string; draft: DbSchema; intent_text: string }
): Promise<DbSchemaIntentResponse> => {
  const url = agentUrl(`/api/db/${encodeURIComponent(projectId)}/schema/intent`);
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "include",
    body: JSON.stringify(payload),
  });
  const data = await readJson(res);
  if (!res.ok)
    throw Object.assign(new Error("db_schema_intent_failed"), {
      status: res.status,
      data,
    });
  return data as DbSchemaIntentResponse;
};

export const dbSchemaApply = async (
  projectId: string,
  payload: { base_version?: string; draft: DbSchema; confirm_destructive: boolean }
): Promise<DbSchemaApplyResponse> => {
  const url = agentUrl(`/api/db/${encodeURIComponent(projectId)}/schema/apply`);
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "include",
    body: JSON.stringify(payload),
  });
  const data = await readJson(res);
  if (!res.ok)
    throw Object.assign(new Error("db_schema_apply_failed"), {
      status: res.status,
      data,
    });
  return data as DbSchemaApplyResponse;
};
