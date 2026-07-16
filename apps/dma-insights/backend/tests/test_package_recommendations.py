"""Schema-tolerant recommendations reader.

Pins normalization of all three real corpus schemas (detail/register,
recommendations.json phase-6 export, 06_recommendations.json) into
RecommendationRow with the keys the persistence layer reads
(root_cause.finding/scoring_impact, solution.description,
cross_pillar_unlock), plus the end-to-end fill that lit up D4 for the
~50 packages that previously parsed to zero recs.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.services.parsers.package_recommendations import (
    _normalize_rec,
    _rec_id,
    parse_recommendations_any,
)

_BASE = Path(__file__).resolve().parents[1] / "tests/fixtures/dma_packages_batches"


def test_rec_id_normalisation() -> None:
    assert _rec_id("REC-01") == "REC-01"
    assert _rec_id("R7") == "REC-07"
    assert _rec_id(3) == "REC-03"
    assert _rec_id("rec_5") == "REC-05"
    assert _rec_id(None) == ""


def test_normalize_phase6_string_root_cause() -> None:
    rec = {
        "rec_id": 1, "title": "Data governance",
        "priority_gap": "P4C1",
        "evidence_ids": ["E-094"],
        "root_cause": "subcaps P4C1.1.1 and P4C1.1.2 score 1.5",
        "solution_rationale": "Salesforce Data Cloud unifies data",
        "zennify_solution_names": ["Salesforce Data Cloud"],
    }
    n = _normalize_rec(rec)
    assert n["id"] == "REC-01"
    assert n["root_cause"]["finding"].startswith("subcaps P4C1")
    # scoring_impact carries subcap refs so target_subcap_ids regex can mine them
    assert "P4C1.1.1" in n["root_cause"]["scoring_impact"]
    assert n["solution"]["description"] == "Salesforce Data Cloud unifies data"


def test_normalize_06_schema() -> None:
    rec = {
        "id": "R1", "title": "Automate marketing", "priority_rank": 3,
        "horizon": "H1",
        "root_cause": {"evidence_ids": ["E-063"], "narrative": "No marketing automation"},
        "solution_fit": {"catalog_rating": "Excellent"},
        "zennify_solution": "Marketing Cloud + Account Engagement",
        "cross_pillar_unlocks": ["Feeds Data Cloud (R2)", "Connects Experience Cloud"],
        "counter_argument": {"objection": "not core", "rebuttal": "E-061 confirms"},
    }
    n = _normalize_rec(rec)
    assert n["id"] == "REC-01"
    assert n["root_cause"]["finding"] == "No marketing automation"
    assert n["solution"]["description"] == "Marketing Cloud + Account Engagement"
    assert "Feeds Data Cloud" in n["cross_pillar_unlock"]
    assert len(n["counter_arguments"]) == 1
    assert n["priority"] == "H1"


def test_detail_schema_passthrough() -> None:
    blob = json.dumps({"recommendations": [{
        "id": "REC-03", "priority": "P0", "title": "Detail rec",
        "root_cause": {"finding": "x", "scoring_impact": "P1C1.1.1"},
        "solution": {"description": "do y"},
        "cross_pillar_unlock": "unlocks z",
    }]})
    recs = parse_recommendations_any(blob)
    assert len(recs) == 1
    assert recs[0].id == "REC-03" and recs[0].priority == "P0"
    assert recs[0].solution["description"] == "do y"


def test_list_and_malformed() -> None:
    assert parse_recommendations_any("not json") == []
    assert parse_recommendations_any("{}") == []
    # top-level list form
    recs = parse_recommendations_any(json.dumps([
        {"rec_id": 1, "title": "A", "root_cause": "rc"},
        {"rec_id": 1, "title": "dup id"},  # deduped
    ]))
    assert len(recs) == 1


def _find(name_glob: str) -> Path | None:
    hits = sorted(_BASE.glob(f"batch_*/*/**/{name_glob}"))
    return hits[0] if hits else None


def test_e2e_recommendations_json_lights_up_d4() -> None:
    """A package that ships recommendations.json (phase-6 schema) and was
    previously parsed to zero recs now yields recs end-to-end."""
    from app.services.parsers.dma_package import parse_package

    # OZK ships 03_scoring_workbook/recommendations.json (phase-6 schema).
    ozk = next(iter(sorted(_BASE.glob("batch_*/OZK Bank - DMA"))), None)
    if ozk is None:
        import pytest
        pytest.skip("OZK fixture moved")
    pkg = parse_package(ozk)
    assert len(pkg.recommendations) > 0
    r = pkg.recommendations[0]
    assert r.id.startswith("REC-")
    assert r.title and r.title != "(untitled)"
