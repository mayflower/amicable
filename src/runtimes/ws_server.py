from __future__ import annotations

import json
import os
import re
import secrets
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response

try:
    # Optional dependency in some minimal builds; only required for Google OAuth mode.
    from authlib.integrations.starlette_client import OAuth, OAuthError  # type: ignore
except Exception:  # pragma: no cover
    OAuth = None  # type: ignore[assignment,misc]
    OAuthError = Exception  # type: ignore[assignment]

try:
    # Optional dependency in some minimal builds; only required for Google OAuth mode.
    from starlette.middleware.sessions import SessionMiddleware  # type: ignore
except Exception:  # pragma: no cover
    SessionMiddleware = None  # type: ignore[assignment,misc]

from src.agent_core import Agent, Message, MessageType

# Load local env after imports to keep linting (E402) happy.
load_dotenv()

app = FastAPI()
_agent: Agent | None = None


_naming_llm: Any = None


async def _generate_project_name(prompt: str) -> str:
    """Use a small model to derive a short project name from the user prompt."""
    global _naming_llm
    if _naming_llm is None:
        try:
            from langchain.chat_models import init_chat_model

            _naming_llm = init_chat_model("anthropic:claude-haiku-4-5")
        except Exception:
            _naming_llm = False
    if _naming_llm is False:
        return ""
    try:
        msg = await _naming_llm.ainvoke(
            "Generate a short project name (2-4 words, no quotes) for this prompt. "
            "Return ONLY the name, nothing else.\n\n"
            f"{prompt[:500]}"
        )
        text = (getattr(msg, "content", "") or "").strip().strip("\"'")
        return text[:80] if text else ""
    except Exception:
        return ""


def _hasura_enabled() -> bool:
    return bool(
        (os.environ.get("HASURA_BASE_URL") or "").strip()
        and (os.environ.get("HASURA_GRAPHQL_ADMIN_SECRET") or "").strip()
    )


def _get_owner_from_request(request: Request) -> tuple[str, str]:
    """Return (sub, email) for project ownership checks."""
    mode = _auth_mode()
    if mode == "google":
        user = (request.session or {}).get("user")  # type: ignore[attr-defined]
        if not isinstance(user, dict):
            raise PermissionError("not authenticated")
        sub = str(user.get("sub") or "").strip()
        email = str(user.get("email") or "").strip()
        if not sub or not email:
            raise PermissionError("not authenticated")
        return sub, email

    # Dev/back-compat: treat all as one owner when not using google auth.
    return ("local", "local@example.com")


def _get_owner_from_ws(ws: WebSocket) -> tuple[str, str]:
    mode = _auth_mode()
    if mode == "google":
        user = getattr(ws, "session", {}).get("user")  # type: ignore[attr-defined]
        if not isinstance(user, dict):
            raise PermissionError("not authenticated")
        sub = str(user.get("sub") or "").strip()
        email = str(user.get("email") or "").strip()
        if not sub or not email:
            raise PermissionError("not authenticated")
        return sub, email
    return ("local", "local@example.com")


def _project_dto(p: Any) -> dict[str, Any]:
    return {
        "project_id": getattr(p, "project_id", None),
        "name": getattr(p, "name", None),
        "slug": getattr(p, "slug", None),
        "template_id": getattr(p, "template_id", None),
        "gitlab_project_id": getattr(p, "gitlab_project_id", None),
        "gitlab_path": getattr(p, "gitlab_path", None),
        "gitlab_web_url": getattr(p, "gitlab_web_url", None),
    }


def _csv_env(name: str) -> list[str]:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _auth_mode() -> str:
    # Modes:
    # - none: no auth enforced
    # - token: legacy ?auth_token=... (AGENT_AUTH_TOKEN)
    # - google: Google OAuth login + session cookie
    mode = (os.environ.get("AUTH_MODE") or "").strip().lower()
    if mode:
        return mode
    if os.environ.get("AGENT_AUTH_TOKEN"):
        return "token"
    # If Google is configured, default to enforcing it.
    if os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"):
        return "google"
    return "none"


def _is_allowed_redirect(target: str, *, request: Request) -> bool:
    """Prevent open redirects.

    Allow:
    - relative paths ("/foo")
    - absolute URLs whose origin is in AUTH_REDIRECT_ALLOW_ORIGINS
    - if allowlist is empty, only allow same-origin redirects
    """
    if not target:
        return False
    if target.startswith("/"):
        return True

    try:
        parsed = urlparse(target)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False

    allow_origins = _csv_env("AUTH_REDIRECT_ALLOW_ORIGINS")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if allow_origins:
        return origin in allow_origins

    req_origin = str(request.base_url).rstrip("/")
    return origin == req_origin


