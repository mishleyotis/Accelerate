"""Part 7.3 — sequence-aware roadmap phasing (routers.platforms pure fns).

The audit measured 91/94 clients on a SINGLE roadmap phase (effort-band
only bucketing), maturity_lift null 89%, target '—' and metric = the rec
title. These tests pin the new assembly: explicit corpus phase →
prerequisite-DAG level → effort band → uplift spread; per-phase target
('M1 → M2 in P1C1' from before/after), top outcome metric, platform
join, customer_impact and cross-phase dependencies.
"""
from __future__ import annotations

from app.routers.platforms import (
    _card_evidence_ids,
    _rec_maturity_lift,
    assign_phases,
    build_roadmap_phases,
)


def test_card_evidence_ids_ladder() -> None:
    """Card evidence_ids union the addressable subcaps' E-IDs, falling back
    to run-level so an evidenced entity's cards always cite something; only a
    truly evidence-less run yields []."""
    bd = {"top_subcaps": [
        {"e_ids": ["E-01", "E-02"]},
        {"e_ids": ["E-02", "E-05"]},  # dedup
        {"e_ids": []},
    ]}
    assert _card_evidence_ids(bd, ["E-99"]) == ["E-01", "E-02", "E-05"]
    # no subcap E-IDs → run-level fallback (entity has evidence).
    assert _card_evidence_ids({"top_subcaps": []}, ["E-99", "E-98"]) == ["E-99", "E-98"]
    # truly evidence-less → honest empty.
    assert _card_evidence_ids(None, []) == []


def _rec(rec_id: str, **kw) -> dict:
    return {
        "rec_id": rec_id,
        "title": kw.pop("title", f"Rec {rec_id}"),
        "platform_id": kw.pop("platform_id", "salesforce"),
        "platform_name": kw.pop("platform_name", "Salesforce"),
        "effort_band": kw.pop("effort_band", None),
        "uplift_per_pillar": kw.pop("uplift_per_pillar", None),
        "phase": kw.pop("phase", None),
        "feature": kw.pop("feature", None),
        "outcomes": kw.pop("outcomes", None),
        "prerequisite_rec_ids": kw.pop("prerequisite_rec_ids", []),
        "target_subcap_ids": kw.pop("target_subcap_ids", []),
    }


def test_explicit_corpus_phase_wins() -> None:
    phases = assign_phases([
        _rec("REC-01", phase=1, effort_band="LARGE"),
        _rec("REC-02", phase=3, effort_band="SMALL"),
    ])
    assert phases == {"REC-01": 1, "REC-02": 3}


def test_prereq_dag_pushes_dependents_later() -> None:
    phases = assign_phases([
        _rec("REC-01", phase=1),
        _rec("REC-02", phase=1, prerequisite_rec_ids=["REC-01"]),
        _rec("REC-03", phase=1, prerequisite_rec_ids=["REC-02"]),
    ])
    assert phases["REC-01"] == 1
    assert phases["REC-02"] == 2, "a rec lands after its prerequisite"
    assert phases["REC-03"] == 3
    # Cycles collapse to the base phase (never crash / never rank 5+).
    cyc = assign_phases([
        _rec("A", phase=1, prerequisite_rec_ids=["B"]),
        _rec("B", phase=1, prerequisite_rec_ids=["A"]),
    ])
    assert set(cyc.values()) <= {1, 2, 3, 4}


def test_effort_band_fallback_then_uplift() -> None:
    phases = assign_phases([
        _rec("REC-01", effort_band="SMALL"),
        _rec("REC-02", effort_band="LARGE"),
        _rec("REC-03", uplift_per_pillar={"P4": 1.5}),   # big jump → 3
        _rec("REC-04", uplift_per_pillar={"P2": 0.3}),   # small → 1
    ])
    assert phases["REC-01"] == 1 and phases["REC-02"] == 3
    assert phases["REC-03"] == 3 and phases["REC-04"] == 1


def test_uplift_spread_breaks_single_phase_pileup() -> None:
    """The 91/94 single-phase audit class: same effort band everywhere,
    no deps → spread by uplift into multiple phases."""
    recs = [
        _rec(f"REC-0{i}", effort_band="MEDIUM",
             uplift_per_pillar={"P4": 0.2 * i})
        for i in range(1, 6)
    ]
    phases = assign_phases(recs)
    assert len(set(phases.values())) >= 2, "pileup must spread"
    # Biggest uplift lands earliest (quick-wins ordering).
    assert phases["REC-05"] <= phases["REC-01"]


def test_build_roadmap_phases_real_fields() -> None:
    recs = [
        _rec("REC-04", phase=1, effort_band="MEDIUM",
             uplift_per_pillar={"P4": 0.8},
             feature="Data Cloud",
             outcomes={"time": "6-9 months", "effort": "M",
                       "metric": "Single customer view across 3 cores",
                       "peer": "Synovus"},
             target_subcap_ids=["P4C1.1.1", "P4C1.2.1"]),
        _rec("REC-07", phase=2, effort_band="MEDIUM",
             platform_id="twilio", platform_name="Twilio",
             prerequisite_rec_ids=["REC-04"],
             outcomes={"time": "9-12 months", "effort": "M",
                       "metric": "Branch deflection: +18pts", "peer": None},
             target_subcap_ids=["P2C1.1.1"]),
    ]
    phases = build_roadmap_phases(recs, {"P4C1": 2.1, "P2C1": 2.7})
    assert len(phases) == 2

    p1 = phases[0]
    # target from before/after on the top-uplifted category
    assert p1["target"] == "M2 → M3 in P4C1"
    # metric = the top extracted outcome metric, NOT the rec title
    assert p1["metric"] == "Single customer view across 3 cores"
    assert p1["platform"] == "Salesforce"
    assert p1["customer_impact"], "customer impact KVs present"
    assert p1["dependencies"] == []
    rec_entry = p1["recommendations"][0]
    assert rec_entry["feature"] == "Data Cloud"
    assert rec_entry["maturity_lift"] == "+0.8"

    p2 = phases[1]
    # cross-phase dependency surfaces (REC-07 depends on phase-1 REC-04)
    assert p2["dependencies"] == ["REC-04"]
    assert p2["customer_impact"]["Branch deflection"] == "+18pts"


