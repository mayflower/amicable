from __future__ import annotations

from src.db.sandbox_inject import (
    ensure_nuxt_config_includes_db_script,
    render_runtime_js,
)


def test_ensure_nuxt_config_includes_db_script_inserts_head_script():
    src = "export default defineNuxtConfig({})\n"
    out = ensure_nuxt_config_includes_db_script(src)
    assert "/amicable-db.js" in out
    assert "/amicable-runtime.js" in out


def test_ensure_nuxt_config_includes_db_script_is_idempotent():
    src = "export default defineNuxtConfig({})\n"
    once = ensure_nuxt_config_includes_db_script(src)
    twice = ensure_nuxt_config_includes_db_script(once)
    assert twice.count("/amicable-db.js") == once.count("/amicable-db.js")
    assert twice.count("/amicable-runtime.js") == once.count("/amicable-runtime.js")


def test_render_runtime_js_includes_console_error_hook_and_probe_ack():
    js = render_runtime_js()
    assert "window.console.error=function(){" in js
    assert "console_error" in js
    assert "amicable_runtime_probe_ack" in js


def test_render_runtime_js_includes_parent_origin_fallbacks():
    js = render_runtime_js()
    assert "amicableParentOrigin" in js
    assert "__amicable_parent_origin" in js
    assert "document.referrer" in js
