from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Literal

TemplateId = Literal[
    "lovable_vite",
    "nextjs15",
    "fastapi",
    "hono",
    "remix",
    "nuxt3",
    "sveltekit",
    "laravel",
]

DEFAULT_TEMPLATE_ID: TemplateId = "lovable_vite"


@dataclass(frozen=True)
class TemplateSpec:
    template_id: TemplateId
    label: str
    k8s_sandbox_template_name: str
    # DB injection target. "none" means: only write the JS file, do not try to
    # patch HTML/TSX entrypoints.
    db_inject_kind: Literal[
        "vite_index_html",
        "next_layout_tsx",
        "remix_root_tsx",
        "nuxt_config_ts",
        "sveltekit_app_html",
        "laravel_blade",
        "none",
    ]


_DEFAULT_SPECS: dict[TemplateId, TemplateSpec] = {
    "lovable_vite": TemplateSpec(
        template_id="lovable_vite",
        label="Single-Page App (React + Vite)",
        k8s_sandbox_template_name="amicable-sandbox-lovable-vite",
        db_inject_kind="vite_index_html",
    ),
    "nextjs15": TemplateSpec(
        template_id="nextjs15",
        label="Full-Stack Web App (Next.js 15)",
        k8s_sandbox_template_name="amicable-sandbox-nextjs15",
        db_inject_kind="next_layout_tsx",
    ),
    "fastapi": TemplateSpec(
        template_id="fastapi",
        label="Python API (FastAPI)",
        k8s_sandbox_template_name="amicable-sandbox-fastapi",
        db_inject_kind="none",
    ),
    "hono": TemplateSpec(
        template_id="hono",
        label="Lightweight API (Hono)",
        k8s_sandbox_template_name="amicable-sandbox-hono",
        db_inject_kind="none",
    ),
    "remix": TemplateSpec(
        template_id="remix",
        label="Multi-Page App (React Router)",
        k8s_sandbox_template_name="amicable-sandbox-remix",
        db_inject_kind="remix_root_tsx",
    ),
    "nuxt3": TemplateSpec(
        template_id="nuxt3",
        label="Full-Stack Web App (Nuxt 3)",
        k8s_sandbox_template_name="amicable-sandbox-nuxt3",
        db_inject_kind="nuxt_config_ts",
    ),
    "sveltekit": TemplateSpec(
        template_id="sveltekit",
        label="Full-Stack Web App (SvelteKit)",
        k8s_sandbox_template_name="amicable-sandbox-sveltekit",
        db_inject_kind="sveltekit_app_html",
    ),
    "laravel": TemplateSpec(
        template_id="laravel",
        label="Full-Stack Web App (Laravel)",
        k8s_sandbox_template_name="amicable-sandbox-laravel",
        db_inject_kind="laravel_blade",
    ),
}


def parse_template_id(raw: Any) -> TemplateId | None:
    v = str(raw or "").strip()
    if v in _DEFAULT_SPECS:
        return v  # type: ignore[return-value]
    return None


def default_template_id() -> TemplateId:
    return DEFAULT_TEMPLATE_ID


def template_spec(template_id: str | None) -> TemplateSpec:
    tid = parse_template_id(template_id) or DEFAULT_TEMPLATE_ID
    return _DEFAULT_SPECS[tid]


def k8s_template_name_for(template_id: str | None) -> str:
    """Return the K8s SandboxTemplate name for a template id.

    Can be overridden by AMICABLE_TEMPLATE_K8S_TEMPLATE_MAP_JSON (JSON object).
    """
    spec = template_spec(template_id)

    raw = (os.environ.get("AMICABLE_TEMPLATE_K8S_TEMPLATE_MAP_JSON") or "").strip()
    if not raw:
        return spec.k8s_sandbox_template_name

    try:
        overrides = json.loads(raw)
    except Exception:
        return spec.k8s_sandbox_template_name
    if not isinstance(overrides, dict):
        return spec.k8s_sandbox_template_name

    v = overrides.get(spec.template_id)
    return str(v).strip() if isinstance(v, str) and v.strip() else spec.k8s_sandbox_template_name
