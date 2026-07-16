"""Part 5.1 D2 derivation-ladder platform tests (shared builders in
``parsers/section_analysis.py`` used by BOTH the ingest ladder and the
DB re-derive).

Pins: the profile-findings quote parser (structured 5-col rows + plain
paragraphs + meta-prose guard), ladder priority (profile > section >
recs via ``combine_insight_rungs``), the multi-``affects[]`` subcap
classifier on real profile text (cross-pillar), counter-evidence
detection (claim-type AND polarity tiers), zennify-opportunity card
generation from a real knowledge row (fully-evidenced-or-not-emitted),
the zero-evidence ladder's ``basis`` marker, and the demoted
category-gap rung (cap 4, rotating non-template prose).
"""
from __future__ import annotations

import re

from app.schemas.package import CategoryScoreRow, InsightCardRow
from app.services.parsers.section_analysis import (
    SubcapClassifier,
    basis_marker,
    combine_insight_rungs,
    counter_evidence_ids,
    insights_from_category_gaps,
    insights_from_profile_findings,
    insights_from_zennify_opportunities,
    offering_platform_family,
    profile_finding_from_quote,
)

# A REAL Client Profile findings-table row (CCU package, focus_areas
# verbatim_quote shape: F-ID | Title | Observation [E-###] | Maturity |
# Zennify relevance).
_REAL_ROW = (
    "F-003 | Critical Third-Party Vendor Breach | Marquis ransomware: "
    "111,368 members' PII exposed via SonicWall exploit (Aug 2025) "
    "[E-016, E-053] | CRITICAL cap P3C4/P4C4 at M2 | "
    "Shield/Security Cloud; vendor risk management"
)

# A REAL zennify-opportunity knowledge row (client_knowledge_sections
# artifact_kind='zennify_opportunity' provenance, Acuity package).
_REAL_OPP = {
    "opportunity_id": "OPP-002",
    "opportunity": "MuleSoft Integration Layer",
    "priority": "HIGH",
    "trigger_evidence": "E-089, E-066",
    "zennify_offering": "API-led connectivity for SaaS-to-legacy core",
    "pillar_alignment": "P4C3,P3C1",
    "entry_point": "Hybrid architecture requires integration fabric",
    "e_ids": ["E-089", "E-066"],
    "pillar_refs": ["P4C3", "P3C1"],
}


# ── profile_finding_from_quote ───────────────────────────────────────

def test_profile_quote_structured_row_parses_all_five_columns() -> None:
    pf = profile_finding_from_quote("F-003", _REAL_ROW)
    assert pf is not None
    assert pf.finding_id == "F-003"
    assert pf.title == "Critical Third-Party Vendor Breach"
    assert pf.observation.startswith("Marquis ransomware: 111,368")
    assert pf.maturity == "CRITICAL cap P3C4/P4C4 at M2"
    assert pf.zennify.startswith("Shield/Security Cloud")
    assert pf.e_ids == ["E-016", "E-053"]
    assert pf.subcap_refs == ["P3C4", "P4C4"]


def test_profile_quote_plain_paragraph_with_lead_title() -> None:
    pf = profile_finding_from_quote(
        "Key Findings with Zennify Relevance",
        "Data Governance Gap: No Chief Data Officer identified. Active "
        "hiring of 10+ data governance roles signals investment [E-077].",
    )
    assert pf is not None
    # Section heading is generic → the observation's own lead becomes
    # the title.
    assert pf.title == "Data Governance Gap"
    assert pf.e_ids == ["E-077"]


def test_profile_quote_rejects_meta_and_pipeline_prose() -> None:
    assert profile_finding_from_quote(
        "1", "Each finding includes a quantified observation with "
        "evidence IDs, maturity implication, and Zennify relevance.",
    ) is None
    assert profile_finding_from_quote(
        "x", "SECTION 2 COMPLETE — Assessment ID DMA-FOO | Evidence "
        "Mode: PUBLIC and some other pipeline noise text",
    ) is None
    assert profile_finding_from_quote("x", "too short") is None


# ── insights_from_profile_findings ───────────────────────────────────