def _google_oauth() -> OAuth | None:
    if OAuth is None:
        return None
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None

    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    return oauth


# Middleware must be registered before the app starts serving requests.
_cors_origins = _csv_env("CORS_ALLOW_ORIGINS")
if _cors_origins:
    preview_base = (os.environ.get("PREVIEW_BASE_DOMAIN") or "").strip().lstrip(".")
    preview_origin_re = None
    if preview_base:
        # Allow preview iframes/apps to call the agent (required for /db proxy).
        preview_origin_re = rf"^https://[a-z0-9-]+\.{re.escape(preview_base)}$"
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_origin_regex=preview_origin_re,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

if _auth_mode() == "google":
    if SessionMiddleware is None:
        raise RuntimeError(
            "Google auth requires Starlette SessionMiddleware (and itsdangerous). "
            "Install it or disable google auth."
        )
    secret_key = os.environ.get("SESSION_SECRET")
    if not secret_key:
        # Local/dev fallback; for production set SESSION_SECRET to a stable value.
        secret_key = secrets.token_urlsafe(32)
        os.environ["SESSION_SECRET"] = secret_key

    cookie_name = os.environ.get("SESSION_COOKIE_NAME") or "amicable_session"
    same_site = (os.environ.get("SESSION_COOKIE_SAMESITE") or "lax").lower()
    https_only = (os.environ.get("SESSION_COOKIE_SECURE") or "").lower() in (
        "1",
        "true",
        "yes",
    )
    max_age = int(os.environ.get("SESSION_MAX_AGE_SECONDS") or str(60 * 60 * 24 * 7))

    app.add_middleware(
        SessionMiddleware,
        secret_key=secret_key,
        session_cookie=cookie_name,
        same_site=same_site,
        https_only=https_only,
        max_age=max_age,
    )


@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/projects")
async def api_list_projects(request: Request) -> JSONResponse:
    if not _hasura_enabled():
        return JSONResponse({"error": "hasura_not_configured"}, status_code=503)
    try:
        sub, email = _get_owner_from_request(request)
    except PermissionError:
        return JSONResponse({"error": "not_authenticated"}, status_code=401)

    from src.db.provisioning import hasura_client_from_env
    from src.projects.store import ProjectOwner, list_projects

    client = hasura_client_from_env()
    owner = ProjectOwner(sub=sub, email=email)
    items = list_projects(client, owner=owner)
    return JSONResponse(
        {
            "projects": [
                {
                    "project_id": p.project_id,
                    "name": p.name,
                    "slug": p.slug,
                    "template_id": p.template_id,
                    "created_at": p.created_at,
                    "updated_at": p.updated_at,
                }
                for p in items
            ]
        },
        status_code=200,
    )


@app.post("/api/projects")
async def api_create_project(request: Request) -> JSONResponse:
    if not _hasura_enabled():
        return JSONResponse({"error": "hasura_not_configured"}, status_code=503)
    try:
        sub, email = _get_owner_from_request(request)
    except PermissionError:
        return JSONResponse({"error": "not_authenticated"}, status_code=401)

    body: Any
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    name = str(body.get("name") or "").strip()
    prompt = str(body.get("prompt") or "").strip()
    template_id = str(body.get("template_id") or "").strip()
    from src.templates.registry import default_template_id, parse_template_id

    parsed_template = parse_template_id(template_id) if template_id else None
    if template_id and parsed_template is None:
        return JSONResponse({"error": "invalid_template_id"}, status_code=400)
    effective_template_id = parsed_template or default_template_id()

    if not name and prompt:
        name = await _generate_project_name(prompt)
    if not name:
        name = "Untitled"

    from src.db.provisioning import hasura_client_from_env
    from src.gitlab.integration import ensure_gitlab_repo_for_project
    from src.projects.store import ProjectOwner, create_project

    client = hasura_client_from_env()
    owner = ProjectOwner(sub=sub, email=email)
    p = create_project(client, owner=owner, name=name, template_id=effective_template_id)

    # Best-effort GitLab repo creation; may adjust slug on collision.
    try:
        p, _git = ensure_gitlab_repo_for_project(client, owner=owner, project=p)
    except Exception:
        # Never block project creation on git integration.
        p = p

    return JSONResponse(
        {
            "project_id": p.project_id,
            "name": p.name,
            "slug": p.slug,
            "prompt": prompt,
            "template_id": p.template_id,
        },
        status_code=200,
    )


