from __future__ import annotations

import asyncio
import base64
import contextlib
import os
import selectors
import shlex
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel


APP_ROOT = Path("/app")

app = FastAPI(title="Amicable Sandbox Runtime", version="1.0.0")


@dataclass
class _PreviewSupervisorState:
    running_pid: int | None = None
    restart_count: int = 0
    exhausted: bool = False
    last_exit_code: int | None = None
    last_exit_ts_ms: int | None = None
    last_error: str | None = None


_preview_state = _PreviewSupervisorState()
_preview_state_lock = threading.Lock()


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return int(default)
    try:
        return int(raw)
    except Exception:
        return int(default)


def _exec_timeout_s() -> int:
    return max(1, _env_int("SANDBOX_EXEC_TIMEOUT_S", 600))


def _exec_max_output_chars() -> int:
    # Bound stdout/stderr so a noisy command can't OOM the runtime.
    return max(10_000, _env_int("SANDBOX_EXEC_MAX_OUTPUT_CHARS", 200_000))


def _preview_max_restarts() -> int:
    return max(1, _env_int("AMICABLE_PREVIEW_MAX_RESTARTS", 100))


def _preview_state_update(**kwargs) -> None:
    with _preview_state_lock:
        for key, value in kwargs.items():
            setattr(_preview_state, key, value)


def _preview_state_snapshot() -> dict:
    with _preview_state_lock:
        running = _preview_state.running_pid is not None and not _preview_state.exhausted
        return {
            "running": running,
            "running_pid": _preview_state.running_pid,
            "restart_count": _preview_state.restart_count,
            "max_restarts": _preview_max_restarts(),
            "exhausted": _preview_state.exhausted,
            "last_exit_code": _preview_state.last_exit_code,
            "last_exit_ts_ms": _preview_state.last_exit_ts_ms,
            "last_error": _preview_state.last_error,
        }


def _decode_output(b: bytes) -> str:
    try:
        return b.decode("utf-8", errors="replace")
    except Exception:
        return b.decode(errors="replace")


def _kill_process_tree(proc: subprocess.Popen[bytes]) -> None:
    # `start_new_session=True` makes proc.pid the process group id on Linux.
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except Exception:
        with contextlib.suppress(Exception):
            proc.terminate()
    try:
        proc.wait(timeout=1.0)
        return
    except Exception:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except Exception:
        with contextlib.suppress(Exception):
            proc.kill()


