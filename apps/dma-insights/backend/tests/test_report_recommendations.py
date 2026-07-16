"""Report-recommendation extraction — anchor precision, real-shape
regressions + the fragment-rejection gate (2026-07-06 defect family).

Pins the 2026-07-06 production defect (interactive-brokers-grou-0001):
the deployed pack shipped recs fabricated from §9 prose fragments
(') and personalized MCAE journeys (' etc.) because (a) the DOCX
extractor detached the 1x1 banner tables from §9 and (b) the body-text
splitter treated parenthesized cross-references — "(R1)", "(R2)",
"prerequisite for R1 and R2" — as rec-definition anchors. Anchors must
never split inside a parenthetical span; when a recs region only
CROSS-REFERENCES its recs the extractor must fall back to the
whole-document bracket-severity definitions (`R1 [CRITICAL]  Title`)
or return an honest []. These tests pin the fixed behaviour on the
REAL IBKR / Guaranteed Rate / Cornerstone fixtures and lock the gate
against every measured bad-title shape.
"""
from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pytest

from app.schemas.package import ReportSectionRow
from app.services.parsers.assessment_report import parse_assessment_report
from app.services.parsers.report_recommendations import (
    _REC_ID_RE,
    _anchor_strength,
    _looks_like_rec_anchor,
    _normalize_rec_id,
    extract_recommendations_from_report_sections,
    title_reject_reason,
)

# The production offender, verbatim shape (IBKR §9 intro prose): rec ids
# appear ONLY as parenthesized cross-references + a bare list mention.
_IBKR_INTRO = (
    "Five recommendations are presented below, ranked by the Six-Factor "
    "Priority Score. The unified profile, powering Einstein NBA in FSC "
    "(R1) and personalized MCAE journeys (R2) from real-time account "
    "signals. This makes Data Cloud the architectural prerequisite for "
    "R1 and R2 to reach their full score potential. Kafka streams, "
    "surfaced via Data Cloud (R3), provides the behavioral signals that "
    "make MCAE journeys predictive rather than generic."
)


def _secs(*bodies_by_kind: tuple[str, str, str]) -> list[ReportSectionRow]:
    return [
        ReportSectionRow(kind=kind, heading=heading, body=body, ordinal=i)
        for i, (kind, heading, body) in enumerate(bodies_by_kind)
    ]


def _strengths(body: str) -> list[int]:
    return [_anchor_strength(body, m) for m in _REC_ID_RE.finditer(body)]


class TestAnchorStrength:
    def test_parenthesized_cross_references_never_anchor(self) -> None:
        # every id in the production intro is a cross-reference → all 0.
        assert set(_strengths(_IBKR_INTRO)) == {0}

    def test_bare_list_mention_never_anchors(self) -> None:
        assert _strengths("the architectural prerequisite for R1 and R2.") == [0, 0]

    def test_id_inside_open_parenthetical_never_anchors(self) -> None:
        # a separator-shaped id INSIDE an unclosed paren is still a
        # reference — splitting there starts the next rec with ")".
        body = "Deploy segments (as REC-04: the data layer) everywhere."
        assert _strengths(body) == [0]

    def test_separator_definition_anchors(self) -> None:
        body = "REC-001 — Deploy Moody's CreditLens on the commercial book."
        assert _strengths(body) == [2]  # line-start + separator
        assert _looks_like_rec_anchor(body, 0)

    def test_mid_prose_separator_definition_is_weaker_but_anchors(self) -> None:
        body = "As noted, REC-002 — Activate the Analyst Digital Partner."
        m = next(_REC_ID_RE.finditer(body))
        assert _anchor_strength(body, m) == 1

    def test_bracket_severity_definition_is_strongest(self) -> None:
        body = "R1 [CRITICAL]  Financial Services Cloud — Enterprise CRM"
        assert _strengths(body) == [3]

    def test_plain_cross_reference_never_anchors(self) -> None:
        body = "R-01 establishes the FS data model that R-03 requires."
        assert _strengths(body) == [0, 0]


