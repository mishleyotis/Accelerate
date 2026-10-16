"""The card's number and the card's bars come from one row.

MEASURED 2026-09-04 on goeasy Ltd. (`DMA-RES-GSY-20260830-0002`). The client
directory rendered the word "maturity" over an empty slot beside four pillar
bars that resolved — 2.09 / 2.19 / 2.01 / 2.16 — and the run's own promoted
overview hero stated `composite: 2.11` the whole time.

`serving_directory` already joined `overview_scores` and already took the
bars from it (`os.pillars`). It took the headline figure from `r.composite`,
the value read out of the scoring workbook at ingest. goeasy's workbook
states no OVERALL row — the composite repair opened it eight times and
reported "workbook states none" every time, which is correct: absent beats
invented. So one card was drawing two figures from two sources and only one
of them existed.

Neither figure is DERIVED. `r.composite` is read from the workbook;
`os.composite` is the hero the producer published and the validator
accepted. The coalesce prefers the workbook — the assessment's own
arithmetic — and lets the hero fill the silence, and only the silence.

These read the migration's SQL rather than a live database: the DB-backed
suites cover behaviour where a Postgres is available, and this must fail in
a checkout with none.
"""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
MIG = ROOT / "migrations" / "versions" / "0060_directory_composite_matches_the_hero.py"


@pytest.fixture(scope="module")
def m():
    spec = importlib.util.spec_from_file_location("_m0060", MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_headline_falls_back_to_the_hero_the_bars_come_from(m):
    """THE POINT. Same row, same card, one source of truth."""
    assert "COALESCE(r.composite, os.composite) AS composite" in m._VIEW_BODY
    assert "LEFT JOIN overview_scores os ON os.run_id = r.id" in m._VIEW_BODY, \
        "the hero row the bars come from must still be joined"
    assert "os.pillars" in m._VIEW_BODY, "the bars still come from the hero"


def test_the_workbook_figure_still_wins_where_there_is_one(m):
    """Order, not merely presence: `COALESCE(os.composite, r.composite)` would
    let a producer's hero override the assessment's own arithmetic."""
    body = m._VIEW_BODY
    assert "COALESCE(os.composite, r.composite)" not in body, \
        "the hero must fill the silence, not overrule the workbook"


def test_nothing_is_derived_from_the_pillars(m):
    """A mean of the four bars would be a computed number in a column whose
    contract is that it was stated, and indistinguishable from a real one
    afterwards. A run stating neither figure still serves NULL."""
    body = m._VIEW_BODY.lower()
    for forbidden in ("avg(", "/ 4", "/4.0", "sum("):
        assert forbidden not in body, \
            f"the composite is being derived ({forbidden!r} in the view body)"


def test_the_rebuild_carries_0059s_worker_grant(m):
    """Rebuilding drops `refresh_serving_directory()` and every grant on it.
    0059 gave svc_worker EXECUTE so the scan Job can publish the composites
    it repairs; a rebuild recreating only svc_mcp's grant would silently
    un-fix 0059 and the repairs would go unpublished again."""
    src = MIG.read_text()
    assert "GRANT EXECUTE ON FUNCTION refresh_serving_directory() \"\n" \
           "               \"TO svc_worker" in src or "TO svc_worker" in src, \
        "the rebuild drops 0059's grant and never restores it"
    assert "TO svc_mcp" in src, "svc_mcp's grant must survive the rebuild too"


def test_downgrade_actually_removes_the_change(m):
    """0042's guard, for its reason: a substitution that produced the same
    string either way makes downgrade() a no-op that reports success."""
    assert m._PRE_0060 != m._VIEW_BODY
    assert "COALESCE(r.composite, os.composite)" not in m._PRE_0060
