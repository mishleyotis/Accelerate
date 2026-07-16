"""Deploy-review wave 2 — the wrong-numbers defect family (2026-07-06).

Regression tests for the diagnosed classes, pinned to the REAL corpus
fixtures wherever the defect was measured:

  * trajectory hardening — external-anchor validation for 2-point series
    (southstate/empower class), whole-series cross-field scale mismatch
    (alliant/american-homes/exchange-bank class), future-fiscal-year
    clamp (vestgen FY2028), NCUA raw-thousands mining (chemung class);
  * the Gemini outlier-confirm rung (financial_series_confirm) —
    acceptor gating + verdict application, deterministic-when-cold;
  * sentiment numbers — clause-local decimal-aware NPS (LPL "$11.0B" /
    ima / guaranteed-rate 9.7), NPS as its own metric kind (compeer
    22/100 BELOW PEER), cohort-from-context (american-homes Employee
    NPS), percent employee ratings (compeer Glassdoor 79%), qualitative
    rows instead of the 62% drop, and the Context tile n=22 misfile;
  * evidence tier card — the workbooks' own per-evidence histograms
    (compeer/spokane exact; OZK Evidence_Master; FNBO no-T5) through the
    build_evidence_summary provenance ladder.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.scripts.derive_evidence_surfaces import build_evidence_summary
from app.scripts.derive_financials import apply_series_verdicts, build_trajectory
from app.scripts.derive_sentiment import _extract, normalize_sentiment
from app.scripts.enrich_corpus import _accept_series_verdicts, _unconfirmed_anomalies
from app.services.context_extras import financials_view, sentiment_view
from app.services.nlp.quantities import extract_metric_year_pairs

_FIXTURES = Path(__file__).parent / "fixtures" / "dma_packages_batches"
_WORKBOOKS = {
    "compeer": _FIXTURES / "batch_12" / "Compeer Financial - DMA"
    / "02_research_workbook" / "DMA_Research_Workbook_Compeer_Financial_20260305.xlsx",
    "spokane": _FIXTURES / "batch_10" / "Spokane Teachers Credit Union - DMA"
    / "02_research_workbook" / "STCU_Research_Workbook.xlsx",
    "ozk": _FIXTURES / "batch_14" / "OZK Bank - DMA"
    / "02_research_workbook" / "DMA_Research_Workbook_OZK_20260306.xlsx",
    "fnbo": _FIXTURES / "batch_10" / "First National Bank of Omaha - DMA"
    / "02_research_workbook" / "DMA_Research_Workbook_FNBO_20260518.xlsx",
}


def _traj(**kw):
    base = {"branches": None, "regulator": None, "geography": None,
            "headcount": None, "source": "test"}
    base.update(kw)
    return build_trajectory(**base)


# ── 1a. external-anchor validation (2-point series the median guard skips) ──

def test_two_point_series_anchor_drops_the_contradicted_point() -> None:
    """southstate class: net income [2.0, 2000] $M under a ~$45B anchor —
    $2.0M is an implausible 0.004% ROA; $2,000M sits in band. The wrong
    point drops (honest gap), the plausible one survives."""
    traj = _traj(ta_series=None, ni_series={2023: 2.0, 2024: 2000.0},
                 anchor_usd=45e9)
    assert traj is not None
    assert traj["series"]["net_income_m"] == [None, 2000.0]
    dropped = [d for d in traj["anomaly_details"] if d["action"] == "dropped"]
    assert dropped and dropped[0]["basis"] == "scale_anchor"


def test_two_point_series_anchor_rescues_pure_unit_mistake() -> None:
    """empower class: 4070 "M" under a ~$3.5B anchor is 4.07 after /1000 —
    a pure unit mistake is rescaled, never dropped."""
    traj = _traj(ta_series=None, ni_series={2021: 12.0, 2025: 4070.0},
                 anchor_usd=3.5e9)
    assert traj is not None
    assert traj["series"]["net_income_m"] == [12.0, 4.07]
    rescued = [d for d in traj["anomaly_details"] if d["action"] == "rescaled"]
    assert rescued and rescued[0]["basis"] == "scale_anchor"


def test_whole_series_cross_field_mismatch_is_suppressed() -> None:
    """alliant/exchange-bank class: every charted point is >5x off the
    firmographics anchor — nothing survives, the chart is an honest empty
    (returns None), never a wrong series."""
    assert _traj(ta_series={2019: 0.01, 2021: 0.11, 2023: 0.11},
                 ni_series=None, anchor_usd=3.31e9) is None
    # american-homes: [0.44, 0.48]B against an $11.7B balance sheet
    assert _traj(ta_series={2023: 0.44, 2024: 0.48},
                 ni_series=None, anchor_usd=11.7e9) is None


def test_anchored_series_in_band_is_untouched() -> None:
    traj = _traj(ta_series={2021: 29.5e9, 2022: 30.8e9, 2023: 32.1e9},
                 ni_series=None, anchor_usd=33.2e9)
    assert traj is not None
    assert traj["series"]["total_assets"] == [29.5, 30.8, 32.1]
    assert traj["anomalies"] == []


def test_unanchored_two_point_jump_is_flagged_not_dropped() -> None:
    """No external anchor → a >10x step cannot be adjudicated
    deterministically: both points chart, the step is FLAGGED for the
    Gemini confirm rung (real post-merger jumps exist)."""
    traj = _traj(ta_series={2020: 1.0, 2024: 14.0}, ni_series=None)
    assert traj is not None
    assert traj["series"]["total_assets"] == [1.0, 14.0]
    flagged = [d for d in traj["anomaly_details"] if d["action"] == "flagged"]
    assert flagged and flagged[0]["basis"] == "unanchored_step"


def test_size_tier_band_is_a_coarse_anchor() -> None:
    """A community-tier ($1-10B) entity charting a $500B point loses it
    even without an aum scalar."""
    traj = _traj(ta_series={2022: 2.1e9, 2023: 2.3e9, 2024: 500e9},
                 ni_series=None, size_tier="community")
    assert traj is not None
    assert traj["series"]["total_assets"][2] is None


# ── 1b. future fiscal years (vestgen FY2028 projection class) ────────────────

def test_future_fiscal_years_beyond_assessment_horizon_drop() -> None:
    traj = _traj(ta_series={2023: 4.1e9, 2024: 4.4e9, 2025: 4.8e9,
                            2028: 6.2e9},
                 ni_series=None, max_fy=2027)
    assert traj is not None
    assert traj["fy"] == ["FY2023", "FY2024", "FY2025"]
    proj = [d for d in traj["anomaly_details"]
            if d["basis"] == "assessment_horizon"]
    assert proj and proj[0]["fy"] == 2028
    assert any("FY2028" in a for a in traj["anomalies"])


# ── 1c. NCUA/call-report raw-thousands mining (chemung class) ────────────────

def test_ncua_thousands_convention_from_source_hint() -> None:
    t = ("Dec 31, 2024 NCUA call report: net income $518,000; "
         "total assets $2,912,000.")
    got = extract_metric_year_pairs(t)
    assert got["net_income"][2024] == 518_000_000.0
    assert got["total_assets"][2024] == 2_912_000_000.0


def test_thousands_harmonized_against_unit_carrying_cluster() -> None:
    """A unitless point ~1000x below the metric's unit-carrying cluster is
    the raw-thousands convention read literally — lifted, never mixed."""
    t = ("Net income 2023: $25.0M; net income 2022: $28.8M.\n"
         "Net income 2021: $26,400 (call report).")
    got = extract_metric_year_pairs(t)
    assert got["net_income"][2021] == 26_400_000.0
    assert got["net_income"][2023] == 25.0e6


def test_chemung_real_fixture_thousands_lines_parse_in_dollars() -> None:
    """The real Chemung evidence shape: '$2,710,529 thousand' carries its
    own unit and must land at $2.71B (never 2.7e6 or a mixed series)."""
    t = ("Total assets Dec 31 2023: $2,710,529 thousand; "
         "Dec 31 2022: $2,645,553 thousand (2.5% growth)")
    got = extract_metric_year_pairs(t)
    assert got["total_assets"] == {2023: 2_710_529_000.0,
                                   2022: 2_645_553_000.0}


# ── 2. Gemini outlier-confirm rung (financial_series_confirm) ────────────────

def _fh_with_anomaly() -> dict:
    traj = _traj(
        ta_series={2021: 29.5, 2022: 30.8, 2023: 32.1, 2024: 0.48, 2025: 34.3},
        ni_series=None, anchor_usd=33.2e9)
    assert traj is not None
    return {"trajectory": traj}


def test_unconfirmed_anomalies_excludes_horizon_drops() -> None:
    fh = _fh_with_anomaly()
    fh["trajectory"]["anomaly_details"].append(
        {"metric": "total_assets", "fy": 2028, "value": 6.2,
         "action": "dropped", "basis": "assessment_horizon", "note": "x"})
    pending = _unconfirmed_anomalies(fh)
    assert all(d["basis"] != "assessment_horizon" for d in pending)
    assert any(d["fy"] == 2024 for d in pending)


def test_accept_series_verdicts_gates_on_quote_and_arithmetic() -> None:
    fh = _fh_with_anomaly()
    details = _unconfirmed_anomalies(fh)
    excerpts = "[E-012] FY2024 total assets of $33.2 billion per the 10-K."
    out = json.dumps([
        # rescale x1000-bounded + verbatim quote → accepted
        {"metric": "total_assets", "fy": 2024, "verdict": "rescale",
         "value": 480.0, "quote": "total assets of $33.2 billion",
         "reason": "unit mistake"},
        # keep with a DIFFERENT value → rejected (fabrication)
        {"metric": "total_assets", "fy": 2024, "verdict": "keep",
         "value": 33.2, "quote": "total assets of $33.2 billion",
         "reason": "restated"},
        # unknown anomaly → rejected
        {"metric": "net_income_m", "fy": 2019, "verdict": "drop",
         "reason": "n/a"},
    ])
    accepted = _accept_series_verdicts(out, excerpts, details)
    assert len(accepted) == 1
    assert accepted[0]["verdict"] == "rescale" and accepted[0]["value"] == 480.0

    # keep must restate the flagged value; quotes must be verbatim
    out2 = json.dumps([{"metric": "total_assets", "fy": 2024,
                        "verdict": "keep", "value": 0.48,
                        "quote": "not in the excerpts", "reason": "r"}])
    assert _accept_series_verdicts(out2, excerpts, details) == []
    # drop is accepted with a reason and needs no quote (fail-closed default)
    out3 = json.dumps([{"metric": "total_assets", "fy": 2024,
                        "verdict": "drop", "reason": "figure unsupported"}])
    got3 = _accept_series_verdicts(out3, excerpts, details)
    assert got3 and got3[0]["verdict"] == "drop"


def test_apply_series_verdicts_reinstates_and_stamps() -> None:
    fh = _fh_with_anomaly()
    assert fh["trajectory"]["series"]["total_assets"][3] is None  # honest gap
    changed = apply_series_verdicts(fh, [
        {"metric": "total_assets", "fy": 2024, "verdict": "keep",
         "value": 33.2, "reason": "10-K restates FY2024 assets"},
    ])
    assert changed is True
    assert fh["trajectory"]["series"]["total_assets"][3] == 33.2
    stamped = [d for d in fh["trajectory"]["anomaly_details"]
               if d.get("verdict")]
    assert stamped and stamped[0]["verdict"] == "keep"
    # headline recomputed — FY2025 (34.3) is still the last surviving year
    assert "$34.3B assets" in fh["trajectory"]["headline"]

    # when the REINSTATED point IS the last year, the recomputed headline
    # reflects it (the pre-verdict headline ended at the prior year)
    traj4 = _traj(ta_series={2021: 29.5, 2022: 30.8, 2023: 32.1, 2024: 0.48},
                  ni_series=None, anchor_usd=33.2e9)
    fh4 = {"trajectory": traj4}
    assert "FY2023" in fh4["trajectory"]["headline"]
    assert apply_series_verdicts(fh4, [
        {"metric": "total_assets", "fy": 2024, "verdict": "keep",
         "value": 33.2, "reason": "10-K restates FY2024 assets"}]) is True
    assert "$33.2B assets" in fh4["trajectory"]["headline"]
    assert "FY2024" in fh4["trajectory"]["headline"]
    # idempotent: a second application of the same verdict is a no-op
    assert apply_series_verdicts(fh, [
        {"metric": "total_assets", "fy": 2024, "verdict": "drop",
         "reason": "should not re-stamp"}]) is False
    # cold path: no verdicts → nothing changes (anomaly stays dropped)
    fh2 = _fh_with_anomaly()
    assert apply_series_verdicts(fh2, []) is False
    assert fh2["trajectory"]["series"]["total_assets"][3] is None


# ── 3. sentiment numbers ─────────────────────────────────────────────────────

_AH4R_SIGNAL = ("FACT: Employee NPS 51 (2024), up from 48 (2023) — 20 points "
                "above sector benchmark. Confirmed improvement trajectory")


def test_employee_nps_classifies_employee_and_never_below_peer() -> None:
    """american-homes-4-rent (real corpus signal): Employee NPS 51 rendered
    as a below-peer CUSTOMER 51/100 row before wave 2."""
    prose = f"Workforce voice: {_AH4R_SIGNAL}. Net Promoter Score tracking continues."
    out = normalize_sentiment({"sources": [
        {"source": "Net Promoter Score", "rating": "51",
         "signal": _AH4R_SIGNAL},
    ]})
    assert out is not None
    assert not out.get("customer")
    row = (out.get("nps") or [None])[0]
    assert row and row["kind"] == "nps" and row["value"] == 51.0
    assert row["cohort"] == "employee" and row["metric"] == "Employee NPS"
    assert "flag" not in row
    # and _extract itself captures the clause-local number + cohort cue
    entries = _extract(prose)
    nps = next(e for e in entries if e["source"] == "Net Promoter Score")
    assert nps.get("rating") == "51" and nps.get("kind") == "nps"
    assert nps.get("cohort") == "employee"


def test_nps_is_never_mined_from_money_prose() -> None:
    """lpl-financials: 'NPS comparisons LPL Financials is a $11.0B in
    assets wealth & advisory firm' minted NPS 11 before wave 2."""
    prose = ("Customer reviews and satisfaction tracking: NPS comparisons "
             "LPL Financials is a $11.0B in assets wealth & advisory firm "
             "with strong ratings across advisory reviews.")
    entries = _extract(prose)
    nps = [e for e in entries if e["source"] == "Net Promoter Score"]
    assert nps and "rating" not in nps[0]


