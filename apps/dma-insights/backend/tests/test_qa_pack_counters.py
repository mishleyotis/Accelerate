"""Unit tests for the Part 0.3 acceptance-counter instruments (QA-gates
workstream 2026-07-02).

Every check function is fed SYNTHETIC page dicts hitting each rule — template
hit, artifact leak, 14-field signal pass/fail, contamination hit, parity
drift — no full-corpus dependency. The registry-freshness test pins the
CounterSpec registry to the collector output so a new counter cannot ship
unregistered (and vice versa).
"""
from __future__ import annotations

import pytest

from app.scripts import qa_coverage_contract as c
from app.scripts.qa_startup_audit import (
    baseline_value,
    counter_value,
    counter_verdicts,
)

# ── synthetic builders ───────────────────────────────────────────────────────

FULL_SIGNAL = {
    "label": "Core migration go-live", "category": "core_migration",
    "strength": "STRONG", "window": "Q3 2026", "confidence": "high",
    "claim": "FACT", "detail": "Jack Henry conversion announced for Q3 2026.",
    "metric": "$4.2M annual run-rate", "peer_context": "peers at 3.1",
    "play": "Scope a data-readiness workshop", "risk": "window closes at go-live",
    "evidence": ["E-012"], "timeline": {"date": "2026-09-01", "event": "go-live"},
    "impact": "unlocks P4C1 modernization",
}


def _bundle(**over) -> dict:
    b = {
        "_files": {p: "ok" for p in c.PAGE_FILES},
        "overview": {"overall_score": 2.4,
                     "pillar_scores": [{"pillar_id": "P1", "score": 2.2}],
                     "narrative": {"scqa_md": "A grounded story citing [E-001]."},
                     "why_now_signals": [dict(FULL_SIGNAL)],
                     "top_findings": [], "firmographics": {}},
        "insights": {"items": []},
        "heatmap": {"cells": [], "value_chain_buckets": []},
        "platforms": {"cards": []},
        "platforms_roadmap": {"phases": []},
        "context": {"timeline_events": [], "acquisitions": [], "financials": {},
                    "firmographics": {}, "narrative": {}},
        "techstack": {"items": []},
        "health": {}, "runs": {"items": []},
        "client_scores": {"scores": {"overall": 2.4, "pillars": {"P1": 2.2}}},
        "scores_row": {"overall": 2.4, "pillars": {"P1": 2.2}},
        "dashboard_card": {"overall_score": 2.4},
    }
    b.update(over)
    return b


# ── SCQA ─────────────────────────────────────────────────────────────────────

def test_scqa_template_families_hit_and_miss():
    assert c.scqa_hits_template("a targeted programme to close the gap would lift it")
    assert c.scqa_hits_template("This points to significant room to mature")
    assert c.scqa_hits_template("The deepest capability gaps concentrate in X")
    assert not c.scqa_hits_template("A concrete, entity-specific narrative.")


def test_scqa_counters_flag_artifacts_stub_length_eids():
    md = "Strengths: (: 1.68 ::F1 pending analyst synthesis " + "x" * 4100
    b = _bundle(overview={"overall_score": 2.4, "narrative": {"scqa_md": md},
                          "why_now_signals": [], "top_findings": [], "firmographics": {}})
    got = c.collect_scqa_counters(b)
    assert got["scqa_paren_colon_clients"] == (1.0, None)
    assert got["scqa_f_marker_clients"] == (1.0, None)
    assert got["scqa_stub_clients"] == (1.0, None)
    assert got["scqa_len_gt4000_clients"] == (1.0, None)
    assert got["scqa_zero_eid_clients"] == (1.0, None)  # no E-IDs in md


def test_scqa_clean_passes():
    got = c.collect_scqa_counters(_bundle())
    assert all(v == (0.0, None) for k, v in got.items())


