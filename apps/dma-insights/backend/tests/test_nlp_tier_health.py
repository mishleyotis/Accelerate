"""A1 (2026-07-14 resilience audit): the offline NLP tiers self-degrade to
TF-IDF, but that degrade must be OBSERVABLE and, in prod, fail-loud —
not silent."""
from __future__ import annotations

import pytest

from app.services.nlp import rerank, semantic
from app.services.nlp.tier_health import (
    SemanticTierUnavailable,
    require_semantic_tier,
    tier_status,
)


def _patch(monkeypatch, *, sem_reason, sem_avail, ce_reason, ce_avail):
    monkeypatch.setattr(semantic, "degrade_reason", lambda: sem_reason)
    monkeypatch.setattr(semantic, "model_available", lambda: sem_avail)
    monkeypatch.setattr(rerank, "degrade_reason", lambda: ce_reason)
    monkeypatch.setattr(rerank, "available", lambda: ce_avail)


def test_status_disabled_is_not_degraded(monkeypatch):
    _patch(monkeypatch, sem_reason="disabled_by_env", sem_avail=False,
           ce_reason="disabled_by_env", ce_avail=False)
    st = tier_status()
    assert st["semantic_minilm"]["available"] is False
    assert st["degraded"] is False          # explicit opt-out is NOT an alarm
    assert st["hard_degraded"] is False


def test_status_load_failure_is_degraded(monkeypatch):
    _patch(monkeypatch, sem_reason="load_failed: OSError: no baked model",
           sem_avail=False, ce_reason=None, ce_avail=True)
    st = tier_status()
    assert st["degraded"] is True           # a load failure IS an alarm
    assert st["hard_degraded"] is True      # bi-encoder down = hard


def test_status_cross_encoder_only_degrade_is_soft(monkeypatch):
    _patch(monkeypatch, sem_reason=None, sem_avail=True,
           ce_reason="load_failed: OSError", ce_avail=False)
    st = tier_status()
    assert st["degraded"] is True
    assert st["hard_degraded"] is False     # bi-encoder up → precision-only loss


def test_require_noop_when_not_required(monkeypatch):
    monkeypatch.delenv("DMA_REQUIRE_SEMANTIC", raising=False)
    _patch(monkeypatch, sem_reason="load_failed: x", sem_avail=False,
           ce_reason=None, ce_avail=True)
    require_semantic_tier()                 # must not raise


def test_require_honours_explicit_disable(monkeypatch):
    monkeypatch.setenv("DMA_REQUIRE_SEMANTIC", "1")
    monkeypatch.setenv("DMA_DISABLE_SEMANTIC", "1")
    _patch(monkeypatch, sem_reason="disabled_by_env", sem_avail=False,
           ce_reason="disabled_by_env", ce_avail=False)
    require_semantic_tier()                 # deliberate opt-out ≠ failure


def test_require_raises_on_missing_model_in_prod(monkeypatch):
    monkeypatch.setenv("DMA_REQUIRE_SEMANTIC", "1")
    monkeypatch.delenv("DMA_DISABLE_SEMANTIC", raising=False)
    monkeypatch.setattr(semantic, "force_reload", lambda: None)
    _patch(monkeypatch, sem_reason="load_failed: OSError: /install/st-minilm missing",
           sem_avail=False, ce_reason=None, ce_avail=True)
    with pytest.raises(SemanticTierUnavailable):
        require_semantic_tier()


# ── self-heal: a transient load failure recovers on a later call ──────────────

def test_semantic_transient_failure_then_recovers(monkeypatch):
    monkeypatch.delenv("DMA_DISABLE_SEMANTIC", raising=False)
    monkeypatch.setenv("DMA_SEMANTIC_RETRY_COOLDOWN_SEC", "0")   # retry every call
    semantic._reset_load_state()
    calls = {"n": 0}

    def flaky(_src):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("transient")
        return object()                     # heals on the 2nd attempt

    monkeypatch.setattr(semantic, "_construct_model", flaky)
    assert semantic.model_available() is False       # attempt 1 fails
    assert semantic.model_available() is True         # cooldown=0 → attempt 2 heals
    assert semantic.degrade_reason() is None
    assert calls["n"] == 2
    semantic._reset_load_state()


def test_semantic_cooldown_blocks_then_force_reload_heals(monkeypatch):
    monkeypatch.delenv("DMA_DISABLE_SEMANTIC", raising=False)
    monkeypatch.setenv("DMA_SEMANTIC_RETRY_COOLDOWN_SEC", "99999")  # long cooldown
    semantic._reset_load_state()
    state = {"ok": False}
    monkeypatch.setattr(
        semantic, "_construct_model",
        lambda _src: object() if state["ok"] else (_ for _ in ()).throw(OSError("x")))
    assert semantic.model_available() is False       # attempt 1 fails
    state["ok"] = True
    assert semantic.model_available() is False       # within cooldown → NOT retried
    assert semantic.force_reload() is not None       # force → heals immediately
    assert semantic.model_available() is True
    semantic._reset_load_state()


def test_semantic_stops_after_max_attempts(monkeypatch):
    monkeypatch.delenv("DMA_DISABLE_SEMANTIC", raising=False)
    monkeypatch.setenv("DMA_SEMANTIC_RETRY_COOLDOWN_SEC", "0")
    monkeypatch.setenv("DMA_SEMANTIC_MAX_LOAD_ATTEMPTS", "2")
    semantic._reset_load_state()
    tries = {"n": 0}

    def always_fail(_src):
        tries["n"] += 1
        raise OSError("still missing")

    monkeypatch.setattr(semantic, "_construct_model", always_fail)
    for _ in range(5):
        semantic.model_available()
    assert tries["n"] == 2                 # capped — no hammering past max attempts
    semantic._reset_load_state()
