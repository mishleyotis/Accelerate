"""Tests for D5 Context extras transforms (B-2/B-3/B-4 + plan Part 8).

The acquisition accept/reject table and the financials spurious-series
regression use the audit's VERBATIM rows (aafcu / access-credit-union /
chemung classes) so the measured false-positive families can never
silently return.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pytest

from app.schemas.context import IssueRegisterOut, TimelineEventOut
from app.services.context_extras import (
    _mine_prose_series,
    acquisitions_from_timeline,
    derive_trend_md,
    financials_view,
    has_open_regulatory_issue,
    leadership_view,
    regulatory_view,
    sentiment_view,
    to_issue_register,
)


@dataclass
class _IssueRow:
    id: str
    issue_id: str
    title: str
    severity: str
    rationale: str | None = None
    opened_on: date | None = None
    resolved_on: date | None = None
    linked_subcap_ids: list[str] | None = None


# ── B-2 issue_register ────────────────────────────────────────────────────


def test_issue_open_vs_resolved_status_derived_from_resolved_on() -> None:
    rows = [
        _IssueRow(id="u1", issue_id="IS-014", title="Core fragmentation",
                  severity="MATERIAL", opened_on=date(2025, 1, 1)),
        _IssueRow(id="u2", issue_id="IS-021", title="Data quality",
                  severity="MINOR", opened_on=date(2024, 6, 1),
                  resolved_on=date(2025, 2, 1)),
    ]
    out = to_issue_register(rows)
    assert out[0].status == "OPEN"
    assert out[0].issue_id == "IS-014"
    assert out[1].status == "RESOLVED"
    assert out[1].resolved_on == date(2025, 2, 1)


def test_issue_linked_subcaps_none_becomes_empty_list() -> None:
    out = to_issue_register(
        [_IssueRow(id="u1", issue_id="IS-001", title="x", severity="MINOR",
                   linked_subcap_ids=None)]
    )
    assert out[0].linked_subcap_ids == []


def test_issue_empty_input() -> None:
    assert to_issue_register([]) == []


def test_issue_inline_eids_mined_into_evidence_anchors() -> None:
    """derive_issues writes inline [E-###] citations; the read path must
    surface them as drawer-openable anchors (2026-07-06)."""
    out = to_issue_register([
        _IssueRow(
            id="u1", issue_id="GAP-1-P2C1", title="Capability gap: CRM",
            severity="high",
            rationale=('Maturity 1.8/5. Observed in the research evidence '
                       '[E-032]: "No CDP; profiles stitched manually." '
                       'Also corroborated [E-047].'),
        ),
    ])
    assert out[0].evidence_e_ids == ["E-032", "E-047"]


def test_issue_bare_eid_prose_is_not_an_anchor() -> None:
    """'Add E-NNN citations' style prose (no brackets) must not fabricate
    evidence anchors — bracketed citations only, deduped."""
    out = to_issue_register([
        _IssueRow(id="u1", issue_id="GOV-001", title="x", severity="low",
                  rationale="1 rationales lack evidence citations; add "
                            "E-003 references. See [E-011] and [E-011]."),
    ])
    assert out[0].evidence_e_ids == ["E-011"]


def test_has_open_regulatory_issue() -> None:
    reg_open = IssueRegisterOut(
        id="1", issue_id="IS-014", title="AML consent order remediation",
        severity="MATERIAL", status="OPEN",
    )
    ops_open = IssueRegisterOut(
        id="2", issue_id="IS-027", title="Branch network rationalization",
        severity="MINOR", status="OPEN",
    )
    reg_resolved = IssueRegisterOut(
        id="3", issue_id="IS-018", title="BSA program gaps",
        severity="MINOR", status="RESOLVED",
    )
    assert has_open_regulatory_issue([reg_open])
    assert not has_open_regulatory_issue([ops_open, reg_resolved])
    assert not has_open_regulatory_issue([])


# ── B-4 / Part 8.3 acquisitions — frame accept/reject table ───────────────


def _te(title: str, *, body: str | None = None, kind: str = "acquisition",
        tid: str = "t1", e_id: str | None = "E-1",
        evidence: list[str] | None = None) -> TimelineEventOut:
    return TimelineEventOut(
        id=tid, event_date=date(2024, 8, 1), kind=kind, title=title,
        body=body, source_url=None, e_id=e_id,
        evidence_e_ids=evidence or [],
    )


# The audit's verbatim FP rows — ALL must be rejected.
AUDIT_ACQ_FALSE_POSITIVES = [
    # aafcu: negative-search / internal-alternative absences
    _te("INTERNAL ALTERNATIVE — 'No M&A activity' (P1C1.8.1-8.4): NEGATIVE "
        "SEARCH confirmed AAFCU not party to any 2024 merger", tid="fp1"),
    _te("NEGATIVE SEARCH: AAFCU NOT named in any 2024 or 2025 NCUA merger "
        "approvals, bank acquisitions, or merger-of-equals", tid="fp2"),
    # aafcu: peer/market M&A (Wings + Ent) — not this entity's deal
    _te("Wings ($9.6B) + Ent ($10B, 580K members, Colorado) merger announced "
        "Apr 2025; full integration expected 2027", tid="fp3"),
    # aafcu: vendor lineage note (Velera = PSCU + Co-op merger)
    _te("DIRECT P1C3.6.CU1 EVIDENCE: AAFCU is a Velera client (Velera = "
        "merged entity of PSCU + Co-op Financial Services)", tid="fp4"),
    # access-credit: complaint/sentiment rows mentioning the merger
    _te("Post-merger sentiment damage: legacy Sunova CU members specifically "
        "complained 'Never had these kind of problems'", tid="fp5"),
    _te("BBB COMPLAINT THEMES (2024): 'No customer service whatsoever — no "
        "one to assist by phone over long weekend'", tid="fp6"),
    # access-credit: vendor M&A (CGI acquired Celero) — third-party frame
    _te("CRITICAL TECH TRANSITION: July 4, 2024 — CGI (TSX:GIB.A; NYSE:GIB) "
        "acquired Celero from CUCM + SaskCentral + Alberta Central",
        tid="fp7"),
    # access-credit: hypothetical/quote ("would be a strategic fit")
    _te("'Owners agreed that the acquisition of its business by CGI would be "
        "a strategic fit, allowing CGI to further develop'", tid="fp8"),
    # access-credit: analogous-peer pattern row
    _te("Conexus also pursuing 3-way merger with Cornerstone + Synergy "
        "(Nov 2024) — analogous M&A pattern to Access", tid="fp9"),
    # access-credit: different-entity disambiguation note
    _te("ACU acu.ca = Assiniboine Credit Union (DIFFERENT entity); merged "
        "with Caisse Financial Group + Westoba CU in 2025", tid="fp10"),
    # chemung-class: strategy intent
    _te("Management actively seeking acquisition targets across the "
        "Southern Tier region", tid="fp11"),
    # leadership/resume row mis-kinded as acquisition by the legacy parser
    _te("CRO IDENTIFIED: Brent Berzuk — Chief Risk Officer; previously Chief "
        "Governance & Risk Officer; CRM designation", tid="fp12"),
]


def test_audit_false_positives_all_rejected() -> None:
    out = acquisitions_from_timeline(
        AUDIT_ACQ_FALSE_POSITIVES, entity_name="Access Credit Union Limited",
    )
    assert out == []
    out2 = acquisitions_from_timeline(AUDIT_ACQ_FALSE_POSITIVES, entity_name="AAFCU")
    assert out2 == []


def test_true_positive_entity_merger_frame() -> None:
    row = _te(
        "Legal merger of Access + Noventis + Sunova CUs",
        body="July 1, 2022: legal merger of Access + Noventis + Sunova CUs "
             "(member vote Jan 27, 2022)",
        tid="tp1", e_id="E-003",
    )
    out = acquisitions_from_timeline([row], entity_name="Access Credit Union Limited")
    assert len(out) == 1
    acq = out[0]
    assert acq.target and "Noventis" in acq.target
    assert acq.acquirer and "Access" in acq.acquirer
    assert acq.status == "closed"        # "legal merger" happened
    assert acq.closed_on == row.event_date
    assert acq.e_id == "E-003"


def test_true_positive_implied_subject_and_amount() -> None:
    row = _te(
        "Acquired Hudson Valley CU branches",
        body="Acquired Hudson Valley CU branches in August 2024 — 32 branches "
             "and ~$420M in deposits; integration tracking to Q3 2026",
        tid="tp2", e_id="E-047",
    )
    out = acquisitions_from_timeline([row], entity_name="Farm Credit East")
    assert len(out) == 1
    acq = out[0]
    assert acq.acquirer == "Farm Credit East"       # implied subject
    assert acq.target and "Hudson Valley" in acq.target
    assert acq.amount and "$420M" in acq.amount
    assert acq.status == "integrating"
    assert acq.details


def test_true_positive_bare_org_title_from_docx_table() -> None:
    # The curated Client-Profile "Acquisition History" table emits just the
    # target name — kept, with the entity as implied acquirer.
    rows = [
        _te("Interlake Insurance", tid="tp3", e_id=None),
        _te("Carpathia Credit Union", tid="tp4", e_id=None),
    ]
    out = acquisitions_from_timeline(rows, entity_name="Access Credit Union Limited")
    assert [a.target for a in out] == ["Interlake Insurance", "Carpathia Credit Union"]
    assert all(a.acquirer == "Access Credit Union Limited" for a in out)


def test_non_acquisition_kinds_ignored() -> None:
    rows = [
        _te("Acquired FinTechCo in 2024", kind="milestone", tid="m1"),
        _te("Jane Doe appointed CEO", kind="leadership", tid="l1"),
    ]
    assert acquisitions_from_timeline(rows, entity_name="X Bank") == []


def test_announced_status_sets_announced_on() -> None:
    row = _te(
        "Merger with Prairie Trust announced",
        body="Sunflower Bank announced a definitive agreement to acquire "
             "Prairie Trust Company in April 2025",
        tid="tp5",
    )
    out = acquisitions_from_timeline([row], entity_name="Sunflower Bank, N.A.")
    assert len(out) == 1
    assert out[0].status == "announced"
    assert out[0].announced_on == row.event_date


# ── B-3 / Part 8.4 financials_view ────────────────────────────────────────


def test_mine_prose_series_skips_none_metric(monkeypatch) -> None:
    """2026-07-06: a card metric whose value list is None fed zip() a NoneType
    and raised TypeError, aborting the whole context derive (empty context page
    for most clients). The None metric is now skipped, valid ones survive."""
    import app.services.overview_cards as oc

    monkeypatch.setattr(oc, "financial_trajectory_card", lambda _fh: {
        "fy": [2021, 2022, 2023], "unit": "B",
        "series": {"total_assets": [1.0, 2.0, 3.0], "net_income_m": None},
    })
    out = _mine_prose_series({"anything": "x"})
    metrics = {row["metric"] for row in out}
    assert "total_assets" in metrics and "net_income_m" not in metrics


def test_financials_none_or_empty_returns_none() -> None:
    assert financials_view(None) is None
    assert financials_view({}) is None


def test_financials_year_keyed_builds_sorted_series() -> None:
    out = financials_view({
        "2024": "$1.2B", "2022": "$0.9B", "2023": "$1.0B",
        "cagr": "8%",
    })
    assert out is not None
    assert out["years"] == [2022, 2023, 2024]
    assert out["series"]["value"] == [0.9e9, 1.0e9, 1.2e9]
    # labelled series contract (metric picker input)
    labeled = out["series_labeled"][0]
    assert labeled["fy"] == [2022, 2023, 2024]
    assert labeled["unit"] == "usd"
    # non-year scalar surfaces as a metric
    assert out["metrics"]["cagr"] == "8%"


def test_financials_prestructured_series_wins() -> None:
    out = financials_view({
        "series": {"FY2023": 1000, "FY2024": 1200},
        "aum": "$5B",
    })
    assert out is not None
    assert out["years"] == [2023, 2024]
    assert out["series"]["value"] == [1000.0, 1200.0]
    assert out["metrics"]["aum"] == "$5B"


def test_financials_metrics_only_no_year_data() -> None:
    out = financials_view({"assets": "$11.3B", "employees": "2,400"})
    assert out is not None
    assert "years" not in out
    assert out["metrics"]["assets"] == "$11.3B"


def test_financials_lines_passthrough() -> None:
    out = financials_view({"lines": ["Revenue grew 8% YoY"], "2024": 100})
    assert out is not None
    assert out["lines"] == ["Revenue grew 8% YoY"]
    assert out["years"] == [2024]


def test_financials_prose_mined_series_shared_with_d1() -> None:
    """No year-keyed data, but the highlights PROSE carries the series
    (the all-94 sweep's dominant shape, 81 clients) — the D5 view mines
    it through the SAME engine as the D1 trajectory card, so both
    surfaces chart identically."""
    out = financials_view({
        "net_income": 36_100_000.0, "nim": 0.043,
        "lines": [
            "Total assets grew from $2.286B in 2021 to $3.209B in 2025, "
            "representing a four-year CAGR of approximately 8.9% [E-015]."
        ],
    })
    assert out is not None
    labeled = out["series_labeled"][0]
    assert labeled["metric"] == "total_assets"
    assert labeled["unit"] == "usd_b"
    assert labeled["fy"] == [2021, 2025]
    assert labeled["values"] == [2.286, 3.209]
    # legacy consumers get the same axis
    assert out["years"] == [2021, 2025]
    # prose stays a line; metrics stay metrics
    assert out["metrics"]["net_income"] == 36_100_000.0


def test_financials_spurious_year_harvest_regression() -> None:
    """The audit's access-credit case: prose-keys carrying an embedded year
    must NOT be harvested into a series ([2022, 2025] → [2023, 87.5])."""
    out = financials_view({
        "net_income": 76100000.0,
        "member_cagr": "7.0% | Net Income Growth (FY2024–FY2025): +",  # noqa: RUF001 — verbatim corpus value
        "a-driven_scale-up_2022": "2023; integration year 2024 (no new mergers)",
        "loan/asset_ratio_fy2025": "87.5% — concentrated lending portfolio.",
        "a-driven_transformation_2022": "2023 followed by organic growth",
        "lines": ["3-Year Asset CAGR (2022–2025): 9.4% | Member CAGR: 7.0%"],  # noqa: RUF001 — verbatim corpus value
    })
    assert out is not None
    # NO fabricated year series from value prose.
    assert "years" not in out
    assert "series" not in out
    # Prose fragments are NOT metric keys.
    assert "member_cagr" not in (out.get("metrics") or {})
    assert "a-driven_scale-up_2022" not in (out.get("metrics") or {})
    assert "loan/asset_ratio_fy2025" not in (out.get("metrics") or {})
    # Real scalar survives.
    assert out["metrics"]["net_income"] == 76100000.0
    # Source lines preserved for the narrative fallback.
    assert out["lines"]


def test_financials_sunflower_series_gets_labeled_unit() -> None:
    """Sunflower's anonymous series is labelled via the Total_Assets_B
    metric whose '(2026)' point matches the series."""
    out = financials_view({
        "series": {"2022": 4.5, "2023": 8.1, "2024": 8.2, "2025": 8.5,
                   "2026": 20.4},
        "Total_Assets_B": "20.4 (2026)",
        "NIM_Pct": "4.10 (2025)",
    })
    assert out is not None
    labeled = out["series_labeled"][0]
    assert labeled["metric"] == "total_assets"
    assert labeled["unit"] == "usd_b"
    assert labeled["fy"] == [2022, 2023, 2024, 2025, 2026]


# ── Part 8.5 sentiment_view ────────────────────────────────────────────────


def test_sentiment_none_and_empty() -> None:
    assert sentiment_view(None) is None
    assert sentiment_view({}) is None
    assert sentiment_view({"sources": []}) is None


def test_sentiment_rating_and_review_count_fragments_merge() -> None:
    """Audit case: 'Glassdoor Rating' 3.8 + 'Glassdoor Reviews' 59 rendered
    as two separate 'sources' — must merge into one row value 3.8/5 n=59."""
    out = sentiment_view({"sources": [
        {"source": "Glassdoor Rating", "rating": "3.8"},
        {"source": "Glassdoor Reviews", "rating": "59"},
    ]})
    assert out is not None
    assert len(out["sources"]) == 1
    row = out["sources"][0]
    assert row["source"] == "Glassdoor"
    assert row["kind"] == "employee"
    assert row["value"] == 3.8 and row["max"] == 5.0
    assert row["n"] == 59


def test_sentiment_structured_row_fields() -> None:
    out = sentiment_view({"sources": [
        {"source": "Glassdoor", "rating": "3.2/5", "trend": "Declining",
         "themes": "37% recommend; CEO 52%; culture declining",
         "volume": "156 reviews",
         "signal": "Recurring themes: manual processing, spreadsheet-heavy "
                   "work in ops [E-236]"},
    ]})
    assert out is not None
    row = out["sources"][0]
    assert row["value"] == 3.2 and row["max"] == 5.0
    assert row["n"] == 156
    assert row["polarity"] == "negative"
    assert "37% recommend" in row["themes"]
    assert row["drilldown"] and "manual processing" in row["drilldown"]
    assert row["evidence_e_id"] == "E-236"


def test_sentiment_unparseable_rating_stays_honest() -> None:
    out = sentiment_view({"sources": [
        {"source": "LinkedIn", "rating": "Active", "trend": "Stable",
         "themes": "CIO award; community posts"},
    ]})
    assert out is not None
    row = out["sources"][0]
    assert row["value"] is None and row["max"] is None
    assert row["kind"] == "social"


def test_sentiment_rating_recovered_from_prose() -> None:
    out = sentiment_view({"sources": [
        {"source": "Glassdoor",
         "signal": "Glassdoor rating of 3.8/5 across 310+ reviews"},
    ]})
    assert out is not None
    row = out["sources"][0]
    assert row["value"] == 3.8 and row["max"] == 5.0
    assert row["n"] == 310


# ── Part 8.6 leadership_view ───────────────────────────────────────────────

_TODAY = date(2026, 7, 2)


def test_leadership_tenure_from_date_phrase() -> None:
    rows = [{"name": "Diana Solis", "title": "CTO", "tenure": None,
             "background": "From Wells Fargo (8 yrs). Hired April 2026."}]
    out = leadership_view(rows, today=_TODAY)
    assert len(out) == 1
    row = out[0]
    assert row["tenure_months"] == 3
    assert row["recent_hire"] is True
    assert row["critical_role"] is True


def test_leadership_tenure_from_title_and_nyear() -> None:
    """Part 8.6 broadening: mine the title '(since YYYY)' and a background
    'N-year veteran' clip, not just the tenure/background verb phrase."""
    rows = [
        {"name": "Dominic Ng", "title": "Chairman & CEO (since 1991)"},
        {"name": "Scott Mitchell", "title": "CFO",
         "background": "Aug 2024). 19-year HAPO veteran, ex-EVP/CFO."},
    ]
    out = leadership_view(rows, today=_TODAY)
    assert out[0]["tenure_months"] == (2026 - 1991) * 12   # (since 1991)
    assert out[1]["tenure_months"] == 19 * 12               # "19-year veteran"


def test_leadership_parentheticals_move_to_note() -> None:
    rows = [{"name": "Jane Doe (interim)", "title": "Chief Financial Officer",
             "tenure": "3 years", "background": None}]
    out = leadership_view(rows, today=_TODAY)
    assert out[0]["name"] == "Jane Doe"
    assert out[0]["note"] == "interim"
    assert out[0]["tenure_months"] == 36
    assert out[0]["critical_role"] is False


def test_leadership_garble_rows_dropped_or_gap_flagged() -> None:
    """The aafcu audit roster: proxy-search garble must never render as a
    person; missing critical roles become explicit gap rows."""
    rows = [
        {"name": "Gail Enda", "title": "President & CEO"},
        {"name": "Recent (within past ~24 months per LeadIQ",
         "title": "LEADERSHIP TRANSITION RECENCY"},
        {"name": "NOT YET CONFIRMED via public proxy searches",
         "title": "NAMED CDO CTO CISO FOUND"},
    ]
    out = leadership_view(rows, today=_TODAY)
    names = [r["name"] for r in out]
    assert "Gail Enda" in names
    assert not any(r["name"] and "LeadIQ" in str(r["name"]) for r in out)
    gaps = [r for r in out if r.get("gap_flag")]
    assert len(gaps) == 1
    assert gaps[0]["title"] == "CDO / CTO / CISO"
    assert gaps[0]["critical_role"] is True


def test_leadership_empty_input() -> None:
    assert leadership_view(None) == []
    assert leadership_view([]) == []


# ── Part 8.6 regulatory_view + derive_trend_md ─────────────────────────────


def test_regulatory_view_extracts_license_and_jurisdictions() -> None:
    out = regulatory_view(
        {"entity_type": "bank"},
        "Chemung Canal Trust Company is a state-chartered trust company "
        "headquartered in Elmira, New York, operating branches across "
        "New York and Pennsylvania.",
        None,
    )
    assert out["license_type"] is not None
    assert "chartered" in out["license_type"].lower()
    assert out["jurisdictions"] == ["New York", "Pennsylvania"]


def test_regulatory_view_structured_keys_win() -> None:
    out = regulatory_view(
        {"license_type": "Federal credit union charter",
         "operating_states": ["Texas", "Oklahoma"]},
        None, None,
    )
    assert out["license_type"] == "Federal credit union charter"
    assert out["jurisdictions"] == ["Texas", "Oklahoma"]


def test_regulatory_view_honest_null() -> None:
    out = regulatory_view({}, "A community institution with modern apps.", None)
    assert out["license_type"] is None
    assert out["jurisdictions"] is None


def test_regulatory_view_regulator_class_fallback() -> None:
    """Part 8.6 (2026-07-02): the primary_regulator determines the charter
    class + jurisdiction when the prose does not spell it out (grounded)."""
    # NCUA regulator + HQ state abbreviation in the narrative
    out = regulatory_view(
        {}, "AAFCU is headquartered in Fort Worth, TX. It serves members.",
        None, primary_regulator="NCUA (National Credit Union Administration)")
    assert out["license_type"] == "Credit union (NCUA-regulated)"
    assert out["jurisdictions"] == ["Texas"]
    # OCC national bank with no stated footprint → national jurisdiction
    out = regulatory_view({}, "TrustCo Bank is a regional bank.", None,
                          primary_regulator="OCC")
    assert out["license_type"] == "National bank charter (OCC)"
    assert out["jurisdictions"] == ["United States (national)"]
    # a plain regional FDIC bank with no geography stays honest-null on juris
    out = regulatory_view({}, "Beacon Bank is a regional bank.", None,
                          primary_regulator="FDIC")
    assert out["license_type"] == "FDIC-insured bank"
    assert out["jurisdictions"] is None


def test_derive_trend_md_from_labeled_series() -> None:
    fin = financials_view({
        "series": {"2022": 4.5, "2023": 8.1, "2024": 8.2, "2025": 8.5,
                   "2026": 20.4},
        "Total_Assets_B": "20.4 (2026)",
        "lines": ["Trend Classification: ACCELERATING — M&A-driven scale-up"],
    })
    md = derive_trend_md(fin)
    assert md is not None
    assert "$4.5B" in md and "$20.4B" in md   # real numbers
    assert "2022" in md and "2026" in md
    assert "CAGR" in md
    assert "ACCELERATING" in md


@pytest.mark.parametrize("fin", [
    None,                                   # no financial view at all
    {},                                     # empty view
    {"metrics": {"size_tier": "Large ($10B-$50B)"}},   # no money/trend metric
    {"lines": ["trend data gap: need CFC-specific 5-year asset trend"]},  # explicit gap
])
def test_derive_trend_md_honest_none(fin) -> None:
    """Honest-null only when the corpus records no usable financials — an
    explicit 'trend data gap' line or a non-money metric never fabricate one."""
    assert derive_trend_md(fin) is None


def test_derive_trend_md_single_metric_snapshot() -> None:
    """Part 8.6 broadening (2026-07-02): a single grounded money metric now
    yields a snapshot line (as of the latest period, no invented direction),
    closing the trend_md residual for the metric-only clients."""
    md = derive_trend_md({"metrics": {"assets": "$1B"}})
    assert md == "Latest available financials show assets of $1B."


def test_derive_trend_md_trajectory_headline() -> None:
    md = derive_trend_md({"metrics": {"trajectory": {
        "headline": "$62M net income · FY2025", "fy": ["FY2023", "FY2024", "FY2025"]}}})
    assert md is not None and "$62M net income" in md and "FY2025" in md


def test_acquisition_acronym_form_matches_entity() -> None:
    """Reports write "APGFCU" for "APG Federal Credit Union" — the compact
    form must scope to the entity (2026-07-04 deep search: real frames for
    27 clients were rejected by strict token matching), while peer M&A
    stays rejected."""
    own = TimelineEventOut(
        id="00000000-0000-0000-0000-000000000001", kind="acquisition",
        title="Apgfcu acquired Members First of Maryland Federal Credit Union",
        body="APGFCU acquired Members First of Maryland Federal Credit Union "
             "effective Aug 29, 2025 (announced Sep 2, 2025).",
        event_date="2025-08-29", e_id="E-001", signal="positive")
    got = acquisitions_from_timeline([own], entity_name="APG Federal Credit Union")
    assert len(got) == 1 and got[0].acquirer.lower().startswith("apg")
    peer = TimelineEventOut(
        id="00000000-0000-0000-0000-000000000002", kind="acquisition",
        title="Zions Bancorporation acquired Foothill Bank",
        body="Zions Bancorporation acquired Foothill Bank in 2024.",
        event_date="2024-05-01", e_id="E-2", signal="positive")
    assert acquisitions_from_timeline([peer], entity_name="Frost Bank") == []


def test_issue_multi_id_bracket_group_mined_and_title_dup_rationale_nulled() -> None:
    out = to_issue_register([
        _IssueRow(id="u1", issue_id="GAP-3", title="Capability gap: CRM",
                  severity="high",
                  rationale="Greenfield gap confirmed via proxy. "
                            "[E-020,E-042,E-052] Observed [E-037]: \"…\""),
        _IssueRow(id="u2", issue_id="ISS-002", title="Glassdoor: manual work",
                  severity="low", rationale="Glassdoor: manual work"),
    ])
    assert out[0].evidence_e_ids == ["E-020", "E-042", "E-052", "E-037"]
    assert out[1].rationale is None   # duplicate-of-title suppressed