class TestBodyTextExtraction:
    def test_cross_reference_only_region_yields_no_shredded_recs(self) -> None:
        recs = extract_recommendations_from_report_sections(_secs(
            ("recommendations", "9. Recommendations", _IBKR_INTRO),
            ("roadmap", "10. Roadmap", "Phase 1 …"),
        ))
        assert recs == []  # honest empty, never ") and personalized …("

    def test_titles_never_start_or_end_inside_parens(self) -> None:
        # definitions present AND parenthesized cross-refs in the intro:
        # the refs must not become split points.
        body = (
            _IBKR_INTRO + "\n"
            "REC-01: Deploy Financial Services Cloud (FSC) for onboarding.\n"
            "Root cause prose (with a parenthetical) follows.\n"
            "REC-02: Activate MCAE journeys (Journey Builder) at scale.\n"
        )
        recs = extract_recommendations_from_report_sections(_secs(
            ("recommendations", "9. Recommendations", body),
            ("roadmap", "10. Roadmap", ""),
        ))
        assert [r.id for r in recs] == ["REC-01", "REC-02"]
        for r in recs:
            assert not r.title.startswith(")"), r.title
            assert not r.title.endswith("("), r.title

    def test_bracket_severity_fallback_recovers_table_definitions(self) -> None:
        # IBKR shape: the region only cross-references; the real
        # definitions live in flattened DOCX tables appended after the
        # last section. The whole-document fallback must recover them —
        # bracket-severity anchors only.
        recs = extract_recommendations_from_report_sections(_secs(
            ("recommendations", "9. Recommendations", _IBKR_INTRO),
            ("roadmap", "10. Roadmap", "Phase 1 …"),
            ("other", "Appendix C",
             "R1 [CRITICAL]  Financial Services Cloud — Enterprise "
             "Relationship Intelligence\nCapabilities: P2C1 · P2C4\n"
             "R2 [HIGH]  Marketing Cloud (MCAE) — Automated Activation "
             "Journeys\nCapabilities: P2C1 · P2C4"),
        ))
        # Rec IDs are zero-padded canonical form (2026-07-06): R1 → R-01, so
        # a body cross-reference `R1` dedups against the real `R-01` rec.
        assert [r.id for r in recs] == ["R-01", "R-02"]
        assert recs[0].priority == "CRITICAL"
        assert recs[1].priority == "HIGH"
        assert recs[0].title.startswith("Financial Services Cloud")
        assert recs[1].title.startswith("Marketing Cloud (MCAE)")

    def test_summary_table_row_title_drops_tab_columns(self) -> None:
        recs = extract_recommendations_from_report_sections(_secs(
            ("recommendations", "9. Recommendations",
             "R1: Financial Services Cloud\tP2C1 (1.79→2.8)\t0-12 months\n"
             "Some body prose."),
            ("roadmap", "10. Roadmap", ""),
        ))
        assert len(recs) == 1
        assert recs[0].title == "Financial Services Cloud"


_IBKR_DOCX = (
    Path(__file__).resolve().parent
    / "fixtures/dma_packages_batches/batch_15/Interactive Brokers - DMA"
    / "04_reports/IBKR_DMA_Assessment_Report_Full_v1.docx"
)


@pytest.mark.skipif(not _IBKR_DOCX.exists(), reason="IBKR fixture not present")
def test_real_ibkr_report_extracts_five_clean_recs() -> None:
    """End-to-end on the real fixture behind the production screenshots."""
    from app.services.parsers.assessment_report import parse_assessment_report

    res = parse_assessment_report(_IBKR_DOCX)
    rows = [
        ReportSectionRow(kind=s.kind, heading=s.heading, body=s.body, ordinal=i)
        for i, s in enumerate(res.sections)
    ]
    recs = extract_recommendations_from_report_sections(rows)
    # Zero-padded canonical rec IDs (2026-07-06): R1..R5 → R-01..R-05.
    assert [r.id for r in recs] == ["R-01", "R-02", "R-03", "R-04", "R-05"]
    titles = {r.id: r.title for r in recs}
    assert titles["R-01"].startswith("Financial Services Cloud")
    assert titles["R-02"].startswith("Marketing Cloud (MCAE)")
    assert titles["R-05"].startswith("Service Cloud Compliance Workflow")
    for r in recs:
        assert not r.title.startswith(")"), r.title
        assert not r.title.endswith("("), r.title
        assert "\t" not in r.title
        # each rec body names its OWN capabilities (per-rec grounding
        # for the outcomes metric — no uniform worst-gap fill).
        assert "Capabilities:" in (getattr(r, "source_body", "") or "")