def test_scqa_score_contradiction_tolerance():
    assert c.scqa_contradicts_score("overall maturity of 3.9 out of 5", 2.4)
    assert not c.scqa_contradicts_score("overall maturity of 2.5 out of 5", 2.4)  # .1 ≤ .15
    # a subcap-scoped claim (no overall context nearby) is not a contradiction
    assert not c.scqa_contradicts_score("Data governance scores 1.5 out of 5", 2.4)
    assert not c.scqa_contradicts_score("no numbers here", 2.4)
    # a subcap GAP score in the SAME sentence-run as the matching overall claim
    # must NOT be read as a contradiction (the 37→1 pack false-positive class):
    scqa = ("assessment places overall digital maturity at 3.0/5. The deepest "
            "capability gap is Model Inventory at 2.2/5 against a 3.0 peer median.")
    assert not c.scqa_contradicts_score(scqa, 3.08)  # overall 3.0≈3.08; 2.2 is a subcap
    # but a real drift on the OVERALL claim still fires:
    assert c.scqa_contradicts_score(
        "places overall digital maturity at 1.8/5. deepest gap is X at 1.2/5", 2.06)


# ── why-now ──────────────────────────────────────────────────────────────────

def test_signal_14_fields_pass_and_fail():
    assert c.signal_has_14_fields(FULL_SIGNAL)
    for missing in c.WHY_NOW_FIELDS:
        broken = {k: v for k, v in FULL_SIGNAL.items() if k != missing}
        assert not c.signal_has_14_fields(broken), missing


def test_signal_window_detection():
    assert c.signal_has_window({"window": "Q3 2026"})
    assert c.signal_has_window({"text": "an 18-month consent-order clock"})
    assert c.signal_has_window({"detail": "go-live scheduled"})
    assert not c.signal_has_window({"text": "a structural gap in personalization"})


def test_why_now_counters_aggregate():
    b = _bundle()
    b["overview"]["why_now_signals"] = [dict(FULL_SIGNAL), {"text": "gap only"}]
    got = c.collect_why_now_counters(b)
    assert got["why_now_ge3_clients"] == (0.0, None)      # only 2 signals
    assert got["why_now_fields14_pct"] == (1.0, 2.0)
    assert got["why_now_evidence_pct"] == (1.0, 2.0)


# ── findings ─────────────────────────────────────────────────────────────────

def test_finding_truncation_rules():
    base = "An observed fact with enough substance to pass the length floor ok."
    assert not c.finding_is_truncated({"body": base + " It ends cleanly."})
    assert c.finding_is_truncated({"body": base + " ends with uneve—"})
    assert c.finding_is_truncated({"body": base + " trails off…"})
    assert c.finding_is_truncated({"body": "too short"})
    assert c.finding_is_truncated({"body": ""})


def test_findings_wwsw_and_scored():
    full = {"what": "w", "why": "y", "so_what": "s", "score": 2.0,
            "peer_median": 3.0, "subcap_id": "P1C1", "evidence": ["E-1"],
            "body": "A finding body that is long enough and ends properly."}
    partial = {"body": "Another body that is long enough and ends properly here.",
               "score": None, "peer_median": 3.0, "subcap_id": "P1C1"}
    b = _bundle()
    b["overview"]["top_findings"] = [full, partial]
    got = c.collect_findings_counters(b)
    assert got["findings_wwsw_pct"] == (1.0, 2.0)
    assert got["findings_scored_pct"] == (1.0, 2.0)
    assert got["findings_evidence_pct"] == (1.0, 2.0)


# ── insights ─────────────────────────────────────────────────────────────────

def test_insight_template_and_evidence_and_affects():
    tmpl = {"ic_id": "GAP-P2C1-1", "so_what_text": "a targeted programme to close the gap",
            "linked_e_ids": [], "affects": []}
    rich = {"ic_id": "INS-RPT-01", "so_what_text": "Board mandated a 2026 core swap.",
            "linked_e_ids": ["E-1"], "affects": ["P1C1", "P2C3", "P4C1"]}
    b = _bundle(insights={"items": [tmpl, rich]})
    got = c.collect_insight_counters(b)
    assert got["insights_template_pct"] == (1.0, 2.0)
    assert got["insights_zero_evidence_pct"] == (1.0, 2.0)
    assert got["insights_affects_avg"] == (3.0, 2.0)
    assert got["insights_report_sourced_pct"] == (1.0, 2.0)