def test_nps_decimal_slash_rating_is_a_scale_row() -> None:
    """guaranteed-rate: '9.7/10' truncated to NPS '9' before wave 2 — it is
    a satisfaction rating on a stated /10 scale."""
    prose = ("Customer reviews are strong: Net Promoter Score data shows a "
             "9.7/10 average across post-close surveys and reviews.")
    entries = _extract(prose)
    nps = next(e for e in entries if e["source"] == "Net Promoter Score")
    assert nps["rating"] == "9.7/10" and nps.get("kind") != "nps"
    out = normalize_sentiment({"sources": [nps]})
    row = (out.get("customer") or [None])[0]
    assert row and row["score"] == 9.7 and row["scale"] == 10


def test_nps_row_never_steals_a_neighbouring_scale(
) -> None:
    """bank-ozk: the NPS row carried CSAT's 3.3/5 (blob-wide scale scan)."""
    out = normalize_sentiment({"sources": [
        {"source": "Net Promoter Score",
         "signal": "Customer satisfaction CSAT 3.3/5 tracked separately; "
                   "NPS program launching with reviews"},
    ]})
    assert out is not None
    assert not out.get("customer") and not out.get("nps")
    qual = out.get("qualitative") or []
    assert qual and qual[0]["source"] == "Net Promoter Score"


