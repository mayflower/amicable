from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)


def _safe_jsonable(obj: Any, *, max_str_len: int = 5000, max_depth: int = 6) -> Any:
    if max_depth <= 0:
        return "<truncated>"
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    if isinstance(obj, str):
        return obj if len(obj) <= max_str_len else (obj[: max_str_len - 3] + "...")
    if isinstance(obj, (list, tuple)):
        return [
            _safe_jsonable(x, max_str_len=max_str_len, max_depth=max_depth - 1)
            for x in obj
        ]
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            kk = str(k)
            out[kk] = _safe_jsonable(
                v, max_str_len=max_str_len, max_depth=max_depth - 1
            )
        return out
    # Fallback for non-serializable objects.
    return _safe_jsonable(str(obj), max_str_len=max_str_len, max_depth=max_depth - 1)


def _redact_large_media(obj: Any, *, max_depth: int = 8) -> Any:
    if max_depth <= 0:
        return "<truncated>"
    if isinstance(obj, list):
        return [_redact_large_media(v, max_depth=max_depth - 1) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_redact_large_media(v, max_depth=max_depth - 1) for v in obj)
    if not isinstance(obj, dict):
        return obj

    out: dict[str, Any] = {}
    block_type = str(obj.get("type") or "").lower()
    for k, v in obj.items():
        kk = str(k)
        if (
            kk in ("base64", "image_base64", "data")
            and isinstance(v, str)
            and (kk != "data" or block_type in ("image", "audio", "video", "file"))
        ):
            out[kk] = f"<redacted:{len(v)} chars>"
            continue
        out[kk] = _redact_large_media(v, max_depth=max_depth - 1)
    return out


def _safe_trace_payload(obj: Any) -> Any:
    return _redact_large_media(_safe_jsonable(obj))


def _pretty_json(obj: Any) -> str:
    try:
        return json.dumps(obj, indent=2, sort_keys=True)
    except Exception:
        return str(obj)


def _deepagents_model() -> str:
    return (
        os.environ.get("DEEPAGENTS_MODEL") or "anthropic:claude-sonnet-4-5-20250929"
    ).strip()


