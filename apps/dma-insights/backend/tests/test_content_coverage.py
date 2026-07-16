"""Corpus content-coverage floors (plan Part 7 regression gate).

Runs the offline coverage matrix over the whole fixture corpus once and
asserts per-block EXTRACTED floors. This locks in the cumulative gains
from the extraction work (firmographics / SCQA / insights / peers /
category rollups / recommendations / timeline / financials / sentiment /
audit / tech) so a future parser change can't silently regress a surface
back toward the empty corpus it started as.

Floors are set below the currently-measured values (headroom for benign
fixture churn) but far above the pre-work baseline (most were 0).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.scripts.parse_coverage import compute_coverage

_FIX = Path(__file__).resolve().parents[1] / "tests/fixtures/dma_packages_batches"

# block → minimum EXTRACTED packages (measured 2026-06-09, minus margin).
_FLOORS = {
    "D1.scqa": 100,
    "D1.firmographics": 100,
    "D1.scores": 90,
    "D2.insights": 85,
    "D3.peer_benchmarks": 82,
    "D3.categories": 90,
    "D4.recommendations": 82,
    "D5.timeline": 46,
    "D5.financials": 50,
    "D5.sentiment": 27,
    "D6.audit": 35,
    "D6.caps": 40,
    "D6.qa_verdict": 88,
    "D7.tech": 96,
}


@pytest.fixture(scope="module")
def coverage():
    if not _FIX.exists():
        pytest.skip("fixtures missing")
    cov, eligible, ineligible = compute_coverage(_FIX)
    return cov, eligible, ineligible


def test_eligible_corpus_size(coverage) -> None:
    _, eligible, ineligible = coverage
    # ~105 eligible / ~8 empty-stub ineligible (discovery resolves the rest).
    assert eligible >= 100
    assert ineligible <= 12


@pytest.mark.parametrize("block,floor", list(_FLOORS.items()))
def test_block_extracted_floor(coverage, block: str, floor: int) -> None:
    cov, _, _ = coverage
    got = cov[block].extracted
    assert got >= floor, (
        f"{block} EXTRACTED regressed to {got} (floor {floor}); "
        f"FAIL={cov[block].fail} PENDING={cov[block].pending}"
    )
