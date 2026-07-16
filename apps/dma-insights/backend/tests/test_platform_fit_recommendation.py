"""Recommendation-driven platform fit (2026-07-15 rework) — pure-logic.

Pins the inversion: a family the ASSESSMENT recommended outranks (and leads
the sequence over) a family it did not, the analyst's most-urgent product
leads, and the requested factors (integration effort, strategic-objective
alignment, L3/L4 coverage) move the fit. No DB — exercises the pure engine.
"""
from __future__ import annotations

from app.services.platform_fit import (
    PlatformFitV2Row,
    RecSignal,
    SubcapForFit,
    apply_recommendation_fit,
    compute_sequence_ranks,
)


def _row(pid, fit, addr=("P2C1.1.1",)):
    return PlatformFitV2Row(
        platform_id=pid, fit_score=fit, state="READY", readiness="green",
        addressable_subcap_ids=list(addr), evidence_strength=0.6, breakdown={})


def _subcaps():
    # a genuinely deficient subcap (score 1.0 vs peer 2.5)
    return [SubcapForFit(subcap_id="P2C1.1.1", current_score=1.0,
                         platform_ids=[], linked_insight_severities=[],
                         name="Origination", peer_median=2.5, category_id="P2C1")]


def test_recommended_family_outranks_unrecommended():
    # databricks has the higher RAW gap-fit, but the analyst recommended
    # salesforce — after the override salesforce must win.
    rows = [_row("databricks", 85.0), _row("salesforce", 60.0)]
    sig = {
        "salesforce": RecSignal(
            recommended=True, best_priority=0, rec_count=4,
            lead_product="Financial Services Cloud",
            lead_product_id="financial_services_cloud",
            so_count=2, evidence_count=5, effort_band="MEDIUM",
            deficient_subcaps=("P2C1.1.1",)),
        # databricks NOT recommended → no signal entry
    }
    out = apply_recommendation_fit(rows, sig, _subcaps())
    by = {r.platform_id: r for r in out}
    assert by["salesforce"].fit_score > by["databricks"].fit_score
    assert by["salesforce"].breakdown["recommendation"]["recommended"] is True
    assert by["salesforce"].breakdown["recommendation"]["lead_product"] == "Financial Services Cloud"
    assert by["databricks"].breakdown["recommendation"]["recommended"] is False


def test_priority_drives_the_lead_between_two_recommended():
    rows = [_row("salesforce", 50.0), _row("tableau", 50.0)]
    sig = {
        "salesforce": RecSignal(recommended=True, best_priority=0, rec_count=3,
                                lead_product="Data Cloud", deficient_subcaps=("P2C1.1.1",)),
        "tableau": RecSignal(recommended=True, best_priority=4, rec_count=1,
                             lead_product="Tableau", deficient_subcaps=("P2C1.1.1",)),
    }
    apply_recommendation_fit(rows, sig, _subcaps())
    ranks = compute_sequence_ranks(
        platform_ids=["salesforce", "tableau"],
        unmet_prereq_subcaps={}, addressable_by_platform={"salesforce": ["P2C1.1.1"], "tableau": ["P2C1.1.1"]},
        rec_priority_by_platform={"salesforce": 0, "tableau": 4},
        fit_by_platform={r.platform_id: r.fit_score for r in rows})
    assert ranks["salesforce"] < ranks["tableau"]          # P0 leads P4


def _sig(effort):
    return RecSignal(recommended=True, best_priority=1, rec_count=2, so_count=1,
                     evidence_count=3, deficient_subcaps=("P2C1.1.1",),
                     effort_band=effort)


def test_integration_effort_is_a_headwind():
    low = apply_recommendation_fit([_row("salesforce", 50)],
                                   {"salesforce": _sig("LOW")}, _subcaps())
    high = apply_recommendation_fit([_row("salesforce", 50)],
                                    {"salesforce": _sig("HIGH")}, _subcaps())
    assert low[0].fit_score > high[0].fit_score            # HIGH effort discounts fit


def test_none_signal_is_graceful_noop():
    rows = [_row("salesforce", 42.0)]
    out = apply_recommendation_fit(rows, None, _subcaps())
    assert out[0].fit_score == 42.0                        # untouched


