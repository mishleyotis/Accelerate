"""An interrupted upload can be inspected and resumed, not only abandoned.

WHAT IT COST. Measured 2026-08-31, a producer pushing a 1.5 MB heatmap:

    "two of my earlier attempts got a stale part-count stuck on the upload
     from an interrupted run, so I had to re-open clean uploads"

Two gaps behind that, both in this module.

1. NOTHING COULD READ AN UPLOAD. The only way to learn which parts had landed
   was to APPEND another part and read the counters off the reply. A producer
   resuming after an interruption was blind: it could not see what it already
   had, could not find the upload it had opened, and its only safe move was to
   open a new one and resend everything. The index that makes finding it cheap
   — `payload_uploads_run_page (run_id, page, opened_at DESC)` — has existed
   since the table was created, with no query anywhere that used it.

2. `parts_total` FROZE ON THE FIRST PART, for the upload's life. That freeze
   is what makes an incomplete transmission detectable and it stays. What was
   missing was a way THROUGH it: the refusal said "Open a new upload if the
   plan changed", and a producer that took the advice discarded every part it
   had already sent.

The fixes keep the atomicity guarantee whole — a part is still inert, submit
still demands exactly {1..parts_total}, nothing partial can be staged.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))

from dma_mcp import transport                                 # noqa: E402


@pytest.fixture()
def db():
    try:
        import pg8000.dbapi
        conn = pg8000.dbapi.connect(host="localhost", port=5432,
                                    user="postgres", password="local",
                                    database="dma_insights")
    except Exception:
        pytest.skip("no migrated local database")
    cur = conn.cursor()
    cur.execute("INSERT INTO entities (display_id, legal_name) "
                "VALUES (%s,%s) RETURNING id",
                (f"upl-{uuid.uuid4().hex[:10]}", "Upload Fixture"))
    entity_id = cur.fetchone()[0]
    cur.execute("INSERT INTO runs (entity_id, request_id, run_seq, status) "
                "VALUES (%s,%s,1,'INGESTED') RETURNING id",
                (entity_id, f"REQ-{uuid.uuid4().hex[:8]}"))
    run_id = cur.fetchone()[0]
    conn.commit()
    yield conn, run_id
    conn.rollback()
    cur.execute("DELETE FROM payload_upload_parts WHERE upload_id IN "
                "(SELECT id FROM payload_uploads WHERE run_id = %s)", (run_id,))
    cur.execute("DELETE FROM payload_uploads WHERE run_id = %s", (run_id,))
    cur.execute("DELETE FROM runs WHERE id = %s", (run_id,))
    cur.execute("DELETE FROM entities WHERE id = %s", (entity_id,))
    conn.commit()
    conn.close()


def _open(conn, run_id):
    r = transport.open_payload(conn, run_id, "heatmap")
    assert r["ok"], r
    return r["upload_id"]


def _part(conn, up, part, total, **kw):
    kw.setdefault("path", "")
    kw.setdefault("fields", {f"s{part}": {"n": part}})
    return transport.append_payload_part(conn, up, part, total, **kw)


# ── reading an upload without writing to it ──────────────────────────────

def test_an_interrupted_upload_says_what_it_still_needs(db):
    """THE DEFECT. 30 of 53 parts landed and the run died."""
    conn, run_id = db
    up = _open(conn, run_id)
    for i in (1, 2, 3, 5):
        _part(conn, up, i, 53)

    st = transport.upload_status(conn, upload_id=up)
    assert st["ok"], st
    one = st["uploads"][0]
    assert one["parts_total"] == 53
    assert one["parts_received"] == 4
    assert 4 in one["missing_parts"] and 53 in one["missing_parts"]
    assert one["complete"] is False
    assert {p["part"] for p in one["parts"]} == {1, 2, 3, 5}


def test_a_resumed_session_can_find_the_upload_it_opened(db):
    """Without this it opens a new one and resends everything — which is
    exactly the churn reported."""
    conn, run_id = db
    up = _open(conn, run_id)
    _part(conn, up, 1, 4)
    st = transport.upload_status(conn, run_id=run_id, page="heatmap")
    assert [u["upload_id"] for u in st["uploads"]] == [up]


def test_reading_an_upload_writes_nothing(db):
    """It is a status call, not a probe that changes what it measures."""
    conn, run_id = db
    up = _open(conn, run_id)
    _part(conn, up, 1, 3)
    before = transport.upload_status(conn, upload_id=up)["uploads"][0]
    for _ in range(3):
        transport.upload_status(conn, upload_id=up)
    after = transport.upload_status(conn, upload_id=up)["uploads"][0]
    assert before == after


def test_an_unknown_upload_says_so_rather_than_returning_empty(db):
    conn, _ = db
    out = transport.upload_status(conn, upload_id=str(uuid.uuid4()))
    assert out["ok"] is False and out["error"] == "unknown_upload"


def test_the_guidance_names_resuming_before_restarting(db):
    """A producer reads this at its worst moment. It has to say 'resend the
    missing parts' before it says anything about starting over."""
    conn, run_id = db
    up = _open(conn, run_id)
    how = transport.upload_status(conn, upload_id=up)["how"]
    assert "missing_parts" in how
    assert how.index("Resume") < how.index("repartition")


