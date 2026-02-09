from __future__ import annotations

import os
import time
from typing import Any


def _commit_model() -> str:
    return (
        os.environ.get("AMICABLE_GIT_COMMIT_MESSAGE_MODEL")
        or os.environ.get("AMICABLE_TRACE_NARRATOR_MODEL")
        or "anthropic:claude-haiku-4-5"
    ).strip()


def _truncate(s: str, n: int) -> str:
    if not s:
        return ""
    return s if len(s) <= n else (s[: n - 3] + "...")


def _sanitize_commit_message(msg: str) -> str:
    s = (msg or "").strip()
    if not s:
        return ""
    # Strip common code fence wrappers.
    if s.startswith("```"):
        s = s.strip("`").strip()
    lines = [ln.rstrip() for ln in s.splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        return ""
    # Enforce a sane subject line.
    subj = lines[0].strip()
    if len(subj) > 72:
        subj = subj[:72]
    rest = "\n".join(lines[1:]).rstrip()
    return subj if not rest else (subj + "\n" + rest)


def deterministic_agent_commit_message(
    *,
    project_slug: str,
    qa_passed: bool | None,
    diff_stat: str,
    name_status: str,
) -> str:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    qa = "unknown" if qa_passed is None else ("passed" if qa_passed else "failed")
    body = [
        f"Agent run ({project_slug}) {ts}",
        "",
        f"QA: {qa}",
        "",
        "Diffstat:",
        _truncate(diff_stat.strip(), 2000),
        "",
        "Changed files:",
        _truncate(name_status.strip(), 2000),
        "",
    ]
    return "\n".join(body).strip() + "\n"


def deterministic_bootstrap_commit_message(
    *,
    project_slug: str,
    template_id: str | None,
) -> str:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "Bootstrap sandbox template",
        "",
        f"Project: {project_slug}",
        f"Template: {template_id or '<unknown>'}",
        f"Time: {ts}",
        "",
        "Initial baseline commit created from the sandbox template state.",
        "",
    ]
    return "\n".join(lines).strip() + "\n"


def generate_agent_commit_message_llm(
    *,
    user_request: str,
    project_slug: str,
    qa_passed: bool | None,
    qa_last_output: str,
    diff_stat: str,
    name_status: str,
    tool_journal_summary: dict[str, Any] | None,
) -> str:
    """Best-effort LLM commit message generator.

    Must always return a usable commit message (falls back deterministically).
    """
    fallback = deterministic_agent_commit_message(
        project_slug=project_slug,
        qa_passed=qa_passed,
        diff_stat=diff_stat,
        name_status=name_status,
    )

    try:
        from langchain.chat_models import init_chat_model  # type: ignore
    except Exception:
        return fallback

    model_name = _commit_model()
    try:
        llm = init_chat_model(model_name)
    except Exception:
        return fallback

    qa = "unknown" if qa_passed is None else ("passed" if qa_passed else "failed")
    journal = tool_journal_summary or {}
    prompt = (
        "You are generating a git commit message for an automated code-editing agent.\n"
        "Output MUST be a valid git commit message:\n"
        "- First line: subject, <= 72 characters\n"
        "- Blank line\n"
        "- Body: explain WHY changes were made in plain language\n"
        "- Include a 'Changes:' section listing the key files/areas touched\n"
        "- Do NOT include raw file contents\n"
        "- Do NOT include secrets\n\n"
        f"Project: {project_slug}\n"
        f"User request: {_truncate(user_request.strip(), 1200)}\n"
        f"QA: {qa}\n"
        f"QA last output (truncated): {_truncate(qa_last_output.strip(), 1500)}\n\n"
        "Staged diffstat:\n"
        f"{_truncate(diff_stat.strip(), 2500)}\n\n"
        "Staged name-status:\n"
        f"{_truncate(name_status.strip(), 2500)}\n\n"
        "Tool journal summary (JSON-ish):\n"
        f"{_truncate(str(journal), 1500)}\n"
    )

    try:
        msg = llm.invoke(prompt)
        text = getattr(msg, "content", "") if msg is not None else ""
        if not isinstance(text, str):
            return fallback
        out = _sanitize_commit_message(text)
        return out + ("\n" if not out.endswith("\n") else "") if out else fallback
    except Exception:
        return fallback