def test_insight_title_body_mismatch_gap_card():
    # the audit's LATERAL-join class: title names X, body describes Y
    bad = {"ic_id": "GAP-P2C1-1", "title": "Channel Strategy trails peers by 1.4",
           "what_text": "Budget Allocation & ROI is one of the least developed…",
           "so_what_text": "Make Budget Allocation & ROI a near-term focus for X."}
    good = {"ic_id": "GAP-P2C1-2", "title": "Budget Allocation & ROI trails peers",
            "so_what_text": "Make Budget Allocation & ROI a near-term focus."}
    rec = {"ic_id": "INS-REC-01", "title": "CRM Modernization — FSC",
           "so_what_text": "Make Transaction Triggers a near-term focus."}
    # GAP category card: WHAT names an in-category subcap, SO-WHAT names the
    # category (title) via a non-"Make" lead — NOT a mismatch (2026-07-03).
    gap_cat = {"ic_id": "GAP-P2C4",
               "title": "CX & Personalization trails peers by 1.1",
               "what_text": "Behavioral Data Capture is one of X's least developed…",
               "so_what_text": "Prioritize CX & Personalization: recover the deficit."}
    assert c.insight_title_body_mismatch(bad)
    assert not c.insight_title_body_mismatch(good)
    assert not c.insight_title_body_mismatch(rec)  # only GAP cards carry the bug
    assert not c.insight_title_body_mismatch(gap_cat)


# ── heatmap ──────────────────────────────────────────────────────────────────

def test_heatmap_counters():
    cells = [
        {"id": "P1C1.1.1", "band": "M2", "cap_applied": False,
         "peer_median": 2.9, "enrichment_evidence_ids": ["E-1"]},
        {"id": "P1C1.1.2", "band": "M3", "cap_applied": True,
         "peer_median": None, "enrichment_evidence_ids": []},
    ]
    b = _bundle(heatmap={"cells": cells, "value_chain_buckets": [], "narrative":
                         {"per_subcap_meta": {"P1C1.1.1": {"text": "x"}}}},
                heatmap_value_chain={"value_chain_buckets": [{}] * 6})
    got = c.collect_heatmap_counters(b)
    assert got["vc_buckets6_clients"] == (1.0, None)
    assert got["heatmap_subcap_synthesis_clients"] == (1.0, None)
    assert got["heatmap_peer_median_cells_pct"] == (1.0, 2.0)
    assert got["heatmap_evidence_cells_pct"] == (1.0, 2.0)
    assert got["heatmap_band_pct"] == (2.0, 2.0)
    assert got["heatmap_cap_fields_pct"] == (2.0, 2.0)


# ── platforms ────────────────────────────────────────────────────────────────

def test_platform_red_hot_and_starters():
    cards = [
        {"fit_score": 86.0, "readiness_index": "red", "state": "READY",
         "conversation_starters": ["Discovery: ask how they handle P1C1.1.1 today"],
         "evidence_ids": [], "opportunity_md": "**X** at 86/100."},
        {"fit_score": 55.0, "readiness_index": "green", "state": "NEEDS_FOUNDATION",
         "conversation_starters": ["Pain: probe the $42M SavvyMoney ROI at Acme FCU"],
         "evidence_ids": ["E-2"], "opportunity_md": "**Y** different skeleton."},
    ]
    b = _bundle(platforms={"cards": cards},
                platforms_roadmap={"phases": [{"recommendations": [
                    {"maturity_lift": None},
                    {"maturity_lift": 0.5, "root_cause_e_ids": ["E-1"],
                     "outcomes": {"time": "6mo"}}]}]})
    got = c.collect_platform_counters(b, "Acme FCU")
    assert got["platform_red_fit80_cards"] == (1.0, None)
    assert got["platform_state_ready_pct"] == (1.0, 2.0)
    assert got["starters_p1c111_anchor_pct"] == (1.0, 2.0)
    assert got["starters_entity_fact_pct"] == (1.0, 2.0)  # $ fact / entity name
    assert got["platform_cards_zero_evidence"] == (1.0, None)
    assert got["roadmap_single_phase_clients"] == (1.0, None)
    assert got["roadmap_rec_root_cause_pct"] == (1.0, 2.0)
    assert got["roadmap_rec_outcomes_pct"] == (1.0, 2.0)
    assert got["roadmap_maturity_lift_null_pct"] == (1.0, 2.0)


