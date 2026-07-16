"""Tests for the assessment-report DOCX section parser (pure)."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.parsers.assessment_report import (
    EXPECTED_KINDS,
    classify_heading,
    extract_paragraphs_from_docx,
    find_assessment_reports,
    parse_assessment_report,
    parse_report_paragraphs,
)


class TestClassifyHeading:
    @pytest.mark.parametrize(
        ("heading", "expected"),
        [
            ("Executive Summary", "executive_summary_scqa"),
            ("SCQA Overview", "executive_summary_scqa"),
            ("Trend Analysis", "trend_analysis"),
            ("Trends", "trend_analysis"),
            ("Issue Register", "issue_register"),
            ("Pillar 1 — Strategy", "pillar_deep_dive_p1"),
            ("PILLAR 4: Data & AI", "pillar_deep_dive_p4"),
            ("Benchmark Comparison", "benchmark_comparison"),
            ("Gap Prioritization", "gap_prioritization"),
            ("Gap Prioritisation", "gap_prioritization"),  # UK spelling
            ("Recommendations", "recommendations"),
            ("Roadmap", "roadmap"),
            ("Data Gaps", "data_gaps"),
            ("Evidence Registry", "evidence_registry"),
            ("Some Random Section", "other"),
        ],
    )
    def test_table(self, heading: str, expected: str) -> None:
        assert classify_heading(heading) == expected


class TestParseReportParagraphs:
    def test_empty_doc(self) -> None:
        res = parse_report_paragraphs([])
        assert res.sections == []

    def test_no_headings_emits_unknown_section(self) -> None:
        res = parse_report_paragraphs([
            ("Normal", "body line 1"),
            ("Normal", "body line 2"),
        ])
        assert len(res.sections) == 1
        assert res.sections[0].kind == "unknown"
        assert "body line 1" in res.sections[0].body
        assert "body line 2" in res.sections[0].body

    def test_two_headings(self) -> None:
        res = parse_report_paragraphs([
            ("Heading 1", "Executive Summary"),
            ("Normal", "SCQA intro"),
            ("Normal", "client snapshot"),
            ("Heading 1", "Recommendations"),
            ("Normal", "adopt nCino"),
        ])
        assert [(s.kind, s.heading) for s in res.sections] == [
            ("executive_summary_scqa", "Executive Summary"),
            ("recommendations", "Recommendations"),
        ]
        assert "SCQA intro" in res.sections[0].body
        assert "adopt nCino" in res.sections[1].body

    def test_unknown_heading_emits_warning(self) -> None:
        res = parse_report_paragraphs([
            ("Heading 1", "Random Side Quest"),
            ("Normal", "stuff"),
        ])
        assert res.sections[0].kind == "other"
        assert any(w["kind"] == "unknown_heading" for w in res.warnings)

    def test_ordinal_assignment(self) -> None:
        res = parse_report_paragraphs([
            ("Heading 1", "Executive Summary"),
            ("Normal", "a"),
            ("Heading 1", "Trends"),
            ("Normal", "b"),
            ("Heading 1", "Recommendations"),
            ("Normal", "c"),
        ])
        ordinals = [s.ordinal for s in res.sections]
        assert ordinals == [1, 2, 3]

    def test_lowercase_heading_style_is_detected(self) -> None:
        # python-docx sometimes returns lowercase 'heading 1'
        res = parse_report_paragraphs([
            ("heading 2", "Pillar 3 — Process"),
            ("Normal", "more text"),
        ])
        assert res.sections[0].kind == "pillar_deep_dive_p3"


class TestHeaderDriftAcrossTemplates:
    """Real-world DMA reports use different phrasings per analyst/vendor.
    The classifier must handle the canonical drift list called out in
    the docstring."""

    @pytest.mark.parametrize(
        ("heading", "expected"),
        [
            ("Strategic Posture & Governance", "pillar_deep_dive_p1"),
            ("Engagement Pillar", "pillar_deep_dive_p2"),
            ("Operations Pillar", "pillar_deep_dive_p3"),
            ("Data & AI", "pillar_deep_dive_p4"),
            ("Customer Experience and Engagement", "pillar_deep_dive_p2"),
            ("Process Automation", "pillar_deep_dive_p3"),
            ("AI Enablement", "pillar_deep_dive_p4"),
            ("1. Executive Summary", "executive_summary_scqa"),
            ("2.3 Trend Analysis", "trend_analysis"),
            ("A. Recommendations", "recommendations"),
            ("Section 4: Issue Register", "issue_register"),
            ("Peer Comparison", "benchmark_comparison"),
            ("Prioritized Gaps", "gap_prioritization"),
            ("Transformation Roadmap", "roadmap"),
            ("Thin Evidence", "data_gaps"),
            ("Evidence Index", "evidence_registry"),
        ],
    )
    def test_drift_variants(self, heading: str, expected: str) -> None:
        assert classify_heading(heading) == expected


class TestSubcapAndEvidenceExtraction:
    def test_paragraph_with_subcap_and_e_id_mentions(self) -> None:
        res = parse_report_paragraphs([
            ("Heading 1", "Pillar 1 — Strategy"),
            ("Normal", "Discussion of P1C1.1.1 and P1C2.3.2 against peer."),
            ("Normal", "See E-101 and E-202 for grounding."),
        ])
        assert len(res.sections) == 1
        s = res.sections[0]
        assert s.kind == "pillar_deep_dive_p1"
        assert "P1C1.1.1" in s.subcap_ids_mentioned
        assert "P1C2.3.2" in s.subcap_ids_mentioned
        assert "E-101" in s.e_ids_mentioned
        assert "E-202" in s.e_ids_mentioned


class TestStateTransitions:
    """The state_kind contract is the canonical branch label."""

    def test_no_docx_found_state(self, tmp_path: Path) -> None:
        res = parse_assessment_report(tmp_path / "missing.docx")
        assert res.state_kind == "no_docx_found"
        assert res.sections == []

    def test_empty_state(self) -> None:
        from app.services.parsers.assessment_report import ReportParseResult
        empty = ReportParseResult()
        assert empty.state_kind == "no_docx_found"

    def test_full_coverage_state(self) -> None:
        # Walk every expected kind exactly once + a known heading line.
        pairs = []
        for k in EXPECTED_KINDS:
            head = {
                "executive_summary_scqa": "Executive Summary",
                "trend_analysis": "Trend Analysis",
                "issue_register": "Issue Register",
                "pillar_deep_dive_p1": "Pillar 1",
                "pillar_deep_dive_p2": "Pillar 2",
                "pillar_deep_dive_p3": "Pillar 3",
                "pillar_deep_dive_p4": "Pillar 4",
                "benchmark_comparison": "Benchmark Comparison",
                "gap_prioritization": "Gap Prioritization",
                "recommendations": "Recommendations",
                "roadmap": "Roadmap",
                "data_gaps": "Data Gaps",
            }[k]
            pairs.append(("Heading 1", head))
            pairs.append(("Normal", f"body for {k}"))
        res = parse_report_paragraphs(pairs)
        assert res.state_kind == "full_coverage"
        assert res.coverage_ratio == 1.0


# Real-fixture round-trip tests — verify the parser handles AlmaBank +
# WSFS DOCX files we have on disk. These tests are skipped if the
# fixtures are absent (e.g. fresh checkout without /tmp/dma-fixtures).

# Committed real-sample DOCX (was /tmp/dma-fixtures/* — dev-only paths that
# made these tests permanently SKIP in CI). The packages ship in-repo under
# tests/fixtures/dma_packages_real_samples/, so the parser is exercised for
# real on every run.
_REAL_SAMPLES = Path(__file__).resolve().parent / "fixtures" / "dma_packages_real_samples"
ALMA_DOCX = (
    _REAL_SAMPLES / "Alma_Bank__DMA" / "04_reports"
    / "AlmaBank_DMA_Assessment_Report_FINAL.docx"
)
WSFS_DOCX = (
    _REAL_SAMPLES / "WSFS_Bank__DMA" / "04_reports"
    / "WSFS_DMA_Assessment_Report.docx"
)


class TestAlmaBankFixture:
    def test_all_canonical_sections_recovered(self) -> None:
        res = parse_assessment_report(ALMA_DOCX)
        assert res.coverage_ratio >= 0.80, f"coverage {res.coverage_ratio}"
        assert res.state_kind in ("full_coverage", "llm_fallback_used")
        kinds = {s.kind for s in res.sections}
        # All 4 pillar deep-dives present + SCQA + recommendations + roadmap.
        for required in (
            "executive_summary_scqa",
            "pillar_deep_dive_p1", "pillar_deep_dive_p2",
            "pillar_deep_dive_p3", "pillar_deep_dive_p4",
            "recommendations", "roadmap",
        ):
            assert required in kinds, f"missing {required}: got {kinds}"

    def test_pillar_dive_p1_contains_strategy_substring(self) -> None:
        res = parse_assessment_report(ALMA_DOCX)
        p1 = [s for s in res.sections if s.kind == "pillar_deep_dive_p1"]
        assert p1, "expected at least one P1 deep-dive section"


class TestWSFSFixture:
    def test_coverage_ratio_meets_threshold(self) -> None:
        res = parse_assessment_report(WSFS_DOCX)
        assert res.coverage_ratio >= 0.80


# IBKR-shape fixture: §9 recommendation banners ("R1 [CRITICAL]
# Financial Services Cloud — …") live in 1x1 DOCX tables between the
# section's paragraphs.
IBKR_DOCX = (
    Path(__file__).resolve().parent / "fixtures" / "dma_packages_batches"
    / "batch_15" / "Interactive Brokers - DMA" / "04_reports"
    / "IBKR_DMA_Assessment_Report_Full_v1.docx"
)


class TestIBKRTableAttachment:
    """Document-order regression (2026-07-06 defect family): tables must
    stay attached to the section whose heading precedes them. The prior
    extractor appended ALL tables after ALL paragraphs, detaching the §9
    rec banners and letting report_recommendations fabricate fragment
    recs from the leftover prose."""

    def test_tables_interleaved_in_document_order(self) -> None:
        texts = [t for _style, t in extract_paragraphs_from_docx(IBKR_DOCX)]
        i_sec9 = next(
            i for i, t in enumerate(texts) if t.startswith("9. Recommendations"))
        i_banner = next(
            i for i, t in enumerate(texts) if t.startswith("R1 [CRITICAL]"))
        i_sec10 = next(
            i for i, t in enumerate(texts)
            if t.startswith("10. Transformation Roadmap"))
        assert i_sec9 < i_banner < i_sec10, (
            "R1 banner table must sit inside the §9 region, "
            f"got sec9={i_sec9} banner={i_banner} sec10={i_sec10}"
        )

    def test_recommendations_section_contains_banner_text(self) -> None:
        res = parse_assessment_report(IBKR_DOCX)
        rec_secs = [s for s in res.sections if s.kind == "recommendations"]
        assert rec_secs, "IBKR §9 must classify as a recommendations section"
        body = "\n".join(s.body for s in rec_secs)
        for token in ("R1", "[CRITICAL]", "Financial Services Cloud"):
            assert token in body, f"{token!r} missing from §9 section text"

    def test_all_five_banners_land_in_recs_region(self) -> None:
        # R2..R5 banners sit inside the per-rec `9.N.4` sub-sections —
        # every one must appear BEFORE the §10 roadmap section opens.
        res = parse_assessment_report(IBKR_DOCX)
        ordered = sorted(res.sections, key=lambda s: s.ordinal)
        roadmap_ord = next(
            s.ordinal for s in ordered if s.kind == "roadmap")
        for n, sev in (("R1", "CRITICAL"), ("R2", "CRITICAL"), ("R3", "HIGH"),
                       ("R4", "HIGH"), ("R5", "HIGH")):
            holder = [
                s for s in ordered
                if f"{n} [{sev}]" in s.body and s.ordinal < roadmap_ord
            ]
            assert holder, f"banner {n} [{sev}] not attached before §10"


class TestFindAssessmentReports:
    def test_skip_client_profile_research_report(self, tmp_path: Path) -> None:
        # Create a fake structure
        rpts = tmp_path / "04_reports"
        rpts.mkdir()
        (rpts / "WSFS_Client_Profile_Research_Report.docx").touch()
        (rpts / "WSFS_DMA_Assessment_Report.docx").touch()
        found = find_assessment_reports(tmp_path)
        assert len(found) == 1
        assert "Assessment_Report" in found[0].name
        assert "Client_Profile" not in found[0].name