def test_customer_nps_flags_against_the_nps_norm_not_five_point() -> None:
    """compeer: 'Net Promoter Score 22.0/100 BELOW PEER' — the +22 index now
    ships as kind=nps benchmarked against the ~+30 FSI norm."""
    out = normalize_sentiment({"sources": [
        {"source": "Net Promoter Score", "rating": "22",
         "signal": "Member NPS 22 reported in the 2024 survey of reviews"},
    ]})
    row = (out.get("nps") or [None])[0]
    assert row and row["value"] == 22.0 and row["benchmark"] == 30.0
    assert row["flag"] == "below_peer"          # vs the NPS norm
    assert not out.get("customer")              # never a 22/100 bar


def test_employee_percent_satisfaction_is_accepted() -> None:
    """compeer: 'Glassdoor 79% satisfaction' was dropped (percent ratings
    were CFPB/JDPower/Forrester-only) — the client's ONLY employee signal."""
    prose = ("Employee sentiment: Glassdoor shows 79% satisfaction across "
             "reviews, with strong culture ratings from current staff.")
    entries = _extract(prose)
    gd = next(e for e in entries if e["source"] == "Glassdoor")
    assert gd["rating"] == "79%"
    out = normalize_sentiment({"sources": [gd]})
    row = (out.get("employee") or [None])[0]
    assert row and row["score"] == 79.0 and row["scale"] == 100