@app.get("/api/projects/by-slug/{slug}")
async def api_get_project_by_slug(slug: str, request: Request) -> JSONResponse:
    if not _hasura_enabled():
        return JSONResponse({"error": "hasura_not_configured"}, status_code=503)
    try:
        sub, email = _get_owner_from_request(request)
    except PermissionError:
        return JSONResponse({"error": "not_authenticated"}, status_code=401)

    slug = (slug or "").strip()
    if not slug:
        return JSONResponse({"error": "invalid_slug"}, status_code=400)

    from src.db.provisioning import hasura_client_from_env
    from src.projects.store import ProjectOwner, get_project_by_slug

    client = hasura_client_from_env()
    owner = ProjectOwner(sub=sub, email=email)
    p = get_project_by_slug(client, owner=owner, slug=slug)
    if not p:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return JSONResponse(
        {
            "project_id": p.project_id,
            "name": p.name,
            "slug": p.slug,
            "template_id": p.template_id,
        },
        status_code=200,
    )


@app.get("/api/projects/{project_id}")
async def api_get_project_by_id(project_id: str, request: Request) -> JSONResponse:
    if not _hasura_enabled():
        return JSONResponse({"error": "hasura_not_configured"}, status_code=503)
    try:
        sub, email = _get_owner_from_request(request)
    except PermissionError:
        return JSONResponse({"error": "not_authenticated"}, status_code=401)

    project_id = (project_id or "").strip()
    if not project_id:
        return JSONResponse({"error": "invalid_project_id"}, status_code=400)

    from src.db.provisioning import hasura_client_from_env
    from src.projects.store import ProjectOwner, get_project_by_id

    client = hasura_client_from_env()
    owner = ProjectOwner(sub=sub, email=email)
    p = get_project_by_id(client, owner=owner, project_id=project_id)
    if not p:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return JSONResponse(
        {
            "project_id": p.project_id,
            "name": p.name,
            "slug": p.slug,
            "template_id": p.template_id,
        },
        status_code=200,
    )


@app.patch("/api/projects/{project_id}")
async def api_rename_project(project_id: str, request: Request) -> JSONResponse:
    if not _hasura_enabled():
        return JSONResponse({"error": "hasura_not_configured"}, status_code=503)
    try:
        sub, email = _get_owner_from_request(request)
    except PermissionError:
        return JSONResponse({"error": "not_authenticated"}, status_code=401)

    body: Any
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    name = str(body.get("name") or "").strip()
    if not name:
        return JSONResponse({"error": "missing_name"}, status_code=400)

    from src.db.provisioning import hasura_client_from_env
    from src.gitlab.integration import rename_gitlab_repo_to_match_project_slug
    from src.projects.store import ProjectOwner, rename_project

    client = hasura_client_from_env()
    owner = ProjectOwner(sub=sub, email=email)
    try:
        p = rename_project(client, owner=owner, project_id=project_id, new_name=name)
    except PermissionError:
        return JSONResponse({"error": "not_found"}, status_code=404)

    # Best-effort GitLab repo rename/move to match slug.
    try:
        p, _git = rename_gitlab_repo_to_match_project_slug(
            client, owner=owner, project=p, new_name=name
        )
    except Exception:
        # Never block rename on git integration.
        p = p
    return JSONResponse(
        {"project_id": p.project_id, "name": p.name, "slug": p.slug}, status_code=200
    )


@app.delete("/api/projects/{project_id}")
async def api_delete_project(project_id: str, request: Request) -> JSONResponse:
    if not _hasura_enabled():
        return JSONResponse({"error": "hasura_not_configured"}, status_code=503)
    try:
        sub, email = _get_owner_from_request(request)
    except PermissionError:
        return JSONResponse({"error": "not_authenticated"}, status_code=401)

    from fastapi import BackgroundTasks

    from src.db.cleanup import cleanup_app_db
    from src.db.provisioning import hasura_client_from_env
    from src.deepagents_backend.session_sandbox_manager import SessionSandboxManager
    from src.projects.store import (
        ProjectOwner,
        get_project_by_id,
        hard_delete_project_row,
        mark_project_deleted,
    )

    client = hasura_client_from_env()
    owner = ProjectOwner(sub=sub, email=email)
    p = get_project_by_id(client, owner=owner, project_id=project_id)
    if not p:
        return JSONResponse({"error": "not_found"}, status_code=404)

    # Mark deleted immediately (so it disappears from the list), then cleanup async.
    mark_project_deleted(client, owner=owner, project_id=project_id)

    bg = BackgroundTasks()

    def _cleanup() -> None:
        import contextlib

        # Best-effort sandbox delete.
        with contextlib.suppress(Exception):
            SessionSandboxManager().delete_session(project_id)
        # Best-effort DB cleanup.
        with contextlib.suppress(Exception):
            cleanup_app_db(client, app_id=project_id)
        # Finally remove row.
        with contextlib.suppress(Exception):
            hard_delete_project_row(client, owner=owner, project_id=project_id)

    bg.add_task(_cleanup)
    return JSONResponse({"status": "deleting"}, status_code=202, background=bg)


