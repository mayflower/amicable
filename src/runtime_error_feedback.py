from __future__ import annotations

import json
import re
from typing import Any


def _truncate(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def build_runtime_error_feedback_prompt(
    *, err: dict[str, Any], preview_logs: str = ""
) -> str:
    kind = str(err.get("kind") or "window_error")
    message = _truncate(str(err.get("message") or ""), max_chars=2000)
    url = _truncate(str(err.get("url") or ""), max_chars=2000)
    stack = _truncate(str(err.get("stack") or ""), max_chars=8000)
    source = str(err.get("source") or "")
    level = str(err.get("level") or "")

    args_preview_raw = err.get("args_preview")
    args_preview = (
        _truncate(str(args_preview_raw), max_chars=4000)
        if isinstance(args_preview_raw, str)
        else ""
    )

    extra = err.get("extra")
    if not args_preview and isinstance(extra, dict):
        extra_args = extra.get("args_preview")
        if isinstance(extra_args, str):
            args_preview = _truncate(extra_args, max_chars=4000)

    if preview_logs:
        preview_logs = preview_logs[-12000:]

    prompt = (
        "Runtime error detected in the running preview. Please fix the cause so the preview runs without errors.\n\n"
        f"Kind: {kind}\n"
        f"Message: {message}\n"
        + (f"URL: {url}\n" if url else "")
        + (f"Stack:\n{stack}\n" if stack else "")
        + (f"Source: {source}\n" if source else "")
        + (f"Level: {level}\n" if level else "")
    )

    if args_preview:
        prompt += f"\nConsole args preview:\n{args_preview}\n"

    if extra is not None:
        try:
            payload = json.dumps(extra, indent=2, sort_keys=True, default=str)
        except Exception:
            payload = str(extra)
        prompt += f"\nExtra:\n{payload}\n"

    if preview_logs:
        prompt += f"\nPreview logs (tail):\n{preview_logs}\n"

    hint = ""
    if kind == "graphql_error":
        m = re.search(
            r"field\s+'([^']+)'\s+not\s+found\s+in\s+type\s*:\s*'query_root'",
            message,
            flags=re.IGNORECASE,
        )
        if m:
            field = m.group(1)
            hint += (
                "\n\nHint: This usually means the Hasura table/field is missing or not tracked. "
                f"Consider creating/tracking the relevant table for `{field}` using `db_create_table` "
                "(safe) or updating the query to match the existing schema."
            )
    if kind == "console_error":
        hint += (
            "\n\nHint: This came from `console.error` in browser runtime. "
            "Fix the underlying code path instead of suppressing the log."
        )
    if kind == "runtime_bridge_missing":
        hint += (
            "\n\nHint: Runtime telemetry bridge is missing. Ensure `/amicable-runtime.js` is present "
            "and included in the app entrypoint/head so runtime errors can be reported."
        )

    prompt += hint
    return prompt
