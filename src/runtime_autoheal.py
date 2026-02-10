from __future__ import annotations

import time
from dataclasses import dataclass, field


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class RuntimeAutoHealConfig:
    enabled: bool = True
    cooldown_s: int = 30
    dedupe_window_s: int = 600  # 10 minutes
    max_attempts_per_fingerprint: int = 2


@dataclass
class _FingerprintState:
    last_handled_ms: int
    attempts: int


@dataclass
class RuntimeAutoHealState:
    last_autoheal_ms: int = 0
    by_fingerprint: dict[str, _FingerprintState] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeAutoHealDecision:
    allowed: bool
    reason: str | None = None
    attempts: int | None = None


def decide_runtime_auto_heal(
    *,
    state: RuntimeAutoHealState,
    fingerprint: str,
    cfg: RuntimeAutoHealConfig,
    now_ms: int | None = None,
) -> RuntimeAutoHealDecision:
    """Pure decision helper.

    This does not mutate `state`. Call `apply_runtime_auto_heal_decision(...)` after an
    allowed decision is acted upon (i.e., once you actually start a run).
    """
    if not cfg.enabled:
        return RuntimeAutoHealDecision(allowed=False, reason="disabled")

    fp = (fingerprint or "").strip()
    if not fp:
        return RuntimeAutoHealDecision(allowed=False, reason="missing_fingerprint")

    now = _now_ms() if now_ms is None else int(now_ms)

    # Global cooldown (per session).
    if state.last_autoheal_ms and now - state.last_autoheal_ms < cfg.cooldown_s * 1000:
        return RuntimeAutoHealDecision(allowed=False, reason="cooldown")

    rec = state.by_fingerprint.get(fp)
    if rec is not None:
        if now - int(rec.last_handled_ms) < cfg.dedupe_window_s * 1000:
            return RuntimeAutoHealDecision(
                allowed=False, reason="dedupe", attempts=int(rec.attempts)
            )
        if int(rec.attempts) >= int(cfg.max_attempts_per_fingerprint):
            return RuntimeAutoHealDecision(
                allowed=False, reason="max_attempts", attempts=int(rec.attempts)
            )

    # Allowed.
    attempts = 1 if rec is None else int(rec.attempts) + 1
    return RuntimeAutoHealDecision(allowed=True, reason=None, attempts=attempts)


def apply_runtime_auto_heal_decision(
    *,
    state: RuntimeAutoHealState,
    fingerprint: str,
    attempts: int | None,
    now_ms: int | None = None,
    max_fingerprints: int = 300,
) -> RuntimeAutoHealState:
    """Apply the decision result by returning an updated state.

    Intended to be called only when an auto-heal run actually starts.
    """
    fp = (fingerprint or "").strip()
    if not fp:
        return state

    now = _now_ms() if now_ms is None else int(now_ms)
    next_state = RuntimeAutoHealState(
        last_autoheal_ms=now,
        by_fingerprint=dict(state.by_fingerprint),
    )
    prev = next_state.by_fingerprint.get(fp)
    next_state.by_fingerprint[fp] = _FingerprintState(
        last_handled_ms=now,
        attempts=int(attempts or (prev.attempts + 1 if prev else 1)),
    )

    # Bound memory: drop oldest if we exceed max_fingerprints.
    if len(next_state.by_fingerprint) > max_fingerprints:
        items = sorted(next_state.by_fingerprint.items(), key=lambda kv: kv[1].last_handled_ms)
        for k, _ in items[: max(0, len(items) - max_fingerprints)]:
            next_state.by_fingerprint.pop(k, None)

    return next_state