class TestDescribeBody:
    """No-sub-block definition body → persisted description (2026-07-06).

    Without this, the IBKR bracket-severity recs persisted description ==
    title, so every card lost its own transitions/timeline and the
    outcomes grid printed the identical run-wide worst gap on all five.
    """

    _IBKR_R2_BODY = (
        "Capabilities: P2C1 · P2C4  |  Timeline: 6 months  |  Validation: "
        "Salesforce/Solution CONFIRMED ABSENT\n"
        "Capability\tCurrent Score\tTarget Score\tImprovement\n"
        "P2C1\t1.79\t3.00\t+1.21\n"
        "P2C4\t2.18\t3.10\t+0.92\n"
        "No MAP confirmed at IBKR. Marketo, HubSpot, Pardot, Eloqua, and "
        "Salesforce MCAE all confirmed absent from tech stack via proxy "
        "search."
    )

    def test_score_table_rows_become_readable_transitions(self) -> None:
        from app.services.parsers.report_recommendations import _describe_body

        out = _describe_body(self._IBKR_R2_BODY)
        assert "P2C1 1.79 → 3.00" in out
        assert "P2C4 2.18 → 3.10" in out
        assert "\t" not in out                      # no raw table cells
        assert "Current Score" not in out           # header dropped
        assert "No MAP confirmed at IBKR." in out   # prose verbatim

    def test_rec_row_gains_gap_description_and_per_rec_metric(self) -> None:
        from app.services.parsers.rec_files import mine_description_enrichment
        from app.services.parsers.report_recommendations import (
            _build_recommendation_row,
        )

        row = _build_recommendation_row(
            "R2", "Marketing Cloud (MCAE) — Automated Activation Journeys",
            self._IBKR_R2_BODY,
        )
        gap = (row.root_cause or {}).get("gap_description") or ""
        assert "P2C1 1.79 → 3.00" in gap
        e = mine_description_enrichment(
            title=row.title, description=gap, effort_band=None, rec_id="R2",
        )
        # the rec's OWN transition + its OWN timeline — never the
        # run-wide "P2C1 score 1.79 → 4.0 / 12-18 months" uniform fill.
        assert e["outcomes"]["metric"] == "P2C1 score 1.79 → 3.0"
        assert e["outcomes"]["time"] == "6 months"

    def test_sub_block_bodies_keep_canonical_mapping(self) -> None:
        from app.services.parsers.report_recommendations import (
            _build_recommendation_row,
        )

        row = _build_recommendation_row(
            "REC-01", "Title",
            "[ROOT CAUSE]\nThe gap narrative.\n[SOLUTION]\nThe fix.",
        )
        assert row.root_cause == {"gap_description": "The gap narrative."}
        assert row.solution == {"description": "The fix."}


_BATCHES = Path(__file__).resolve().parent / "fixtures" / "dma_packages_batches"
IBKR_DOCX = (
    _BATCHES / "batch_15" / "Interactive Brokers - DMA" / "04_reports"
    / "IBKR_DMA_Assessment_Report_Full_v1.docx"
)
GRATE_DOCX = (
    _BATCHES / "batch_06" / "Guaranteed Rate - DMA" / "DMA_Rate_GRATE_20260416"
    / "04_reports" / "DMA_Assessment_Report_Rate_COMPLETE.docx"
)
CCB_DOCX = (
    _BATCHES / "batch_06" / "Cornerstone Capital Bank - DMA" / "DMA_CCB_20260504"
    / "04_reports" / "CCB_DMA_Assessment_Report.docx"
)


def _rows_from_docx(path: Path) -> list[ReportSectionRow]:
    res = parse_assessment_report(path)
    return [
        ReportSectionRow(
            kind=s.kind, heading=s.heading, body=s.body, ordinal=s.ordinal,
            subcap_ids_mentioned=s.subcap_ids_mentioned,
            e_ids_mentioned=s.e_ids_mentioned,
        )
        for s in res.sections
    ]


def _sections(*pairs: tuple[str, str, str]) -> list[ReportSectionRow]:
    """(kind, heading, body) triples → ordinal-numbered section rows."""
    return [
        ReportSectionRow(kind=k, heading=h, body=b, ordinal=i)
        for i, (k, h, b) in enumerate(pairs)
    ]


# ── The real IBKR fixture: 5 banner recs, zero fabrications ────────────


