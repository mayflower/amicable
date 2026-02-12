import {
  ComputerIcon,
  ExternalLink,
  Loader2,
  Paperclip,
  PhoneIcon,
  Play,
  RotateCcw,
  TabletIcon,
  X,
} from "lucide-react";
import {
  MessageType,
  Sender,
  type HitlActionRequest,
  type HitlDecision,
  type HitlDecisionType,
  type HitlRequest,
  type HitlReviewConfig,
  type JsonObject,
  type RuntimeErrorPayload,
} from "../../types/messages";
import { ProjectLockedModal } from "@/components/ProjectLockedModal";
import { SessionClaimedModal } from "@/components/SessionClaimedModal";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type ChangeEvent,
} from "react";

import { AGENT_CONFIG } from "../../config/agent";
import { AgentAuthStatus } from "../../components/AgentAuthStatus";
import { ChatMarkdown } from "../../components/ChatMarkdown";
import { Button } from "@/components/ui/button";
import { CodePane } from "@/components/CodePane";
import { DatabasePane } from "@/components/DatabasePane";
import { Input } from "@/components/ui/input";
import type { Message } from "../../types/messages";
import { cn } from "@/lib/utils";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useMessageBus } from "../../hooks/useMessageBus";
import { useAgentAuth } from "../../hooks/useAgentAuth";

const DEVICE_SPECS = {
  mobile: { width: 390, height: 844 },
  tablet: { width: 768, height: 1024 },
  desktop: { width: "100%", height: "100%" },
};

const MAX_IMAGE_ATTACHMENTS = 4;
const MAX_IMAGE_FILE_BYTES = 5 * 1024 * 1024;

type PendingImageAttachment = {
  name: string;
  mimeType: string;
  base64: string;
  size: number;
};

const readFileAsDataUrl = (file: File): Promise<string> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const out = reader.result;
      if (typeof out === "string") {
        resolve(out);
      } else {
        reject(new Error("Failed to read file"));
      }
    };
    reader.onerror = () => reject(reader.error || new Error("Failed to read file"));
    reader.readAsDataURL(file);
  });

type _ToggleButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  active?: boolean;
};

const ToggleButton = ({ active, className, type, ...props }: _ToggleButtonProps) => {
  return (
    <button
      type={type ?? "button"}
      className={cn(
        "border border-gray-300 rounded-md px-4 py-1.5 text-[15px] font-medium transition disabled:cursor-not-allowed disabled:text-gray-400",
        active ? "bg-gray-50 text-gray-800" : "bg-gray-200 text-gray-500 hover:bg-gray-300",
        className
      )}
      {...props}
    />
  );
};

type _DeviceButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  active?: boolean;
};

const DeviceButton = ({ active, className, type, ...props }: _DeviceButtonProps) => {
  return (
    <button
      type={type ?? "button"}
      className={cn(
        "border border-gray-300 rounded-md px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:text-gray-400 flex items-center justify-center",
        active ? "bg-blue-500 text-white hover:bg-blue-700" : "bg-gray-200 text-gray-500 hover:bg-blue-700 hover:text-white",
        className
      )}
      {...props}
    />
  );
};

const extractUiBlocks = (
  raw: string
): { text: string; uiBlocks: JsonObject[] } => {
  const text = typeof raw === "string" ? raw : "";
  const uiBlocks: JsonObject[] = [];

  // Support model-emitted blocks:
  // ```ui
  // { ...json... }
  // ```
  const re = /```ui\s*([\s\S]*?)```/gi;
  let cleaned = text;
  let match: RegExpExecArray | null;
  while ((match = re.exec(text)) !== null) {
    const body = match[1] || "";
    try {
      const parsed = JSON.parse(body);
      if (parsed && typeof parsed === "object") {
        uiBlocks.push(parsed as JsonObject);
      }
    } catch {
      // ignore parse errors, still strip
    }
    cleaned = cleaned.replace(match[0], "").trim();
  }

  return { text: cleaned, uiBlocks };
};

const stripUiBlocks = (raw: string): string => {
  const text = typeof raw === "string" ? raw : "";
  return text.replace(/```ui[\s\S]*?```/gi, "").trim();
};

type CreateRouteState = {
  session_id?: string;
  project_id?: string;
  initialPrompt?: string;
};

const asObj = (v: unknown): Record<string, unknown> | null => {
  return v && typeof v === "object" && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : null;
};

