export enum MessageType {
  INIT = "init",
  LOAD_CODE = "load_code",
  ERROR = "error",
  PING = "ping",
  AGENT_FINAL = "agent_final",
  AGENT_PARTIAL = "agent_partial",
  USER = "user",
  UPDATE_IN_PROGRESS = "update_in_progress",
  UPDATE_FILE = "update_file",
  UPDATE_COMPLETED = "update_completed",
  TRACE_EVENT = "trace_event",
  HITL_REQUEST = "hitl_request",
  HITL_RESPONSE = "hitl_response",
  RUNTIME_ERROR = "runtime_error",
  SESSION_CLAIMED = "session_claimed",
}

export enum Sender {
  ASSISTANT = "assistant",
  USER = "user",
}

export type JsonObject = Record<string, unknown>;

export type HitlDecisionType = "approve" | "edit" | "reject";

export interface HitlActionRequest {
  name: string;
  args: JsonObject;
  description?: string;
}

export interface HitlReviewConfig {
  action_name: string;
  allowed_decisions: HitlDecisionType[];
  args_schema?: JsonObject;
}

export interface HitlRequest {
  action_requests: HitlActionRequest[];
  review_configs: HitlReviewConfig[];
}

export type HitlDecision =
  | { type: "approve" }
  | { type: "reject"; message?: string }
  | { type: "edit"; edited_action: { name: string; args: JsonObject } };

export type RuntimeErrorSource = "console" | "window" | "promise" | "bridge";

export interface RuntimeErrorPayload {
  kind: string;
  message: string;
  stack?: string;
  url?: string;
  ts_ms?: number;
  fingerprint?: string;
  level?: "error";
  source?: RuntimeErrorSource;
  args_preview?: string;
  extra?: JsonObject;
}

export type MessageData = JsonObject & {
  text?: string;
  sender?: Sender;
  isStreaming?: boolean;
  error?: RuntimeErrorPayload | unknown;
  content_blocks?: JsonObject[];

  // Optional: associate trace events with the assistant message they belong to.
  // (Backend may omit this; frontend can best-effort infer in that case.)
  assistant_msg_id?: string;

  // Optional generative UI blocks parsed from assistant text.
  ui_blocks?: JsonObject[];

  url?: string;
  sandbox_id?: string;
  exists?: boolean;

  hitl_pending?: { interrupt_id: string; request: HitlRequest };
  interrupt_id?: string;
  request?: HitlRequest;
  response?: { decisions: HitlDecision[] };

  // Trace events (tool start/end/error, etc.)
  phase?: "tool_start" | "tool_end" | "tool_error" | string;
  tool_name?: string;
  input?: JsonObject | unknown;
  output?: JsonObject | unknown;
  run_id?: string;
  parent_ids?: string[];
  tags?: string[];
};

export interface Message {
  type: MessageType;
  data: MessageData;
  id?: string;
  timestamp?: number;
  session_id?: string;
}

export const createMessage = (
  type: MessageType,
  data: MessageData = {},
  id?: string,
  timestamp?: number,
  session_id?: string
): Message => ({
  type,
  data,
  id,
  timestamp: timestamp || Date.now(),
  session_id,
});