class TestIBKRRealRecs:
    @pytest.fixture(scope="class")
    def extraction(self) -> tuple[list, list[str]]:
        warnings: list[str] = []
        recs = extract_recommendations_from_report_sections(
            _rows_from_docx(IBKR_DOCX), warnings)
        return recs, warnings

    def test_five_recs_with_normalized_ids(self, extraction) -> None:
        recs, _w = extraction
        assert [r.id for r in recs] == ["R-01", "R-02", "R-03", "R-04", "R-05"]

    def test_real_titles_extracted(self, extraction) -> None:
        recs, _w = extraction
        assert [r.title for r in recs] == [
            "Financial Services Cloud",
            "Marketing Cloud (MCAE) — Automated Activation Journeys "
            "for 1M+ Annual New Accounts",
            "Salesforce Data Cloud on AWS — Governed Unified Client "
            "Profile from Kafka Event Streams",
            "Einstein AI + Agentforce — Enterprise AI Governance for "
            "IBKR's 5-Tool AI Flywheel",
            "Service Cloud Compliance Workflow",
        ]

    def test_severities_mapped_to_priority(self, extraction) -> None:
        recs, _w = extraction
        assert [r.priority for r in recs] == [
            "CRITICAL", "CRITICAL", "HIGH", "HIGH", "HIGH",
        ]

    def test_titles_all_pass_the_gate(self, extraction) -> None:
        recs, warnings = extraction
        for r in recs:
            assert title_reject_reason(r.title) is None, r.title
        assert not [w for w in warnings if w.startswith("rec_title_rejected")]

    def test_titles_within_display_budget(self, extraction) -> None:
        recs, _w = extraction
        assert all(len(r.title) <= 90 for r in recs)

    def test_no_fabricated_fragment_recs(self, extraction) -> None:
        # The pre-fix output fabricated exactly these three titles from
        # mid-sentence cross-references. None may ever ship again.
        recs, _w = extraction
        titles = {r.title for r in recs}
        assert ") and personalized MCAE journeys (" not in titles
        for t in titles:
            assert not t.startswith((")", "(", ".", ","))
            assert t.count("(") == t.count(")")

    def test_each_rec_carries_its_own_capability_targets(self, extraction) -> None:
        # gap_description must carry the rec's OWN score-impact grid —
        # that is what lets derive_recommendations ground each rec's
        # metric in its own subcaps instead of one shared entity gap.
        recs, _w = extraction
        by_id = {r.id: (r.root_cause or {}).get("gap_description", "") for r in recs}
        assert "P2C1" in by_id["R-01"] and "1.79" in by_id["R-01"]
        assert "P4C1" in by_id["R-03"] and "2.10" in by_id["R-03"]
        assert "P3C3" in by_id["R-05"] and "2.15" in by_id["R-05"]

    def test_own_timeline_and_severity_survive_into_gap_description(
        self, extraction,
    ) -> None:
        recs, _w = extraction
        gap1 = (recs[0].root_cause or {}).get("gap_description", "")
        assert "Timeline: 12 months" in gap1
        assert "Severity: [CRITICAL]" in gap1
        gap2 = (recs[1].root_cause or {}).get("gap_description", "")
        assert "Timeline: 6 months" in gap2

    def test_sub_blocks_mapped_from_ibkr_subheadings(self, extraction) -> None:
        recs, _w = extraction
        r1 = recs[0]
        assert (r1.solution or {}).get("description"), "9.N.2 → solution"
        assert r1.expected_outcomes, "9.N.3 → expected_outcomes"
        assert r1.model_dump().get("risk_of_inaction"), "9.N.4 → risk"


# ── Tab-row shapes: Guaranteed Rate + Cornerstone (2026-07-06 follow-up) ──
# The document-order table flattening emits §9 rec tables as tab-joined
# rows. Guaranteed Rate stacks `REC-01\nHIGH` in the id cell (severity-led
# cells on the next line, column order id/severity/title); Cornerstone
# ships one line per rec (column order id/TITLE/severity+qualifier/[ZENNIFY]).
# Both parsed 0 recs before the tab-row path (the gate correctly rejected
# the pre-fix fragments, but the real rows went unparsed).


