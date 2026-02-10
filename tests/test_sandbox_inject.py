from __future__ import annotations

from src.db.sandbox_inject import ensure_nuxt_config_includes_db_script


def test_ensure_nuxt_config_includes_db_script_inserts_head_script():
    src = "export default defineNuxtConfig({})\n"
    out = ensure_nuxt_config_includes_db_script(src)
    assert "/amicable-db.js" in out