def _deepagents_validate() -> bool:
    return (os.environ.get("DEEPAGENTS_VALIDATE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _csv_env(name: str, default: str = "") -> list[str]:
    raw = (os.environ.get(name) or default).strip()
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return int(default)
    try:
        return int(raw)
    except Exception:
        return int(default)


def _deepagents_memory_sources() -> list[str]:
    return _csv_env(
        "DEEPAGENTS_MEMORY_SOURCES",
        default="/AGENTS.md,/.deepagents/AGENTS.md",
    )


def _deepagents_skills_sources() -> list[str]:
    return _csv_env(
        "DEEPAGENTS_SKILLS_SOURCES",
        default="/.deepagents/skills,/skills",
    )


def _deepagents_tool_retry_max_retries() -> int:
    return max(0, _env_int("DEEPAGENTS_TOOL_RETRY_MAX_RETRIES", 2))


def _langgraph_database_url() -> str:
    # Prefer an explicit DSN for LangGraph store/checkpointing.
    # Fall back to DATABASE_URL for compatibility with LangChain docs/examples.
    return (
        os.environ.get("AMICABLE_LANGGRAPH_DATABASE_URL")
        or os.environ.get("LANGGRAPH_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or ""
    ).strip()


def _deepagents_summarization_model() -> str:
    # Prefer a cheap model for summarization.
    return (
        os.environ.get("DEEPAGENTS_SUMMARIZATION_MODEL")
        or os.environ.get("AMICABLE_TRACE_NARRATOR_MODEL")
        or "anthropic:claude-haiku-4-5"
    ).strip()


def _deepagents_summarization_trigger_messages() -> int:
    # Summarize once the message history grows too large.
    return max(5, _env_int("DEEPAGENTS_SUMMARIZATION_TRIGGER_MESSAGES", 50))


def _deepagents_summarization_keep_messages() -> int:
    # Keep the most recent messages verbatim after summarizing.
    return max(2, _env_int("DEEPAGENTS_SUMMARIZATION_KEEP_MESSAGES", 20))


def _deepagents_interrupt_on() -> dict[str, Any]:
    raw = (os.environ.get("DEEPAGENTS_HITL_INTERRUPT_ON_JSON") or "{}").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        logger.warning(
            "Invalid DEEPAGENTS_HITL_INTERRUPT_ON_JSON; expected JSON object"
        )
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _langfuse_callback_handler():
    """Return a Langfuse CallbackHandler if configured, else None."""
    if not os.environ.get("LANGFUSE_PUBLIC_KEY"):
        return None
    try:
        from langfuse.langchain import CallbackHandler

        return CallbackHandler()
    except Exception:
        logger.warning("Langfuse callback init failed; tracing disabled", exc_info=True)
        return None


def _deepagents_qa_enabled() -> bool:
    # Backwards-compatible behavior: existing deployments set DEEPAGENTS_VALIDATE=1.
    from src.deepagents_backend.qa import qa_enabled_from_env

    return qa_enabled_from_env(legacy_validate_env=_deepagents_validate())


PermissionMode = Literal["default", "accept_edits", "bypass"]
ThinkingLevel = Literal["none", "think", "think_hard", "ultrathink"]


def _default_permission_mode() -> PermissionMode:
    raw = (os.environ.get("AMICABLE_PERMISSION_MODE_DEFAULT") or "default").strip()
    return normalize_permission_mode(raw)


def normalize_permission_mode(raw: Any) -> PermissionMode:
    mode = str(raw or "").strip().lower()
    if mode == "accept_edits":
        return "accept_edits"
    if mode == "bypass":
        return "bypass"
    return "default"


def normalize_thinking_level(raw: Any) -> ThinkingLevel:
    level = str(raw or "").strip().lower()
    if level in ("think", "think_hard", "ultrathink"):
        return level  # type: ignore[return-value]
    return "none"


def _compaction_trigger_messages() -> int:
    # Keep defaults aligned with deepagents summarization thresholds.
    return max(
        5,
        _env_int(
            "AMICABLE_COMPACTION_TRIGGER_MESSAGES",
            _deepagents_summarization_trigger_messages(),
        ),
    )


_DEEPAGENTS_SYSTEM_PROMPT = """You are Amicable, an AI editor for sandboxed application workspaces.

Your job: implement the user's request by editing the live sandboxed codebase. The user can see a live preview.

Long-term memory:
- You can store notes/preferences in files under `/memories/` (inside the sandbox workspace).
- Read `/AGENTS.md` in the sandbox and follow any stack-specific constraints and conventions it defines.

User-visible output format:
- Start responses with a **Plan** section (3-7 bullets).
- Then a short **Progress** section describing what you are doing right now.
- End with a **Result** section once complete.
- Do NOT reveal hidden chain-of-thought. Keep explanations concise and factual.

Generative UI (optional):
- You MAY include a machine-readable UI block for the editor to render:

```ui
{"type":"steps","title":"Plan","steps":["...","..."]}
```

Keep UI blocks small. Do not include secrets.

Hard rules:
- Prefer editing existing files over creating new ones.
- Do not add new dependencies unless absolutely necessary. If you must, update the appropriate project manifest (for example `/package.json`, `/pubspec.yaml`, `/requirements.txt`, or `/composer.json`) and explain why.
- Follow stack-specific conventions from `/AGENTS.md` and existing project files.
- For web UI changes, ensure changes render correctly inside an iframe and remain responsive.
- For React projects using `react-router-dom`, use `Routes` (not `Switch`).
- For visual/UI bugs, use the `capture_preview_screenshot` tool to inspect the live preview before guessing.

Workflow (always):
1. Start by writing a short plan.
2. Use filesystem tools to inspect the code before making edits.
3. Make minimal, relevant changes to satisfy the request.
4. After edits, verify the app still works.
"""


class MessageType(Enum):
    INIT = "init"
    USER = "user"
    AGENT_PARTIAL = "agent_partial"
    AGENT_FINAL = "agent_final"
    LOAD_CODE = "load_code"
    EDIT_CODE = "edit_code"
    UPDATE_IN_PROGRESS = "update_in_progress"
    UPDATE_FILE = "update_file"
    UPDATE_COMPLETED = "update_completed"
    TRACE_EVENT = "trace_event"
    HITL_REQUEST = "hitl_request"
    HITL_RESPONSE = "hitl_response"
    RUNTIME_ERROR = "runtime_error"
    ERROR = "error"
    PING = "ping"


@dataclass
class Message:
    id: str
    timestamp: int
    type: MessageType
    data: dict
    session_id: str

    @classmethod
    def new(
        cls,
        type: MessageType,
        data: dict,
        id: str | None = None,
        session_id: str | None = None,
    ) -> Message:
        return cls(
            type=type,
            data=data,
            id=id or str(uuid.uuid4()),
            timestamp=time.time_ns() // 1_000_000,
            session_id=session_id or str(uuid.uuid4()),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type.value,
            "data": self.data,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
        }


class ChatHistoryPersistenceError(RuntimeError):
    def __init__(self, *, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


class Agent:
    def __init__(self):
        # map of session_id -> {sandbox_id, url, ...}
        self.session_data: dict[str, dict] = {}
        self.history: list[dict] = []

        # DeepAgents state (initialized lazily).
        self._session_manager = None
        self._deep_agent = None
        self._deep_controller = None
        self._deep_controller_checkpointer = None

        # HITL pending state (session_id -> pending interrupt payload).
        self._hitl_pending: dict[str, dict[str, Any]] = {}

        # Optional tool-trace narrator.
        self._trace_narrator = None

        # Optional persistent LangGraph checkpointer (PostgresSaver) for HITL resume across restarts.
        self._lg_checkpointer_ctx = None
        self._lg_checkpointer = None

        # Avoid double-provisioning or double-injection for the same session_id when multiple
        # concurrent WS/HTTP requests hit init paths.
        self._ensure_env_lock_by_session: dict[str, asyncio.Lock] = {}

        # Optional lifecycle hooks (fail-open).
        self._hook_bus = None
        try:
            from src.agent_hooks import AgentHookBus

            self._hook_bus = AgentHookBus()
        except Exception:
            self._hook_bus = None

    def _ensure_env_lock(self, session_id: str) -> asyncio.Lock:
        lock = self._ensure_env_lock_by_session.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._ensure_env_lock_by_session[session_id] = lock
        return lock

    async def _get_langgraph_checkpointer(self):
        """Return an AsyncPostgresSaver if configured, else None."""
        if self._lg_checkpointer is not None:
            return self._lg_checkpointer

        dsn = _langgraph_database_url()
        if not dsn:
            logger.info(
                "LangGraph checkpointing disabled (no AMICABLE_LANGGRAPH_DATABASE_URL/LANGGRAPH_DATABASE_URL/DATABASE_URL); "
                "using in-memory checkpointing"
            )
            return None

        try:
            from langgraph.checkpoint.postgres.aio import (
                AsyncPostgresSaver,  # type: ignore
            )
        except Exception:
            logger.warning(
                "AsyncPostgresSaver unavailable (install langgraph-checkpoint-postgres + psycopg[binary]); checkpointing stays in-memory"
            )
            return None

        try:
            ctx = AsyncPostgresSaver.from_conn_string(dsn)
            checkpointer = await ctx.__aenter__()
            await checkpointer.setup()
        except Exception:
            logger.exception(
                "Failed to initialize AsyncPostgresSaver; checkpointing stays in-memory"
            )
            return None

        self._lg_checkpointer_ctx = ctx
        self._lg_checkpointer = checkpointer
        logger.info("LangGraph AsyncPostgresSaver initialized for checkpointing")
        return self._lg_checkpointer

    def has_pending_hitl(self, session_id: str) -> bool:
        return session_id in self._hitl_pending

    def _get_trace_narrator(self):
        # Lazy import to keep minimal env behavior.
        if self._trace_narrator is not None:
            return self._trace_narrator
        try:
            from src.trace_narrator import TraceNarrator

            self._trace_narrator = TraceNarrator()
        except Exception:
            self._trace_narrator = None
        return self._trace_narrator

    def set_session_controls(
        self,
        session_id: str,
        *,
        permission_mode: str | None = None,
        thinking_level: str | None = None,
    ) -> None:
        meta = self.session_data.get(session_id)
        if not isinstance(meta, dict):
            meta = {}
            self.session_data[session_id] = meta

        current_mode = meta.get("permission_mode")
        current_level = meta.get("thinking_level")
        mode = normalize_permission_mode(
            permission_mode
            if permission_mode is not None
            else (
                current_mode
                if isinstance(current_mode, str)
                else _default_permission_mode()
            )
        )
        level = normalize_thinking_level(
            thinking_level
            if thinking_level is not None
            else (current_level if isinstance(current_level, str) else "none")
        )
        meta["permission_mode"] = mode
        meta["thinking_level"] = level

    def _permission_mode_for_session(self, session_id: str) -> PermissionMode:
        init_data = self.session_data.get(session_id)
        if isinstance(init_data, dict):
            mode = init_data.get("permission_mode")
            if isinstance(mode, str):
                return normalize_permission_mode(mode)
        return _default_permission_mode()

    def _thinking_level_for_session(self, session_id: str) -> ThinkingLevel:
        init_data = self.session_data.get(session_id)
        if isinstance(init_data, dict):
            level = init_data.get("thinking_level")
            if isinstance(level, str):
                return normalize_thinking_level(level)
        return "none"

    def _conversation_history(self, session_id: str) -> list[dict[str, str]]:
        init_data = self.session_data.get(session_id)
        if not isinstance(init_data, dict):
            init_data = {}
            self.session_data[session_id] = init_data
        raw = init_data.get("_conversation_history")
        if isinstance(raw, list):
            return raw
        history: list[dict[str, str]] = []
        init_data["_conversation_history"] = history
        return history

    def _append_conversation_turn(self, session_id: str, role: str, text: str) -> None:
        t = (text or "").strip()
        if not t:
            return
        history = self._conversation_history(session_id)
        history.append({"role": role, "text": t[:4000]})
        if len(history) > 250:
            del history[: len(history) - 250]

    def _normalize_history_role(self, raw: Any) -> str | None:
        role = str(raw or "").strip().lower()
        if role in ("human", "user"):
            return "user"
        if role in ("ai", "assistant"):
            return "assistant"
        return None

    def _message_content_to_text(self, content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                text = self._message_content_to_text(item)
                if text:
                    parts.append(text)
            return "".join(parts)
        if isinstance(content, dict):
            text = content.get("text")
            if isinstance(text, str):
                return text
            nested = content.get("content")
            return self._message_content_to_text(nested)
        text_attr = getattr(content, "text", None)
        if isinstance(text_attr, str):
            return text_attr
        nested_attr = getattr(content, "content", None)
        return self._message_content_to_text(nested_attr)

    def _strip_thinking_prefix(self, text: str) -> str:
        out = text.strip()
        if not out.startswith("Thinking level:"):
            return out
        sep = "\n\n"
        idx = out.find(sep)
        if idx < 0:
            return out
        return out[idx + len(sep) :].strip()

    def _sanitize_user_history_text(self, text: str) -> str:
        out = self._strip_thinking_prefix(text)

        workspace_prefix = "Workspace instruction context:\n"
        workspace_marker = "\n\nUser request:\n"
        if out.startswith(workspace_prefix):
            idx = out.rfind(workspace_marker)
            if idx >= 0:
                out = out[idx + len(workspace_marker) :].strip()

        out = self._strip_thinking_prefix(out)

        compact_prefix = "Compacted conversation context:\n"
        compact_marker = "\n\nCurrent request:\n"
        if out.startswith(compact_prefix):
            idx = out.rfind(compact_marker)
            if idx >= 0:
                out = out[idx + len(compact_marker) :].strip()

        return self._strip_thinking_prefix(out)

    def _is_internal_self_heal_prompt(self, text: str) -> bool:
        t = text.strip()
        if "Please fix the cause, then make QA pass." not in t:
            return False
        return t.startswith("QA failed on `") or t.startswith(
            "QA failed, but no command output was captured."
        )

    def _history_item_role_text(self, item: Any) -> tuple[str, str] | None:
        role_raw: Any = None
        content: Any = None

        if isinstance(item, tuple) and len(item) >= 2:
            role_raw = item[0]
            content = item[1]
        elif isinstance(item, dict):
            role_raw = item.get("role") or item.get("type")
            content = item.get("content")
            if content is None and isinstance(item.get("text"), str):
                content = item.get("text")
        else:
            role_raw = getattr(item, "role", None) or getattr(item, "type", None)
            content = getattr(item, "content", None)

        role = self._normalize_history_role(role_raw)
        if role is None:
            return None

        text = self._message_content_to_text(content).strip()
        if not text:
            return None
        if role == "user":
            text = self._sanitize_user_history_text(text)
            if not text or self._is_internal_self_heal_prompt(text):
                return None
        return role, text[:4000]

    def _normalize_conversation_history(
        self, items: list[Any]
    ) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        for item in items:
            parsed = self._history_item_role_text(item)
            if parsed is None:
                continue
            role, text = parsed
            out.append({"role": role, "text": text})
        if len(out) > 250:
            out = out[-250:]
        return out

    def _set_conversation_history(
        self, session_id: str, history: list[dict[str, str]]
    ) -> None:
        init_data = self.session_data.get(session_id)
        if not isinstance(init_data, dict):
            init_data = {}
            self.session_data[session_id] = init_data
        init_data["_conversation_history"] = history[-250:]

    def _state_values_from_snapshot(self, snapshot: Any) -> dict[str, Any]:
        if isinstance(snapshot, dict):
            values = snapshot.get("values")
            if isinstance(values, dict):
                return values
            return snapshot
        values = getattr(snapshot, "values", None)
        if isinstance(values, dict):
            return values
        return {}

    async def _controller_state_snapshot(self, session_id: str) -> Any:
        if self._deep_controller is None:
            return None
        config: dict[str, Any] = {
            "configurable": {"thread_id": session_id, "checkpoint_ns": "controller"}
        }
        controller = self._deep_controller

        aget_state = getattr(controller, "aget_state", None)
        if callable(aget_state):
            try:
                return await aget_state(config=config)
            except TypeError:
                return await aget_state(config)

        get_state = getattr(controller, "get_state", None)
        if callable(get_state):
            def _call_get_state():
                try:
                    return get_state(config=config)
                except TypeError:
                    return get_state(config)

            return await asyncio.to_thread(_call_get_state)

        return None

    async def _restore_conversation_history_from_checkpoint(
        self, session_id: str
    ) -> list[dict[str, str]]:
        snapshot = await self._controller_state_snapshot(session_id)
        values = self._state_values_from_snapshot(snapshot)
        raw_messages = values.get("messages")
        if not isinstance(raw_messages, list):
            return []
        return self._normalize_conversation_history(raw_messages)

    async def ensure_ws_chat_history_ready(
        self, session_id: str
    ) -> list[dict[str, str]]:
        checkpointer = await self._get_langgraph_checkpointer()
        if checkpointer is None:
            raise ChatHistoryPersistenceError(
                code="chat_history_persistence_required",
                detail=(
                    "Chat history persistence is required for this workspace. "
                    "Configure AMICABLE_LANGGRAPH_DATABASE_URL and ensure "
                    "langgraph-checkpoint-postgres is installed."
                ),
            )

        history = self._normalize_conversation_history(
            self._conversation_history(session_id)
        )
        if history:
            self._set_conversation_history(session_id, history)
            return history[-20:]

        try:
            await self._ensure_deep_agent()
            restored = await self._restore_conversation_history_from_checkpoint(
                session_id
            )
        except ChatHistoryPersistenceError:
            raise
        except Exception as exc:
            raise ChatHistoryPersistenceError(
                code="chat_history_restore_failed",
                detail=f"Failed to restore persisted chat history: {exc}",
            ) from exc

        self._set_conversation_history(session_id, restored)
        return restored[-20:]

    def _compose_workspace_instruction_context(self, session_id: str) -> str:
        if self._session_manager is None:
            return ""
        try:
            from src.prompting.instruction_loader import compose_instruction_prompt

            backend = self._session_manager.get_backend(session_id)
            composed = compose_instruction_prompt(
                base_prompt="",
                backend=backend,
            )
            return composed.prompt.strip()
        except Exception:
            return ""

    def _maybe_compact_user_text(
        self,
        *,
        session_id: str,
        user_text: str,
    ) -> tuple[str, dict[str, Any] | None]:
        history = self._conversation_history(session_id)
        threshold = _compaction_trigger_messages()
        if len(history) < threshold:
            return user_text, None

        keep_recent = _deepagents_summarization_keep_messages()
        if keep_recent < 1:
            keep_recent = 1

        recent = history[-keep_recent:] if keep_recent < len(history) else list(history)
        older = history[: max(0, len(history) - len(recent))]

        init_data = self.session_data.get(session_id)
        prior_summary = ""
        if isinstance(init_data, dict):
            ps = init_data.get("_conversation_summary")
            if isinstance(ps, str):
                prior_summary = ps

        bullets: list[str] = []
        if prior_summary.strip():
            bullets.append(prior_summary.strip())
        for item in older[-80:]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "msg")
            text = str(item.get("text") or "").replace("\n", " ").strip()
            if text:
                bullets.append(f"{role}: {text[:220]}")

        if isinstance(init_data, dict):
            qa_last = init_data.get("_last_qa_failure")
            if isinstance(qa_last, str) and qa_last.strip():
                bullets.append(f"last_qa_failure: {qa_last[:900]}")
        if session_id in self._hitl_pending:
            bullets.append("pending_hitl: unresolved approval is in progress")

        merged_summary = "\n".join(f"- {b}" for b in bullets if b.strip()).strip()
        if len(merged_summary) > 8_000:
            merged_summary = merged_summary[:8_000]

        if isinstance(init_data, dict):
            init_data["_conversation_summary"] = merged_summary
            init_data["_conversation_history"] = recent

        compacted = (
            "Compacted conversation context:\n"
            f"{merged_summary}\n\n"
            "Current request:\n"
            f"{user_text}"
        )
        return compacted, {
            "history_before": len(history),
            "history_after": len(recent),
            "summary_chars": len(merged_summary),
            "threshold": threshold,
        }

    async def _emit_hook(self, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._hook_bus is None:
            return {"event": event, "called": False, "results": []}
        try:
            return await self._hook_bus.emit(event, payload)
        except Exception as exc:
            return {
                "event": event,
                "called": False,
                "results": [{"status": "error", "error": str(exc)}],
            }

    async def emit_session_start_hook(
        self,
        *,
        session_id: str,
    ) -> dict[str, Any]:
        return await self._emit_hook(
            "session_start",
            {
                "session_id": session_id,
                "permission_mode": self._permission_mode_for_session(session_id),
                "thinking_level": self._thinking_level_for_session(session_id),
            },
        )

    async def init(
        self,
        session_id: str,
        template_id: str | None = None,
        slug: str | None = None,
    ) -> bool:
        exists = await self._ensure_app_environment(
            session_id, template_id=template_id, slug=slug
        )
        return exists

    async def _ensure_app_environment(
        self,
        session_id: str,
        *,
        template_id: str | None = None,
        slug: str | None = None,
    ) -> bool:
        # This method does a lot of synchronous I/O (Hasura, k8s, sandbox runtime).
        # Run the heavy lifting in a background thread so we never block the main
        # event loop (otherwise /healthz and websockets will stall and readiness will fail).
        lock = self._ensure_env_lock(session_id)
        async with lock:
            if session_id in self.session_data:
                return True
            return await asyncio.to_thread(
                self._ensure_app_environment_sync,
                session_id,
                template_id=template_id,
                slug=slug,
            )

    def _ensure_app_environment_sync(
        self,
        session_id: str,
        *,
        template_id: str | None = None,
        slug: str | None = None,
    ) -> bool:
        from src.db.provisioning import hasura_client_from_env, require_hasura_from_env
        from src.deepagents_backend.session_sandbox_manager import SessionSandboxManager
        from src.templates.registry import (
            default_template_id,
            k8s_template_name_for,
            parse_template_id,
        )

        # This deployment requires Hasura. Fail fast for clearer errors.
        require_hasura_from_env()

        if self._session_manager is None:
            self._session_manager = SessionSandboxManager()

        # Resolve missing slug from the DB so all init paths (WS + HTTP sandbox FS)
        # can create/reuse the same sandbox and generate stable preview URLs.
        effective_slug = slug
        if effective_slug is None:
            try:
                from src.projects.store import get_project_any_owner

                client = hasura_client_from_env()
                p = get_project_any_owner(client, project_id=session_id)
                if p is not None and isinstance(p.slug, str) and p.slug.strip():
                    effective_slug = p.slug.strip()
            except Exception:
                effective_slug = slug

        effective_template_id = parse_template_id(template_id) if template_id else None
        if effective_template_id is None:
            try:
                from src.projects.store import get_project_template_id_any_owner

                client = hasura_client_from_env()
                stored = get_project_template_id_any_owner(
                    client, project_id=session_id
                )
                effective_template_id = parse_template_id(stored)
            except Exception:
                effective_template_id = None
        if effective_template_id is None:
            effective_template_id = default_template_id()

        sandbox_template_name = k8s_template_name_for(effective_template_id)
        sess = self._session_manager.ensure_session(
            session_id, template_name=sandbox_template_name, slug=effective_slug
        )

        backend = None

        # Poll the sandbox runtime API until it accepts connections. The K8s
        # readiness probe should handle this, but a short retry here avoids
        # races when the probe hasn't caught up yet.
        try:
            import time as _time

            backend = self._session_manager.get_backend(session_id)
            for _attempt in range(15):
                try:
                    backend.execute("true")
                    break
                except Exception:
                    _time.sleep(1)
        except Exception:
            pass

        # Ensure the conventional memories directory exists inside the sandbox workspace.
        # (This is sandbox-local, not store-backed.)
        try:
            if backend is None:
                backend = self._session_manager.get_backend(session_id)
            backend.execute("cd /app && mkdir -p memories")
        except Exception:
            pass

        init_data: dict[str, Any] = {
            # Prefer a slug-based preview hostname when we have a slug. With the
            # preview-router resolver in place, this remains stable even if the
            # underlying sandbox_id is hash-based or if the slug changes later.
            "url": sess.preview_url,
            "sandbox_id": sess.sandbox_id,
            "exists": sess.exists,
            "app_id": session_id,
            "template_id": effective_template_id,
            "k8s_template_name": sandbox_template_name,
            "permission_mode": _default_permission_mode(),
            "thinking_level": "none",
            "_conversation_history": [],
            "_conversation_summary": "",
            "_last_qa_failure": "",
        }

        # Persist sandbox_id (best-effort) for preview routing and debugging.
        try:
            from src.projects.store import set_project_sandbox_id_any_owner

            client = hasura_client_from_env()
            set_project_sandbox_id_any_owner(
                client, project_id=session_id, sandbox_id=str(sess.sandbox_id)
            )
        except Exception:
            pass

        # Now that we have both PREVIEW_BASE_DOMAIN and the slug, override the
        # init preview URL to use the slug host label if possible.
        try:
            base = (os.environ.get("PREVIEW_BASE_DOMAIN") or "").strip().lstrip(".")
            scheme = (os.environ.get("PREVIEW_SCHEME") or "https").strip()
            if effective_slug and base:
                init_data["url"] = f"{scheme}://{effective_slug}.{base}/"
        except Exception:
            pass

        # Platform scaffolding: Backstage + SonarQube + TechDocs (+ optional CI).
        # Non-destructive (create-only) and best-effort.
        try:
            from src.platform_scaffold.scaffold import (
                ensure_platform_scaffold,
                scaffold_on_existing_enabled,
            )

            should_scaffold = (not bool(sess.exists)) or scaffold_on_existing_enabled()
            if should_scaffold:
                if backend is None:
                    backend = self._session_manager.get_backend(session_id)

                project_name = None
                project_slug = slug
                project_prompt = None
                repo_web_url = None

                # Best-effort project metadata from Hasura (no ownership enforcement).
                try:
                    from src.projects.store import get_project_any_owner

                    client = hasura_client_from_env()
                    p = get_project_any_owner(client, project_id=session_id)
                    if p is not None:
                        project_name = p.name
                        project_slug = p.slug
                        project_prompt = p.project_prompt
                        repo_web_url = p.gitlab_web_url
                except Exception:
                    pass

                # GitLab context for source-location/repo_url fallback.
                try:
                    from src.gitlab.config import (
                        git_sync_branch,
                        gitlab_base_url,
                        gitlab_group_path,
                    )

                    branch = git_sync_branch()
                    base = gitlab_base_url()
                    group = gitlab_group_path()
                except Exception:
                    branch = "main"
                    base = None
                    group = None

                ensure_platform_scaffold(
                    backend,
                    project_id=session_id,
                    template_id=str(effective_template_id),
                    project_name=project_name,
                    project_slug=project_slug,
                    project_prompt=project_prompt,
                    repo_web_url=repo_web_url,
                    branch=str(branch or "main"),
                    gitlab_base_url=base,
                    gitlab_group_path=group,
                    create_ci=True,
                )
        except Exception:
            logger.exception("platform scaffolding failed (continuing)")

        # DB provisioning + sandbox injection (required).
        from urllib.parse import urlparse

        from src.db.provisioning import ensure_app, rotate_app_key, verify_app_key
        from src.db.sandbox_inject import (
            ensure_index_includes_db_script,
            ensure_laravel_welcome_includes_db_script,
            ensure_next_layout_includes_db_script,
            ensure_nuxt_config_includes_db_script,
            ensure_remix_root_includes_db_script,
            ensure_sveltekit_app_html_includes_db_script,
            laravel_db_paths,
            next_db_paths,
            nuxt_db_paths,
            parse_db_js,
            remix_db_paths,
            render_db_js,
            render_runtime_js,
            runtime_js_path_for_inject_kind,
            sveltekit_db_paths,
            vite_db_paths,
        )
        from src.templates.registry import template_spec

        client = hasura_client_from_env()
        app = ensure_app(client, app_id=session_id)

        # Build proxy URL for the browser to call (no Hasura secrets).
        public_base = (os.environ.get("AMICABLE_PUBLIC_BASE_URL") or "").strip().rstrip(
            "/"
        ) or (os.environ.get("PUBLIC_BASE_URL") or "").strip().rstrip("/")
        graphql_path = f"/db/apps/{session_id}/graphql"
        graphql_url = f"{public_base}{graphql_path}" if public_base else graphql_path

        backend = self._session_manager.get_backend(session_id)
        spec = template_spec(effective_template_id)
        inject_kind = spec.db_inject_kind

        db_js_path = "/amicable-db.js"
        runtime_js_path = "/amicable-runtime.js"
        entry_paths: tuple[str, ...] = ()
        ensure_entry = None
        if inject_kind == "vite_index_html":
            db_js_path, index_path = vite_db_paths()
            entry_paths = (index_path,)
            ensure_entry = ensure_index_includes_db_script
        elif inject_kind == "next_layout_tsx":
            db_js_path, entry_paths = next_db_paths()
            ensure_entry = ensure_next_layout_includes_db_script
        elif inject_kind == "remix_root_tsx":
            db_js_path, entry_paths = remix_db_paths()
            ensure_entry = ensure_remix_root_includes_db_script
        elif inject_kind == "nuxt_config_ts":
            db_js_path, entry_paths = nuxt_db_paths()
            ensure_entry = ensure_nuxt_config_includes_db_script
        elif inject_kind == "sveltekit_app_html":
            db_js_path, app_html = sveltekit_db_paths()
            entry_paths = (app_html,)
            ensure_entry = ensure_sveltekit_app_html_includes_db_script
        elif inject_kind == "laravel_blade":
            db_js_path, entry_paths = laravel_db_paths()
            ensure_entry = ensure_laravel_welcome_includes_db_script
        runtime_js_path = runtime_js_path_for_inject_kind(inject_kind)

        # Determine app_key to inject:
        # - if newly created/rotated, we have plaintext app_key
        # - else, attempt to read it from the sandbox and validate against stored hash
        app_key = app.app_key
        if not app_key:
            downloads = backend.download_files([db_js_path])
            existing_key: str | None = None
            if (
                downloads
                and downloads[0].error is None
                and downloads[0].content is not None
            ):
                text = downloads[0].content.decode("utf-8", errors="replace")
                obj = parse_db_js(text) or {}
                k = obj.get("appKey")
                if isinstance(k, str) and k:
                    existing_key = k

            if existing_key and verify_app_key(app=app, app_key=existing_key):
                app_key = existing_key
            else:
                rotated = rotate_app_key(client, app_id=session_id)
                app_key = rotated.app_key
                app = rotated

        if isinstance(app_key, str) and app_key:
            parsed = urlparse(str(sess.preview_url or ""))
            preview_origin = (
                f"{parsed.scheme}://{parsed.netloc}"
                if parsed.scheme and parsed.netloc
                else ""
            )
            db_js = render_db_js(
                app_id=session_id,
                graphql_url=graphql_url,
                app_key=app_key,
                preview_origin=preview_origin,
            )
            runtime_js = render_runtime_js()

            # Ensure the browser gets the injected db file. Optionally patch
            # the stack entrypoint to include the script tag.
            if entry_paths and ensure_entry is not None:
                downloads = backend.download_files(list(entry_paths))
                entry_path = None
                entry_text = ""
                for idx, d in enumerate(downloads):
                    if d.error is None and d.content is not None:
                        entry_path = entry_paths[idx]
                        entry_text = d.content.decode("utf-8", errors="replace")
                        break

                if entry_path and entry_text:
                    updated = ensure_entry(entry_text)
                    backend.upload_files(
                        [
                            (db_js_path, db_js.encode("utf-8")),
                            (runtime_js_path, runtime_js.encode("utf-8")),
                            (entry_path, updated.encode("utf-8")),
                        ]
                    )
                else:
                    backend.upload_files(
                        [
                            (db_js_path, db_js.encode("utf-8")),
                            (runtime_js_path, runtime_js.encode("utf-8")),
                        ]
                    )
            else:
                backend.upload_files(
                    [
                        (db_js_path, db_js.encode("utf-8")),
                        (runtime_js_path, runtime_js.encode("utf-8")),
                    ]
                )

        init_data["app_id"] = session_id
        init_data["db"] = {"graphql_url": graphql_url}
        init_data["db_schema"] = app.schema_name
        init_data["db_role"] = app.role_name

        self.session_data[session_id] = init_data
        return bool(sess.exists)

    def get_pending_hitl(self, session_id: str) -> dict[str, Any] | None:
        pending = self._hitl_pending.get(session_id)
        if not pending:
            return None
        # Only return the request payload; keep internal fields private.
        return {
            "interrupt_id": pending.get("interrupt_id"),
            "request": pending.get("request"),
        }

    def _preview_url_candidates(self, session_id: str) -> list[str]:
        candidates: list[str] = []
        if self._session_manager is not None:
            try:
                internal = self._session_manager.get_internal_preview_url(session_id)
                if isinstance(internal, str) and internal.strip():
                    candidates.append(internal.strip())
            except Exception:
                pass

        init_data = self.session_data.get(session_id)
        if isinstance(init_data, dict):
            public = init_data.get("url")
            if isinstance(public, str) and public.strip():
                candidates.append(public.strip())

        # De-dupe while preserving order.
        seen: set[str] = set()
        out: list[str] = []
        for c in candidates:
            if c not in seen:
                out.append(c)
                seen.add(c)
        return out

    def _capture_preview_screenshot(
        self,
        *,
        session_id: str,
        path: str = "/",
        full_page: bool = True,
        timeout_s: int = 15,
        viewport_width: int = 1280,
        viewport_height: int = 800,
    ) -> dict[str, Any]:
        from src.deepagents_backend.preview_screenshot import capture_preview_screenshot

        result = capture_preview_screenshot(
            source_urls=self._preview_url_candidates(session_id),
            path=path,
            timeout_ms=max(1, int(timeout_s)) * 1000,
            full_page=bool(full_page),
            viewport_width=max(1, int(viewport_width)),
            viewport_height=max(1, int(viewport_height)),
        )

        payload: dict[str, Any] = {
            "ok": result.ok,
            "path": result.path,
            "target_url": result.target_url,
            "source_url": result.source_url,
            "mime_type": result.mime_type,
            "width": result.width,
            "height": result.height,
            "error": result.error,
            "attempted_urls": result.attempted_urls,
        }
        if result.image_bytes is not None:
            payload["image_base64"] = base64.b64encode(result.image_bytes).decode(
                "ascii"
            )
        return payload

    async def capture_preview_screenshot(
        self,
        *,
        session_id: str,
        path: str = "/",
        full_page: bool = True,
        timeout_s: int = 15,
        viewport_width: int = 1280,
        viewport_height: int = 800,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._capture_preview_screenshot,
            session_id=session_id,
            path=path,
            full_page=full_page,
            timeout_s=timeout_s,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
        )

    async def send_feedback(
        self,
        *,
        session_id: str,
        feedback: str,
        user_content_blocks: list[dict[str, Any]] | None = None,
    ):
        # Per-run tool journal: cleared at the start so the eventual git commit
        # message only describes this run.
        try:
            from src.deepagents_backend.tool_journal import clear as _clear_tool_journal

            _clear_tool_journal(session_id)
        except Exception:
            pass

        yield Message.new(
            MessageType.UPDATE_IN_PROGRESS, {}, session_id=session_id
        ).to_dict()

        # Defensive: ensure sandbox exists even if the frontend skipped init.
        await self._ensure_app_environment(session_id)
        self.set_session_controls(session_id)

        await self._ensure_deep_agent()

        assert self._deep_agent is not None
        assert self._session_manager is not None
        assert self._deep_controller is not None

        from src.db.context import reset_current_app_id, set_current_app_id

        ctx_token = set_current_app_id(session_id)

        plan_msg_id = str(uuid.uuid4())
        file_msg_id = str(uuid.uuid4())

        buffer = ""
        last_partial_at = 0.0
        sent_final = False
        final_from_end: str | None = None
        interrupted = False
        saw_git_sync = False
        controller_failed = False
        sent_qa_failed_error = False
        tool_trace_for_reason: list[str] = []

        permission_mode = self._permission_mode_for_session(session_id)
        thinking_level = self._thinking_level_for_session(session_id)

        config: dict[str, Any] = {
            "configurable": {
                "thread_id": session_id,
                "checkpoint_ns": "controller",
                "permission_mode": permission_mode,
                "thinking_level": thinking_level,
            },
            "metadata": {"assistant_id": session_id},
            "recursion_limit": 500,
        }

        # Provide project/git metadata to the controller graph (best-effort).
        try:
            init_data = self.session_data.get(session_id) or {}
            proj = init_data.get("project") if isinstance(init_data, dict) else None
            git = init_data.get("git") if isinstance(init_data, dict) else None

            if isinstance(proj, dict):
                slug = proj.get("slug")
                name = proj.get("name")
                if isinstance(slug, str) and slug:
                    config["configurable"]["project_slug"] = slug
                if isinstance(name, str) and name:
                    config["configurable"]["project_name"] = name

            if isinstance(git, dict):
                repo_url = git.get("http_url_to_repo") or git.get("repo_http_url")
                if isinstance(repo_url, str) and repo_url:
                    config["configurable"]["git_repo_http_url"] = repo_url

                # Additional back-compat: accept "http_url_to_repo" directly.
                if "git_repo_http_url" not in config["configurable"]:
                    repo_url2 = git.get("http_url_to_repo")
                    if isinstance(repo_url2, str) and repo_url2:
                        config["configurable"]["git_repo_http_url"] = repo_url2

                # Back-compat: sometimes we only have a GitLab web URL.
                if "git_repo_http_url" not in config["configurable"]:
                    web_url = git.get("web_url")
                    if isinstance(web_url, str) and web_url:
                        url = web_url.rstrip("/")
                        if url.endswith(".git"):
                            config["configurable"]["git_repo_http_url"] = url
                        else:
                            config["configurable"]["git_repo_http_url"] = url + ".git"

                pwn = git.get("path_with_namespace")
                web = git.get("web_url")
                if isinstance(pwn, str) and pwn:
                    config["configurable"]["git_path_with_namespace"] = pwn
                if isinstance(web, str) and web:
                    config["configurable"]["git_web_url"] = web
        except Exception:
            pass
        lf = _langfuse_callback_handler()
        if lf is not None:
            lf.session_id = session_id
            config["callbacks"] = [lf]

        raw_user_text = feedback.strip()
        user_text = raw_user_text
        self._append_conversation_turn(session_id, "user", raw_user_text)

        submit_hook = await self._emit_hook(
            "user_prompt_submit",
            {
                "session_id": session_id,
                "permission_mode": permission_mode,
                "thinking_level": thinking_level,
                "user_text": raw_user_text[:4000],
            },
        )
        if submit_hook.get("called"):
            yield Message.new(
                MessageType.TRACE_EVENT,
                {
                    "phase": "user_prompt_submit",
                    "tool_name": "hooks",
                    "output": _safe_trace_payload(submit_hook),
                    "assistant_msg_id": plan_msg_id,
                },
                session_id=session_id,
            ).to_dict()

        compacted_text, compact_meta = self._maybe_compact_user_text(
            session_id=session_id, user_text=user_text
        )
        if compact_meta is not None:
            compact_hook = await self._emit_hook(
                "pre_compact",
                {
                    "session_id": session_id,
                    "meta": compact_meta,
                },
            )
            user_text = compacted_text
            yield Message.new(
                MessageType.TRACE_EVENT,
                {
                    "phase": "pre_compact",
                    "tool_name": "compaction",
                    "output": {
                        **compact_meta,
                        "hook_called": bool(compact_hook.get("called")),
                    },
                    "assistant_msg_id": plan_msg_id,
                },
                session_id=session_id,
            ).to_dict()

        workspace_ctx = self._compose_workspace_instruction_context(session_id)
        if workspace_ctx:
            user_text = (
                "Workspace instruction context:\n"
                f"{workspace_ctx}\n\n"
                "User request:\n"
                f"{user_text}"
            )

        if thinking_level != "none":
            user_text = f"Thinking level: {thinking_level}\n\n{user_text}"

        content_blocks = (
            [b for b in (user_content_blocks or []) if isinstance(b, dict)]
            if user_content_blocks
            else []
        )
        if content_blocks:
            non_text_blocks = [
                b for b in content_blocks if str(b.get("type") or "").lower() != "text"
            ]
            content_blocks = [{"type": "text", "text": user_text}, *non_text_blocks]

        def _chunk_text(chunk: Any) -> str:
            if chunk is None:
                return ""
            content = getattr(chunk, "content", None)
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if isinstance(item, str):
                        parts.append(item)
                    elif isinstance(item, dict):
                        text = item.get("text")
                        if isinstance(text, str):
                            parts.append(text)
                return "".join(parts)
            return ""

        def _message_text(msg: Any) -> str:
            if msg is None:
                return ""
            if isinstance(msg, dict):
                content = msg.get("content")
            else:
                content = getattr(msg, "content", None)

            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if isinstance(item, str):
                        parts.append(item)
                    elif isinstance(item, dict):
                        text = item.get("text")
                        if isinstance(text, str):
                            parts.append(text)
                return "".join(parts)
            return ""

        def _is_ai_message(msg: Any) -> bool:
            if isinstance(msg, dict):
                t = (msg.get("type") or msg.get("role") or "").lower()
            else:
                t = (
                    getattr(msg, "type", None) or getattr(msg, "role", None) or ""
                ).lower()
            return t in ("ai", "assistant")

        try:
            initial_messages = (
                [("user", user_text)]
                if not content_blocks
                else [
                    (
                        "user",
                        [
                            *content_blocks,
                        ],
                    )
                ]
            )
            async for event in self._deep_controller.astream_events(
                {"messages": initial_messages, "attempt": 0},
                config=config,
                version="v2",
            ):
                etype = event.get("event")
                name = event.get("name")
                data = event.get("data") or {}

                if etype == "on_chain_start" and name in (
                    "qa_validate",
                    "self_heal_message",
                    "qa_fail_summary",
                    "git_sync",
                ):
                    if name == "git_sync":
                        saw_git_sync = True
                    text = None
                    if name == "qa_validate":
                        text = "Running QA checks (lint/typecheck/build)..."
                    elif name == "self_heal_message":
                        text = "QA failed, attempting self-heal..."
                    elif name == "qa_fail_summary":
                        text = "QA still failing after self-heal attempts; preparing summary..."
                    elif name == "git_sync":
                        text = "Committing changes to GitLab..."
                    if text:
                        tool_trace_for_reason.append(name)
                        yield Message.new(
                            MessageType.UPDATE_FILE,
                            {"text": text},
                            id=file_msg_id,
                            session_id=session_id,
                        ).to_dict()

                if etype == "on_chain_stream":
                    chunk = (data or {}).get("chunk")
                    if isinstance(chunk, dict) and "__interrupt__" in chunk:
                        interrupts = chunk.get("__interrupt__")
                        intr = (
                            interrupts[0]
                            if isinstance(interrupts, (tuple, list)) and interrupts
                            else None
                        )
                        if intr is not None:
                            interrupt_id = getattr(intr, "id", None)
                            request = getattr(intr, "value", None)
                            if isinstance(interrupt_id, str) and interrupt_id:
                                # Record pending HITL so the WS handler can block user messages.
                                self._hitl_pending[session_id] = {
                                    "interrupt_id": interrupt_id,
                                    "request": request,
                                    "plan_msg_id": plan_msg_id,
                                    "file_msg_id": file_msg_id,
                                    "buffer": buffer,
                                }

                                yield Message.new(
                                    MessageType.HITL_REQUEST,
                                    {"interrupt_id": interrupt_id, "request": request},
                                    session_id=session_id,
                                ).to_dict()

                                # Stop typing (do NOT complete the update; we're paused).
                                final = buffer.strip() or (final_from_end or "").strip()
                                if not final:
                                    final = "Awaiting approval..."
                                yield Message.new(
                                    MessageType.AGENT_FINAL,
                                    {"text": final},
                                    id=plan_msg_id,
                                    session_id=session_id,
                                ).to_dict()
                                sent_final = True
                                interrupted = True
                                break

                if (
                    etype == "on_tool_start"
                    and isinstance(name, str)
                    and name in ("write_file", "edit_file", "execute")
                ):
                    tool_input = data.get("input") or {}
                    text = None
                    if isinstance(tool_input, dict):
                        if name in ("write_file", "edit_file"):
                            fp = tool_input.get("file_path")
                            if isinstance(fp, str):
                                text = f"{'Writing' if name == 'write_file' else 'Editing'} {fp}"
                        if name == "execute":
                            cmd = tool_input.get("command")
                            if isinstance(cmd, str):
                                # Keep this short; commands can be long.
                                snippet = (
                                    cmd if len(cmd) <= 120 else (cmd[:117] + "...")
                                )
                                text = f"Running {snippet}"
                    if text:
                        yield Message.new(
                            MessageType.UPDATE_FILE,
                            {"text": text},
                            id=file_msg_id,
                            session_id=session_id,
                        ).to_dict()

                if etype == "on_tool_start" and isinstance(name, str) and name:
                    tool_input = _safe_trace_payload(data.get("input"))
                    pre_tool_hook = await self._emit_hook(
                        "pre_tool_use",
                        {
                            "session_id": session_id,
                            "tool_name": name,
                            "input": tool_input,
                        },
                    )
                    if pre_tool_hook.get("called"):
                        yield Message.new(
                            MessageType.TRACE_EVENT,
                            {
                                "phase": "pre_tool_use",
                                "tool_name": name,
                                "output": _safe_trace_payload(pre_tool_hook),
                                "assistant_msg_id": plan_msg_id,
                            },
                            session_id=session_id,
                        ).to_dict()
                    # Minimal tool trace for reasoning summaries. Avoid including raw command strings.
                    if name in ("write_file", "edit_file") and isinstance(
                        tool_input, dict
                    ):
                        fp = tool_input.get("file_path")
                        if isinstance(fp, str) and fp:
                            tool_trace_for_reason.append(f"{name}: {fp}")
                        else:
                            tool_trace_for_reason.append(name)
                    else:
                        tool_trace_for_reason.append(name)
                    yield Message.new(
                        MessageType.TRACE_EVENT,
                        {
                            "phase": "tool_start",
                            "tool_name": name,
                            "input": tool_input,
                            "run_id": event.get("run_id"),
                            "parent_ids": event.get("parent_ids"),
                            "tags": event.get("tags"),
                            "assistant_msg_id": plan_msg_id,
                            "text": f"[tool_start] {name}\n{_pretty_json(tool_input)}",
                        },
                        session_id=session_id,
                    ).to_dict()

                if etype == "on_tool_end" and isinstance(name, str) and name:
                    tool_output = _safe_trace_payload(data.get("output"))
                    post_tool_hook = await self._emit_hook(
                        "post_tool_use",
                        {
                            "session_id": session_id,
                            "tool_name": name,
                            "output": tool_output,
                        },
                    )
                    if post_tool_hook.get("called"):
                        yield Message.new(
                            MessageType.TRACE_EVENT,
                            {
                                "phase": "post_tool_use",
                                "tool_name": name,
                                "output": _safe_trace_payload(post_tool_hook),
                                "assistant_msg_id": plan_msg_id,
                            },
                            session_id=session_id,
                        ).to_dict()
                    tool_trace_for_reason.append(f"{name}: ok")
                    yield Message.new(
                        MessageType.TRACE_EVENT,
                        {
                            "phase": "tool_end",
                            "tool_name": name,
                            "output": tool_output,
                            "run_id": event.get("run_id"),
                            "parent_ids": event.get("parent_ids"),
                            "tags": event.get("tags"),
                            "assistant_msg_id": plan_msg_id,
                            "text": f"[tool_end] {name}\n{_pretty_json(tool_output)}",
                        },
                        session_id=session_id,
                    ).to_dict()
                    narrator = self._get_trace_narrator()
                    if (
                        narrator is not None
                        and getattr(narrator, "enabled", lambda: False)()
                    ):
                        try:
                            explain = await narrator.aexplain(
                                phase="tool_end",
                                tool_name=name,
                                tool_input=None,
                                tool_output=tool_output,
                                tool_error=None,
                            )
                        except Exception:
                            explain = ""
                        if explain:
                            yield Message.new(
                                MessageType.TRACE_EVENT,
                                {
                                    "phase": "tool_explain",
                                    "tool_name": name,
                                    "text": f"[explain] {explain}",
                                    "run_id": event.get("run_id"),
                                    "assistant_msg_id": plan_msg_id,
                                },
                                session_id=session_id,
                            ).to_dict()

                if etype == "on_tool_error" and isinstance(name, str) and name:
                    err = _safe_trace_payload(data.get("error"))
                    tool_error_hook = await self._emit_hook(
                        "tool_error",
                        {
                            "session_id": session_id,
                            "tool_name": name,
                            "error": err,
                        },
                    )
                    if tool_error_hook.get("called"):
                        yield Message.new(
                            MessageType.TRACE_EVENT,
                            {
                                "phase": "tool_error",
                                "tool_name": name,
                                "output": _safe_trace_payload(tool_error_hook),
                                "assistant_msg_id": plan_msg_id,
                            },
                            session_id=session_id,
                        ).to_dict()
                    tool_trace_for_reason.append(f"{name}: error")
                    yield Message.new(
                        MessageType.TRACE_EVENT,
                        {
                            "phase": "tool_error",
                            "tool_name": name,
                            "error": err,
                            "run_id": event.get("run_id"),
                            "parent_ids": event.get("parent_ids"),
                            "tags": event.get("tags"),
                            "assistant_msg_id": plan_msg_id,
                            "text": f"[tool_error] {name}\n{_pretty_json(err)}",
                        },
                        session_id=session_id,
                    ).to_dict()
                    narrator = self._get_trace_narrator()
                    if (
                        narrator is not None
                        and getattr(narrator, "enabled", lambda: False)()
                    ):
                        try:
                            explain = await narrator.aexplain(
                                phase="tool_error",
                                tool_name=name,
                                tool_input=None,
                                tool_output=None,
                                tool_error=err,
                            )
                        except Exception:
                            explain = ""
                        if explain:
                            yield Message.new(
                                MessageType.TRACE_EVENT,
                                {
                                    "phase": "tool_explain",
                                    "tool_name": name,
                                    "text": f"[explain] {explain}",
                                    "run_id": event.get("run_id"),
                                    "assistant_msg_id": plan_msg_id,
                                },
                                session_id=session_id,
                            ).to_dict()

                if etype in ("on_chat_model_stream", "on_llm_stream"):
                    chunk = data.get("chunk")
                    delta = _chunk_text(chunk)
                    if delta:
                        buffer += delta
                        now = time.monotonic()
                        if now - last_partial_at >= 0.2:
                            yield Message.new(
                                MessageType.AGENT_PARTIAL,
                                {"text": buffer},
                                id=plan_msg_id,
                                session_id=session_id,
                            ).to_dict()
                            last_partial_at = now

                if etype == "on_chain_end":
                    if name == "qa_validate" and not sent_qa_failed_error:
                        out = data.get("output")
                        if isinstance(out, dict) and out.get("qa_passed") is False:
                            qa_results = out.get("qa_results")
                            results_for_ui: list[dict[str, Any]] = []
                            if isinstance(qa_results, list):
                                for r in qa_results:
                                    if not isinstance(r, dict):
                                        continue
                                    results_for_ui.append(
                                        {
                                            "command": r.get("command"),
                                            "exit_code": r.get("exit_code"),
                                            "truncated": r.get("truncated"),
                                        }
                                    )

                            last_detail = ""
                            if isinstance(qa_results, list) and qa_results:
                                last = qa_results[-1]
                                if isinstance(last, dict):
                                    cmd = last.get("command", "<unknown>")
                                    code = last.get("exit_code", "<unknown>")
                                    o = last.get("output", "")
                                    if not isinstance(o, str):
                                        o = str(o)
                                    if len(o) > 8000:
                                        o = o[:8000]
                                    last_detail = (
                                        f"QA failed on `{cmd}` (exit {code}). Output:\n\n{o}"
                                    )
                            if not last_detail:
                                last_detail = "QA failed (no output captured)."

                            yield Message.new(
                                MessageType.ERROR,
                                {
                                    "error": "qa_failed",
                                    "detail": last_detail,
                                    "qa_results": results_for_ui,
                                },
                                session_id=session_id,
                            ).to_dict()
                            init_data = self.session_data.get(session_id)
                            if isinstance(init_data, dict):
                                init_data["_last_qa_failure"] = last_detail
                            sent_qa_failed_error = True
                        elif isinstance(out, dict):
                            init_data = self.session_data.get(session_id)
                            if isinstance(init_data, dict):
                                init_data["_last_qa_failure"] = ""
                    if name == "git_sync":
                        out = data.get("output")
                        if isinstance(out, dict):
                            raw_warnings = out.get("git_warnings")
                            warnings = (
                                [
                                    str(w).strip()
                                    for w in raw_warnings
                                    if isinstance(w, str) and str(w).strip()
                                ]
                                if isinstance(raw_warnings, list)
                                else []
                            )
                            if warnings:
                                yield Message.new(
                                    MessageType.UPDATE_FILE,
                                    {"text": f"README policy warning: {warnings[0]}"},
                                    id=file_msg_id,
                                    session_id=session_id,
                                ).to_dict()

                    # Try to extract the final assistant message even when the provider
                    # does not emit token stream events.
                    output = data.get("output")
                    if isinstance(output, dict):
                        msgs = output.get("messages")
                        if isinstance(msgs, list):
                            for m in reversed(msgs):
                                if _is_ai_message(m):
                                    text = _message_text(m).strip()
                                    if text:
                                        final_from_end = text
                                        break

        except Exception as e:
            logger.exception("deepagents run failed")
            controller_failed = True
            yield Message.new(
                MessageType.ERROR,
                {"error": str(e)},
                session_id=session_id,
            ).to_dict()
        finally:
            reset_current_app_id(ctx_token)

        # Safety net: if the controller graph failed before reaching `git_sync`, attempt a
        # direct snapshot sync so "agent stops working" still produces a commit.
        if not interrupted:
            try:
                from src.gitlab.config import git_sync_enabled

                if git_sync_enabled() and (controller_failed or not saw_git_sync):
                    from src.gitlab.commit_message import (
                        append_commit_warnings,
                        evaluate_agent_readme_policy,
                        generate_agent_commit_message_llm,
                    )
                    from src.gitlab.config import git_agent_readme_policy_enabled
                    from src.gitlab.sync import sync_sandbox_tree_to_repo

                    repo_http_url = config.get("configurable", {}).get(
                        "git_repo_http_url"
                    )
                    project_slug = (
                        config.get("configurable", {}).get("project_slug") or session_id
                    )
                    if not (isinstance(repo_http_url, str) and repo_http_url):
                        yield Message.new(
                            MessageType.ERROR,
                            {"error": "git_sync_failed: missing repo url"},
                            session_id=session_id,
                        ).to_dict()
                    else:
                        yield Message.new(
                            MessageType.UPDATE_FILE,
                            {"text": "Committing changes to GitLab..."},
                            id=file_msg_id,
                            session_id=session_id,
                        ).to_dict()
                        assert self._session_manager is not None
                        backend = self._session_manager.get_backend(session_id)
                        policy_warnings: list[str] = []

                        def _msg(diff_stat: str, name_status: str) -> str:
                            agent_summary = (
                                buffer.strip() or (final_from_end or "")
                            ).strip()
                            msg = generate_agent_commit_message_llm(
                                user_request=raw_user_text,
                                agent_summary=agent_summary,
                                project_slug=str(project_slug),
                                qa_passed=None,
                                qa_last_output="",
                                diff_stat=diff_stat,
                                name_status=name_status,
                                tool_journal_summary=None,
                            )
                            if git_agent_readme_policy_enabled():
                                warnings = evaluate_agent_readme_policy(name_status)
                                policy_warnings[:] = warnings
                                return append_commit_warnings(msg, warnings)
                            return msg

                        await asyncio.to_thread(
                            sync_sandbox_tree_to_repo,
                            backend,
                            repo_http_url=repo_http_url,
                            project_slug=str(project_slug),
                            commit_message_fn=_msg,
                        )
                        if policy_warnings:
                            yield Message.new(
                                MessageType.UPDATE_FILE,
                                {"text": f"README policy warning: {policy_warnings[0]}"},
                                id=file_msg_id,
                                session_id=session_id,
                            ).to_dict()
            except Exception as e:
                logger.exception("git sync fallback failed")
                yield Message.new(
                    MessageType.ERROR,
                    {"error": f"git_sync_failed: {e}"},
                    session_id=session_id,
                ).to_dict()

        # If we paused for HITL, do not mark the update as completed.
        if interrupted:
            narrator = self._get_trace_narrator()
            if narrator is not None:
                try:
                    reason = await narrator.areason(
                        user_request=raw_user_text,
                        tool_trace=tool_trace_for_reason,
                        status="paused_for_approval",
                    )
                except Exception:
                    reason = ""
                if reason:
                    yield Message.new(
                        MessageType.TRACE_EVENT,
                        {
                            "phase": "reasoning_summary",
                            "tool_name": "reasoning",
                            "text": f"[reasoning] {reason}",
                            "assistant_msg_id": plan_msg_id,
                        },
                        session_id=session_id,
                    ).to_dict()
            stop_hook = await self._emit_hook(
                "stop",
                {
                    "session_id": session_id,
                    "status": "paused_for_approval",
                    "assistant_msg_id": plan_msg_id,
                },
            )
            if stop_hook.get("called"):
                yield Message.new(
                    MessageType.TRACE_EVENT,
                    {
                        "phase": "stop",
                        "tool_name": "hooks",
                        "output": _safe_trace_payload(stop_hook),
                        "assistant_msg_id": plan_msg_id,
                    },
                    session_id=session_id,
                ).to_dict()
            return

        final = buffer.strip() or (final_from_end or "").strip()
        self._append_conversation_turn(session_id, "assistant", final)
        if final and not sent_final:
            yield Message.new(
                MessageType.AGENT_FINAL,
                {"text": final},
                id=plan_msg_id,
                session_id=session_id,
            ).to_dict()
            sent_final = True

        narrator = self._get_trace_narrator()
        if narrator is not None:
            try:
                reason = await narrator.areason(
                    user_request=raw_user_text,
                    tool_trace=tool_trace_for_reason,
                    status="completed",
                )
            except Exception:
                reason = ""
            if reason:
                yield Message.new(
                    MessageType.TRACE_EVENT,
                    {
                        "phase": "reasoning_summary",
                        "tool_name": "reasoning",
                        "text": f"[reasoning] {reason}",
                        "assistant_msg_id": plan_msg_id,
                    },
                    session_id=session_id,
                ).to_dict()

        stop_hook = await self._emit_hook(
            "stop",
            {
                "session_id": session_id,
                "status": "completed",
                "assistant_msg_id": plan_msg_id,
            },
        )
        if stop_hook.get("called"):
            yield Message.new(
                MessageType.TRACE_EVENT,
                {
                    "phase": "stop",
                    "tool_name": "hooks",
                    "output": _safe_trace_payload(stop_hook),
                    "assistant_msg_id": plan_msg_id,
                },
                session_id=session_id,
            ).to_dict()

        # Complete the update even on errors so the UI can clear "in progress".
        yield Message.new(
            MessageType.UPDATE_COMPLETED, {}, session_id=session_id
        ).to_dict()

    async def resume_hitl(
        self,
        *,
        session_id: str,
        interrupt_id: str,
        response: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        """Resume a paused DeepAgents controller run after a HITL interrupt."""
        pending = self._hitl_pending.get(session_id)
        if not pending:
            yield Message.new(
                MessageType.ERROR,
                {"error": "no pending HITL request for this session"},
                session_id=session_id,
            ).to_dict()
            return

        expected = pending.get("interrupt_id")
        if expected != interrupt_id:
            yield Message.new(
                MessageType.ERROR,
                {"error": "interrupt_id does not match pending request"},
                session_id=session_id,
            ).to_dict()
            return

        # Validate response matches request semantics (review_configs allowed_decisions).
        req = pending.get("request")
        if isinstance(req, dict):
            action_reqs = req.get("action_requests")
            review_cfgs = req.get("review_configs")
            decisions = response.get("decisions")

            if isinstance(action_reqs, list):
                if not isinstance(decisions, list) or len(decisions) != len(
                    action_reqs
                ):
                    yield Message.new(
                        MessageType.ERROR,
                        {
                            "error": "invalid HITL response: decisions length must match action_requests"
                        },
                        session_id=session_id,
                    ).to_dict()
                    return

                allowed_by_name: dict[str, set[str]] = {}
                if isinstance(review_cfgs, list):
                    for cfg in review_cfgs:
                        if not isinstance(cfg, dict):
                            continue
                        action_name = cfg.get("action_name")
                        allowed = cfg.get("allowed_decisions")
                        if (
                            isinstance(action_name, str)
                            and action_name
                            and isinstance(allowed, list)
                            and all(isinstance(x, str) for x in allowed)
                        ):
                            allowed_by_name[action_name] = set(allowed)

                for i, ar in enumerate(action_reqs):
                    if not isinstance(ar, dict):
                        continue
                    tool_name = ar.get("name")
                    if not isinstance(tool_name, str) or not tool_name:
                        continue
                    allowed = allowed_by_name.get(tool_name)
                    if not allowed:
                        continue
                    d = decisions[i]
                    if not isinstance(d, dict):
                        continue
                    dtype = d.get("type")
                    if isinstance(dtype, str) and dtype not in allowed:
                        yield Message.new(
                            MessageType.ERROR,
                            {
                                "error": f"invalid HITL response: decision {dtype!r} not allowed for tool {tool_name!r}"
                            },
                            session_id=session_id,
                        ).to_dict()
                        return

        await self._ensure_deep_agent()
        self.set_session_controls(session_id)
        assert self._deep_controller is not None

        from src.db.context import reset_current_app_id, set_current_app_id

        ctx_token = set_current_app_id(session_id)

        plan_msg_id = str(pending.get("plan_msg_id") or uuid.uuid4())
        file_msg_id = str(pending.get("file_msg_id") or uuid.uuid4())

        buffer = str(pending.get("buffer") or "")
        last_partial_at = 0.0
        sent_final = False
        final_from_end: str | None = None
        interrupted = False
        saw_git_sync = False
        controller_failed = False
        sent_qa_failed_error = False
        tool_trace_for_reason: list[str] = []

        permission_mode = self._permission_mode_for_session(session_id)
        thinking_level = self._thinking_level_for_session(session_id)
        config: dict[str, Any] = {
            "configurable": {
                "thread_id": session_id,
                "checkpoint_ns": "controller",
                "permission_mode": permission_mode,
                "thinking_level": thinking_level,
            },
            "metadata": {"assistant_id": session_id},
            "recursion_limit": 500,
        }

        # Provide project/git metadata to the controller graph (required for git_sync).
        try:
            init_data = self.session_data.get(session_id) or {}
            proj = init_data.get("project") if isinstance(init_data, dict) else None
            git = init_data.get("git") if isinstance(init_data, dict) else None

            if isinstance(proj, dict):
                slug = proj.get("slug")
                name = proj.get("name")
                if isinstance(slug, str) and slug:
                    config["configurable"]["project_slug"] = slug
                if isinstance(name, str) and name:
                    config["configurable"]["project_name"] = name

            if isinstance(git, dict):
                repo_url = git.get("http_url_to_repo") or git.get("repo_http_url")
                if isinstance(repo_url, str) and repo_url:
                    config["configurable"]["git_repo_http_url"] = repo_url

                if "git_repo_http_url" not in config["configurable"]:
                    web_url = git.get("web_url")
                    if isinstance(web_url, str) and web_url:
                        url = web_url.rstrip("/")
                        config["configurable"]["git_repo_http_url"] = (
                            url if url.endswith(".git") else url + ".git"
                        )

                pwn = git.get("path_with_namespace")
                web = git.get("web_url")
                if isinstance(pwn, str) and pwn:
                    config["configurable"]["git_path_with_namespace"] = pwn
                if isinstance(web, str) and web:
                    config["configurable"]["git_web_url"] = web
        except Exception:
            pass
        lf = _langfuse_callback_handler()
        if lf is not None:
            lf.session_id = session_id
            config["callbacks"] = [lf]

        def _chunk_text(chunk: Any) -> str:
            if chunk is None:
                return ""
            content = getattr(chunk, "content", None)
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if isinstance(item, str):
                        parts.append(item)
                    elif isinstance(item, dict):
                        text = item.get("text")
                        if isinstance(text, str):
                            parts.append(text)
                return "".join(parts)
            return ""

        def _message_text(msg: Any) -> str:
            if msg is None:
                return ""
            if isinstance(msg, dict):
                content = msg.get("content")
            else:
                content = getattr(msg, "content", None)

            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if isinstance(item, str):
                        parts.append(item)
                    elif isinstance(item, dict):
                        text = item.get("text")
                        if isinstance(text, str):
                            parts.append(text)
                return "".join(parts)
            return ""

        def _is_ai_message(msg: Any) -> bool:
            if isinstance(msg, dict):
                t = (msg.get("type") or msg.get("role") or "").lower()
            else:
                t = (
                    getattr(msg, "type", None) or getattr(msg, "role", None) or ""
                ).lower()
            return t in ("ai", "assistant")

        # We'll clear pending once we successfully enter resume.
        self._hitl_pending.pop(session_id, None)

        try:
            from langgraph.types import Command  # type: ignore

            async for event in self._deep_controller.astream_events(
                Command(resume=response),
                config=config,
                version="v2",
            ):
                etype = event.get("event")
                name = event.get("name")
                data = event.get("data") or {}

                if etype == "on_chain_start" and name in (
                    "qa_validate",
                    "self_heal_message",
                    "qa_fail_summary",
                    "git_sync",
                ):
                    if name == "git_sync":
                        saw_git_sync = True
                    text = None
                    if name == "qa_validate":
                        text = "Running QA checks (lint/typecheck/build)..."
                    elif name == "self_heal_message":
                        text = "QA failed, attempting self-heal..."
                    elif name == "qa_fail_summary":
                        text = "QA still failing after self-heal attempts; preparing summary..."
                    elif name == "git_sync":
                        text = "Committing changes to GitLab..."
                    if text:
                        tool_trace_for_reason.append(name)
                        yield Message.new(
                            MessageType.UPDATE_FILE,
                            {"text": text},
                            id=file_msg_id,
                            session_id=session_id,
                        ).to_dict()

                if etype == "on_chain_stream":
                    chunk = (data or {}).get("chunk")
                    if isinstance(chunk, dict) and "__interrupt__" in chunk:
                        interrupts = chunk.get("__interrupt__")
                        intr = (
                            interrupts[0]
                            if isinstance(interrupts, (tuple, list)) and interrupts
                            else None
                        )
                        if intr is not None:
                            new_interrupt_id = getattr(intr, "id", None)
                            request = getattr(intr, "value", None)
                            if isinstance(new_interrupt_id, str) and new_interrupt_id:
                                self._hitl_pending[session_id] = {
                                    "interrupt_id": new_interrupt_id,
                                    "request": request,
                                    "plan_msg_id": plan_msg_id,
                                    "file_msg_id": file_msg_id,
                                    "buffer": buffer,
                                }
                                yield Message.new(
                                    MessageType.HITL_REQUEST,
                                    {
                                        "interrupt_id": new_interrupt_id,
                                        "request": request,
                                    },
                                    session_id=session_id,
                                ).to_dict()
                                final = buffer.strip() or (final_from_end or "").strip()
                                if not final:
                                    final = "Awaiting approval..."
                                yield Message.new(
                                    MessageType.AGENT_FINAL,
                                    {"text": final},
                                    id=plan_msg_id,
                                    session_id=session_id,
                                ).to_dict()
                                sent_final = True
                                interrupted = True
                                break

                if etype == "on_tool_start" and isinstance(name, str) and name:
                    tool_input = _safe_trace_payload(data.get("input"))
                    pre_tool_hook = await self._emit_hook(
                        "pre_tool_use",
                        {
                            "session_id": session_id,
                            "tool_name": name,
                            "input": tool_input,
                        },
                    )
                    if pre_tool_hook.get("called"):
                        yield Message.new(
                            MessageType.TRACE_EVENT,
                            {
                                "phase": "pre_tool_use",
                                "tool_name": name,
                                "output": _safe_trace_payload(pre_tool_hook),
                                "assistant_msg_id": plan_msg_id,
                            },
                            session_id=session_id,
                        ).to_dict()
                    if name in ("write_file", "edit_file") and isinstance(
                        tool_input, dict
                    ):
                        fp = tool_input.get("file_path")
                        if isinstance(fp, str) and fp:
                            tool_trace_for_reason.append(f"{name}: {fp}")
                        else:
                            tool_trace_for_reason.append(name)
                    else:
                        tool_trace_for_reason.append(name)
                    yield Message.new(
                        MessageType.TRACE_EVENT,
                        {
                            "phase": "tool_start",
                            "tool_name": name,
                            "input": tool_input,
                            "run_id": event.get("run_id"),
                            "parent_ids": event.get("parent_ids"),
                            "tags": event.get("tags"),
                            "assistant_msg_id": plan_msg_id,
                            "text": f"[tool_start] {name}\n{_pretty_json(tool_input)}",
                        },
                        session_id=session_id,
                    ).to_dict()

                if etype == "on_tool_end" and isinstance(name, str) and name:
                    tool_output = _safe_trace_payload(data.get("output"))
                    post_tool_hook = await self._emit_hook(
                        "post_tool_use",
                        {
                            "session_id": session_id,
                            "tool_name": name,
                            "output": tool_output,
                        },
                    )
                    if post_tool_hook.get("called"):
                        yield Message.new(
                            MessageType.TRACE_EVENT,
                            {
                                "phase": "post_tool_use",
                                "tool_name": name,
                                "output": _safe_trace_payload(post_tool_hook),
                                "assistant_msg_id": plan_msg_id,
                            },
                            session_id=session_id,
                        ).to_dict()
                    tool_trace_for_reason.append(f"{name}: ok")
                    yield Message.new(
                        MessageType.TRACE_EVENT,
                        {
                            "phase": "tool_end",
                            "tool_name": name,
                            "output": tool_output,
                            "run_id": event.get("run_id"),
                            "parent_ids": event.get("parent_ids"),
                            "tags": event.get("tags"),
                            "assistant_msg_id": plan_msg_id,
                            "text": f"[tool_end] {name}\n{_pretty_json(tool_output)}",
                        },
                        session_id=session_id,
                    ).to_dict()
                    narrator = self._get_trace_narrator()
                    if (
                        narrator is not None
                        and getattr(narrator, "enabled", lambda: False)()
                    ):
                        try:
                            explain = await narrator.aexplain(
                                phase="tool_end",
                                tool_name=name,
                                tool_input=None,
                                tool_output=tool_output,
                                tool_error=None,
                            )
                        except Exception:
                            explain = ""
                        if explain:
                            yield Message.new(
                                MessageType.TRACE_EVENT,
                                {
                                    "phase": "tool_explain",
                                    "tool_name": name,
                                    "text": f"[explain] {explain}",
                                    "run_id": event.get("run_id"),
                                    "assistant_msg_id": plan_msg_id,
                                },
                                session_id=session_id,
                            ).to_dict()

                if etype == "on_tool_error" and isinstance(name, str) and name:
                    err = _safe_trace_payload(data.get("error"))
                    tool_error_hook = await self._emit_hook(
                        "tool_error",
                        {
                            "session_id": session_id,
                            "tool_name": name,
                            "error": err,
                        },
                    )
                    if tool_error_hook.get("called"):
                        yield Message.new(
                            MessageType.TRACE_EVENT,
                            {
                                "phase": "tool_error",
                                "tool_name": name,
                                "output": _safe_trace_payload(tool_error_hook),
                                "assistant_msg_id": plan_msg_id,
                            },
                            session_id=session_id,
                        ).to_dict()
                    tool_trace_for_reason.append(f"{name}: error")
                    yield Message.new(
                        MessageType.TRACE_EVENT,
                        {
                            "phase": "tool_error",
                            "tool_name": name,
                            "error": err,
                            "run_id": event.get("run_id"),
                            "parent_ids": event.get("parent_ids"),
                            "tags": event.get("tags"),
                            "assistant_msg_id": plan_msg_id,
                            "text": f"[tool_error] {name}\n{_pretty_json(err)}",
                        },
                        session_id=session_id,
                    ).to_dict()
                    narrator = self._get_trace_narrator()
                    if (
                        narrator is not None
                        and getattr(narrator, "enabled", lambda: False)()
                    ):
                        try:
                            explain = await narrator.aexplain(
                                phase="tool_error",
                                tool_name=name,
                                tool_input=None,
                                tool_output=None,
                                tool_error=err,
                            )
                        except Exception:
                            explain = ""
                        if explain:
                            yield Message.new(
                                MessageType.TRACE_EVENT,
                                {
                                    "phase": "tool_explain",
                                    "tool_name": name,
                                    "text": f"[explain] {explain}",
                                    "run_id": event.get("run_id"),
                                    "assistant_msg_id": plan_msg_id,
                                },
                                session_id=session_id,
                            ).to_dict()

                if etype in ("on_chat_model_stream", "on_llm_stream"):
                    chunk = data.get("chunk")
                    delta = _chunk_text(chunk)
                    if delta:
                        buffer += delta
                        now = time.monotonic()
                        if now - last_partial_at >= 0.2:
                            yield Message.new(
                                MessageType.AGENT_PARTIAL,
                                {"text": buffer},
                                id=plan_msg_id,
                                session_id=session_id,
                            ).to_dict()
                            last_partial_at = now

                if etype == "on_chain_end":
                    if name == "qa_validate" and not sent_qa_failed_error:
                        out = data.get("output")
                        if isinstance(out, dict) and out.get("qa_passed") is False:
                            qa_results = out.get("qa_results")
                            results_for_ui: list[dict[str, Any]] = []
                            if isinstance(qa_results, list):
                                for r in qa_results:
                                    if not isinstance(r, dict):
                                        continue
                                    results_for_ui.append(
                                        {
                                            "command": r.get("command"),
                                            "exit_code": r.get("exit_code"),
                                            "truncated": r.get("truncated"),
                                        }
                                    )

                            last_detail = ""
                            if isinstance(qa_results, list) and qa_results:
                                last = qa_results[-1]
                                if isinstance(last, dict):
                                    cmd = last.get("command", "<unknown>")
                                    code = last.get("exit_code", "<unknown>")
                                    o = last.get("output", "")
                                    if not isinstance(o, str):
                                        o = str(o)
                                    if len(o) > 8000:
                                        o = o[:8000]
                                    last_detail = (
                                        f"QA failed on `{cmd}` (exit {code}). Output:\n\n{o}"
                                    )
                            if not last_detail:
                                last_detail = "QA failed (no output captured)."

                            yield Message.new(
                                MessageType.ERROR,
                                {
                                    "error": "qa_failed",
                                    "detail": last_detail,
                                    "qa_results": results_for_ui,
                                },
                                session_id=session_id,
                            ).to_dict()
                            init_data = self.session_data.get(session_id)
                            if isinstance(init_data, dict):
                                init_data["_last_qa_failure"] = last_detail
                            sent_qa_failed_error = True
                        elif isinstance(out, dict):
                            init_data = self.session_data.get(session_id)
                            if isinstance(init_data, dict):
                                init_data["_last_qa_failure"] = ""
                    if name == "git_sync":
                        out = data.get("output")
                        if isinstance(out, dict):
                            raw_warnings = out.get("git_warnings")
                            warnings = (
                                [
                                    str(w).strip()
                                    for w in raw_warnings
                                    if isinstance(w, str) and str(w).strip()
                                ]
                                if isinstance(raw_warnings, list)
                                else []
                            )
                            if warnings:
                                yield Message.new(
                                    MessageType.UPDATE_FILE,
                                    {"text": f"README policy warning: {warnings[0]}"},
                                    id=file_msg_id,
                                    session_id=session_id,
                                ).to_dict()

                    output = data.get("output")
                    if isinstance(output, dict):
                        msgs = output.get("messages")
                        if isinstance(msgs, list):
                            for m in reversed(msgs):
                                if _is_ai_message(m):
                                    text = _message_text(m).strip()
                                    if text:
                                        final_from_end = text
                                        break

        except Exception as e:
            logger.exception("deepagents resume failed")
            controller_failed = True
            yield Message.new(
                MessageType.ERROR,
                {"error": str(e)},
                session_id=session_id,
            ).to_dict()
        finally:
            reset_current_app_id(ctx_token)

        if not interrupted:
            try:
                from src.gitlab.config import git_sync_enabled

                if git_sync_enabled() and (controller_failed or not saw_git_sync):
                    from src.gitlab.commit_message import (
                        append_commit_warnings,
                        evaluate_agent_readme_policy,
                        generate_agent_commit_message_llm,
                    )
                    from src.gitlab.config import git_agent_readme_policy_enabled
                    from src.gitlab.sync import sync_sandbox_tree_to_repo

                    repo_http_url = config.get("configurable", {}).get(
                        "git_repo_http_url"
                    )
                    project_slug = (
                        config.get("configurable", {}).get("project_slug") or session_id
                    )
                    if not (isinstance(repo_http_url, str) and repo_http_url):
                        yield Message.new(
                            MessageType.ERROR,
                            {"error": "git_sync_failed: missing repo url"},
                            session_id=session_id,
                        ).to_dict()
                    else:
                        yield Message.new(
                            MessageType.UPDATE_FILE,
                            {"text": "Committing changes to GitLab..."},
                            id=file_msg_id,
                            session_id=session_id,
                        ).to_dict()
                        assert self._session_manager is not None
                        backend = self._session_manager.get_backend(session_id)
                        policy_warnings: list[str] = []

                        def _msg(diff_stat: str, name_status: str) -> str:
                            agent_summary = (
                                buffer.strip() or (final_from_end or "")
                            ).strip()
                            msg = generate_agent_commit_message_llm(
                                user_request="(resumed after approval)",
                                agent_summary=agent_summary,
                                project_slug=str(project_slug),
                                qa_passed=None,
                                qa_last_output="",
                                diff_stat=diff_stat,
                                name_status=name_status,
                                tool_journal_summary=None,
                            )
                            if git_agent_readme_policy_enabled():
                                warnings = evaluate_agent_readme_policy(name_status)
                                policy_warnings[:] = warnings
                                return append_commit_warnings(msg, warnings)
                            return msg

                        await asyncio.to_thread(
                            sync_sandbox_tree_to_repo,
                            backend,
                            repo_http_url=repo_http_url,
                            project_slug=str(project_slug),
                            commit_message_fn=_msg,
                        )
                        if policy_warnings:
                            yield Message.new(
                                MessageType.UPDATE_FILE,
                                {"text": f"README policy warning: {policy_warnings[0]}"},
                                id=file_msg_id,
                                session_id=session_id,
                            ).to_dict()
            except Exception as e:
                logger.exception("git sync fallback failed")
                yield Message.new(
                    MessageType.ERROR,
                    {"error": f"git_sync_failed: {e}"},
                    session_id=session_id,
                ).to_dict()

        if interrupted:
            narrator = self._get_trace_narrator()
            if narrator is not None:
                try:
                    reason = await narrator.areason(
                        user_request="(resumed after approval)",
                        tool_trace=tool_trace_for_reason,
                        status="paused_for_approval",
                    )
                except Exception:
                    reason = ""
                if reason:
                    yield Message.new(
                        MessageType.TRACE_EVENT,
                        {
                            "phase": "reasoning_summary",
                            "tool_name": "reasoning",
                            "text": f"[reasoning] {reason}",
                            "assistant_msg_id": plan_msg_id,
                        },
                        session_id=session_id,
                    ).to_dict()
            stop_hook = await self._emit_hook(
                "stop",
                {
                    "session_id": session_id,
                    "status": "paused_for_approval",
                    "assistant_msg_id": plan_msg_id,
                },
            )
            if stop_hook.get("called"):
                yield Message.new(
                    MessageType.TRACE_EVENT,
                    {
                        "phase": "stop",
                        "tool_name": "hooks",
                        "output": _safe_trace_payload(stop_hook),
                        "assistant_msg_id": plan_msg_id,
                    },
                    session_id=session_id,
                ).to_dict()
            return

        final = buffer.strip() or (final_from_end or "").strip()
        self._append_conversation_turn(session_id, "assistant", final)
        if final and not sent_final:
            yield Message.new(
                MessageType.AGENT_FINAL,
                {"text": final},
                id=plan_msg_id,
                session_id=session_id,
            ).to_dict()
            sent_final = True

        narrator = self._get_trace_narrator()
        if narrator is not None:
            try:
                reason = await narrator.areason(
                    user_request="(resumed after approval)",
                    tool_trace=tool_trace_for_reason,
                    status="completed",
                )
            except Exception:
                reason = ""
            if reason:
                yield Message.new(
                    MessageType.TRACE_EVENT,
                    {
                        "phase": "reasoning_summary",
                        "tool_name": "reasoning",
                        "text": f"[reasoning] {reason}",
                        "assistant_msg_id": plan_msg_id,
                    },
                    session_id=session_id,
                ).to_dict()

        stop_hook = await self._emit_hook(
            "stop",
            {
                "session_id": session_id,
                "status": "completed",
                "assistant_msg_id": plan_msg_id,
            },
        )
        if stop_hook.get("called"):
            yield Message.new(
                MessageType.TRACE_EVENT,
                {
                    "phase": "stop",
                    "tool_name": "hooks",
                    "output": _safe_trace_payload(stop_hook),
                    "assistant_msg_id": plan_msg_id,
                },
                session_id=session_id,
            ).to_dict()

        yield Message.new(
            MessageType.UPDATE_COMPLETED, {}, session_id=session_id
        ).to_dict()

    async def _ensure_deep_agent(self) -> None:
        if self._deep_agent is not None and self._deep_controller is not None:
            return

        from deepagents import create_deep_agent

        checkpointer = await self._get_langgraph_checkpointer()

        from langchain.agents.middleware.tool_retry import ToolRetryMiddleware
        from langgraph.checkpoint.memory import MemorySaver

        from src.db.tools import get_db_tools
        from src.deepagents_backend.dangerous_db_hitl import DangerousDbHitlMiddleware
        from src.deepagents_backend.dangerous_ops_hitl import (
            DangerousExecuteHitlMiddleware,
        )
        from src.deepagents_backend.policy import SandboxPolicyWrapper
        from src.deepagents_backend.screenshot_tools import get_screenshot_tools
        from src.deepagents_backend.session_sandbox_manager import SessionSandboxManager
        from src.deepagents_backend.tool_journal import append as _append_tool_journal
        from src.deepagents_backend.web_tools import get_web_tools

        if self._session_manager is None:
            self._session_manager = SessionSandboxManager()

        # Stable policy defaults.
        deny_write_paths: list[str] = []
        deny_commands = [
            # Catastrophic deletes should be blocked regardless of HITL approval.
            "rm -rf /",
            "rm -rf /*",
            "--no-preserve-root",
            "shutdown",
            "reboot",
            "mkfs",
            ":(){:|:&};:",
        ]

        def policy_backend(thread_id: str):
            mode = self._permission_mode_for_session(thread_id)
            backend = self._session_manager.get_backend(thread_id)
            deny_write_prefixes = ["/node_modules/", "/.git/"]
            if mode in ("accept_edits", "bypass"):
                deny_write_prefixes = []
            return SandboxPolicyWrapper(
                backend,
                deny_write_paths=deny_write_paths,
                deny_write_prefixes=deny_write_prefixes,
                deny_commands=deny_commands,
                audit_log=lambda op, target, meta: _append_tool_journal(
                    thread_id,
                    op,
                    target,
                    {
                        **(meta if isinstance(meta, dict) else {}),
                        "permission_mode": mode,
                    },
                ),
            )

        def backend_factory(runtime: Any):
            # Runtime (model middleware) does not carry config; use LangGraph's
            # context-var based get_config() to retrieve the RunnableConfig
            # (which contains thread_id set by the controller graph).
            from langgraph.config import get_config as _lg_get_config

            try:
                config = _lg_get_config()
            except RuntimeError:
                config = getattr(runtime, "config", {}) or {}
            configurable = config.get("configurable", {}) or {}
            thread_id = configurable.get("thread_id", "default-thread")
            default_backend = policy_backend(thread_id)
            return default_backend

        # NOTE: TodoListMiddleware and SummarizationMiddleware are already added
        # internally by create_deep_agent(); including them here would cause a
        # "duplicate middleware" assertion error.
        def _should_require_hitl(thread_id: str) -> bool:
            return self._permission_mode_for_session(thread_id) != "bypass"

        middleware = [
            # Require approval before destructive deletes (e.g. rm/unlink/git clean/find -delete).
            DangerousExecuteHitlMiddleware(should_interrupt=_should_require_hitl),
            # Require approval before destructive DB ops (drop/truncate).
            DangerousDbHitlMiddleware(should_interrupt=_should_require_hitl),
            ToolRetryMiddleware(max_retries=_deepagents_tool_retry_max_retries()),
        ]

        db_tools = []
        try:
            db_tools = get_db_tools()
        except Exception:
            logger.exception("DB tools unavailable; continuing without DB tools")

        screenshot_tools = []
        try:
            screenshot_tools = get_screenshot_tools(
                capture_fn=lambda **kwargs: self._capture_preview_screenshot(**kwargs)
            )
        except Exception:
            logger.exception("Screenshot tools unavailable; continuing without them")

        web_tools = []
        try:
            web_tools = get_web_tools()
        except Exception:
            logger.exception("Web tools unavailable; continuing without them")

        memory_sources = _deepagents_memory_sources()
        system_prompt = _DEEPAGENTS_SYSTEM_PROMPT
        try:
            from src.prompting.instruction_loader import compose_instruction_prompt

            backend = self._session_manager.get_backend("default-thread")
            composed = compose_instruction_prompt(
                base_prompt=_DEEPAGENTS_SYSTEM_PROMPT, backend=backend
            )
            if composed.prompt.strip():
                system_prompt = composed.prompt
        except Exception:
            # Per-session instruction layering is applied at request time.
            system_prompt = _DEEPAGENTS_SYSTEM_PROMPT

        self._deep_agent = create_deep_agent(
            model=_deepagents_model(),
            system_prompt=system_prompt,
            checkpointer=checkpointer or MemorySaver(),
            backend=backend_factory,
            middleware=middleware,
            tools=[*db_tools, *screenshot_tools, *web_tools],
            memory=memory_sources,
            skills=_deepagents_skills_sources(),
            interrupt_on=_deepagents_interrupt_on(),
            store=None,
        )
        logger.info("DeepAgents initialized (model=%s)", _deepagents_model())

        # Build an outer controller graph that runs deterministic QA and self-healing.
        from src.deepagents_backend.controller_graph import build_controller_graph

        # Controller needs its own checkpointer for HITL resume.
        self._deep_controller_checkpointer = checkpointer or MemorySaver()
        self._deep_controller = build_controller_graph(
            deep_agent_runnable=self._deep_agent,
            get_backend=policy_backend,
            qa_enabled=_deepagents_qa_enabled(),
            checkpointer=self._deep_controller_checkpointer,
        )
        logger.info(
            "DeepAgents controller initialized (qa_enabled=%s)",
            _deepagents_qa_enabled(),
        )


def parse_ws_message(raw: str) -> dict:
    try:
        return json.loads(raw)
    except Exception:
        return {}
