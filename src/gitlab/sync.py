from __future__ import annotations

import glob
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Any, Protocol

from src.gitlab.config import (
    git_commit_author_email,
    git_commit_author_name,
    git_sync_branch,
    git_sync_cache_dir,
    git_sync_excludes,
    gitlab_token,
)

_GIT_STATE_PATH = "/.amicable/git_state.json"


class CommandRunner(Protocol):
    def run(
        self,
        args: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]: ...


@dataclass
class SubprocessRunner:
    def run(
        self,
        args: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            check=check,
        )


def _git_show_bytes(
    repo_dir: str, *, env: dict[str, str], sha: str, path: str
) -> bytes | None:
    """Return file content at <sha>:<path>, or None if missing."""
    # Use `git show` for blob contents; avoid text decoding (binary safe).
    cp = subprocess.run(
        ["git", "show", f"{sha}:{path}"],
        cwd=repo_dir,
        env=env,
        capture_output=True,
        check=False,
    )
    if cp.returncode != 0:
        return None
    return cp.stdout


def _read_git_state(backend: Any) -> dict[str, Any] | None:
    try:
        res = backend.download_files([_GIT_STATE_PATH])
    except Exception:
        return None
    if not res:
        return None

    item = res[0]
    if isinstance(item, dict):
        err = item.get("error")
        content = item.get("content")
    else:
        err = getattr(item, "error", None)
        content = getattr(item, "content", None)

    if err is not None or content is None:
        return None

    payload = content
    if not isinstance(payload, (bytes, bytearray)):
        try:
            payload = str(payload).encode("utf-8", errors="replace")
        except Exception:
            return None
    try:
        parsed = json.loads(bytes(payload).decode("utf-8"))
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _write_git_state(backend: Any, state: dict[str, Any]) -> None:
    # Best-effort: keep git sync functional even if state writes fail.
    with suppress(Exception):
        backend.execute("cd /app && mkdir -p .amicable")

    try:
        payload = json.dumps(state, ensure_ascii=True, sort_keys=True).encode("utf-8")
        up = backend.upload_files([(_GIT_STATE_PATH, payload)])
        if not up or (isinstance(up[0], dict) and up[0].get("error") is not None):
            return
    except Exception:
        return


def get_remote_head_sha(
    *, repo_http_url: str, branch: str | None = None, runner: CommandRunner | None = None
) -> str | None:
    token = gitlab_token()
    if not token:
        raise RuntimeError("GITLAB_TOKEN is not set")
    r = runner or SubprocessRunner()
    br = (branch or git_sync_branch()).strip() or "main"

    with _git_auth_env(token=token) as env:
        heads = r.run(
            ["git", "ls-remote", "--heads", repo_http_url, br], env=env, check=True
        )
        out = (heads.stdout or "").strip()
        if not out:
            return None
        # Format: "<sha>\trefs/heads/<branch>"
        sha = out.split()[0].strip()
        return sha or None


def _bytes_equal(a: bytes | None, b: bytes | None) -> bool:
    if a is None or b is None:
        return False
    return a == b


def _download_one(backend: Any, public_path: str) -> tuple[bytes | None, str | None]:
    try:
        res = backend.download_files([public_path])
    except Exception as e:
        return None, str(e)
    if not res:
        return None, "file_not_found"
    item = res[0]
    if isinstance(item, dict):
        err = item.get("error")
        content = item.get("content")
    else:
        err = getattr(item, "error", None)
        content = getattr(item, "content", None)
    if err is not None or content is None:
        return None, str(err) if err else "file_not_found"
    if not isinstance(content, (bytes, bytearray)):
        try:
            content = str(content).encode("utf-8", errors="replace")
        except Exception:
            return None, "invalid_content"
    return bytes(content), None


