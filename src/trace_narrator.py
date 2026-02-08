from __future__ import annotations

import os
from typing import Any


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return bool(default)
    return raw in ("1", "true", "yes", "y", "on")


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return int(default)
    try:
        return int(raw)
    except Exception:
        return int(default)


def narrator_enabled() -> bool:
    return _env_bool("AMICABLE_TRACE_NARRATOR_ENABLED", False)


def narrator_model() -> str:
    return (os.environ.get("AMICABLE_TRACE_NARRATOR_MODEL") or "").strip() or (
        "anthropic:claude-haiku-4-5"
    )


def _extract_summary(tool_name: str, payload: Any) -> str:
    """Heuristic summary for tool outputs/errors."""
    if tool_name == "execute" and isinstance(payload, dict):
        exit_code = payload.get("exit_code")
        out = payload.get("output")
        if isinstance(out, str):
            snippet = out.strip().splitlines()[:6]
            text = "\n".join(snippet)
            if len(out) > len(text):
                text = text + "\n..."
            if exit_code is not None:
                return f"exit_code={exit_code}\n{text}".strip()
            return text.strip()
    if tool_name in ("write_file", "edit_file") and isinstance(payload, dict):
        fp = payload.get("file_path") or payload.get("path")
        if isinstance(fp, str) and fp:
            return fp
    if tool_name.startswith("db_") and isinstance(payload, str):
        return payload[:4000]
    if isinstance(payload, str):
        return payload[:4000]
    return ""


