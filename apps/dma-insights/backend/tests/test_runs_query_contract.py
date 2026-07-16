"""Static contract: every column the /entities/{id}/runs handler reads
off its result rows must actually be selected by the SQL it executes.

Regression lock for the 2026-06-10 incident: F2 added
``COUNT(*) AS subcap_count`` to the aggregate subquery and read
``r.subcap_count`` when building RunSummary, but the OUTER select list
was not updated — every runs call 500'd with NoSuchColumnError across
the whole corpus (95/95 FAIL in qa_render_validation). Unit suites
missed it because no test executes that SQL against live PG; this
static check closes the class cheaply: it extracts the runs query and
asserts each ``r.<attr>`` consumed in the RunSummary construction
appears in the SELECT list (directly or via the agg alias).
"""
from __future__ import annotations

import re
from pathlib import Path

ROUTER = Path(__file__).resolve().parents[1] / "app" / "routers" / "entities.py"


def _extract_entity_runs_block() -> str:
    src = ROUTER.read_text(encoding="utf-8")
    start = src.index("async def entity_runs(")
    # Block ends at the next top-level route decorator.
    end = src.index("@router.", start)
    return src[start:end]


def test_runs_select_covers_every_consumed_column() -> None:
    block = _extract_entity_runs_block()

    sql_match = re.search(r'"""\s*(SELECT.*?)"""', block, re.S)
    assert sql_match, "runs SQL not found — keep the triple-quoted SELECT"
    sql = sql_match.group(1)
    select_list = sql.split("FROM")[0]

    consumed = set(re.findall(r"\br\.([a-z_]+)\b", block.split(").all()")[1]))
    assert consumed, "no r.<attr> consumption found after .all()"

    for col in sorted(consumed):
        assert re.search(rf"\b(?:r|agg)\.{col}\b|\bAS {col}\b", select_list), (
            f"entity_runs reads r.{col} but the SELECT list does not "
            f"provide it — this is the NoSuchColumnError class that "
            f"500'd all 95 corpus entities on 2026-06-10. Add it to the "
            f"outer SELECT (and the agg subquery if aggregated)."
        )


def test_runs_select_includes_subcap_count() -> None:
    """The Subcaps column (prototype parity F2) must stay wired."""
    block = _extract_entity_runs_block()
    assert "agg.subcap_count" in block
    assert "COUNT(*) AS subcap_count" in block