def _ensure_project_access(request: Request, *, project_id: str) -> None:
    """Raise PermissionError if request is not allowed to access project_id."""
    if _hasura_enabled():
        sub, email = _get_owner_from_request(request)
        from src.db.provisioning import hasura_client_from_env
        from src.projects.store import ProjectOwner, ensure_project_for_id

        client = hasura_client_from_env()
        owner = ProjectOwner(sub=sub, email=email)
        ensure_project_for_id(client, owner=owner, project_id=str(project_id))
        return

    # Without Hasura configured, we can't verify ownership; allow for dev.
    _get_owner_from_request(request)


def _get_agent() -> Agent:
    global _agent
    if _agent is None:
        _agent = Agent()
    return _agent


@app.get("/api/sandbox/{project_id}/ls")
async def api_sandbox_ls(project_id: str, request: Request, path: str = "/"):
    try:
        _ensure_project_access(request, project_id=project_id)
    except PermissionError:
        return JSONResponse({"error": "not_authenticated"}, status_code=401)

    agent = _get_agent()
    await agent.init(session_id=project_id)

    from src.sandbox_files.policy import normalize_public_path
    from src.sandbox_files.sandbox_fs import SandboxFs

    p = normalize_public_path(path)

    assert agent._session_manager is not None
    backend = agent._session_manager.get_backend(project_id)
    fs = SandboxFs(backend)
    entries = fs.ls(p)
    return JSONResponse({"path": p, "entries": entries}, status_code=200)


@app.get("/api/sandbox/{project_id}/read")
async def api_sandbox_read(project_id: str, path: str, request: Request):
    try:
        _ensure_project_access(request, project_id=project_id)
    except PermissionError:
        return JSONResponse({"error": "not_authenticated"}, status_code=401)

    agent = _get_agent()
    await agent.init(session_id=project_id)

    from src.sandbox_files.policy import normalize_public_path
    from src.sandbox_files.sandbox_fs import SandboxFs

    p = normalize_public_path(path)

    assert agent._session_manager is not None
    backend = agent._session_manager.get_backend(project_id)
    fs = SandboxFs(backend)
    try:
        r = fs.read(p)
    except FileNotFoundError:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return JSONResponse(
        {
            "path": r.path,
            "content": r.content,
            "sha256": r.sha256,
            "is_binary": bool(r.is_binary),
        },
        status_code=200,
    )


@app.put("/api/sandbox/{project_id}/write")
async def api_sandbox_write(project_id: str, request: Request) -> JSONResponse:
    try:
        _ensure_project_access(request, project_id=project_id)
    except PermissionError:
        return JSONResponse({"error": "not_authenticated"}, status_code=401)

    body: Any
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    path = str(body.get("path") or "")
    content = str(body.get("content") or "")
    expected_sha = body.get("expected_sha256")
    expected_sha = str(expected_sha) if isinstance(expected_sha, str) and expected_sha else None

    agent = _get_agent()
    await agent.init(session_id=project_id)

    from src.sandbox_files.policy import normalize_public_path
    from src.sandbox_files.sandbox_fs import SandboxFs

    p = normalize_public_path(path)

    assert agent._session_manager is not None
    backend = agent._session_manager.get_backend(project_id)
    fs = SandboxFs(backend)
    try:
        sha = fs.write(path=p, content=content, expected_sha256=expected_sha)
    except FileNotFoundError:
        return JSONResponse({"error": "not_found"}, status_code=404)
    except RuntimeError as e:
        if str(e) == "conflict":
            return JSONResponse({"error": "conflict"}, status_code=409)
        return JSONResponse({"error": str(e)}, status_code=400)
    except PermissionError:
        return JSONResponse({"error": "permission_denied"}, status_code=403)

    return JSONResponse({"path": p, "sha256": sha}, status_code=200)


