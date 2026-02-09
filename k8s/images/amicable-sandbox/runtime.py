from __future__ import annotations

import base64
import os
import shlex
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

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


@app.post("/download_many")
async def download_many(req: DownloadManyRequest) -> dict:
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

    entries = _walk_manifest(base, include_hidden=bool(int(include_hidden or 0)))
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

    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(payload)
    return {"ok": True, "path": str(req.path)}