def test_profile_findings_become_primary_rung_cards() -> None:
    pf = profile_finding_from_quote("F-003", _REAL_ROW)
    cards = insights_from_profile_findings([pf], sub_scores={"P3C4": 1.8})
    assert len(cards) == 1
    c = cards[0]
    assert c.ic_id == "CP-F-003"
    # The analyst wrote CRITICAL → severity critical (not the M2 medium).
    assert c.severity == "critical"
    assert c.linked_subcap_id == "P3C4"
    # WHAT is the report's own observation, verbatim incl. citations.
    assert "111,368 members" in c.what_text
    assert c.linked_e_ids == ["E-016", "E-053"]
    # WHY carries the report's ceiling clause + the live score standing.
    assert "CRITICAL cap P3C4/P4C4 at M2" in c.why_text
    assert "1.8/5" in c.why_text
    # SO-WHAT is the report's Zennify play, framed as the next move
    # (actionable per the nlp.quality rubric).
    assert c.so_what_text.startswith("Recommended play:")
    assert "Shield/Security Cloud" in c.so_what_text


def test_profile_findings_skip_unanchorable_without_classifier() -> None:
    pf = profile_finding_from_quote(
        "T", "A statement about nothing capability-shaped whatsoever "
        "that still is long enough to pass the length gate.",
    )
    assert pf is not None and pf.subcap_refs == []
    assert insights_from_profile_findings([pf]) == []


# ── SubcapClassifier (multi-affects, cross-pillar) ──────────────────

def test_affects_classifier_cross_pillar_on_real_profile_text() -> None:
    clf = SubcapClassifier()  # keyword-anchor tier only (no catalogue)
    affects = clf.affects_for(
        "Marquis ransomware: 111,368 members' PII exposed via SonicWall "
        "exploit. Vendor risk management gaps compound the breach; the "
        "credit union has no CRM and manual loan origination workflow.",
        anchor="P3C4",
    )
    assert affects[0] == "P3C4"          # anchor always first
    assert "P4C4" in affects             # cyber/ransomware/breach
    assert "P2C4" in affects             # CRM
    pillars = {a[:2] for a in affects}
    assert len(pillars) >= 2             # cross-pillar contract


def test_affects_classifier_resolves_category_to_weakest_leaf() -> None:
    scores = {"P4C4.1.1": 2.9, "P4C4.2.2": 1.3}

    def leaf(cat: str) -> str | None:
        subs = {s: v for s, v in scores.items() if s.startswith(cat + ".")}
        return min(subs, key=subs.get) if subs else None

    clf = SubcapClassifier(resolve_leaf=leaf)
    affects = clf.affects_for("Ransomware breach exposed member PII.")
    assert "P4C4.2.2" in affects         # category ref → weakest leaf


def test_affects_classifier_similarity_tier_vs_catalogue_names() -> None:
    clf = SubcapClassifier({
        "P2C4.1.1": "CRM Platform Adoption",
        "P4C1.2.1": "Customer Data Platform Foundation",
        "P1C5.1.1": "ESG Reporting",
    })
    affects = clf.affects_for(
        "The institution lacks a modern CRM platform and any customer "
        "data platform foundation for unified member profiles.",
    )
    assert "P2C4.1.1" in affects or "P4C1.2.1" in affects


# ── counter-evidence detection ───────────────────────────────────────

def test_counter_evidence_claim_type_and_polarity_tiers() -> None:
    evidence = [
        # Same subcap, POSITIVE claim label → counters a gap card.
        {"e_id": "E-101", "claim_type": "POSITIVE", "tier": 2,
         "excerpt": "irrelevant", "subcap_ids": ["P2C1.1.1"]},
        # Same subcap, neutral label but positive polarity in the
        # excerpt → nlp.polarity catches it (the 40% EVIDENCE/FACT class).
        {"e_id": "E-102", "claim_type": "EVIDENCE", "tier": 3,
         "excerpt": "Mobile app launched with strong adoption and "
                    "record engagement growth.",
         "subcap_ids": ["P2C1.1.1"]},
        # Different subcap → never a counter.
        {"e_id": "E-103", "claim_type": "POSITIVE", "tier": 1,
         "excerpt": "great", "subcap_ids": ["P4C1.1.1"]},
        # Supporting E-IDs are excluded.
        {"e_id": "E-104", "claim_type": "POSITIVE", "tier": 1,
         "excerpt": "great", "subcap_ids": ["P2C1.1.1"]},
    ]
    counters = counter_evidence_ids(
        "P2C1.1.1", "high", ["E-104"], evidence)
    assert counters == ["E-101", "E-102"]   # tier order, best first


