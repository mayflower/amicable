from __future__ import annotations

import asyncio
import inspect
import json
import os
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

HookHandler = Callable[[dict[str, Any]], dict[str, Any] | None | Awaitable[dict[str, Any] | None]]


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return int(default)
    try:
        return int(raw)
    except Exception:
        return int(default)


def hook_timeout_ms() -> int:
    return max(100, _env_int("AMICABLE_HOOK_TIMEOUT_MS", 1000))


def _hook_commands_from_env() -> dict[str, list[str]]:
    raw = (os.environ.get("AMICABLE_HOOK_COMMANDS_JSON") or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}

    out: dict[str, list[str]] = {}
    for event, commands in parsed.items():
        if not isinstance(event, str) or not event.strip():
            continue
        if isinstance(commands, str):
            cmd = commands.strip()
            if cmd:
                out[event] = [cmd]
            continue
        if isinstance(commands, list):
            cleaned = [c.strip() for c in commands if isinstance(c, str) and c.strip()]
            if cleaned:
                out[event] = cleaned
    return out


class AgentHookBus:
    """Best-effort hook bus with fail-open semantics.

    Hooks are optional. Failures/timeouts are reported in return metadata and do not
    interrupt the main agent workflow.
    """

    def __init__(self, *, timeout_ms: int | None = None) -> None:
        self._timeout_ms = int(timeout_ms or hook_timeout_ms())
        self._handlers: dict[str, list[HookHandler]] = defaultdict(list)
        self._shell_callouts = _hook_commands_from_env()

    def on(self, event: str, handler: HookHandler) -> None:
        e = (event or "").strip()
        if not e:
            return
        self._handlers[e].append(handler)

    async def _run_handler(self, event: str, idx: int, payload: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        label = f"py:{event}:{idx}"
        try:
            maybe = self._handlers[event][idx](payload)
            if inspect.isawaitable(maybe):
                data = await asyncio.wait_for(maybe, timeout=self._timeout_ms / 1000)
            else:
                data = maybe
            duration = int((time.monotonic() - started) * 1000)
            return {
                "hook": label,
                "status": "ok",
                "duration_ms": duration,
                "data": data if isinstance(data, dict) else None,
            }
        except TimeoutError:
            duration = int((time.monotonic() - started) * 1000)
            return {
                "hook": label,
                "status": "timeout",
                "duration_ms": duration,
            }
        except Exception as exc:
            duration = int((time.monotonic() - started) * 1000)
            return {
                "hook": label,
                "status": "error",
                "duration_ms": duration,
                "error": str(exc),
            }

    async def _run_shell_callout(
        self, event: str, idx: int, command: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        started = time.monotonic()
        label = f"sh:{event}:{idx}"
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdin_bytes = json.dumps(payload).encode("utf-8", errors="replace")
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(stdin_bytes),
                timeout=self._timeout_ms / 1000,
            )
            duration = int((time.monotonic() - started) * 1000)
            return {
                "hook": label,
                "status": "ok" if proc.returncode == 0 else "error",
                "duration_ms": duration,
                "exit_code": int(proc.returncode or 0),
                "stdout": stdout.decode("utf-8", errors="replace")[:2000],
                "stderr": stderr.decode("utf-8", errors="replace")[:2000],
            }
        except TimeoutError:
            duration = int((time.monotonic() - started) * 1000)
            return {
                "hook": label,
                "status": "timeout",
                "duration_ms": duration,
            }
        except Exception as exc:
            duration = int((time.monotonic() - started) * 1000)
            return {
                "hook": label,
                "status": "error",
                "duration_ms": duration,
                "error": str(exc),
            }

    async def emit(self, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        e = (event or "").strip()
        if not e:
            return {"event": e, "called": False, "results": []}

        results: list[dict[str, Any]] = []
        handlers = self._handlers.get(e, [])
        for idx in range(len(handlers)):
            results.append(await self._run_handler(e, idx, payload))

        for idx, cmd in enumerate(self._shell_callouts.get(e, [])):
            results.append(await self._run_shell_callout(e, idx, cmd, payload))

        return {
            "event": e,
            "called": bool(results),
            "results": results,
            "error_count": sum(1 for r in results if r.get("status") in ("error", "timeout")),
        }
