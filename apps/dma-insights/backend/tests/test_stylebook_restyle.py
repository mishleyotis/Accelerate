"""Unit tests for the 2026-07-13 anti-template layer: nlp.stylebook, the
capability-fact relevance gate, the template census masks, and the restyle
re-render regexes. Pure-logic, no DB."""
from __future__ import annotations

import re

from app.scripts.qa_template_census import _frames, _mask
from app.scripts.restyle_narratives import (
    _ORPHAN_SCORE_RE,
    _SCORE_LINE_NOPEER_RE,
    _SEQ_SOWHAT_RE,
    _SUBSTANCE_RE,
)
from app.services import startup_enrich as se
from app.services.nlp import stylebook as sb

# ── stylebook primitives ─────────────────────────────────────────────────────

def test_seeded_is_deterministic_and_key_sensitive():
    assert sb.seeded("a", "b").random() == sb.seeded("a", "b").random()
    assert sb.seeded("a", "b").random() != sb.seeded("a", "c").random()


def test_pick_fills_slots_and_stays_in_pool():
    rng = sb.seeded("x")
    pool = ("alpha {v}", "beta {v}")
    for _ in range(10):
        out = sb.pick(rng, pool, v="Z")
        assert out in ("alpha Z", "beta Z")


def test_scqa_style_is_content_first_and_spreads():
    # unresolved issue → risk eligible; identical signals still spread
    styles = {sb.scqa_style(f"client-{i}", {"unresolved_issue": True,
                                            "strength": True})
              for i in range(24)}
    assert "risk" in styles and len(styles) >= 2
    assert all(s in sb.SCQA_STYLES for s in styles)
    # stable per client
    assert (sb.scqa_style("k", {"new_hire": True})
            == sb.scqa_style("k", {"new_hire": True}))


# ── capability-fact relevance gate (the incoherent-splice floor) ────────────

def test_capability_fact_relevant_accepts_domain_and_name_matches():
    assert se.capability_fact_relevant(
        "Three production core systems retained through acquisitions with "
        "no member 360 view", "Data Foundation", "P4C1")
    assert se.capability_fact_relevant(
        "Personal eBanking upgraded Nov 18 — phased two-week deployment "
        "window across both channels", "UAT Planning & Execution", "P3C2")


def test_capability_fact_relevant_rejects_non_sequitur():
    assert not se.capability_fact_relevant(
        "Cetera Financial Institutions partnered with the bank to "
        "strengthen and grow the wealth management program, Sep 15, 2025",
        "Technology Operations & Reliability", "P3C1")


def test_pipeline_leak_titles_extended_classes():
    for leak in (
        "v5.5 assessment produces: P1_Subcap_Scoring, P2_Subcap_Scoring",
        "v2.4 expects a Calculation_Chain sheet with OVERALL hierarchy",
        "RC-02 requires 'peer proxy disclosure' with required phrases",
        "PV-01 sample of 15 subcaps: 93% PASS (14/15)",
        "Benchmark section Section 7 contains range-style evidence",
    ):
        assert se._is_pipeline_leak_title(leak), leak
    for real in (
        "2015 NY DFS Consent Order — BSA/AML noncompliance",
        "Acuity Advantage DTC net loss $682K after 4 years",
        "CIO/technology transformation leader vacant since Oct 2024",
    ):
        assert not se._is_pipeline_leak_title(real), real


# ── census masks ─────────────────────────────────────────────────────────────

def test_census_masks_score_notation_and_entity():
    s = ("Frost Bank reads 1.9/5 against a 2.8 peer median and pays $1.2B "
         "for it [E-001].")
    m = _mask(s, "Frost Bank")
    assert "SCORE_VS_PEER" in m and "$N" in m and "[CITE]" in m
    assert "ENTITY" in m and "Frost" not in m


def test_census_frames_are_six_word_shingles():
    frames = list(_frames("one two three four five six seven", ""))
    assert "one two three four five six" in frames
    assert all(len(f.split()) == 6 for f in frames)


# ── restyle re-render regexes ────────────────────────────────────────────────

def test_orphan_score_repair_pattern():
    t = "needs the Tableau capability. scores 1.5/5 on the current assessment."
    m = _ORPHAN_SCORE_RE.search(t)
    assert m and m.group("s") == "1.5"
    # a subject-carrying line is NOT an orphan
    ok = "The linked capability scores 1.5/5 on the current assessment."
    assert not _ORPHAN_SCORE_RE.search(ok)


