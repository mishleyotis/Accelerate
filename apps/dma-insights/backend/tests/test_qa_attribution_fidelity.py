"""qa_attribution_fidelity — the gate that makes CI OBSERVE the AI layer.

Pure-logic + tier-aware: the DB-backed fidelity pass is exercised in qa-gates
against the seeded corpus; here we pin the module contract (DATABASE_URL guard,
the fused signal, and — only when the cross-encoder tier is actually baked — the
calibration probe's discrimination). Skips the model assertion on a cold env so
it is green in the lexical-only backend-tests stage.
"""
from __future__ import annotations

import os

from app.scripts.qa_attribution_fidelity import (
    _CAL_CAP,
    _CAL_DECOY,
    _CAL_STRONG,
    _fused,
    main,
)
from app.services.nlp import rerank
from app.services.nlp.semantic import SemanticIndex


def test_main_requires_database_url(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr("sys.argv", ["qa_attribution_fidelity"])
    assert main() == 2


def test_fused_degrades_to_bi_cosine_when_ce_cold(monkeypatch) -> None:
    # force the CE tier unavailable → support_score returns the raw cosine, so
    # _fused is exactly the bi-encoder relevance (zero regression contract).
    monkeypatch.setattr(rerank, "available", lambda: False)

    class _FakeIdx:
        def relevance(self, a: str, b: str) -> float:
            return 0.42

    val = _fused("capability", "evidence text", _FakeIdx())
    assert abs(val - 0.42) < 1e-9


def test_calibration_probe_discriminates_when_ce_baked() -> None:
    # Only meaningful when the cross-encoder is actually baked (qa-gates); on a
    # cold dev/CI env there is nothing to assert about discrimination.
    if not (rerank.available()
            and os.environ.get("DMA_CE_MODEL_DIR")):
        return
    idx = SemanticIndex()
    strong = _fused(_CAL_CAP, _CAL_STRONG, idx)
    decoy = _fused(_CAL_CAP, _CAL_DECOY, idx)
    assert strong >= 0.50, f"strong pair should fuse high, got {strong:.3f}"
    assert decoy <= 0.40, f"decoy pair should fuse low, got {decoy:.3f}"
    assert strong - decoy >= 0.20, f"margin too small: {strong - decoy:.3f}"
