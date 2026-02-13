from __future__ import annotations

import os
import re
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


def _normalize_project_about(prompt: str | None, *, max_chars: int = 220) -> str:
    raw = re.sub(r"\s+", " ", str(prompt or "")).strip()
    if not raw:
        return "No project description was provided at creation time."
    if len(raw) > max_chars:
        return raw[: max_chars - 3].rstrip() + "..."
    return raw


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
    project_name: str | None,
    project_prompt: str | None,
) -> str:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    about = _normalize_project_about(project_prompt)
    lines = [
        "Bootstrap sandbox template",
        "",
        f"Project Name: {project_name or project_slug}",
        f"Project: {project_slug}",
        f"Template: {template_id or '<unknown>'}",
        f"About: {about}",
        f"Time: {ts}",
        "",
        "Initial baseline commit created from the sandbox template state.",
        "",
    ]
    return "\n".join(lines).strip() + "\n"


def generate_agent_commit_message_llm(
    *,
    user_request: str,
    agent_summary: str,
    project_slug: str,
    qa_passed: bool | None,
    qa_last_output: str,
    diff_stat: str,
    name_status: str,
    tool_journal_summary: dict[str, Any] | None,
) -> str:
    """LLM git commit message generator.

    Commit messages are project history. If LLM generation fails, we fail the git
    sync rather than silently producing low-signal commits.
    """

    try:
        from langchain.chat_models import init_chat_model  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError("langchain init_chat_model unavailable") from e

    model_name = _commit_model()
    try:
        llm = init_chat_model(model_name)
    except Exception as e:  # pragma: no cover
        raise RuntimeError(f"failed to init commit-message model: {model_name}") from e

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
        "- Do NOT include timestamps\n"
        "- Prefer imperative mood in the subject (e.g. 'Add ...', 'Fix ...')\n\n"
        f"Project: {project_slug}\n"
        f"User request: {_truncate(user_request.strip(), 1200)}\n"
        f"Agent summary (truncated): {_truncate(agent_summary.strip(), 1500)}\n"
        f"QA: {qa}\n"
        f"QA last output (truncated): {_truncate(qa_last_output.strip(), 1500)}\n\n"
        "Staged name-status:\n"
        f"{_truncate(name_status.strip(), 2500)}\n\n"
        "Staged diffstat:\n"
        f"{_truncate(diff_stat.strip(), 2500)}\n\n"
        "Tool journal summary (JSON-ish):\n"
        f"{_truncate(str(journal), 1500)}\n"
    )

    try:
        msg = llm.invoke(prompt)
        text = getattr(msg, "content", "") if msg is not None else ""
        if not isinstance(text, str):
            raise RuntimeError("commit-message model returned non-text content")
        out = _sanitize_commit_message(text)
        if not out:
            raise RuntimeError("commit-message model returned empty message")
        return out + ("\n" if not out.endswith("\n") else "")
    except Exception as e:  # pragma: no cover
        raise RuntimeError("commit-message model invocation failed") from e


def _parse_name_status_paths(name_status: str) -> list[str]:
    paths: list[str] = []
    for raw in (name_status or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split("\t")
        if not parts:
            continue
        status = parts[0].strip().upper()
        if status.startswith(("R", "C")) and len(parts) >= 3:
            # For rename/copy, include source and destination.
            paths.extend([parts[1].strip(), parts[2].strip()])
            continue
        if len(parts) >= 2:
            paths.append(parts[-1].strip())
    return [p.lstrip("./") for p in paths if p.strip()]


def _is_doc_path(path: str) -> bool:
    p = (path or "").strip().lstrip("/")
    if not p:
        return False
    pl = p.lower()
    if pl.startswith("docs/"):
        return True
    return bool(pl.endswith(".md") or pl.endswith(".mdx"))


def _satisfies_readme_requirement(path: str) -> bool:
    p = (path or "").strip().lstrip("/").lower()
    return p in ("readme.md", "docs/index.md")


def evaluate_agent_readme_policy(name_status: str) -> list[str]:
    """Return policy warnings for agent commits based on staged name-status."""
    paths = _parse_name_status_paths(name_status)
    if not paths:
        return []

    has_non_doc = any(not _is_doc_path(p) for p in paths)
    has_readme_update = any(_satisfies_readme_requirement(p) for p in paths)
    if not has_non_doc or has_readme_update:
        return []

    return [
        "README policy: non-doc files changed without updating README.md or docs/index.md."
    ]


def append_commit_warnings(message: str, warnings: list[str]) -> str:
    msg = (message or "").rstrip()
    if not warnings:
        return msg + "\n"
    block = "\n".join(f"- {w}" for w in warnings)
    return msg + "\n\nREADME Policy Warnings:\n" + block + "\n"
