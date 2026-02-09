from __future__ import annotations

import json
import re
from typing import Any

# NOTE: Vite dev server treats `/<name>.js` requests as source modules before public assets.
# Writing to `/amicable-db.js` (workspace root) ensures it is served correctly.
_VITE_DB_JS_PATH = "/amicable-db.js"
_PUBLIC_DB_JS_PATH = "/public/amicable-db.js"
_VITE_INDEX_HTML_PATH = "/index.html"
_SVELTEKIT_APP_HTML_PATH = "/src/app.html"
_NUXT_CONFIG_TS_PATHS = ("/nuxt.config.ts",)
_LARAVEL_WELCOME_BLADE_PATHS = ("/resources/views/welcome.blade.php",)
_NEXT_LAYOUT_PATHS = ("/app/layout.tsx", "/src/app/layout.tsx")
_REMIX_ROOT_PATHS = ("/app/root.tsx",)


def render_db_js(*, app_id: str, graphql_url: str, app_key: str, preview_origin: str) -> str:
    payload = {
        "appId": app_id,
        "graphqlUrl": graphql_url,
        "appKey": app_key,
        "previewOrigin": preview_origin,
    }
    # JSON is safe to parse back out; browser can read window.__AMICABLE_DB__.
    return f"window.__AMICABLE_DB__ = {json.dumps(payload, separators=(',', ':'), sort_keys=True)};\n"


def parse_db_js(text: str) -> dict[str, Any] | None:
    if not isinstance(text, str) or "__AMICABLE_DB__" not in text:
        return None
    # Expect: window.__AMICABLE_DB__ = {...};
    m = re.search(r"__AMICABLE_DB__\s*=\s*({.*?})\s*;", text, flags=re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(1))
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def ensure_index_includes_db_script(index_html: str) -> str:
    if not isinstance(index_html, str):
        return index_html
    if "/amicable-db.js" in index_html:
        return index_html
    tag = '  <script src="/amicable-db.js"></script>\n'
    if "</head>" in index_html:
        return index_html.replace("</head>", f"{tag}</head>", 1)
    return index_html + "\n" + tag


def ensure_next_layout_includes_db_script(layout_tsx: str) -> str:
    if not isinstance(layout_tsx, str):
        return layout_tsx
    if "/amicable-db.js" in layout_tsx:
        return layout_tsx

    # Prefer injecting into <head> if present; otherwise insert a <head> block
    # right after the opening <html ...> tag.
    tag = '        <script src="/amicable-db.js"></script>\n'
    if "<head>" in layout_tsx:
        return layout_tsx.replace("<head>", "<head>\n" + tag, 1)
    if "</head>" in layout_tsx:
        return layout_tsx.replace("</head>", tag + "      </head>", 1)

    m = re.search(r"<html[^>]*>", layout_tsx)
    if m:
        head = "      <head>\n" + tag + "      </head>\n"
        return layout_tsx[: m.end()] + "\n" + head + layout_tsx[m.end() :]

    # Fallback: insert before <body> or at the top of the file.
    if "<body" in layout_tsx:
        return layout_tsx.replace("<body", tag + "      <body", 1)
    return tag + layout_tsx


def ensure_remix_root_includes_db_script(root_tsx: str) -> str:
    if not isinstance(root_tsx, str):
        return root_tsx
    if "/amicable-db.js" in root_tsx:
        return root_tsx

    # Inject before <Scripts /> when possible.
    tag = '      <script src="/amicable-db.js"></script>\n'
    if "<Scripts" in root_tsx:
        return root_tsx.replace("<Scripts", tag + "      <Scripts", 1)
    if "</head>" in root_tsx:
        return root_tsx.replace("</head>", tag + "    </head>", 1)
    return root_tsx + "\n" + tag


def ensure_sveltekit_app_html_includes_db_script(app_html: str) -> str:
    if not isinstance(app_html, str):
        return app_html
    if "/amicable-db.js" in app_html:
        return app_html
    tag = '  <script src="/amicable-db.js"></script>\n'
    if "</head>" in app_html:
        return app_html.replace("</head>", f"{tag}</head>", 1)
    return app_html + "\n" + tag


def ensure_nuxt_config_includes_db_script(nuxt_config_ts: str) -> str:
    if not isinstance(nuxt_config_ts, str):
        return nuxt_config_ts
    if "/amicable-db.js" in nuxt_config_ts:
        return nuxt_config_ts

    # Minimal, idempotent insert: add app.head.script entry.
    # Prefer inserting inside defineNuxtConfig({...}).
    m = re.search(r"defineNuxtConfig\\(\\s*\\{", nuxt_config_ts)
    if not m:
        return nuxt_config_ts + '\n\nexport default defineNuxtConfig({ app: { head: { script: [{ src: "/amicable-db.js" }] } } });\n'

    insert = (
        "\n  app: {\n"
        "    head: {\n"
        '      script: [{ src: "/amicable-db.js" }],\n'
        "    },\n"
        "  },"
    )
    # If config already has an `app:` section, try to insert into its `head`.
    if re.search(r"\\bapp\\s*:\\s*\\{", nuxt_config_ts):
        # Insert a head.script if missing (simple heuristic).
        if re.search(r"\\bhead\\s*:\\s*\\{", nuxt_config_ts):
            # Insert script array after head: {
            return re.sub(
                r"(\\bhead\\s*:\\s*\\{)",
                r"\\1\\n      script: [{ src: \"/amicable-db.js\" }],",
                nuxt_config_ts,
                count=1,
            )
        return re.sub(
            r"(\\bapp\\s*:\\s*\\{)",
            r"\\1\\n    head: { script: [{ src: \"/amicable-db.js\" }] },",
            nuxt_config_ts,
            count=1,
        )

    # No app section: insert one near the top of the object literal.
    return nuxt_config_ts[: m.end()] + insert + nuxt_config_ts[m.end() :]


def ensure_laravel_welcome_includes_db_script(welcome_blade: str) -> str:
    if not isinstance(welcome_blade, str):
        return welcome_blade
    if "/amicable-db.js" in welcome_blade:
        return welcome_blade
    tag = '    <script src="/amicable-db.js"></script>\n'
    if "</head>" in welcome_blade:
        return welcome_blade.replace("</head>", f"{tag}</head>", 1)
    return welcome_blade + "\n" + tag


def vite_db_paths() -> tuple[str, str]:
    return (_VITE_DB_JS_PATH, _VITE_INDEX_HTML_PATH)


def next_db_paths() -> tuple[str, tuple[str, ...]]:
    return (_PUBLIC_DB_JS_PATH, _NEXT_LAYOUT_PATHS)


def remix_db_paths() -> tuple[str, tuple[str, ...]]:
    return (_PUBLIC_DB_JS_PATH, _REMIX_ROOT_PATHS)


def sveltekit_db_paths() -> tuple[str, str]:
    # SvelteKit serves static files from /static at /. We write to /static so it
    # is available at /amicable-db.js, then inject a <script> in app.html.
    return ("/static/amicable-db.js", _SVELTEKIT_APP_HTML_PATH)


def nuxt_db_paths() -> tuple[str, tuple[str, ...]]:
    # Nuxt serves /public at /. Use public so it works regardless of server routing.
    return (_PUBLIC_DB_JS_PATH, _NUXT_CONFIG_TS_PATHS)


def laravel_db_paths() -> tuple[str, tuple[str, ...]]:
    return (_PUBLIC_DB_JS_PATH, _LARAVEL_WELCOME_BLADE_PATHS)
