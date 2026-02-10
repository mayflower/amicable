from __future__ import annotations

import os
import re
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterable

from src.projects.store import slugify

_SAFE_KEY_RE = re.compile(r"[^a-zA-Z0-9_.:-]+")


@dataclass(frozen=True)
class ScaffoldContext:
    project_id: str
    template_id: str
    project_name: str
    project_slug: str
    repo_url: str
    branch: str
    sonar_project_key: str
    backstage_owner: str
    backstage_system: str | None
    backstage_lifecycle: str
    backstage_type: str
    tags: tuple[str, ...]


def _env_str(name: str) -> str:
    return str(os.environ.get(name) or "").strip()


def _env_bool(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    v = raw.strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return default


def _normalize_sonar_key(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("/", "_")
    s = _SAFE_KEY_RE.sub("_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def _backstage_type_for(template_id: str) -> str:
    tid = (template_id or "").strip().lower()
    if tid in ("fastapi", "hono"):
        return "service"
    return "website"


def _tags_for(template_id: str) -> tuple[str, ...]:
    tid = (template_id or "").strip().lower()
    if tid == "vite":
        return ("amicable", "react", "vite", "typescript")
    if tid == "nextjs15":
        return ("amicable", "react", "nextjs", "typescript")
    if tid == "remix":
        return ("amicable", "react", "remix", "typescript")
    if tid == "nuxt3":
        return ("amicable", "vue", "nuxt", "typescript")
    if tid == "sveltekit":
        return ("amicable", "svelte", "sveltekit", "typescript")
    if tid == "fastapi":
        return ("amicable", "python", "fastapi")
    if tid == "hono":
        return ("amicable", "typescript", "hono")
    if tid == "laravel":
        return ("amicable", "php", "laravel")
    # Unknown/future templates: keep stable but minimal.
    return ("amicable",)


def _sonar_sources_for(template_id: str) -> str:
    tid = (template_id or "").strip().lower()
    if tid in ("vite", "nextjs15", "sveltekit", "hono"):
        return "src"
    if tid == "remix":
        return "app"
    if tid == "nuxt3":
        return "."
    if tid == "fastapi":
        return "app"
    if tid == "laravel":
        return "app,resources,routes"
    return "."


def build_scaffold_context(
    *,
    project_id: str,
    template_id: str,
    project_name: str | None,
    project_slug: str | None,
    repo_web_url: str | None,
    branch: str | None,
    gitlab_base_url: str | None,
    gitlab_group_path: str | None,
) -> ScaffoldContext:
    pid = str(project_id or "").strip()
    tid = str(template_id or "").strip() or "vite"

    slug = (str(project_slug or "").strip() or slugify(pid)).strip()
    name = (str(project_name or "").strip() or slug or "Untitled").strip()

    br = (str(branch or "").strip() or "main").strip()

    repo_url = (str(repo_web_url or "").strip()).rstrip("/")
    if not repo_url:
        base = (str(gitlab_base_url or "").strip()).rstrip("/")
        group = (str(gitlab_group_path or "").strip()).strip("/")
        if base and group and slug:
            repo_url = f"{base}/{group}/{slug}"
        elif base and slug:
            repo_url = f"{base}/{slug}"
        else:
            repo_url = ""  # allowed (we'll omit source-location when missing)

    owner = _env_str("AMICABLE_BACKSTAGE_OWNER") or "group:platform"
    system = _env_str("AMICABLE_BACKSTAGE_SYSTEM") or ""
    lifecycle = _env_str("AMICABLE_BACKSTAGE_LIFECYCLE") or "experimental"

    sonar_prefix = _env_str("AMICABLE_SONAR_PROJECTKEY_PREFIX") or (
        gitlab_group_path or ""
    )
    sonar_prefix = _normalize_sonar_key(str(sonar_prefix))
    sonar_slug = _normalize_sonar_key(slug)
    sonar_pid = _normalize_sonar_key(pid)
    sonar_project_key = "_".join(
        [p for p in (sonar_prefix, sonar_slug, sonar_pid) if p]
    )
    if not sonar_project_key:
        sonar_project_key = _normalize_sonar_key(pid) or "amicable_project"

    return ScaffoldContext(
        project_id=pid,
        template_id=tid,
        project_name=name,
        project_slug=slug,
        repo_url=repo_url,
        branch=br,
        sonar_project_key=sonar_project_key,
        backstage_owner=owner,
        backstage_system=system or None,
        backstage_lifecycle=lifecycle,
        backstage_type=_backstage_type_for(tid),
        tags=_tags_for(tid),
    )


def render_catalog_info(ctx: ScaffoldContext) -> str:
    # Keep it simple: one Component entity, ready for TechDocs.
    tags = "\n".join([f"    - {t}" for t in ctx.tags]) if ctx.tags else ""

    # Backstage expects a single string annotation value. When repo_url is missing,
    # we omit source-location entirely to avoid emitting invalid URLs.
    annotations: list[str] = [
        "    backstage.io/techdocs-ref: dir:.",
        f"    sonarqube.org/project-key: {ctx.sonar_project_key}",
    ]
    if ctx.repo_url:
        annotations.insert(
            1,
            f"    backstage.io/source-location: url:{ctx.repo_url}/tree/{ctx.branch}/",
        )

    owner_line = f"  owner: {ctx.backstage_owner}"
    system_line = f"  system: {ctx.backstage_system}" if ctx.backstage_system else None
    lifecycle_line = f"  lifecycle: {ctx.backstage_lifecycle}"

    spec_lines = [f"  type: {ctx.backstage_type}", lifecycle_line, owner_line]
    if system_line:
        spec_lines.insert(1, system_line)

    return (
        "apiVersion: backstage.io/v1alpha1\n"
        "kind: Component\n"
        "metadata:\n"
        f"  name: {ctx.project_slug}\n"
        f"  title: {ctx.project_name}\n"
        "  description: Amicable project\n"
        "  annotations:\n" + "\n".join(annotations) + "\n"
        "  tags:\n"
        + (tags + "\n" if tags else "    - amicable\n")
        + "  links:\n"
        + (
            f"    - url: {ctx.repo_url}\n      title: Repository\n      icon: git\n"
            if ctx.repo_url
            else ""
        )
        + "spec:\n"
        + "\n".join(spec_lines)
        + "\n"
    )


def render_sonar_properties(ctx: ScaffoldContext) -> str:
    sources = _sonar_sources_for(ctx.template_id)
    # Based on ../contextmine/sonar-project.properties, kept generic across templates.
    return (
        f"sonar.projectKey={ctx.sonar_project_key}\n"
        "\n"
        "# Source directories\n"
        f"sonar.sources={sources}\n"
        "\n"
        "# Exclusions - vendored code and generated files\n"
        "sonar.exclusions="
        "**/node_modules/**,**/.venv/**,**/venv/**,**/__pycache__/**,"
        "**/dist/**,**/.next/**,**/artifacts/**,**/*.min.js,**/*.min.css,"
        "**/uv.lock,**/pnpm-lock.yaml,**/package-lock.json,**/composer.lock,"
        "**/alembic/versions/**\n"
        "\n"
        "# Test file patterns\n"
        f"sonar.tests={sources}\n"
        "sonar.test.inclusions="
        "**/tests/**,**/test_*.py,**/*.test.ts,**/*.test.tsx,"
        "**/*.spec.ts,**/*.spec.tsx\n"
        "\n"
        "# Python settings\n"
        "sonar.python.version=3.12\n"
        "sonar.python.coverage.reportPaths=coverage.xml\n"
        "\n"
        "# TypeScript/JavaScript settings\n"
        "sonar.typescript.lcov.reportPaths=coverage/lcov.info\n"
        "sonar.javascript.lcov.reportPaths=coverage/lcov.info\n"
    )


def render_mkdocs_yml(ctx: ScaffoldContext) -> str:
    repo_url = ctx.repo_url
    edit_uri = f"edit/{ctx.branch}/docs/" if repo_url else ""

    # Modeled after ../contextmine/mkdocs.yml, but kept minimal and guaranteed to
    # match our starter docs.
    return (
        f"site_name: {ctx.project_name}\n"
        "site_description: Amicable project documentation\n"
        + (f"repo_url: {repo_url}\n" if repo_url else "")
        + (f"edit_uri: {edit_uri}\n" if edit_uri else "")
        + "\n"
        "nav:\n"
        "  - Overview: index.md\n"
        "  - Development Guide: development.md\n"
        "  - Architecture: architecture.md\n"
        "  - Runbook: runbook.md\n"
        "\n"
        "theme:\n"
        "  name: material\n"
        "  features:\n"
        "    - navigation.instant\n"
        "    - navigation.tabs\n"
        "    - navigation.sections\n"
        "    - content.code.copy\n"
        "  palette:\n"
        "    - scheme: default\n"
        "      primary: indigo\n"
        "      accent: indigo\n"
        "      toggle:\n"
        "        icon: material/brightness-7\n"
        "        name: Switch to dark mode\n"
        "    - scheme: slate\n"
        "      primary: indigo\n"
        "      accent: indigo\n"
        "      toggle:\n"
        "        icon: material/brightness-4\n"
        "        name: Switch to light mode\n"
        "\n"
        "markdown_extensions:\n"
        "  - pymdownx.highlight:\n"
        "      anchor_linenums: true\n"
        "  - pymdownx.superfences:\n"
        "      custom_fences:\n"
        "        - name: mermaid\n"
        "          class: mermaid\n"
        "          format: !!python/name:pymdownx.superfences.fence_code_format\n"
        "  - pymdownx.tabbed:\n"
        "      alternate_style: true\n"
        "  - admonition\n"
        "  - pymdownx.details\n"
        "  - tables\n"
        "  - toc:\n"
        "      permalink: true\n"
        "\n"
        "plugins:\n"
        "  - techdocs-core\n"
    )


def _dev_commands_for(template_id: str) -> tuple[str, str]:
    tid = (template_id or "").strip().lower()
    if tid in ("vite", "nextjs15", "remix", "nuxt3", "sveltekit", "hono"):
        return (
            "npm install\nnpm run dev",
            "npm run -s lint\nnpm run -s build",
        )
    if tid == "fastapi":
        return (
            "pip install -r requirements.txt\nuvicorn app.main:app --reload --host 0.0.0.0 --port 3000",
            "python -m compileall -q .\nruff check .\npytest",
        )
    if tid == "laravel":
        return (
            "composer install\nnpm install\nphp artisan serve --host 0.0.0.0 --port 3000",
            "php artisan test",
        )
    return ("<fill in>", "<fill in>")


def render_docs_index(ctx: ScaffoldContext) -> str:
    repo_line = f"- Repository: {ctx.repo_url}\n" if ctx.repo_url else ""
    return (
        f"# {ctx.project_name}\n"
        "\n"
        "This is the TechDocs documentation site for this Amicable project.\n"
        "\n"
        "## Links\n" + repo_line + "\n"
        "## Quick Start\n"
        "See the Development Guide for local and sandbox workflows.\n"
    )


def render_docs_development(ctx: ScaffoldContext) -> str:
    run_cmds, qa_cmds = _dev_commands_for(ctx.template_id)
    return (
        "# Development Guide\n"
        "\n"
        "## Run Locally\n"
        "```bash\n" + run_cmds + "\n```\n"
        "\n"
        "## QA\n"
        "```bash\n" + qa_cmds + "\n```\n"
        "\n"
        "## TechDocs (Local)\n"
        "```bash\n"
        "pip install mkdocs-material mkdocs-techdocs-core pymdown-extensions\n"
        "mkdocs serve\n"
        "```\n"
    )


def render_docs_architecture(_ctx: ScaffoldContext) -> str:
    return (
        "# Architecture\n"
        "\n"
        "## Overview\n"
        "- What does this project do?\n"
        "- What are the main components?\n"
        "\n"
        "## Data Flow\n"
        "- Request/response paths\n"
        "- Background jobs and integrations\n"
        "\n"
        "## Key Decisions\n"
        "- Tradeoffs and rationale\n"
    )


def render_docs_runbook(_ctx: ScaffoldContext) -> str:
    return (
        "# Runbook\n"
        "\n"
        "## Deploy\n"
        "- Steps to deploy\n"
        "- Required environment variables\n"
        "\n"
        "## Rollback\n"
        "- Steps to rollback\n"
        "\n"
        "## Common Issues\n"
        "- Symptoms, causes, and fixes\n"
    )


def render_root_readme(ctx: ScaffoldContext) -> str:
    return (
        f"# {ctx.project_name}\n"
        "\n"
        "This project was created with Amicable.\n"
        "\n"
        "## Documentation\n"
        "- TechDocs: see `mkdocs.yml` and `docs/`\n"
        "- Backstage: see `catalog-info.yaml`\n"
        "- SonarQube: see `sonar-project.properties`\n"
        "\n"
        "## Development\n"
        "See `docs/development.md`.\n"
    )


def render_gitlab_ci_yml(_ctx: ScaffoldContext) -> str:
    # Keep generic; only depends on external CI variables.
    return (
        "stages:\n"
        "  - quality\n"
        "  - docs\n"
        "\n"
        "sonarqube:\n"
        "  stage: quality\n"
        "  image: sonarsource/sonar-scanner-cli:latest\n"
        "  variables:\n"
        '    GIT_DEPTH: "0"\n'
        "  cache:\n"
        "    key: sonar\n"
        "    paths:\n"
        "      - .sonar/cache\n"
        "  script:\n"
        '    - sonar-scanner -Dsonar.host.url="$SONAR_HOST_URL" -Dsonar.token="$SONAR_TOKEN"\n'
        "  rules:\n"
        "    - if: '$SONAR_HOST_URL && $SONAR_TOKEN'\n"
        "\n"
        "techdocs:\n"
        "  stage: docs\n"
        "  image: python:3.12-slim\n"
        "  script:\n"
        "    - pip install mkdocs-material mkdocs-techdocs-core pymdown-extensions\n"
        "    - mkdocs build --strict\n"
        "  artifacts:\n"
        "    when: always\n"
        "    paths:\n"
        "      - site/\n"
        "    expire_in: 1 week\n"
    )


def _dl_item_error(item: Any) -> str | None:
    if item is None:
        return "file_not_found"
    if isinstance(item, dict):
        err = item.get("error")
        return str(err) if isinstance(err, str) and err else None
    err = getattr(item, "error", None)
    return str(err) if isinstance(err, str) and err else None


def _dl_item_content(item: Any) -> bytes | None:
    if item is None:
        return None
    if isinstance(item, dict):
        c = item.get("content")
        return bytes(c) if c is not None else None
    c = getattr(item, "content", None)
    return bytes(c) if c is not None else None


def _file_exists(backend: Any, path: str) -> bool:
    try:
        out = backend.download_files([path])
    except Exception:
        return True  # conservative: don't overwrite if unsure
    if not isinstance(out, list) or not out:
        return True
    item = out[0]
    err = _dl_item_error(item)
    if err == "file_not_found":
        return False
    # If we can read state at all, treat it as existing unless explicitly missing.
    if err is None:
        return True
    content = _dl_item_content(item)
    return content is not None


def _upload_missing_files(backend: Any, files: Iterable[tuple[str, bytes]]) -> None:
    batch: list[tuple[str, bytes]] = []
    for path, payload in files:
        if _file_exists(backend, path):
            continue
        batch.append((path, payload))
    if not batch:
        return
    try:
        backend.upload_files(batch)
    except Exception:
        # Best-effort: scaffolding should never break init.
        return


def ensure_platform_scaffold(
    backend: Any,
    *,
    project_id: str,
    template_id: str,
    project_name: str | None,
    project_slug: str | None,
    repo_web_url: str | None,
    branch: str,
    gitlab_base_url: str | None,
    gitlab_group_path: str | None,
    create_ci: bool,
) -> None:
    ctx = build_scaffold_context(
        project_id=project_id,
        template_id=template_id,
        project_name=project_name,
        project_slug=project_slug,
        repo_web_url=repo_web_url,
        branch=branch,
        gitlab_base_url=gitlab_base_url,
        gitlab_group_path=gitlab_group_path,
    )

    # Ensure parents exist. upload_files() requires the parent dir to exist.
    with suppress(Exception):
        backend.execute("cd /app && mkdir -p docs")

    files: list[tuple[str, bytes]] = [
        ("/catalog-info.yaml", render_catalog_info(ctx).encode("utf-8")),
        ("/sonar-project.properties", render_sonar_properties(ctx).encode("utf-8")),
        ("/mkdocs.yml", render_mkdocs_yml(ctx).encode("utf-8")),
        ("/docs/index.md", render_docs_index(ctx).encode("utf-8")),
        ("/docs/development.md", render_docs_development(ctx).encode("utf-8")),
        ("/docs/architecture.md", render_docs_architecture(ctx).encode("utf-8")),
        ("/docs/runbook.md", render_docs_runbook(ctx).encode("utf-8")),
        ("/README.md", render_root_readme(ctx).encode("utf-8")),
    ]
    if create_ci:
        files.append(("/.gitlab-ci.yml", render_gitlab_ci_yml(ctx).encode("utf-8")))

    _upload_missing_files(backend, files)


def scaffold_on_existing_enabled() -> bool:
    return _env_bool("AMICABLE_PLATFORM_SCAFFOLD_ON_EXISTING", default=False)