def test_scoreless_sources_become_qualitative_rows_not_dropped() -> None:
    """the 62%-dropped class: a source without a parsed rating renders as a
    qualitative row (signal + trend, no bar) instead of vanishing."""
    out = normalize_sentiment({"sources": [
        {"source": "CFPB complaints", "trend": "Improving",
         "signal": "Complaint volume declining year over year per CFPB data"},
    ]})
    assert out is not None
    qual = out.get("qualitative") or []
    assert qual and qual[0]["source"] == "CFPB complaints"
    assert qual[0]["trend"] == "Improving"
    assert "score" not in qual[0]               # no invented number


def test_sentiment_view_nps_value_is_the_value_not_n() -> None:
    """compeer context tile: 'Net Promoter · n=22' — the bare 22 IS the
    score, never the sample size."""
    view = sentiment_view({"sources": [
        {"source": "Net Promoter", "rating": "22",
         "signal": "NPS 22 in member survey responses"},
    ]})
    assert view is not None
    row = view["sources"][0]
    assert row["kind"] == "nps"
    assert row["value"] == 22.0 and row["max"] is None
    assert row["n"] != 22


def test_sentiment_view_bare_number_still_counts_on_count_fragments() -> None:
    view = sentiment_view({"sources": [
        {"source": "Glassdoor Rating", "rating": "3.8"},
        {"source": "Glassdoor Reviews", "rating": "59"},
    ]})
    row = view["sources"][0]
    assert row["value"] == 3.8 and row["n"] == 59