# ── 2026-07-15 structural guarantees (root-cause fixes from the 5-writeup QA) ──

def test_residual_compressed_below_weakest_recommended():
    """A structural invariant: even when the recommended family's composite is
    WEAK (no numeric priority, thin signals), it must still out-score a
    high-fit family the assessment never recommended — the residual band is
    compressed strictly beneath the lowest recommended fit. (Empower: a Tableau
    residual edged the recommended Salesforce composite before this landed.)"""
    rows = [_row("databricks", 90.0), _row("salesforce", 50.0)]
    sig = {
        # deliberately weak: worst priority, zero SO/evidence → tiny composite
        "salesforce": RecSignal(recommended=True, best_priority=8, rec_count=1,
                                lead_product="Service Cloud", so_count=0,
                                evidence_count=0, deficient_subcaps=("P2C1.1.1",)),
    }
    out = apply_recommendation_fit(rows, sig, _subcaps())
    by = {r.platform_id: r for r in out}
    assert by["salesforce"].fit_score > by["databricks"].fit_score
    assert by["databricks"].breakdown["recommendation"].get(
        "compressed_below_recommended") is True


def test_unrecommended_prereq_never_leads_the_sequence():
    """The sequence partition: an unrecommended family that addresses an unmet
    prerequisite of the recommended family must NOT lead the sequence — the
    prereq edge cannot pull it ahead of a recommended family (Sunflower: an
    unrecommended nCino prereq wrongly led rank 1)."""
    ranks = compute_sequence_ranks(
        platform_ids=["ncino", "salesforce"],
        # ncino addresses P2C1.1.1, which is an unmet prereq of salesforce
        unmet_prereq_subcaps={"salesforce": ["P2C1.1.1"]},
        addressable_by_platform={"ncino": ["P2C1.1.1"], "salesforce": ["P9C9.9.9"]},
        rec_priority_by_platform={"salesforce": 2},   # only salesforce recommended
        fit_by_platform={"salesforce": 50.0, "ncino": 20.0})
    assert ranks["salesforce"] == 1
    assert ranks["ncino"] == 2


def test_sequence_partition_noop_when_nothing_recommended():
    """No recommendation read → prior DAG behaviour (graceful)."""
    ranks = compute_sequence_ranks(
        platform_ids=["ncino", "salesforce"],
        unmet_prereq_subcaps={"salesforce": ["P2C1.1.1"]},
        addressable_by_platform={"ncino": ["P2C1.1.1"], "salesforce": ["P9C9.9.9"]},
        rec_priority_by_platform={},                  # nothing recommended
        fit_by_platform={"salesforce": 50.0, "ncino": 20.0})
    # ncino gates salesforce via the prereq edge → ncino leads (unchanged)
    assert ranks["ncino"] == 1


class _FakeRec:
    def __init__(self, **kw):
        self.zennify_product = kw.get("zennify_product")
        self.priority_rank = kw.get("priority_rank")
        self.rec_id = kw.get("rec_id")
        self.platform_id = kw.get("platform_id")
        self.strategic_objectives = kw.get("strategic_objectives")
        self.root_cause_e_ids = kw.get("root_cause_e_ids")
        self.effort_band = kw.get("effort_band", "LOW")
        self.target_subcap_ids = kw.get("target_subcap_ids")
        self.prerequisite_rec_ids = kw.get("prerequisite_rec_ids")


def test_list_order_priority_fallback_when_rank_missing():
    """The lettered-schema recs ship NO numeric priority_rank. The signal builder
    must fall back to the REC-NN ordinal (most-urgent-first) so the composite's
    priority factor is not cratered — and REC-01's product leads."""
    from app.services.platform_fit_data import _build_rec_signal
    recs = [
        _FakeRec(rec_id="REC-01", zennify_product="service_cloud", priority_rank=None),
        _FakeRec(rec_id="REC-02", zennify_product="marketing_cloud", priority_rank=None),
    ]
    sig = _build_rec_signal(recs)
    assert "salesforce" in sig
    # REC-01 → best_priority 1 (not the old worst-case default of 6)
    assert sig["salesforce"].best_priority == 1