class TestGuaranteedRateTabRows:
    @pytest.fixture(scope="class")
    def extraction(self) -> tuple[list, list[str]]:
        warnings: list[str] = []
        recs = extract_recommendations_from_report_sections(
            _rows_from_docx(GRATE_DOCX), warnings)
        return recs, warnings

    def test_six_real_recs(self, extraction) -> None:
        recs, warnings = extraction
        assert [r.id for r in recs] == [f"REC-0{n}" for n in range(1, 7)]
        assert not [w for w in warnings if w.startswith("rec_title_rejected")]

    def test_real_titles_extracted(self, extraction) -> None:
        recs, _w = extraction
        assert [r.title for r in recs] == [
            "Salesforce Data Cloud + Chief Data Officer Advisory",
            "AI Model Governance + Einstein Trust Layer",
            "Salesforce Financial Services Cloud for LO Productivity",
            "MuleSoft Embedded Finance API Architecture",
            "Digital Strategy Documentation + Board Governance",
            "Compliance Automation + ECOA Adverse Action AI",
        ]

    def test_severities_mapped(self, extraction) -> None:
        recs, _w = extraction
        assert [r.priority for r in recs] == [
            "HIGH", "HIGH", "HIGH", "MEDIUM", "MEDIUM", "MEDIUM",
        ]

    def test_titles_pass_the_gate(self, extraction) -> None:
        recs, _w = extraction
        for r in recs:
            assert title_reject_reason(r.title) is None, r.title

    def test_label_rows_fold_into_sub_blocks(self, extraction) -> None:
        # `ROOT CAUSE\t…` / `ZENNIFY SOLUTION\t…` / `EXPECTED OUTCOMES\t…`
        # label rows must land on the canonical schema fields.
        recs, _w = extraction
        r1 = recs[0]
        gap = (r1.root_cause or {}).get("gap_description", "")
        assert "fragmented, application-native master data" in gap
        assert (r1.solution or {}).get("description")
        assert r1.expected_outcomes

    def test_meta_cells_fold_into_gap_description(self, extraction) -> None:
        # The rec's own severity + Category cell must survive so the
        # derive passes can ground per-rec outcomes.
        recs, _w = extraction
        gap = (recs[0].root_cause or {}).get("gap_description", "")
        assert "Severity: [HIGH]" in gap
        assert "Category: P4C1" in gap


class TestCornerstoneTabRows:
    @pytest.fixture(scope="class")
    def extraction(self) -> tuple[list, list[str]]:
        warnings: list[str] = []
        recs = extract_recommendations_from_report_sections(
            _rows_from_docx(CCB_DOCX), warnings)
        return recs, warnings

    def test_eight_real_recs(self, extraction) -> None:
        recs, warnings = extraction
        assert [r.id for r in recs] == [f"REC-00{n}" for n in range(1, 9)]
        assert not [w for w in warnings if w.startswith("rec_title_rejected")]

    def test_real_titles_extracted(self, extraction) -> None:
        recs, _w = extraction
        titles = [r.title for r in recs]
        assert titles[:3] == [
            "MuleSoft: Deploy the Integration Orchestration Layer Before "
            "the LOS Window Closes",
            "AgentForce: Govern the AI Already Deployed and Scale It "
            "Across 700K Borrowers",
            "Salesforce Data Cloud: Accelerate the Build and Add the "
            "Peoples Bank + Surefire Feeds",
        ]
        assert titles[3].startswith("nCino Analytics: Activate the Modules")
        assert titles[4].startswith("Einstein Analytics / CRM Analytics:")
        assert titles[5].startswith("Experience Cloud: Build the JV Partner")
        assert titles[6].startswith("Salesforce Shield: Establish Data-Layer")
        assert titles[7].startswith("Salesforce Financial Services Cloud:")
        assert all(len(t) <= 90 for t in titles)
        for t in titles:
            assert title_reject_reason(t) is None, t

    def test_severity_qualifiers_parsed(self, extraction) -> None:
        # `CRITICAL — IMMEDIATE` → CRITICAL; `IMMEDIATE — FASTEST WIN` →
        # IMMEDIATE; `MEDIUM — When CISO Confirmed` → MEDIUM.
        recs, _w = extraction
        assert [r.priority for r in recs] == [
            "CRITICAL", "CRITICAL", "CRITICAL", "IMMEDIATE",
            "HIGH", "HIGH", "MEDIUM", "MEDIUM",
        ]

    def test_qualified_bracket_sub_blocks_slice(self, extraction) -> None:
        # `[ROOT CAUSE — SITUATION]` / `[ROOT CAUSE — COMPLICATION]`
        # (qualified brackets) concat into gap_description;
        # `[SOLUTION — ANSWER]` lands on solution.
        recs, _w = extraction
        r1 = recs[0]
        gap = (r1.root_cause or {}).get("gap_description", "")
        assert "three-layer data architecture" in gap    # SITUATION
        assert "three consequences compound" in gap      # COMPLICATION
        assert "MuleSoft API-led connectivity" in (
            (r1.solution or {}).get("description", ""))  # ANSWER

    def test_zennify_tag_and_qualifier_folded_not_titled(self, extraction) -> None:
        recs, _w = extraction
        for r in recs:
            assert "[ZENNIFY]" not in r.title
        gap1 = (recs[0].root_cause or {}).get("gap_description", "")
        assert "Severity: [CRITICAL]" in gap1
        assert "Priority qualifier: IMMEDIATE" in gap1

    def test_own_score_targets_survive_for_derive_grounding(self, extraction) -> None:
        # `Current Score: P4C1=2.76 … Expected After Deployment: P4C1:
        # 2.76 → 3.25` rows must survive into the rec body so PASS-4
        # grounds each rec's metric in ITS OWN targets.
        recs, _w = extraction
        r1 = recs[0]
        blob = "\n".join([
            (r1.root_cause or {}).get("gap_description", ""),
            (r1.solution or {}).get("description", ""),
            str(r1.model_dump().get("source_body") or ""),
        ])
        assert "2.76 → 3.25" in blob


