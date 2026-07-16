"""report_synthesis.md → D1 SCQA section.

Pins the markdown parser (heading, E-ID + subcap extraction, empty-guard)
and the end-to-end wiring: a package with report_synthesis.md but no DOCX
exec-summary gains an `executive_summary_scqa` ReportSectionRow that flows
to the D1 SCQA card via the existing document_sections pipeline.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.services.parsers.report_synthesis import (
    build_derived_scqa,
    find_report_synthesis,
    parse_report_synthesis_md,
)


def _cat(cid: str, name: str, score, peer=None):
    return SimpleNamespace(
        category_id=cid, category_name=name, score=score, peer_median=peer
    )

_GREENSTONE = (
    Path(__file__).resolve().parents[1]
    / "tests/fixtures/dma_packages_batches/batch_14/Greenstone - DMA"
)


def test_parse_real_report_synthesis() -> None:
    p = _GREENSTONE / "02_research_workbook/report_synthesis.md"
    if not p.exists():
        import pytest
        pytest.skip(f"fixture moved: {p}")
    synth = parse_report_synthesis_md(p)
    assert synth is not None
    assert "What story does the DATA tell" in synth.body
    assert synth.heading.startswith("Report Synthesis")
    # E-IDs + category ids extracted for lineage
    assert "E-072" in synth.e_ids
    assert any(c.startswith("P3C3") for c in synth.subcap_ids)


def test_empty_and_absent(tmp_path: Path) -> None:
    assert parse_report_synthesis_md(tmp_path / "nope.md") is None
    thin = tmp_path / "report_synthesis.md"
    thin.write_text("# Report Synthesis\n\n(pending)")
    assert parse_report_synthesis_md(thin) is None  # < 80 chars of body


def test_heading_and_extraction(tmp_path: Path) -> None:
    p = tmp_path / "report_synthesis.md"
    p.write_text(
        "# Report Synthesis — Acme Bank DMA\n"
        "# Generated from report_analysis.json\n\n"
        "## 1. What story does the DATA tell?\n"
        "Acme scores 2.5 overall. P1C1 strong (E-001, T1); P4C2 weak (E-091).\n"
        "Compliance P3C3.1 at 3.2 (E-072).\n"
    )
    synth = parse_report_synthesis_md(p)
    assert synth is not None
    assert synth.heading == "Report Synthesis — Acme Bank DMA"
    assert synth.e_ids == ["E-001", "E-072", "E-091"]
    assert "P1C1" in synth.subcap_ids and "P3C3.1" in synth.subcap_ids


def test_find_report_synthesis() -> None:
    if not _GREENSTONE.exists():
        import pytest
        pytest.skip("fixture moved")
    found = find_report_synthesis(_GREENSTONE)
    assert found is not None and found.name == "report_synthesis.md"


def test_e2e_scqa_prefers_richer_synthesis() -> None:
    """Greenstone ships report_synthesis.md AND a (thinner) DOCX
    exec-summary → parse_package should PREFER the richer synthesis,
    leaving exactly one executive_summary_scqa carrying the md body."""
    from app.services.parsers.dma_package import parse_package

    if not _GREENSTONE.exists():
        import pytest
        pytest.skip("fixture moved")
    pkg = parse_package(_GREENSTONE)
    scqa = [s for s in pkg.report_sections if s.kind == "executive_summary_scqa"]
    assert len(scqa) == 1, "exactly one SCQA section (thin DOCX one replaced)"
    sec = scqa[0]
    assert "What story does the DATA tell" in sec.body
    assert (sec.source_path or "").endswith("report_synthesis.md")
    assert len(sec.e_ids_mentioned) > 0
    assert any(
        w.startswith("scqa_from_report_synthesis_md") for w in pkg.parser_warnings
    )


# ---------------------------------------------------------------------
# D2.5 — the "0.00 overall" SCQA bug
# ---------------------------------------------------------------------
# A real DMA maturity score clamps to [1.0, 5.0]; a 0.0 is a placeholder
# sentinel. Including placeholders rendered "**0.00** overall" even when
# real scores existed (aafcu: shown 0.00 vs 2.36 real).


def test_derived_scqa_ignores_zero_placeholder_scores() -> None:
    """0.0 placeholders must be dropped so `overall` reflects only real
    scores — never the spurious 0.00."""
    cats = [
        _cat("P1C1", "Strategy", 0.0),       # placeholder — must be ignored
        _cat("P2C1", "Customer", 2.0, 2.5),
        _cat("P3C1", "Operations", 3.0, 2.5),
    ]
    out = build_derived_scqa("Aafcu Bank", cats, [])
    assert out is not None
    assert "0.00" not in out, "zero-placeholder leaked into overall"
    # overall = mean(2.0, 3.0) = 2.50 (the 0.0 excluded)
    assert "**2.50** overall" in out
    assert "2 capability categories" in out  # only the 2 real ones counted


def test_derived_scqa_returns_none_when_all_scores_are_placeholders() -> None:
    """An all-placeholder set has no real anchor → return None so the
    richer downstream pass (grounded in real subcap_scores) fills it."""
    cats = [_cat("P1C1", "Strategy", 0.0), _cat("P2C1", "Customer", 0.0)]
    assert build_derived_scqa("Placeholder CU", cats, []) is None


def test_derived_scqa_still_none_when_no_scores() -> None:
    """The original contract (None when nothing to anchor) is preserved."""
    assert build_derived_scqa("Empty", [], []) is None
    assert build_derived_scqa("AllNone", [_cat("P1C1", "X", None)], []) is None
