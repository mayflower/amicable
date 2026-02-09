from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

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
        from langfuse.callback import CallbackHandler

        return CallbackHandler()
    except Exception:
        logger.warning("Langfuse callback init failed; tracing disabled", exc_info=True)
        return None


def _deepagents_qa_enabled() -> bool:
    # Backwards-compatible behavior: existing deployments set DEEPAGENTS_VALIDATE=1.
    from src.deepagents_backend.qa import qa_enabled_from_env

    return qa_enabled_from_env(legacy_validate_env=_deepagents_validate())


_DEEPAGENTS_SYSTEM_PROMPT = """You are Amicable, an AI editor for sandboxed web application workspaces.

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
- Do not add new dependencies unless absolutely necessary. If you must, update /package.json and explain why.
- Use Tailwind CSS for styling, and prefer shadcn/ui components where applicable.
- Ensure changes render correctly inside an iframe.
- Always produce responsive layouts.
- react-router-dom: use Routes (not Switch).

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

    async def _get_langgraph_checkpointer(self):
        """Return an AsyncPostgresSaver if configured, else None."""
        if self._lg_checkpointer is not None:
            return self._lg_checkpointer

        dsn = _langgraph_database_url()
        if not dsn:
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
        if session_id in self.session_data:
            return True

        from src.db.provisioning import db_enabled_from_env, hasura_client_from_env
        from src.deepagents_backend.session_sandbox_manager import SessionSandboxManager
        from src.templates.registry import (
            default_template_id,
            k8s_template_name_for,
            parse_template_id,
        )

        if self._session_manager is None:
            self._session_manager = SessionSandboxManager()

        # Resolve missing slug from the DB so all init paths (WS + HTTP sandbox FS)
        # can create/reuse the same sandbox and generate stable preview URLs.
        effective_slug = slug
        if effective_slug is None and db_enabled_from_env():
            try:
                from src.projects.store import get_project_any_owner

                client = hasura_client_from_env()
                p = get_project_any_owner(client, project_id=session_id)
                if p is not None and isinstance(p.slug, str) and p.slug.strip():
                    effective_slug = p.slug.strip()
            except Exception:
                effective_slug = slug

        effective_template_id = parse_template_id(template_id) if template_id else None
        if effective_template_id is None and db_enabled_from_env():
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

        # Ensure the conventional memories directory exists inside the sandbox workspace.
        # (This is sandbox-local, not store-backed.)
        try:
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
        }

        # Persist sandbox_id (best-effort) for preview routing and debugging.
        if db_enabled_from_env():
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
                repo_web_url = None

                # Best-effort project metadata from Hasura (no ownership enforcement).
                if db_enabled_from_env():
                    try:
                        from src.projects.store import get_project_any_owner

                        client = hasura_client_from_env()
                        p = get_project_any_owner(client, project_id=session_id)
                        if p is not None:
                            project_name = p.name
                            project_slug = p.slug
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
                    repo_web_url=repo_web_url,
                    branch=str(branch or "main"),
                    gitlab_base_url=base,
                    gitlab_group_path=group,
                    create_ci=True,
                )
        except Exception:
            logger.exception("platform scaffolding failed (continuing)")

        # DB provisioning + sandbox injection (optional if not configured).
        if db_enabled_from_env():
            try:
                from urllib.parse import urlparse

                from src.db.provisioning import (
                    ensure_app,
                    rotate_app_key,
                    verify_app_key,
                )
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
                    sveltekit_db_paths,
                    vite_db_paths,
                )
                from src.templates.registry import template_spec

                client = hasura_client_from_env()
                app = ensure_app(client, app_id=session_id)

                # Build proxy URL for the browser to call (no Hasura secrets).
                public_base = (
                    os.environ.get("AMICABLE_PUBLIC_BASE_URL") or ""
                ).strip().rstrip("/") or (
                    os.environ.get("PUBLIC_BASE_URL") or ""
                ).strip().rstrip("/")
                graphql_path = f"/db/apps/{session_id}/graphql"
                graphql_url = (
                    f"{public_base}{graphql_path}" if public_base else graphql_path
                )

                backend = self._session_manager.get_backend(session_id)
                spec = template_spec(effective_template_id)
                inject_kind = spec.db_inject_kind

                db_js_path = "/amicable-db.js"
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
                                    (entry_path, updated.encode("utf-8")),
                                ]
                            )
                        else:
                            backend.upload_files([(db_js_path, db_js.encode("utf-8"))])
                    else:
                        backend.upload_files([(db_js_path, db_js.encode("utf-8"))])

                init_data["app_id"] = session_id
                init_data["db"] = {"graphql_url": graphql_url}
                init_data["db_schema"] = app.schema_name
                init_data["db_role"] = app.role_name
            except Exception:
                logger.exception(
                    "DB provisioning/injection failed (continuing without DB)"
                )

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

    async def send_feedback(self, *, session_id: str, feedback: str):
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
        tool_trace_for_reason: list[str] = []

        config: dict[str, Any] = {
            "configurable": {"thread_id": session_id, "checkpoint_ns": "controller"},
            "metadata": {"assistant_id": session_id},
            "recursion_limit": 150,
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

        user_text = feedback.strip()

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
            async for event in self._deep_controller.astream_events(
                {
                    "messages": [("user", user_text)],
                    "attempt": 0,
                },
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
                    tool_input = _safe_jsonable(data.get("input"))
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
                    tool_output = _safe_jsonable(data.get("output"))
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
                    err = _safe_jsonable(data.get("error"))
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
                        generate_agent_commit_message_llm,
                    )
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

                        def _msg(diff_stat: str, name_status: str) -> str:
                            agent_summary = (
                                buffer.strip() or (final_from_end or "")
                            ).strip()
                            return generate_agent_commit_message_llm(
                                user_request=user_text,
                                agent_summary=agent_summary,
                                project_slug=str(project_slug),
                                qa_passed=None,
                                qa_last_output="",
                                diff_stat=diff_stat,
                                name_status=name_status,
                                tool_journal_summary=None,
                            )

                        await asyncio.to_thread(
                            sync_sandbox_tree_to_repo,
                            backend,
                            repo_http_url=repo_http_url,
                            project_slug=str(project_slug),
                            commit_message_fn=_msg,
                        )
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
                        user_request=user_text,
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
            return

        final = buffer.strip() or (final_from_end or "").strip()
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
                    user_request=user_text,
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
        tool_trace_for_reason: list[str] = []

        config: dict[str, Any] = {
            "configurable": {"thread_id": session_id, "checkpoint_ns": "controller"},
            "metadata": {"assistant_id": session_id},
            "recursion_limit": 150,
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
                    tool_input = _safe_jsonable(data.get("input"))
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
                    tool_output = _safe_jsonable(data.get("output"))
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
                    err = _safe_jsonable(data.get("error"))
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
                        generate_agent_commit_message_llm,
                    )
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

                        def _msg(diff_stat: str, name_status: str) -> str:
                            agent_summary = (
                                buffer.strip() or (final_from_end or "")
                            ).strip()
                            return generate_agent_commit_message_llm(
                                user_request="(resumed after approval)",
                                agent_summary=agent_summary,
                                project_slug=str(project_slug),
                                qa_passed=None,
                                qa_last_output="",
                                diff_stat=diff_stat,
                                name_status=name_status,
                                tool_journal_summary=None,
                            )

                        await asyncio.to_thread(
                            sync_sandbox_tree_to_repo,
                            backend,
                            repo_http_url=repo_http_url,
                            project_slug=str(project_slug),
                            commit_message_fn=_msg,
                        )
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
            return

        final = buffer.strip() or (final_from_end or "").strip()
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
        from src.deepagents_backend.session_sandbox_manager import SessionSandboxManager
        from src.deepagents_backend.tool_journal import append as _append_tool_journal

        if self._session_manager is None:
            self._session_manager = SessionSandboxManager()

        # Stable policy defaults.
        deny_write_paths: list[str] = []
        deny_write_prefixes = ["/node_modules/", "/.git/"]
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
            backend = self._session_manager.get_backend(thread_id)
            return SandboxPolicyWrapper(
                backend,
                deny_write_paths=deny_write_paths,
                deny_write_prefixes=deny_write_prefixes,
                deny_commands=deny_commands,
                audit_log=lambda op, target, meta: _append_tool_journal(
                    thread_id, op, target, meta
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
        middleware = [
            # Require approval before destructive deletes (e.g. rm/unlink/git clean/find -delete).
            DangerousExecuteHitlMiddleware(),
            # Require approval before destructive DB ops (drop/truncate).
            DangerousDbHitlMiddleware(),
            ToolRetryMiddleware(max_retries=_deepagents_tool_retry_max_retries()),
        ]

        db_tools = []
        try:
            db_tools = get_db_tools()
        except Exception:
            logger.exception("DB tools unavailable; continuing without DB tools")

        memory_sources = _deepagents_memory_sources()

        self._deep_agent = create_deep_agent(
            model=_deepagents_model(),
            system_prompt=_DEEPAGENTS_SYSTEM_PROMPT,
            checkpointer=checkpointer or MemorySaver(),
            backend=backend_factory,
            middleware=middleware,
            tools=db_tools,
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