@app.post("/api/sandbox/{project_id}/mkdir")
async def api_sandbox_mkdir(project_id: str, request: Request) -> JSONResponse:
    try:
        _ensure_project_access(request, project_id=project_id)
    except PermissionError:
        return JSONResponse({"error": "not_authenticated"}, status_code=401)

    body: Any
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    path = str(body.get("path") or "")

    agent = _get_agent()
    await agent.init(session_id=project_id)

    from src.sandbox_files.policy import normalize_public_path
    from src.sandbox_files.sandbox_fs import SandboxFs

    p = normalize_public_path(path)

    assert agent._session_manager is not None
    backend = agent._session_manager.get_backend(project_id)
    fs = SandboxFs(backend)
    try:
        fs.mkdir(p)
    except PermissionError:
        return JSONResponse({"error": "permission_denied"}, status_code=403)
    return JSONResponse({"path": p}, status_code=200)


@app.post("/api/sandbox/{project_id}/create")
async def api_sandbox_create(project_id: str, request: Request) -> JSONResponse:
    try:
        _ensure_project_access(request, project_id=project_id)
    except PermissionError:
        return JSONResponse({"error": "not_authenticated"}, status_code=401)

    body: Any
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    path = str(body.get("path") or "")
    kind = str(body.get("kind") or "")
    content = str(body.get("content") or "")

    agent = _get_agent()
    await agent.init(session_id=project_id)

    from src.sandbox_files.policy import normalize_public_path
    from src.sandbox_files.sandbox_fs import SandboxFs

    p = normalize_public_path(path)
    if kind not in ("file", "dir"):
        return JSONResponse({"error": "invalid_kind"}, status_code=400)

    assert agent._session_manager is not None
    backend = agent._session_manager.get_backend(project_id)
    fs = SandboxFs(backend)
    try:
        if kind == "dir":
            fs.mkdir(p)
            return JSONResponse({"path": p}, status_code=200)
        sha = fs.create_file(path=p, content=content)
        return JSONResponse({"path": p, "sha256": sha}, status_code=200)
    except PermissionError:
        return JSONResponse({"error": "permission_denied"}, status_code=403)
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/sandbox/{project_id}/rename")
async def api_sandbox_rename(project_id: str, request: Request) -> JSONResponse:
    try:
        _ensure_project_access(request, project_id=project_id)
    except PermissionError:
        return JSONResponse({"error": "not_authenticated"}, status_code=401)

    body: Any
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    src = str(body.get("from") or "")
    dst = str(body.get("to") or "")

    agent = _get_agent()
    await agent.init(session_id=project_id)

    from src.sandbox_files.policy import normalize_public_path
    from src.sandbox_files.sandbox_fs import SandboxFs

    s = normalize_public_path(src)
    d = normalize_public_path(dst)

    assert agent._session_manager is not None
    backend = agent._session_manager.get_backend(project_id)
    fs = SandboxFs(backend)
    try:
        fs.rename(src=s, dst=d)
    except PermissionError:
        return JSONResponse({"error": "permission_denied"}, status_code=403)
    return JSONResponse({"from": s, "to": d}, status_code=200)


@app.delete("/api/sandbox/{project_id}/rm")
async def api_sandbox_rm(
    project_id: str, request: Request, path: str, recursive: int = 0
) -> JSONResponse:
    try:
        _ensure_project_access(request, project_id=project_id)
    except PermissionError:
        return JSONResponse({"error": "not_authenticated"}, status_code=401)

    agent = _get_agent()
    await agent.init(session_id=project_id)

    from src.sandbox_files.policy import normalize_public_path
    from src.sandbox_files.sandbox_fs import SandboxFs

    p = normalize_public_path(path)
    rec = bool(int(recursive or 0))

    assert agent._session_manager is not None
    backend = agent._session_manager.get_backend(project_id)
    fs = SandboxFs(backend)
    try:
        fs.rm(path=p, recursive=rec)
    except PermissionError:
        return JSONResponse({"error": "permission_denied"}, status_code=403)
    return JSONResponse({"path": p}, status_code=200)


def _db_proxy_origin_mode() -> str:
    return (
        (os.environ.get("AMICABLE_DB_PROXY_ORIGIN_MODE") or "strict_preview")
        .strip()
        .lower()
    )


def _db_cors_headers(origin: str) -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Headers": "content-type,x-amicable-app-key",
        "Access-Control-Allow-Methods": "POST,OPTIONS",
        "Vary": "Origin",
    }