def _ensure_parent_dirs(backend: Any, public_paths: list[str]) -> None:
    parents: set[str] = set()
    for p in public_paths:
        rel = _normalize_rel_path(p)
        if not rel or rel == ".":
            continue
        parent = os.path.dirname(rel)
        if parent and parent != ".":
            parents.add(parent)
    for parent in sorted(parents):
        with suppress(Exception):
            backend.execute(f"cd /app && mkdir -p -- {shlex.quote(parent)}")


def sync_repo_tree_to_sandbox(
    backend: Any,
    *,
    repo_http_url: str,
    project_slug: str,
    branch: str | None = None,
    cache_dir: str | None = None,
    excludes: list[str] | None = None,
    runner: CommandRunner | None = None,
) -> dict[str, Any]:
    """Fetch remote repo changes and apply them into the sandbox (non-destructive).

    If a path conflicts (sandbox diverged from base_sha), write the remote version
    under `/.amicable/git-remote/<remote_sha>/...` and return conflict metadata.
    """
    token = gitlab_token()
    if not token:
        raise RuntimeError("GITLAB_TOKEN is not set")

    r = runner or SubprocessRunner()
    br = (branch or git_sync_branch()).strip() or "main"
    ex = excludes or git_sync_excludes()
    cache = cache_dir or git_sync_cache_dir()

    repo_dir = os.path.join(cache, _sanitize_dir_name(project_slug))
    os.makedirs(cache, exist_ok=True)

    with _git_auth_env(token=token) as env:
        if not os.path.isdir(os.path.join(repo_dir, ".git")):
            if os.path.exists(repo_dir):
                shutil.rmtree(repo_dir)
            r.run(["git", "clone", repo_http_url, repo_dir], env=env, check=True)

        r.run(["git", "fetch", "origin"], cwd=repo_dir, env=env, check=True)

        # Resolve remote head for the branch.
        remote_sha = (
            r.run(
                ["git", "rev-parse", f"origin/{br}"],
                cwd=repo_dir,
                env=env,
                check=False,
            ).stdout.strip()
            or None
        )
        if not remote_sha:
            return {
                "updated": False,
                "remote_sha": None,
                "applied": {"added": [], "modified": [], "deleted": []},
                "conflicts": [],
                "error": "remote_branch_missing",
                "detail": f"origin/{br} not found",
            }

        state = _read_git_state(backend) or {}
        base_sha = state.get("remote_head_sha") if isinstance(state, dict) else None
        if not isinstance(base_sha, str) or not base_sha.strip():
            return {"error": "git_pull_no_baseline", "remote_sha": remote_sha}
        base_sha = base_sha.strip()

        if remote_sha == base_sha:
            return {
                "updated": False,
                "remote_sha": remote_sha,
                "applied": {"added": [], "modified": [], "deleted": []},
                "conflicts": [],
            }

        diff = (
            r.run(
                ["git", "diff", "--name-status", f"{base_sha}..{remote_sha}"],
                cwd=repo_dir,
                env=env,
                check=True,
            ).stdout
            or ""
        )

        changes: list[tuple[str, str]] = []  # (status, path) for A/M/D only
        for line in diff.splitlines():
            if not line.strip():
                continue
            # Prefer tab separation (robust to spaces in filenames), but fall back
            # to generic whitespace splitting if git emits space-separated output.
            parts = line.split("\t") if "\t" in line else line.split()
            st = parts[0].strip()
            if st.startswith("R") and len(parts) >= 3:
                oldp = parts[1].strip()
                newp = parts[2].strip()
                if oldp:
                    changes.append(("D", oldp))
                if newp:
                    changes.append(("A", newp))
                continue
            if st.startswith("C") and len(parts) >= 3:
                # Copy: treat as add of new path.
                newp = parts[2].strip()
                if newp:
                    changes.append(("A", newp))
                continue
            if st in ("A", "M", "D") and len(parts) >= 2:
                p = parts[1].strip()
                if p:
                    changes.append((st, p))

        applied_added: list[str] = []
        applied_modified: list[str] = []
        applied_deleted: list[str] = []
        conflicts: list[dict[str, str]] = []

        upload_batch: list[tuple[str, bytes]] = []
        shadow_uploads: list[tuple[str, bytes]] = []
        shadow_paths: list[str] = []
        upload_paths: list[str] = []

        def _shadow_path(p: str) -> str:
            rel = _normalize_rel_path(p)
            return f"/.amicable/git-remote/{remote_sha}/{rel}"

        for st, rel_path in changes:
            if _excluded(rel_path, excludes=ex):
                continue

            pub_path = "/" + _normalize_rel_path(rel_path)

            if pub_path.startswith("/.amicable/"):
                continue

            sandbox_bytes, sandbox_err = _download_one(backend, pub_path)
            sandbox_exists = sandbox_err is None

            if st in ("A", "M"):
                remote_bytes = _git_show_bytes(
                    repo_dir, env=env, sha=remote_sha, path=rel_path
                )
                if remote_bytes is None:
                    # Nothing to apply.
                    continue

                if st == "A":
                    if (not sandbox_exists) or _bytes_equal(sandbox_bytes, remote_bytes):
                        if not sandbox_exists:
                            upload_batch.append((pub_path, remote_bytes))
                            upload_paths.append(pub_path)
                            applied_added.append(pub_path)
                        # else already matches; no-op
                    else:
                        sp = _shadow_path(rel_path)
                        shadow_uploads.append((sp, remote_bytes))
                        shadow_paths.append(sp)
                        conflicts.append(
                            {
                                "path": pub_path,
                                "remote_sha": remote_sha,
                                "remote_shadow_path": sp,
                            }
                        )
                    continue

                # st == "M"
                base_bytes = _git_show_bytes(
                    repo_dir, env=env, sha=base_sha, path=rel_path
                )
                if base_bytes is None:
                    # If base is missing but diff says modified, be conservative.
                    sp = _shadow_path(rel_path)
                    shadow_uploads.append((sp, remote_bytes))
                    shadow_paths.append(sp)
                    conflicts.append(
                        {
                            "path": pub_path,
                            "remote_sha": remote_sha,
                            "remote_shadow_path": sp,
                        }
                    )
                    continue

                if not sandbox_exists:
                    sp = _shadow_path(rel_path)
                    shadow_uploads.append((sp, remote_bytes))
                    shadow_paths.append(sp)
                    conflicts.append(
                        {
                            "path": pub_path,
                            "remote_sha": remote_sha,
                            "remote_shadow_path": sp,
                        }
                    )
                    continue

                if _bytes_equal(sandbox_bytes, base_bytes):
                    upload_batch.append((pub_path, remote_bytes))
                    upload_paths.append(pub_path)
                    applied_modified.append(pub_path)
                elif _bytes_equal(sandbox_bytes, remote_bytes):
                    # already at remote version; no-op
                    pass
                else:
                    sp = _shadow_path(rel_path)
                    shadow_uploads.append((sp, remote_bytes))
                    shadow_paths.append(sp)
                    conflicts.append(
                        {
                            "path": pub_path,
                            "remote_sha": remote_sha,
                            "remote_shadow_path": sp,
                        }
                    )
                continue

            # st == "D"
            base_bytes = _git_show_bytes(repo_dir, env=env, sha=base_sha, path=rel_path)
            if not sandbox_exists:
                # Already deleted locally; no-op.
                continue
            if base_bytes is None:
                # Can't validate; treat as conflict.
                marker = _shadow_path(rel_path) + ".REMOTE_DELETED"
                msg = f"REMOTE DELETED {pub_path} at {remote_sha}\n".encode()
                shadow_uploads.append((marker, msg))
                shadow_paths.append(marker)
                conflicts.append(
                    {
                        "path": pub_path,
                        "remote_sha": remote_sha,
                        "remote_shadow_path": marker,
                    }
                )
                continue
            if _bytes_equal(sandbox_bytes, base_bytes):
                try:
                    rel = _normalize_rel_path(pub_path)
                    backend.execute(f"cd /app && rm -f -- {shlex.quote(rel)}")
                    applied_deleted.append(pub_path)
                except Exception:
                    # If delete fails, surface as conflict-ish shadow marker.
                    marker = _shadow_path(rel_path) + ".REMOTE_DELETED"
                    msg = f"REMOTE DELETED {pub_path} at {remote_sha}\n".encode()
                    shadow_uploads.append((marker, msg))
                    shadow_paths.append(marker)
                    conflicts.append(
                        {
                            "path": pub_path,
                            "remote_sha": remote_sha,
                            "remote_shadow_path": marker,
                        }
                    )
            else:
                marker = _shadow_path(rel_path) + ".REMOTE_DELETED"
                msg = f"REMOTE DELETED {pub_path} at {remote_sha}\n".encode()
                shadow_uploads.append((marker, msg))
                shadow_paths.append(marker)
                conflicts.append(
                    {
                        "path": pub_path,
                        "remote_sha": remote_sha,
                        "remote_shadow_path": marker,
                    }
                )

        # Ensure parent dirs exist in sandbox, then upload.
        _ensure_parent_dirs(backend, upload_paths + shadow_paths)

        if upload_batch:
            # backend.upload_files expects public paths like "/src/App.tsx".
            for i in range(0, len(upload_batch), 200):
                chunk = upload_batch[i : i + 200]
                backend.upload_files([(p, b) for p, b in chunk])
        if shadow_uploads:
            for i in range(0, len(shadow_uploads), 200):
                chunk = shadow_uploads[i : i + 200]
                backend.upload_files([(p, b) for p, b in chunk])

        # Update sandbox-local git state to avoid repeated prompts.
        _write_git_state(
            backend,
            {
                "branch": br,
                "remote_head_sha": remote_sha,
                "updated_at_unix": int(time.time()),
                "conflicts": conflicts,
            },
        )

        return {
            "updated": True,
            "remote_sha": remote_sha,
            "applied": {
                "added": applied_added,
                "modified": applied_modified,
                "deleted": applied_deleted,
            },
            "conflicts": conflicts,
        }


