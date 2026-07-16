"""Observable health of the offline NLP tiers (MiniLM bi-encoder +
cross-encoder).

Both tiers self-degrade to TF-IDF / bi-encoder-only on any load failure so the
"NLP layer never raises" contract holds. That degrade is correct for
resilience, but it was previously SILENT at runtime (loud only at image-build
time) — so a production image that shipped WITHOUT the baked model would quietly
serve the whole corpus on TF-IDF with no signal (2026-07-14 resilience audit,
HIGH).

This module makes the degrade observable and, when the operator asks for it,
fatal:

  * ``tier_status()`` — a dict a /health endpoint or the derive preflight can
    surface; ``degraded`` is True when a tier is down for an UNEXPECTED reason
    (a load failure), never merely because it was disabled by env.
  * ``require_semantic_tier()`` — when ``DMA_REQUIRE_SEMANTIC=1`` (production),
    a missing/broken baked model raises ``SemanticTierUnavailable`` at startup
    instead of silently degrading. A deliberate ``DMA_DISABLE_SEMANTIC=1`` is
    still honoured (explicit opt-out is not a failure).

The status accessors force the (lazy, once-per-process) model load, so calling
them at startup is also the cheapest way to warm the tier and emit the one-time
alarm log early rather than on the first derive call.
"""
from __future__ import annotations

import os

from app.services.nlp import rerank, semantic


class SemanticTierUnavailable(RuntimeError):
    """Raised by ``require_semantic_tier`` when the semantic tier is required
    (``DMA_REQUIRE_SEMANTIC=1``) but the baked model could not be loaded."""


def tier_status() -> dict:
    """Health of both offline tiers. ``degraded`` flags an UNEXPECTED outage
    (load failure) — an env opt-out (``disabled_by_env``) is not degraded."""
    sem_reason = semantic.degrade_reason()
    ce_reason = rerank.degrade_reason()
    sem_failed = bool(sem_reason and sem_reason.startswith("load_failed"))
    ce_failed = bool(ce_reason and ce_reason.startswith("load_failed"))
    return {
        "semantic_minilm": {
            "available": semantic.model_available(),
            "reason": sem_reason,
            "model_src": semantic.model_src(),
        },
        "cross_encoder": {
            "available": rerank.available(),
            "reason": ce_reason,
            "model_src": rerank.ce_src(),
        },
        # The cross-encoder can be off while the bi-encoder is up (precision-only
        # loss); the HARD alarm is the bi-encoder failing to load.
        "degraded": sem_failed or ce_failed,
        "hard_degraded": sem_failed,
        "required": os.environ.get("DMA_REQUIRE_SEMANTIC") == "1",
    }


def require_semantic_tier() -> None:
    """Fail-loud preflight for production. No-op unless ``DMA_REQUIRE_SEMANTIC=1``.

    Raises ``SemanticTierUnavailable`` when the bi-encoder could not be loaded
    for an unexpected reason (missing/broken baked model). A deliberate
    ``DMA_DISABLE_SEMANTIC=1`` opt-out is honoured and never raises.
    """
    if os.environ.get("DMA_REQUIRE_SEMANTIC") != "1":
        return
    if os.environ.get("DMA_DISABLE_SEMANTIC") == "1":
        return
    # Heal-then-check: force one fresh load attempt (resets the retry cooldown)
    # before deciding to fail — a transient failure shouldn't down the preflight.
    semantic.force_reload()
    reason = semantic.degrade_reason()
    if reason and reason.startswith("load_failed"):
        raise SemanticTierUnavailable(
            f"DMA_REQUIRE_SEMANTIC=1 but the MiniLM semantic tier could not "
            f"load ({reason}); refusing to serve the corpus on TF-IDF. "
            f"model_src={semantic.model_src()}")
