"""Acceptor gates for the empties-census enrichment queries.

Every acceptor is a pure function (out_text, ctx) → payload|None; these
tests pin the anti-fabrication contract: verbatim-quote substring,
E-ID-in-grounding, id-set membership, numeric sanity, and honesty
(absence is a legal answer; fabrications drop silently).
"""
import json

from app.services.enrichment_queries import (
    ENRICHMENT_QUERIES,
    parse_strict_json,
)

_ACCEPT = {name: q.accept for name, q in ENRICHMENT_QUERIES.items()}


def test_registry_covers_all_census_classes() -> None:
    classes = {q.empty_class for q in ENRICHMENT_QUERIES.values()}
    assert classes == {
        "D1.sentiment_card", "D5.acquisitions_zero", "D5.fin_no_multiyear",
        "D5.timeline_lt3", "D2.cards_lt5", "D3.kpis_all_empty",
        "D3.fa_no_subcaps", "D6.rows_no_evidence",
        # focus-enrichment wave (056)
        "D3.fa_no_grounding", "D3.fa_no_linked_insights",
        # firmographics deploy safeguard (2026-07-06)
        "D1.firmographics_empty",
    }
    for q in ENRICHMENT_QUERIES.values():
        assert "{" in q.template and q.model in ("flash", "pro")


def test_firmographics_is_tier_zero() -> None:
    # the operator safeguard must be first in the registry so a budget cut
    # trims it last (enrich_empty_surfaces uses registry order as the tier).
    assert next(iter(ENRICHMENT_QUERIES)) == "firmographics_extraction"


# ── firmographics extraction (verbatim-quote + per-field format gated) ──────

_FIRMO_CTX = {
    "grounding": "[E-01] Acme Bank was founded in 1994 and is headquartered in "
                 "Dallas, Texas. It operates 42 branches and trades as "
                 "NASDAQ: ACME.",
    "_missing": ["website", "founded", "hq", "branches", "ticker", "cagr",
                 "geography", "trend", "employees_approx"],
}


def test_firmographics_accepts_grounded_fields_only() -> None:
    out = json.dumps({
        "founded": {"value": "1994", "quote": "Acme Bank was founded in 1994"},
        "branches": {"value": "42", "quote": "It operates 42 branches"},
        "ticker": {"value": "NASDAQ: ACME", "quote": "trades as NASDAQ: ACME"},
        "hq": {"value": "Dallas, Texas", "quote": "headquartered in Dallas, Texas"},
        # fabricated — the quote is not in the grounding → dropped
        "cagr": {"value": "12%", "quote": "grew at a 12% CAGR over five years"},
    })
    got = _ACCEPT["firmographics_extraction"](out, _FIRMO_CTX)
    assert got["founded"] == "1994"
    assert got["branches"] == "42"
    assert got["ticker"] == "NASDAQ: ACME"
    assert got["hq"] == "Dallas, Texas"
    assert "cagr" not in got                      # ungrounded quote dropped


def test_firmographics_rejects_malformed_and_unrequested() -> None:
    # a CEO-tenure year mis-labelled as founded still fails the year guard only
    # if out of range; here the value is fine but the field was NOT requested.
    ctx = {"grounding": _FIRMO_CTX["grounding"], "_missing": ["founded"]}
    out = json.dumps({
        "founded": {"value": "not-a-year", "quote": "Acme Bank was founded in 1994"},
        "ticker": {"value": "NASDAQ: ACME", "quote": "trades as NASDAQ: ACME"},
    })
    # founded value malformed → dropped; ticker not in _missing → ignored.
    assert _ACCEPT["firmographics_extraction"](out, ctx) is None


def test_parse_strict_json_tolerates_fences() -> None:
    assert parse_strict_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_strict_json("not json") is None


# ── sentiment ──────────────────────────────────────────────────────────────

_SENT_CTX = {"grounding": "[E-001] Glassdoor rating 4.2/5 from 310 reviews. "
                          "[E-002] BBB score 1.2/5 across 44 complaints."}


