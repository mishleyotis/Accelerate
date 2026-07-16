"""Tests for the Client Profile DOCX parser.

State-transition coverage matrix (per scope §2):

  - no_docx_found    → test_missing_path_returns_no_docx
  - partial_coverage → test_partial_when_leadership_missing
  - full_coverage    → test_full_coverage_alma_shape
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.parsers.client_profile import (
    parse_client_profile_doc,
    parse_client_profile_path,
)


@dataclass
class _Style:
    name: str


@dataclass
class _Para:
    text: str
    style: _Style


@dataclass
class _Doc:
    paragraphs: list[_Para]


def _doc(*paras: tuple[str, str]) -> _Doc:
    return _Doc(paragraphs=[_Para(text=t, style=_Style(name=s)) for s, t in paras])


class TestParseClientProfile:
    def test_full_coverage_alma_shape(self) -> None:
        doc = _doc(
            ("Heading 1", "1. Executive Summary"),
            ("Heading 2", "1.2 Top Findings"),
            ("Normal",
             "Alma Bank's CEO has been in role since 2015 (P1C1.1.1) and "
             "drives a refreshed digital strategy in partnership with "
             "Cetera. Source: PRNewswire press release p. 3."),
            ("Normal",
             "Branch network spans 14 locations across NY-NJ. Loan growth "
             "+8% YoY (P3C1.2.1). Source: 10-K filing page 12."),
            ("Heading 2", "1.3 Critical Gaps"),
            ("Normal",
             "Absence of formal data governance committee constrains "
             "P4C2.1.1 maturity. Source: Discovery interview."),
            ("Heading 1", "2. Entity Profile"),
            ("Heading 2", "2.1 Corporate Identity"),
            ("Normal",
             "Alma Bank was founded in 2007 to serve the Greek-American "
             "community in Astoria, Queens."),
            ("Heading 2", "2.2 Scale Metrics"),
            ("Normal", "AUM: $1.5B; Branches: 14; Employees: 170."),
            ("Heading 1", "4. Strategic Intelligence"),
            ("Heading 2", "4.3 Leadership Overview"),
            ("Normal", "Michael Psyllos — President & CEO"),
            ("Normal", "Kimon Skarlatos — EVP, Chief Lending Officer"),
            ("Normal", "John Doe — CFO"),
            ("Normal", "Jane Roe — Chief Risk Officer"),
            ("Normal", "Carl Marx — Chief Operating Officer"),
        )
        res = parse_client_profile_doc(doc)
        assert res.state_kind == "full_coverage"
        assert len(res.focus_areas) >= 3
        # Verbatim quote preserved
        assert any("Cetera" in fa.verbatim_quote for fa in res.focus_areas)
        # Subcap IDs extracted
        all_subcaps = {s for fa in res.focus_areas for s in fa.involved_subcap_ids}
        assert "P1C1.1.1" in all_subcaps
        # Page numbers extracted
        assert any(fa.page_number == 3 for fa in res.focus_areas)
        # 5 leaders captured (Alma fixture has 5-7 in real data)
        assert len(res.leadership) >= 5
        leader_names = {e.name for e in res.leadership}
        assert "Michael Psyllos" in leader_names
        # Financials parsed
        assert res.financial_highlights
        assert "lines" in res.financial_highlights
        # Firmographics narrative
        assert "Astoria" in res.firmographics_narrative_md

    def test_partial_when_leadership_missing(self) -> None:
        doc = _doc(
            ("Heading 2", "1.2 Top Findings"),
            ("Normal",
             "First finding — strong digital posture overall. Source: 10-K."),
            ("Normal",
             "Second finding — gaps in data governance. Source: interview."),
            ("Heading 2", "2.1 Corporate Identity"),
            ("Normal", "Bank with 50 branches."),
        )
        res = parse_client_profile_doc(doc)
        assert res.state_kind == "partial_coverage"
        assert len(res.focus_areas) >= 2
        assert res.leadership == []
        assert any(w["kind"] == "no_leadership_found" for w in res.warnings)

    def test_missing_path_returns_no_docx(self) -> None:
        res = parse_client_profile_path("/no/such/file.docx")
        assert res.state_kind == "no_docx_found"
        assert res.focus_areas == []
        assert res.leadership == []


class TestFixtureRoundTrip:
    """Verify against the real AlmaBank + WSFS fixtures when available."""

    def test_alma_real_fixture(self) -> None:
        from pathlib import Path
        # Committed real sample (was /tmp/dma-fixtures/* — a dev-only path
        # that made this test permanently SKIP in CI).
        p = (
            Path(__file__).resolve().parent / "fixtures"
            / "dma_packages_real_samples" / "Alma_Bank__DMA" / "04_reports"
            / "AlmaBank_ClientProfile_Research_Report.docx"
        )
        assert p.exists(), f"committed Alma client-profile DOCX missing: {p}"
        res = parse_client_profile_path(p)
        assert res.state_kind in {"full_coverage", "partial_coverage"}
        # Must extract leaders from the real Alma profile.
        assert len(res.leadership) >= 1, "No leadership captured from Alma fixture"
        # Must extract at least one focus area.
        assert len(res.focus_areas) >= 1
        # And the firmographics narrative is non-empty for full coverage.
        if res.state_kind == "full_coverage":
            assert res.firmographics_narrative_md != ""

    def test_wsfs_real_fixture(self) -> None:
        from pathlib import Path
        p = (
            Path(__file__).resolve().parent / "fixtures"
            / "dma_packages_real_samples" / "WSFS_Bank__DMA" / "04_reports"
            / "WSFS_Client_Profile_Research_Report.docx"
        )
        assert p.exists(), f"committed WSFS client-profile DOCX missing: {p}"
        res = parse_client_profile_path(p)
        assert res.state_kind in {"full_coverage", "partial_coverage"}
        # WSFS profile must yield ≥1 focus area.
        assert len(res.focus_areas) >= 1


class TestStrategicObjectives:
    """Per 2026-06 operator mandate: strategic objectives in the research
    report should be surfaced as focus_areas with
    `source_path='docx:strategic_section'` so the focus-area synthesizer
    can prefer them over Gemini-derived focus areas.
    """

    def test_strategic_priorities_header_classified(self) -> None:
        doc = _doc(
            ("Heading 2", "3.1 Strategic Priorities"),
            ("Normal",
             "Modernize the mortgage origination workflow within 18 "
             "months to lift P3 efficiency."),
            ("Normal",
             "Deepen relationship banking across the Astoria branch "
             "footprint to grow primary-PFI share."),
        )
        res = parse_client_profile_doc(doc)
        strat = [fa for fa in res.focus_areas
                 if fa.source_path == "docx:strategic_section"]
        assert len(strat) == 2
        assert "Modernize" in strat[0].title
        assert all(fa.verbatim_quote for fa in strat)

    def test_five_year_strategic_plan_header(self) -> None:
        doc = _doc(
            ("Heading 1", "4. Five-Year Strategic Plan"),
            ("Normal",
             "Bet 1 — Build a unified data foundation (P4C1.1.1) "
             "across all subsidiaries by 2028."),
            ("Normal",
             "Bet 2 — Launch a digital-first SMB lending product line "
             "within the next 24 months."),
        )
        res = parse_client_profile_doc(doc)
        strat = [fa for fa in res.focus_areas
                 if fa.source_path == "docx:strategic_section"]
        assert len(strat) == 2
        assert "P4C1.1.1" in strat[0].involved_subcap_ids

    def test_transformation_roadmap_header(self) -> None:
        doc = _doc(
            ("Heading 2", "5.2 Transformation Roadmap"),
            ("Normal",
             "Phase 1: Cloud migration of core banking platform "
             "(targeting 2027 cutover)."),
        )
        res = parse_client_profile_doc(doc)
        strat = [fa for fa in res.focus_areas
                 if fa.source_path == "docx:strategic_section"]
        assert len(strat) == 1

    def test_strategic_imperatives_header(self) -> None:
        doc = _doc(
            ("Heading 2", "Strategic Imperatives"),
            ("Normal",
             "Imperative 1 — Reduce branch operating costs by 15% "
             "via self-service uplift."),
            ("Normal",
             "Imperative 2 — Deploy AI-assisted underwriting across "
             "consumer + small-business loans."),
        )
        res = parse_client_profile_doc(doc)
        strat = [fa for fa in res.focus_areas
                 if fa.source_path == "docx:strategic_section"]
        assert len(strat) == 2

    def test_strategic_section_does_not_collide_with_top_findings(self) -> None:
        """A heading that matches BOTH Strategic + Top Findings stays
        in the Top Findings bucket only — the strategic extractor
        defers to that classification."""
        doc = _doc(
            ("Heading 2", "1.2 Strategic Top Findings"),
            ("Normal",
             "Finding — board pushed CEO to clarify the digital roadmap."),
        )
        res = parse_client_profile_doc(doc)
        # The row classifies as top-finding (no source_path override)
        # and there's no duplicate strategic-section row.
        strategic_rows = [fa for fa in res.focus_areas
                          if fa.source_path == "docx:strategic_section"]
        assert strategic_rows == []
        assert len(res.focus_areas) == 1

    def test_strategic_dedupes_repeated_bullets(self) -> None:
        """Bullet lists that repeat the same imperative in summary +
        detail sections are de-duped on normalized quote."""
        doc = _doc(
            ("Heading 2", "Strategic Pillars (summary)"),
            ("Normal",
             "Pillar A — Modernize the channels architecture across "
             "consumer and small-business."),
            ("Heading 2", "Strategic Pillars (detail)"),
            ("Normal",
             "Pillar A   —   Modernize the channels architecture across "
             "consumer and small-business."),
            ("Normal",
             "Pillar B — Deepen relationships through a relationship-"
             "manager-first SMB program."),
        )
        res = parse_client_profile_doc(doc)
        strat = [fa for fa in res.focus_areas
                 if fa.source_path == "docx:strategic_section"]
        # Pillar A duplicated across both subsections → 1 row, not 2.
        assert len(strat) == 2