def test_starter_entity_fact_ignores_subcap_ids_and_fit():
    card = {"conversation_starters":
            ["Discovery: ask about P1C1.1.1 (fit 81/100) and P4C1.1.1 next."]}
    assert not c.starter_names_entity_fact(card, "Acme FCU")
    card2 = {"conversation_starters": ["Reference the +$230M loan growth as ROI."]}
    assert c.starter_names_entity_fact(card2, "Acme FCU")


def test_opportunity_signature_collapses_variants():
    a = "**Salesforce** is the highest-fit platform at 79/100, concentrated in P2."
    b2 = "**Tableau** is the highest-fit platform at 82/100, concentrated in P4."
    different = "**Twilio** owns the contact-center modernization angle (CCaaS)."
    assert c.opportunity_signature(a) == c.opportunity_signature(b2)
    assert c.opportunity_signature(a) != c.opportunity_signature(different)


# ── context ──────────────────────────────────────────────────────────────────

def test_event_date_defaulted():
    assert c.event_date_defaulted({"date_precision": "publish_fallback"})
    assert not c.event_date_defaulted({"date_precision": "day",
                                       "event_date": "2026-04-01"})
    # pre-migration heuristic: month-start pile-ups
    assert c.event_date_defaulted({"event_date": "2026-04-01"})
    assert not c.event_date_defaulted({"event_date": "2026-04-17"})


def test_title_garbage_heuristics():
    # structural defects → garbage
    assert c.title_is_garbage("First sentence. Second one. Third.")  # raw multi-sentence
    assert c.title_is_garbage("04_reports/Assessment_Report.docx")   # file-path artifact
    assert c.title_is_garbage("Something TRUNC")                     # truncation marker
    assert c.title_is_garbage("consol—")                            # mid-word truncation
    assert c.title_is_garbage("P1C1.1.1 Data governance foundation")  # subcap-id prefix
    assert c.title_is_garbage("STRATEGIC POSTURE: governance lags")  # ALL-CAPS header prefix
    assert c.title_is_garbage("**Bold markdown heading**")           # markdown marker
    # legitimate NLP titles → NOT garbage (the recalibrated false-positive classes)
    assert not c.title_is_garbage(" ".join(["word"] * 19))          # long single clean run
    assert not c.title_is_garbage("Anchor Bancorp/Anchor Bank")     # inline prose slash
    assert not c.title_is_garbage("52-branch consolidation planned…")  # intentional clip
    assert not c.title_is_garbage("Acme selects nCino for lending")  # clean title