def test_sentiment_accepts_grounded_scores_only() -> None:
    out = json.dumps({
        "employee": [{"source": "Glassdoor", "metric": "overall", "score": 4.2,
                      "scale": 5, "n": 310, "quote": "Glassdoor rating 4.2/5 from 310 reviews"}],
        "customer": [{"source": "BBB", "metric": "overall", "score": 4.9,
                      "scale": 5, "n": 44, "quote": "this quote is fabricated entirely"}],
    })
    got = _ACCEPT["sentiment_extraction"](out, _SENT_CTX)
    assert len(got["employee"]) == 1 and got["employee"][0]["score"] == 4.2
    assert got["customer"] == []          # fabricated quote dropped


def test_sentiment_rejects_score_above_scale() -> None:
    out = json.dumps({"employee": [{"source": "Glassdoor", "metric": "x",
                                    "score": 7.0, "scale": 5,
                                    "quote": "Glassdoor rating 4.2/5"}],
                      "customer": []})
    assert _ACCEPT["sentiment_extraction"](out, _SENT_CTX) is None


# ── acquisitions ───────────────────────────────────────────────────────────

_ACQ_CTX = {
    "entity_name": "Frost Bank",
    "grounding": "[E-045] Frost Bank announced the acquisition of Hudson "
                 "Valley CU branches in August 2024 for $120M.",
}


def test_acquisition_frame_accepted_with_entity_party() -> None:
    out = json.dumps({"acquisitions": [{
        "acquirer": "Frost Bank", "target": "Hudson Valley CU branches",
        "amount": "$120M", "status": "announced", "announced_on": "2024-08",
        "e_id": "E-045",
        "quote": "Frost Bank announced the acquisition of Hudson Valley CU branches",
    }], "verified_absent": False})
    got = _ACCEPT["acquisition_extraction"](out, _ACQ_CTX)
    assert got["acquisitions"][0]["target"] == "Hudson Valley CU branches"


def test_acquisition_peer_deal_rejected_but_absent_verifiable() -> None:
    out = json.dumps({"acquisitions": [{
        "acquirer": "Some Other Bank", "target": "Third Bank",
        "status": "closed", "e_id": "E-045",
        "quote": "Frost Bank announced the acquisition of Hudson Valley",
    }], "verified_absent": True})
    got = _ACCEPT["acquisition_extraction"](out, _ACQ_CTX)
    # peer frame dropped → falls through to the verified-absent marker
    assert got == {"acquisitions": [], "verified_absent": True}


# ── financial series ───────────────────────────────────────────────────────

_FIN_CTX = {"grounding": "Total assets grew from $2.286B in 2021 to "
                         "$3.209B in 2025, an 8.9% CAGR."}


def test_fin_series_years_must_appear_in_quote() -> None:
    out = json.dumps({"metric": "total_assets", "unit": "usd_b",
                      "series": {"2021": 2.286, "2023": 2.7, "2025": 3.209},
                      "quote": "grew from $2.286B in 2021 to $3.209B in 2025"})
    got = _ACCEPT["financial_series_extraction"](out, _FIN_CTX)
    # 2023 was interpolated — not in the quote — dropped; 2 real points kept
    assert set(got["series"]) == {"2021", "2025"}


def test_fin_series_single_point_rejected() -> None:
    out = json.dumps({"metric": "total_assets", "unit": "usd_b",
                      "series": {"2021": 2.286},
                      "quote": "grew from $2.286B in 2021"})
    assert _ACCEPT["financial_series_extraction"](out, _FIN_CTX) is None


# ── timeline ───────────────────────────────────────────────────────────────

_TL_CTX = {
    "grounding": "[E-012] The bank completed its nCino migration in March 2024.",
    "_existing_titles": ["Existing event"],
}


def test_timeline_event_date_must_live_in_quote() -> None:
    out = json.dumps({"events": [
        {"date": "2024-03", "kind": "milestone", "title": "nCino migration completed",
         "body": "Core migration done.", "signal": "positive", "e_id": "E-012",
         "quote": "completed its nCino migration in March 2024"},
        {"date": "2022-01", "kind": "milestone", "title": "Something else",
         "body": "x", "signal": "neutral", "e_id": "E-012",
         "quote": "completed its nCino migration in March 2024"},
    ]})
    got = _ACCEPT["timeline_event_extraction"](out, _TL_CTX)
    assert len(got["events"]) == 1
    ev = got["events"][0]
    assert ev["date"] == "2024-03-01" and ev["precision"] == "month"


# ── insight generation ─────────────────────────────────────────────────────

