import {
  ComputerIcon,
  ExternalLink,
  Loader2,
  PhoneIcon,
  Play,
  RotateCcw,
  TabletIcon,
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
} from "../../types/messages";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ButtonHTMLAttributes,
} from "react";

import { AGENT_CONFIG } from "../../config/agent";
import { Button } from "@/components/ui/button";
import { CodePane } from "@/components/CodePane";
import { Input } from "@/components/ui/input";
import type { Message } from "../../types/messages";
import { cn } from "@/lib/utils";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useMessageBus } from "../../hooks/useMessageBus";
import { AgentAuthStatus } from "../../components/AgentAuthStatus";
import { useAgentAuth } from "../../hooks/useAgentAuth";

const DEVICE_SPECS = {
  mobile: { width: 390, height: 844 },
  tablet: { width: 768, height: 1024 },
  desktop: { width: "100%", height: "100%" },
};

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
  const [iframeError, setIframeError] = useState(false);
  const [iframeReady, setIframeReady] = useState(false);
  const [isUpdateInProgress, setIsUpdateInProgress] = useState(false);
  const [initCompleted, setInitCompleted] = useState(false);
  const [sandboxExists, setSandboxExists] = useState(false);
  const [pendingHitl, setPendingHitl] = useState<{
    interruptId: string;
    request: HitlRequest;
  } | null>(null);
  const chatHistoryRef = useRef<HTMLDivElement>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);
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
  const [mainView, setMainView] = useState<"preview" | "code">("preview");

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
        setIframeUrl(message.data.url);
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
        if (id) {
          const existingIndex = prev.findIndex((msg) => msg.id === id);
          if (existingIndex !== -1) {
            // Update in place
            return prev.map((msg, idx) =>
              idx === existingIndex
                ? {
                    ...msg,
                    timestamp: message.timestamp || msg.timestamp,
                    data: {
                      ...msg.data,
                      text: "Workspace loaded! You can now make edits here.",
                      sender: Sender.ASSISTANT,
                    },
                  }
                : msg
            );
          }
        }
        // Insert new
        return [
          ...prev,
          {
            ...message,
            timestamp: message.timestamp || Date.now(),
            data: {
              ...message.data,
              text: "Workspace loaded! You can now make edits here.",
              sender: Sender.ASSISTANT,
            },
          },
        ];
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

    [MessageType.AGENT_PARTIAL]: (message: Message) => {
      const text = message.data.text;
      const id = message.id;

      if (!id) {
        console.warn("AGENT_PARTIAL message missing id, ignoring:", message);
        return;
      }

      if (text && text.trim()) {
        const cleaned = stripUiBlocks(text.replace(/\\/g, ""));
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
      if (text && text.trim()) {
        const cleanedText = text.replace(/\\/g, "");
        const extracted = extractUiBlocks(cleanedText);
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
      // Keep trace in message stream; render it in the Actions tab.
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
      setMessages((prev) => [
        ...prev,
        {
          ...message,
          timestamp: message.timestamp || Date.now(),
          data: {
            ...message.data,
            sender: Sender.ASSISTANT,
            isStreaming: false,
          },
        },
      ]);
    },
  };

  const toolRuns = useMemo(() => {
    type Run = {
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
    const byId = new Map<string, Run>();

    for (const m of messages) {
      if (m.type !== MessageType.TRACE_EVENT) continue;
      const runId = typeof m.data.run_id === "string" ? m.data.run_id : "";
      const toolName = typeof m.data.tool_name === "string" ? m.data.tool_name : "";
      if (!runId || !toolName) continue;

      const phase = typeof m.data.phase === "string" ? m.data.phase : "";
      if (phase === "reasoning_summary") continue;
      const ts = typeof m.timestamp === "number" ? m.timestamp : 0;

      const cur: Run =
        byId.get(runId) ||
        ({
          runId,
          toolName,
          status: "running",
          explanations: [],
        } as Run);

      if (!cur.startTs) cur.startTs = ts;
      cur.toolName = toolName;

      if (phase === "tool_start") {
        cur.startTs = ts;
        cur.input = m.data.input;
        cur.status = "running";
      } else if (phase === "tool_end") {
        cur.endTs = ts;
        cur.output = m.data.output;
        cur.status = "success";
      } else if (phase === "tool_error") {
        cur.endTs = ts;
        cur.error = m.data.error;
        cur.status = "error";
      } else if (phase === "tool_explain") {
        const t = typeof m.data.text === "string" ? m.data.text : "";
        if (t) cur.explanations.push(t.replace(/^\[explain\]\s*/i, "").trim());
      }

      byId.set(runId, cur);
    }

    return Array.from(byId.values()).sort((a, b) => (a.startTs || 0) - (b.startTs || 0));
  }, [messages]);

  const reasoningSummaries = useMemo(() => {
    return messages
      .filter((m) => m.type === MessageType.TRACE_EVENT)
      .filter((m) => typeof m.data.phase === "string" && m.data.phase === "reasoning_summary")
      .map((m) => ({
        key: m.id || `reason-${m.timestamp ?? 0}`,
        ts: typeof m.timestamp === "number" ? m.timestamp : 0,
        text: typeof m.data.text === "string" ? m.data.text : "",
      }))
      .filter((x) => x.text.trim())
      .sort((a, b) => a.ts - b.ts);
  }, [messages]);

  const { isConnecting, isConnected, error, connect, send } = useMessageBus({
    wsUrl: AGENT_CONFIG.WS_URL,
    token: AGENT_CONFIG.TOKEN,
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

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    if (chatHistoryRef.current) {
      chatHistoryRef.current.scrollTop = chatHistoryRef.current.scrollHeight;
    }
  }, [messages]);

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

  const handleSendMessage = () => {
    if (inputValue.trim()) {
      send(MessageType.USER, { text: inputValue });
      setInputValue("");
      setMessages((prev) => [
        ...prev,
        {
          type: MessageType.USER,
          timestamp: Date.now(),
          data: {
            text: inputValue,
            sender: Sender.USER,
          },
          session_id: resolvedSessionId || undefined,
        },
      ]);
    }
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

  const renderActions = () => {
    const statusLines = messages
      .filter((m) => m.type === MessageType.UPDATE_FILE)
      .map((m, i) => ({
        key: m.id || `status-${i}-${m.timestamp ?? 0}`,
        text: typeof m.data.text === "string" ? m.data.text : "",
        ts: typeof m.timestamp === "number" ? m.timestamp : 0,
      }))
      .filter((x) => x.text.trim())
      .sort((a, b) => a.ts - b.ts);

    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div className="text-xs text-muted-foreground">
          {toolRuns.length} tool runs
          {statusLines.length ? `, ${statusLines.length} status updates` : ""}
        </div>

        {reasoningSummaries.length ? (
          <details
            className="border w-full bg-muted-foreground/5 rounded-md text-sm text-muted-foreground"
            style={{ padding: 10 }}
            open
          >
            <summary style={{ cursor: "pointer", fontWeight: 600 }}>
              Reasoning summary
            </summary>
            <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 8 }}>
              {reasoningSummaries.map((r) => (
                <div key={r.key} className="text-xs text-muted-foreground" style={{ whiteSpace: "pre-wrap" }}>
                  {r.text.replace(/^\[reasoning\]\s*/i, "")}
                </div>
              ))}
            </div>
          </details>
        ) : null}

        {toolRuns.map((r) => {
          const dur =
            r.startTs && r.endTs ? Math.max(0, r.endTs - r.startTs) : undefined;
          const badge =
            r.status === "running"
              ? "Running"
              : r.status === "success"
              ? "OK"
              : "Error";
          const badgeColor =
            r.status === "running"
              ? "bg-blue-500/10 text-blue-700"
              : r.status === "success"
              ? "bg-green-500/10 text-green-700"
              : "bg-red-500/10 text-red-700";
          const explain = r.explanations.length ? r.explanations[r.explanations.length - 1] : "";

          return (
            <details
              key={r.runId}
              className="border w-full bg-muted-foreground/5 rounded-md text-sm text-muted-foreground"
              style={{ padding: 10 }}
              open={r.status === "error"}
	            >
	              <summary style={{ cursor: "pointer", listStyle: "none" }}>
	                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
	                  <span className={`px-2 py-0.5 rounded ${badgeColor}`}>{badge}</span>
	                  <span style={{ fontWeight: 600 }}>{r.toolName}</span>
                  {dur !== undefined ? (
                    <span className="text-xs text-muted-foreground">
                      {dur}ms
                    </span>
                  ) : null}
                </div>
                {explain ? (
                  <div className="text-xs text-muted-foreground" style={{ marginTop: 4 }}>
                    {explain}
                  </div>
                ) : null}
              </summary>
              <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
                {r.input !== undefined ? (
                  <details className="border bg-background rounded-md" style={{ padding: 8 }}>
                    <summary style={{ cursor: "pointer", fontWeight: 600 }}>
                      Input
                    </summary>
                    <pre style={{ marginTop: 8, whiteSpace: "pre-wrap" }}>
                      {JSON.stringify(r.input, null, 2)}
                    </pre>
                  </details>
                ) : null}
                {r.output !== undefined ? (
                  <details className="border bg-background rounded-md" style={{ padding: 8 }}>
                    <summary style={{ cursor: "pointer", fontWeight: 600 }}>
                      Output
                    </summary>
                    <pre style={{ marginTop: 8, whiteSpace: "pre-wrap" }}>
                      {JSON.stringify(r.output, null, 2)}
                    </pre>
                  </details>
                ) : null}
                {r.error !== undefined ? (
                  <details className="border bg-background rounded-md" style={{ padding: 8 }} open>
                    <summary style={{ cursor: "pointer", fontWeight: 600 }}>
                      Error
                    </summary>
                    <pre style={{ marginTop: 8, whiteSpace: "pre-wrap" }}>
                      {JSON.stringify(r.error, null, 2)}
                    </pre>
                  </details>
                ) : null}
              </div>
            </details>
          );
        })}

        {statusLines.length ? (
          <details className="border w-full bg-muted-foreground/5 rounded-md text-sm text-muted-foreground" style={{ padding: 10 }}>
            <summary style={{ cursor: "pointer", fontWeight: 600 }}>Status</summary>
            <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 6 }}>
              {statusLines.map((s) => (
                <div key={s.key} className="text-xs text-muted-foreground">
                  {s.text}
                </div>
              ))}
            </div>
          </details>
        ) : null}
      </div>
    );
  };

  useEffect(() => {
    if (iframeUrl && isConnected) {
      setIframeError(false);
    }
  }, [iframeUrl, isConnected]);

  const handleIframeLoad = () => {
    console.log("Iframe loaded successfully:", iframeUrl);
    setIframeError(false);
    setIframeReady(true);
  };

  const handleIframeError = () => {
    console.error("Iframe failed to load:", iframeUrl);
    setIframeError(true);
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
      try {
        const url = new URL(`/api/projects/by-slug/${encodeURIComponent(slug)}`, AGENT_CONFIG.HTTP_URL).toString();
        const res = await fetch(url, { credentials: "include" });
        const data = (await res.json()) as unknown;
        const d = asObj(data);
        if (!res.ok) return;
        if (d && typeof d.project_id === "string") {
          setResolvedSessionId(d.project_id);
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
        // ignore
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

  const UpdateInProgressState = () => (
    <div className="flex flex-col items-center justify-center gap-6">
      <div className="animate-spin flex items-center justify-center text-gray-400">
        <Loader2 size={64} />
      </div>
      <div
        className="text-[18px] font-medium text-muted-foreground animate-pulse"
        style={{ marginTop: "24px" }}
      >
        Updating Workspace...
      </div>
      <p style={{ marginTop: "12px", textAlign: "center" }}>
        Please wait while we apply your changes to the website.
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

  const renderMainViewToggle = (activeView: "preview" | "code") => {
    return (
      <div className="flex gap-2">
        <ToggleButton
          active={activeView === "preview"}
          disabled={
            activeView === "preview" &&
            (!iframeUrl || !iframeReady || isUpdateInProgress || !initCompleted)
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
              ) : !iframeReady || isUpdateInProgress || !initCompleted ? (
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
                        visibility:
                          iframeReady && !isUpdateInProgress ? "visible" : "hidden",
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
                    {isUpdateInProgress || (!iframeReady && !initCompleted) ? (
                      <UpdateInProgressState />
                    ) : (
                      <LoadingState />
                    )}
                  </div>
                </>
              ) : (
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
                      visibility:
                        iframeReady && !isUpdateInProgress ? "visible" : "hidden",
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
              )}
            </div>

            <div className="w-full flex items-center justify-between bg-gray-200 border-t border-gray-200 px-6 h-14 absolute left-0 right-0 bottom-0 z-[3]">
              {renderMainViewToggle("preview")}
              <div className="flex gap-2">
                <DeviceButton
                  active={selectedDevice === "mobile"}
                  disabled={
                    !iframeUrl ||
                    !iframeReady ||
                    isUpdateInProgress ||
                    !initCompleted
                  }
                  onClick={() => setSelectedDevice("mobile")}
                >
                  <PhoneIcon />
                </DeviceButton>
                <DeviceButton
                  active={selectedDevice === "tablet"}
                  disabled={
                    !iframeUrl ||
                    !iframeReady ||
                    isUpdateInProgress ||
                    !initCompleted
                  }
                  onClick={() => setSelectedDevice("tablet")}
                >
                  <TabletIcon />
                </DeviceButton>
                <DeviceButton
                  active={selectedDevice === "desktop"}
                  disabled={
                    !iframeUrl ||
                    !iframeReady ||
                    isUpdateInProgress ||
                    !initCompleted
                  }
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
            <div
              className="text-[18px] font-medium text-muted-foreground"
              style={{ marginTop: "24px" }}
            >
              Connect to start building
            </div>

            {error && (
              <div className="border border-red-400 rounded-md p-3 mt-4 text-destructive">
                <div className="text-sm">Error: {error}</div>
              </div>
            )}

            <Button
              onClick={() => {
                connect().catch((e) => console.error("Connect failed:", e));
              }}
              disabled={!resolvedSessionId || isConnecting}
              style={{ marginTop: "16px" }}
            >
              {isConnecting ? "Connecting..." : "Connect"}
            </Button>

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
        className="p-6 flex flex-col text-white gap-6 h-full min-w-[340px] bg-black/35 border-l border-white/10"
        style={{ width: `${chatWidth}px` }}
      >
        <div className="flex flex-row items-center gap-3">
          <img
            className="w-14 h-14 object-contain"
            src="/amicable-logo.svg"
            alt="Amicable"
            loading="eager"
            decoding="async"
          />
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <div style={{ fontWeight: 600, lineHeight: 1.1 }}>
              {projectInfo?.name || "Project"}
            </div>
            {projectInfo?.slug ? (
              <div className="text-xs text-muted-foreground">/{projectInfo.slug}</div>
            ) : null}
          </div>
          <div className="flex-1" />
          <AgentAuthStatus />
        </div>

        <div className="flex flex-col min-h-0 flex-1">
          <div
            className="flex flex-col gap-2.5 overflow-y-auto flex-1 min-h-0"
            ref={chatHistoryRef}
          >
            {messages
              .filter((msg) => {
                if (msg.type === MessageType.TRACE_EVENT) return false;
                if (msg.type === MessageType.UPDATE_FILE) return false;
                if (msg.type === MessageType.UPDATE_IN_PROGRESS) return false;
                if (msg.type === MessageType.UPDATE_COMPLETED) return false;
                return (
                  msg.data.text &&
                  typeof msg.data.text === "string" &&
                  msg.data.text.trim()
                );
              })
              .sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0))
              .map((msg, index) => {
                const isUser = msg.data.sender === Sender.USER;
                return (
                  <div
                    key={msg.id || `msg-${index}-${msg.timestamp ?? 0}`}
                    className={cn("flex", isUser ? "justify-end" : "justify-start")}
                  >
                    <div
                      className={cn(
                        "p-3 rounded-md max-w-[70%]",
                        "border w-full bg-muted-foreground/10 rounded-md text-sm text-muted-foreground"
                      )}
                    >
                      {!isUser ? renderUiBlocks(msg.data.ui_blocks) : null}
                      <p
                        style={{
                          whiteSpace: "pre-wrap",
                        }}
                        className={isUser ? "text-white" : "text-foreground"}
                      >
                        {String(msg.data.text || "")}
                      </p>
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

          <div
            className="border-t"
            style={{
              padding: "10px 12px",
              maxHeight: 260,
              overflow: "auto",
              background: "rgba(0,0,0,0.02)",
            }}
          >
            {renderActions()}
          </div>
        </div>

        <div className="mt-auto flex flex-row gap-2">
          {pendingHitl ? (
            <div style={{ marginBottom: 12 }}>
              <HitlPanel />
            </div>
          ) : null}
          <Input
            placeholder="Ask Amicable..."
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSendMessage()}
            disabled={!isConnected || !iframeReady || !!pendingHitl}
          />
          <Button
            onClick={handleSendMessage}
            disabled={
              !isConnected ||
              !iframeReady ||
              !!pendingHitl ||
              !inputValue.trim()
            }
          >
            Send
          </Button>
        </div>
      </div>
    </div>
  );
};

export default Create;
