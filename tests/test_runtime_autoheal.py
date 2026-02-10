from __future__ import annotations

from src.runtime_autoheal import (
    RuntimeAutoHealConfig,
    RuntimeAutoHealState,
    apply_runtime_auto_heal_decision,
    decide_runtime_auto_heal,
)


def test_first_error_allowed():
    cfg = RuntimeAutoHealConfig(enabled=True, cooldown_s=30, dedupe_window_s=600, max_attempts_per_fingerprint=2)
    st = RuntimeAutoHealState()
    d = decide_runtime_auto_heal(state=st, fingerprint="fp1", cfg=cfg, now_ms=1_000)
    assert d.allowed is True
    assert d.attempts == 1


def test_cooldown_blocks_even_for_new_fingerprint():
    cfg = RuntimeAutoHealConfig(enabled=True, cooldown_s=30, dedupe_window_s=600, max_attempts_per_fingerprint=2)
    st = RuntimeAutoHealState(last_autoheal_ms=1_000)
    d = decide_runtime_auto_heal(state=st, fingerprint="fp2", cfg=cfg, now_ms=1_000 + 5_000)
    assert d.allowed is False
    assert d.reason == "cooldown"


def test_dedupe_blocks_same_fingerprint_within_window():
    cfg = RuntimeAutoHealConfig(enabled=True, cooldown_s=0, dedupe_window_s=600, max_attempts_per_fingerprint=2)
    st = RuntimeAutoHealState()
    st = apply_runtime_auto_heal_decision(state=st, fingerprint="fp1", attempts=1, now_ms=10_000)
    d = decide_runtime_auto_heal(state=st, fingerprint="fp1", cfg=cfg, now_ms=10_000 + 1_000)
    assert d.allowed is False
    assert d.reason == "dedupe"


def test_max_attempts_blocks_after_limit():
    cfg = RuntimeAutoHealConfig(enabled=True, cooldown_s=0, dedupe_window_s=0, max_attempts_per_fingerprint=2)
    st = RuntimeAutoHealState()
    st = apply_runtime_auto_heal_decision(state=st, fingerprint="fp1", attempts=1, now_ms=1_000)
    st = apply_runtime_auto_heal_decision(state=st, fingerprint="fp1", attempts=2, now_ms=2_000)
    d = decide_runtime_auto_heal(state=st, fingerprint="fp1", cfg=cfg, now_ms=3_000)
    assert d.allowed is False
    assert d.reason == "max_attempts"

