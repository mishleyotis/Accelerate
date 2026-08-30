"""_served_figures resolves pillar and category grain from the run's own cells.

CG-07 has two branches, and only one of them was ever about a wrong number.
The first catches a quoted figure that disagrees with its named row. The
second refuses a figure whose grain the run serves nothing for, on the
ground that it "cannot be checked" — and on a run whose ingestion carried no
pillar or category rollup row that branch fired on every pillar figure,
which is why the first card of the first page could show four empty bars
over a run that serves all 705 cells the mean is taken over.

The premise is what was wrong, not the gate. `bundle.rollups.capabilities`
already computes exactly this arithmetic one grain lower and declares its
basis; these tests hold pillar and category grain to the same rule, and hold
the precedence that matters: a STATED workbook figure always wins.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dma_mcp.validation2 import _served_figures     # noqa: E402


class _Cur:
    """The two queries `_served_figures` makes, answered in order."""

    def __init__(self, cells, manifest):
        self._cells = cells
        self._manifest = manifest
        self._last = None

    def execute(self, sql, args=None):
        self._last = "manifest" if "run_manifest" in sql else "cells"

    def fetchall(self):
        return list(self._cells)

    def fetchone(self):
        return [self._manifest]


class _Conn:
    def __init__(self, cells, manifest=None):
        self._cur = _Cur(cells, manifest)

    def cursor(self):
        return self._cur


CELLS = [("P1C1.1.1", 2.0), ("P1C1.1.2", 1.0),      # P1C1 -> 1.5
         ("P1C2.7.3", 3.0),                          # P1C2 -> 3.0, P1 -> 2.0
         ("P4C2.5.1", 1.5), ("P4C2.5.2", 1.5)]       # P4C2 -> 1.5, P4 -> 1.5


def test_pillar_and_category_are_derived_when_the_workbook_states_none():
    served = _served_figures(_Conn(CELLS), "run")
    assert served["P1C1.1.1"] == 2.0                 # cells still served
    assert served["P1C1"] == 1.5                     # mean of its two cells
    assert served["P1C2"] == 3.0
    assert round(served["P1"], 4) == 2.0             # mean of all three P1 cells
    assert served["P4C2"] == 1.5
    assert served["P4"] == 1.5


def test_a_stated_workbook_figure_wins_over_the_derived_one():
    manifest = {"workbook_grains": {
        "pillars": [{"pillar_id": "P1", "score": 1.62}],
        "categories": [{"category_id": "P1C1", "score": 1.8}]}}
    served = _served_figures(_Conn(CELLS, manifest), "run")
    assert served["P1"] == 1.62                      # struck, not computed
    assert served["P1C1"] == 1.8
    assert served["P1C2"] == 3.0                     # no stated row, derived
    assert served["P4"] == 1.5


def test_a_grain_with_no_scored_cell_stays_unresolvable():
    """The rejection branch must still fire where nothing was scored — an
    unserved grain is not made checkable by inventing a mean of nothing."""
    served = _served_figures(_Conn([("P1C1.1.1", 2.0)]), "run")
    assert "P2" not in served and "P2C1" not in served


def test_a_null_score_contributes_to_no_mean():
    served = _served_figures(_Conn([("P1C1.1.1", 2.0), ("P1C1.1.2", None)]),
                             "run")
    assert served["P1C1"] == 2.0 and served["P1"] == 2.0
