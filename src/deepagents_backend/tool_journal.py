from __future__ import annotations

import os
import re
import threading
import time
from collections import Counter, defaultdict
from typing import Any

_LOCK = threading.Lock()
_EVENTS_BY_THREAD: dict[str, list[dict[str, Any]]] = defaultdict(list)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _redact(text: str) -> str:
    s = text or ""
    # Redact values of common secret env vars if they accidentally appear in commands.
    for key in (
        "GITLAB_TOKEN",
        "HASURA_GRAPHQL_ADMIN_SECRET",
        "DATABASE_URL",
        "LANGGRAPH_DATABASE_URL",
        "AMICABLE_LANGGRAPH_DATABASE_URL",
        "AGENT_AUTH_TOKEN",
    ):
        val = (os.environ.get(key) or "").strip()
        if val and val in s:
            s = s.replace(val, f"<redacted:{key.lower()}>")

    # Basic "token=..." / "password=..." style redaction.
    s = re.sub(r"(?i)(token|password|secret)\s*=\s*[^\\s]+", r"\\1=<redacted>", s)
    return s


def clear(thread_id: str) -> None:
    tid = (thread_id or "").strip() or "default-thread"
    with _LOCK:
        _EVENTS_BY_THREAD.pop(tid, None)


def append(thread_id: str, operation: str, target: str, metadata: dict[str, Any] | None = None) -> None:
    tid = (thread_id or "").strip() or "default-thread"
    op = (operation or "").strip()
    tgt = _redact((target or "").strip())
    meta = metadata if isinstance(metadata, dict) else {}
    evt = {"ts_ms": _now_ms(), "op": op, "target": tgt, "meta": meta}
    with _LOCK:
        _EVENTS_BY_THREAD[tid].append(evt)


def drain(thread_id: str) -> list[dict[str, Any]]:
    tid = (thread_id or "").strip() or "default-thread"
    with _LOCK:
        evts = _EVENTS_BY_THREAD.pop(tid, [])
    return list(evts)


def summarize(events: list[dict[str, Any]], *, max_paths: int = 40, max_cmds: int = 30) -> dict[str, Any]:
    ops = Counter()
    paths = Counter()
    cmds = Counter()

    for e in events or []:
        if not isinstance(e, dict):
            continue
        op = str(e.get("op") or "")
        tgt = str(e.get("target") or "")
        ops[op] += 1

        if op in ("write", "edit", "upload") and tgt:
            paths[tgt] += 1
        if op == "execute" and tgt:
            cmds[tgt] += 1

    top_paths = [p for p, _n in paths.most_common(max_paths)]
    top_cmds = [c for c, _n in cmds.most_common(max_cmds)]

    return {
        "counts": dict(ops),
        "modified_paths": top_paths,
        "commands": top_cmds,
        "event_count": int(sum(ops.values())),
    }