def _run_command_limited(
    *, args: list[str], cwd: str, timeout_s: int, max_output_chars: int
) -> tuple[str, str, int]:
    # Run without shell; capture stdout/stderr with truncation and a hard timeout.
    max_bytes = max_output_chars * 4  # worst-case utf-8 expansion
    proc: subprocess.Popen[bytes] = subprocess.Popen(
        args,
        cwd=cwd,
        env=os.environ.copy(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    assert proc.stdout is not None
    assert proc.stderr is not None

    sel = selectors.DefaultSelector()
    sel.register(proc.stdout, selectors.EVENT_READ, data="stdout")
    sel.register(proc.stderr, selectors.EVENT_READ, data="stderr")

    out = bytearray()
    err = bytearray()
    out_trunc = False
    err_trunc = False

    deadline = time.monotonic() + float(timeout_s)
    while True:
        # Drain pipes until EOF and process exit.
        if proc.poll() is not None and not sel.get_map():
            break

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _kill_process_tree(proc)
            # Best-effort drain any remaining output quickly.
            with contextlib.suppress(Exception):
                while sel.get_map():
                    for key, _ in sel.select(timeout=0):
                        chunk = key.fileobj.read1(8192)  # type: ignore[attr-defined]
                        if not chunk:
                            sel.unregister(key.fileobj)
                            with contextlib.suppress(Exception):
                                key.fileobj.close()
                            continue
                        if key.data == "stdout":
                            if len(out) < max_bytes:
                                take = min(len(chunk), max_bytes - len(out))
                                out.extend(chunk[:take])
                                if take < len(chunk):
                                    out_trunc = True
                            else:
                                out_trunc = True
                        else:
                            if len(err) < max_bytes:
                                take = min(len(chunk), max_bytes - len(err))
                                err.extend(chunk[:take])
                                if take < len(chunk):
                                    err_trunc = True
                            else:
                                err_trunc = True
            stdout = _decode_output(bytes(out))
            stderr = _decode_output(bytes(err)) or f"Command timed out after {timeout_s}s"
            if out_trunc:
                stdout = stdout[:max_output_chars] + "\n<output truncated>"
            if err_trunc:
                stderr = stderr[:max_output_chars] + "\n<output truncated>"
            return stdout, stderr, 124

        for key, _ in sel.select(timeout=min(0.2, remaining)):
            stream = key.fileobj
            try:
                chunk = stream.read1(8192)  # type: ignore[attr-defined]
            except Exception:
                chunk = b""
            if not chunk:
                with contextlib.suppress(Exception):
                    sel.unregister(stream)
                with contextlib.suppress(Exception):
                    stream.close()
                continue

            if key.data == "stdout":
                if len(out) < max_bytes:
                    take = min(len(chunk), max_bytes - len(out))
                    out.extend(chunk[:take])
                    if take < len(chunk):
                        out_trunc = True
                else:
                    out_trunc = True
            else:
                if len(err) < max_bytes:
                    take = min(len(chunk), max_bytes - len(err))
                    err.extend(chunk[:take])
                    if take < len(chunk):
                        err_trunc = True
                else:
                    err_trunc = True

    rc = int(proc.returncode or 0)
    stdout = _decode_output(bytes(out))
    stderr = _decode_output(bytes(err))
    if out_trunc:
        stdout = stdout[:max_output_chars] + "\n<output truncated>"
    if err_trunc:
        stderr = stderr[:max_output_chars] + "\n<output truncated>"
    return stdout, stderr, rc


class ExecRequest(BaseModel):
    command: str


class ExecResponse(BaseModel):
    stdout: str
    stderr: str
    exit_code: int


class WriteB64Request(BaseModel):
    path: str
    content_b64: str


class DownloadManyRequest(BaseModel):
    paths: list[str]


@dataclass(frozen=True)
class _ManifestEntry:
    path: str
    kind: Literal["file", "dir", "symlink"]
    size: int | None
    mtime_ns: int
    mode: int
    link_target: str | None


def _safe_path(rel_path: str) -> Path:
    p = rel_path.strip().lstrip("/")
    if not p:
        raise ValueError("empty path")

    full = (APP_ROOT / p).resolve()
    # Prevent escape from /app.
    if APP_ROOT not in full.parents and full != APP_ROOT:
        raise ValueError("path escapes /app")
    return full


def _start_preview() -> None:
    # Start the preview server in the background with auto-respawn.
    env = os.environ.copy()
    raw = (env.get("AMICABLE_PREVIEW_CMD") or "").strip()
    if raw:
        cmd = shlex.split(raw)
    else:
        cmd = ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]

    max_restarts = _preview_max_restarts()

    def _run() -> None:
        restarts = 0
        log_path = (env.get("AMICABLE_PREVIEW_LOG_PATH") or "/tmp/amicable-preview.log").strip()
        pid_path = (env.get("AMICABLE_PREVIEW_PID_PATH") or "/tmp/amicable-preview.pid").strip()
        while restarts < max_restarts:
            logf = None
            try:
                try:
                    logf = open(log_path, "a", encoding="utf-8", errors="replace")
                except Exception:
                    logf = None
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(APP_ROOT),
                    env=env,
                    stdout=logf or subprocess.DEVNULL,
                    stderr=subprocess.STDOUT if logf else subprocess.DEVNULL,
                )
                _preview_state_update(
                    running_pid=proc.pid,
                    exhausted=False,
                    last_error=None,
                )
                try:
                    Path(pid_path).write_text(str(proc.pid), encoding="utf-8")
                except Exception:
                    pass
                rc = proc.wait()
                _preview_state_update(
                    running_pid=None,
                    last_exit_code=int(rc),
                    last_exit_ts_ms=int(time.time() * 1000),
                )
            except Exception as exc:
                print(f"Preview server error: {exc}")
                _preview_state_update(
                    running_pid=None,
                    last_error=str(exc),
                    last_exit_ts_ms=int(time.time() * 1000),
                )
            finally:
                try:
                    if logf is not None:
                        logf.close()
                except Exception:
                    pass
            restarts += 1
            _preview_state_update(restart_count=restarts)
            print(f"Preview server exited, restarting ({restarts}/{max_restarts}) in 3s...")
            time.sleep(3)
        _preview_state_update(running_pid=None, exhausted=True)
        print(f"Preview server exceeded {max_restarts} restarts, giving up.")

    threading.Thread(target=_run, daemon=True).start()


