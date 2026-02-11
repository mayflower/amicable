from __future__ import annotations

import os
from typing import Any


def _review_model() -> str:
    return (
        os.environ.get("AMICABLE_SCHEMA_REVIEW_MODEL")
        or os.environ.get("AMICABLE_TRACE_NARRATOR_MODEL")
        or "anthropic:claude-haiku-4-5"
    ).strip()


def _fallback_review(*, diff: dict[str, Any]) -> dict[str, Any]:
    ops = list(diff.get("operations") or [])
    destructive = bool(diff.get("destructive"))
    destructive_details = list(diff.get("destructive_details") or [])

    counts: dict[str, int] = {}
    for op in ops:
        t = str(op.get("type") or "unknown")
        counts[t] = counts.get(t, 0) + 1

    lines: list[str] = []
    if not ops:
        lines.append("No schema changes detected.")
    else:
        lines.append("Planned database changes:")
        for k in sorted(counts.keys()):
            lines.append(f"- {k.replace('_', ' ')}: {counts[k]}")

    if destructive:
        lines.append("")
        lines.append("Destructive changes require confirmation:")
        for item in destructive_details:
            lines.append(f"- {item}")

    lines.append("")
    lines.append(
        "After apply, Amicable will sync Hasura metadata (tracked tables, permissions, relationships)."
    )

    return {
        "summary": "\n".join(lines).strip(),
        "destructive": destructive,
        "destructive_details": destructive_details,
        "warnings": list(diff.get("warnings") or []),
    }


def generate_schema_review(*, current: dict[str, Any], diff: dict[str, Any]) -> dict[str, Any]:
    fallback = _fallback_review(diff=diff)

    try:
        from langchain.chat_models import init_chat_model
    except Exception:
        return fallback

    try:
        llm = init_chat_model(_review_model())
    except Exception:
        return fallback

    ops = list(diff.get("operations") or [])
    destructive = bool(diff.get("destructive"))
    destructive_details = list(diff.get("destructive_details") or [])
    current_tables = [
        str(t.get("label") or t.get("name") or "")
        for t in list(current.get("tables") or [])
        if isinstance(t, dict)
    ]

    prompt = (
        "You are reviewing a planned database schema change for non-programmer users.\n"
        "Write concise plain language with: summary, potential impact, and what to verify in app behavior.\n"
        "Keep under 180 words. No SQL.\n\n"
        f"Current tables: {', '.join(current_tables) if current_tables else '<none>'}\n"
        f"Operation count: {len(ops)}\n"
        f"Destructive: {'yes' if destructive else 'no'}\n"
        f"Destructive details: {destructive_details}\n"
        f"Operations: {ops}\n"
    )

    try:
        msg = llm.invoke(prompt)
        text = getattr(msg, "content", "") if msg is not None else ""
        if not isinstance(text, str) or not text.strip():
            return fallback
        out = dict(fallback)
        out["summary"] = text.strip()
        return out
    except Exception:
        return fallback
