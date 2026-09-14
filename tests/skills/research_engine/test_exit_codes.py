"""What the shell learns from a stopped run.

`watchdog --revive` reads the driver's return code and records RESOLVED or
FAILED from it, so the table is not cosmetic: a clean stop that exits
non-zero is re-dispatched by the next hourly sweep, and a real failure that
exits 0 is never looked at again.

A budget stop stays exit 1 ON PURPOSE — it needs a person to raise the
ceiling or narrow the scope, and a sweep that reported it RESOLVED would be
lying. What stops the re-dispatch loop is that the driver now remembers what
it spent (`test_budget_ceiling`) and the watchdog gives it a state no agent
may advance (`test_watchdog_stops_that_need_a_person`).
"""
from __future__ import annotations

import pytest

from engine import pipeline as P
from fixtures import new_run


ZERO = ("COMPLETE", "STOPPED_AT_UNTIL", "STOPPED_WALL_CLOCK")
ONE = ("STOPPED_BUDGET", "FAILED", "BLOCKED", "REFUSED")


@pytest.mark.parametrize("outcome", ZERO + ONE)
def test_the_exit_table(tmp_path, monkeypatch, outcome):
    run = new_run(tmp_path, n=3)
    monkeypatch.setattr(P.Pipeline, "run_all",
                        lambda self: {"outcome": outcome, "stage": "RESEARCH",
                                      "reason": "x", "stages_run": []})
    rc = P.main(["run", "--run", run.run_id, "--root", str(run.root),
                 "--dispatcher", "stub", "--json"])
    assert rc == (0 if outcome in ZERO else 1), outcome


def test_the_table_is_declared_once():
    assert set(P.EXIT_ZERO_OUTCOMES) == set(ZERO)
