"""Intelligence tier — cross-encoder re-ranking of evidence↔capability support
(app/services/nlp/rerank.py) and its wiring into EntityKnowledge.

The bare bi-encoder is "basic semantic matching": it plateaus ~0.5 for a true
match and is fooled by word-overlap decoys (a privacy notice shares "member"
with a lending capability). The cross-encoder reads each pair jointly and
verifies genuine support, so decoys collapse to ~0 and the fused, calibrated
confidence reaches ~0.95 on strong support.

The CE-using tests run live in the model-baked image via the ``ce`` fixture
(which clears the process-wide DMA_DISABLE_SEMANTIC a sibling module sets and
resets the lazy singleton); they skip ONLY in a bare dev venv without the baked
cross-encoder — never in CI/prod, so no gate-breaking skip. A separate test
proves the graceful degrade path with the tier disabled.
"""
from __future__ import annotations

import pytest

from app.services.nlp import rerank
from app.services.nlp.knowledge import Claim, EntityKnowledge, Evidence

_UW = "Loan officers hand-key underwriting decisions; approvals take 9 days."
_PRIVACY = "Privacy notice: collects member personal info via email and chat."
_BALANCE = "Total assets reached $2.5 billion at fiscal year end."
_CAP = "Manual, staff-driven underwriting slows member lending decisions."


@pytest.fixture()
def ce(monkeypatch):
    """Enable the cross-encoder tier and reset its lazy singleton.

    A sibling module (test_semantic_alignment) sets DMA_DISABLE_SEMANTIC=1
    process-wide; clear it (and any DMA_DISABLE_RERANK) so the baked
    cross-encoder loads, then restore + reset on teardown. Skips the test when
    no model is baked (bare dev venv only)."""
    monkeypatch.delenv("DMA_DISABLE_SEMANTIC", raising=False)
    monkeypatch.delenv("DMA_DISABLE_RERANK", raising=False)
    rerank._reset_load_state()
    rerank._CE_SPENT = 0.0
    rerank._CE_EXHAUSTED = False
    try:
        if not rerank.available():
            pytest.skip("cross-encoder not baked (bare dev venv; the image bakes /install/st-ce)")
        yield rerank
    finally:
        rerank._CE = None
        rerank._CE_TRIED = False
        rerank._CE_SPENT = 0.0
        rerank._CE_EXHAUSTED = False


def test_ce_budget_autoscales_to_half_the_step_timeout(monkeypatch) -> None:
    # DEPLOY SAFEGUARD: with no explicit budget, the cross-encoder budget is half
    # the derive step timeout — so it can never itself cause a SIGKILL on any CPU
    # (the other half covers the bi-encoder + composition). Explicit wins; capped.
    monkeypatch.delenv("DMA_RERANK_BUDGET_SEC", raising=False)
    monkeypatch.setenv("DERIVE_STEP_TIMEOUT_SEC", "1500")
    assert rerank._default_ce_budget() == 750.0
    monkeypatch.setenv("DERIVE_STEP_TIMEOUT_SEC", "300")
    assert rerank._default_ce_budget() == 150.0
    monkeypatch.setenv("DERIVE_STEP_TIMEOUT_SEC", "99999")
    assert rerank._default_ce_budget() == 900.0          # capped
    monkeypatch.setenv("DMA_RERANK_BUDGET_SEC", "42")
    assert rerank._default_ce_budget() == 42.0           # explicit override wins


def test_fuse_is_calibrated_and_bounded() -> None:
    # pure-logic (no model): strong+strong saturates high, decoy floors to ~0,
    # always within [0,1].
    assert rerank.fuse(0.95, 0.85) > 0.9
    assert rerank.fuse(0.01, 0.02) < 0.1
    assert 0.0 <= rerank.fuse(2.0, 2.0) <= 1.0
    assert 0.0 <= rerank.fuse(-1.0, -1.0) <= 1.0


