"""Tests for the Drive file classifier."""
from __future__ import annotations

import pytest

from app.services.parsers.classifier import (
    Classification,
    classify,
    classify_by_extension,
    classify_by_filename,
)


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("Assessment_Report_FCE_REQ-A6654887.docx", "assessment_report"),
        ("Scoring_Workbook_FCE_REQ-A6654887.xlsx", "scoring_workbook"),
        ("Research_Workbook_FCE.xlsx", "research_workbook"),
        ("app_payload_v1.json", "evidence_handoff_json"),
        ("evidence-handoff-FCE.json", "evidence_handoff_json"),
        ("Client_Profile_FCE.docx", "client_profile"),
        ("Issue_Register_FCE_REQ-A6654887.xlsx", "issue_register"),
    ],
)
def test_filename_patterns(filename: str, expected: str) -> None:
    c = classify_by_filename(filename)
    assert c is not None
    assert c.kind == expected
    assert c.confidence >= 0.6


def test_unknown_json_low_confidence() -> None:
    c = classify_by_filename("random_thing.json")
    assert c is not None
    assert c.kind == "evidence_handoff_json"
    assert c.confidence == 0.6


def test_extension_fallback() -> None:
    c = classify_by_extension("screenshot_login.png")
    assert c is not None
    assert c.kind == "supplementary"


def test_cascade_unknown_with_no_signal() -> None:
    c = classify("random.txt")
    assert c.kind == "unknown"
    assert c.confidence == 0.0


def test_cascade_prefers_high_confidence_filename_over_llm() -> None:
    # Even if the LLM disagrees, a high-confidence filename match wins.
    def fake_llm(_name: str, _chars: str) -> Classification:
        return Classification(kind="supplementary", confidence=0.9, rationale="LLM said so")

    c = classify("Scoring_Workbook_X.xlsx", gemini_classify=fake_llm)
    assert c.kind == "scoring_workbook"


def test_cascade_uses_llm_when_filename_low_conf() -> None:
    def fake_llm(_name: str, _chars: str) -> Classification:
        return Classification(kind="research_workbook", confidence=0.85,
                              rationale="LLM said so")

    c = classify("misc.json", gemini_classify=fake_llm)
    assert c.kind == "research_workbook"


def test_cascade_falls_back_when_llm_low_conf() -> None:
    def fake_llm(_name: str, _chars: str) -> Classification:
        return Classification(kind="unknown", confidence=0.3, rationale="dunno")

    c = classify("random.txt", gemini_classify=fake_llm)
    # No filename match, LLM below threshold → unknown
    assert c.kind == "unknown"


def test_cascade_tolerates_llm_exception() -> None:
    def bad_llm(_name: str, _chars: str) -> Classification:
        raise RuntimeError("vertex down")

    c = classify("Scoring_Workbook_X.xlsx", gemini_classify=bad_llm)
    assert c.kind == "scoring_workbook"
