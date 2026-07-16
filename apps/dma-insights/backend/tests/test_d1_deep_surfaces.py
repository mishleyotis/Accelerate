"""D1 deep-surface engines (plan Part 4 + AE-depth contract Part D).

Pure-logic tests for the 2026-07-02 rebuild: the SCQA composition contract,
W/W/SW finding decomposition, the readiness-driven opportunity_md, why-now
deep-field helpers, the financial trajectory/sentiment/leadership/evidence
surface builders, and the prose-key kill in package_financials.
"""
from __future__ import annotations

import re

from app.scripts.derive_evidence_surfaces import (
    build_coverage_stats,
    build_evidence_summary,
    normalize_register_rows,
    synthesize_band,
)
from app.scripts.derive_financials import build_trajectory, compute_cagr
from app.scripts.derive_leadership import (
    enrich_roster,
    tenure_months_of,
    tl_from_evidence,
)
from app.scripts.derive_sentiment import normalize_sentiment
from app.services import startup_enrich as se
from app.services.nlp.quality import markdown_lint, rubric_score
from app.services.parsers.package_financials import (
    is_sane_metric_key,
    sanitize_metric_keys,
)

# ── compose_opportunity_md: readiness from readiness_index, never state ──────

_CARD = {
    "display_name": "Salesforce", "platform_id": "salesforce", "pillar": "P2",
    "fit_score": 82.0, "state": "READY",  # the dead field — must be ignored
    "addressable_subcap_ids": ["P2C1.1", "P2C2.3", "P2C3.4"],
    "fit_breakdown": {
        "top_subcaps": [
            {"subcap_id": "P2C1.1", "name": "Omnichannel Orchestration",
             "score": 1.9, "peer_median": 2.8},
            {"subcap_id": "P2C2.3", "name": "Next-Best-Action"},
        ],
        "absent_families": ["CDP", "Marketing Automation"],
    },
}


def test_opportunity_md_blocked_readiness_never_says_ready() -> None:
    md = se.compose_opportunity_md({**_CARD, "readiness_index": 25.0})
    assert md is not None
    assert "blocked on prerequisites" in md
    assert "currently ready" not in md
    # entity facts: the named top-opportunity subcaps + absent family. Per the
    # S13 mandate the precise subcap score-vs-peer stays OUT of the card prose
    # (it renders as the card's own stat); the prose names the opportunity and
    # frames the peer gap qualitatively.
    assert "Omnichannel Orchestration" in md
    assert "trail the peer benchmark" in md
    assert "CDP" in md


def test_opportunity_md_bands() -> None:
    ready = se.compose_opportunity_md({**_CARD, "readiness_index": 88})
    near = se.compose_opportunity_md({**_CARD, "readiness_index": 55})
    assert "deployable now" in (ready or "")
    assert "near-ready" in (near or "")
    # readiness unmeasured → no posture clause, never a fabricated one
    unmeasured = se.compose_opportunity_md(dict(_CARD))
    assert unmeasured is not None and "readiness" not in unmeasured


def test_opportunity_md_honest_blanks() -> None:
    assert se.compose_opportunity_md({"state": "INSUFFICIENT_EVIDENCE"}) is None
    assert se.compose_opportunity_md({"display_name": "X"}) is None  # no surface


def test_opportunity_md_diversifies_with_unmet_prereq() -> None:
    md = se.compose_opportunity_md({
        **_CARD, "readiness_index": 45,
        "prereq_checks": [{"name": "Data foundation ≥ 2.5", "status": "UNMET",
                           "current_score": 2.1, "threshold": 2.5}],
    })
    assert md is not None and "Data foundation" in md and "2.1" in md