def _origin_allowed_for_app(origin: str, *, app_id: str) -> bool:
    mode = _db_proxy_origin_mode()
    if mode == "any":
        return bool(origin)

    # Default: only allow the expected preview origin for this deterministic app.
    from src.db.origin import origin_matches_expected

    try:
        return origin_matches_expected(
            origin,
            app_id=app_id,
            preview_base_domain=os.environ.get("PREVIEW_BASE_DOMAIN") or "",
            preview_scheme=os.environ.get("PREVIEW_SCHEME") or "https",
        )
    except Exception:
        return False


@app.options("/db/apps/{app_id}/graphql")
async def db_graphql_preflight(app_id: str, request: Request) -> Response:
    origin = (request.headers.get("origin") or "").strip()
    if not origin or not _origin_allowed_for_app(origin, app_id=app_id):
        return Response(status_code=403)
    return Response(status_code=204, headers=_db_cors_headers(origin))


@app.post("/db/apps/{app_id}/graphql")
async def db_graphql_proxy(app_id: str, request: Request) -> Response:
    origin = (request.headers.get("origin") or "").strip()
    if not origin or not _origin_allowed_for_app(origin, app_id=app_id):
        return Response(status_code=403, content=b"forbidden")

    app_key = (request.headers.get("x-amicable-app-key") or "").strip()
    if not app_key:
        return Response(
            status_code=401,
            content=b"missing app key",
            headers=_db_cors_headers(origin),
        )

    # Load app record to validate key + get role.
    try:
        from src.db.jwt import mint_hasura_jwt
        from src.db.provisioning import get_app, hasura_client_from_env, verify_app_key

        client = hasura_client_from_env()
        app = get_app(client, app_id=app_id)
        if not app:
            return Response(
                status_code=404,
                content=b"unknown app",
                headers=_db_cors_headers(origin),
            )
        if not verify_app_key(app=app, app_key=app_key):
            return Response(
                status_code=403,
                content=b"invalid app key",
                headers=_db_cors_headers(origin),
            )

        jwt_secret = (os.environ.get("HASURA_GRAPHQL_JWT_SECRET") or "").strip()
        if not jwt_secret:
            return Response(
                status_code=503,
                content=b"hasura jwt not configured",
                headers=_db_cors_headers(origin),
            )

        bearer = mint_hasura_jwt(
            jwt_secret_json=jwt_secret,
            role_name=app.role_name,
            app_id=app_id,
            ttl_s=300,
        )

        body = await request.json()
        if not isinstance(body, dict):
            return Response(
                status_code=400,
                content=b"invalid body",
                headers=_db_cors_headers(origin),
            )
        resp = client.graphql(body, bearer_jwt=bearer)
    except Exception as e:
        return Response(
            status_code=500,
            content=str(e).encode("utf-8", errors="replace"),
            headers=_db_cors_headers(origin),
        )

    headers = _db_cors_headers(origin)
    # Bubble up content-type from Hasura if present.
    ct = resp.headers.get("content-type")
    if ct:
        headers["content-type"] = ct
    return Response(status_code=resp.status_code, content=resp.content, headers=headers)


@app.on_event("startup")
async def _startup() -> None:
    global _agent
    if _agent is None:
        _agent = Agent()


@app.get("/auth/me")
async def auth_me(request: Request) -> JSONResponse:
    if _auth_mode() != "google":
        return JSONResponse(
            {"authenticated": False, "mode": _auth_mode()}, status_code=200
        )

    user = (request.session or {}).get("user")  # type: ignore[attr-defined]
    if not user:
        return JSONResponse({"authenticated": False, "mode": "google"}, status_code=200)
    return JSONResponse(
        {"authenticated": True, "mode": "google", "user": user}, status_code=200
    )