def test_roadmap_starts_at_phase_one_even_without_quick_wins() -> None:
    """2026-07-06 operator report: 91/94 roadmaps started at Phase 2/3 because
    the emit loop shipped absolute effort-tier numbers. A run whose recs are all
    Foundational/Strategic must still begin at display Phase 1, with the tier
    preserved in the label (Bank of Utah class)."""
    recs = [
        _rec("REC-01", phase=2, effort_band="MEDIUM",
             uplift_per_pillar={"P4": 0.6}, target_subcap_ids=["P4C1.1.1"]),
        _rec("REC-02", phase=3, effort_band="LARGE",
             uplift_per_pillar={"P2": 0.4}, target_subcap_ids=["P2C1.1.1"]),
    ]
    phases = build_roadmap_phases(recs, {"P4C1": 2.1, "P2C1": 2.7})
    assert [p["phase"] for p in phases] == [1, 2], "contiguous, 1-based"
    # tier label preserved — this roadmap is genuinely Foundational-first
    assert phases[0]["name"] == "Foundational"
    assert phases[1]["name"] == "Strategic"


def test_maturity_lift_mined_from_metric_when_uplift_missing() -> None:
    """The audit's maturity_lift-null-89%: the corpus quantifies its own
    lift inside the outcome metric ('1.18 → 2.0')."""
    recs = [
        _rec("REC-01", phase=1,
             outcomes={"time": None, "effort": None,
                       "metric": "P1C1 score: 1.18 → 2.0", "peer": None},
             title="Digital Strategy Workshop for P1C1"),
    ]
    phases = build_roadmap_phases(recs, {"P1C1": 1.18})
    entry = phases[0]["recommendations"][0]
    assert entry["maturity_lift"] == "+0.82"
    # And the mined category feeds the phase target.
    assert phases[0]["target"] == "M1 → M2 in P1C1"


def test_maturity_lift_ladder_falls_back_to_scores() -> None:
    """The maturity_lift-null-86% fix: when a rec carries neither uplift nor
    an 'a -> b' metric, the lift is grounded on the target subcap / mined
    category / platform-pillar score (M4 - current)."""
    cat = {"P4C1": 2.1, "P2C1": 2.7, "P2C4": 1.5}
    sub = {"P4C1.1.1": 1.6, "P4C1.2.1": 2.4}
    # 1. target subcap -> M4 - worst(1.6) = 2.4
    r1 = _rec(
        "REC-01", uplift_per_pillar=None,
        outcomes={"time": None, "effort": None, "metric": None, "peer": None},
        target_subcap_ids=["P4C1.1.1", "P4C1.2.1"], platform_id="databricks",
    )
    assert _rec_maturity_lift(r1, None, cat, sub) == 2.4
    # 2. mined category in the title -> M4 - 1.5 = 2.5
    r2 = _rec("REC-02", title="Close the P2C4 governance gap",
              target_subcap_ids=[], platform_id="")
    assert _rec_maturity_lift(r2, None, cat, sub) == 2.5
    # 3. no subcap/category signal → platform pillar's worst category.
    #    twilio → P2; worst P2 category is P2C4 (1.5) → 2.5
    r3 = _rec("REC-03", title="Untitled initiative", platform_id="twilio",
              target_subcap_ids=[])
    assert _rec_maturity_lift(r3, None, cat, sub) == 2.5
    # 4. genuinely uncomputable (no signal, no scored pillar) → None.
    r4 = _rec("REC-04", title="Nothing scored here", platform_id="")
    assert _rec_maturity_lift(r4, None, cat, sub) is None


def test_build_roadmap_phases_emits_lift_from_scores() -> None:
    """End-to-end through build_roadmap_phases: a metric-less rec still gets
    a non-null maturity_lift from its target subcap score."""
    recs = [_rec("REC-01", phase=1, effort_band="MEDIUM",
                 platform_id="databricks", platform_name="Databricks",
                 target_subcap_ids=["P4C1.1.1"])]
    phases = build_roadmap_phases(recs, {"P4C1": 2.1}, {"P4C1.1.1": 1.6})
    assert phases[0]["recommendations"][0]["maturity_lift"] == "+2.4"


def test_duration_is_parallel_max_not_sum() -> None:
    recs = [
        _rec("REC-01", phase=1, effort_band="MEDIUM"),
        _rec("REC-02", phase=1, effort_band="MEDIUM"),
        _rec("REC-03", phase=1, effort_band="LARGE"),
    ]
    phases = build_roadmap_phases(recs, {})
    assert phases[0]["duration_months"] == 8, (
        "recs in one phase run in parallel — the phase lasts as long as "
        "its longest rec (LARGE=8), not the 16-month sum"
    )


def test_empty_recs_yield_no_phases() -> None:
    assert build_roadmap_phases([], {}) == []