def test_opportunity_md_never_leaks_platform_or_pillar_code() -> None:
    """2026-07-15 cohesion mandate: prose surfaces the platform DISPLAY name and
    the pillar LABEL, never the raw code (`data_cloud` / bare `P2`)."""
    md = se.compose_opportunity_md({
        "platform_id": "data_cloud", "pillar": "P2", "state": "READY",
        "addressable_subcap_ids": ["P2C1.1"], "readiness_index": 88.0,
        "fit_breakdown": {"top_subcaps": [{"subcap_id": "P2C1.1",
            "name": "Omnichannel Orchestration", "score": 1.9, "peer_median": 2.8}],
            "absent_families": ["CDP"]},
    }, entity_key="AcmeBank")
    assert md is not None
    assert "data_cloud" not in md and "Data Cloud" in md   # display name, not code
    assert not re.search(r"\bP2\b", md)                     # no bare pillar code
    assert "customer experience" in md                      # pillar label instead
    # the shared display helpers (used across composers) are leak-proof
    assert se.pillar_prose("P4") == "data and technology"
    assert se.pillar_prose("nonsense") == ""                # unknown -> drop, never leak
    assert se.platform_display_name("salesforce") == "Salesforce"
    assert se.platform_display_name("financial_services_cloud") == "Financial Services Cloud"


# ── W/W/SW finding decomposition ─────────────────────────────────────────────

def test_finding_wwsw_decomposes_causal_prose() -> None:
    body = ("Loan origination is still substantially manual because hand-offs "
            "are tracked in email. The bank should activate the workflow "
            "engine it already owns.")
    out = se.finding_wwsw("Loan origination", body, "P3C2.1", 2.1, 2.9,
                          platform="nCino")
    assert "manual" in out["what"].lower()
    assert "email" in out["why"].lower()
    assert "workflow engine" in out["so_what"].lower()
    assert out["theme"] == "Operations"
    assert out["magnitude"] is not None


def test_finding_wwsw_fallbacks_are_grounded_not_generic() -> None:
    out = se.finding_wwsw("Data Foundation", "Three cores run in parallel.",
                          "P4C1", 1.8, 2.6,
                          evidence_excerpt="The 10-K discloses three production core systems retained through acquisitions")
    # WHY falls back to the linked evidence excerpt (real cause material)
    assert "10-K" in out["why"]
    assert out["magnitude"] == "0.8 pts below peer median"
    # at/above-peer → protect framing, never "priority gap"
    strong = se.finding_wwsw("Analytics", "Tableau adoption is broad.",
                             "P4C2", 3.4, 2.9)
    assert "protect" in strong["so_what"].lower()


# ── SCQA composition contract ────────────────────────────────────────────────

_BUNDLE = {
    "name": "First Example Bank", "label": "regional bank",
    "aum_usd": 9.8e9, "regulator": "FDIC", "headcount": 1640,
    "founded": 1934, "overall": 2.6, "trend": "ACCELERATING",
    "cagr_pct": 10.4, "ratio_bits": ["ROA 1.15%", "efficiency 54.20%"],
    "fin_eids": ["E-047"],
    "gaps": [
        {"name": "Data Foundation", "cat": "P4C1", "score": 1.9, "peer": 2.8,
         "eids": ["E-141", "E-047"]},
        {"name": "AI & Decisioning", "cat": "P4C3", "score": 2.0, "peer": 2.7,
         "eids": ["E-283"]},
    ],
    "strengths": [{"name": "Analytics & BI", "score": 3.4, "peer": 2.9}],
    "issues": [{"title": "Open AML consent order remediation through Q4 2026",
                "severity": "high", "eids": ["E-218"]}],
    "leadership": {"new_hires": [("Dana Field", "Chief Data Officer")],
                   "gap_roles": [], "n": 7},
    "platforms": [{"name": "Salesforce", "fit": 82.0,
                   "top_subcap": "Omnichannel Orchestration"},
                  {"name": "Databricks", "fit": 74.0, "top_subcap": None}],
    "focus_quote": "Unify the customer data layer ahead of the core go-live",
    "base_eids": ["E-001", "E-002", "E-003"],
}