def _sanitize_dir_name(name: str) -> str:
    s = (name or "").strip().lower()
    s = re.sub(r"[^a-z0-9_.-]+", "-", s)
    s = s.strip("-.")
    return s or "project"


def _is_glob(pat: str) -> bool:
    return any(ch in pat for ch in ("*", "?", "["))


@contextmanager
def _git_auth_env(*, token: str) -> dict[str, str]:
    # Use GIT_ASKPASS to avoid embedding tokens in URLs.
    tmpdir = tempfile.mkdtemp(prefix="amicable-askpass-")
    script = os.path.join(tmpdir, "askpass.sh")

    # Git prompts vary; cover common cases.
    content = """#!/bin/sh
case "$1" in
  *Username*) echo "oauth2" ;;
  *Password*) echo "$GITLAB_TOKEN" ;;
  *) echo "" ;;
esac
"""
    with open(script, "w", encoding="utf-8") as f:
        f.write(content)
    os.chmod(script, 0o700)

    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = script
    env["GITLAB_TOKEN"] = token

    try:
        yield env
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _rsync_available() -> bool:
    return shutil.which("rsync") is not None


def _normalize_rel_path(p: str) -> str:
    s = (p or "").strip().lstrip("/")
    if s.startswith("./"):
        s = s[2:]
    return s