class TraceNarrator:
    """Generates user-facing explanations for tool activity.

    Intended to be cheap: either heuristics-only, or optionally backed by a small model.
    """

    def __init__(self) -> None:
        self._enabled = narrator_enabled()
        self._model_name = narrator_model()
        self._max_chars = max(200, _env_int("AMICABLE_TRACE_NARRATOR_MAX_CHARS", 280))
        self._llm = None

    def enabled(self) -> bool:
        return self._enabled

    async def aexplain(
        self,
        *,
        phase: str,
        tool_name: str,
        tool_input: Any | None = None,
        tool_output: Any | None = None,
        tool_error: Any | None = None,
    ) -> str:
        if not self._enabled:
            return ""

        # Prefer deterministic heuristics; LLM is optional.
        heuristic = self._heuristic(
            phase=phase,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
            tool_error=tool_error,
        )
        if heuristic:
            return heuristic[: self._max_chars]

        llm = await self._ensure_llm()
        if llm is None:
            return ""

        # Keep prompts tiny and avoid leaking raw tool output.
        summary = _extract_summary(tool_name, tool_output or tool_error or {})
        prompt = (
            "Explain this tool activity to a non-technical user in ONE short sentence.\n"
            "Avoid jargon. Do not mention internal IDs. Do not include secrets.\n\n"
            f"phase={phase}\n"
            f"tool={tool_name}\n"
            f"summary={summary}\n"
        )

        try:
            msg = await llm.ainvoke(prompt)  # type: ignore[no-any-return]
            text = getattr(msg, "content", "") if msg is not None else ""
            if isinstance(text, str):
                return text.strip()[: self._max_chars]
        except Exception:
            return ""
        return ""

    async def areason(
        self,
        *,
        user_request: str,
        tool_trace: list[str],
        status: str,
    ) -> str:
        """High-level reasoning summary without exposing chain-of-thought.

        This summarizes observable activity (tools, QA, pauses) in a user-friendly way.
        """
        req = (user_request or "").strip()
        trace = [t.strip() for t in tool_trace if isinstance(t, str) and t.strip()]
        trace_txt = "\n".join(trace[:20])

        # Heuristic first (avoid extra model calls).
        heuristic = self._heuristic_reason(
            user_request=req,
            tool_trace=trace,
            status=status,
        )
        if heuristic:
            return heuristic[: self._max_chars]

        # Optional: LLM-backed improvement, only when narrator is enabled.
        if not self._enabled:
            return ""

        llm = await self._ensure_llm()
        if llm is None:
            return ""

        prompt = (
            "Write a short, user-facing summary of what the agent is doing and why.\n"
            "Constraints:\n"
            "- 1 to 2 sentences\n"
            "- Do NOT reveal chain-of-thought or internal reasoning.\n"
            "- Do NOT include secrets.\n"
            "- Do NOT mention internal IDs.\n\n"
            f"user_request={req[:600]}\n"
            f"status={status}\n"
            "observable_actions:\n"
            f"{trace_txt[:1500]}\n"
        )

        try:
            msg = await llm.ainvoke(prompt)  # type: ignore[no-any-return]
            text = getattr(msg, "content", "") if msg is not None else ""
            if isinstance(text, str):
                return text.strip()[: self._max_chars]
        except Exception:
            return ""
        return ""

    def _heuristic(
        self,
        *,
        phase: str,
        tool_name: str,
        tool_input: Any | None,
        tool_output: Any | None,
        _tool_error: Any | None,
    ) -> str:
        if phase == "tool_start":
            if tool_name in ("ls", "glob", "grep", "read_file"):
                return "Looking through the project files."
            if tool_name in ("write_file", "edit_file"):
                fp = None
                if isinstance(tool_input, dict):
                    fp = tool_input.get("file_path")
                if isinstance(fp, str) and fp:
                    return f"Updating {fp}."
                return "Updating a project file."
            if tool_name == "execute":
                cmd = None
                if isinstance(tool_input, dict):
                    cmd = tool_input.get("command")
                if isinstance(cmd, str) and cmd:
                    snippet = cmd if len(cmd) <= 80 else (cmd[:77] + "...")
                    return f"Running: {snippet}"
                return "Running a command."
            if tool_name.startswith("db_"):
                return "Updating the database schema."

        if phase == "tool_end":
            if tool_name == "execute" and isinstance(tool_output, dict):
                exit_code = tool_output.get("exit_code")
                if exit_code == 0:
                    return "Command finished successfully."
                if exit_code is not None:
                    return f"Command finished with exit code {exit_code}."
                return "Command finished."
            if tool_name in ("write_file", "edit_file"):
                return "File updated."
            if tool_name.startswith("db_"):
                return "Database updated."

        if phase == "tool_error":
            if tool_name == "execute":
                return "That command failed."
            if tool_name.startswith("db_"):
                return "That database change failed."
            return "That step failed."

        return ""

    def _heuristic_reason(
        self,
        *,
        user_request: str,
        tool_trace: list[str],
        status: str,
    ) -> str:
        # Keep this very general and non-sensitive.
        lower = " ".join(tool_trace).lower()
        lower_req = (user_request or "").lower()
        did_files = ("write_file" in lower) or ("edit_file" in lower)
        did_cmds = "execute" in lower
        did_db = "db_" in lower or "database" in lower or "hasura" in lower_req
        did_qa = "qa" in lower or "lint" in lower or "typecheck" in lower or "build" in lower

        parts: list[str] = []
        if did_files:
            parts.append("I updated your project files")
        if did_db:
            parts.append("I updated your app's database schema")
        if did_cmds or did_qa:
            parts.append("and ran checks/commands to validate the changes")

        if not parts:
            parts.append("I reviewed the project and planned the next steps")

        if status == "paused_for_approval":
            return (" ".join(parts) + ", but paused to request your approval before continuing.").strip()

        if status == "completed":
            return (" ".join(parts) + " to move your request forward.").strip()

        return (" ".join(parts) + ".").strip()

    async def _ensure_llm(self):
        if self._llm is not None:
            return self._llm
        try:
            from langchain.chat_models import init_chat_model  # type: ignore

            self._llm = init_chat_model(self._model_name)
            return self._llm
        except Exception:
            self._llm = None
            return None
