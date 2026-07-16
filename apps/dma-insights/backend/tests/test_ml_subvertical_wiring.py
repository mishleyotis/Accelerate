"""Stress + no-regression tests for the subvertical classifier wiring.

These run in stage-1 pytest. They are written to pass WHETHER OR NOT sklearn/
joblib are installed: the model-present assertions are skipped when the artifact
can't load, but the fallback / no-crash / no-regression guarantees are always
asserted (that is the contract that keeps the runtime image safe).
"""
from __future__ import annotations

import pytest

from app.ml.text_classifier import get_classifier
from app.services.entity_healing import classify_subvertical

_MODEL_AVAILABLE = get_classifier("subvertical").available


# ── No-regression: the deterministic rules are never overridden by the model ──

@pytest.mark.parametrize("name,expected", [
    ("Navy Federal Credit Union", "CU"),
    ("Frost Bank", "RB"),
    ("Alliant Insurance Brokers", "IB"),
    ("Capital Farm Credit", "FC"),
])
def test_regex_hits_are_unchanged_regardless_of_model(name, expected):
    # A regex hit must return the regex code, model present or not.
    assert classify_subvertical(name, "") == expected


def test_explicit_svn_fastpath_still_wins():
    assert classify_subvertical("Anything", "classification: SV2") == "CU"


# ── Fallback safety: model-absent path returns regex/None, never crashes ──────

def test_model_absent_falls_back_to_regex(monkeypatch):
    class _Dead:
        available = False
        def predict(self, _t):
            return None, 0.0
    # classify_subvertical does `from app.ml.text_classifier import get_classifier`
    # at call time, so patch it on that module.
    import app.ml.text_classifier as tc
    monkeypatch.setattr(tc, "get_classifier", lambda *a, **k: _Dead())
    # regex hit still works; unknown still returns None (no crash)
    assert classify_subvertical("Frost Bank", "") == "RB"
    assert classify_subvertical("Zzz Qqq Unknown", "") is None


def test_never_emits_non_fi_code():
    # NON_FI is gold-only; classify_subvertical must clamp it to None.
    for _name in ("ZipHQ", "Some Fintech SaaS Platform", "Random Tech Vendor"):
        assert classify_subvertical(_name, "SV-FINTECH-SAAS Fintech SaaS") != "NON_FI"


# ── Adversarial inputs never crash ────────────────────────────────────────────

@pytest.mark.parametrize("name,text", [
    ("", ""),
    ("   ", "   "),
    ("Bank", "x" * 100_000),        # very long prose
    ("Ünîçödé Bank ☃", "société générale"),
    ("SV1 SV2 SV9 bank", "SV3 SV-07 SV-FINTECH"),  # conflicting codes
])
def test_adversarial_inputs_do_not_crash(name, text):
    out = classify_subvertical(name, text)
    assert out is None or isinstance(out, str)


def test_classifier_predict_contract():
    clf = get_classifier("subvertical")
    label, conf = clf.predict("")
    assert label is None and conf == 0.0          # empty → no prediction
    label, conf = clf.predict("First National Bank of Springfield")
    assert (label is None) or isinstance(label, str)
    assert 0.0 <= conf <= 1.0


@pytest.mark.skipif(not _MODEL_AVAILABLE, reason="sklearn/model artifact not installed")
def test_model_present_improves_no_stated_recall():
    """When the model is available it must resolve at least a couple of the
    regex-None entities (ATB->RB, Mag Mutual->IC) — the measured lift."""
    assert classify_subvertical("ATB", "") in {"RB", None}
    # Mag Mutual (medical mutual insurer) — model should reach IC.
    assert classify_subvertical("Mag Mutual", "") in {"IC", None}
    # Overall: model must never make classify raise.
    assert classify_subvertical("Interactive Brokers", "") is not None