const Create = () => {
  const [inputValue, setInputValue] = useState("");
  const [chatWidth, setChatWidth] = useState(420);
  const [isChatResizing, setIsChatResizing] = useState(false);
  const isResizing = isChatResizing;
  const [messages, setMessages] = useState<Message[]>([]);
  const [iframeUrl, setIframeUrl] = useState("");
  const [rawIframeUrl, setRawIframeUrl] = useState("");
  const [iframeError, setIframeError] = useState(false);
  const [iframeReady, setIframeReady] = useState(false);
  const [isUpdateInProgress, setIsUpdateInProgress] = useState(false);
  // Small bottom status line: driven by UPDATE_FILE messages.
  const [agentStatusText, setAgentStatusText] = useState<string>("");
  const [initCompleted, setInitCompleted] = useState(false);
  const [sandboxExists, setSandboxExists] = useState(false);
  const [pendingHitl, setPendingHitl] = useState<{
    interruptId: string;
    request: HitlRequest;
  } | null>(null);
  const chatHistoryRef = useRef<HTMLDivElement>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const isConnectedRef = useRef(false);
  const sendRef = useRef<(type: MessageType, payload: Record<string, unknown>) => void>(
    () => {}
  );
  const runtimeErrorRecentRef = useRef<Map<string, number>>(new Map());
  const runtimeProbeSeqRef = useRef(0);
  const processedMessageIds = useRef<Set<string>>(new Set());
  const location = useLocation();
  const routeState = (location.state as unknown as CreateRouteState | null) ?? null;
  const navigate = useNavigate();
  const params = useParams();
  const [searchParams] = useSearchParams();
  const querySessionId =
    searchParams.get("session_id") || routeState?.session_id;
  const slug = typeof params.slug === "string" ? params.slug : null;
  const [resolvedSessionId, setResolvedSessionId] = useState<string | null>(
    querySessionId || routeState?.project_id || null
  );
  const [slugResolutionStatus, setSlugResolutionStatus] = useState<
    "idle" | "loading" | "resolved" | "not_found" | "error"
  >("idle");
  const [slugResolutionError, setSlugResolutionError] = useState<string | null>(
    null
  );
  const [projectInfo, setProjectInfo] = useState<{
    project_id: string;
    name: string;
    slug: string;
  } | null>(null);
  const redirectedFromLegacy = useRef(false);
  const initialPromptSent = useRef(false);
  const [selectedDevice, setSelectedDevice] = useState<
    "mobile" | "tablet" | "desktop"
  >("desktop");
  const { loading: authLoading, mode: authMode, user: authUser, loginUrl } =
    useAgentAuth();
  const [agentTouchedPath, setAgentTouchedPath] = useState<string | null>(null);
  const toolFileByRunId = useRef<Map<string, string>>(new Map());
  const latestAssistantMsgIdRef = useRef<string | null>(null);
  const [mainView, setMainView] = useState<"preview" | "code" | "database">("preview");
  const [pendingImages, setPendingImages] = useState<PendingImageAttachment[]>([]);
  const [attachmentError, setAttachmentError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [projectLockedInfo, setProjectLockedInfo] = useState<{
    email: string;
    lockedAt?: string;
  } | null>(null);
  const [sessionClaimed, setSessionClaimed] = useState<{
    byEmail?: string;
  } | null>(null);

  type ToolRun = {
    runId: string;
    toolName: string;
    startTs?: number;
    endTs?: number;
    status: "running" | "success" | "error";
    input?: unknown;
    output?: unknown;
    error?: unknown;
    explanations: string[];
  };

  // Trace events can be extremely chatty. Keep an incrementally-aggregated view instead
  // of appending every trace_event into `messages` (which causes O(n) re-aggregation and
  // huge DOM growth during streaming).
  const toolRunsByIdRef = useRef<Map<string, ToolRun>>(new Map());
  const runToAssistantMsgIdRef = useRef<Map<string, string>>(new Map());
  const reasoningByAssistantMsgIdRef = useRef<
    Map<string, { key: string; ts: number; text: string }[]>
  >(new Map());
  const assistantTraceFirstTsRef = useRef<Map<string, number>>(new Map());
  type AssistantStreamItem =
    | { kind: "text"; key: string; ts: number; text: string }
    | { kind: "tool"; key: string; ts: number; runId: string }
    | { kind: "reasoning"; key: string; ts: number; text: string };
  const assistantTimelineRef = useRef<Map<string, AssistantStreamItem[]>>(new Map());
  const assistantLastFullTextRef = useRef<Map<string, string>>(new Map());
  const assistantOpenTextKeyRef = useRef<Map<string, string | null>>(new Map());
  const assistantTextSeqRef = useRef<Map<string, number>>(new Map());
  const [traceVersion, setTraceVersion] = useState(0);

  useEffect(() => {
    if (authLoading) return;
    if (authMode === "google" && !authUser) {
      window.location.href = loginUrl;
    }
  }, [authLoading, authMode, authUser, loginUrl]);

  // Debug log for session_id
  useEffect(() => {
    if (resolvedSessionId) {
      console.log("Session ID initialized:", resolvedSessionId);
    }
  }, [resolvedSessionId]);

  const refreshIframe = useCallback(() => {
    if (iframeRef.current && iframeUrl && iframeUrl !== "/") {
      setIframeReady(false);
      setIframeError(false);

      // First refresh
      const currentSrc = iframeRef.current.src;
      iframeRef.current.src = "";

      setTimeout(() => {
        if (iframeRef.current) {
          iframeRef.current.src = currentSrc;

          // Second refresh after a longer delay
          setTimeout(() => {
            if (iframeRef.current) {
              iframeRef.current.src = "";

              setTimeout(() => {
                if (iframeRef.current) {
                  iframeRef.current.src = currentSrc;
                }
              }, 200);
            }
          }, 500);
        }
      }, 300);
    }
  }, [iframeUrl]);

  const hash = useCallback((s: string): string => {
    let h = 5381;
    for (let i = 0; i < s.length; i++) h = ((h << 5) + h) ^ s.charCodeAt(i);
    return (h >>> 0).toString(16);
  }, []);

  const trunc = useCallback((s: unknown, n: number): string => {
    const v = typeof s === "string" ? s : String(s ?? "");
    if (v.length <= n) return v;
    return v.slice(0, Math.max(0, n - 3)) + "...";
  }, []);

  const shouldSkipRuntimeFingerprint = useCallback((fingerprint: string, now: number) => {
    const recent = runtimeErrorRecentRef.current;
    const maxRecent = 200;
    const windowMs = 10 * 60 * 1000;
    const prev = recent.get(fingerprint);
    if (typeof prev === "number" && now - prev < windowMs) return true;
    recent.set(fingerprint, now);
    if (recent.size > maxRecent) {
      const items = [...recent.entries()].sort((a, b) => a[1] - b[1]);
      for (let i = 0; i < items.length - maxRecent; i++) {
        recent.delete(items[i]![0]);
      }
    }
    return false;
  }, []);

  const sendRuntimeError = useCallback(
    (error: RuntimeErrorPayload) => {
      if (!resolvedSessionId || !isConnectedRef.current) return;
      const now = Date.now();
      const kind = typeof error.kind === "string" ? error.kind : "window_error";
      const message = trunc(error.message, 2000);
      const stack = typeof error.stack === "string" ? trunc(error.stack, 8000) : undefined;
      const url = typeof error.url === "string" ? trunc(error.url, 2000) : undefined;
      const argsPreview =
        typeof error.args_preview === "string" ? trunc(error.args_preview, 4000) : undefined;
      const tsMs = typeof error.ts_ms === "number" ? error.ts_ms : now;
      const base = `${kind}|${message}|${stack || ""}|${url || ""}|${argsPreview || ""}`;
      const fingerprint =
        typeof error.fingerprint === "string" && error.fingerprint
          ? error.fingerprint
          : `rt_${hash(base)}`;

      if (shouldSkipRuntimeFingerprint(fingerprint, now)) return;

      sendRef.current(MessageType.RUNTIME_ERROR, {
        session_id: resolvedSessionId,
        error: {
          kind,
          message,
          stack,
          url,
          ts_ms: tsMs,
          fingerprint,
          level: error.level,
          source: error.source,
          args_preview: argsPreview,
          extra: error.extra,
        },
      });
    },
    [resolvedSessionId, trunc, hash, shouldSkipRuntimeFingerprint]
  );

  const runRuntimeBridgeProbe = useCallback(
    (trigger: "iframe_load" | "update_completed") => {
      const iframeWindow = iframeRef.current?.contentWindow;
      const iframeSrc = rawIframeUrl || iframeUrl;
      if (!iframeWindow || !iframeSrc) return;

      let allowedOrigin = "";
      try {
        allowedOrigin = new URL(iframeSrc).origin;
      } catch {
        allowedOrigin = "";
      }
      if (!allowedOrigin) return;

      const probeId = `probe_${++runtimeProbeSeqRef.current}_${Date.now()}`;
      const fingerprint = `bridge_${hash(`${allowedOrigin}|${trigger}`)}`;
      let done = false;

      const cleanup = () => {
        window.removeEventListener("message", onMessage);
      };

      const onMessage = (event: MessageEvent) => {
        if (done) return;
        if (!event?.data || typeof event.data !== "object") return;
        if (event.origin !== allowedOrigin) return;
        const dataObj = asObj(event.data);
        if (!dataObj || dataObj.type !== "amicable_runtime_probe_ack") return;
        if (dataObj.probe_id !== probeId) return;
        done = true;
        cleanup();
      };

      window.addEventListener("message", onMessage);

      const timeoutId = window.setTimeout(() => {
        if (done) return;
        done = true;
        cleanup();
        sendRuntimeError({
          kind: "runtime_bridge_missing",
          message: "Runtime bridge probe was not acknowledged by preview iframe",
          source: "bridge",
          level: "error",
          url: iframeSrc,
          fingerprint,
          extra: { trigger, probe_id: probeId },
        });
      }, 1500);

      try {
        iframeWindow.postMessage(
          { type: "amicable_runtime_probe", probe_id: probeId },
          allowedOrigin
        );
      } catch {
        window.clearTimeout(timeoutId);
        done = true;
        cleanup();
        sendRuntimeError({
          kind: "runtime_bridge_missing",
          message: "Failed to send runtime bridge probe to preview iframe",
          source: "bridge",
          level: "error",
          url: iframeSrc,
          fingerprint,
          extra: { trigger, probe_id: probeId },
        });
      }
    },
    [rawIframeUrl, iframeUrl, hash, sendRuntimeError]
  );

  // Message handlers for different message types
  const messageHandlers = {
    [MessageType.INIT]: (message: Message) => {
      const id = message.id;
      if (id) {
        if (processedMessageIds.current.has(id)) {
          console.log("Skipping duplicate INIT message:", id);
          return;
        }
        processedMessageIds.current.add(id);
        console.log("Processing INIT message:", id);
      }

      if (typeof message.data.url === "string" && message.data.sandbox_id) {
        const raw = message.data.url;
        setRawIframeUrl(raw);
        try {
          const u = new URL(raw, window.location.origin);
          u.searchParams.set(
            "amicableParentOrigin",
            window.location.origin
          );
          setIframeUrl(u.toString());
        } catch {
          const sep = raw.includes("?") ? "&" : "?";
          setIframeUrl(
            `${raw}${sep}amicableParentOrigin=${encodeURIComponent(window.location.origin)}`
          );
        }
        setIframeError(false);
      }
      // Backfill session id for WS-generated sessions.
      if (!resolvedSessionId && typeof message.session_id === "string") {
        setResolvedSessionId(message.session_id);
      }

      // Check if sandbox already exists
      if (message.data.exists === true) {
        setSandboxExists(true);
        console.log("Sandbox already exists, skipping initial prompt");
      }

      setMessages((prev) => {
        // Only show one "Workspace loaded!" message — update in place on reconnect.
        const existingInitIndex = prev.findIndex(
          (msg) =>
            msg.type === MessageType.INIT ||
            msg.data?.text === "Workspace loaded! You can now make edits here."
        );
        const entry = {
          ...message,
          timestamp: message.timestamp || Date.now(),
          data: {
            ...message.data,
            text: "Workspace loaded! You can now make edits here.",
            sender: Sender.ASSISTANT,
          },
        };
        if (existingInitIndex !== -1) {
          return prev.map((msg, idx) =>
            idx === existingInitIndex ? { ...msg, ...entry } : msg
          );
        }
        return [...prev, entry];
      });
      setInitCompleted(true);

      // If the server reports a pending HITL request (e.g., reconnect), surface it.
      const hp = message.data.hitl_pending;
      if (hp?.interrupt_id && hp?.request) {
        setPendingHitl({ interruptId: hp.interrupt_id, request: hp.request });
      }

      const md = asObj(message.data);
      const proj = md ? asObj(md.project) : null;
      if (
        proj &&
        typeof proj.project_id === "string" &&
        typeof proj.name === "string" &&
        typeof proj.slug === "string"
      ) {
        setProjectInfo({
          project_id: proj.project_id,
          name: proj.name,
          slug: proj.slug,
        });
      }
    },

    [MessageType.ERROR]: (message: Message) => {
      // Check for project_locked error
      const md = asObj(message.data);
      if (md && md.code === "project_locked") {
        const lockedBy = md.locked_by as { email?: string; at?: string } | undefined;
        setProjectLockedInfo({
          email: lockedBy?.email || "another user",
          lockedAt: lockedBy?.at,
        });
        return;
      }
      setMessages((prev) => [
        ...prev,
        {
          ...message,
          timestamp: message.timestamp || Date.now(),
          data: {
            ...message.data,
            sender: Sender.ASSISTANT,
          },
        },
      ]);
    },

    [MessageType.SESSION_CLAIMED]: (message: Message) => {
      const md = asObj(message.data);
      setSessionClaimed({
        byEmail: md?.claimed_by_email as string | undefined,
      });
    },

    [MessageType.AGENT_PARTIAL]: (message: Message) => {
      const text = message.data.text;
      const id = message.id;

      if (!id) {
        console.warn("AGENT_PARTIAL message missing id, ignoring:", message);
        return;
      }
      latestAssistantMsgIdRef.current = id;

      if (text && text.trim()) {
        const cleaned = stripUiBlocks(text.replace(/\\/g, ""));

        // Build an interleaved stream timeline: text segments + tool cards inserted by trace events.
        // We assume partials are append-only (cumulative text). If not, we fall back to replacing
        // the current open text segment.
        try {
          const ts = typeof message.timestamp === "number" ? message.timestamp : Date.now();
          const prevFull = assistantLastFullTextRef.current.get(id) || "";
          const isAppend = cleaned.startsWith(prevFull);
          const delta = isAppend ? cleaned.slice(prevFull.length) : cleaned;
          assistantLastFullTextRef.current.set(id, cleaned);

          if (!isAppend) {
            const seq = 1;
            assistantTextSeqRef.current.set(id, seq);
            const key = `text-${id}-${seq}`;
            assistantTimelineRef.current.set(id, [{ kind: "text", key, ts, text: cleaned }]);
            assistantOpenTextKeyRef.current.set(id, key);
            setTraceVersion((v) => v + 1);
          } else if (delta) {
            const timeline = assistantTimelineRef.current.get(id) || [];
            const openKey = assistantOpenTextKeyRef.current.get(id) || null;
            const last = timeline.length ? timeline[timeline.length - 1] : null;

            if (openKey && last && last.kind === "text" && last.key === openKey) {
              last.text += delta;
            } else {
              const seq = (assistantTextSeqRef.current.get(id) || 0) + 1;
              assistantTextSeqRef.current.set(id, seq);
              const key = `text-${id}-${seq}`;
              timeline.push({ kind: "text", key, ts, text: delta });
              assistantTimelineRef.current.set(id, timeline);
              assistantOpenTextKeyRef.current.set(id, key);
            }
            setTraceVersion((v) => v + 1);
          }
        } catch {
          // ignore
        }

        setMessages((prev) => {
          const existingIndex = prev.findIndex((msg) => msg.id === id);
          if (existingIndex !== -1) {
            return prev.map((msg, idx) =>
              idx === existingIndex
                ? {
                    ...msg,
                    // Keep stable ordering while streaming; don't update the timestamp
                    // on every partial chunk.
                    timestamp: msg.timestamp || message.timestamp || Date.now(),
                    data: {
                      ...msg.data,
                      text: cleaned,
                      sender: Sender.ASSISTANT,
                      isStreaming: true,
                    },
                  }
                : msg
            );
          }
          // Insert new
          return [
            ...prev,
            {
              ...message,
              timestamp: message.timestamp || Date.now(),
              data: {
                ...message.data,
                text: cleaned,
                isStreaming: true,
                sender: Sender.ASSISTANT,
              },
            },
          ];
        });
      }
    },

    [MessageType.AGENT_FINAL]: (message: Message) => {
      const text = message.data.text;
      const id = message.id;
      if (!id) {
        console.warn("AGENT_FINAL message missing id, ignoring:", message);
        return;
      }
      latestAssistantMsgIdRef.current = id;
      if (text && text.trim()) {
        const cleanedText = text.replace(/\\/g, "");
        const extracted = extractUiBlocks(cleanedText);

        // Finalize stream timeline for this assistant message.
        try {
          const ts = typeof message.timestamp === "number" ? message.timestamp : Date.now();
          const prevFull = assistantLastFullTextRef.current.get(id) || "";
          const nextFull = extracted.text || "";
          const isAppend = nextFull.startsWith(prevFull);
          const delta = isAppend ? nextFull.slice(prevFull.length) : nextFull;
          assistantLastFullTextRef.current.set(id, nextFull);

          if (!isAppend) {
            const seq = 1;
            assistantTextSeqRef.current.set(id, seq);
            const key = `text-${id}-${seq}`;
            assistantTimelineRef.current.set(id, [{ kind: "text", key, ts, text: nextFull }]);
            assistantOpenTextKeyRef.current.set(id, key);
            setTraceVersion((v) => v + 1);
          } else if (delta) {
            const timeline = assistantTimelineRef.current.get(id) || [];
            const openKey = assistantOpenTextKeyRef.current.get(id) || null;
            const last = timeline.length ? timeline[timeline.length - 1] : null;

            if (openKey && last && last.kind === "text" && last.key === openKey) {
              last.text += delta;
            } else {
              const seq = (assistantTextSeqRef.current.get(id) || 0) + 1;
              assistantTextSeqRef.current.set(id, seq);
              const key = `text-${id}-${seq}`;
              timeline.push({ kind: "text", key, ts, text: delta });
              assistantTimelineRef.current.set(id, timeline);
              assistantOpenTextKeyRef.current.set(id, key);
            }
            setTraceVersion((v) => v + 1);
          }
        } catch {
          // ignore
        }

        setMessages((prev) => {
          const existingIndex = prev.findIndex((msg) => msg.id === id);
          if (existingIndex !== -1) {
            return prev.map((msg, idx) =>
              idx === existingIndex
                ? {
                    ...msg,
                    timestamp: msg.timestamp || message.timestamp || Date.now(),
                    data: {
                      ...msg.data,
                      text: extracted.text,
                      ui_blocks: extracted.uiBlocks,
                      isStreaming: false,
                      sender: Sender.ASSISTANT,
                    },
                  }
                : msg
            );
          }
          // Insert new
          return [
            ...prev,
            {
              ...message,
              timestamp: message.timestamp || Date.now(),
              data: {
                ...message.data,
                text: extracted.text,
                ui_blocks: extracted.uiBlocks,
                isStreaming: false,
                sender: Sender.ASSISTANT,
              },
            },
          ];
        });
      }
    },

    [MessageType.UPDATE_IN_PROGRESS]: (message: Message) => {
      setIsUpdateInProgress(true);
      setAgentStatusText("");

      const id = message.id;

      setMessages((prev) => {
        if (id) {
          const existingIndex = prev.findIndex((msg) => msg.id === id);
          if (existingIndex !== -1) {
            return prev.map((msg, idx) =>
              idx === existingIndex
                ? {
                    ...msg,
                    timestamp: message.timestamp || msg.timestamp,
                    data: {
                      ...msg.data,
                      text: "Ok - I'll make those changes!",
                      sender: Sender.ASSISTANT,
                    },
                  }
                : msg
            );
          }
        }

        return [
          ...prev,
          {
            ...message,
            timestamp: message.timestamp || Date.now(),
            data: {
              ...message.data,
              text: "Ok - I'll make those changes!",
              sender: Sender.ASSISTANT,
            },
          },
        ];
      });
    },

    [MessageType.UPDATE_FILE]: (message: Message) => {
      const id = message.id;
      if (!id) {
        console.warn("UPDATE_FILE message missing id, ignoring:", message);
        return;
      }
      const t = typeof message.data?.text === "string" ? message.data.text : "";
      if (t.trim()) setAgentStatusText(t);
      setMessages((prev) => {
        const existingIndex = prev.findIndex((msg) => msg.id === id);
        if (existingIndex !== -1) {
          return prev.map((msg, idx) =>
            idx === existingIndex
              ? {
                  ...msg,
                  timestamp: message.timestamp || msg.timestamp,
                  data: {
                    ...msg.data,
                    text: message.data.text,
                    sender: Sender.ASSISTANT,
                    isStreaming: true,
                  },
                }
              : msg
          );
        }
        // Insert new
        return [
          ...prev,
          {
            ...message,
            timestamp: message.timestamp || Date.now(),
            data: {
              ...message.data,
              text: message.data.text,
              sender: Sender.ASSISTANT,
              isStreaming: true,
            },
          },
        ];
      });
    },

    [MessageType.UPDATE_COMPLETED]: (message: Message) => {
      setIsUpdateInProgress(false);
      setAgentStatusText("");
      const id = message.id;
      setMessages((prev) => {
        const filtered = prev;

        if (id) {
          const existingIndex = filtered.findIndex((msg) => msg.id === id);
          if (existingIndex !== -1) {
            return filtered.map((msg, idx) =>
              idx === existingIndex
                ? {
                    ...msg,
                    timestamp: message.timestamp || msg.timestamp || Date.now(),
                    data: {
                      ...msg.data,
                      text: "Update completed!",
                      sender: Sender.ASSISTANT,
                    },
                  }
                : msg
            );
          }
        }
        // Insert new
        return [
          ...filtered,
          {
            ...message,
            timestamp: message.timestamp || Date.now(),
            data: {
              ...message.data,
              text: "Update completed!",
              sender: Sender.ASSISTANT,
            },
          },
        ];
      });
      refreshIframe();
      window.setTimeout(() => {
        runRuntimeBridgeProbe("update_completed");
      }, 1800);
    },

    [MessageType.HITL_REQUEST]: (message: Message) => {
      const interruptId = message.data.interrupt_id;
      const request = message.data.request;
      if (typeof interruptId !== "string" || !interruptId || !request) {
        console.warn("HITL_REQUEST missing interrupt_id:", message);
        return;
      }
      setPendingHitl({ interruptId, request });
      // Consider this a paused state rather than "updating".
      setIsUpdateInProgress(false);
    },

    [MessageType.TRACE_EVENT]: (message: Message) => {
	      // Render tool runs inline in the chat timeline. Keep trace aggregation incremental
	      // to avoid unbounded message growth and expensive re-aggregation on every update.
	      const ts = typeof message.timestamp === "number" ? message.timestamp : Date.now();
	      const explicitAssistantMsgId =
	        typeof message.data.assistant_msg_id === "string" && message.data.assistant_msg_id
	          ? message.data.assistant_msg_id
	          : "";
	      const assistantMsgId = explicitAssistantMsgId || latestAssistantMsgIdRef.current || "";

      if (assistantMsgId) {
        const prev = assistantTraceFirstTsRef.current.get(assistantMsgId);
        if (typeof prev !== "number" || ts < prev) {
          assistantTraceFirstTsRef.current.set(assistantMsgId, ts);
        }
      }

      try {
        const phase = typeof message.data.phase === "string" ? message.data.phase : "";
        const toolName =
          typeof message.data.tool_name === "string" ? message.data.tool_name : "";
        const runId = typeof message.data.run_id === "string" ? message.data.run_id : "";

        if (
          (toolName === "write_file" || toolName === "edit_file") &&
          (phase === "tool_start" || phase === "tool_end")
        ) {
          if (phase === "tool_start") {
            const inputObj = asObj(message.data.input);
            const fpRaw = inputObj ? inputObj.file_path ?? inputObj.path : undefined;
            const fp = typeof fpRaw === "string" ? fpRaw : undefined;
            if (typeof fp === "string" && fp.trim()) {
              const norm = fp.startsWith("/") ? fp : `/${fp}`;
              if (runId) toolFileByRunId.current.set(runId, norm);
              setAgentTouchedPath(norm);
            }
          } else if (phase === "tool_end") {
            const fp = runId ? toolFileByRunId.current.get(runId) : undefined;
            if (fp) setAgentTouchedPath(fp);
            if (runId) toolFileByRunId.current.delete(runId);
          }
        }
      } catch {
        // ignore
      }

      try {
        const phase = typeof message.data.phase === "string" ? message.data.phase : "";
        const runId = typeof message.data.run_id === "string" ? message.data.run_id : "";
        const toolName =
          typeof message.data.tool_name === "string" ? message.data.tool_name : "";

        if (phase === "reasoning_summary") {
          if (assistantMsgId) {
            const text = typeof message.data.text === "string" ? message.data.text : "";
            if (text.trim()) {
              const arr = reasoningByAssistantMsgIdRef.current.get(assistantMsgId) || [];
              const key = message.id || `reason-${ts}`;
              arr.push({ key, ts, text });
              reasoningByAssistantMsgIdRef.current.set(assistantMsgId, arr);

              const timeline = assistantTimelineRef.current.get(assistantMsgId) || [];
              timeline.push({ kind: "reasoning", key: `reason-${key}`, ts, text });
              assistantTimelineRef.current.set(assistantMsgId, timeline);
              // Next text should start a new segment after this reasoning block.
              assistantOpenTextKeyRef.current.set(assistantMsgId, null);
            }
          }
          setTraceVersion((v) => v + 1);
          return;
        }

        // Tool events: aggregate by run_id.
        if (!runId || !toolName) {
          setTraceVersion((v) => v + 1);
          return;
        }

        const byId = toolRunsByIdRef.current;
        const cur: ToolRun =
          byId.get(runId) ||
          ({
            runId,
            toolName,
            status: "running",
            explanations: [],
          } as ToolRun);

        cur.toolName = toolName;
        if (!cur.startTs) cur.startTs = ts;

        if (phase === "tool_start") {
          cur.startTs = ts;
          cur.input = message.data.input;
          cur.status = "running";
        } else if (phase === "tool_end") {
          cur.endTs = ts;
          cur.output = message.data.output;
          cur.status = "success";
        } else if (phase === "tool_error") {
          cur.endTs = ts;
          cur.error = message.data.error;
          cur.status = "error";
        } else if (phase === "tool_explain") {
          const t = typeof message.data.text === "string" ? message.data.text : "";
          if (t) cur.explanations.push(t.replace(/^\[explain\]\s*/i, "").trim());
        }

        byId.set(runId, cur);

        // Attach the run to an assistant message id.
	        // If the backend provided an explicit assistant_msg_id, treat it as authoritative.
	        // Otherwise, fall back to "first seen wins" to avoid reshuffling on streaming updates.
        if (explicitAssistantMsgId) {
          runToAssistantMsgIdRef.current.set(runId, explicitAssistantMsgId);
        } else if (assistantMsgId && !runToAssistantMsgIdRef.current.has(runId)) {
          runToAssistantMsgIdRef.current.set(runId, assistantMsgId);
        }

        // Insert a tool card into the assistant stream timeline (at the first event we see).
        const attachId = explicitAssistantMsgId || assistantMsgId;
        if (attachId) {
          const timeline = assistantTimelineRef.current.get(attachId) || [];
          const key = `tool-${runId}`;
          const exists = timeline.some((it) => it.kind === "tool" && it.runId === runId);
          if (!exists) {
            timeline.push({ kind: "tool", key, ts, runId });
            assistantTimelineRef.current.set(attachId, timeline);
            // Next text should start a new segment after the tool.
            assistantOpenTextKeyRef.current.set(attachId, null);
          }
        }

        setTraceVersion((v) => v + 1);
      } catch {
        setTraceVersion((v) => v + 1);
      }
    },
  };

  const toolRunsByAssistantMsgId = useMemo(() => {
    // Depends on traceVersion to re-evaluate mutable refs.
    if (traceVersion === -1) return new Map<string, ToolRun[]>();
    const out = new Map<string, ToolRun[]>();
    for (const [runId, assistantMsgId] of runToAssistantMsgIdRef.current.entries()) {
      const r = toolRunsByIdRef.current.get(runId);
      if (!assistantMsgId || !r) continue;
      const arr = out.get(assistantMsgId) || [];
      arr.push(r);
      out.set(assistantMsgId, arr);
    }
    for (const v of out.values()) {
      v.sort((a, b) => (a.startTs || 0) - (b.startTs || 0));
    }
    return out;
  }, [traceVersion]);

  const reasoningByAssistantMsgId = useMemo(() => {
    // Depends on traceVersion to re-evaluate mutable refs.
    if (traceVersion === -1) return new Map<string, { key: string; ts: number; text: string }[]>();
    const out = new Map<string, { key: string; ts: number; text: string }[]>();
    for (const [assistantMsgId, entries] of reasoningByAssistantMsgIdRef.current.entries()) {
      const arr = [...entries];
      arr.sort((a, b) => a.ts - b.ts);
      out.set(assistantMsgId, arr);
    }
    return out;
  }, [traceVersion]);

  const displayMessages = useMemo(() => {
    const base = messages.filter((msg) => {
      if (msg.type === MessageType.TRACE_EVENT) return false;
      if (msg.type === MessageType.UPDATE_FILE) return false;
      if (msg.type === MessageType.UPDATE_IN_PROGRESS) return false;
      if (msg.type === MessageType.UPDATE_COMPLETED) return false;
      return true;
    });

    const haveIds = new Set(base.map((m) => m.id).filter(Boolean) as string[]);

    // If tools start before any assistant token stream, we still want a bubble to hang them from.
    const placeholders: Message[] = [];
    const assistantIds = new Set<string>();
    for (const k of toolRunsByAssistantMsgId.keys()) assistantIds.add(k);
    for (const k of reasoningByAssistantMsgId.keys()) assistantIds.add(k);
    for (const assistantMsgId of assistantIds) {
      if (!assistantMsgId || haveIds.has(assistantMsgId)) continue;

      const ts = assistantTraceFirstTsRef.current.get(assistantMsgId) || 0;

      placeholders.push({
        type: MessageType.AGENT_PARTIAL,
        id: assistantMsgId,
        timestamp: ts,
        session_id: resolvedSessionId || undefined,
        data: { text: "", sender: Sender.ASSISTANT, isStreaming: true },
      });
    }

    const combined = [...base, ...placeholders]
      .filter((msg) => {
        const id = typeof msg.id === "string" ? msg.id : "";
        const isUser = msg.data.sender === Sender.USER;
        const text = typeof msg.data.text === "string" ? msg.data.text : "";
        const hasTools = id ? (toolRunsByAssistantMsgId.get(id)?.length || 0) > 0 : false;
        const hasReason = id ? (reasoningByAssistantMsgId.get(id)?.length || 0) > 0 : false;

        if (msg.type === MessageType.ERROR) return true;
        if (isUser) return !!text.trim();
        return !!text.trim() || hasTools || hasReason;
      })
      .sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));

    return combined;
  }, [messages, toolRunsByAssistantMsgId, reasoningByAssistantMsgId, resolvedSessionId]);

  const { isConnecting, isConnected, error, connect, send } = useMessageBus({
    wsUrl: AGENT_CONFIG.WS_URL,
    sessionId: resolvedSessionId || undefined,
    handlers: messageHandlers,
    onConnect: () => {
      console.log("Connected to Amicable Agent");
    },
    onError: (errorMsg) => {
      console.error("Connection error:", errorMsg);

      let errorString = "Unknown connection error";
      if (typeof errorMsg === "string") {
        errorString = errorMsg;
      } else if (errorMsg && typeof errorMsg === "object") {
        const errorObj = errorMsg as { message?: unknown };
        if (errorObj.message) {
          errorString = String(errorObj.message);
        }
      }

      console.error("Processed error:", errorString);
    },
  });

  useEffect(() => {
    isConnectedRef.current = isConnected;
    sendRef.current = send;
  }, [isConnected, send]);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    if (chatHistoryRef.current) {
      chatHistoryRef.current.scrollTop = chatHistoryRef.current.scrollHeight;
    }
  }, [messages, traceVersion]);

  // Handle resizing
  useEffect(() => {
    const MIN_CHAT = 340;

    const handleMouseMove = (e: MouseEvent) => {
      if (!isChatResizing) return;
      const vw = window.innerWidth || 0;
      const maxChat = Math.max(MIN_CHAT, vw - 320 - 4); // leave room for main panel + handle
      const next = vw - e.clientX;
      setChatWidth(Math.max(MIN_CHAT, Math.min(maxChat, next)));
    };

    const handleMouseUp = () => {
      setIsChatResizing(false);
    };

    if (isChatResizing) {
      document.addEventListener("mousemove", handleMouseMove);
      document.addEventListener("mouseup", handleMouseUp);
    }

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isChatResizing, chatWidth]);

  const handleTakeOverSession = useCallback(() => {
    // Reconnect with force=true to take over the session
    setProjectLockedInfo(null);
    // Send INIT with force_claim to take over the session
    send(MessageType.INIT, { force_claim: true });
  }, [send]);

  const handleGoBackToProjects = useCallback(() => {
    navigate("/");
  }, [navigate]);

  const handleSessionClaimedDismiss = useCallback(() => {
    setSessionClaimed(null);
    navigate("/");
  }, [navigate]);

  const handleSendMessage = () => {
    const text = inputValue.trim();
    const imgs = pendingImages;
    if (!text && imgs.length === 0) return;

    const content_blocks =
      imgs.length > 0
        ? [
            ...(text ? [{ type: "text", text }] : []),
            ...imgs.map((img) => ({
              type: "image",
              base64: img.base64,
              mime_type: img.mimeType,
            })),
          ]
        : undefined;
    const localText =
      text ||
      `[Attached ${imgs.length} image${imgs.length === 1 ? "" : "s"}]`;

    send(MessageType.USER, { text, content_blocks });
    setInputValue("");
    setPendingImages([]);
    setAttachmentError(null);
    setMessages((prev) => [
      ...prev,
      {
        type: MessageType.USER,
        timestamp: Date.now(),
        data: {
          text: localText,
          content_blocks,
          sender: Sender.USER,
        },
        session_id: resolvedSessionId || undefined,
      },
    ]);
  };

  const sendUserMessage = (text: string) => {
    const t = (text || "").trim();
    if (!t) return;
    send(MessageType.USER, { text: t });
    setMessages((prev) => [
      ...prev,
      {
        type: MessageType.USER,
        timestamp: Date.now(),
        data: {
          text: t,
          sender: Sender.USER,
        },
        session_id: resolvedSessionId || undefined,
      },
    ]);
  };

  const handleAttachClick = () => {
    fileInputRef.current?.click();
  };

  const handleAttachmentChange = async (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    // Allow selecting the same file again later.
    e.target.value = "";
    if (!files.length) return;

    const remaining = MAX_IMAGE_ATTACHMENTS - pendingImages.length;
    if (remaining <= 0) {
      setAttachmentError(`You can attach up to ${MAX_IMAGE_ATTACHMENTS} images.`);
      return;
    }

    const accepted: PendingImageAttachment[] = [];
    const errors: string[] = [];
    for (const file of files.slice(0, remaining)) {
      if (!file.type.startsWith("image/")) {
        errors.push(`${file.name}: only image files are supported.`);
        continue;
      }
      if (file.size > MAX_IMAGE_FILE_BYTES) {
        errors.push(`${file.name}: exceeds ${Math.round(MAX_IMAGE_FILE_BYTES / 1024 / 1024)}MB.`);
        continue;
      }
      try {
        const dataUrl = await readFileAsDataUrl(file);
        const comma = dataUrl.indexOf(",");
        if (comma < 0 || comma + 1 >= dataUrl.length) {
          errors.push(`${file.name}: failed to encode image.`);
          continue;
        }
        accepted.push({
          name: file.name,
          mimeType: file.type || "image/png",
          base64: dataUrl.slice(comma + 1),
          size: file.size,
        });
      } catch {
        errors.push(`${file.name}: failed to read image.`);
      }
    }

    if (files.length > remaining) {
      errors.push(`Only ${remaining} additional image(s) can be attached.`);
    }

    if (accepted.length) {
      setPendingImages((prev) => [...prev, ...accepted]);
    }
    setAttachmentError(errors.length ? errors.join(" ") : null);
  };

  const removePendingImage = (idx: number) => {
    setPendingImages((prev) => prev.filter((_, i) => i !== idx));
    setAttachmentError(null);
  };

  const renderUiBlocks = (blocks: JsonObject[] | undefined) => {
    if (!blocks || !blocks.length) return null;
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 8 }}>
        {blocks.map((b, idx) => {
          const type = typeof b.type === "string" ? b.type : "unknown";
          if (type === "steps") {
            const title = typeof b.title === "string" ? b.title : "Steps";
            const steps = Array.isArray(b.steps) ? b.steps : [];
            return (
              <div
                key={`ui-${idx}`}
                className="border w-full bg-muted-foreground/5 rounded-md text-sm text-muted-foreground"
                style={{ padding: 10 }}
              >
                <div style={{ fontWeight: 600, marginBottom: 6 }}>{title}</div>
                <ol style={{ margin: 0, paddingLeft: 18 }}>
                  {steps.map((s, i) => (
                    <li key={`step-${idx}-${i}`}>{String(s)}</li>
                  ))}
                </ol>
              </div>
            );
          }

	          if (type === "cards") {
	            const title = typeof b.title === "string" ? b.title : undefined;
	            const cards = Array.isArray(b.cards) ? b.cards : [];
	            return (
              <div
                key={`ui-${idx}`}
                className="border w-full bg-muted-foreground/5 rounded-md text-sm text-muted-foreground"
                style={{ padding: 10 }}
              >
                {title ? (
                  <div style={{ fontWeight: 600, marginBottom: 8 }}>{title}</div>
                ) : null}
	                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
	                  {cards.map((c, i) => (
	                    <div
	                      key={`card-${idx}-${i}`}
	                      className="border bg-background rounded-md"
	                      style={{ padding: 10 }}
	                    >
	                      {(() => {
	                        const co = asObj(c);
	                        const ctitle =
	                          co && typeof co.title === "string"
	                            ? co.title
	                            : `Card ${i + 1}`;
	                        const cbody =
	                          co && typeof co.body === "string" ? co.body : "";
	                        return (
	                          <>
	                            <div style={{ fontWeight: 600 }}>
	                              {String(ctitle)}
	                            </div>
	                            <div
	                              style={{ whiteSpace: "pre-wrap", marginTop: 6 }}
	                            >
	                              {String(cbody)}
	                            </div>
	                          </>
	                        );
	                      })()}
	                    </div>
	                  ))}
	                </div>
	              </div>
	            );
	          }

          // Fallback: render raw JSON.
          return (
            <details
              key={`ui-${idx}`}
              className="border w-full bg-muted-foreground/5 rounded-md text-sm text-muted-foreground"
              style={{ padding: 10 }}
            >
              <summary style={{ cursor: "pointer", fontWeight: 600 }}>
                UI block ({type})
              </summary>
              <pre style={{ marginTop: 8, whiteSpace: "pre-wrap" }}>
                {JSON.stringify(b, null, 2)}
              </pre>
            </details>
          );
        })}
      </div>
    );
  };

  const previewJson = (v: unknown, depth = 0): unknown => {
    if (depth > 2) return "[…]";
    if (typeof v === "string") {
      const s = v.length > 2000 ? `${v.slice(0, 2000)}\n…(truncated)…` : v;
      return s;
    }
    if (typeof v !== "object" || v === null) return v;
    if (Array.isArray(v)) return v.slice(0, 50).map((x) => previewJson(x, depth + 1));
    const o = v as Record<string, unknown>;
    const keys = Object.keys(o).slice(0, 50);
    const out: Record<string, unknown> = {};
    for (const k of keys) out[k] = previewJson(o[k], depth + 1);
    const extra = Object.keys(o).length - keys.length;
    if (extra > 0) out["…"] = `+${extra} more keys`;
    return out;
  };

  const ToolRunCard = ({ r }: { r: ToolRun }) => {
    const [open, setOpen] = useState(false);
    const dur =
      r.startTs && r.endTs ? Math.max(0, r.endTs - r.startTs) : undefined;
    const badge =
      r.status === "running" ? "Running" : r.status === "success" ? "OK" : "Error";
    const badgeColor =
      r.status === "running"
        ? "bg-blue-500/10 text-blue-200"
        : r.status === "success"
          ? "bg-green-500/10 text-green-200"
          : "bg-red-500/10 text-red-200";
    const explain = r.explanations.length
      ? r.explanations[r.explanations.length - 1]
      : "";

    return (
      <div className="flex justify-start">
        <details
          className="border w-full bg-muted-foreground/5 rounded-md text-sm text-muted-foreground"
          style={{ padding: 10 }}
          open={open}
          onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
        >
          <summary style={{ cursor: "pointer", listStyle: "none" }}>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <span className={`px-2 py-0.5 rounded ${badgeColor}`}>{badge}</span>
              <span style={{ fontWeight: 600 }}>{r.toolName}</span>
              {dur !== undefined ? (
                <span className="text-xs text-muted-foreground">{dur}ms</span>
              ) : null}
              {r.status === "running" ? (
                <span className="ml-auto flex gap-1 justify-start">
                  <span
                    className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce"
                    style={{ animationDelay: "0ms" }}
                  />
                  <span
                    className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce"
                    style={{ animationDelay: "150ms" }}
                  />
                  <span
                    className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce"
                    style={{ animationDelay: "300ms" }}
                  />
                </span>
              ) : null}
            </div>
            {explain ? (
              <div className="text-xs text-muted-foreground" style={{ marginTop: 4 }}>
                {explain}
              </div>
            ) : null}
          </summary>

          {open ? (
            <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
              {r.input !== undefined ? (
                <details className="border bg-background/60 rounded-md" style={{ padding: 8 }}>
                  <summary style={{ cursor: "pointer", fontWeight: 600 }}>Input</summary>
                  <pre style={{ marginTop: 8, whiteSpace: "pre-wrap" }}>
                    {JSON.stringify(previewJson(r.input), null, 2)}
                  </pre>
                </details>
              ) : null}
              {r.output !== undefined ? (
                <details className="border bg-background/60 rounded-md" style={{ padding: 8 }}>
                  <summary style={{ cursor: "pointer", fontWeight: 600 }}>Output</summary>
                  <pre style={{ marginTop: 8, whiteSpace: "pre-wrap" }}>
                    {JSON.stringify(previewJson(r.output), null, 2)}
                  </pre>
                </details>
              ) : null}
              {r.error !== undefined ? (
                <details className="border bg-background/60 rounded-md" style={{ padding: 8 }}>
                  <summary style={{ cursor: "pointer", fontWeight: 600 }}>Error</summary>
                  <pre style={{ marginTop: 8, whiteSpace: "pre-wrap" }}>
                    {JSON.stringify(previewJson(r.error), null, 2)}
                  </pre>
                </details>
              ) : null}
            </div>
          ) : null}
        </details>
      </div>
    );
  };

  const renderReasoningSummaryBubble = (text: string) => {
    const cleaned = text.replace(/^\[reasoning\]\s*/i, "").trim();
    if (!cleaned) return null;

    return (
      <div className="flex justify-start">
        <details
          className="border w-full bg-muted-foreground/5 rounded-md text-sm text-muted-foreground"
          style={{ padding: 10 }}
        >
          <summary style={{ cursor: "pointer", fontWeight: 600, listStyle: "none" }}>
            Reasoning summary
          </summary>
          <div
            className="text-xs text-muted-foreground"
            style={{ marginTop: 8, whiteSpace: "pre-wrap" }}
          >
            {cleaned}
          </div>
        </details>
      </div>
    );
  };

  useEffect(() => {
    if (iframeUrl && isConnected) {
      setIframeError(false);
    }
  }, [iframeUrl, isConnected]);

  // Forward preview runtime errors (postMessage) to the agent for auto-heal.
  useEffect(() => {
    if (!rawIframeUrl) return;

    let allowedOrigin = "";
    try {
      allowedOrigin = new URL(rawIframeUrl).origin;
    } catch {
      allowedOrigin = "";
    }

    const handler = (event: MessageEvent) => {
      if (!event?.data || typeof event.data !== "object") return;
      if (allowedOrigin && event.origin !== allowedOrigin) return;

      const dataObj = asObj(event.data);
      if (!dataObj || dataObj.type !== "amicable_runtime_error") return;
      const p = asObj(dataObj.payload);
      if (!p) return;

      const kind = typeof p.kind === "string" ? p.kind : "window_error";
      const message =
        typeof p.message === "string" ? p.message : String(p.message ?? "");
      sendRuntimeError({
        kind,
        message,
        stack: typeof p.stack === "string" ? p.stack : undefined,
        url: typeof p.url === "string" ? p.url : undefined,
        ts_ms: typeof p.ts_ms === "number" ? p.ts_ms : undefined,
        fingerprint:
          typeof p.fingerprint === "string" ? p.fingerprint : undefined,
        level: p.level === "error" ? "error" : undefined,
        source:
          p.source === "console" ||
          p.source === "window" ||
          p.source === "promise" ||
          p.source === "bridge"
            ? p.source
            : undefined,
        args_preview:
          typeof p.args_preview === "string" ? p.args_preview : undefined,
        extra: asObj(p.extra) ?? undefined,
      });
    };

    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, [rawIframeUrl, sendRuntimeError]);

  const handleIframeLoad = () => {
    console.log("Iframe loaded successfully:", iframeUrl);
    setIframeError(false);
    setIframeReady(true);
    runRuntimeBridgeProbe("iframe_load");
  };

  const handleIframeError = () => {
    console.error("Iframe failed to load:", iframeUrl);
    setIframeError(true);
    const u = rawIframeUrl || iframeUrl;
    const fp = `preview_${hash(u)}`;
    sendRuntimeError({
      kind: "preview_load_failed",
      message: "Preview iframe failed to load",
      url: u,
      fingerprint: fp,
      source: "bridge",
      level: "error",
      extra: { iframe_url: u },
    });
  };

  // Auto-connect when sessionId is available
  useEffect(() => {
    if (authLoading) {
      return;
    }
    if (authMode === "google" && !authUser) {
      return;
    }
    if (!isConnected && !isConnecting && resolvedSessionId) {
      console.log("Connecting to Workspace with sessionId:", resolvedSessionId);
      connect().catch((e) => {
        console.error("Connect failed:", e);
      });
    }
  }, [
    authLoading,
    authMode,
    authUser,
    connect,
    isConnected,
    isConnecting,
    resolvedSessionId,
  ]);

  // Clear processed message IDs when connection is lost
  useEffect(() => {
    if (!isConnected) {
      processedMessageIds.current.clear();
    }
  }, [isConnected]);

  useEffect(() => {
    setIframeReady(false);
  }, [iframeUrl]);

  useEffect(() => {
    if (
      initCompleted &&
      !sandboxExists &&
      routeState?.initialPrompt &&
      !initialPromptSent.current
    ) {
      const prompt = routeState.initialPrompt;
      // Send as user message (so it appears in chat)
      send(MessageType.USER, { text: prompt });
      setMessages((prev) => [
        ...prev,
        {
          type: MessageType.USER,
          timestamp: Date.now(),
          data: {
            text: prompt,
            sender: Sender.USER,
          },
          session_id: resolvedSessionId || undefined,
        },
      ]);
      initialPromptSent.current = true;
    }
  }, [
    initCompleted,
    sandboxExists,
    routeState,
    send,
    setMessages,
    resolvedSessionId,
  ]);

  // Resolve slug -> project_id for /p/:slug routes.
  useEffect(() => {
    const run = async () => {
      if (!slug) return;
      setSlugResolutionStatus("loading");
      setSlugResolutionError(null);
      try {
        const url = new URL(`/api/projects/by-slug/${encodeURIComponent(slug)}`, AGENT_CONFIG.HTTP_URL).toString();
        const res = await fetch(url, { credentials: "include" });
        const data = (await res.json()) as unknown;
        const d = asObj(data);
        if (!res.ok) {
          if (res.status === 404) {
            setSlugResolutionStatus("not_found");
            return;
          }
          const detail =
            d && typeof d.error === "string"
              ? d.error
              : `failed to resolve project (${res.status})`;
          setSlugResolutionStatus("error");
          setSlugResolutionError(detail);
          return;
        }
        if (d && typeof d.project_id === "string") {
          setResolvedSessionId(d.project_id);
          setSlugResolutionStatus("resolved");
        }
        if (
          d &&
          typeof d.name === "string" &&
          typeof d.slug === "string" &&
          typeof d.project_id === "string"
        ) {
          setProjectInfo({ project_id: d.project_id, name: d.name, slug: d.slug });
        }
      } catch {
        setSlugResolutionStatus("error");
        setSlugResolutionError("failed to resolve project (network error)");
      }
    };
    run();
  }, [slug]);

  // Legacy route: /create?session_id=... -> redirect to /p/<slug>
  useEffect(() => {
    const run = async () => {
      if (slug) return;
      if (!querySessionId) return;
      if (redirectedFromLegacy.current) return;
      try {
        const url = new URL(`/api/projects/${encodeURIComponent(querySessionId)}`, AGENT_CONFIG.HTTP_URL).toString();
        const res = await fetch(url, { credentials: "include" });
        const data = (await res.json()) as unknown;
        const d = asObj(data);
        if (!res.ok) return;
        if (d && typeof d.slug === "string" && d.slug) {
          redirectedFromLegacy.current = true;
          // Keep any initial prompt state for first-run bootstrap.
          navigate(`/p/${d.slug}`, { replace: true, state: routeState ?? undefined });
        }
      } catch {
        // ignore
      }
    };
    run();
  }, [routeState, navigate, querySessionId, slug]);

  const LoadingState = () => (
    <div className="flex flex-col items-center justify-center gap-6">
      <div className="animate-spin flex items-center justify-center text-gray-400">
        <Loader2 size={64} />
      </div>
      <div
        className="text-[18px] font-medium text-muted-foreground animate-pulse"
        style={{ marginTop: "24px" }}
      >
        Connecting to Workspace...
      </div>
      <p style={{ marginTop: "12px", textAlign: "center" }}>
        Please wait while we setup your workspace and load the website.
      </p>
    </div>
  );

  type HitlDecisionDraft = {
    type: HitlDecisionType;
    rejectMessage: string;
    editedName: string;
    editedArgsText: string;
    argsError: string | null;
  };

  const hitlActionRequests = useMemo(() => {
    return pendingHitl?.request.action_requests || [];
  }, [pendingHitl]);

  const hitlReviewConfigs = useMemo(() => {
    return pendingHitl?.request.review_configs || [];
  }, [pendingHitl]);

  const [hitlDecisions, setHitlDecisions] = useState<HitlDecisionDraft[]>([]);

  useEffect(() => {
    if (!pendingHitl) {
      setHitlDecisions([]);
      return;
    }
    setHitlDecisions(
      hitlActionRequests.map((ar: HitlActionRequest) => ({
        type: "approve",
        rejectMessage: "",
        editedName: ar?.name || "",
        editedArgsText: JSON.stringify(ar?.args ?? {}, null, 2),
        argsError: null,
      }))
    );
  }, [pendingHitl?.interruptId, hitlActionRequests]);

  const HitlPanel = () => {
    if (!pendingHitl) return null;

    const actionRequests: HitlActionRequest[] = hitlActionRequests;
    const reviewConfigs: HitlReviewConfig[] = hitlReviewConfigs;

    const defaultAllowed: HitlDecisionType[] = ["approve", "edit", "reject"];

    // LangChain HITL strategies docs treat review_configs as a per-tool config list.
    // Map by action_name so we can support both:
    // - per-action config (same length as action_requests)
    // - per-tool config (unique action_name entries)
    const cfgByActionName = new Map<string, HitlReviewConfig>();
    for (const cfg of reviewConfigs) {
      if (cfg && typeof cfg.action_name === "string" && cfg.action_name) {
        cfgByActionName.set(cfg.action_name, cfg);
      }
    }

    const updateDecision = (idx: number, patch: Partial<HitlDecisionDraft>) => {
      setHitlDecisions((prev) =>
        prev.map((d, i) => (i === idx ? { ...d, ...patch } : d))
      );
    };

    const allowedFor = (idx: number): HitlDecisionType[] => {
      const toolName = actionRequests[idx]?.name;
      const cfg =
        typeof toolName === "string" && toolName ? cfgByActionName.get(toolName) : undefined;
      const allowed = cfg?.allowed_decisions;
      if (Array.isArray(allowed) && allowed.length) return allowed;
      return defaultAllowed;
    };

    const validateArgs = (idx: number, text: string) => {
      try {
        const parsed = JSON.parse(text || "{}");
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
          updateDecision(idx, { argsError: null });
          return parsed as JsonObject;
        }
        updateDecision(idx, { argsError: "Args must be a JSON object" });
        return null;
      } catch {
        updateDecision(idx, { argsError: "Invalid JSON" });
        return null;
      }
    };

    const submit = () => {
      const payloadDecisions: HitlDecision[] = [];
      for (let i = 0; i < actionRequests.length; i++) {
        const d = hitlDecisions[i];
        if (!d) continue;
        if (d.type === "approve") {
          payloadDecisions.push({ type: "approve" });
          continue;
        }
        if (d.type === "reject") {
          const msg = (d.rejectMessage || "").trim();
          payloadDecisions.push(
            msg ? { type: "reject", message: msg } : { type: "reject" }
          );
          continue;
        }
        if (d.type === "edit") {
          const args = validateArgs(i, d.editedArgsText || "");
          if (args == null) return;
          const name = (d.editedName || "").trim();
          if (!name) {
            updateDecision(i, { argsError: "Tool name is required for edit" });
            return;
          }
          payloadDecisions.push({ type: "edit", edited_action: { name, args } });
          continue;
        }
      }

      send(MessageType.HITL_RESPONSE, {
        interrupt_id: pendingHitl.interruptId,
        response: { decisions: payloadDecisions },
      });
      setPendingHitl(null);
    };

    return (
      <div
        style={{
          border: "1px solid rgba(255,255,255,0.15)",
          borderRadius: 12,
          padding: 12,
          background: "rgba(0,0,0,0.25)",
        }}
      >
        <div style={{ fontWeight: 700, marginBottom: 8 }}>Approval required</div>
        <div style={{ fontSize: 12, opacity: 0.9, marginBottom: 12 }}>
          Review the requested tool calls and approve, reject, or edit.
        </div>

        {actionRequests.length === 0 ? (
          <div style={{ fontSize: 12, opacity: 0.9 }}>
            No actions were provided in this HITL request.
          </div>
        ) : (
          actionRequests.map((ar, idx) => {
            const allowed = allowedFor(idx);
            const d = hitlDecisions[idx];
            const desc = ar?.description;
            return (
              <div
                key={`hitl-${idx}`}
                style={{
                  borderTop: idx === 0 ? "none" : "1px solid rgba(255,255,255,0.12)",
                  paddingTop: idx === 0 ? 0 : 12,
                  marginTop: idx === 0 ? 0 : 12,
                }}
              >
                <div style={{ fontSize: 12, opacity: 0.9 }}>
                  <div style={{ fontWeight: 700 }}>Tool: {String(ar?.name || "")}</div>
                  {desc ? (
                    <div style={{ marginTop: 6, whiteSpace: "pre-wrap" }}>{String(desc)}</div>
                  ) : null}
                  <div style={{ marginTop: 6, fontFamily: "monospace", whiteSpace: "pre-wrap" }}>
                    {JSON.stringify(ar?.args ?? {}, null, 2)}
                  </div>
                </div>

                <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
                  <select
                    value={d?.type || "approve"}
                    onChange={(e) =>
                      updateDecision(idx, { type: e.target.value as HitlDecisionType, argsError: null })
                    }
                    style={{
                      background: "rgba(255,255,255,0.08)",
                      color: "white",
                      border: "1px solid rgba(255,255,255,0.15)",
                      borderRadius: 10,
                      padding: "8px 10px",
                    }}
                  >
                    {allowed.includes("approve") && <option value="approve">Approve</option>}
                    {allowed.includes("edit") && <option value="edit">Edit</option>}
                    {allowed.includes("reject") && <option value="reject">Reject</option>}
                  </select>
                </div>

                {d?.type === "reject" ? (
                  <div style={{ marginTop: 10 }}>
                    <textarea
                      value={d.rejectMessage || ""}
                      onChange={(e) => updateDecision(idx, { rejectMessage: e.target.value })}
                      placeholder="Optional rejection message to the agent"
                      style={{
                        width: "100%",
                        minHeight: 64,
                        background: "rgba(255,255,255,0.06)",
                        color: "white",
                        border: "1px solid rgba(255,255,255,0.12)",
                        borderRadius: 10,
                        padding: 10,
                      }}
                    />
                  </div>
                ) : null}

                {d?.type === "edit" ? (
                  <div style={{ marginTop: 10 }}>
                    <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
                      <input
                        value={d.editedName || ""}
                        onChange={(e) => updateDecision(idx, { editedName: e.target.value, argsError: null })}
                        placeholder="Tool name"
                        style={{
                          flex: 1,
                          background: "rgba(255,255,255,0.06)",
                          color: "white",
                          border: "1px solid rgba(255,255,255,0.12)",
                          borderRadius: 10,
                          padding: 10,
                        }}
                      />
                    </div>
                    <textarea
                      value={d.editedArgsText || ""}
                      onChange={(e) => {
                        updateDecision(idx, { editedArgsText: e.target.value });
                        validateArgs(idx, e.target.value);
                      }}
                      placeholder='Args JSON, e.g. {"command":"npm -v"}'
                      style={{
                        width: "100%",
                        minHeight: 120,
                        background: "rgba(255,255,255,0.06)",
                        color: "white",
                        border: "1px solid rgba(255,255,255,0.12)",
                        borderRadius: 10,
                        padding: 10,
                        fontFamily: "monospace",
                      }}
                    />
                    {d.argsError ? (
                      <div style={{ marginTop: 6, fontSize: 12, color: "#ffb4b4" }}>
                        {d.argsError}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            );
          })
        )}

        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <Button onClick={submit} disabled={!isConnected}>
            Submit decisions
          </Button>
          <Button
            variant="secondary"
            onClick={() => {
              // Safety: do not leave the backend stuck in a pending HITL state.
              const decisions: HitlDecision[] = actionRequests.map(() => ({
                type: "reject",
                message: "Dismissed by user",
              }));
              send(MessageType.HITL_RESPONSE, {
                interrupt_id: pendingHitl.interruptId,
                response: { decisions },
              });
              setPendingHitl(null);
            }}
            disabled={!isConnected}
          >
            Reject all
          </Button>
        </div>
      </div>
    );
  };

  const renderMainViewToggle = (activeView: "preview" | "code" | "database") => {
    return (
      <div className="flex gap-2">
        <ToggleButton
          active={activeView === "preview"}
          disabled={
            activeView === "preview" &&
            (!iframeUrl || !iframeReady || !initCompleted)
          }
          onClick={() => setMainView("preview")}
        >
          Preview
        </ToggleButton>
        <ToggleButton
          active={activeView === "code"}
          onClick={() => setMainView("code")}
        >
          Code
        </ToggleButton>
        <ToggleButton
          active={activeView === "database"}
          onClick={() => setMainView("database")}
        >
          Database
        </ToggleButton>
      </div>
    );
  };

  return (
    <div className="flex flex-row w-full h-full">
      <div
        className={cn(
          "flex-1 flex flex-col bg-card",
          iframeUrl ? "items-stretch justify-stretch gap-0" : "items-center justify-center gap-6"
        )}
      >
        {!authLoading && authMode === "google" && !authUser ? (
          <div className="flex flex-col items-center justify-center gap-6">
            <div className="text-[18px] font-medium text-gray-700">Please sign in</div>
            <div className="text-sm" style={{ marginTop: "8px", textAlign: "center" }}>
              Google login is required before connecting to a workspace.
            </div>
            <div style={{ marginTop: "16px" }}>
              <Button asChild>
                <a href={loginUrl}>Sign in with Google</a>
              </Button>
            </div>
          </div>
        ) : mainView === "code" ? (
          <div style={{ height: "100%", minHeight: 0 }}>
            {resolvedSessionId ? (
              <CodePane
                projectId={resolvedSessionId}
                agentTouchedPath={agentTouchedPath}
                onSendUserMessage={sendUserMessage}
              />
            ) : (
              <div style={{ padding: 16 }}>Loading project...</div>
            )}
            <div className="w-full flex items-center justify-between bg-gray-200 border-t border-gray-200 px-6 h-14 absolute left-0 right-0 bottom-0 z-[3]">
              {renderMainViewToggle("code")}
              <div />
              <div />
            </div>
          </div>
        ) : mainView === "database" ? (
          <div style={{ height: "100%", minHeight: 0 }}>
            {resolvedSessionId ? (
              <DatabasePane projectId={resolvedSessionId} />
            ) : (
              <div style={{ padding: 16 }}>Loading project...</div>
            )}
            <div className="w-full flex items-center justify-between bg-gray-200 border-t border-gray-200 px-6 h-14 absolute left-0 right-0 bottom-0 z-[3]">
              {renderMainViewToggle("database")}
              <div />
              <div />
            </div>
          </div>
        ) : isConnected ? (
          <div className="relative w-full h-full overflow-auto">
            <div className="flex items-center bg-gray-200 border-b border-gray-200 px-3 py-1.5 gap-2">
              <button
                type="button"
                className="bg-transparent border-0 text-gray-700 flex items-center justify-center p-1 rounded cursor-pointer hover:bg-gray-50"
                style={{ cursor: iframeUrl ? "pointer" : "not-allowed" }}
                onClick={iframeUrl ? refreshIframe : undefined}
                title="Refresh"
              >
                <RotateCcw size={16} />
              </button>
              <input
                className="flex-1 bg-gray-100 border-0 text-gray-700 rounded px-2 py-1 text-sm outline-none"
                value={iframeUrl || ""}
                readOnly
              />
              <a
                href={iframeUrl || undefined}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  display: "flex",
                  alignItems: "center",
                  pointerEvents: iframeUrl ? "auto" : "none",
                }}
                tabIndex={iframeUrl ? 0 : -1}
              >
                <ExternalLink size={16} />
              </a>
            </div>

            <div className="relative w-full h-[calc(100%-56px-40px)] min-h-0 p-0 m-0 box-border">
              {iframeError ? (
                <div className="flex flex-col items-center justify-center gap-6">
                  <img
                    className="w-24 h-24 object-contain"
                    src="/amicable-logo.svg"
                    alt="Amicable"
                    loading="lazy"
                    decoding="async"
                  />
                  <div
                    className="text-[18px] font-medium text-gray-700"
                    style={{ marginTop: "24px" }}
                  >
                    Failed to load website
                  </div>
                  <div className="text-sm" style={{ marginTop: "12px", textAlign: "center" }}>
                    {iframeUrl} took too long to load or failed to respond.
                  </div>
                  <div className="text-sm" style={{ marginTop: "8px", textAlign: "center" }}>
                    This could be due to network issues or the website being temporarily unavailable.
                  </div>
                </div>
              ) : !iframeUrl ? (
                <div className="absolute inset-0 flex flex-col items-center justify-center z-[2]">
                  <LoadingState />
                </div>
              ) : !iframeReady || !initCompleted ? (
                <>
                  <div className="w-full h-full overflow-auto flex items-center justify-center">
                    <iframe
                      ref={iframeRef}
                      src={iframeUrl}
                      sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"
                      allow="fullscreen"
                      referrerPolicy="no-referrer"
                      loading="lazy"
                      onLoad={handleIframeLoad}
                      onError={handleIframeError}
                      className={cn(
                        "w-full h-full max-w-full max-h-full border-0 block box-border",
                        isResizing && "pointer-events-none"
                      )}
                      style={{
                        visibility: iframeReady ? "visible" : "hidden",
                        width:
                          typeof DEVICE_SPECS[selectedDevice].width === "number"
                            ? `${DEVICE_SPECS[selectedDevice].width}px`
                            : DEVICE_SPECS[selectedDevice].width,
                        height:
                          typeof DEVICE_SPECS[selectedDevice].height === "number"
                            ? `${DEVICE_SPECS[selectedDevice].height}px`
                            : DEVICE_SPECS[selectedDevice].height,
                        margin: selectedDevice === "desktop" ? "0" : "24px auto",
                        display: "block",
                        borderRadius: selectedDevice === "desktop" ? 0 : 16,
                        boxShadow:
                          selectedDevice === "desktop"
                            ? "none"
                            : "0 2px 16px rgba(0,0,0,0.12)",
                        background: "#fff",
                        boxSizing: "border-box",
                      }}
                    />
                  </div>
                  <div className="absolute inset-0 flex flex-col items-center justify-center z-[2]">
                    <LoadingState />
                  </div>
                </>
              ) : (
                <>
                  <div className="w-full h-full overflow-auto flex items-center justify-center">
                    <iframe
                      ref={iframeRef}
                      src={iframeUrl}
                      sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"
                      allow="fullscreen"
                      referrerPolicy="no-referrer"
                      loading="lazy"
                      onLoad={handleIframeLoad}
                      onError={handleIframeError}
                      className={cn(
                        "w-full h-full max-w-full max-h-full border-0 block box-border",
                        isResizing && "pointer-events-none"
                      )}
                      style={{
                        visibility: iframeReady ? "visible" : "hidden",
                        width:
                          typeof DEVICE_SPECS[selectedDevice].width === "number"
                            ? `${DEVICE_SPECS[selectedDevice].width}px`
                            : DEVICE_SPECS[selectedDevice].width,
                        height:
                          typeof DEVICE_SPECS[selectedDevice].height === "number"
                            ? `${DEVICE_SPECS[selectedDevice].height}px`
                            : DEVICE_SPECS[selectedDevice].height,
                        margin: selectedDevice === "desktop" ? "0" : "24px auto",
                        display: "block",
                        borderRadius: selectedDevice === "desktop" ? 0 : 16,
                        boxShadow:
                          selectedDevice === "desktop"
                            ? "none"
                            : "0 2px 16px rgba(0,0,0,0.12)",
                        background: "#fff",
                        boxSizing: "border-box",
                      }}
                    />
                  </div>
                  {isUpdateInProgress && (
                    <div className="absolute top-3 right-3 z-[2] flex items-center gap-2 bg-black/70 text-white text-xs px-3 py-1.5 rounded-full backdrop-blur-sm">
                      <Loader2 size={12} className="animate-spin" />
                      <span>{agentStatusText || "Updating..."}</span>
                    </div>
                  )}
                </>
              )}
            </div>

            <div className="w-full flex items-center justify-between bg-gray-200 border-t border-gray-200 px-6 h-14 absolute left-0 right-0 bottom-0 z-[3]">
              {renderMainViewToggle("preview")}
              <div className="flex gap-2">
                <DeviceButton
                  active={selectedDevice === "mobile"}
                  disabled={!iframeUrl || !iframeReady || !initCompleted}
                  onClick={() => setSelectedDevice("mobile")}
                >
                  <PhoneIcon />
                </DeviceButton>
                <DeviceButton
                  active={selectedDevice === "tablet"}
                  disabled={!iframeUrl || !iframeReady || !initCompleted}
                  onClick={() => setSelectedDevice("tablet")}
                >
                  <TabletIcon />
                </DeviceButton>
                <DeviceButton
                  active={selectedDevice === "desktop"}
                  disabled={!iframeUrl || !iframeReady || !initCompleted}
                  onClick={() => setSelectedDevice("desktop")}
                >
                  <ComputerIcon />
                </DeviceButton>
              </div>
              <button
                type="button"
                className="bg-violet-600 text-white rounded-md px-7 py-2 text-[15px] font-semibold transition disabled:cursor-not-allowed disabled:opacity-60 hover:bg-violet-700"
                disabled={
                  !iframeUrl ||
                  !iframeReady ||
                  isUpdateInProgress ||
                  !initCompleted
                }
              >
                Deploy
              </button>
            </div>
          </div>
        ) : (
          <>
            <img
              className="w-24 h-24 object-contain"
              src="/amicable-logo.svg"
              alt="Amicable"
              loading="lazy"
              decoding="async"
            />
            {slug && !resolvedSessionId && slugResolutionStatus === "loading" ? (
              <div
                className="text-[18px] font-medium text-muted-foreground animate-pulse"
                style={{ marginTop: "24px" }}
              >
                Loading project...
              </div>
            ) : slug && !resolvedSessionId && slugResolutionStatus === "not_found" ? (
              <div style={{ marginTop: "24px", textAlign: "center" }}>
                <div className="text-[18px] font-medium text-gray-700">Project not found</div>
                <div className="text-sm text-muted-foreground" style={{ marginTop: "12px" }}>
                  No project exists for slug <span className="font-mono">{slug}</span>.
                </div>
                <Button
                  onClick={() => navigate("/", { replace: true })}
                  style={{ marginTop: "16px" }}
                >
                  Go to Home
                </Button>
              </div>
            ) : (
              <div
                className="text-[18px] font-medium text-muted-foreground"
                style={{ marginTop: "24px" }}
              >
                Connect to start building
              </div>
            )}

            {slugResolutionError && (
              <div className="border border-red-400 rounded-md p-3 mt-4 text-destructive">
                <div className="text-sm">Error: {slugResolutionError}</div>
              </div>
            )}

            {error && (
              <div className="border border-red-400 rounded-md p-3 mt-4 text-destructive">
                <div className="text-sm">Error: {error}</div>
              </div>
            )}

            {!(slug && !resolvedSessionId && slugResolutionStatus === "not_found") && (
              <Button
                onClick={() => {
                  connect().catch((e) => console.error("Connect failed:", e));
                }}
                disabled={!resolvedSessionId || isConnecting}
                style={{ marginTop: "16px" }}
              >
                {isConnecting ? "Connecting..." : "Connect"}
              </Button>
            )}

            <div className="flex flex-col gap-4 mt-12">
              <div className="flex flex-row items-center gap-3">
                <Play size={16} />
                <div className="text-sm text-muted-foreground">Connect to Workspace</div>
              </div>
              <div className="flex flex-row items-center gap-3">
                <Play size={16} />
                <div className="text-sm text-muted-foreground">Chat with AI in the sidebar</div>
              </div>
              <div className="flex flex-row items-center gap-3">
                <Play size={16} />
                <div className="text-sm text-muted-foreground">Select specific elements to modify</div>
              </div>
            </div>
          </>
        )}
      </div>

      <div
        className="w-1 cursor-col-resize transition-colors hover:bg-gray-400 active:bg-blue-500"
        onMouseDown={(e) => {
          e.preventDefault();
          setIsChatResizing(true);
        }}
        title="Resize chat"
      />

      <div
        className="p-6 flex flex-col text-foreground gap-6 h-full min-w-[340px] bg-card border-l border-border"
        style={{ width: `${chatWidth}px` }}
      >
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-3 min-w-0">
            <img
              className="w-14 h-14 object-contain"
              src="/amicable-logo.svg"
              alt="Amicable"
              loading="eager"
              decoding="async"
            />
            <div style={{ display: "flex", flexDirection: "column", gap: 2 }} className="min-w-0">
              <div style={{ fontWeight: 600, lineHeight: 1.1 }} className="truncate">
                {projectInfo?.name || "Project"}
              </div>
              {projectInfo?.slug ? (
                <div className="text-xs text-muted-foreground truncate">/{projectInfo.slug}</div>
              ) : null}
            </div>
          </div>
          <div className="flex items-center justify-end">
            <AgentAuthStatus />
          </div>
        </div>

        <div className="flex flex-col min-h-0 flex-1">
          <div
            className="flex flex-col gap-2.5 overflow-y-auto flex-1 min-h-0"
            ref={chatHistoryRef}
          >
	            {displayMessages.map((msg, index) => {
	              const id = typeof msg.id === "string" ? msg.id : "";
	              const isUser = msg.data.sender === Sender.USER;
	              const timeline = !isUser && id ? assistantTimelineRef.current.get(id) || [] : [];
	              const hasTimeline = !isUser && timeline.length > 0;
	              const hasMeta =
	                !isUser &&
	                (timeline.some((it) => it.kind !== "text") || !!msg.data.ui_blocks?.length);

	              return (
	                <div
	                  key={msg.id || `msg-${index}-${msg.timestamp ?? 0}`}
	                  className={cn("flex", isUser ? "justify-end" : "justify-start")}
	                >
	                  <div
	                    className={cn(
	                      "max-w-[70%] text-sm",
	                      isUser
	                        ? "px-3 py-2 rounded-md bg-violet-600 text-white border border-violet-500/40"
	                        : hasMeta
	                          ? "w-full flex flex-col gap-2"
	                          : "px-3 py-2 rounded-md bg-muted/40 border border-border"
	                    )}
	                  >
	                    {!isUser ? renderUiBlocks(msg.data.ui_blocks) : null}

	                    {!isUser && hasTimeline ? (
	                      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
	                        {timeline.map((it) => {
	                          if (it.kind === "tool") {
	                            const r = toolRunsByIdRef.current.get(it.runId);
	                            if (!r) return null;
	                            return (
	                              <div key={it.key}>
	                                <ToolRunCard r={r} />
	                              </div>
	                            );
	                          }
	                          if (it.kind === "reasoning") {
	                            const el = renderReasoningSummaryBubble(it.text);
	                            return el ? <div key={it.key}>{el}</div> : null;
	                          }
	                          // text
	                          return (
	                            <ChatMarkdown
	                              key={it.key}
	                              markdown={it.text}
	                              className="text-foreground"
	                            />
	                          );
	                        })}
	                      </div>
	                    ) : msg.data.text && typeof msg.data.text === "string" && msg.data.text.trim() ? (
	                      isUser ? (
	                        <p
	                          style={{
	                            whiteSpace: "pre-wrap",
	                          }}
	                          className="text-white"
	                        >
	                          {String(msg.data.text || "")}
	                        </p>
	                      ) : (
	                        <ChatMarkdown
	                          markdown={String(msg.data.text || "")}
	                          className="text-foreground"
	                        />
	                      )
	                    ) : null}

	                    {msg.data.isStreaming && (
	                      <div className="flex gap-1 mt-2 justify-start">
	                        <div
                          className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce"
                          style={{ animationDelay: "0ms" }}
                        />
                        <div
                          className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce"
                          style={{ animationDelay: "150ms" }}
                        />
                        <div
                          className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce"
                          style={{ animationDelay: "300ms" }}
                        />
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="mt-auto flex flex-col gap-2">
          {pendingHitl ? (
            <div style={{ marginBottom: 12 }}>
              <HitlPanel />
            </div>
          ) : null}
          {agentStatusText.trim() ? (
            <div
              className="w-full border rounded-md bg-muted/40 border-border"
              style={{
                padding: "10px 12px",
                marginBottom: 12,
              }}
            >
              <div className="text-xs text-muted-foreground" style={{ fontWeight: 600 }}>
                Agent status
              </div>
              <div className="text-sm" style={{ marginTop: 4, whiteSpace: "pre-wrap" }}>
                {agentStatusText}
              </div>
            </div>
          ) : null}
          {attachmentError ? (
            <div className="text-xs text-destructive">{attachmentError}</div>
          ) : null}
          {pendingImages.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {pendingImages.map((img, idx) => (
                <div
                  key={`${img.name}-${idx}`}
                  className="flex items-center gap-1 rounded-md border border-border bg-muted/40 px-2 py-1 text-xs"
                >
                  <span className="max-w-[180px] truncate">{img.name}</span>
                  <button
                    type="button"
                    onClick={() => removePendingImage(idx)}
                    className="inline-flex items-center text-muted-foreground hover:text-foreground"
                    aria-label={`Remove ${img.name}`}
                  >
                    <X size={12} />
                  </button>
                </div>
              ))}
            </div>
          ) : null}
          <div className="flex flex-row gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              multiple
              className="hidden"
              onChange={(e) => {
                void handleAttachmentChange(e);
              }}
            />
            <Button
              variant="outline"
              onClick={handleAttachClick}
              disabled={!isConnected || !iframeReady || !!pendingHitl}
              title="Attach screenshot or diagram image"
            >
              <Paperclip size={14} />
            </Button>
            <Input
              placeholder="Ask Amicable..."
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  handleSendMessage();
                }
              }}
              disabled={!isConnected || !iframeReady || !!pendingHitl}
            />
            <Button
              onClick={handleSendMessage}
              disabled={
                !isConnected ||
                !iframeReady ||
                !!pendingHitl ||
                (!inputValue.trim() && pendingImages.length === 0)
              }
            >
              Send
            </Button>
          </div>
        </div>
      </div>

      {/* Project locking modals */}
      {projectLockedInfo && (
        <ProjectLockedModal
          lockedByEmail={projectLockedInfo.email}
          lockedAt={projectLockedInfo.lockedAt}
          onTakeOver={handleTakeOverSession}
          onGoBack={handleGoBackToProjects}
        />
      )}

      {sessionClaimed && (
        <SessionClaimedModal
          claimedByEmail={sessionClaimed.byEmail}
          onDismiss={handleSessionClaimedDismiss}
        />
      )}
    </div>
  );
};

export default Create;
