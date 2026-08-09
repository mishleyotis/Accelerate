"""withdraw_run (0042) — and the negative control that the old lever fails.

The defect this exists for is not "there was no way to stop serving a run".
There was one: `UPDATE runs SET is_active = FALSE`. The defect is that it
does not work, and looks like it does. `serving_directory` selects on
`promoted_at IS NOT NULL`, so a demoted run stays in the view, and
`/v1/directory` — which reads nothing else — keeps publishing the client's
name, slug, sub-vertical and a run row, while every page beneath it 404s.

So the first test here is the NEGATIVE CONTROL, and it asserts the BUG:
after the old lever, the entity is still listed. If that test ever starts
failing, the old mechanism has changed and the rest of this file is
measuring something else. Every other test then asserts the state the
lever was supposed to produce.

This is the shape the plan's stress test demanded of every fix: a check
that passes on the repaired state and demonstrably fails on the state that
produced the defect. Here they are the same run of pytest.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pg8000.dbapi

from dma_mcp.withdraw import withdraw_run, list_withdrawn

DSN = os.environ.get("LOCAL_DATABASE_URL",
                     "postgresql://postgres:local@localhost:5432/dma_insights")
HOST = DSN.split("@")[1].split(":")[0] if "@" in DSN else "localhost"

DISPLAY = "synthetic-withdrawal-dealer"
REASON = ("Fifty-two cells at or above 4.0 rest on a filing for a "
          "subsidiary 175 times smaller than the assessed entity.")


def _connect(user):
    return pg8000.dbapi.connect(user=user, password="local", host=HOST,
                                port=5432, database="dma_insights")


@pytest.fixture()
def seeded():
    admin = _connect("postgres")
    cur = admin.cursor()

    def clean():
        cur.execute("SELECT id FROM entities WHERE display_id = %s", (DISPLAY,))
        for (eid,) in cur.fetchall():
            cur.execute("SELECT id FROM runs WHERE entity_id = %s", (eid,))
            for (rid,) in cur.fetchall():
                cur.execute("DELETE FROM heatmap_alerts WHERE run_id = %s", (rid,))
            cur.execute("DELETE FROM runs WHERE entity_id = %s", (eid,))
            cur.execute("DELETE FROM entities WHERE id = %s", (eid,))
        admin.commit()

    clean()
    cur.execute("""INSERT INTO entities (display_id, legal_name, sub_vertical,
                                         status, created_at)
                   VALUES (%s, 'Synthetic Withdrawal Dealer Limited',
                           'WEALTH_RIAS', 'ACTIVE', now()) RETURNING id""",
                (DISPLAY,))
    eid = cur.fetchone()[0]
    # Promoted by hand rather than through promote_run: this file is about
    # what the DIRECTORY does with a promoted run, and a real promote would
    # drag 34 writers into a test about one predicate.
    cur.execute("""INSERT INTO runs (entity_id, request_id, run_seq, status,
                                     is_active, promoted_at, composite)
                   VALUES (%s, 'DMA-ASM-SWD-20260809-01', 1, 'PROMOTED',
                           TRUE, now(), 2.76) RETURNING id""", (eid,))
    rid = str(cur.fetchone()[0])
    cur.execute("""INSERT INTO heatmap_alerts
                     (run_id, entity_id, subcap_id, score, evidence_count,
                      state, severity, status, justification,
                      promoted_at, producer_version)
                   VALUES (%s, %s, 'P3C3.4.RIA1', 4.2, 0, 'thin', 'MEDIUM',
                           'open', 'Top-band cell with no citable evidence',
                           now(), 'test@1')""", (rid, eid))
    admin.commit()
    cur.execute("SELECT refresh_serving_directory()")
    admin.commit()
    yield admin, cur, rid, eid
    clean()
    admin.close()


def _listed(cur, display_id=DISPLAY) -> int:
    """Rows the DIRECTORY would publish for this entity. /v1/directory reads
    serving_directory and nothing else, so this count IS whether the client
    appears on the front page."""
    cur.execute("SELECT count(*) FROM serving_directory WHERE display_id = %s",
                (display_id,))
    return cur.fetchone()[0]


def test_negative_control_the_old_lever_leaves_the_client_listed(seeded):
    """THE BUG, asserted. `is_active = FALSE` was the only suppression this
    build had, and it suppresses nothing a reader can see: the run keeps its
    row in the one view the API reads, so the directory keeps the client's
    name, sub-vertical and run history on screen. Pages 404 underneath. One
    client and one named ghost."""
    admin, cur, rid, _ = seeded
    assert _listed(cur) == 1

    cur.execute("""UPDATE runs SET is_active = FALSE, status = 'SUPERSEDED'
                    WHERE id = %s""", (rid,))
    admin.commit()
    cur.execute("SELECT refresh_serving_directory()")
    admin.commit()

    assert _listed(cur) == 1, (
        "the old lever now removes the run from serving_directory — if this "
        "fails, the mechanism changed and every other test in this file is "
        "measuring the wrong thing")
    cur.execute("""SELECT legal_name, sub_vertical, run_status
                     FROM serving_directory WHERE display_id = %s""", (DISPLAY,))
    name, sub_vertical, status = cur.fetchone()
    assert name == "Synthetic Withdrawal Dealer Limited"
    assert sub_vertical == "WEALTH_RIAS"
    assert status == "SUPERSEDED"


def test_withdrawal_removes_the_entity_from_the_directory(seeded):
    admin, cur, rid, _ = seeded
    out = withdraw_run(admin, rid, REASON, "agent:build-session-b6f97535")

    assert out["withdrawn"] is True and out["already"] is False
    assert out["entity_still_listed"] is False
    assert out["remaining_promoted_runs"] == 0
    assert _listed(cur) == 0, "the client is still on the directory"


def test_the_reason_is_required_and_recorded_on_the_run(seeded):
    admin, cur, rid, _ = seeded
    short = withdraw_run(admin, rid, "wrong", "agent:test")
    assert short["withdrawn"] is False and short["error"] == "reason_required"
    assert _listed(cur) == 1, "a refused withdrawal must not withdraw"

    assert withdraw_run(admin, rid, REASON, "")["error"] == "actor_required"

    withdraw_run(admin, rid, REASON, "agent:test")
    cur.execute("""SELECT withdrawn_reason, withdrawn_by, withdrawn_at
                     FROM runs WHERE id = %s""", (rid,))
    reason, by, at = cur.fetchone()
    assert reason == REASON and by == "agent:test" and at is not None

    rows = list_withdrawn(admin)["withdrawn"]
    assert [r["display_id"] for r in rows if r["run_id"] == rid] == [DISPLAY]


def test_withdrawing_twice_keeps_the_first_reason(seeded):
    """A retry after a network failure must not overwrite a considered reason
    with whatever the second caller happened to type."""
    admin, cur, rid, _ = seeded
    withdraw_run(admin, rid, REASON, "agent:first")
    again = withdraw_run(admin, rid,
                         "A second and much vaguer reason, thirty plus chars.",
                         "agent:second")
    assert again["withdrawn"] is True and again["already"] is True
    assert again["reason"] == REASON and again["withdrawn_by"] == "agent:first"


def test_alerts_are_left_alone_and_leave_the_queue_with_the_run(seeded):
    """`heatmap_alerts.status` is open · resolved · waived, and all three are
    statements about the FINDING. Writing `waived` here would fabricate a
    human decision that belongs in alert_actions with a name on it. So the
    rows are untouched, and they disappear from the queue because the queue
    joins the view."""
    admin, cur, rid, _ = seeded
    cur.execute("SELECT count(*) FROM heatmap_alerts WHERE run_id = %s", (rid,))
    before = cur.fetchone()[0]
    assert before == 1

    withdraw_run(admin, rid, REASON, "agent:test")

    cur.execute("""SELECT count(*) FROM heatmap_alerts
                    WHERE run_id = %s AND status = 'open'""", (rid,))
    assert cur.fetchone()[0] == before, "withdrawal rewrote an alert's status"

    # The queue's own join (apps/api/dma_api/alerts.py): the alert is gone
    # from what a reader sees without anything having been un-done.
    cur.execute("""SELECT count(*) FROM heatmap_alerts a
                     JOIN serving_directory d
                       ON d.run_id = a.run_id AND d.is_active""")
    assert cur.fetchone()[0] == 0


def test_a_run_that_never_promoted_cannot_be_withdrawn(seeded):
    admin, cur, _, eid = seeded
    cur.execute("""INSERT INTO runs (entity_id, request_id, run_seq, status)
                   VALUES (%s, 'DMA-ASM-SWD-20260809-02', 2, 'INGESTED')
                RETURNING id""", (eid,))
    unpromoted = str(cur.fetchone()[0])
    admin.commit()
    out = withdraw_run(admin, unpromoted, REASON, "agent:test")
    assert out["withdrawn"] is False and out["error"] == "not_promoted"


def test_a_second_promoted_run_keeps_the_entity_listed(seeded):
    """Withdrawal is per RUN. An entity with another promoted run stays on the
    directory, and the caller is told so rather than left to assume."""
    admin, cur, rid, eid = seeded
    cur.execute("""INSERT INTO runs (entity_id, request_id, run_seq, status,
                                     is_active, promoted_at, composite)
                   VALUES (%s, 'DMA-ASM-SWD-20260809-03', 3, 'PROMOTED',
                           FALSE, now(), 2.40)""", (eid,))
    admin.commit()
    out = withdraw_run(admin, rid, REASON, "agent:test")
    assert out["entity_still_listed"] is True
    assert out["remaining_promoted_runs"] == 1
    assert _listed(cur) == 1
