"""Part 7.2 — rich rec corpus parsing on the REAL fixture files.

The audit found `recommendations_detail.json` (Alma canonical) and the
per-REC `REC-NN.json` directory (CACU shape) shipping feature / phase /
root-cause E-IDs / quantified outcomes / dependency clauses that were
never ingested. These tests pin the extraction against the actual
committed fixtures — not synthetic shapes — so a corpus drift breaks
loudly here.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.parsers.package_recommendations import parse_recommendations_any
from app.services.parsers.rec_files import (
    compose_gap_outcomes,
    effort_band_from_gap,
    extract_dependencies,
    extract_rec_enrichment,
    feature_from_text,
    find_rec_sources,
    mine_description_enrichment,
    parse_rec_dir,
)

FIXTURES = Path(__file__).parent / "fixtures"
ALMA_DETAIL = (
    FIXTURES / "dma_packages_batches" / "batch_08" / "Alma Bank - DMA"
    / "08_appendices" / "recommendations_detail.json"
)
CACU_REC_DIR = (
    FIXTURES / "dma_packages_batches" / "batch_05"
    / "Corporate America Credit Union - DMA" / "CACU_DMA_Deliverables"
    / "08_appendices" / "recommendations"
)

pytestmark = pytest.mark.skipif(
    not ALMA_DETAIL.exists() or not CACU_REC_DIR.exists(),
    reason="real rec fixtures not present",
)


def test_alma_detail_rows_carry_048_fields() -> None:
    rows = parse_recommendations_any(ALMA_DETAIL.read_text(encoding="utf-8"))
    assert len(rows) == 7
    r0 = rows[0].model_dump()
    assert r0["id"] == "REC-01"
    # feature from solution.zennify_offering
    assert r0["feature"] == "Digital Strategy Workshop"
    # phase from "P0 — IMMEDIATE"
    assert r0["phase"] == 1
    # root-cause E-IDs from the structured evidence_ids array
    assert r0["root_cause_e_ids"][:3] == ["E-033", "E-018", "E-091"]
    # quantified outcomes: baseline → target metric + named peer
    assert "2.061" in r0["outcomes"]["metric"]
    assert r0["outcomes"]["peer"].startswith("Hanover Community Bank")
    # "R7 is the organizational prerequisite for R1-R6" fans out
    assert len(r0["prereq_of_rec_ids"]) >= 4


def test_cacu_per_rec_dir_parses_all_files() -> None:
    recs = parse_rec_dir(CACU_REC_DIR)
    assert len(recs) == 12
    by_id = {r["id"] for r in recs}
    assert "REC-01" in by_id and "REC-12" in by_id


def test_cacu_rec01_enrichment() -> None:
    raw = json.loads((CACU_REC_DIR / "REC-01.json").read_text(encoding="utf-8"))
    e = extract_rec_enrichment(raw)
    # zennify_solution "#12 Digital Strategy Workshop" → number stripped
    assert e["feature"] == "Digital Strategy Workshop"
    # tier "T1 Foundation" → phase 1
    assert e["phase"] == 1
    # root_cause.evidence keeps E-IDs, drops the IC-010 insight ref
    assert "E-025" in e["root_cause_e_ids"]
    assert all(x.startswith("E-") for x in e["root_cause_e_ids"])
    # numeric baseline→target outcome preferred
    assert e["outcomes"]["metric"] == "P1C1 score: 1.18 → 2.0+"
    # "REC-10 GRC Platform requires governance charter as prerequisite"
    # → REC-10 depends on THIS rec.
    assert "REC-10" in e["prereq_of_rec_ids"]


def test_find_rec_sources_prefers_per_rec_dir() -> None:
    pkg_root = CACU_REC_DIR.parents[2]
    sources = find_rec_sources(pkg_root)
    assert sources, "CACU package must expose a rec source"
    assert sources[0].name == "recommendations"  # the per-REC directory


def test_dependency_mining_requires_and_prereq_of() -> None:
    requires, prereq_of = extract_dependencies(
        {"cross_pillar_unlock":
            "REC-03 requires REC-01 as prerequisite. "
            "This initiative is the prerequisite for R5-R6."},
        "REC-03",
    )
    assert requires == ["REC-01"]
    assert prereq_of == ["REC-05", "REC-06"]


def test_feature_keyword_scan() -> None:
    assert feature_from_text("Deploy Data Cloud for unified profiles") == "Data Cloud"
    assert feature_from_text("nCino Workflow Engine rollout") == "nCino Workflow Engine"
    assert feature_from_text("nothing platformy here") is None


def test_mine_description_enrichment_grounded() -> None:
    e = mine_description_enrichment(
        title="Strengthen P4C1: Unified Customer Profile",
        description=(
            "P4C1 scores 2.14 vs peer 2.95 — below the M4 target. "
            "Closing this gap is addressable via databricks. "
            "Grounded in E-047 and E-141."
        ),
        effort_band="MEDIUM",
        rec_id="REC-02",
    )
    assert e["root_cause_e_ids"] == ["E-047", "E-141"]
    assert e["phase"] == 2                       # MEDIUM effort band
    assert e["outcomes"]["effort"] == "M"
    assert "P4C1 score 2.14" in e["outcomes"]["metric"]
    assert "peer median 2.95" in e["outcomes"]["metric"]


def test_compose_gap_outcomes_grounded() -> None:
    """The DB-grounded fill tier (derive PASS 4): every slot traces to a real
    score, the gap-derived effort band, or a real peer name."""
    assert effort_band_from_gap(2.5) == "LARGE"
    assert effort_band_from_gap(0.9) == "MEDIUM"
    assert effort_band_from_gap(0.4) == "SMALL"
    oc = compose_gap_outcomes(
        label="P2C4", current=1.5, peer_median=2.58, peer_name="Synovus")
    # metric carries its own a → b lift clause (roadmap re-mines it).
    assert oc["metric"] == "P2C4 score 1.50 → 4.0 (peer median 2.58)"
    assert oc["peer"] == "Synovus"
    # gap 2.5 → LARGE → 12-18mo window + effort "L"
    assert oc["effort"] == "L"
    assert oc["time"] == "12–18 months"  # noqa: RUF001 — en-dash per _PHASE_WINDOW
    # explicit effort band overrides the gap-derived one.
    oc2 = compose_gap_outcomes(label="P1C1", current=3.4, effort_band="SMALL")
    assert oc2["effort"] == "S"
    assert oc2["peer"] is None  # honest: no peer supplied


def test_mine_description_honest_nulls() -> None:
    e = mine_description_enrichment(
        title="A title", description="Prose with no numbers or citations.",
        effort_band=None, rec_id="REC-09",
    )
    assert e["root_cause_e_ids"] == []
    assert e["phase"] is None
    assert e["outcomes"] is None


# ── per-rec declared score transitions (2026-07-06 production fix) ─────────
# All three IBKR rec cards rendered the IDENTICAL metric "P2C1 score
# 1.79 → 4.0" because nothing read the rec's OWN "P2C1 (1.79→2.8)"
# clauses — every card inherited the run-wide worst gap → uniform fill.


def test_extract_score_transitions_paren_and_colon_shapes() -> None:
    from app.services.parsers.rec_files import extract_score_transitions

    text = (
        "R1: Financial Services Cloud — P2C1 (1.79→2.8), P2C4 (2.18→2.9). "
        "P4C2 (Analytics & AI): 2.65 → 3.4 under governance."
    )
    trans = extract_score_transitions(text)
    assert [(t["label"], t["current"], t["target"]) for t in trans] == [
        ("P2C1", 1.79, 2.8), ("P2C4", 2.18, 2.9), ("P4C2", 2.65, 3.4),
    ]


def test_extract_score_transitions_rejects_off_band_and_dedupes() -> None:
    from app.services.parsers.rec_files import extract_score_transitions

    # >5 values are not maturity scores; the first per-label mention wins.
    trans = extract_score_transitions(
        "P2C1 (12→48) is a volume figure. P2C1 (2.0→3.0) and P2C1 (1.0→4.0)."
    )
    assert trans == [{"label": "P2C1", "current": 2.0, "target": 3.0}]
    assert extract_score_transitions("") == []


def test_mine_description_prefers_own_transition_metric() -> None:
    e = mine_description_enrichment(
        title="R2 Marketing Cloud (MCAE)",
        description=(
            "Capabilities: P2C1 (2.0→3.0), P2C4 (2.3→3.1). "
            "Timeline: 6 months. Grounded in E-075."
        ),
        effort_band="MEDIUM",
        rec_id="R2",
    )
    # the rec's OWN declared transition, not a generic quantities hit
    assert e["outcomes"]["metric"] == "P2C1 score 2.00 → 3.0"
    assert e["outcomes"]["time"] == "6 months"       # rec's own timeline
    assert e["root_cause_e_ids"] == ["E-075"]
