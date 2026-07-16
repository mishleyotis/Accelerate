"""D4 — recommendation_validation prerequisite parser + source_rec_id capture.

Pure / no DB. Covers the confident-match (Greenstone), honest-empty (Frost),
the id-format mapping edge cases, and the insight source_rec_id capture.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.schemas.package import RecommendationRow
from app.services.parsers.recommendation_validation import parse_rec_prerequisites
from app.services.parsers.section_analysis import insights_from_recommendations

_FIX = Path(__file__).resolve().parent / "fixtures" / "dma_packages_batches"
_GREENSTONE = (_FIX / "batch_14" / "Greenstone - DMA" / "02_research_workbook"
               / "recommendation_validation.json")
_FROST = (_FIX / "batch_05" / "Frost Bank - DMA" / "01_evidence"
          / "recommendation_validation.json")


def test_greenstone_confident_prerequisite_match() -> None:
    if not _GREENSTONE.exists():
        pytest.skip("Greenstone fixture not present")
    known = {f"REC-{n:02d}" for n in range(1, 10)}  # REC-01..REC-09
    result = parse_rec_prerequisites(_GREENSTONE.read_text(encoding="utf-8"), known)
    # Only R8 (Agentforce) declares a prerequisite: "R2 + R5 must precede R8".
    assert result == {"REC-08": ["REC-02", "REC-05"]}


def test_frost_no_prerequisite_field_yields_empty() -> None:
    if not _FROST.exists():
        pytest.skip("Frost fixture not present")
    known = {f"REC-{n:02d}" for n in range(1, 11)}  # REC-01..REC-10
    # Frost's validations carry finding + status only — no prerequisite.
    assert parse_rec_prerequisites(_FROST.read_text(encoding="utf-8"), known) == {}


def test_malformed_input_returns_empty() -> None:
    assert parse_rec_prerequisites("not json{", {"REC-01"}) == {}
    assert parse_rec_prerequisites("", set()) == {}
    assert parse_rec_prerequisites("[]", {"REC-01"}) == {}        # list, not dict
    assert parse_rec_prerequisites('{"validations": "x"}', {"REC-01"}) == {}


def test_id_mapping_and_filtering() -> None:
    known = {"REC-01", "REC-02", "REC-05", "REC-08"}
    rows = [
        # R-format id; self-ref R8 dropped; R2/R5 kept.
        {"id": "R8", "prerequisite": "R2 + R5 must precede R8"},
        # REC-format own id; prereq in REC- form.
        {"id": "REC-01", "prerequisite": "after REC-08"},
        # unknown token -> no confident match -> no entry.
        {"id": "R2", "prerequisite": "needs R99 only"},
        # `rec`-field variant ("REC-05 MuleSoft"); self-only -> no entry.
        {"rec": "REC-05 MuleSoft", "prerequisite": "R5 then nothing"},
    ]
    result = parse_rec_prerequisites(json.dumps({"validations": rows}), known)
    assert result == {"REC-08": ["REC-02", "REC-05"], "REC-01": ["REC-08"]}


def test_prerequisites_list_form_is_accepted() -> None:
    known = {"REC-01", "REC-02", "REC-03"}
    rows = [{"id": "R3", "prerequisites": ["R1", "R2"]}]
    result = parse_rec_prerequisites(json.dumps({"validations": rows}), known)
    assert result == {"REC-03": ["REC-01", "REC-02"]}


def test_source_rec_id_captured_from_derived_insight() -> None:
    rec = RecommendationRow(
        id="R3", title="Adopt Marketing Cloud",
        root_cause={"finding": "P2C4 personalization ceiling capped at M1",
                    "scoring_impact": "P2C4 below peer median"},
        solution={"description": "Deploy Salesforce Marketing Cloud"},
    )
    cards = insights_from_recommendations([rec])
    assert len(cards) == 1
    assert cards[0].source_rec_id == "REC-03"
    assert cards[0].linked_subcap_id.startswith("P2C4")