@app.get("/auth/login")
async def auth_login(request: Request, redirect: str | None = None):
    if _auth_mode() != "google":
        return JSONResponse({"error": "AUTH_MODE is not google"}, status_code=400)

    oauth = _google_oauth()
    if oauth is None:
        return JSONResponse(
            {
                "error": "Google OAuth not configured (missing deps or GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET)"
            },
            status_code=500,
        )

    if redirect and _is_allowed_redirect(redirect, request=request):
        request.session["post_auth_redirect"] = redirect  # type: ignore[index,attr-defined]
    else:
        request.session.pop("post_auth_redirect", None)  # type: ignore[union-attr]

    base = (os.environ.get("PUBLIC_BASE_URL") or "").rstrip("/")
    redirect_uri = (
        f"{base}/auth/callback" if base else str(request.url_for("auth_callback"))
    )
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/auth/callback", name="auth_callback")
async def auth_callback(request: Request):
    if _auth_mode() != "google":
        return JSONResponse({"error": "AUTH_MODE is not google"}, status_code=400)

    oauth = _google_oauth()
    if oauth is None:
        return JSONResponse(
            {
                "error": "Google OAuth not configured (missing deps or GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET)"
            },
            status_code=500,
        )

    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as e:
        return JSONResponse({"error": "oauth_error", "detail": str(e)}, status_code=400)

    userinfo = token.get("userinfo")
    if not userinfo:
        try:
            userinfo = await oauth.google.parse_id_token(request, token)
        except Exception:
            userinfo = None

    if not userinfo:
        return JSONResponse({"error": "missing_userinfo"}, status_code=400)

    request.session["user"] = {  # type: ignore[index,attr-defined]
        "sub": userinfo.get("sub"),
        "email": userinfo.get("email"),
        "name": userinfo.get("name"),
        "picture": userinfo.get("picture"),
    }

    dest = request.session.pop("post_auth_redirect", "/")  # type: ignore[union-attr]
    if isinstance(dest, str) and _is_allowed_redirect(dest, request=request):
        return RedirectResponse(url=dest, status_code=302)
    return RedirectResponse(url="/", status_code=302)


@app.get("/auth/logout")
async def auth_logout(request: Request, redirect: str | None = None):
    if _auth_mode() != "google":
        return JSONResponse({"error": "AUTH_MODE is not google"}, status_code=400)

    request.session.clear()  # type: ignore[attr-defined]
    dest = (
        redirect
        if (redirect and _is_allowed_redirect(redirect, request=request))
        else "/"
    )
    return RedirectResponse(url=dest, status_code=302)


def _require_auth(ws: WebSocket) -> None:
    mode = _auth_mode()
    if mode == "none":
        return

    if mode == "token":
        expected = os.environ.get("AGENT_AUTH_TOKEN")
        # Keep old behavior: if token isn't configured, don't enforce.
        if not expected:
            return
        token = ws.query_params.get("auth_token")
        if token != expected:
            raise PermissionError("invalid auth_token")
        return

    if mode == "google":
        user = getattr(ws, "session", {}).get("user")  # type: ignore[attr-defined]
        if not user:
            raise PermissionError("not authenticated")
        return

    raise PermissionError(f"unknown AUTH_MODE: {mode}")


