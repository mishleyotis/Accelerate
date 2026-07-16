"""Platform fit REASONING (2026-07-06 mandate) — pure-logic contract.

Pins:
  - stack-mention classification: in-use / absent / planned polarity is
    sentence-scoped, verbatim, E-ID-cited;
  - the greenfield (absent-boost) correction ladder: evidence saying the
    family is IN USE removes the boost even when tech_stack_entries
    missed it; small-scale entities on heavy platforms get the
    documented dampener; confirmed absence keeps the boost;
  - the engine folds the reasoned boost in and persists an auditable
    ``reasoning`` record (factor → points → detail → subcap/E-IDs);
  - the deterministic card narrative quotes the entity's own evidence
    verbatim with E-IDs and never fabricates;
  - opportunity areas rank categories by summed engine contribution.
"""
from __future__ import annotations

from app.services.platform_fit import (
    SubcapForFit,
    compute_platform_fit_v2,
)
from app.services.platform_fit_data import (
    FAMILY_PRODUCTS,
    PLATFORM_FAMILY_PATTERNS,
)
from app.services.platform_signals import (
    SMALL_SCALE_ABSENT_DAMP,
    StackSignal,
    absent_boost_adjustment,
    classify_stack_mentions,
    evidence_confirms_in_use,
    scale_context,
)
from app.services.platform_story import (
    compose_platform_narrative,
    opportunity_areas_from_breakdown,
)

_PIDS = list(PLATFORM_FAMILY_PATTERNS.keys())


# ── classify_stack_mentions ────────────────────────────────────────────

def test_in_use_mention_is_classified_and_verbatim():
    rows = [("E-101", "The bank deployed Tableau in 2025; 1,800 users are live.")]
    out = classify_stack_mentions(
        rows, family_patterns=PLATFORM_FAMILY_PATTERNS,
        family_products=FAMILY_PRODUCTS,
    )
    sigs = out["tableau"]
    assert len(sigs) == 1
    assert sigs[0].polarity == "in_use"
    assert sigs[0].e_id == "E-101"
    # verbatim — the sentence survives untouched
    assert sigs[0].excerpt == "The bank deployed Tableau in 2025; 1,800 users are live."


def test_absent_mention_beats_usage_verbs_in_same_sentence():
    rows = [("E-047", "The firm has no Salesforce instance; profiles are stitched manually.")]
    out = classify_stack_mentions(
        rows, family_patterns=PLATFORM_FAMILY_PATTERNS,
    )
    assert out["salesforce"][0].polarity == "absent"


def test_planned_mention():
    rows = [("E-060", "Leadership is evaluating Databricks for risk decisioning.")]
    out = classify_stack_mentions(rows, family_patterns=PLATFORM_FAMILY_PATTERNS)
    assert out["databricks"][0].polarity == "planned"


def test_mention_scoping_is_per_sentence_not_per_excerpt():
    # The negation lives in the FIRST sentence; the nCino mention in the
    # second must not inherit it.
    rows = [(
        "E-071",
        "There is no CDP in place. The nCino migration went live in March.",
    )]
    out = classify_stack_mentions(rows, family_patterns=PLATFORM_FAMILY_PATTERNS)
    assert out["ncino"][0].polarity == "in_use"


def test_dedup_one_signal_per_eid_polarity():
    rows = [
        ("E-101", "Tableau is deployed. Tableau dashboards are used daily."),
    ]
    out = classify_stack_mentions(rows, family_patterns=PLATFORM_FAMILY_PATTERNS)
    assert len(out["tableau"]) == 1


# ── absent_boost_adjustment ladder ─────────────────────────────────────

def _sig(pid: str, polarity: str, e_id: str = "E-101") -> StackSignal:
    return StackSignal(platform_id=pid, e_id=e_id, polarity=polarity,
                       excerpt="x", products=[])


def test_in_use_evidence_removes_greenfield_boost():
    boost, reason, cites = absent_boost_adjustment(
        platform_id="tableau", base_absent=True,
        signals=[_sig("tableau", "in_use", "E-101")], scale=None,
    )
    assert boost == 0.0
    assert "in use" in reason
    assert cites == ["E-101"]
    assert evidence_confirms_in_use([_sig("tableau", "in_use")])


