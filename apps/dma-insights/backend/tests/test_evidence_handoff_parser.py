"""Tests for the evidence_handoff JSON parser."""
from __future__ import annotations

import json

from app.services.parsers.evidence_handoff import parse_handoff_text


def _minimal_payload() -> dict:
    return {
        "payload_version": "v1",
        "request_id": "REQ-A6654887",
        "ccg_catalog_version": "v7.0",
        "entity_name": "Farm Credit East",
        "entity_subvertical": "FC",
        "scqa": {
            "situation": "s", "complication": "c", "question": "q", "answer": "a",
        },
        "subcap_scores": [
            {"subcap_id": "P1C1.1.1", "score": 3.2, "band": "M3"},
        ],
        "evidence": [
            {
                "e_id": "E-1",
                "source_name": "ABA Banking Journal",
                "excerpt": "AUM grew 8% YoY",
                "claim_type": "strategic_signal",
                "tier": 2,
            }
        ],
        "insights": [
            {
                "ic_id": "IC-1",
                "severity": "high",
                "title": "Paper origination",
                "what_text": "PDF-driven",
                "why_text": "lagged investments",
                "so_what_text": "member churn",
                "linked_subcap_id": "P1C1.1.1",
                "linked_e_ids": ["E-1"],
            }
        ],
        "recommendations": [
            {
                "rec_id": "REC-1",
                "title": "Adopt nCino",
                "description": "Replaces 14 manual steps.",
                "target_subcap_ids": ["P1C1.1.1"],
                "platform_id": "ncino",
                "uplift_per_pillar": {"P1": 0.8},
                "effort_band": "large",
            }
        ],
    }


class TestHappyPath:
    def test_ok_round_trip(self) -> None:
        res = parse_handoff_text(json.dumps(_minimal_payload()))
        assert res.ok is True
        assert res.payload is not None
        assert res.payload.request_id == "REQ-A6654887"
        # rows_by_kind populated for every category
        assert len(res.rows_by_kind["subcap_scores"]) == 1
        assert len(res.rows_by_kind["evidence"]) == 1
        assert len(res.rows_by_kind["insights"]) == 1
        assert len(res.rows_by_kind["recommendations"]) == 1


class TestFailureModes:
    def test_bad_json(self) -> None:
        res = parse_handoff_text("{not valid")
        assert res.ok is False
        assert res.payload is None
        assert any(e["kind"] == "json_decode" for e in res.errors)

    def test_schema_violation(self) -> None:
        bad = _minimal_payload()
        bad["request_id"] = "REQ-lowercase"  # pattern fail
        res = parse_handoff_text(json.dumps(bad))
        assert res.ok is False
        assert res.payload is None
        assert any(e["kind"] == "schema_validation" for e in res.errors)


class TestNonFatalWarnings:
    def test_ic_links_unknown_evidence(self) -> None:
        payload = _minimal_payload()
        payload["insights"][0]["linked_e_ids"] = ["E-1", "E-9999"]
        res = parse_handoff_text(json.dumps(payload))
        assert res.ok is True
        assert any(
            w["kind"] == "ic_links_unknown_evidence" and w["missing_e_id"] == "E-9999"
            for w in res.warnings
        )

    def test_rec_targets_unscored_subcap(self) -> None:
        payload = _minimal_payload()
        payload["recommendations"][0]["target_subcap_ids"] = ["P1C1.1.1", "P9C9.9.9"]
        res = parse_handoff_text(json.dumps(payload))
        assert res.ok is True
        assert any(
            w["kind"] == "rec_targets_unscored_subcap" and w["subcap_id"] == "P9C9.9.9"
            for w in res.warnings
        )