async def _handle_ws(ws: WebSocket) -> None:
    try:
        _require_auth(ws)
    except PermissionError:
        await ws.close(code=1008)
        return

    await ws.accept()

    global _agent
    if _agent is None:
        _agent = Agent()
    agent = _agent

    while True:
        try:
            raw = await ws.receive_text()
        except WebSocketDisconnect:
            return

        msg: dict[str, Any]
        try:
            msg = json.loads(raw)
        except Exception:
            continue

        mtype = msg.get("type")
        data = msg.get("data") or {}

        if mtype == MessageType.INIT.value:
            session_id = data.get("session_id")
            if not session_id:
                # Keep behavior: server-side session id if missing.
                session_id = Message.new(
                    MessageType.INIT, {}, session_id=None
                ).session_id

            project = None
            git = None
            if _hasura_enabled():
                try:
                    sub, email = _get_owner_from_ws(ws)
                    from src.db.provisioning import hasura_client_from_env
                    from src.gitlab.integration import ensure_gitlab_repo_for_project
                    from src.projects.store import ProjectOwner, ensure_project_for_id

                    client = hasura_client_from_env()
                    owner = ProjectOwner(sub=sub, email=email)
                    project = ensure_project_for_id(
                        client, owner=owner, project_id=str(session_id)
                    )

                    # Best-effort GitLab enrichment.
                    try:
                        project, git = ensure_gitlab_repo_for_project(
                            client, owner=owner, project=project
                        )
                    except Exception:
                        git = None
                except PermissionError:
                    await ws.close(code=1008)
                    return
                except Exception:
                    # If projects are misconfigured, continue without project metadata.
                    project = None
                    git = None

            template_id = getattr(project, "template_id", None) if project is not None else None
            exists = await agent.init(session_id=session_id, template_id=template_id)
            init_data = agent.session_data[session_id]
            init_data["exists"] = exists
            if project is not None:
                init_data["project"] = _project_dto(project)
                init_data["template_id"] = getattr(project, "template_id", None)
            if git is not None:
                init_data["git"] = git
            pending = agent.get_pending_hitl(session_id)
            if pending:
                init_data["hitl_pending"] = pending

            await ws.send_json(
                Message.new(
                    MessageType.INIT,
                    session_id=session_id,
                    data=init_data,
                ).to_dict()
            )
            continue

        if mtype == MessageType.USER.value:
            session_id = data.get("session_id")
            text = data.get("text")
            if not session_id or not isinstance(text, str):
                await ws.send_json(
                    Message.new(
                        MessageType.ERROR,
                        {"error": "missing session_id or text"},
                        session_id=session_id or "",
                    ).to_dict()
                )
                continue

            if _hasura_enabled():
                try:
                    sub, email = _get_owner_from_ws(ws)
                    from src.db.provisioning import hasura_client_from_env
                    from src.gitlab.integration import ensure_gitlab_repo_for_project
                    from src.projects.store import ProjectOwner, ensure_project_for_id

                    client = hasura_client_from_env()
                    owner = ProjectOwner(sub=sub, email=email)
                    project = ensure_project_for_id(
                        client, owner=owner, project_id=str(session_id)
                    )

                    # Ensure agent session exists so we can attach project/git metadata
                    # for downstream controller graph nodes (git_sync).
                    await agent.init(session_id=session_id)
                    try:
                        project, git = ensure_gitlab_repo_for_project(
                            client, owner=owner, project=project
                        )
                    except Exception:
                        git = None

                    # Persist into session_data for the controller run.
                    init_data = agent.session_data.get(session_id) or {}
                    if isinstance(init_data, dict):
                        init_data["project"] = _project_dto(project)
                        if git is not None:
                            init_data["git"] = git
                        agent.session_data[session_id] = init_data
                except PermissionError:
                    await ws.close(code=1008)
                    return
                except Exception:
                    # If projects are misconfigured, don't block core editing.
                    pass
            if agent.has_pending_hitl(session_id):
                await ws.send_json(
                    Message.new(
                        MessageType.ERROR,
                        {
                            "error": "HITL approval pending. Approve/reject the pending tool call to continue."
                        },
                        session_id=session_id,
                    ).to_dict()
                )
                continue

            async for out in agent.send_feedback(session_id=session_id, feedback=text):
                await ws.send_json(out)
            continue

        if mtype == MessageType.HITL_RESPONSE.value:
            session_id = data.get("session_id")
            interrupt_id = data.get("interrupt_id")
            response = data.get("response")
            if (
                not session_id
                or not isinstance(interrupt_id, str)
                or not isinstance(response, dict)
            ):
                await ws.send_json(
                    Message.new(
                        MessageType.ERROR,
                        {"error": "missing session_id, interrupt_id, or response"},
                        session_id=session_id or "",
                    ).to_dict()
                )
                continue

            if _hasura_enabled():
                try:
                    sub, email = _get_owner_from_ws(ws)
                    from src.db.provisioning import hasura_client_from_env
                    from src.gitlab.integration import ensure_gitlab_repo_for_project
                    from src.projects.store import ProjectOwner, ensure_project_for_id

                    client = hasura_client_from_env()
                    owner = ProjectOwner(sub=sub, email=email)
                    project = ensure_project_for_id(
                        client, owner=owner, project_id=str(session_id)
                    )

                    await agent.init(session_id=session_id)
                    try:
                        project, git = ensure_gitlab_repo_for_project(
                            client, owner=owner, project=project
                        )
                    except Exception:
                        git = None

                    init_data = agent.session_data.get(session_id) or {}
                    if isinstance(init_data, dict):
                        init_data["project"] = _project_dto(project)
                        if git is not None:
                            init_data["git"] = git
                        agent.session_data[session_id] = init_data
                except PermissionError:
                    await ws.close(code=1008)
                    return
                except Exception:
                    pass

            async for out in agent.resume_hitl(
                session_id=session_id,
                interrupt_id=interrupt_id,
                response=response,
            ):
                await ws.send_json(out)
            continue

        # Ignore unknowns (frontend can send ping)
        if mtype == MessageType.PING.value:
            await ws.send_json(
                Message.new(
                    MessageType.PING, {}, session_id=data.get("session_id") or ""
                ).to_dict()
            )
            continue


@app.websocket("/")
async def websocket_root(ws: WebSocket) -> None:
    await _handle_ws(ws)


@app.websocket("/ws")
async def websocket_ws(ws: WebSocket) -> None:
    await _handle_ws(ws)
