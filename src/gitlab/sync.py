from __future__ import annotations

import glob
import io
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from typing import Any, Protocol

from src.gitlab.config import (
    git_commit_author_email,
    git_commit_author_name,
    git_sync_branch,
    git_sync_cache_dir,
    git_sync_excludes,
    gitlab_token,
)


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


def _sanitize_dir_name(name: str) -> str:
    s = (name or "").strip().lower()
    s = re.sub(r"[^a-z0-9_.-]+", "-", s)
    s = s.strip("-.")
    return s or "project"


def _build_tar_command(*, out_name: str, excludes: list[str]) -> str:
    # Run from /app inside the sandbox.
    parts = ["tar", "-czf", out_name]
    for ex in excludes:
        ex = (ex or "").strip()
        if not ex:
            continue
        ex = ex.rstrip("/")
        # Use patterns relative to /app.
        parts.append(f"--exclude=./{ex}")
    parts.append(".")
    return " ".join(parts)


def export_sandbox_snapshot(backend: Any, *, excludes: list[str] | None = None) -> bytes:
    """Create a tar.gz snapshot in the sandbox, download it, delete it."""
    ex = excludes or git_sync_excludes()
    out_name = ".amicable_snapshot.tgz"

    res = backend.execute(_build_tar_command(out_name=out_name, excludes=ex))
    if getattr(res, "exit_code", 1) != 0:
        raise RuntimeError(f"Snapshot tar failed: {getattr(res, 'output', '')}")

    downloads = backend.download_files([f"/{out_name}"])
    if not downloads or downloads[0].error is not None or downloads[0].content is None:
        raise RuntimeError(f"Snapshot download failed: {downloads[0].error if downloads else 'unknown'}")

    backend.execute(f"rm -f {out_name}")
    return bytes(downloads[0].content)


def _safe_extract_tgz(payload: bytes, *, dest_dir: str) -> None:
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as tf:
        for m in tf.getmembers():
            name = m.name
            if name.startswith("/"):
                raise ValueError("tar contains absolute path")
            if ".." in name.split("/"):
                raise ValueError("tar contains parent traversal")
        tf.extractall(dest_dir)


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


def sync_snapshot_to_repo(
    snapshot_tgz: bytes,
    *,
    repo_http_url: str,
    project_slug: str,
    branch: str | None = None,
    cache_dir: str | None = None,
    excludes: list[str] | None = None,
    runner: CommandRunner | None = None,
) -> tuple[bool, str | None]:
    """Sync sandbox snapshot into a cached clone, commit, and push.

    Returns (pushed, commit_sha).
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

        heads = r.run(["git", "ls-remote", "--heads", "origin", br], cwd=repo_dir, env=env, check=True)
        if (heads.stdout or "").strip():
            r.run(["git", "checkout", "-B", br, f"origin/{br}"], cwd=repo_dir, env=env, check=True)
        else:
            # New/empty repo: create orphan branch.
            r.run(["git", "checkout", "--orphan", br], cwd=repo_dir, env=env, check=True)
            # Clear index and working tree (except .git).
            r.run(["git", "rm", "-rf", "."], cwd=repo_dir, env=env, check=False)

        # Extract to temp dir.
        with tempfile.TemporaryDirectory(prefix="amicable-snap-") as tmp:
            _safe_extract_tgz(snapshot_tgz, dest_dir=tmp)

            # Snapshot tar is created from /app with '.' root; normalize.
            src_root = tmp
            dot = os.path.join(tmp, ".")
            if os.path.isdir(dot):
                src_root = dot

            if _rsync_available():
                args = ["rsync", "-a", "--delete"]
                # Ensure we never overwrite git metadata.
                args.append("--exclude=.git/")
                args.extend([src_root + "/", repo_dir + "/"])
                r.run(args, env=env, check=True)
            else:
                _sync_tree_fallback(src_root, repo_dir)

            # Enforce excludes (remove from destination even if previously present).
            _remove_excluded_paths(repo_dir, excludes=ex)

        # Configure author.
        r.run(["git", "config", "user.name", git_commit_author_name()], cwd=repo_dir, env=env, check=True)
        r.run(["git", "config", "user.email", git_commit_author_email()], cwd=repo_dir, env=env, check=True)

        if not _git_dirty(r, repo_dir, env=env):
            return False, None

        r.run(["git", "add", "-A"], cwd=repo_dir, env=env, check=True)
        msg = f"Amicable snapshot ({project_slug}) {time.strftime('%Y-%m-%d %H:%M:%S')}"
        r.run(["git", "commit", "-m", msg], cwd=repo_dir, env=env, check=True)

        sha = r.run(["git", "rev-parse", "HEAD"], cwd=repo_dir, env=env, check=True).stdout.strip() or None

        # Push with simple rebase retry.
        for _attempt in range(3):
            cp = r.run(["git", "push", "origin", br], cwd=repo_dir, env=env, check=False)
            if cp.returncode == 0:
                return True, sha
            # Best-effort rebase then retry.
            r.run(["git", "pull", "--rebase", "origin", br], cwd=repo_dir, env=env, check=False)

        raise RuntimeError(f"git push failed: {cp.stderr or cp.stdout}")