def test_counter_evidence_for_strength_cards_wants_negatives() -> None:
    evidence = [
        {"e_id": "E-201", "claim_type": "NEGATIVE", "tier": 2,
         "excerpt": "x", "subcap_ids": ["P1C1"]},
        {"e_id": "E-202", "claim_type": "POSITIVE", "tier": 1,
         "excerpt": "x", "subcap_ids": ["P1C1"]},
    ]
    assert counter_evidence_ids("P1C1", "low", [], evidence) == ["E-201"]


# ── zennify-opportunity OPPORTUNITY cards ────────────────────────────

def test_zennify_opportunity_card_from_real_knowledge_row() -> None:
    cards = insights_from_zennify_opportunities(
        [_REAL_OPP],
        sub_scores={"P4C3": 2.1},
        evidence_excerpts={
            "E-089": ("Job posting seeks integration engineers for the "
                      "core modernization program.", "Indeed"),
        },
    )
    assert len(cards) == 1
    c = cards[0]
    assert c.ic_id == "Z-OPP-002"
    assert c.severity == "high"          # HIGH priority → OPPORTUNITY flag
    assert c.linked_subcap_id == "P4C3"  # pillar_refs anchor
    assert c.linked_e_ids == ["E-089", "E-066"]
    # WHAT quotes the actual trigger fact, cited.
    assert '"Job posting seeks integration engineers' in c.what_text
    assert "[E-089]" in c.what_text
    # WHY names the analyst priority + entry point + live score.
    assert "HIGH priority" in c.why_text
    assert "Hybrid architecture requires integration fabric" in c.why_text
    assert "2.1/5" in c.why_text
    assert "MuleSoft" in c.title


def test_zennify_opportunity_not_emitted_without_evidence() -> None:
    row = dict(_REAL_OPP, e_ids=[], trigger_evidence="none recorded")
    assert insights_from_zennify_opportunities([row]) == []


def test_zennify_opportunity_family_leaf_anchor() -> None:
    row = dict(_REAL_OPP, pillar_refs=[], pillar_alignment="")
    cards = insights_from_zennify_opportunities(
        [row], family_leafs={"salesforce": "P2C4.1.1"},
    )
    # "MuleSoft" offering → salesforce family → its weakest tagged leaf.
    assert cards and cards[0].linked_subcap_id == "P2C4.1.1"


def test_offering_platform_family_mapping() -> None:
    assert offering_platform_family("MuleSoft integration") == "salesforce"
    assert offering_platform_family("Data Cloud + FSC") == "salesforce"
    assert offering_platform_family("Mosaic AI on the lakehouse") == "databricks"
    assert offering_platform_family("nCino Workflow Engine") == "ncino"
    assert offering_platform_family("something unmappable") is None


# ── ladder priority + dedup ──────────────────────────────────────────

def _card(ic_id: str, title: str, what: str, sub: str = "P1C1") -> InsightCardRow:
    return InsightCardRow(
        ic_id=ic_id, severity="medium", title=title, what_text=what,
        linked_subcap_id=sub,
    )


def test_combine_insight_rungs_priority_and_near_dup() -> None:
    profile = [_card("CP-F-001", "Data governance gap",
                     "No Chief Data Officer identified; data governance "
                     "roles being hired across the institution.")]
    section = [_card("F-1-1", "Different finding entirely",
                     "Loan origination workflow is 85% manual with 12-day "
                     "cycle times in underwriting.")]
    recs = [_card("INS-REC-01", "Data governance gap",
                  "No Chief Data Officer identified; data governance "
                  "roles being hired across the institution.")]
    merged = combine_insight_rungs(profile, section, recs)
    ids = [c.ic_id for c in merged]
    # Priority order kept; the rec near-duplicate of the profile card
    # is dropped (higher rung wins).
    assert ids[0] == "CP-F-001"
    assert "F-1-1" in ids
    assert "INS-REC-01" not in ids