# ── Fragment-rejection gate: the measured bad-title shapes ─────────────


class TestFragmentGate:
    # The 9 known-bad title shapes from the 2026-07-06 pack diagnosis
    # (punctuation-start, unbalanced parens, lowercase mid-sentence
    # fragments, bare '.', '(untitled)', connector words).
    KNOWN_BAD: ClassVar[list[str]] = [
        ") and personalized MCAE journeys (",
        ") from real-time account signals. This makes Data Cloud the "
        "architectural prerequisite for R1 and R2 to reach full potential",
        "), provides the behavioral signals that make MCAE journeys "
        "predictive rather than generic.",
        "through",
        "launching without Data Cloud foundation yields partial outcomes "
        "and re-work risk.",
        ".",
        "(untitled)",
        "Deploy FSC (Financial Services",
        "— Phase 1: Foundation",
    ]

    @pytest.mark.parametrize("title", KNOWN_BAD)
    def test_known_bad_titles_rejected(self, title: str) -> None:
        assert title_reject_reason(title) is not None, title

    GOOD: ClassVar[list[str]] = [
        "Financial Services Cloud",
        "Financial Services Cloud Rollout",
        "Marketing Cloud (MCAE) — Automated Activation Journeys for "
        "1M+ Annual New Accounts",
        "Marketing Cloud (MCAE) Activation",
        "Deploy nCino loan origination workflows",
        "nCino Workflow Engine rollout",  # brand-cased lowercase lead
        "nCino Loan Origination Platform",
        "Strengthen P2C1: Digital Marketing & Acquisition",
        "Service Cloud Compliance Workflow",
    ]

    @pytest.mark.parametrize("title", GOOD)
    def test_real_titles_pass(self, title: str) -> None:
        assert title_reject_reason(title) is None, title

    def test_reason_codes_are_stable(self) -> None:
        assert title_reject_reason("") == "empty"
        assert title_reject_reason(".") == "too_short"
        assert title_reject_reason("FSC") == "too_short"          # <12 chars
        # length check precedes the punctuation check, so use a long clip
        assert title_reject_reason(") and personalized MCAE journeys (") \
            == "punctuation_start"
        assert title_reject_reason(") and personalized journeys") \
            == "punctuation_start"
        assert title_reject_reason(
            "launching without Data Cloud foundation yields partial outcomes"
        ) == "lowercase_start"
        assert title_reject_reason("through the platform to reach") \
            == "lowercase_start"
        assert title_reject_reason("Deploy FSC (Financial Services") \
            == "unbalanced_parens"


# ── Fabrication paths are dead ─────────────────────────────────────────