def test_family_in_stack_means_no_boost():
    boost, reason, cites = absent_boost_adjustment(
        platform_id="tableau", base_absent=False, signals=[], scale=None,
    )
    assert boost == 0.0 and reason is None and cites == []


def test_small_scale_dampens_heavy_platform_greenfield():
    scale = scale_context(200e6, 40)
    assert scale["band"] == "small"
    boost, reason, _ = absent_boost_adjustment(
        platform_id="databricks", base_absent=True, signals=[], scale=scale,
    )
    assert boost == SMALL_SCALE_ABSENT_DAMP
    assert "scale" in reason


def test_small_scale_does_not_dampen_moderate_platforms():
    scale = scale_context(200e6, 40)
    boost, _, _ = absent_boost_adjustment(
        platform_id="tableau", base_absent=True, signals=[], scale=scale,
    )
    assert boost == 1.0


def test_confirmed_absence_keeps_full_boost_with_citation():
    boost, reason, cites = absent_boost_adjustment(
        platform_id="twilio", base_absent=True,
        signals=[_sig("twilio", "absent", "E-047")],
        scale=scale_context(5e9, 900),
    )
    assert boost == 1.0
    assert "absent" in reason
    assert cites == ["E-047"]


def test_scale_context_honest_none():
    assert scale_context(None, None)["band"] is None


# ── engine fold-in + reasoning record ──────────────────────────────────

def _subcap(sid="P4C1.1.1", score=1.5, pid="salesforce", e_ids=None):
    return SubcapForFit(
        subcap_id=sid, current_score=score, platform_ids=[pid],
        linked_insight_severities=["high"], name="Data foundation",
        peer_median=2.8, category_id=sid[:4],
        evidence_e_ids=e_ids or ["E-047"], evidence_strength=0.8,
        evidence_tier=2,
    )


def test_engine_uses_reasoned_boost_and_persists_reasoning():
    rows = compute_platform_fit_v2(
        [_subcap()], ["salesforce"],
        readiness_by_platform={"salesforce": "green"},
        absent_families_by_platform={"salesforce": ["Salesforce"]},
        absent_boost_by_platform={"salesforce": 0.0},   # evidence said in-use
        absent_reason_by_platform={"salesforce": (
            "evidence names the family in use — greenfield boost removed",
            ["E-101"],
        )},
        stack_signals_by_platform={"salesforce": [
            {"platform_id": "salesforce", "e_id": "E-101",
             "polarity": "in_use", "excerpt": "Uses Salesforce.", "products": []},
        ]},
        scale={"band": "mid", "basis": "assets $2.0B", "aum_usd": 2e9,
               "headcount": None},
    )
    bd = rows[0].breakdown
    assert bd["factors"]["absent_boost"]["value"] == 0.0
    assert bd["stack_signals"][0]["e_id"] == "E-101"
    assert bd["scale"]["band"] == "mid"
    reasoning = bd["reasoning"]
    factors = [s["factor"] for s in reasoning]
    assert factors == ["opportunity", "interconnect", "absent_boost",
                       "scale", "readiness"]
    abs_step = next(s for s in reasoning if s["factor"] == "absent_boost")
    assert abs_step["e_ids"] == ["E-101"]
    assert "in use" in abs_step["detail"]
    opp_step = reasoning[0]
    assert opp_step["subcap_ids"] == ["P4C1.1.1"]
    assert "E-047" in opp_step["e_ids"]
    assert opp_step["points"] == bd["factors"]["opportunity"]["points"]


def test_engine_without_new_inputs_is_backward_compatible():
    legacy = compute_platform_fit_v2(
        [_subcap()], ["salesforce"],
        readiness_by_platform={"salesforce": "green"},
        absent_families_by_platform={"salesforce": ["Salesforce"]},
    )
    assert legacy[0].breakdown["factors"]["absent_boost"]["value"] == 1.0
    # the reasoning record exists even for legacy calls (engine state only)
    assert legacy[0].breakdown["reasoning"][0]["factor"] == "opportunity"
    assert "stack_signals" not in legacy[0].breakdown