def test_combine_insight_rungs_ic_id_collision_keeps_first() -> None:
    a = [_card("X-1", "One", "First card body about digital channels.")]
    b = [_card("X-1", "Two", "Totally different body about compliance.")]
    merged = combine_insight_rungs(a, b)
    assert len(merged) == 1 and merged[0].title == "One"


# ── category-gap rung: demoted, capped, non-template ────────────────

def test_category_gaps_capped_at_four_with_distinct_prose() -> None:
    cats = [
        CategoryScoreRow(category_id=f"P{p}C1", pillar_id=f"P{p}",
                         score=1.2 + p * 0.1, peer_median=3.0)
        for p in (1, 2, 3, 4)
    ] + [
        CategoryScoreRow(category_id="P1C2", pillar_id="P1",
                         score=1.0, peer_median=3.2),
        CategoryScoreRow(category_id="P2C2", pillar_id="P2",
                         score=1.1, peer_median=3.1),
    ]
    cards = insights_from_category_gaps(cats)
    assert len(cards) == 4               # demoted last resort: cap 4
    whys = [c.why_text for c in cards]
    so_whats = [c.so_what_text for c in cards]
    # Rotating variants — no single template family across the set.
    assert len(set(whys)) == len(whys)
    assert len(set(so_whats)) == len(so_whats)
    # Still honest: every card carries the real numbers.
    for c in cards:
        assert "/5" in c.what_text and "peer median" in c.what_text


def test_category_gap_names_fall_back_to_canonical_catalogue() -> None:
    cards = insights_from_category_gaps([
        CategoryScoreRow(category_id="P4C1", pillar_id="P4",
                         score=1.4, peer_median=2.9),
    ])
    # No category_name given → curated display name, never a bare id.
    assert "Data Management & Governance" in cards[0].title


# ── zero-evidence ladder: the basis marker ──────────────────────────

def test_basis_marker_shape() -> None:
    m = basis_marker()
    assert m["kind"] == "basis"
    assert m["note"] == "scores + peer benchmark"
    assert m["e_ids"] == []


def test_attach_evidence_category_rollup_then_basis() -> None:
    from app.scripts.derive_insights import _attach_evidence
    cards = [
        _card("A", "t", "w", sub="P2C1.9.9"),   # leaf: category roll-up
        _card("B", "t", "w", sub="P9C9"),        # nothing anywhere
    ]
    _attach_evidence(cards, {"P2C1.1.1": ["E-1", "E-2"]})
    assert cards[0].linked_e_ids == ["E-1", "E-2"]   # rolled up via P2C1
    assert cards[1].linked_e_ids == []               # stays empty → basis chip


def test_zennify_quote_truncates_verbatim_at_claim_boundary() -> None:
    """2026-07-06 verbatim-quote mandate: the trigger excerpt is quoted as
    written — truncated only at a claim boundary with an ellipsis; a
    boundary-free excerpt is never misquoted (falls through to the
    trigger-evidence citation line)."""
    long_excerpt = (
        "Job posting seeks integration engineers for the core modernization "
        "program at the bank's new technology hub. The posting lists MuleSoft "
        "and event-streaming experience as required and names the 2027 core "
        "conversion as the first assignment for the incoming team, which "
        "is expected to double within eighteen months of the go-live date."
    )
    cards = insights_from_zennify_opportunities(
        [_REAL_OPP], sub_scores={"P4C3": 2.1},
        evidence_excerpts={"E-089": (long_excerpt, "Indeed")},
    )
    what = cards[0].what_text
    m = re.search(r'The research recorded: "([^"]+)"', what)
    assert m is not None
    q = m.group(1)
    assert q.endswith("…")
    core = q.rstrip("… ").strip()
    assert core.endswith(".")           # sentence boundary, never mid-claim
    assert core in long_excerpt          # contiguous verbatim span

    run_on = ("job posting for a role that keeps describing itself without "
              "any sentence boundary or clause seam anywhere in range of "
              "the truncation window so a claim-safe verbatim cut is not "
              "possible and quoting it would slice through the middle of "
              "the single long claim it makes about the hiring plans of "
              "the institution over the coming period of time")
    cards = insights_from_zennify_opportunities(
        [_REAL_OPP], sub_scores={"P4C3": 2.1},
        evidence_excerpts={"E-089": (run_on, "Indeed")},
    )
    what = cards[0].what_text
    assert "The research recorded" not in what      # no misquote shipped
    assert "Trigger evidence: E-089" in what        # honest citation fallback


