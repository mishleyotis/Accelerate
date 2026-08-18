"""Stage 2.5/2.6 QA bullets — claim leases and run progress, against a
real database as the dmai-mcp parity user; skips without one."""
import os
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pg8000.dbapi

from dma_mcp.claims import claim_run, get_run_progress, release_claim

DSN = os.environ.get("LOCAL_DATABASE_URL", "postgresql://postgres:local@localhost:5432/dma_insights")
HOST = DSN.split("@")[1].split(":")[0] if "@" in DSN else "localhost"


def _connect(user):
    return pg8000.dbapi.connect(user=user, password="local", host=HOST,
                                port=5432, database="dma_insights")


@pytest.fixture()
def run_row():
    try:
        mcp = _connect("dmai-mcp@digital-maturity-assessor.iam")
        admin = _connect("dmai-migrate@digital-maturity-assessor.iam")
    except Exception:
        pytest.skip("no migrated local database")
    cur = admin.cursor()
    cur.execute("""INSERT INTO entities (display_id, status, created_at)
                   VALUES ('synthetic-claims-bank', 'ACTIVE', now()) RETURNING id""")
    eid = cur.fetchone()[0]
    cur.execute("""INSERT INTO runs (entity_id, request_id, run_seq, status)
                   VALUES (%s, 'DMA-ASM-SCB-20260801-01', 1, 'INGESTED')
                   RETURNING id""", (eid,))
    rid = cur.fetchone()[0]
    admin.commit()
    yield mcp, str(rid)
    mcp.rollback()
    cur.execute("DELETE FROM run_claims WHERE run_id = %s", (rid,))
    cur.execute("""DELETE FROM submission_verdicts WHERE submission_id IN
                     (SELECT id FROM submissions WHERE run_id = %s)""", (rid,))
    cur.execute("DELETE FROM submissions WHERE run_id = %s", (rid,))
    cur.execute("DELETE FROM runs WHERE id = %s", (rid,))
    cur.execute("DELETE FROM entities WHERE id = %s", (eid,))
    admin.commit()
    mcp.close()
    admin.close()


def test_lease_is_exclusive_renewable_and_recoverable(run_row):
    mcp, rid = run_row
    a = claim_run(mcp, rid, "session-a", "test@1")
    assert a["claimed"] is True
    # exclusivity: a live lease refuses a second session, with a hint
    b = claim_run(mcp, rid, "session-b", "test@1")
    assert b["claimed"] is False and b["held_by"] == "session-a"
    assert "get_run_progress" in b["hint"]
    # renewal by the holder extends, never refuses
    a2 = claim_run(mcp, rid, "session-a", "test@1")
    assert a2["claimed"] is True
    # a lapsed lease is taken over: expire it manually, then claim
    cur = mcp.cursor()
    cur.execute("""UPDATE run_claims SET expires_at = now() - interval '1 minute'
                    WHERE run_id = %s""", (rid,))
    mcp.commit()
    c = claim_run(mcp, rid, "session-b", "test@1")
    assert c["claimed"] is True and c["held_by"] == "session-b"
    assert release_claim(mcp, rid, "session-b")["released"] is True


def test_progress_names_what_blocks_and_never_guesses(run_row):
    mcp, rid = run_row
    p = get_run_progress(mcp, rid)
    assert p["promotable"] is False
    assert {b["page"] for b in p["blocking"]} == \
        {"heatmap", "overview", "insights", "platform", "context", "techstack"}
    assert all(p["pages"][pg]["status"] == "missing" for pg in p["pages"])

    # one failing page: its verdict reasons surface in blocking
    cur = mcp.cursor()
    cur.execute("""INSERT INTO submissions (run_id, page, payload, status,
                                            provenance, producer_version,
                                            submitted_by, submitted_at)
                   VALUES (%s,'overview','{}','FAIL','producer','test@1',
                           'svc_mcp', now()) RETURNING id""", (rid,))
    sid = cur.fetchone()[0]
    cur.execute("""INSERT INTO submission_verdicts
                     (submission_id, status, reasons, evaluated_at)
                   VALUES (%s,'FAIL',%s, now())""",
                (sid, '[{"gate_id":"CG-01","section":"scores","path":"scores.composite","message":"quoted 2.34 resolves to 2.10 (delta 0.24 > 0.05)","severity":"block"}]'))
    mcp.commit()
    p2 = get_run_progress(mcp, rid)
    over = [b for b in p2["blocking"] if b["page"] == "overview"][0]
    assert over["reasons"][0]["gate_id"] == "CG-01"
    assert p2["pages"]["overview"]["status"] == "FAIL"
    assert p2["promotable"] is False