def test_compose_scqa_deep_meets_the_contract() -> None:
    out = se.compose_scqa_deep(_BUNDLE)
    md = out["md"]
    assert len(md) <= 4000
    assert len(out["eids"]) >= 2
    assert len(out["families"]) >= 4
    assert md.count("\n\n") >= 2          # key message / case / plan
    # S13 mandate: the exec summary reads as narrative, not a score recap —
    # it carries at most ONE numeric maturity anchor (the binding gap, "1.9/5")
    # and the peer relation is stated in words ("runs behind its peer line"),
    # never a second recited "vs 2.8 peer median" number.
    assert "1.9/5" in md          # the single binding-gap numeric anchor
    assert "2.8" not in md        # peer standing carried qualitatively, not numerically
    assert "E-141" in md and "E-218" in md
    assert "Dana Field" in md
    assert "Salesforce" in md
    # no-firmographics-recap doctrine: the AUM figure never leads the
    # executive summary (the financial family rides the growth-trajectory
    # motion clause instead)
    assert "$9.8B" not in md
    assert "financials" in out["families"]
    assert markdown_lint(md) == []
    verdict = rubric_score(md, evidence_ids=out["eids"],
                           numbers_in_scope=out["numbers"])
    assert verdict["pass"], verdict


def test_compose_scqa_leads_with_key_message_never_firmographics() -> None:
    """2026-07-13 mandate: no firmographics recap in the executive summary,
    and the first paragraph carries the key message (the binding gap), not
    background."""
    out = se.compose_scqa_deep(_BUNDLE)
    md = out["md"]
    for recap in ("regulated by", "operating since", "employees",
                  "in assets", "$9.8B"):
        assert recap not in md, f"firmographics recap leaked: {recap}"
    first = md.split("\n\n")[0]
    assert "Data Foundation" in first          # the binding gap leads
    # style engine: deterministic per client, varied across clients
    assert md == se.compose_scqa_deep(_BUNDLE)["md"]
    openers = set()
    for i in range(12):
        b = dict(_BUNDLE)
        b["client_key"] = f"client-{i:04d}"
        openers.add(se.compose_scqa_deep(b)["md"][:60])
    assert len(openers) >= 4                   # styles + frame pools spread


def test_compose_scqa_rejects_topically_unrelated_gap_excerpt() -> None:
    """The incoherent-splice class: an excerpt that is not ABOUT the gap's
    capability must not be welded onto its score claim."""
    b = dict(_BUNDLE)
    b["gaps"] = [dict(_BUNDLE["gaps"][0],
                      excerpt="Cetera Financial Institutions partnered with "
                              "the bank to strengthen and grow the wealth "
                              "management program, Sep 15, 2025")]
    md = se.compose_scqa_deep(b)["md"]
    assert "Cetera" not in md and "wealth management program" not in md


def test_compose_scqa_grounding_floor_fires_for_unlinked_runs() -> None:
    sparse = dict(_BUNDLE)
    sparse["gaps"] = [{"name": "Data Foundation", "cat": "P4C1",
                       "score": 1.9, "peer": 2.8, "eids": []}]
    sparse["issues"] = []
    sparse["fin_eids"] = []
    out = se.compose_scqa_deep(sparse)
    # An unlinked run has no claim-relevant evidence, so it grounds on a SINGLE
    # best-tier anchor threaded onto the closing recommendation — not the old
    # hollow "evidence base reads the same way" filler, and NOT a 3-id tier dump
    # (2026-07-15 operator note: cite the most-relevant evidence, not many ids).
    assert len(out["eids"]) == 1
    assert "reads the same way" not in out["md"]
    assert "evidence base reads" not in out["md"].lower()
    assert "[[" not in out["md"]


def test_scqa_family_count_heuristic() -> None:
    assert se.scqa_family_count(_BUNDLE and se.compose_scqa_deep(_BUNDLE)["md"]) >= 4
    assert se.scqa_family_count("Just some text.") == 0


def test_scrub_unknown_eids_removes_dead_citations() -> None:
    md = "Real claim [E-047]. Quoted claim [E-999, E-047]."
    out = se.scrub_unknown_eids(md, {"E-047"})
    assert "E-999" not in out
    assert out.count("E-047") == 2
    assert "[]" not in out