# ── the frozen parts_total, and the way through it ───────────────────────

def test_a_changed_plan_is_still_refused_by_default(db):
    """The property that makes an incomplete transmission detectable does not
    get weaker: two plans never merge silently."""
    conn, run_id = db
    up = _open(conn, run_id)
    _part(conn, up, 1, 53)
    r = _part(conn, up, 2, 51)
    assert r["ok"] is False and r["error"] == "parts_total_disagreement"


def test_the_refusal_names_both_ways_out(db):
    """It used to name only 'open a new upload', which discards everything
    already sent. Resuming is the cheaper answer and comes first."""
    conn, run_id = db
    up = _open(conn, run_id)
    _part(conn, up, 1, 53)
    msg = _part(conn, up, 2, 51)["message"]
    assert "get_upload_status" in msg
    assert "parts_total=53" in msg
    assert "repartition=true" in msg


def test_repartition_adopts_the_new_plan_and_says_what_it_discarded(db):
    conn, run_id = db
    up = _open(conn, run_id)
    for i in (1, 2, 3):
        _part(conn, up, i, 53)
    r = _part(conn, up, 1, 51, repartition=True)
    assert r["ok"], r
    assert r["repartitioned_away"] == 3, (
        "a discard nobody is told about is indistinguishable from parts that "
        "never arrived")
    assert r["parts_total"] == 51
    assert r["parts_received"] == 1


def test_repartition_belongs_on_part_one(db):
    """Sent later it would delete the parts of the NEW plan that had already
    arrived — a footgun pointing at the work it is meant to save."""
    conn, run_id = db
    up = _open(conn, run_id)
    _part(conn, up, 1, 53)
    r = _part(conn, up, 7, 51, repartition=True)
    assert r["ok"] is False and r["error"] == "repartition_not_at_start"


def test_after_repartition_the_old_parts_cannot_assemble(db):
    """The whole point: the new declared length has to be honest about what
    is actually held."""
    conn, run_id = db
    up = _open(conn, run_id)
    for i in (1, 2, 3):
        _part(conn, up, i, 3)
    _part(conn, up, 1, 2, repartition=True)
    st = transport.upload_status(conn, upload_id=up)["uploads"][0]
    assert st["parts_total"] == 2
    assert st["parts_received"] == 1
    assert st["missing_parts"] == [2]


def test_resuming_the_same_plan_needs_no_repartition(db):
    """The common case stays plain: same total, resend what is missing."""
    conn, run_id = db
    up = _open(conn, run_id)
    _part(conn, up, 1, 3)
    _part(conn, up, 3, 3)
    r = _part(conn, up, 2, 3)
    assert r["ok"] and r["complete"] is True
    assert r["repartitioned_away"] == 0