def test_support_score_falls_back_to_raw_cosine_when_tier_disabled(monkeypatch) -> None:
    # tier off → EXACT raw bi-encoder cosine (zero-regression contract).
    monkeypatch.setenv("DMA_DISABLE_RERANK", "1")
    rerank._CE = None
    rerank._CE_TRIED = False
    try:
        assert rerank.cross_scores(_CAP, [_UW]) is None
        assert rerank.support_score(_CAP, _UW, bi_cos=0.44) == 0.44
    finally:
        rerank._CE = None
        rerank._CE_TRIED = False


def test_cross_encoder_crushes_word_overlap_decoy(ce) -> None:
    # the privacy decoy shares "member" with the lending capability; the
    # cross-encoder must score the real underwriting evidence far higher.
    scores = ce.cross_scores(_CAP, [_UW, _PRIVACY, _BALANCE])
    assert scores is not None
    uw, privacy, balance = scores
    assert uw > privacy and uw > balance
    assert privacy < 0.15 and balance < 0.15


def test_calibration_strong_support_high_decoy_low(ce) -> None:
    strong = ce.support_score(
        "Manual underwriting adds 9 days to loan decisions",
        "Manual underwriting adds 9 days to loan decisions.", bi_cos=0.85)
    decoy = ce.support_score(
        "Manual underwriting adds 9 days to loan decisions",
        _PRIVACY, bi_cos=0.20)
    assert strong >= 0.90, f"strong support should calibrate ~0.95, got {strong}"
    assert decoy <= 0.15, f"decoy should floor to ~0, got {decoy}"


def test_entity_knowledge_challenge_drops_the_decoy_citation(ce) -> None:
    ek = EntityKnowledge([
        Evidence("E-uw", _UW, tier=2),
        Evidence("E-pri", _PRIVACY, tier=3),
        Evidence("E-bal", _BALANCE, tier=4),
    ])
    # a claim that WRONGLY cites the privacy + balance decoys alongside the real
    # evidence — challenge() must keep only the genuinely-supporting E-uw.
    claim = Claim(text="Underwriting is manual and slow",
                  capability="Manual underwriting slows loan decisions",
                  e_ids=["E-uw", "E-pri", "E-bal"])
    ek.challenge(claim, min_support=0.30)
    assert claim.e_ids == ["E-uw"], f"decoys not dropped: {claim.e_ids}"
    assert claim.verdict == "grounded"
    assert claim.support >= 0.30


def test_budget_exhaustion_degrades_to_bi_encoder_no_timeout(ce) -> None:
    # DEPLOY SAFEGUARD: once the per-process cross-encoder budget is spent, calls
    # degrade to the raw bi-encoder cosine (never SIGKILL the derive step).
    ce._CE_EXHAUSTED = True
    assert ce.cross_scores("cap", ["evidence"]) is None
    # a band-range pair (0.15<=cos<=0.82) falls back to its RAW cosine, unchanged
    assert ce.support_score("cap", "evidence", bi_cos=0.50) == 0.50
    assert ce.support_scores("cap", [("a", 0.4), ("b", 0.6)]) == [0.4, 0.6]


def test_band_limit_skips_cross_encoder_on_clear_cosine(ce) -> None:
    # a very high cosine is taken as supported WITHOUT a cross-encoder call
    # (speed) and still calibrates high; a very low cosine floors to ~0.
    assert ce.support_score("cap", "clearly matching evidence", bi_cos=0.90) >= 0.90
    assert ce.support_score("cap", "unrelated evidence", bi_cos=0.05) <= 0.10


def test_entity_knowledge_supporting_evidence_rejects_decoys(ce) -> None:
    ek = EntityKnowledge([
        Evidence("E-uw", _UW, tier=2),
        Evidence("E-pri", _PRIVACY, tier=3),
        Evidence("E-bal", _BALANCE, tier=4),
    ])
    hits = ek.supporting_evidence(_CAP, k=3, min_score=0.30)
    ids = [e for e, _ in hits]
    assert "E-uw" in ids
    assert "E-pri" not in ids and "E-bal" not in ids
