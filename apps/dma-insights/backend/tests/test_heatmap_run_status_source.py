"""Regression: HeatmapResponse.run_status MUST be sourced from the
resolved DB run row, not from the `run` query-string parameter.

Pre-2026-06-06 the heatmap router had:
    run_status=getattr(run, "status", None)

Where `run` is the function's `str | None` query-string argument.
`getattr(str, "status", None)` ALWAYS returns None (str has no
status attribute). So every heatmap response returned
run_status=None regardless of the actual run state, breaking the
PENDING_REVIEW chip + any frontend logic that gates on run status.

The fix replaces the source with the resolved row's status field:
    run_status=resolved.status

Since `resolved` IS the run row (a SQLAlchemy mapping with a real
`status` column), the actual run status now round-trips to the
response.

This is a STATIC source-AST check (pure-logic, no DB) so it lands
in CI Stage 1.
"""
from __future__ import annotations

from pathlib import Path

ROUTER = (
    Path(__file__).parent.parent / "app" / "routers" / "heatmap.py"
)


def test_heatmap_run_status_uses_resolved_not_run_param() -> None:
    src = ROUTER.read_text()
    # The canonical correct line:
    assert "run_status=resolved.status" in src, (
        "heatmap.py must set run_status=resolved.status (the run row's "
        "status). If the source line moved, update this test."
    )
    # The old broken pattern MUST NOT appear:
    assert 'run_status=getattr(run, "status"' not in src, (
        "heatmap.py still has the broken pattern "
        "`run_status=getattr(run, \"status\", None)`. `run` is the "
        "query-string str | None, NOT the resolved row -- getattr on a "
        "str always returns None, so the response always emits "
        "run_status=null regardless of the actual run state. Replace "
        "with `run_status=resolved.status`."
    )


def test_heatmap_subcap_drawer_accepts_run_query_param() -> None:
    """QA-2: the heatmap_subcap drawer route MUST accept `run` and
    forward it to the inner heatmap() call so a historical-run drawer
    reads from the same run as the parent page."""
    src = ROUTER.read_text()
    # The route signature must declare `run: str | None`.
    assert "run: str | None = None" in src, (
        "heatmap_subcap must declare `run: str | None = None` so the "
        "frontend drawer can pass the parent page's selected run."
    )
    # The inner heatmap() call must forward it.
    assert "run=run" in src, (
        "heatmap_subcap must pass `run=run` into the inner heatmap() "
        "call so the drawer uses the same resolved run as the parent."
    )
