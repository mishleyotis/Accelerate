"""run_manifest schema-drift tolerance (Part 12.1) — real failing manifests.

The corpus audit measured 45 packages whose run_manifest ValidationError'd
into the synthesized-manifest path. This suite pins the reconcile rung on
the ACTUAL drifted fixtures:

  - Amalgamated: `entity` is a nested dict; scores under
    scores.pillars.P#.post_critic; weights/date under
    assessment_parameters.
  - Access CU: band-string scores ("M1.66") + overall_maturity.
  - Haventree: assessment_run_id + institution_legal_name +
    framework_version.

Truly-malformed manifests (no run_id-shaped field anywhere) must STILL
raise so `_maybe` records the DEGRADED schema_mismatch and the
synthesized-manifest rungs take over.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.parsers.dma_package import (
    _parse_run_manifest_tolerant,
    _score_like_to_float,
)

_CORPUS = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / \
    "dma_packages_batches"

_AMALGAMATED = _CORPUS / "batch_07" / "Amalgamated Bank - DMA" / \
    "Amalgamated_Bank_DMA_2026" / "07_governance" / "run_manifest.json"
_ACCESS = _CORPUS / "batch_06" / "Access Credit Union - DMA" / \
    "Access_Credit_Union_DMA_20260504" / "07_governance" / "run_manifest.json"
_HAVENTREE = _CORPUS / "batch_01" / "Haventree Bank DMA - DMA" / \
    "08_appendices" / "run_manifest_assessment.json"


class TestScoreCoercion:
    def test_band_strings(self) -> None:
        assert _score_like_to_float("M1.66") == 1.66
        assert _score_like_to_float("m2") == 2.0
        assert _score_like_to_float(2.43) == 2.43
        assert _score_like_to_float("2.43") == 2.43
        assert _score_like_to_float("CRITICAL") is None
        assert _score_like_to_float(None) is None


class TestRealDriftedManifests:
    def test_amalgamated_nested_entity_dict(self) -> None:
        assert _AMALGAMATED.is_file(), f"fixture moved: {_AMALGAMATED}"
        ws: list[str] = []
        rm = _parse_run_manifest_tolerant(
            _AMALGAMATED.read_text(), warnings=ws, label="run_manifest.json",
        )
        assert rm.run_id == "DMA-ASSESS-AMAL-20260428-0001"
        assert rm.institution_name.startswith("Amalgamated")
        assert rm.subvertical_code == "SV1"
        # Post-critic pillar scores + weights lifted from the nesting.
        assert rm.pillar_scores and abs(rm.pillar_scores["P1"] - 2.9) < 0.5
        assert rm.pillar_weights == {"P1": 0.25, "P2": 0.3, "P3": 0.2, "P4": 0.25}
        assert rm.overall_score is not None and 2.0 < rm.overall_score < 3.0
        assert str(rm.assessment_date) == "2026-04-28"
        # The reconcile is announced as INFO (not DEGRADED — data intact).
        assert any("INFO/run_manifest_reconciled" in w for w in ws)

    def test_access_band_string_scores(self) -> None:
        assert _ACCESS.is_file(), f"fixture moved: {_ACCESS}"
        ws: list[str] = []
        rm = _parse_run_manifest_tolerant(
            _ACCESS.read_text(), warnings=ws, label="run_manifest.json",
        )
        assert rm.run_id == "DMA-ASM-ACCU-20260504-0001"
        assert rm.institution_name == "Access Credit Union Limited"
        assert rm.pillar_scores == {
            "P1": 1.66, "P2": 1.37, "P3": 2.07, "P4": 1.34,
        }
        assert rm.overall_score == 1.58   # from overall_maturity "M1.58"

    def test_haventree_assessment_run_id(self) -> None:
        assert _HAVENTREE.is_file(), f"fixture moved: {_HAVENTREE}"
        ws: list[str] = []
        rm = _parse_run_manifest_tolerant(
            _HAVENTREE.read_text(), warnings=ws,
            label="run_manifest_assessment.json",
        )
        assert rm.run_id == "DMA-ASM-HAVENTREE-20260429-0001"
        assert rm.institution_name == "Haventree Bank"
        assert rm.overall_score == 2.9
        assert rm.subvertical_name and "Specialty Lender" in rm.subvertical_name
        assert rm.rubric_version and "5.5" in rm.rubric_version


class TestCanonicalShapesUntouched:
    def test_strict_parse_wins_without_reconcile_warning(self) -> None:
        blob = json.dumps({
            "run_id": "DMA-ASM-ALMA-20260501-0001",
            "institution_name": "AlmaBank",
            "evidence_mode": "PUBLIC",
            "overall_score": 3.1,
        })
        ws: list[str] = []
        rm = _parse_run_manifest_tolerant(blob, warnings=ws)
        assert rm.institution_name == "AlmaBank"
        assert not ws    # no reconcile note for a clean manifest


class TestTrulyMalformedStillRaises:
    def test_no_run_id_anywhere(self) -> None:
        blob = json.dumps({"phases": {"0": "COMPLETE"}, "note": "junk"})
        with pytest.raises(ValueError, match="no run_id-shaped field"):
            _parse_run_manifest_tolerant(blob, warnings=[])

    def test_non_object_json(self) -> None:
        with pytest.raises(ValueError):
            _parse_run_manifest_tolerant("[1, 2, 3]", warnings=[])
