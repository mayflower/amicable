from __future__ import annotations

import base64
import os
import shlex
import subprocess
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel


APP_ROOT = Path("/app")

app = FastAPI(title="Amicable Sandbox Runtime", version="1.0.0")


class ExecRequest(BaseModel):
    command: str


class ExecResponse(BaseModel):
    stdout: str
    stderr: str
    exit_code: int


class WriteB64Request(BaseModel):
    path: str
    content_b64: str


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
    # Start the preview server in the background. If it exits, we just log.
    env = os.environ.copy()
    raw = (env.get("AMICABLE_PREVIEW_CMD") or "").strip()
    if raw:
        cmd = shlex.split(raw)
    else:
        cmd = ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]

    def _run() -> None:
        try:
            subprocess.Popen(cmd, cwd=str(APP_ROOT), env=env)
        except Exception as exc:
            print(f"Failed to start preview server: {exc}")

    threading.Thread(target=_run, daemon=True).start()


@app.on_event("startup")
async def _on_startup() -> None:
    _start_preview()


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.post("/exec", response_model=ExecResponse)
async def exec_cmd(req: ExecRequest) -> ExecResponse:
    try:
        args = shlex.split(req.command)
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            cwd=str(APP_ROOT),
        )
        return ExecResponse(stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode)
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

    out: list[str] = []
    for root, dirs, files in os.walk(base):
        # Skip node_modules for performance
        dirs[:] = [d for d in dirs if d != "node_modules" and not d.startswith(".")]
        for fn in files:
            if fn.startswith("."):
                continue
            full = Path(root) / fn
            rel = full.relative_to(APP_ROOT)
            out.append(str(rel))

    out.sort()
    return {"files": out}


@app.get("/download/{file_path:path}")
async def download(file_path: str):
    try:
        full = _safe_path(file_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not full.exists() or not full.is_file():
        raise HTTPException(status_code=404, detail="file not found")

    return Response(content=full.read_bytes(), media_type="application/octet-stream")


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

    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(payload)
    return {"ok": True, "path": str(req.path)}