def test_context_counters_negation_dupes_acq_prose_keys():
    events = [
        {"title": "NEGATIVE SEARCH RESULT: no orders", "event_date": "2026-04-01",
         "e_id": "E-1"},
        {"title": "Acme acquires Beta Bank", "event_date": "2026-03-14", "e_id": "E-2"},
        {"title": "Acme acquires Beta Bank", "event_date": "2026-03-14", "e_id": "E-3"},
    ]
    ctx = {
        "timeline_events": events,
        "acquisitions": [{"acquirer": "Acme", "target": "Beta Bank"}, {"title": "loose"}],
        # D5 financials_view contract: series_labeled is the Part 8.4 shape
        "financials": {"metrics": {"Total Assets ($B)": 4.2,
                                   "workforce_scale_stands_at_approximately_750": 750},
                       "years": [2024, 2025], "series": {"value": [4.0, 4.2]},
                       "series_labeled": [{"metric": "total_assets", "unit": "$B",
                                           "fy": [2024, 2025], "values": [4.0, 4.2]}]},
        "firmographics": {"license_type": "State charter", "jurisdictions": ["TX"],
                          "leadership": [{"name": "A", "tenure_months": 24},
                                         {"name": "B"}]},
        # D5 sentiment_view contract: {sources: [...]} with honest-None values
        "sentiment": {"sources": [{"source": "Glassdoor", "kind": "employee",
                                   "value": 3.9, "max": 5, "n": 120,
                                   "polarity": None, "themes": [],
                                   "drilldown": None, "evidence_e_id": None}]},
        "narrative": {"trend_md": "Assets grew 8% CAGR."},
    }
    got = c.collect_context_counters(_bundle(context=ctx))
    assert got["context_negation_title_pct"] == (1.0, 3.0)
    assert got["context_duplicate_events"] == (1.0, None)
    assert got["acq_structured_pct"] == (1.0, 2.0)
    assert got["fin_prose_keys"] == (1.0, None)
    assert got["fin_series_labeled_pct"] == (1.0, 1.0)
    assert got["sentiment_structured_pct"] == (1.0, 1.0)
    assert got["context_license_jurisdiction_clients"] == (1.0, None)
    assert got["context_leadership_tenure_pct"] == (1.0, 2.0)
    assert got["context_trend_md_missing_clients"] == (0.0, None)


def test_sentiment_fragments_are_not_structured():
    assert not c.sentiment_is_structured("4.1 stars and 230 reviews")
    assert not c.sentiment_is_structured([{"source": "Glassdoor"}])  # no value
    assert c.sentiment_is_structured({"employee": [], "customer": []})
    # D5 sources shape: value KEY required (honest-None allowed), source required
    assert c.sentiment_is_structured(
        {"sources": [{"source": "BBB", "value": None, "max": None, "n": 3}]})
    assert not c.sentiment_is_structured({"sources": [{"kind": "customer"}]})
    assert not c.sentiment_is_structured({"sources": []})


def test_fin_series_legacy_unlabeled_counts_as_unlabeled():
    got = c.collect_context_counters(_bundle(context={
        "timeline_events": [], "acquisitions": [],
        "financials": {"years": [2024, 2025], "series": {"value": [1.0, 2.0]}},
        "firmographics": {}, "narrative": {}}))
    assert got["fin_series_labeled_pct"] == (0.0, 1.0)


# ── tech stack ───────────────────────────────────────────────────────────────

def test_techstack_deny_lists_and_status():
    items = [
        {"product": "JavaScript", "status": "DETECTED"},
        {"product": "Various", "status": "DETECTED"},
        {"product": "Salesforce", "status": "CONFIRMED"},
        {"product": "Siebel", "status": "CONFIRMED_REMOVED"},
        {"product": "Snowflake", "status": "ABSENT", "peer_coverage": 0.4},
    ]
    got = c.collect_techstack_counters(_bundle(techstack={"items": items}))
    assert got["tech_language_os_rows"] == (1.0, None)
    assert got["tech_noise_rows"] == (1.0, None)
    assert got["tech_disallowed_rows"] == (2.0, None)
    assert got["tech_absent_row_clients"] == (1.0, None)
    assert got["tech_peer_coverage_clients"] == (1.0, None)
    assert got["tech_status_valid_pct"] == (3.0, 5.0)  # DETECTED rows are dishonest


# ── firmographics ────────────────────────────────────────────────────────────