# ── card narrative ─────────────────────────────────────────────────────

def _breakdown_for_narrative():
    rows = compute_platform_fit_v2(
        [_subcap()], ["salesforce"],
        readiness_by_platform={"salesforce": "amber"},
        absent_families_by_platform={"salesforce": ["Salesforce"]},
        absent_boost_by_platform={"salesforce": 1.0},
        absent_reason_by_platform={"salesforce": (
            "family confirmed absent from the detected stack — greenfield entry",
            ["E-052"],
        )},
        stack_signals_by_platform={"salesforce": [
            {"platform_id": "salesforce", "e_id": "E-052", "polarity": "absent",
             "excerpt": "There is no Salesforce instance; CRM is a homegrown tool.",
             "products": []},
        ]},
        scale={"band": "mid", "basis": "assets $2.0B", "aum_usd": 2e9,
               "headcount": None},
    )
    return rows[0]


def test_narrative_quotes_evidence_verbatim_with_e_ids():
    row = _breakdown_for_narrative()
    md = compose_platform_narrative(
        entity_name="Alma Bank",
        platform_name="Salesforce",
        fit_score=row.fit_score,
        readiness="amber",
        state=row.state,
        breakdown=row.breakdown,
        excerpts_by_e_id={
            "E-047": "The firm has no CDP; profiles are stitched manually across 4 systems.",
        },
        category_names={"P4C1": "Data Foundation"},
    )
    assert md is not None
    # ONE score anchor; peer relation in words, not a second number
    # (2026-07-14 operator mandate: the card opens on the story, not a
    # scorecard of three figures).
    assert "Alma Bank scores 1.5" in md
    assert "below the peer median" in md
    assert "2.8" not in md
    # greenfield sentence quotes the entity's own absence evidence
    assert '"There is no Salesforce instance; CRM is a homegrown tool." [E-052]' in md
    # the gap itself is quoted verbatim with its E-ID
    assert '"The firm has no CDP; profiles are stitched manually across 4 systems." [E-047]' in md
    assert "assets $2.0B" in md
    assert "Data Foundation" in md  # opportunity area names the category


def test_narrative_none_when_no_addressable_surface():
    assert compose_platform_narrative(
        entity_name="X", platform_name="Y", fit_score=0.0,
        readiness="amber", state="INSUFFICIENT_EVIDENCE", breakdown={},
    ) is None


def test_narrative_no_fabricated_quotes():
    """Excerpts not supplied ⇒ no quote sentence — the composer never
    invents evidence text."""
    row = _breakdown_for_narrative()
    md = compose_platform_narrative(
        entity_name="Alma Bank", platform_name="Salesforce",
        fit_score=row.fit_score, readiness="amber", state=row.state,
        breakdown={**row.breakdown, "stack_signals": []},
        excerpts_by_e_id={},
    )
    assert md is not None
    assert "the record states" not in md


# ── opportunity areas ──────────────────────────────────────────────────

def test_opportunity_areas_rank_by_summed_contribution():
    bd = {
        "top_subcaps": [
            {"subcap_id": "P4C1.1.1", "name": "Data foundation",
             "opportunity": 0.5, "e_ids": ["E-1"]},
            {"subcap_id": "P4C1.2.1", "name": "Data quality",
             "opportunity": 0.3, "e_ids": ["E-2"]},
            {"subcap_id": "P2C2.1.1", "name": "Digital service",
             "opportunity": 0.4, "e_ids": []},
        ],
    }
    areas = opportunity_areas_from_breakdown(
        bd, {"P4C1": "Data Foundation", "P2C2": "Service Model"},
    )
    assert [a["category_id"] for a in areas] == ["P4C1", "P2C2"]
    assert areas[0]["name"] == "Data Foundation"
    assert areas[0]["opportunity"] == 0.8
    assert areas[0]["subcap_ids"] == ["P4C1.1.1", "P4C1.2.1"]
    assert areas[0]["e_ids"] == ["E-1", "E-2"]


def test_opportunity_areas_empty_for_empty_breakdown():
    assert opportunity_areas_from_breakdown(None) == []
    assert opportunity_areas_from_breakdown({"top_subcaps": []}) == []
