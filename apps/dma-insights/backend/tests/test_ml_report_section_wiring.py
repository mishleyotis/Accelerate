"""Stress + no-regression tests for the report-section classifier wiring.

CI-safe whether or not sklearn/joblib are installed: model-present assertions are
skipped when the artifact can't load; the fallback / no-crash / no-regression
guarantees always hold.
"""
from __future__ import annotations

import pytest

from app.ml.text_classifier import get_classifier
from app.services.parsers.assessment_report import EXPECTED_KINDS, classify_heading

_MODEL_AVAILABLE = get_classifier("report_section").available


@pytest.mark.parametrize("heading,expected", [
    ("Executive Summary", "executive_summary_scqa"),
    ("Recommendations", "recommendations"),
    ("Issue Register", "issue_register"),
])
def test_regex_hits_unchanged(heading, expected):
    # A regex dictionary hit must be returned regardless of the model.
    assert classify_heading(heading) == expected


def test_unknown_heading_stays_other_or_valid_kind():
    out = classify_heading("Appendix G — Miscellaneous Notes and Sundry Items")
    assert out == "other" or out in EXPECTED_KINDS


def test_model_absent_falls_back_to_other(monkeypatch):
    class _Dead:
        available = False
        def predict(self, _t):
            return None, 0.0
    import app.ml.text_classifier as tc
    monkeypatch.setattr(tc, "get_classifier", lambda *a, **k: _Dead())
    # regex hit still works; unknown -> "other" (no crash)
    assert classify_heading("Recommendations") == "recommendations"
    assert classify_heading("Zzz Qqq Unknown Heading") == "other"


@pytest.mark.parametrize("heading", ["", "   ", "x" * 100_000, "Ünîçödé ☃ Heading", "P1C1.1.1"])
def test_adversarial_headings_never_crash(heading):
    out = classify_heading(heading)
    assert out == "other" or out in EXPECTED_KINDS


def test_classify_heading_only_emits_valid_kinds():
    for h in ["Strategic Recommendations", "Phased Roadmap", "random text",
              "Digital Evolution Timeline", "Peer Set Overview"]:
        assert classify_heading(h) in set(EXPECTED_KINDS) | {"other"}


@pytest.mark.skipif(not _MODEL_AVAILABLE, reason="sklearn/model artifact not installed")
def test_model_recovers_recurring_other_forms():
    # forms the regex misses but the model should confidently recover
    assert classify_heading("Strategic Recommendations") == "recommendations"
    assert classify_heading("Phased Roadmap") in {"roadmap", "other"}