def test_firmographic_nulls_and_provenance():
    firm = {"website": "https://acme.example", "website_basis": "entity_profile",
            "cagr": 8.2,  # present but no provenance
            "leadership": [{"name": "A"}], "aum_usd": 4.2e9, "aum_basis": "package"}
    b = _bundle(overview={"overall_score": 2.4, "firmographics": firm,
                          "narrative": {}, "why_now_signals": [], "top_findings": []})
    got = c.collect_firmographic_counters(b)
    assert got["firm_null_website"] == (0.0, None)
    assert got["firm_null_cagr"] == (0.0, None)
    assert got["firm_null_ticker"] == (1.0, None)
    assert got["firm_null_leadership"] == (0.0, None)
    # website+aum provenanced, cagr not → 2/3
    assert got["firm_provenance_pct"] == (2.0, 3.0)
    assert len([k for k in got if k.startswith("firm_null_")]) == len(c.FIRM_FIELDS)


# ── value parity ─────────────────────────────────────────────────────────────

def test_score_parity_detects_drift_and_tolerates_rounding():
    assert not c.score_parity_mismatch(_bundle())  # all equal
    b = _bundle()
    b["overview"]["overall_score"] = 2.82
    b["scores_row"]["overall"] = 2.75
    assert c.score_parity_mismatch(b)              # the AH4R class
    b2 = _bundle()
    b2["overview"]["overall_score"] = 2.36          # 2dp rounding of 2.3559
    b2["scores_row"]["overall"] = 2.3559
    b2["client_scores"]["scores"]["overall"] = 2.3559
    b2["dashboard_card"]["overall_score"] = 2.3559
    assert not c.score_parity_mismatch(b2)
    b3 = _bundle()
    b3["overview"]["pillar_scores"] = [{"pillar_id": "P1", "score": 2.9}]
    assert c.score_parity_mismatch(b3)              # pillar drift vs 2.2


# ── markdown lint ────────────────────────────────────────────────────────────

def test_markdown_counter_flags_artifact_fields():
    b = _bundle(overview={"overall_score": 2.4, "why_now_signals": [], "top_findings": [],
                          "firmographics": {"narrative_md": "broken (: 1.68 label"},
                          "narrative": {"scqa_md": "clean text with [E-001]."}})
    got = c.collect_markdown_counters(b)
    assert got["markdown_lint_flagged_fields"] == (1.0, None)


# ── contamination ────────────────────────────────────────────────────────────

def test_contamination_hit_whitelist_and_skips():
    b = _bundle()
    b["overview"]["narrative"]["scqa_md"] = (
        "Acme FCU's roadmap mirrors Langley Federal Credit Union's playbook. [E-1]")
    names = {"Langley Federal Credit Union", "CCU", "Acme FCU of Texas"}
    hits = c.foreign_name_hits(b, "Acme FCU", names)
    assert hits == ["Langley Federal Credit Union"]
    # peer-cue clause → analytic content, not contamination
    b["overview"]["narrative"]["scqa_md"] = (
        "Acme trails the peer median set by Langley Federal Credit Union. [E-1]")
    assert c.foreign_name_hits(b, "Acme FCU", names) == []
    # ≤3-char names (CCU) and own-name superstrings are never counted
    b["overview"]["narrative"]["scqa_md"] = "CCU and Acme FCU of Texas appear here."
    assert c.foreign_name_hits(b, "Acme FCU", names) == []


def test_contamination_ignores_peer_context_field():
    b = _bundle()
    b["overview"]["why_now_signals"] = [
        {**FULL_SIGNAL, "peer_context": "Langley Federal Credit Union runs FSC"}]
    assert c.foreign_name_hits(b, "Acme FCU", {"Langley Federal Credit Union"}) == []


# ── surfaces + dashboard ─────────────────────────────────────────────────────

def test_surface_counters_tolerate_absent_new_surfaces():
    b = _bundle()
    b["_files"]["focus_areas"] = "absent"
    b["_files"]["heatmap_value_chain"] = "absent"
    b["_files"]["evidence"] = "absent"
    got = c.collect_surface_counters(b)
    assert got["pages_loaded_10_clients"] == (1.0, None)
    assert got["surface_focus_areas_clients"] == (0.0, None)
    assert got["surface_value_chain_clients"] == (0.0, None)
    assert got["surface_evidence_clients"] == (0.0, None)


