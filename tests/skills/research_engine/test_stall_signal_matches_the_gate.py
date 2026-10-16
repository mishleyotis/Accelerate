"""The driver's progress counter and the gate count "evidenced" the same way.

Measured 2026-09-14: floors_gate required the citation link to run BOTH ways
(the cell cites the id AND the register row names the cell back — Golden 1
has 248 cells where only the first holds), while pipeline._research_progress
accepted a one-way citation. So a lane citing ids the register did not name
back kept the stall counter moving through rounds the gate could never pass:
activity read as progress, which is the defect the 2026-09-12 stall work
removed from the search count and left here.
"""
from __future__ import annotations

import inspect

from engine import floors_gate, pipeline as P


def test_a_one_way_citation_is_not_evidenced():
    register = {"E-1": {"SubCap_IDs": "P1C1.1.2"}}
    assert floors_gate.cell_evidenced("P1C1.1.1", ["E-1"], register) is False
    assert floors_gate.cell_evidenced("P1C1.1.2", ["E-1"], register) is True


def test_a_dead_citation_is_not_evidenced():
    assert floors_gate.cell_evidenced("P1C1.1.1", ["E-9"], {}) is False


def test_a_row_naming_several_cells_evidences_each_of_them():
    register = {"E-1": {"SubCap_IDs": "P1C1.1.1, P3C2.4.1"}}
    for cell in ("P1C1.1.1", "P3C2.4.1"):
        assert floors_gate.cell_evidenced(cell, ["E-1"], register) is True


def test_the_two_definitions_are_one_function():
    """Two statements of one rule drift; this is the rule with one address."""
    src = inspect.getsource(P.Pipeline._research_progress)
    assert "floors_gate.cell_evidenced" in src
    assert "any(e in register for e in eids)" not in src, (
        "the one-way count is back in the driver's progress signature")


def test_the_gate_uses_it_too():
    assert "cell_evidenced" in inspect.getsource(floors_gate.run)
    assert "cell_evidenced" in inspect.getsource(floors_gate.run_density)