@app.on_event("startup")
async def _on_startup() -> None:
    _start_preview()


@app.get("/healthz")
async def healthz(response: Response) -> dict:
    preview = _preview_state_snapshot()
    healthy = not bool(preview.get("exhausted"))
    if not healthy:
        response.status_code = 503
    return {"status": "ok" if healthy else "degraded", "preview": preview}


@app.get("/readyz")
async def readyz(response: Response) -> dict:
    preview = _preview_state_snapshot()
    ready = bool(preview.get("running")) and not bool(preview.get("exhausted"))
    if not ready:
        response.status_code = 503
    return {"status": "ready" if ready else "not_ready", "preview": preview}


@app.post("/exec", response_model=ExecResponse)
async def exec_cmd(req: ExecRequest) -> ExecResponse:
    try:
        args = shlex.split(req.command)
        stdout, stderr, code = await asyncio.to_thread(
            _run_command_limited,
            args=args,
            cwd=str(APP_ROOT),
            timeout_s=_exec_timeout_s(),
            max_output_chars=_exec_max_output_chars(),
        )
        return ExecResponse(stdout=stdout, stderr=stderr, exit_code=code)
    except ValueError as exc:
        return ExecResponse(stdout="", stderr=f"Invalid command: {exc}", exit_code=2)
    except Exception as exc:
        return ExecResponse(stdout="", stderr=f"Failed to execute command: {exc}", exit_code=1)


# Compatibility alias for DeepAgents / agentic-sandbox clients.
@app.post("/execute", response_model=ExecResponse)
async def execute_cmd(req: ExecRequest) -> ExecResponse:
    return await exec_cmd(req)