def test_eid_regex_recognizes_corpus_variants() -> None:
    text = "cited E-047 and E0002 and E-INT-0003 and E-B1-001 and EV-12"
    found = se.extract_eids(text)
    for eid in ("E-047", "E0002", "E-INT-0003", "E-B1-001", "EV-12"):
        assert eid in found, found


# ── why-now deep-field helpers ───────────────────────────────────────────────

def test_wn_claim_and_strength_classes() -> None:
    assert se.wn_claim_class(["E-1"], 2, True) == "FACT"
    assert se.wn_claim_class(["E-1"], 5, False) == "INFERENCE"
    assert se.wn_claim_class([], None, False) == "HYPOTHESIS"
    assert se.wn_strength("core_migration", "FACT", True) == "STRONG"
    assert se.wn_strength("leadership", "INFERENCE", False) == "LEADING"
    assert se.wn_strength("market", "HYPOTHESIS", False) == "SUPPORTING"


def test_quarter_and_month_helpers() -> None:
    import datetime as dt
    assert se.quarter_label(dt.date(2026, 8, 1)) == "Q3 2026"
    assert se.add_months(dt.date(2026, 1, 31), 1) == dt.date(2026, 2, 28)
    assert se.add_months(dt.date(2025, 11, 3), 9).year == 2026


# ── package_financials: prose-keys die at the source ─────────────────────────

def test_prose_keys_die() -> None:
    assert not is_sane_metric_key(
        "this_revenue_mix_shift_toward_recurring_fee_income_is_the_execution")
    assert not is_sane_metric_key("mce_evidence_shows_that_security_finance")
    assert not is_sane_metric_key("e-p1c1")
    assert not is_sane_metric_key("vg")
    assert is_sane_metric_key("total_assets")
    assert is_sane_metric_key("Revenue ($B)")
    assert is_sane_metric_key("efficiency_ratio_pct")
    d = sanitize_metric_keys({
        "total_assets": 9.8, "lines": ["kept"], "series": {"2024": 1},
        "this_reduced_portfolio_sq_ft_but_lifted_per-sq-ft_metrics": "x",
    })
    assert set(d) == {"total_assets", "lines", "series"}


# ── derive_financials: trajectory + CAGR ─────────────────────────────────────

def test_compute_cagr() -> None:
    assert compute_cagr({2020: 100.0, 2024: 146.4}) is not None
    assert abs(compute_cagr({2020: 100.0, 2024: 146.4}) - 0.1) < 0.005
    assert compute_cagr({2024: 5.0}) is None
    assert compute_cagr({2020: 0.0, 2024: 5.0}) is None


def test_build_trajectory_shape() -> None:
    traj = build_trajectory(
        ta_series={2021: 9.8e9, 2022: 10.4e9, 2023: 11.1e9},
        ni_series={2021: 188e6, 2023: 199e6},
        branches=64, regulator="FDIC", geography="NY · NJ", headcount=1640,
        source="report_prose")
    assert traj is not None
    assert traj["fy"] == ["FY2021", "FY2022", "FY2023"]
    assert traj["series"]["total_assets"] == [9.8, 10.4, 11.1]
    assert traj["series"]["net_income_m"] == [188.0, None, 199.0]
    assert traj["unit"] == "B" and traj["currency"] == "USD"
    assert "assets" in traj["headline"] and "CAGR" in traj["headline"]
    # honest-null: a single period is not a trajectory
    assert build_trajectory(ta_series={2024: 1e9}, ni_series={},
                            branches=None, regulator=None, geography=None,
                            headcount=None, source="x") is None