def test_surface_evidence_counter_counts_baked_rows():
    b = _bundle(evidence={"items": [{"e_id": "E-001", "tier": 2}]})
    b["_files"]["evidence"] = "ok"
    assert c.collect_surface_counters(b)["surface_evidence_clients"] == (1.0, None)
    # File present but zero rows → NOT counted (an empty bake is a defect,
    # mirroring export_startup_pages' _REQUIRED/_nonempty contract).
    b2 = _bundle(evidence={"items": []})
    b2["_files"]["evidence"] = "ok"
    assert c.collect_surface_counters(b2)["surface_evidence_clients"] == (0.0, None)


def test_dashboard_counters():
    dash = {"dashboard": {"catalogue_version": "v7.0", "recent_completions": [
        {"display_id": "a-0001"}, {"display_id": "b-0001"}]}}
    got = c.collect_dashboard_counters(dash, 2)
    assert got["dashboard_recent_completions_match"] == (1.0, None)
    assert got["dashboard_catalogue_version"] == (1.0, None)
    got = c.collect_dashboard_counters({"dashboard": {}}, 2)
    assert got["dashboard_recent_completions_match"] == (0.0, None)
    assert got["dashboard_catalogue_version"] == (0.0, None)


# ── registry freshness ───────────────────────────────────────────────────────

# counters computed at corpus level by the runner, not per-client collectors
_CORPUS_LEVEL = {"opportunity_md_dominant_skeleton_pct",
                 "dashboard_recent_completions_match", "dashboard_catalogue_version"}


def test_every_registered_counter_is_produced_and_vice_versa():
    produced = set(c.collect_client_counters(_bundle(), entity_name="Acme",
                                             foreign_names={"Other Bank"}))
    produced |= set(c.collect_dashboard_counters({}, 1))
    produced |= {"opportunity_md_dominant_skeleton_pct"}
    registered = {s.name for s in c.COUNTERS}
    assert registered - produced == set(), "registered but never computed"
    assert produced - registered == set(), "computed but unregistered"


def test_counter_specs_are_well_formed():
    seen = set()
    for spec in c.COUNTERS:
        assert spec.name not in seen, f"duplicate counter {spec.name}"
        seen.add(spec.name)
        assert spec.direction in ("<=", ">=")
        assert spec.severity in ("hard", "soft")
        assert spec.script, spec.name


# ── verdict/baseline gate (qa_startup_audit) ─────────────────────────────────

def _one_spec_totals(name: str, num: float, den: float | None):
    return {name: [num, den]}


def test_counter_verdicts_baseline_suppression_and_hard_fail():
    spec = c.COUNTER_INDEX["scqa_zero_eid_clients"]  # <=0, baseline-mapped
    totals = _one_spec_totals(spec.name, 92.0, None)
    bl = {"overview": {"scqa": {"zero_eids": 92}}}
    v = {x["name"]: x for x in counter_verdicts(totals, 94, bl)}[spec.name]
    assert v["status"] == "baseline" and v["suppressed"]
    # worse than baseline → hard fail even with --baseline
    totals = _one_spec_totals(spec.name, 93.0, None)
    v = {x["name"]: x for x in counter_verdicts(totals, 94, bl)}[spec.name]
    assert v["status"] == "fail"
    # no baseline recorded → failing counter still fails
    v = {x["name"]: x for x in counter_verdicts(totals, 94, {})}[spec.name]
    assert v["status"] == "fail"
    # without --baseline (None) → plain fail
    v = {x["name"]: x for x in counter_verdicts(totals, 94, None)}[spec.name]
    assert v["status"] == "fail"