def _excluded(path: str, *, excludes: list[str]) -> bool:
    rel = _normalize_rel_path(path)
    if not rel or rel == ".":
        return False

    for raw in excludes:
        pat = (raw or "").strip()
        if not pat:
            continue
        pat = _normalize_rel_path(pat)
        if not pat:
            continue

        # Treat trailing slash as directory prefix exclude.
        if raw.rstrip() != raw.rstrip("/"):
            base = pat.rstrip("/")
            if rel == base or rel.startswith(base + "/"):
                return True
            continue

        if _is_glob(pat):
            if fnmatch(rel, pat):
                return True
            continue

        if rel == pat:
            return True

    return False


def _remove_excluded_paths(repo_dir: str, *, excludes: list[str]) -> None:
    """Hard-remove excluded paths from the destination tree.

    rsync excludes prevent both copying and deletion. We want excluded paths to
    be absent from the repo even if they were previously committed, so we
    enforce deletion explicitly (skipping .git).
    """
    for raw in excludes:
        pat = (raw or "").strip()
        if not pat:
            continue
        # Never touch git metadata.
        if pat.rstrip("/") == ".git":
            continue
        pat = pat.lstrip("/")
        # Remove trailing slash for filesystem ops.
        pat_no_slash = pat.rstrip("/")

        # Glob patterns: remove all matches.
        if any(ch in pat_no_slash for ch in ("*", "?", "[")):
            matches = glob.glob(os.path.join(repo_dir, pat_no_slash))
            for m in matches:
                if os.path.basename(m) == ".git":
                    continue
                if os.path.isdir(m) and not os.path.islink(m):
                    shutil.rmtree(m, ignore_errors=True)
                else:
                    with suppress(FileNotFoundError):
                        os.unlink(m)
            continue

        target = os.path.join(repo_dir, pat_no_slash)
        if os.path.isdir(target) and not os.path.islink(target):
            shutil.rmtree(target, ignore_errors=True)
        else:
            with suppress(FileNotFoundError):
                os.unlink(target)