def test_normalize_merges_structured_fragment_pairs() -> None:
    """'Glassdoor Rating' 3.8 + 'Glassdoor Reviews' 59 (CSV/Clay fragments)
    → ONE scored employee row on the D1 card, matching the D5 merge."""
    out = normalize_sentiment({"sources": [
        {"source": "Glassdoor Rating", "rating": "3.8"},
        {"source": "Glassdoor Reviews", "rating": "59"},
    ]})
    emp = out.get("employee") or []
    assert len(emp) == 1
    assert emp[0]["source"] == "Glassdoor"
    assert emp[0]["score"] == 3.8 and emp[0]["scale"] == 5
    assert emp[0]["n"] == 59


# ── 4. evidence tier card from the workbooks ─────────────────────────────────

def _wb_hist(name: str) -> dict | None:
    openpyxl = pytest.importorskip("openpyxl")
    from app.services.parsers.research_workbook import evidence_tier_histogram
    path = _WORKBOOKS[name]
    if not path.exists():
        pytest.skip(f"fixture workbook missing: {path}")
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        return evidence_tier_histogram(wb)
    finally:
        wb.close()


def test_compeer_workbook_histogram_exact() -> None:
    h = _wb_hist("compeer")
    assert h == {"tiers": {"T1": 3, "T2": 23, "T3": 9, "T4": 5},
                 "total_items": 40, "sheet": "Evidence_Linkage_Matrix"}


def test_spokane_workbook_histogram_exact() -> None:
    h = _wb_hist("spokane")
    assert h["tiers"] == {"T1": 3, "T2": 10, "T3": 75, "T5": 11}
    assert h["total_items"] == 99


def test_ozk_workbook_histogram_matches_evidence_master() -> None:
    """OZK's card showed 43 index items {T1:1,…,T5:13} — the workbook's
    Evidence_Master carries 115 rows and this exact histogram."""
    h = _wb_hist("ozk")
    assert h == {"tiers": {"T1": 12, "T2": 22, "T3": 34, "T4": 26, "T5": 21},
                 "total_items": 115, "sheet": "Evidence_Master"}


def test_fnbo_workbook_histogram_unique_eids_no_t5() -> None:
    """FNBO's pack histogram invented a T5:34 bucket; the workbook's 145
    unique evidence rows have NO T5."""
    h = _wb_hist("fnbo")
    assert h["tiers"] == {"T1": 92, "T2": 32, "T3": 9, "T4": 12}
    assert h["total_items"] == 145 and "T5" not in h["tiers"]


def test_ozk_underscore_sheets_now_parse_with_evidence_tiers() -> None:
    openpyxl = pytest.importorskip("openpyxl")
    from app.services.parsers.research_workbook import parse_per_pillar_sheets
    path = _WORKBOOKS["ozk"]
    if not path.exists():
        pytest.skip(f"fixture workbook missing: {path}")
    wb = openpyxl.load_workbook(path, data_only=True)
    try:
        result = parse_per_pillar_sheets(wb)
    finally:
        wb.close()
    assert result.sheets_scanned == 4          # P1_…P4_ underscore names
    assert len(result.rows) >= 40              # was 0 before wave 2
    assert all(1 <= r.tier <= 8 for r in result.rows)
    # per-evidence annotation parsed, not the ERS decimal ("E-065:T2 ERS:3.65")
    by_id = {r.e_id: r for r in result.rows}
    assert "E-065" in by_id and by_id["E-065"].tier == 2
    assert not any(w["kind"] == "bad_tier" for w in result.warnings)