def test_zennify_fallback_why_is_jargon_free() -> None:
    row = dict(_REAL_OPP, priority="", entry_point="", pillar_alignment="")
    cards = insights_from_zennify_opportunities([row], sub_scores={})
    why = cards[0].why_text
    assert not re.search(r"P[1-4]C\d", why), why    # no raw code in prose
    assert "[E-089, E-066]" in why                  # citations chip-bracketed


# ── counter-evidence ANALYSIS ("But also…" content, 2026-07-06) ──────────────

def test_counter_note_analyzes_content_with_verbatim_quotes() -> None:
    from app.services.parsers.section_analysis import counter_evidence_note
    rows = [
        {"e_id": "E-101", "excerpt": (
            "The commercial lending team already runs automated document "
            "collection through the portal, with e-signature completion at "
            "94% of new originations.")},
        {"e_id": "E-102", "excerpt": (
            "A dedicated data quality council meets biweekly and has "
            "closed 60% of the flagged reconciliation items this year.")},
    ]
    note = counter_evidence_note(rows, "high")
    # analyzes CONTENT: verbatim quotes with E-ID attribution, plus framing
    assert "“The commercial lending team already runs automated document" in note
    assert "[E-101]" in note and "[E-102]" in note
    assert "94%" in note and "60%" in note            # numbers preserved exactly
    assert "not one-sided" in note
    # each quote is a contiguous verbatim span of its source excerpt
    for q in re.findall(r"“([^”]+)”", note):
        core = q[:-1].strip() if q.endswith("…") else q
        assert any(core in re.sub(r"\s+", " ", r["excerpt"]) for r in rows), core
    assert not re.search(r"P[1-4]C\d|\bsub-?cap\b", note, re.I)


def test_counter_note_falls_back_to_honest_chips_when_unquotable() -> None:
    from app.services.parsers.section_analysis import counter_evidence_note
    rows = [{"e_id": "E-301", "excerpt": "TOO SHORT"},
            {"e_id": "E-302", "excerpt": ""}]
    note = counter_evidence_note(rows, "high")
    assert "[E-301, E-302]" in note
    assert "open each item" in note
    assert "“" not in note                     # nothing fake-quoted
    assert counter_evidence_note([], "high") == ""


def test_enrich_card_persists_analyzed_counter_note() -> None:
    from app.scripts.derive_insights import _enrich_card
    from app.services.parsers.section_analysis import SubcapClassifier
    evidence_rows = [
        {"e_id": "E-101", "claim_type": "strength", "tier": 2,
         "subcap_ids": ["P3C2.1"],
         "excerpt": ("The commercial lending team already runs automated "
                     "document collection through the portal, with "
                     "e-signature completion at 94% of new originations.")},
    ]
    out = _enrich_card(
        {"ic_id": "INS-01", "title": "Loan origination is manual",
         "what": "Manual hand-offs dominate.", "why": "Email-tracked.",
         "so_what": "Automate.", "anchor": "P3C2.1", "e_ids": ["E-500"],
         "severity": "high", "source_rec_id": None},
        classifier=SubcapClassifier({"P3C2.1": "Loan Origination"}),
        platform_tags={}, evidence_rows=evidence_rows,
        rec_targets=[], absent_families=[], sibling_eids={},
    )
    entry = next(ic for ic in out["interconnections"]
                 if ic["kind"] == "counter_evidence")
    assert entry["e_ids"] == ["E-101"]
    # the persisted note ANALYZES the counter-evidence, not the old stub
    assert "same-subcap evidence with opposing polarity" not in entry["note"]
    assert "“The commercial lending team already runs" in entry["note"]
    assert "[E-101]" in entry["note"]
