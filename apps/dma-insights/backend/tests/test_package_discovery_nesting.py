"""Discovery robustness for nested / non-canonical package layouts.

~49% of the historical DMA corpus buries the canonical `01_..08_`
subfolders 2-4 levels below the entity folder. The legacy `_find_root`
only inspected the entity folder and its direct children, so those
packages were dropped wholesale. These tests pin the bounded-depth
descent (`_descend_to_best_root`) against synthetic trees that mirror the
real corpus archetypes from the 113-package structural census.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.parsers.dma_package import (
    _descend_to_best_root,
    _find_root,
    _score_package_dir,
)

_CANON = (
    "01_evidence", "02_research_workbook", "03_scoring_workbook",
    "04_reports", "05_narrative_deck", "06_peers", "07_governance",
    "08_appendices",
)


def _make_canonical_package(at: Path) -> Path:
    """Create a full canonical 8-folder package rooted at `at`."""
    at.mkdir(parents=True, exist_ok=True)
    for folder in _CANON:
        (at / folder).mkdir()
    (at / "08_appendices" / "04_scores.json").write_text("{}")
    (at / "03_scoring_workbook" / "DMA_Assessment_Workbook_X.xlsx").write_text("")
    (at / "04_reports" / "DMA_Assessment_Report_X.docx").write_text("")
    return at


def test_canonical_root_unchanged(tmp_path: Path) -> None:
    """Archetype A: package at the entity root resolves to itself."""
    pkg = _make_canonical_package(tmp_path / "Acme Bank - DMA")
    assert _find_root(pkg) == pkg


def test_single_level_nesting(tmp_path: Path) -> None:
    """Archetype E1: `<Entity> - DMA/<Entity>/` (depth 1) — already
    handled by the legacy one-level check, asserted here as a guard."""
    entity = tmp_path / "Zions Bancorporation - DMA"
    entity.mkdir()
    pkg = _make_canonical_package(entity / "Zions")
    assert _find_root(entity) == pkg


def test_deep_nesting_depth_two(tmp_path: Path) -> None:
    """Archetype E4: `<Entity> - DMA/<Entity>/<Entity> DMA/` (depth 2)."""
    entity = tmp_path / "IMA Financial - DMA"
    pkg = _make_canonical_package(entity / "IMA Financial" / "IMA Financial DMA")
    assert _find_root(entity) == pkg


def test_deep_nesting_depth_three(tmp_path: Path) -> None:
    """Archetype E1 deep: `<Entity> - DMA/DMA/DMA <date>/` (depth 3)."""
    entity = tmp_path / "Navy Federal Credit Union - DMA"
    pkg = _make_canonical_package(entity / "DMA" / "DMA 2026-02-20" / "pkg")
    assert _find_root(entity) == pkg


def test_atb_v2_hybrid_prefers_full_package(tmp_path: Path) -> None:
    """Archetype E3 (ATB): a loose top-level report DOCX sits beside a
    nested `<Entity> v2/` folder holding the full package. The full
    package must win over the bare DOCX."""
    entity = tmp_path / "ATB - DMA"
    entity.mkdir()
    (entity / "DMA_Assessment_Report_ATB_Financial.docx").write_text("")
    pkg = _make_canonical_package(entity / "ATB DMA v2")
    assert _find_root(entity) == pkg


def test_descent_skips_exports_and_charts(tmp_path: Path) -> None:
    """The descent must never mis-root onto a leaf-artifact subfolder
    (`exports/`, `charts/`) even when it contains CSVs."""
    pkg = _make_canonical_package(tmp_path / "Acme - DMA")
    exports = pkg / "03_scoring_workbook" / "exports"
    exports.mkdir()
    (exports / "export_scoring_detail.csv").write_text("a,b\n1,2\n")
    assert _find_root(pkg) == pkg


def test_score_zero_for_empty_tree(tmp_path: Path) -> None:
    """A directory tree with no DMA signal scores 0 and descent returns None."""
    empty = tmp_path / "random"
    (empty / "notes").mkdir(parents=True)
    (empty / "notes" / "todo.txt").write_text("hi")
    assert _score_package_dir(empty) == 0
    assert _descend_to_best_root(empty) is None


def test_find_root_raises_on_no_package(tmp_path: Path) -> None:
    """No package signal anywhere → FileNotFoundError (unchanged contract)."""
    empty = tmp_path / "random"
    empty.mkdir()
    (empty / "meeting_notes.docx").write_text("")  # non-DMA docx
    with pytest.raises(FileNotFoundError):
        _find_root(empty)
