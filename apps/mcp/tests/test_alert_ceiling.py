"""The alert queue is COUNTED and never refused, and both halves are load-bearing.

## Why there was a ceiling

Measured 2026-08-14: a run promoted carrying 98 open alerts — 59 high, 39
medium — because NOTHING anywhere read the count. Not at submit, not at
promote, not in the directory. The queue was the first thing an AE would meet
and it was unusable, and the run had passed every gate this connector has. The
build owner set a ceiling of 15 and the run was withdrawn.

## Why it was removed, 2026-08-16

A second client retired it. Under H3's literal contract — one alert per cell
scored on insufficient evidence — that run owed **621** alerts against the
same ceiling of 15: 621 of 705 scored cells flagged thin, 472 carrying no
linked evidence. The cause was structural rather than particular. The
assessment ran in PUBLIC evidence mode, whose own methodology states that is
why two thirds of subcapabilities come back Unknown, so an alert per unknown
cell counts the EVIDENCE MODE and not the work.

A ceiling of 15 against a floor of 621 is not a queue-length rule. It refuses
the corpus, and the only escape it leaves a producer is deleting alerts to
clear it — the one repair its own refusal text forbade.

## What must not be lost with it

The original defect was never the SIZE of the queue. It was that nobody read
the count. Deleting the counter alongside the ceiling would restore the exact
condition that let 98 alerts reach a dashboard unremarked, while looking like
a simplification. So the count survives as `promote_run`'s `open_alerts`, and
the tests below pin it: the number is still taken from the payload about to be
WRITTEN (invariant 8 — computed, never read from a stored total), it is still
honest about absence, and it is still returned to whoever promotes.
"""
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp import gates, promote
from dma_mcp.promote import _open_alert_count


def _live(n):
    return {"heatmap": {"payload": {"alerts": {"alerts": [{"subcap_id": f"P1C1.1.{i}"}
                                                          for i in range(n)]}}}}


# ── the ceiling is gone, and gone in every place that held it ──────────
def test_THERE_IS_NO_ALERT_CEILING():
    assert not hasattr(promote, "ALERT_CEILING")


def test_promote_cannot_refuse_on_the_alert_count():
    """The refusal path is removed, not merely raised to a bigger number. A
    ceiling of 10_000 would still be a rule that fires on some client, and the
    finding was that the count is the wrong thing to refuse on at all."""
    src = inspect.getsource(promote)
    assert "alert_ceiling_exceeded" not in src
    assert "ALERT_CEILING" not in src.replace(
        "# THE ALERT CEILING WAS REMOVED", "")


def test_the_registry_does_not_answer_for_a_rule_nothing_enforces():
    """`explain_gate` returning a definition for a removed gate is worse than
    `unknown_gate`: it reads as a live constraint to anyone who looks it up,
    and a producer would repair against a rule that cannot fire."""
    assert "SG-AC1" not in gates.GATES


# ── the count survives, because losing it restores the original defect ─
def test_THE_COUNT_IS_STILL_REPORTED_ON_PROMOTE():
    """The whole reason 98 reached a dashboard was that no code path returned
    this number. With the gate gone, the success path is the only one left."""
    src = inspect.getsource(promote)
    assert '"open_alerts": alerts' in src, (
        "promote_run no longer reports the open alert count anywhere — the "
        "ceiling and the measurement were removed together, which is the "
        "state that let 98 alerts promote unremarked")


def test_the_run_that_prompted_the_ceiling_is_still_counted_correctly():
    assert _open_alert_count(_live(98)) == 98


def test_the_second_client_that_retired_it_is_counted_too():
    assert _open_alert_count(_live(621)) == 621


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
    array length IS the queue — reading a stored count would report yesterday's
    number for a payload that changed since."""
    src = inspect.getsource(promote._open_alert_count)
    assert "SELECT" not in src.upper(), "the count must not query a stored total"
    assert "live" in src