_INS_CTX = {
    "grounding": "[E-002] No CRM detected; branch staff track leads in "
                 "spreadsheets across 46 branches.",
    "_gap_ids": ["P2C1.1.1", "P4C1.2.2"],
    "_existing_titles": ["Old card"],
    "want": 4,
}


def test_insight_gen_validates_subcap_and_eids() -> None:
    card = {"title": "No CRM despite 46-branch lead volume",
            "what_text": "Branch staff track leads in spreadsheets across 46 "
                         "branches with no CRM detected in any source.",
            "why_text": "Without a system of record, lead handoffs between "
                        "branches drop and marketing cannot attribute.",
            "so_what_text": "Lead with the FSC conversation anchored on lead "
                            "routing.",
            "severity": "HIGH", "linked_subcap_id": "P2C1.1.1",
            "linked_e_ids": ["E-002"], "affects": ["P4C1.2.2"],
            "theme": "CRM foundation"}
    got = _ACCEPT["insight_card_generation"](json.dumps({"cards": [card]}), _INS_CTX)
    assert len(got["cards"]) == 1
    bad = dict(card, linked_subcap_id="P9C9.9.9")
    assert _ACCEPT["insight_card_generation"](
        json.dumps({"cards": [bad]}), _INS_CTX) is None
    fab = dict(card, linked_e_ids=["E-999"])
    assert _ACCEPT["insight_card_generation"](
        json.dumps({"cards": [fab]}), _INS_CTX) is None


# ── focus KPIs (reasoned: disclosed-current + roadmap-uplift target) ───────

_KPI_CTX = {
    "_fa_ids": ["fa-1"],
    # e_id → its disclosed excerpt (the acceptor checks current is a number
    # in a CITED excerpt).
    "_excerpt_by_eid": {
        "E-045": "Straight-through processing sits at 18% today across channels.",
        "E-050": "Loan cycle time runs 12 days end to end.",
    },
    # the roadmap recs targeting this focus area, with their uplift text.
    "_rec_texts_by_fa": {
        "fa-1": ["Deploy nCino to lift STP to 45%.",
                 "Automation cuts the loan cycle to 4 days."],
    },
}


def test_focus_kpi_current_must_be_disclosed_in_cited_excerpt() -> None:
    out = json.dumps({"kpis": [
        {"fa_id": "fa-1", "label": "STP rate", "current": "18%",
         "target": "45%", "rationale": "nCino lifts STP.",
         "evidence_e_ids": ["E-045"]},
        # 99% current is NOT in the cited excerpt → fabricated, dropped.
        {"fa_id": "fa-1", "label": "Made up", "current": "99%",
         "target": "45%", "rationale": "x", "evidence_e_ids": ["E-045"]},
    ]})
    got = _ACCEPT["focus_kpi_extraction"](out, _KPI_CTX)
    assert len(got["kpis"]) == 1
    row = got["kpis"][0]
    assert row["current"] == "18%" and row["target"] == "45%"
    assert row["delta"] == "+150%"          # (45-18)/18
    assert row["evidence_e_ids"] == ["E-045"]


def test_focus_kpi_rejects_target_uplift_mismatch() -> None:
    # current disclosed (12 days), but a 2-day target no roadmap rec
    # supports (the recs say → 4 days) → WRONG KPI, rejected.
    out = json.dumps({"kpis": [
        {"fa_id": "fa-1", "label": "Loan cycle time", "current": "12 days",
         "target": "2 days", "rationale": "aggressive", "evidence_e_ids": ["E-050"]},
    ]})
    assert _ACCEPT["focus_kpi_extraction"](out, _KPI_CTX) is None
    # the roadmap-consistent 4-day target IS accepted.
    ok = json.dumps({"kpis": [
        {"fa_id": "fa-1", "label": "Loan cycle time", "current": "12 days",
         "target": "4 days", "rationale": "automation", "evidence_e_ids": ["E-050"]},
    ]})
    got = _ACCEPT["focus_kpi_extraction"](ok, _KPI_CTX)
    assert got["kpis"][0]["target"] == "4 days"


def test_focus_kpi_rejects_fabricated_evidence_id() -> None:
    out = json.dumps({"kpis": [
        {"fa_id": "fa-1", "label": "STP rate", "current": "18%",
         "target": "45%", "rationale": "x", "evidence_e_ids": ["E-999"]},
    ]})
    assert _ACCEPT["focus_kpi_extraction"](out, _KPI_CTX) is None