def test_build_trajectory_series_consistency_guard() -> None:
    """Compeer regression (2026-07-06 deploy review): a $480M net-income
    figure joined the ~$30B total-assets series as 0.48. The guard must drop
    the cross-metric point (honest gap), record the anomaly, and keep the
    headline/CAGR computed from the surviving points."""
    traj = build_trajectory(
        ta_series={2021: 29.5, 2022: 30.8, 2023: 32.1, 2024: 0.48, 2025: 34.3},
        ni_series={2021: 385e6, 2022: 420e6, 2023: 455e6},
        branches=None, regulator="FCA", geography="Upper Midwest",
        headcount=1300, source="financial_highlights")
    assert traj is not None
    assert traj["series"]["total_assets"] == [29.5, 30.8, 32.1, None, 34.3]
    assert len(traj["anomalies"]) == 1 and "dropped" in traj["anomalies"][0]
    assert "$34.3B assets" in traj["headline"]

    # pure unit mistake (1000x off) is RESCUED, not dropped
    traj2 = build_trajectory(
        ta_series={2021: 9.5e9, 2022: 0.0102, 2023: 10.9e9},
        ni_series=None, branches=None, regulator=None, geography=None,
        headcount=None, source="x")
    assert traj2 is not None
    assert traj2["series"]["total_assets"][1] == 10.0
    assert "rescaled" in traj2["anomalies"][0]

    # clean series: no anomalies, values untouched
    traj3 = build_trajectory(
        ta_series={2021: 9.8e9, 2022: 10.4e9, 2023: 11.1e9},
        ni_series=None, branches=None, regulator=None, geography=None,
        headcount=None, source="x")
    assert traj3 is not None and traj3["anomalies"] == []
    assert traj3["series"]["total_assets"] == [9.8, 10.4, 11.1]


# ── derive_sentiment: normalized scorecard ───────────────────────────────────

def test_normalize_sentiment_scorecard() -> None:
    blob = {"sources": [
        {"source": "Glassdoor", "rating": "3.6/5",
         "signal": "Glassdoor rating 3.6/5 across 312 reviews"},
        {"source": "Indeed", "rating": "3.4", "signal": "Indeed rating"},
        {"source": "App Store", "rating": "2.4/5",
         "signal": "App Store rating 2.4/5 from 1,240 ratings"},
        {"source": "J.D. Power", "rating": "78%", "signal": "satisfaction 78%"},
        {"source": "CFPB complaints", "signal": "no rating here"},
    ]}
    out = normalize_sentiment(blob)
    assert out is not None and out["normalized"] is True
    emp = {r["source"]: r for r in out["employee"]}
    cus = {r["source"]: r for r in out["customer"]}
    assert emp["Glassdoor"]["score"] == 3.6 and emp["Glassdoor"]["scale"] == 5
    assert emp["Glassdoor"]["n"] == 312
    assert emp["Indeed"]["scale"] == 5          # bare 0-5 → 5-pt scale
    assert cus["App Store"]["n"] == 1240
    assert cus["App Store"].get("flag") == "below_peer"
    assert cus["J.D. Power"]["scale"] == 100    # % → 100-pt scale
    assert out["b2b_b2c_gap"] in (True, False)
    # sources[] preserved for the Context grid
    assert len(out["sources"]) == 5
    assert normalize_sentiment({"sources": []}) is None


# ── derive_leadership: flags + gap rows + TL guard ───────────────────────────

def test_enrich_roster_flags_and_gap_rows() -> None:
    roster = [
        {"name": "Dana Field", "title": "Chief Data Officer", "tenure": "2026-03"},
        {"name": "Sam Rivers", "title": "CEO", "tenure": "2012"},
    ]
    rows, gaps, enriched = enrich_roster(roster, entity_evidence_blob="")
    byname = {r.get("name"): r for r in rows}
    assert byname["Dana Field"]["critical_role"] is True
    assert byname["Dana Field"]["recent_hire"] is True
    assert byname["Sam Rivers"]["recent_hire"] is False
    assert byname["Dana Field"]["tenure_months"] is not None
    # CISO + CTO/CIO absent from roster AND evidence → explicit GAP rows
    gap_rows = [r for r in rows if r.get("gap_flag")]
    assert gaps >= 1 and gap_rows
    assert any("CISO" in str(r.get("title")) for r in gap_rows)
    # a CISO evidenced in the trail is NOT a gap
    rows2, gaps2, _ = enrich_roster(roster, "the CISO leads a team of 4")
    assert not any(str(r.get("title")) == "CISO" for r in rows2 if r.get("gap_flag"))