def test_counter_verdicts_all_clients_target_and_na():
    spec = c.COUNTER_INDEX["vc_buckets6_clients"]  # ALL_CLIENTS target
    v = {x["name"]: x for x in counter_verdicts(
        _one_spec_totals(spec.name, 94.0, None), 94, None)}[spec.name]
    assert v["status"] == "pass" and v["target"] == 94.0
    # pct counter with zero denominator → N/A → pass
    spec2 = c.COUNTER_INDEX["fin_series_labeled_pct"]
    v2 = {x["name"]: x for x in counter_verdicts(
        _one_spec_totals(spec2.name, 0.0, 0.0), 94, None)}[spec2.name]
    assert v2["status"] == "na" and v2["pass"]


def test_baseline_value_prefers_counters_section():
    spec = c.COUNTER_INDEX["score_parity_mismatch_clients"]
    bl = {"counters": {"score_parity_mismatch_clients": 20},
          "pack_integrity": {"score_drift_clients": 19}}
    assert baseline_value(bl, spec) == 20.0
    assert baseline_value({"pack_integrity": {"score_drift_clients": 19}}, spec) == 19.0
    assert baseline_value(None, spec) is None


@pytest.mark.parametrize("unit,num,den,expected", [
    ("pct", 50.0, 200.0, 25.0),
    ("avg", 6.0, 3.0, 2.0),
    ("clients", 7.0, None, 7.0),
    ("pct", 0.0, 0.0, None),
])
def test_counter_value_units(unit, num, den, expected):
    spec = c.CounterSpec("x", "s", 0, "<=", unit, "hard")
    assert counter_value(spec, num, den) == expected


# ── stress-test probes (coordinator additions 2026-07-02) ────────────────────

def test_focus_probes_title_and_grounding():
    items = [
        {"title": "F-01", "grounding": {"representative_quote": "x", "evidence_e_ids": []}},
        {"title": "Gaps", "verbatim_quote": "growth [E-012] cited",
         "grounding": {"representative_quote": "", "evidence_e_ids": []}},
        {"title": "Member experience modernization",
         "grounding": {"representative_quote": "quote [E-3]",
                       "evidence_e_ids": ["E-3"], "source_kind": "docx"}},
    ]
    got = c.collect_focus_counters(_bundle(focus_areas={"items": items}))
    assert got["focus_title_hygiene"] == (2.0, None)   # F-01 id + <8 chars
    assert got["focus_grounding_eids"] == (1.0, None)  # [E- quote, no eids


def test_synthesis_probes_none_generic_substance():
    narr = {"per_subcap": {
        "P1C1.1.1": "Score 2.0 vs peer: None — pending",                # none leak
        "P1C1.1.2": "capability dimension 3 trails the cohort",          # generic
        "P1C1.1.3": "Scores 2.0 vs peer 3.1 [E-004] [E-007].",           # hollow citation
        "P1C1.1.4": "Runs Salesforce with 4 data silos [E-004].",        # substantive
        "P1C1.1.5": {"narrative_md": "Subcap 7 (P1C1.1.5) placeholder"},  # generic dict form
    }}
    got = c.collect_synthesis_counters(_bundle(heatmap={"cells": [], "narrative": narr}))
    assert got["synthesis_none_leak"] == (1.0, None)
    assert got["synthesis_generic_name"] == (2.0, None)
    assert got["synthesis_evidence_substance"] == (1.0, None)
    # non-evidence-bearing text is not "hollow" (other counters own it)
    assert not c.synthesis_lacks_substance("Scores 2.0 vs peer 3.1, no citations")


def test_timeline_title_artifacts():
    events = [
        {"title": "Acme launches core ="},          # dangling markup
        {"title": "- Acme selects nCino"},          # list marker lead
        {"title": "**Regulatory update**"},         # md emphasis lead
        {"title": "Acme selects nCino for lending"},
    ]
    got = c.collect_context_counters(_bundle(context={
        "timeline_events": events, "acquisitions": [], "financials": {},
        "firmographics": {}, "narrative": {}}))
    assert got["timeline_title_artifacts"] == (3.0, None)
