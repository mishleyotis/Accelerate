"""The search-op ceiling is a wall, not a number in a report.

R27 has said since the beginning: "a conversation that has fired 40
search-ops must checkpoint and STOP". It was enforced by `stats()` returning
`checkpoint_required` and `orient.py` printing it first in `do_first`.

AUD-0037 already recorded what that is worth: orient reported 45/40, said
"state clean", handed over the next card and exited 0. The fix at the time
was to make the number louder.

Measured 2026-08-30 on a live run: **73 search ops against a cap of 40** —
183% of the limit, the same finding recurring, because a louder number is
still a number and nothing refused the 41st search.

So `append_search` refuses. The window is measured from the last checkpoint
rather than from run start, because the ceiling is per CONVERSATION: a long
run must be able to checkpoint and legitimately continue. That is not a
loophole — it is the whole mechanism. The ceiling exists to force a run to
write down where it got to before its context fills with searches it will
not remember, which is the same failure as "the agents lose context".

These tests pin both halves: the wall stops a run, and the checkpoint lets
it through.
"""
import pytest

from engine import ledger as L
from engine import runstate
from fixtures import new_run


def _fire(wb, n, *, start=0):
    """n search ops, distinctly queried so nothing dedupes them."""
    for i in range(start, start + n):
        L.append_search(wb, subcap=None, facet="works",
                        query=f"probe {i} — distinct query text",
                        tool="web_search", hits=2, kept=1, outcome="kept 1",
                        prelim=True)


def test_the_ceiling_refuses_rather_than_reporting(tmp_path):
    """The 41st search is refused. This is the whole fix."""
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    before = len(wb.rows("Search_Log"))
    room = L.SEARCH_OP_CEILING - L._ops_since_checkpoint(wb)
    _fire(wb, room)
    with pytest.raises(L.LedgerRefusal) as e:
        _fire(wb, 1, start=9000)
    assert "ceiling" in str(e.value).lower()
    assert "checkpoint" in str(e.value).lower(), (
        "the refusal must name the way out, or an agent that hits it has "
        "nowhere to go and the run simply dies at the wall")
    assert len(wb.rows("Search_Log")) >= before


def test_a_checkpoint_reopens_the_window(tmp_path):
    """A long run must be able to continue — after writing down where it is.

    If this fails, the ceiling has become a lifetime budget and any run
    needing more than 40 searches is unfinishable.
    """
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    _fire(wb, L.SEARCH_OP_CEILING - L._ops_since_checkpoint(wb))
    with pytest.raises(L.LedgerRefusal):
        _fire(wb, 1, start=9000)

    runstate.checkpoint(wb, "P1C1 closed; resuming at P1C2")
    _fire(wb, 1, start=9100)          # must not raise
    assert L._ops_since_checkpoint(wb) == 1


def test_the_checkpoint_records_the_mark_it_is_measured_from(tmp_path):
    """Without the count, the window has nothing to measure from and the
    ceiling silently becomes a lifetime budget again."""
    import json
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    _fire(wb, 5)
    runstate.checkpoint(wb, "somewhere")
    mark = json.loads(wb.metadata()["checkpoint"])
    assert mark["search_ops"] == len(wb.rows("Search_Log"))
    assert mark["position"] == "somewhere"


def test_a_run_that_never_checkpointed_measures_from_zero(tmp_path):
    """Its whole history is one conversation, so every op counts."""
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    base = L._ops_since_checkpoint(wb)
    assert base == len(wb.rows("Search_Log"))
    _fire(wb, 3)
    assert L._ops_since_checkpoint(wb) == base + 3


def test_stats_and_the_wall_agree(tmp_path):
    """`checkpoint_required` was the advisory half. It must not now say
    'fine' while append_search refuses, or the next reader trusts the wrong
    one — which is how AUD-0037 happened in the first place."""
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    _fire(wb, L.SEARCH_OP_CEILING - L._ops_since_checkpoint(wb))
    assert L.stats(wb)["checkpoint_required"] is True
    with pytest.raises(L.LedgerRefusal):
        _fire(wb, 1, start=9000)


def test_the_ceiling_is_still_reachable_by_normal_work(tmp_path):
    """A guard that fires on ordinary volumes would push agents to stop
    logging searches, which would blind every other check that reads the
    Search_Log. Under the five-volley rule eight cells cost forty searches
    — the old cap exactly — so the wall is sixty: twelve fully volleyed
    cells between checkpoints, still one conversation's worth."""
    run = new_run(tmp_path, n=8, prelim=False)
    wb = run.open()
    from fixtures import bank_evidence
    for cell in wb.selected_subcaps():
        bank_evidence(wb, cell, n=3)
    assert L._ops_since_checkpoint(wb) < L.SEARCH_OP_CEILING, (
        "banking three items for each of eight subcaps already hits the "
        "ceiling — it is too tight to do a category's work under")