def test_tenure_months_of() -> None:
    assert tenure_months_of("2026-01") is not None
    assert tenure_months_of("3 years") == 36
    assert tenure_months_of("7 months") == 7
    assert tenure_months_of("n/a") is None


def test_tl_from_evidence_types_and_absence_guard() -> None:
    ev = [
        {"e_id": "E-1", "excerpt": "CEO Sam Rivers appeared on the Banking "
                                   "Transformed podcast discussing the core "
                                   "migration roadmap and data strategy.",
         "source_url": "https://example.com/pod", "published_date": "2026-02-01"},
        {"e_id": "E-2", "excerpt": "NEGATIVE SEARCH RESULT: no podcast "
                                   "appearances or conference talks found for "
                                   "any executive at the institution this year.",
         "source_url": None, "published_date": None},
    ]
    roster = [{"name": "Sam Rivers", "title": "CEO"}]
    items = tl_from_evidence(ev, roster, "Example Bank")
    assert len(items) == 1
    assert items[0]["type"] == "podcast"
    assert items[0]["author"] == "Sam Rivers"
    assert items[0]["e_id"] == "E-1"


# ── derive_evidence_surfaces builders ────────────────────────────────────────

def test_build_evidence_summary_histogram() -> None:
    rows = [
        {"tier": 1, "claim_type": "FACT", "excerpt": "launched a new platform",
         "source_name": "Explorium export", "linked_n": 3},
        {"tier": 3, "claim_type": "INFERENCE", "excerpt": "declining reviews",
         "source_name": "Glassdoor", "linked_n": 1},
        {"tier": 3, "claim_type": "FACT", "excerpt": "neutral note",
         "source_name": "10-K", "linked_n": 0},
    ]
    out = build_evidence_summary(rows)
    # enrichment-connector rows (Explorium/Clay/Indeed) never enter the
    # tier histogram — they inflated Bank of Utah's card to 95 items vs
    # the workbook's 81 (2026-07-06 deploy review); connectors-only listing.
    assert out["total_items"] == 2 and out["total_facts"] == 4
    assert out["tiers"] == {"T3": 2}
    assert out["derived_from"] == "evidence_index"
    assert out["claims"]["FACT"] == 2
    assert out["connectors"]["Explorium"] == 1
    assert set(out["signals"]) <= {"POSITIVE", "NEUTRAL", "NEGATIVE"}
    assert build_evidence_summary([]) is None


def test_build_coverage_stats() -> None:
    out = build_coverage_stats([
        {"pillar": "P1", "subcaps": 16, "scored": 16, "thin": 2},
        {"pillar": "P4", "subcaps": 10, "scored": 5, "thin": 5},
    ])
    assert out["overall_pct"] == 81
    p4 = next(p for p in out["by_pillar"] if p["pillar"] == "P4")
    assert p4["pct"] == 50 and p4["thin"] == 5
    assert out["gate_pct"] == 80
    assert build_coverage_stats([]) is None


def test_normalize_register_rows_shapes() -> None:
    rows = [
        {"cap_id": "P1C1.1", "ceiling_estimate": "L2.5 ±0.5", "coverage_pct": "40%",
         "no_evidence": "3", "capability": "Strategy Foundation"},
        {"cap_id": "P1C1.2", "ceiling_estimate": "L3.0 ±0.3"},
        {"cap_id": "P2C3.1", "base": "2.0", "band": 0.6, "note": "self-service gaps evidenced only by community signal"},
        {"cap_id": "not-a-cap"},
    ]
    out = normalize_register_rows(rows)
    assert set(out) == {"P1C1", "P2C3"}
    assert out["P1C1"]["ceiling"] == 2.8      # mean of 2.5 / 3.0 → 2.75 → 2.8
    assert any("coverage 40%" in m for m in out["P1C1"]["modifiers"])
    assert "community signal" in out["P2C3"]["rationale"]