def _sync_tree_fallback(src: str, dst: str) -> None:
    # Python-only fallback when rsync isn't available.
    # Strategy: delete everything except .git, then copy.
    for entry in os.listdir(dst):
        if entry == ".git":
            continue
        path = os.path.join(dst, entry)
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            with suppress(FileNotFoundError):
                os.unlink(path)

    for root, _dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        if rel == ".":
            rel = ""
        for fn in files:
            if fn == ".git":
                continue
            src_path = os.path.join(root, fn)
            out_path = os.path.join(dst, rel, fn)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            shutil.copy2(src_path, out_path)


def _git_dirty(runner: CommandRunner, repo_dir: str, *, env: dict[str, str]) -> bool:
    cp = runner.run(["git", "status", "--porcelain"], cwd=repo_dir, env=env, check=True)
    return bool((cp.stdout or "").strip())


def _clear_worktree(repo_dir: str) -> None:
    for entry in os.listdir(repo_dir):
        if entry == ".git":
            continue
        path = os.path.join(repo_dir, entry)
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            with suppress(FileNotFoundError):
                os.unlink(path)


def _write_file(path: str, content: bytes, *, mode: int | None) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    if mode is not None:
        with suppress(Exception):
            os.chmod(path, int(mode) & 0o777)


def _write_symlink(path: str, target: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with suppress(FileNotFoundError):
        os.unlink(path)
    os.symlink(target, path)


def _backend_manifest_entries(backend: Any) -> list[dict[str, Any]]:
    if not hasattr(backend, "manifest"):
        raise RuntimeError("sandbox backend does not support manifest()")
    entries = backend.manifest("/")  # public root
    if not isinstance(entries, list):
        return []
    out: list[dict[str, Any]] = []
    for e in entries:
        if isinstance(e, dict):
            out.append(e)
    return out


def sync_sandbox_tree_to_repo(
    backend: Any,
    *,
    repo_http_url: str,
    project_slug: str,
    commit_message: str | None = None,
    commit_message_fn: Any | None = None,
    branch: str | None = None,
    cache_dir: str | None = None,
    excludes: list[str] | None = None,
    runner: CommandRunner | None = None,
    allow_empty_commit: bool = False,
) -> tuple[bool, str | None, str, str]:
    """Sync sandbox filesystem tree into a cached clone, commit, and push.

    Returns (pushed, commit_sha, diff_stat, name_status) where diff outputs are
    from the staged index (git diff --cached).
    """

    token = gitlab_token()
    if not token:
        raise RuntimeError("GITLAB_TOKEN is not set")

    r = runner or SubprocessRunner()
    br = (branch or git_sync_branch()).strip() or "main"
    ex = excludes or git_sync_excludes()
    cache = cache_dir or git_sync_cache_dir()

    repo_dir = os.path.join(cache, _sanitize_dir_name(project_slug))
    os.makedirs(cache, exist_ok=True)

    with _git_auth_env(token=token) as env:
        # Clone if needed.
        if not os.path.isdir(os.path.join(repo_dir, ".git")):
            if os.path.exists(repo_dir):
                shutil.rmtree(repo_dir)
            r.run(["git", "clone", repo_http_url, repo_dir], env=env, check=True)

        # Fetch and checkout branch.
        r.run(["git", "fetch", "origin"], cwd=repo_dir, env=env, check=True)

        heads = r.run(
            ["git", "ls-remote", "--heads", "origin", br],
            cwd=repo_dir,
            env=env,
            check=True,
        )
        if (heads.stdout or "").strip():
            r.run(
                ["git", "checkout", "-B", br, f"origin/{br}"],
                cwd=repo_dir,
                env=env,
                check=True,
            )
            base_sha = (
                r.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=repo_dir,
                    env=env,
                    check=True,
                ).stdout.strip()
                or None
            )
        else:
            # New/empty repo: create orphan branch.
            r.run(
                ["git", "checkout", "--orphan", br], cwd=repo_dir, env=env, check=True
            )
            base_sha = None
            # Clear index and working tree (except .git).
            r.run(["git", "rm", "-rf", "."], cwd=repo_dir, env=env, check=False)

        # Populate worktree from sandbox manifest.
        _clear_worktree(repo_dir)

        entries = _backend_manifest_entries(backend)
        file_entries: list[dict[str, Any]] = []
        link_entries: list[dict[str, Any]] = []
        for e in entries:
            rel = e.get("path")
            kind = e.get("kind")
            if not isinstance(rel, str) or not rel or rel.startswith("/"):
                continue
            if _excluded(rel, excludes=ex):
                continue
            if kind == "file":
                file_entries.append(e)
            elif kind == "symlink":
                link_entries.append(e)

        # Download and write files in chunks.
        chunk: list[str] = []
        meta_by_path: dict[str, dict[str, Any]] = {}
        for e in file_entries:
            p = str(e.get("path") or "")
            if p:
                meta_by_path[p] = e

        def _flush() -> None:
            nonlocal chunk
            if not chunk:
                return
            downloads = backend.download_files(["/" + p for p in chunk])
            if not isinstance(downloads, list):
                raise RuntimeError("sandbox download_files returned invalid response")
            if len(downloads) != len(chunk):
                raise RuntimeError("sandbox download_files length mismatch")
            for rel_path, dl in zip(chunk, downloads, strict=False):
                if isinstance(dl, dict):
                    err = dl.get("error")
                    content = dl.get("content")
                else:
                    err = getattr(dl, "error", None) if dl is not None else None
                    content = getattr(dl, "content", None) if dl is not None else None
                if err is not None or content is None:
                    raise RuntimeError(f"download failed for {rel_path}: {err}")
                payload = bytes(content)
                meta = meta_by_path.get(rel_path) or {}
                mode = meta.get("mode")
                out_path = os.path.join(repo_dir, rel_path)
                _write_file(
                    out_path, payload, mode=int(mode) if isinstance(mode, int) else None
                )
            chunk = []

        for e in file_entries:
            rel_path = str(e.get("path") or "")
            if not rel_path:
                continue
            chunk.append(rel_path)
            if len(chunk) >= 200:
                _flush()
        _flush()

        for e in link_entries:
            rel_path = e.get("path")
            target = e.get("link_target")
            if not isinstance(rel_path, str) or not rel_path:
                continue
            if not isinstance(target, str):
                target = ""
            _write_symlink(os.path.join(repo_dir, rel_path), target)

        # Enforce excludes (remove from destination even if previously present).
        _remove_excluded_paths(repo_dir, excludes=ex)

        # Configure author.
        r.run(
            ["git", "config", "user.name", git_commit_author_name()],
            cwd=repo_dir,
            env=env,
            check=True,
        )
        r.run(
            ["git", "config", "user.email", git_commit_author_email()],
            cwd=repo_dir,
            env=env,
            check=True,
        )

        if not _git_dirty(r, repo_dir, env=env):
            if base_sha:
                _write_git_state(
                    backend,
                    {
                        "branch": br,
                        "remote_head_sha": base_sha,
                        "updated_at_unix": int(time.time()),
                        "conflicts": [],
                    },
                )
            return False, None, "", ""

        r.run(["git", "add", "-A"], cwd=repo_dir, env=env, check=True)
        diff_stat = (
            r.run(
                ["git", "diff", "--cached", "--stat"], cwd=repo_dir, env=env, check=True
            ).stdout
            or ""
        )
        name_status = (
            r.run(
                ["git", "diff", "--cached", "--name-status"],
                cwd=repo_dir,
                env=env,
                check=True,
            ).stdout
            or ""
        )

        msg = None
        if commit_message_fn is not None and callable(commit_message_fn):
            msg = str(commit_message_fn(diff_stat, name_status))
        elif commit_message is not None:
            msg = str(commit_message)
        else:
            msg = f"Amicable sync ({project_slug}) {time.strftime('%Y-%m-%d %H:%M:%S')}"

        if not msg.strip() and not allow_empty_commit:
            return False, None, diff_stat, name_status

        if not allow_empty_commit and not _git_dirty(r, repo_dir, env=env):
            return False, None, diff_stat, name_status

        r.run(["git", "commit", "-m", msg], cwd=repo_dir, env=env, check=True)

        # Push with simple rebase retry.
        for _attempt in range(3):
            cp = r.run(
                ["git", "push", "origin", br], cwd=repo_dir, env=env, check=False
            )
            if cp.returncode == 0:
                final_sha = (
                    r.run(
                        ["git", "rev-parse", "HEAD"],
                        cwd=repo_dir,
                        env=env,
                        check=True,
                    ).stdout.strip()
                    or None
                )
                if final_sha:
                    _write_git_state(
                        backend,
                        {
                            "branch": br,
                            "remote_head_sha": final_sha,
                            "updated_at_unix": int(time.time()),
                            "conflicts": [],
                        },
                    )
                return True, final_sha, diff_stat, name_status
            # Best-effort rebase then retry.
            r.run(
                ["git", "pull", "--rebase", "origin", br],
                cwd=repo_dir,
                env=env,
                check=False,
            )

        raise RuntimeError(f"git push failed: {cp.stderr or cp.stdout}")


def bootstrap_repo_if_empty(
    backend: Any,
    *,
    repo_http_url: str,
    project_slug: str,
    commit_message: str,
    branch: str | None = None,
    cache_dir: str | None = None,
    excludes: list[str] | None = None,
    runner: CommandRunner | None = None,
) -> tuple[bool, str | None]:
    """Create a baseline commit if the remote branch doesn't exist yet.

    Returns (bootstrapped, commit_sha).
    """
    token = gitlab_token()
    if not token:
        raise RuntimeError("GITLAB_TOKEN is not set")

    r = runner or SubprocessRunner()
    br = (branch or git_sync_branch()).strip() or "main"

    with _git_auth_env(token=token) as env:
        heads = r.run(
            ["git", "ls-remote", "--heads", repo_http_url, br], env=env, check=True
        )
        if (heads.stdout or "").strip():
            return False, None

    pushed, sha, _ds, _ns = sync_sandbox_tree_to_repo(
        backend,
        repo_http_url=repo_http_url,
        project_slug=project_slug,
        commit_message=commit_message,
        branch=br,
        cache_dir=cache_dir,
        excludes=excludes,
        runner=r,
    )
    return bool(pushed), sha
