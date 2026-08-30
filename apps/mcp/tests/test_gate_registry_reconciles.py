"""Removing a gate from the code did not remove it from production.

Measured 2026-08-16. The build owner removed the open alert ceiling. `SG-AC1`
was deleted from `gates.GATES`, its refusal was deleted from `promote_run`,
two test files asserted its absence, the connector deployed, and
`verify_deployed.py` reported every compiled module byte-identical to a local
build of HEAD.

`explain_gate("SG-AC1")` then answered from production with the full
definition and `on_failure: "block"`.

`gate_registry` is a TABLE, and `ensure_gate_registry` seeded it with
`INSERT … ON CONFLICT DO UPDATE`: it could create a gate and amend a gate and
could never retire one. Every passing check was reading the Python dict.
Nothing read the row.

    RULE_HELD_IN_TWO_PLACES_DRIFTS — with the second place in the database,
    and only the first place under test.

The lesson these tests encode is narrow and worth stating plainly: a test that
asserts `"SG-AC1" not in gates.GATES` proves the source changed. It says
nothing about what a producer is told, and what a producer is told was wrong
for the whole window. So the assertions below are about the SEEDER'S EFFECT
and the SHAPE `explain_gate` RETURNS, not about the dict.

Retirement rather than deletion is forced by the schema and is right anyway:
`gate_results` carries a foreign key onto `gate_registry(gate_id)`, and a gate
outcome recorded against a run is evidence about that run.
"""
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp import gates


class _Cur:
    """Records SQL rather than running it. The point is which statements the
    seeder issues; a live database is not needed to answer that, and a test
    that needed one would not run in CI where this has to be caught."""

    def __init__(self):
        self.sql = []
        self.rowcount = 0

    def execute(self, sql, params=None):
        self.sql.append((" ".join(sql.split()), params))

    def fetchone(self):
        return None


class _Conn:
    def __init__(self):
        self.cur = _Cur()
        self.commits = 0

    def cursor(self):
        return self.cur

    def commit(self):
        self.commits += 1


def _seed():
    conn = _Conn()
    gates.ensure_gate_registry(conn)
    return conn.cur.sql


# ── the seeder reconciles ─────────────────────────────────────────────
def test_THE_SEEDER_RETIRES_WHAT_THE_CODE_NO_LONGER_DEFINES():
    """The missing half. Without this the registry only ever grows, and every
    gate ever removed keeps answering as live."""
    retiring = [s for s, _ in _seed()
                if "UPDATE gate_registry" in s and "retired_at = COALESCE" in s]
    assert retiring, (
        "ensure_gate_registry only inserts and updates; nothing retires a gate "
        "that has left the code registry, so removing a gate leaves a row that "
        "explain_gate still reports as enforced")


def test_the_retirement_is_scoped_to_gates_absent_from_the_code():
    """It must retire what is gone and nothing else. A statement that retired
    unconditionally would take out every live gate on the next deploy — a far
    worse failure than the one being fixed."""
    stmt = next((s, p) for s, p in _seed()
                if "retired_at = COALESCE" in s)
    sql, params = stmt
    assert "NOT (gate_id = ANY(" in sql
    assert params and set(params[0]) == set(gates.GATES), (
        "the retirement predicate is not driven by the code registry")


def test_a_gate_that_comes_back_is_live_again():
    """`retired_at` is cleared for anything present in GATES, so restoring a
    gate needs no second migration and no manual row edit."""
    revive = [(s, p) for s, p in _seed()
              if "SET retired_at = NULL" in s]
    assert revive, "a gate restored to the code would stay marked retired"
    sql, params = revive[0]
    assert "gate_id = ANY(" in sql and set(params[0]) == set(gates.GATES)


def test_the_seeder_never_deletes_a_gate_row():
    """`gate_results` references gate_registry(gate_id). A DELETE would either
    fail on the constraint or, cascaded, destroy the record of which gates ran
    against a promoted run."""
    assert not any("DELETE" in s.upper() for s, _ in _seed())


# ── what a producer is actually told ──────────────────────────────────
def test_A_RETIRED_GATE_DOES_NOT_ANSWER_BLOCK():
    """The observable the whole defect lived in. `on_failure` is the one field
    a producer acts on, and a retired gate reporting `block` sends it to repair
    against a rule no code path can fire."""
    src = inspect.getsource(gates.explain_gate)
    assert 'out["on_failure"] = "retired"' in src
    assert 'retired_at' in src, "explain_gate does not read the retirement date"


def test_the_retired_definition_stays_readable():
    """Retention is the whole reason the row is not deleted: a verdict naming
    a since-retired gate has to remain explicable. So `explain_gate` must not
    start returning unknown_gate for it."""
    src = inspect.getsource(gates.explain_gate)
    branch_at = src.index('out["retired_at"] is not None')
    retired_branch = src[branch_at:]
    assert "unknown_gate" not in retired_branch
    # It must FALL THROUGH rather than early-return: everything after the
    # branch — most importantly the threshold history — has to still run for a
    # retired gate, or retention buys nothing over deletion.
    branch_body = retired_branch[:retired_branch.index("out.pop(")]
    assert "return" not in branch_body, (
        "the retired branch returns early, so a retired gate loses its "
        "threshold history — the exact thing keeping the row was meant to save")
    assert src.index("threshold_history") > branch_at, (
        "the threshold history is attached before the retirement branch runs")


def test_the_live_shape_carries_no_retirement_noise():
    """A live gate's answer should look exactly as it always did — no null
    `retired_at`, which reads as a field somebody forgot to fill in."""
    src = inspect.getsource(gates.explain_gate)
    assert 'out.pop("retired_at")' in src


def test_the_removed_ceiling_is_the_case_this_was_written_for():
    assert "SG-AC1" not in gates.GATES