class TestFabricationKilled:
    def test_cross_reference_only_prose_yields_no_recs(self) -> None:
        # The exact IBKR failure shape pre-fix: the recs region carries
        # ONLY mid-sentence (R1)/(R2) cross-references — no anchors.
        secs = _sections(
            ("recommendations", "9. Recommendations",
             "MCAE delivers automated Day-1 journeys (R1) and personalized "
             "MCAE journeys (R2) from real-time account signals. This makes "
             "Data Cloud the architectural prerequisite for R1 and R2 to "
             "reach full potential."),
            ("roadmap", "10. Roadmap", "Phase 1 covers the foundation."),
        )
        warnings: list[str] = []
        assert extract_recommendations_from_report_sections(secs, warnings) == []

    def test_rec_range_prose_never_yields_a_rec_titled_through(self) -> None:
        # AMH reproduction: 'REC-01 through REC-03' range prose used to
        # split into a rec titled literally 'through'.
        secs = _sections(
            ("recommendations", "Recommendations",
             "REC-01 through REC-03 share a single data foundation and "
             "should be sequenced within the first two phases."),
            ("roadmap", "Roadmap", "..."),
        )
        recs = extract_recommendations_from_report_sections(secs)
        assert all(r.title != "through" for r in recs)
        assert recs == []

    def test_unpadded_cross_reference_dedups_against_real_rec(self) -> None:
        # ANB reproduction: 'REC-1' escaping dedup against 'REC-01' shipped
        # a lowercase fragment title alongside the real rec.
        secs = _sections(
            ("recommendations", "Recommendations",
             "REC-01 — Deploy Financial Services Cloud for relationship "
             "onboarding across the retail segment.\n"
             "REC-1 — launching without Data Cloud foundation yields "
             "partial outcomes and re-work risk."),
            ("roadmap", "Roadmap", "..."),
        )
        recs = extract_recommendations_from_report_sections(secs)
        assert [r.id for r in recs] == ["REC-01"]
        assert recs[0].title.startswith("Deploy Financial Services Cloud")

    def test_rejected_candidates_are_counted_never_placeholdered(self) -> None:
        secs = _sections(
            ("recommendations", "Recommendations", ""),
            ("other", "REC-01: through", "Body prose for the fragment."),
            ("roadmap", "Roadmap", "..."),
        )
        warnings: list[str] = []
        recs = extract_recommendations_from_report_sections(secs, warnings)
        assert recs == []
        assert warnings == ["rec_title_rejected:REC-01:too_short"]

    def test_untitled_placeholder_never_ships(self) -> None:
        secs = _rows_from_docx(IBKR_DOCX)
        recs = extract_recommendations_from_report_sections(secs)
        for r in recs:
            assert "(untitled)" not in r.title
            assert "no title" not in r.title


# ── Rec-id normalization ───────────────────────────────────────────────


class TestNormalizeRecId:
    @pytest.mark.parametrize(("raw", "expected"), [
        ("REC-1", "REC-01"),      # zero-pad 1-digit (ANB dedup fix)
        ("REC-01", "REC-01"),
        ("REC-001", "REC-001"),   # keep the WSFS 3-digit canonical width
        ("R1", "R-01"),           # IBKR banner form
        ("R-7", "R-07"),
        ("RECOMMENDATION 2", "REC-02"),
        ("RECOMMENDATION 3", "REC-03"),
    ])
    def test_forms(self, raw: str, expected: str) -> None:
        assert _normalize_rec_id(raw) == expected


# ── Anchored body-text path still works (WSFS-style separators) ────────


class TestBodyTextPathStillAnchors:
    def test_separator_anchored_ids_extract(self) -> None:
        secs = _sections(
            ("recommendations", "Recommendations",
             "REC-001 — Deploy Financial Services Cloud to unify the "
             "relationship data model.\n"
             "REC-002 — Modernize digital onboarding with automated "
             "KYC decisioning."),
            ("roadmap", "Roadmap", "..."),
        )
        recs = extract_recommendations_from_report_sections(secs)
        assert [r.id for r in recs] == ["REC-001", "REC-002"]
        assert recs[0].title.startswith("Deploy Financial Services Cloud")

    def test_severity_banner_without_separator_extracts(self) -> None:
        # Tolerance: severity tag present, no dash between tag and title.
        secs = _sections(
            ("recommendations", "Recommendations",
             "R1 [CRITICAL]  Financial Services Cloud — Enterprise "
             "Relationship Intelligence\n"
             "Capabilities: P2C1 · P2C4  |  Timeline: 12 months"),
            ("roadmap", "Roadmap", "..."),
        )
        recs = extract_recommendations_from_report_sections(secs)
        assert [r.id for r in recs] == ["R-01"]
        assert recs[0].priority == "CRITICAL"
        assert recs[0].title == (
            "Financial Services Cloud — Enterprise Relationship Intelligence"
        )
