"""Recall arrives with the refusal that earned it.

THE HOLE, measured 2026-08-19. The findings memory has held defect classes,
their measurements and the refinements that closed them since migration 0034,
and the surface-production skill named none of its tools on any of its 40
pages. So the store was written by the rectifier and read by nobody at
production time: every run began from zero, and the same defect classes were
rediscovered by a person looking at a rendered page — four rounds running.

A memory a producer has to REMEMBER to consult is a memory nobody consults.
This is the same fix the rejection ledger made: attach it to the refusal, on
the submit that earned it, so it cannot be skipped by forgetting.

These cases pin the three properties that make it worth returning: it answers
by GATE, it carries the change that closed the finding last time, and it says
which gates it asked about so "nothing known" is distinguishable from "never
asked".
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))
from dma_mcp import memory  # noqa: E402


# ── no database needed ─────────────────────────────────────────────────

def test_a_verdict_with_no_gates_says_so_rather_than_answering_emptily():
    out = memory.recall_for_gates(None, [])
    assert out["known"] == {} and out["checked"] == []
    assert "no gate ids" in out["note"]


def test_the_submit_path_returns_recall_and_cannot_be_broken_by_it():
    """Wiring asserted rather than trusted: the failure mode of a recall
    nobody wired is SILENT — every submit keeps working and the producer
    simply never learns anything."""
    src = (ROOT / "apps" / "mcp" / "dma_mcp" / "submit.py").read_text()
    assert "recall_for_gates" in src, \
        "submit no longer asks the memory what it knows about these gates"
    assert '"memory": memory_recall' in src, \
        "the recall is computed and then not returned, which is the same as " \
        "not computing it"
    i = src.index("recall_for_gates")
    assert "try:" in src[max(0, i - 400):i], \
        "the recall is not guarded — a memory that can break a submit is " \
        "worse than a memory that is silent"


# ── against the migrated local database ────────────────────────────────

@pytest.fixture()
def db():
    try:
        import pg8000.dbapi
        conn = pg8000.dbapi.connect(host="localhost", port=5432, user="postgres",
                                    password="local", database="dma_insights")
    except Exception:
        pytest.skip("no migrated local database")
    tag = uuid.uuid4().hex[:8]
    yield conn, tag
    cur = conn.cursor()
    cur.execute("DELETE FROM memory_refinement_findings WHERE finding_id IN "
                "(SELECT finding_id FROM memory_findings WHERE title LIKE %s)",
                (f"%{tag}%",))
    cur.execute("DELETE FROM memory_finding_sightings WHERE finding_id IN "
                "(SELECT finding_id FROM memory_findings WHERE title LIKE %s)",
                (f"%{tag}%",))
    cur.execute("DELETE FROM memory_findings WHERE title LIKE %s", (f"%{tag}%",))
    cur.execute("DELETE FROM memory_refinements WHERE change LIKE %s", (f"%{tag}%",))
    conn.commit()
    conn.close()


def _finding(conn, tag, gate):
    return memory.record_finding(conn, {
        "title": f"A cell drawer showed a citation with no quote [{tag}]",
        "observed": "eight linked rows, none carrying a verbatim span",
        "measurement": "counted excerpt-less rows in the served listing",
        "measured_value": "36 of 104",
        "component": "mcp",
        "gate_id": gate,
        # The class this very defect belongs to: the store was written by the
        # rectifier and read by nobody at production time.
        "defect_class": "WRITE_PATH_WITH_NO_READ_PATH",
        "severity": "MAJOR",
        "raised_by_kind": "USER",
        "raised_by": "owner",
    })


def test_a_gate_with_a_finding_comes_back_with_it(db):
    conn, tag = db
    gate = f"CG-{tag[:4]}"
    rec = _finding(conn, tag, gate)
    assert rec.get("finding_id"), rec
    out = memory.recall_for_gates(conn, [gate])
    assert out["checked"] == [gate]
    assert [f["finding_id"] for f in out["known"][gate]] == [rec["finding_id"]]
    assert out["known"][gate][0]["times_seen"] >= 1


def test_the_recall_carries_the_change_that_closed_it_last_time(db):
    """The reason this is worth returning at all: a producer reading "the fix
    last time was X" repairs in one pass instead of rediscovering the shape of
    the refusal."""
    conn, tag = db
    gate = f"CG-{tag[:4]}"
    rec = _finding(conn, tag, gate)
    ref = memory.record_refinement(conn, {
        "target_kind": "SKILL",
        "target": "skill:dma-surface-production",
        "change": f"spelled the source label out at the projection [{tag}]",
        "rationale": "the ingested tier is read-only once scanned",
        "change_ref": "session-test",
        "gate_added": "CG-27",
        "verification": "test_a_source_label_is_not_a_verbatim_span",
        "applied_by": "test",
        "finding_ids": [rec["finding_id"]],
    })
    assert ref.get("refinement_id"), ref
    hit = memory.recall_for_gates(conn, [gate])["known"][gate][0]
    assert tag in (hit["last_refinement"] or "")
    assert hit["gate_added_then"] == "CG-27"


def test_a_gate_this_store_has_never_seen_is_checked_and_empty(db):
    conn, tag = db
    out = memory.recall_for_gates(conn, ["CG-NOSUCH"])
    assert out["checked"] == ["CG-NOSUCH"]
    assert out["known"] == {}, \
        "an unknown gate must answer empty, never invent a neighbour's finding"


def test_duplicate_gate_ids_are_asked_once(db):
    conn, tag = db
    gate = f"CG-{tag[:4]}"
    _finding(conn, tag, gate)
    out = memory.recall_for_gates(conn, [gate, gate, gate, None, ""])
    assert out["checked"] == [gate]