def test_scoring_detail_sheets_never_emit_taxonomy_tiers() -> None:
    """Compeer's P*_Scoring_Detail sheets carry the SUBCAP taxonomy tier —
    they are skipped (observed), and the flat ELM remains the tier truth."""
    openpyxl = pytest.importorskip("openpyxl")
    from app.services.parsers.research_workbook import parse_per_pillar_sheets
    path = _WORKBOOKS["compeer"]
    if not path.exists():
        pytest.skip(f"fixture workbook missing: {path}")
    wb = openpyxl.load_workbook(path, data_only=True)
    try:
        result = parse_per_pillar_sheets(wb)
    finally:
        wb.close()
    assert result.rows == []
    assert result.state_kind != "headers_too_drifted_requires_admin_review"
    assert any(o["kind"] == "scoring_detail_sheet_skipped"
               for o in result.observations)


def test_evidence_summary_provenance_ladder() -> None:
    rows = [{"tier": 5, "claim_type": "FACT", "excerpt": "x",
             "source_name": "Indeed", "linked_n": 1},
            {"tier": 2, "claim_type": "FACT", "excerpt": "y",
             "source_name": "10-K", "linked_n": 2}]
    wb = {"tiers": {"T1": 12, "T2": 22, "T3": 34, "T4": 26, "T5": 21},
          "total_items": 115, "sheet": "Evidence_Master"}
    ho = {"total_items": 110, "total_facts": 387,
          "tier_distribution": {"T1": 8, "T2": 15, "T3": 70, "T4": 5, "T5": 12}}
    # rung 1: workbook wins
    out = build_evidence_summary(rows, workbook_tiers=wb, handoff_summary=ho)
    assert out["derived_from"] == "research_workbook"
    assert out["tiers"]["T3"] == 34 and out["total_items"] == 115
    # rung 2: handoff when no workbook
    out2 = build_evidence_summary(rows, handoff_summary=ho)
    assert out2["derived_from"] == "research_handoff"
    assert out2["tiers"] == {"T1": 8, "T2": 15, "T3": 70, "T4": 5, "T5": 12}
    assert out2["total_items"] == 110 and out2["total_facts"] == 387
    # rung 3: index last resort — enrichment connectors excluded
    out3 = build_evidence_summary(rows)
    assert out3["derived_from"] == "evidence_index"
    assert out3["tiers"] == {"T2": 1} and out3["connectors"]["Indeed"] == 1


# ── 5. D5 chart plumbing (financials_view lifts the guarded trajectory) ─────

def test_financials_view_lifts_guarded_trajectory_series() -> None:
    traj = _traj(
        ta_series={2021: 29.5, 2022: 30.8, 2023: 32.1, 2024: 0.48, 2025: 34.3},
        ni_series={2021: 385e6, 2022: 420e6, 2023: 455e6},
        anchor_usd=33.2e9)
    out = financials_view({"trajectory": traj, "roa_pct": 1.4})
    assert out is not None
    labeled = {s["metric"]: s for s in out["series_labeled"]}
    ta = labeled["total_assets"]
    assert ta["unit"] == "usd_b"
    # the dropped FY2024 point is an honest gap — trimmed, never charted
    assert ta["fy"] == [2021, 2022, 2023, 2025]
    assert ta["values"] == [29.5, 30.8, 32.1, 34.3]
    ni = labeled["net_income"]
    assert ni["unit"] == "usd_m" and ni["values"] == [385.0, 420.0, 455.0]
    # the raw dict never reaches the kv-grid ('[object Object]' class)
    assert "trajectory" not in (out.get("metrics") or {})
    assert out["metrics"]["roa_pct"] == 1.4
    # legacy consumers keep the same primary axis
    assert out["years"] == [2021, 2022, 2023, 2025]


def test_financials_view_trend_still_reads_trajectory_headline() -> None:
    from app.services.context_extras import derive_trend_md
    traj = _traj(ta_series={2021: 9.8e9, 2022: 10.4e9}, ni_series=None)
    view = financials_view({"trajectory": traj})
    assert view is not None and view.get("trajectory")
    assert derive_trend_md(view)   # never None when a series exists