# ── focus grounding (attach real, topically-relevant evidence ids) ─────────

_GROUND_CTX = {
    "grounding": (
        "[E-101] Loan origination workflow reduced decisioning to under 3 days.\n"
        "[E-102] The staff cafeteria refreshed its lunch menu in March."
    ),
    "_fa_ids": ["fa-1"],
    "_fa_text": {"fa-1": "Modernize the loan origination workflow decisioning"},
}


def test_focus_grounding_accepts_relevant_eid_only() -> None:
    out = json.dumps({"grounding": [
        {"fa_id": "fa-1", "evidence_e_ids": ["E-101", "E-102"]},
    ]})
    got = _ACCEPT["focus_grounding"](out, _GROUND_CTX)
    # E-101 shares ≥3 significant tokens (loan/origination/workflow/
    # decisioning); E-102 (cafeteria) is dropped as off-topic.
    assert got == {"grounding": [{"fa_id": "fa-1", "evidence_e_ids": ["E-101"]}]}


def test_focus_grounding_rejects_fabricated_eid() -> None:
    out = json.dumps({"grounding": [
        {"fa_id": "fa-1", "evidence_e_ids": ["E-777"]},
    ]})
    assert _ACCEPT["focus_grounding"](out, _GROUND_CTX) is None


# ── focus linked insights (Gemini adjudication of empties) ─────────────────

_LINK_CTX = {
    "_fa_ids": ["fa-1"],
    "_card_meta": {
        "c-1": {"id": "c-1", "ic_id": "IC-007", "title": "No CRM",
                "severity": "high", "linked_subcap_id": "P2C1.1.1",
                "e_ids": ["E-9"]},
    },
}


def test_focus_linked_insights_requires_real_card_id() -> None:
    out = json.dumps({"links": [
        {"fa_id": "fa-1", "card_ids": ["c-1", "c-FAKE"]},
    ]})
    got = _ACCEPT["focus_linked_insights"](out, _LINK_CTX)
    entries = got["links"][0]["linked_insights"]
    assert len(entries) == 1                     # c-FAKE dropped
    assert entries[0]["ic_id"] == "IC-007"
    assert entries[0]["source"] == "gemini"
    assert entries[0]["bases"][0]["kind"] == "gemini"
    # an all-fabricated link yields nothing.
    bad = json.dumps({"links": [{"fa_id": "fa-1", "card_ids": ["nope"]}]})
    assert _ACCEPT["focus_linked_insights"](bad, _LINK_CTX) is None


# ── focus subcap classification ────────────────────────────────────────────

def test_fa_subcap_ids_must_be_scored() -> None:
    ctx = {"_fa_ids": ["fa-1"], "_subcap_ids": ["P1C1.1.1", "P1C1.1.2", "P2C1.1.1"]}
    out = json.dumps({"assignments": [
        {"fa_id": "fa-1", "subcap_ids": ["P1C1.1.1", "P9C9.9.9", "P2C1.1.1"]}]})
    got = _ACCEPT["focus_subcap_classification"](out, ctx)
    assert got["assignments"][0]["subcap_ids"] == ["P1C1.1.1", "P2C1.1.1"]
    # a single surviving id (<2) is not a mapping
    out2 = json.dumps({"assignments": [{"fa_id": "fa-1", "subcap_ids": ["P1C1.1.1"]}]})
    assert _ACCEPT["focus_subcap_classification"](out2, ctx) is None


# ── techstack evidence linking ─────────────────────────────────────────────

def test_tech_evidence_link_requires_name_in_cited_line() -> None:
    ctx = {
        "grounding": "[E-010] The bank runs Salesforce Financial Services "
                     "Cloud for RM workflows.\n[E-020] Q3 revenue rose 4%.",
        "_rows": {"t-1": "Salesforce FSC", "t-2": "Snowflake"},
    }
    out = json.dumps({"links": [
        {"tech_id": "t-1", "e_ids": ["E-010", "E-020"]},   # E-020 line ≠ SF
        {"tech_id": "t-2", "e_ids": ["E-010"]},            # line ≠ Snowflake
    ]})
    got = _ACCEPT["techstack_evidence_linking"](out, ctx)
    assert got == {"links": [{"tech_id": "t-1", "e_ids": ["E-010"]}]}
