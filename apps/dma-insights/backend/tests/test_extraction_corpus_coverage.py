"""Corpus-wide extraction coverage gate (the data-quality proof + regression
guard). Runs the real `parse_package` over all 113 fixture packages and
asserts per-surface coverage floors — this is what answers "does extraction
work for ALL clients?".

Baselines captured 2026-06-23 BEFORE the data-quality fixes:
    leadership non-empty:  53/113
    insight so_what:       121/651 cards (19%)
    insight synthetic title (old "{cat}: maturity gap" style): 491/651
    tech non-empty:        110/113

The floors below lock in the improvement and fail if a regression drops
coverage. Slow (~2 min, parses 113 packages); skip locally with
DMA_SKIP_CORPUS_COVERAGE=1.
"""
from __future__ import annotations

import functools
import os

import pytest

from app.scripts.diagnose_extraction import _DEFAULT_CORPUS, run

pytestmark = pytest.mark.skipif(
    os.environ.get("DMA_SKIP_CORPUS_COVERAGE") == "1"
    or not _DEFAULT_CORPUS.exists(),
    reason="corpus fixtures absent or DMA_SKIP_CORPUS_COVERAGE=1",
)


@functools.lru_cache(maxsize=1)
def _census():
    return run(_DEFAULT_CORPUS)


def test_corpus_parses_without_errors() -> None:
    c = _census()
    assert c.packages >= 110, f"expected the full corpus, parsed {c.packages}"
    assert c.parse_errors == 0, f"parse errors: {c.error_names}"


def test_leadership_coverage_floor() -> None:
    # Baseline 53/113; the dict-of-roles + role-string + DOCX-discovery fixes
    # lift it to ~76. Floor at 70 keeps headroom while catching regressions.
    c = _census()
    assert c.lead_nonempty >= 70, (
        f"leadership coverage regressed to {c.lead_nonempty}/{c.packages} (floor 70)"
    )


def test_insight_so_what_floor() -> None:
    # Baseline 121/651 (19%); the category-gap rewrite populates a real
    # so-what on every derived card → ~94%.
    c = _census()
    assert c.ic_rows > 0
    ratio = c.ic_with_sowhat / c.ic_rows
    assert ratio >= 0.85, (
        f"so_what coverage {c.ic_with_sowhat}/{c.ic_rows} ({ratio:.0%}) below 85%"
    )


def test_no_old_style_synthetic_titles() -> None:
    # The robotic "{category}: maturity gap" / ": relative priority" titles
    # (491 at baseline) are replaced with thematic, deficit-stating titles.
    c = _census()
    assert c.ic_synthetic_title == 0, (
        f"{c.ic_synthetic_title} old-style synthetic titles remain"
    )


def test_tech_extraction_floor() -> None:
    c = _census()
    assert c.tech_nonempty >= 100, (
        f"tech coverage regressed to {c.tech_nonempty}/{c.packages} (floor 100)"
    )


def test_tech_prototype_fields_populated() -> None:
    # Baselines were status_enum=0, l3=0. Every row must now carry the
    # prototype status enum; l3_id resolves wherever a scored platform maps
    # (~478/2442 — the rest legitimately don't map to the five platforms).
    c = _census()
    assert c.tech_with_status_enum == c.tech_rows, (
        f"{c.tech_rows - c.tech_with_status_enum} tech rows lack the status enum"
    )
    assert c.tech_with_l3 >= 300, (
        f"l3_id coverage {c.tech_with_l3} below floor 300 (was 0 at baseline)"
    )