def test_synthesize_band_names_real_modifiers() -> None:
    out = synthesize_band(
        cat="P4C1", cat_name="Data Foundation", avg_score=1.8, n_subcaps=10,
        thin_n=6, caps=[{"cap": True, "reason": "AML consent order caps at M3"}],
        eids=["E-218"])
    assert 1.0 <= out["ceiling"] <= 3.0
    assert any("consent order" in m for m in out["modifiers"])
    assert any("6 of 10" in m for m in out["modifiers"])
    assert "Data Foundation" in out["rationale"] and "1.8/5" in out["rationale"]
    assert out["evidence"] == ["E-218"]
    # boolean cap flag without a level never becomes "cap False"
    out2 = synthesize_band(cat="P1C1", cat_name="X", avg_score=2.0,
                           n_subcaps=4, thin_n=0,
                           caps=[{"cap": False, "reason": ""}], eids=[])
    assert out2["ceiling"] >= 2.0
    assert not any("False" in m for m in out2["modifiers"])


def test_readiness_phrase_bands() -> None:
    assert "deployable now" in se.readiness_phrase(85)
    assert "near-ready" in se.readiness_phrase(50, unmet_count=2)
    assert "blocked" in se.readiness_phrase(20)
    assert se.readiness_phrase(None) is None
    assert se.readiness_phrase("n/a") is None


def test_wn_category_map() -> None:
    assert se.wn_category("MIGRATION") == "core_migration"
    assert se.wn_category("HIRING") == "hiring"
    assert se.wn_category("anything-else") == "market"


def test_clip_sentence_boundary_never_cuts_midword() -> None:
    long = ("A sentence about the bank. " * 300).strip()
    out = se.clip_sentence_boundary(long, 4000)
    assert len(out) <= 4000
    assert re.search(r"\.$", out)


def test_finding_wwsw_what_closes_on_peer_context() -> None:
    """ASK-OV6-2: when the finding's own prose carries no peer context,
    the WHAT gains a closer grounded in the run's exact score / peer
    median / delta — and the composed blocks stay clear of every banned
    rehearsed skeleton."""
    from app.scripts.countercheck_pack import TEMPLATE_RES

    out = se.finding_wwsw(
        "Loan origination",
        "Loan origination is still substantially manual because hand-offs "
        "are tracked in email. The bank should activate the workflow "
        "engine it already owns.",
        "P3C2.1", 2.1, 2.9, platform="nCino")
    blob = f"{out['what']} {out['why']} {out['so_what']}"
    assert "peer" in out["what"].lower() or "median" in out["what"].lower()
    assert "2.9/5" in out["what"] and "2.1/5" in out["what"]
    assert "0.8" in out["what"]  # the exact run delta, not a rounded invention
    assert not any(rx.search(blob) for rx in TEMPLATE_RES)

    # shape varies by measured standing: a lead reads as a lead
    ahead = se.finding_wwsw("Analytics", "Tableau adoption is broad.",
                            "P4C2", 3.4, 2.9)
    assert "ahead" in ahead["what"].lower()
    assert not any(rx.search(ahead["so_what"]) for rx in TEMPLATE_RES)

    # no peer data -> no closer, never a fabricated number
    bare = se.finding_wwsw("Analytics", "Tableau adoption is broad.", "P4C2",
                           3.4, None)
    assert "median" not in bare["what"].lower()

    # prose that already carries peer context is left alone
    owned = se.finding_wwsw(
        "Analytics",
        "Adoption trails the peer cohort median on the latest workbook "
        "because dashboard access is limited to head office.",
        "P4C2", 2.2, 3.0)
    assert owned["what"].count("median") <= 1


def test_finding_wwsw_peer_closer_respects_what_budget() -> None:
    """A long WHAT is re-clipped at a sentence boundary so the 600-char
    cap never severs the peer closer mid-sentence."""
    body = " ".join(
        f"Observation {i} records a distinct manual hand-off in the "
        f"origination path documented by the assessment." for i in range(12)
    ) + " This persists because hand-offs are tracked in email."
    out = se.finding_wwsw("Loan origination", body, "P3C2.1", 2.1, 2.9)
    assert len(out["what"]) <= 600
    assert out["what"].rstrip().endswith((".", "!", "?"))
    assert "median" in out["what"].lower()