def test_score_line_anchor_never_eats_sentence_boundary():
    t = ("a near-term opportunity. P4C3.1 scores 1.5/5 on the current "
         "assessment.")
    m = _SCORE_LINE_NOPEER_RE.search(t)
    # the anchor must not eat the ". " sentence boundary before it
    assert m and m.group("a").strip() == "P4C3.1"


def test_seq_sowhat_and_substance_frames_match_shipped_shapes():
    sw = ("Prioritize Modernize customer experience in the next phase; "
          "sequencing it first lifts the customer experience capabilities "
          "that depend on it.")
    m = _SEQ_SOWHAT_RE.match(sw)
    assert m and m.group("nm") == "Modernize customer experience"
    why = ("That is the substance the assessment reads into Sharpen "
           "strategic posture's 1.93/5, 1.1 points under the 3.0 peer "
           "median — the concrete constraint holding strategy and "
           "governance back.")
    assert _SUBSTANCE_RE.search(why)


# ── composer mandate invariants ──────────────────────────────────────────────

_BUNDLE = {
    "name": "Example Bank", "client_key": "example-0001", "overall": 2.4,
    "trend": "ACCELERATING", "cagr_pct": 9.1, "fin_eids": ["E-004"],
    "gaps": [{"name": "Data Foundation", "cat": "P4C1", "score": 1.9,
              "peer": 2.8, "eids": ["E-141"]}],
    "strengths": [{"name": "Claims Experience", "score": 3.6, "peer": 2.9}],
    "issues": [{"title": "Open AML consent order remediation through Q4 2026",
                "severity": "high", "eids": ["E-218"]}],
    "platforms": [{"name": "Salesforce", "fit": 82.0,
                   "top_subcap": "Data Foundation"}],
    "base_eids": ["E-001", "E-002"],
}


def test_scqa_every_style_leads_with_key_message_and_acts():
    from app.services.nlp.quality import _ACTION_RE
    for i in range(18):
        b = dict(_BUNDLE)
        b["client_key"] = f"c-{i}"
        md = se.compose_scqa_deep(b)["md"]
        first = md.split("\n\n")[0]
        assert "Data Foundation" in first, md[:120]
        assert _ACTION_RE.search(md), md
        for recap in ("regulated by", "operating since", " employees"):
            assert recap not in md


def test_scqa_no_gaps_composes_strengths_led_not_gap_skeleton():
    b = dict(_BUNDLE)
    b["gaps"] = []
    md = se.compose_scqa_deep(b)["md"]
    assert "Claims Experience" in md
    assert "binding gap" not in md.lower()
    assert re.search(r"extend|extension|invest", md)


# ── round-2 sweep: polarity + leak gates ─────────────────────────────────────

def test_leak_fact_re_catches_worksheet_rows():
    from app.scripts.restyle_narratives import _LEAK_FACT_RE
    for leak in (
        "DIRECT P2C1.1.1 EVIDENCE — AAFCU NAMED MARKETING DEPARTMENT",
        "PASS — DMA-ASM-TRST-20260330-0001 consistent across all artifacts",
        "Clay search for CDO/Data Governance titles returned ONLY 1 result",
        "Celent Model Bank Awards — United Business Bank NOT among them",
        "18 evidence items in index but never cited",
        "MANDATORY ANTI-GENERIC PROTOCOL: Each recommendation verified",
        "SO-006: Financial Scale & Credit Rating Upgrade",
        "public evidence supports this maturity level; internal discovery required",
    ):
        assert _LEAK_FACT_RE.search(leak), leak
    # a real client fact must pass through
    for ok in (
        "Three production core systems retained through acquisitions",
        "NAIC complaint index 0.66 — roughly 1/3 fewer complaints than expected",
        "2015 NY DFS Consent Order — BSA/AML noncompliance",
    ):
        assert not _LEAK_FACT_RE.search(ok), ok


def test_ws_token_re_strips_leading_subcap_code():
    from app.scripts.restyle_narratives import _WS_TOKEN_RE
    out = _WS_TOKEN_RE.sub("", "P3C3.5.4 Regulatory Change Management: NAIC updated")
    assert out.startswith("Regulatory Change Management")
    out2 = _WS_TOKEN_RE.sub("", "(P4C2.2.3 Embedded Analytics & Actionable Insights)")
    assert "P4C2" not in out2 and "Embedded Analytics" in out2
