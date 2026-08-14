"""A run reaches a dashboard only if its alert queue is workable.

Measured 2026-08-14: a run promoted carrying 98 open alerts — 59 high, 39
medium — because NOTHING anywhere read the count. Not at submit, not at
promote, not in the directory. The queue was the first thing an AE would meet
and it was unusable, and the run had passed every gate this connector has.

The build owner set the ceiling at 15 and the run was withdrawn.

The tests below pin the two halves that matter: the count is taken from the
payload about to be WRITTEN (invariant 8 — counted, never read from a stored
total), and the refusal names the number so the repair is obvious.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.promote import ALERT_CEILING, _open_alert_count


def _live(n):
    return {"heatmap": {"payload": {"alerts": {"alerts": [{"subcap_id": f"P1C1.1.{i}"}
                                                          for i in range(n)]}}}}


def test_the_ceiling_is_the_number_the_owner_set():
    assert ALERT_CEILING == 15


def test_the_run_that_prompted_this_is_over_the_ceiling():
    """98 alerts, the shape actually promoted."""
    assert _open_alert_count(_live(98)) == 98
    assert _open_alert_count(_live(98)) > ALERT_CEILING


def test_a_workable_queue_passes():
    assert _open_alert_count(_live(14)) <= ALERT_CEILING


def test_the_boundary_is_inclusive_of_the_ceiling():
    """"fewer than 15 before being shown" — 15 itself is allowed through, 16
    is not. Stated because an off-by-one here is the difference between a
    rule and a rule nobody trusts."""
    assert not _open_alert_count(_live(15)) > ALERT_CEILING
    assert _open_alert_count(_live(16)) > ALERT_CEILING


# ── the count is honest about absence ─────────────────────────────────
def test_a_run_with_no_alerts_section_counts_zero():
    """A run that raised none is not a run that hid them."""
    assert _open_alert_count({"heatmap": {"payload": {}}}) == 0


def test_an_empty_alert_list_counts_zero():
    assert _open_alert_count(_live(0)) == 0


def test_a_missing_heatmap_page_does_not_raise():
    assert _open_alert_count({}) == 0
    assert _open_alert_count({"heatmap": {}}) == 0


def test_a_malformed_alerts_section_counts_zero_rather_than_crashing():
    """Promotion must not die on a shape; CG-03 owns the shape."""
    for bad in ("nonsense", 42, [], None):
        assert _open_alert_count({"heatmap": {"payload": {"alerts": bad}}}) == 0


def test_the_count_reads_the_payload_not_a_stored_total():
    """Invariant 8. The alert rows promotion writes all start open, so the
    array length IS the queue — reading a stored count would let a run whose
    payload grew since the last promote through on yesterday's number."""
    import inspect

    from dma_mcp import promote
    src = inspect.getsource(promote._open_alert_count)
    assert "SELECT" not in src.upper(), "the count must not query a stored total"
    assert "live" in src
