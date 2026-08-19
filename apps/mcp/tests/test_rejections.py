"""A refused payload gets a name, a queue and a way back.

THE HOLE. A submission that fails validation supersedes the passing row for
its page and then sits there. `get_run_progress` shows it, but only for one
run and only if somebody already knows to ask; nothing lists refusals across
the corpus, so a producer session that ends leaves no trace that anything is
outstanding.

Measured three times in one day on this build: a heatmap resubmit dropped
`cell_evidence`, failed CG-01 and superseded a PASS; an overview was refused
on ET-07 and again on ET-09. Every one was found by a person reading a
verdict. Nothing would have surfaced them otherwise, and the heatmap's 1.36 MB
of cell evidence was unreachable for a day because of it.

These tests pin the four properties that make the ledger worth having:
one ticket per distinct reason (not per attempt), closure by EVIDENCE rather
than assertion, the SG exception the charter grants, and a corpus-wide read
that does not require knowing the run.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))
from dma_mcp import rejections  # noqa: E402


def _reason(gate, path, sev="block", msg="because"):
    return {"gate_id": gate, "path": path, "severity": sev, "message": msg,
            "section": path.split(".")[0] if path else None}


# ── the pure filter, no database ───────────────────────────────────────

def test_a_safeguard_result_never_opens_a_ticket():
    """Invariant 12: a failing SG discloses and still promotes, so it is not
    an outstanding repair. A queue that carried them would never empty and a
    producer would learn to ignore it."""
    kept = rejections._blocking([
        _reason("SG-V4", "scores.framing"),
        _reason("CG-01", "cell_evidence"),
    ])
    assert [r["gate_id"] for r in kept] == ["CG-01"]


def test_a_warning_never_opens_a_ticket():
    kept = rejections._blocking([_reason("CG-13", "x", sev="warn")])
    assert kept == []


def test_the_key_is_the_gate_and_the_path():
    """Two different paths refused by one gate are two things to repair; the
    same gate on the same path twice is one thing, tried twice."""
    a = rejections._key(_reason("ET-09", "sentiment.bars[4].source"))
    b = rejections._key(_reason("ET-09", "sentiment.bars[5].source"))
    assert a != b
    assert a == rejections._key(_reason("ET-09", "sentiment.bars[4].source"))


def test_the_summary_names_a_looping_repair():
    """Three identical fixes for one gate is the loop this field exists to
    make visible: past two attempts, change approach rather than repeat."""
    s = rejections.summary([
        {"page": "overview", "attempts": 4, "gate_id": "ET-07"},
        {"page": "heatmap", "attempts": 1, "gate_id": "CG-01"},
    ])
    assert s["open"] == 2 and s["looping"] == 1
    assert s["pages"] == ["heatmap", "overview"]
    assert s["done"] is False
    assert rejections.summary([])["done"] is True


# ── against the migrated schema ────────────────────────────────────────

@pytest.fixture()
def db():
    try:
        import pg8000.dbapi
        conn = pg8000.dbapi.connect(host="localhost", port=5432, user="postgres",
                                    password="local", database="dma_insights")
    except Exception:
        pytest.skip("no migrated local database")
    cur = conn.cursor()
    eid, rid = uuid.uuid4(), uuid.uuid4()
    slug = f"rej-test-{eid.hex[:8]}"
    cur.execute("""INSERT INTO entities (id, display_id, legal_name, status)
                   VALUES (%s,%s,%s,'ACTIVE')""",
                (eid, slug, "Rejection Test Entity"))
    cur.execute("""INSERT INTO runs (id, entity_id, run_seq, status)
                   VALUES (%s,%s,1,'INGESTED')""", (rid, eid))
    conn.commit()
    yield conn, cur, rid, slug
    cur.execute("DELETE FROM rejection_ledger WHERE run_id = %s", (rid,))
    cur.execute("DELETE FROM runs WHERE id = %s", (rid,))
    cur.execute("DELETE FROM entities WHERE id = %s", (eid,))
    conn.commit()


def test_a_refusal_opens_one_ticket_per_reason(db):
    conn, cur, rid, slug = db
    out = rejections.record_verdict(conn, rid, "overview", None, [
        _reason("ET-07", "why_now.e_ids"),
        _reason("ET-09", "sentiment.bars[4].source"),
        _reason("SG-V4", "scores.framing"),
    ])
    conn.commit()
    assert len(out["opened"]) == 2, "the safeguard must not be queued"
    assert out["open_after"] == 2
    assert all(o["attempts"] == 1 for o in out["opened"])


def test_the_same_reason_twice_is_one_ticket_tried_twice(db):
    """The queue length must mean "distinct things wrong", never "times we
    tried" — otherwise a producer looping on one gate looks like a client
    with a dozen problems."""
    conn, cur, rid, slug = db
    r = [_reason("CG-01", "cell_evidence")]
    rejections.record_verdict(conn, rid, "heatmap", None, r); conn.commit()
    out = rejections.record_verdict(conn, rid, "heatmap", None, r); conn.commit()
    assert out["opened"] == []
    assert out["reopened_or_bumped"][0]["attempts"] == 2
    assert len(rejections.open_for_run(conn, rid)) == 1


def test_a_pass_closes_what_the_failure_opened(db):
    """Closure by EVIDENCE. Nothing asserts the repair worked; the gate not
    firing is what closes the row, and the submission that closed it is
    recorded so "which payload fixed it" stays answerable."""
    conn, cur, rid, slug = db
    rejections.record_verdict(conn, rid, "heatmap", None,
                              [_reason("CG-01", "cell_evidence")])
    conn.commit()
    assert len(rejections.open_for_run(conn, rid)) == 1
    out = rejections.record_verdict(conn, rid, "heatmap", None, [])
    conn.commit()
    assert len(out["closed"]) == 1
    assert rejections.open_for_run(conn, rid) == []


def test_a_partial_repair_closes_only_what_it_fixed(db):
    """The case that matters most: two reasons, one fixed. Closing both would
    report a client done over a defect still on the page."""
    conn, cur, rid, slug = db
    rejections.record_verdict(conn, rid, "overview", None, [
        _reason("ET-07", "why_now.e_ids"),
        _reason("ET-09", "sentiment.bars[4].source")])
    conn.commit()
    out = rejections.record_verdict(conn, rid, "overview", None,
                                    [_reason("ET-09", "sentiment.bars[4].source")])
    conn.commit()
    assert [c["gate_id"] for c in out["closed"]] == ["ET-07"]
    still = rejections.open_for_run(conn, rid)
    assert [s["gate_id"] for s in still] == ["ET-09"]
    assert still[0]["attempts"] == 2


def test_one_page_passing_does_not_close_another_page(db):
    conn, cur, rid, slug = db
    rejections.record_verdict(conn, rid, "overview", None,
                              [_reason("ET-07", "why_now.e_ids")])
    rejections.record_verdict(conn, rid, "heatmap", None,
                              [_reason("CG-01", "cell_evidence")])
    conn.commit()
    rejections.record_verdict(conn, rid, "heatmap", None, [])
    conn.commit()
    left = rejections.open_for_run(conn, rid)
    assert [(l["page"], l["gate_id"]) for l in left] == [("overview", "ET-07")]


def test_the_corpus_wide_read_needs_no_run_id(db):
    """The read that did not exist. A producer session must be able to ask
    "is anything outstanding" without already knowing which run to ask
    about — not knowing is exactly why refusals went unnoticed."""
    conn, cur, rid, slug = db
    rejections.record_verdict(conn, rid, "overview", None,
                              [_reason("ET-07", "why_now.e_ids")])
    conn.commit()
    rows = rejections.open_corpus_wide(conn)
    mine = [r for r in rows if str(r["run_id"]) == str(rid)]
    assert len(mine) == 1
    assert mine[0]["display_id"].startswith("rej-test-")
    assert mine[0]["gate_id"] == "ET-07"


def test_a_closed_ticket_is_retained_not_deleted(db):
    """A refusal is evidence about a run. The row stays; only its state
    changes."""
    conn, cur, rid, slug = db
    rejections.record_verdict(conn, rid, "heatmap", None,
                              [_reason("CG-01", "cell_evidence")])
    rejections.record_verdict(conn, rid, "heatmap", None, [])
    conn.commit()
    cur.execute("""SELECT count(*), count(closed_at)
                     FROM rejection_ledger WHERE run_id = %s""", (rid,))
    total, closed = cur.fetchone()
    assert (total, closed) == (1, 1)
