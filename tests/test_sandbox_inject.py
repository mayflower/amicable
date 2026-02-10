from __future__ import annotations

from src.db.sandbox_inject import ensure_nuxt_config_includes_db_script


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
