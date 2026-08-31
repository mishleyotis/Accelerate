"""The search-op ceiling, measured ONE way.

MEM-0436, 2026-08-31. Three runs walled at 141, ~180 and 567 search ops and
could not be unwalled by checkpointing. The cause was two measurements of one
rule:

  append_search  (the WALL)    refuses on `_ops_since_checkpoint` — a window
                               a checkpoint resets, because the ceiling is
                               per CONVERSATION and a long run must be able
                               to checkpoint and legitimately continue.
  stats()        (the ADVICE)  computed `checkpoint_required` from the
                               LIFETIME count, so once a run passed 40
                               searches ever it was true forever.

orient prints the advice first, so every conductor obediently stopped, and
no checkpoint could clear it. One of the three had already had its window
reset by a revival and was still being told to stop.

THESE TESTS ASSERT BOTH DIRECTIONS, which is the whole point. A fix that
only made runs proceed would have silently disabled the runaway-spend
protection the ceiling exists to provide (MEM-0338 / R27) — the same defect
pointing the other way, and far harder to notice.
"""
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[2].parent / (
    "plugins/dma-insights/skills/dma-research")
sys.path.insert(0, str(ENGINE))

from engine import ledger as L, runstate  # noqa: E402
from fixtures import new_run  # noqa: E402

CAP = L.SEARCH_OP_CEILING


def _search(wb, i):
    L.append_search(wb, subcap=None, facet=None, query=f"q{i}",
                    tool="web", hits=1, kept=1)


# ── direction one: the gate must still STOP ──────────────────────────────

def test_over_the_cap_since_the_last_checkpoint_still_stops(tmp_path):
    """The half a loosened ceiling would have lost."""
    wb = new_run(tmp_path, prelim=False).open()
    for i in range(CAP):
        _search(wb, i)
    assert L.stats(wb)["checkpoint_required"] is True
    with pytest.raises(L.LedgerRefusal) as e:
        _search(wb, CAP)
    assert "ceiling" in str(e.value)


def test_the_wall_and_the_advice_agree_at_every_step(tmp_path):
    """Two measurements of one rule is the defect. At no point may the
    advice say proceed while the wall refuses, or the reverse."""
    wb = new_run(tmp_path, prelim=False).open()
    for i in range(CAP + 3):
        advice = L.stats(wb)["checkpoint_required"]
        try:
            _search(wb, i)
            walled = False
        except L.LedgerRefusal:
            walled = True
        assert advice == walled, (
            f"at op {i}: advice said checkpoint_required={advice} while the "
            f"wall {'refused' if walled else 'allowed'} the search")


# ── direction two: a checkpoint must actually clear it ───────────────────

def test_a_checkpoint_clears_the_advice_not_just_the_wall(tmp_path):
    """THE BUG ITSELF. Before the fix this stayed True forever."""
    wb = new_run(tmp_path, prelim=False).open()
    for i in range(CAP):
        _search(wb, i)
    assert L.stats(wb)["checkpoint_required"] is True

    runstate.checkpoint(wb, "closed P1C1, resuming at P1C2")

    st = L.stats(wb)
    assert st["checkpoint_required"] is False, (
        "checkpointing did not clear the advice — this is MEM-0436, and it "
        "walled three live runs")
    _search(wb, CAP + 1)          # and the wall agrees


def test_a_run_far_over_the_lifetime_cap_proceeds_after_checkpointing(
        tmp_path):
    """goeasy was at 567 ops, 1425% of the cap, with its window legitimately
    reset. Lifetime spend must never be what decides."""
    wb = new_run(tmp_path, prelim=False).open()
    fired = 0
    for _ in range(4):
        for _ in range(CAP - 1):
            _search(wb, fired); fired += 1
        runstate.checkpoint(wb, f"after {fired} ops")
    assert fired > CAP * 3, fired
    st = L.stats(wb)
    assert st["search_ops"] == fired, "lifetime spend is still reported"
    assert st["checkpoint_required"] is False
    _search(wb, fired)


def test_lifetime_spend_is_reported_but_never_decides(tmp_path):
    """Spend is worth seeing. It just may not be the gate."""
    wb = new_run(tmp_path, prelim=False).open()
    for i in range(CAP + 5):
        try:
            _search(wb, i)
        except L.LedgerRefusal:
            runstate.checkpoint(wb, "mid")
            _search(wb, i)
    st = L.stats(wb)
    assert st["search_ops"] > CAP
    assert st["search_ops_since_checkpoint"] < st["search_ops"]
    assert st["checkpoint_required"] is False


def test_a_fresh_run_is_not_told_to_checkpoint(tmp_path):
    wb = new_run(tmp_path, prelim=False).open()
    st = L.stats(wb)
    assert st["checkpoint_required"] is False
    assert st["search_ops"] == 0 and st["search_ops_since_checkpoint"] == 0