@app.get("/list")
async def list_files(dir: str = "src") -> dict:
    try:
        base = _safe_path(dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not base.exists() or not base.is_dir():
        raise HTTPException(status_code=404, detail="dir not found")

    def _list_sync() -> list[str]:
        out: list[str] = []
        for root, dirs, files in os.walk(base):
            # Skip node_modules for performance
            dirs[:] = [
                d for d in dirs if d != "node_modules" and not d.startswith(".")
            ]
            for fn in files:
                if fn.startswith("."):
                    continue
                full = Path(root) / fn
                rel = full.relative_to(APP_ROOT)
                out.append(str(rel))

        out.sort()
        return out

    return {"files": await asyncio.to_thread(_list_sync)}


@app.get("/download/{file_path:path}")
async def download(file_path: str):
    try:
        full = _safe_path(file_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not full.exists() or not full.is_file():
        raise HTTPException(status_code=404, detail="file not found")

    payload = await asyncio.to_thread(full.read_bytes)
    return Response(content=payload, media_type="application/octet-stream")


@app.post("/download_many")
async def download_many(req: DownloadManyRequest) -> dict:
    def _download_many_sync() -> dict:
        files: list[dict] = []
        paths = req.paths if isinstance(req.paths, list) else []
        for raw in paths:
            p = str(raw or "")
            try:
                full = _safe_path(p)
            except ValueError:
                files.append({"path": p, "content_b64": None, "error": "invalid_path"})
                continue

            if not full.exists():
                files.append({"path": p, "content_b64": None, "error": "file_not_found"})
                continue
            if full.is_dir():
                files.append({"path": p, "content_b64": None, "error": "is_directory"})
                continue
            try:
                payload = full.read_bytes()
            except PermissionError:
                files.append({"path": p, "content_b64": None, "error": "permission_denied"})
                continue

            files.append(
                {
                    "path": p,
                    "content_b64": base64.b64encode(payload).decode("ascii"),
                    "error": None,
                }
            )

        return {"files": files}

    return await asyncio.to_thread(_download_many_sync)


def _walk_manifest(base: Path, *, include_hidden: bool) -> list[_ManifestEntry]:
    out: list[_ManifestEntry] = []

    def _is_hidden(rel_parts: tuple[str, ...]) -> bool:
        return any(part.startswith(".") for part in rel_parts if part)

    # Safety/perf: never export .git, and avoid traversing node_modules which can be enormous.
    prune_dirs = {".git", "node_modules"}

    for root, dirs, files in os.walk(base, followlinks=False):
        try:
            root_path = Path(root)
            rel_root = root_path.relative_to(APP_ROOT)
        except Exception:
            continue

        # Prune selected dirs early.
        dirs[:] = [d for d in dirs if d not in prune_dirs]

        if not include_hidden:
            # If any component of the directory is hidden, skip its contents.
            if _is_hidden(rel_root.parts):
                dirs[:] = []
                continue
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            files = [f for f in files if not f.startswith(".")]

        for d in dirs:
            full = root_path / d
            rel = full.relative_to(APP_ROOT)
            try:
                st = full.lstat()
            except Exception:
                continue
            out.append(
                _ManifestEntry(
                    path=str(rel),
                    kind="dir",
                    size=None,
                    mtime_ns=int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))),
                    mode=int(st.st_mode) & 0o777,
                    link_target=None,
                )
            )

        for f in files:
            full = root_path / f
            rel = full.relative_to(APP_ROOT)
            try:
                st = full.lstat()
            except Exception:
                continue

            if full.is_symlink():
                try:
                    target = os.readlink(full)
                except Exception:
                    target = ""
                out.append(
                    _ManifestEntry(
                        path=str(rel),
                        kind="symlink",
                        size=None,
                        mtime_ns=int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))),
                        mode=int(st.st_mode) & 0o777,
                        link_target=target,
                    )
                )
                continue

            if full.is_file():
                out.append(
                    _ManifestEntry(
                        path=str(rel),
                        kind="file",
                        size=int(st.st_size),
                        mtime_ns=int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))),
                        mode=int(st.st_mode) & 0o777,
                        link_target=None,
                    )
                )

    out.sort(key=lambda e: e.path)
    return out


@app.get("/manifest")
async def manifest(dir: str = ".", include_hidden: int = 1) -> dict:
    try:
        base = _safe_path(dir or ".")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not base.exists() or not base.is_dir():
        raise HTTPException(status_code=404, detail="dir not found")

    entries = await asyncio.to_thread(
        _walk_manifest, base, include_hidden=bool(int(include_hidden or 0))
    )
    payload = [
        {
            "path": e.path,
            "kind": e.kind,
            "size": e.size,
            "mtime_ns": e.mtime_ns,
            "mode": e.mode,
            "link_target": e.link_target,
        }
        for e in entries
    ]
    return {"entries": payload}


@app.post("/write_b64")
async def write_b64(req: WriteB64Request) -> dict:
    try:
        full = _safe_path(req.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        payload = base64.b64decode(req.content_b64.encode("ascii"), validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid base64")

    def _write_sync() -> None:
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(payload)

    await asyncio.to_thread(_write_sync)
    return {"ok": True, "path": str(req.path)}
