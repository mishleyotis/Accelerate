"""CG-22 — a safeguard gate_id a producer writes is a real gate.

Measured 2026-08-17, during an adversarial verification pass on three
already-staged runs: a heatmap payload carried safeguard_gates.gates[]
entries SG-E1, SG-E2, SG-Q1 and SG-D1, none of them ever registered in
gates.py or gate_registry, three rendering FAIL with an official-looking
plain_label. computed.safeguard_gates in apps/api only ever serves rows it
reads back from gate_results — a table only a real, machine-evaluated gate
writes to — so the fabricated entries never reached a client. But that safety
was accidental: they simply landed in a key nothing renders, not a rule the
producer could see, and the effort spent authoring convincing-looking FAIL
disclosures for gates that never ran was wasted.

Invariant 10 already forbids inventing an identifier outside five named
classes plus rec_id; a gate_id was never one of them, and nothing enforced
that until now.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.validation2 import _check_safeguard_gate_ids


class _Cur:
    def __init__(self, known_ids):
        self.known_ids = known_ids
        self.last_sql = None

    def execute(self, sql, params=None):
        self.last_sql = sql
        if "FROM gate_registry" not in sql:
            raise AssertionError("unmodelled statement:\n" + sql)
        wanted = set(params[0])
        self._out = [(gid,) for gid in wanted & self.known_ids]

    def fetchall(self):
        return self._out


class _Conn:
    def __init__(self, known_ids):
        self._cur = _Cur(known_ids)

    def cursor(self):
        return self._cur


def _gates_payload(gate_ids):
    return {"safeguard_gates": {
        "gates": [{"gate_id": g, "result": "FAIL",
                  "plain_label": "A disclosure about the run's evidence"}
                 for g in gate_ids]}}


def test_A_FABRICATED_GATE_ID_IS_BLOCKED():
    conn = _Conn(known_ids={"SG-S8", "SG-V4"})
    reasons = _check_safeguard_gate_ids(
        conn, "heatmap", _gates_payload(["SG-E1", "SG-S8"]))
    assert len(reasons) == 1
    r = reasons[0]
    assert r["gate_id"] == "CG-22"
    assert "SG-E1" in r["message"] and "caps[]" in r["message"]
    assert r["path"] == "safeguard_gates.gates[0].gate_id"


def test_ALL_FOUR_MEASURED_FABRICATIONS_ARE_CAUGHT():
    conn = _Conn(known_ids={"SG-S8", "SG-V4"})
    reasons = _check_safeguard_gate_ids(
        conn, "heatmap", _gates_payload(["SG-E1", "SG-E2", "SG-Q1", "SG-D1"]))
    assert {r["message"].split("'")[1] for r in reasons} == \
        {"SG-E1", "SG-E2", "SG-Q1", "SG-D1"}


def test_a_real_gate_is_never_flagged():
    conn = _Conn(known_ids={"SG-S8", "SG-V4"})
    reasons = _check_safeguard_gate_ids(
        conn, "heatmap", _gates_payload(["SG-S8", "SG-V4"]))
    assert reasons == []


def test_A_RETIRED_GATE_STILL_COUNTS_AS_REAL():
    """Retention (2026-08-16's fix) means a retired gate's row is retained in
    gate_registry, not deleted — its history stays explicable. A producer
    citing a retired gate by id must not be treated the same as one who
    invented an id that never existed."""
    conn = _Conn(known_ids={"SG-S8", "SG-V4", "SG-AC1"})  # SG-AC1: retired, still a row
    reasons = _check_safeguard_gate_ids(
        conn, "heatmap", _gates_payload(["SG-AC1"]))
    assert reasons == []


def test_the_check_is_scoped_to_heatmap_only():
    conn = _Conn(known_ids=set())
    assert _check_safeguard_gate_ids(
        conn, "overview", _gates_payload(["SG-FAKE"])) == []


def test_no_safeguard_gates_section_is_not_an_error():
    conn = _Conn(known_ids=set())
    assert _check_safeguard_gate_ids(conn, "heatmap", {}) == []
    assert _check_safeguard_gate_ids(
        conn, "heatmap", {"safeguard_gates": {}}) == []
    assert _check_safeguard_gate_ids(
        conn, "heatmap", {"safeguard_gates": {"gates": []}}) == []


def test_a_transient_db_error_does_not_block_the_promote():
    """The gate that cannot read its own registry must not silently wave a
    fabrication through, but it also must not fail a run on a blip — it says
    nothing, the same posture _check_foreign_entity_prose takes."""
    class _BrokenCur:
        def execute(self, *a, **k):
            raise RuntimeError("connection reset")

    class _BrokenConn:
        def cursor(self):
            return _BrokenCur()

    reasons = _check_safeguard_gate_ids(
        _BrokenConn(), "heatmap", _gates_payload(["SG-E1"]))
    assert reasons == []


def test_the_message_names_the_correct_home_for_the_content():
    """The point is not just refusal — it has to tell the producer where this
    kind of disclosure actually belongs."""
    conn = _Conn(known_ids=set())
    r = _check_safeguard_gate_ids(
        conn, "heatmap", _gates_payload(["SG-Q1"]))[0]
    assert "caps[]" in r["message"]
    assert "gates[]" in r["message"]


def test_THE_CHECK_IS_ACTUALLY_WIRED_INTO_VALIDATE_PASS2():
    """A check that exists but is never called is worse than no check: the
    unit tests above would all still pass. Pin the call site itself."""
    import inspect

    from dma_mcp import validation2

    src = inspect.getsource(validation2.validate_pass2)
    assert "_check_safeguard_gate_ids(conn, page, payload)" in src
