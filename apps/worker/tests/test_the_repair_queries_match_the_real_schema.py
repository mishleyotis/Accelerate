"""Every repair pass's work list runs against the schema that ships.

MEASURED IN PRODUCTION, 2026-09-04T12:13:20Z. The scheduled evidence repair
asked for `evidence_index.run_id`. There is no such column — `evidence_index`
is keyed `e_id` and scoped `entity_id`; the run linkage lives one table over
in `evidence_subcap_links`. PostgreSQL answered `42703 column i.run_id does
not exist`, the caller's `except Exception` printed "evidence repair skipped
this firing", and then the SCAN died: a failed statement leaves the
transaction aborted, so `_scan_and_ingest`'s first SELECT came back `25P02
current transaction is aborted, commands ignored until end of transaction
block`. One wrong column name in a repair took down the job's whole reason
for existing.

Three hundred and ninety-six worker tests were green while that shipped,
because every one of them hands these functions a FAKE cursor that answers
any SQL it is given. A fake cursor cannot know a column does not exist.

So: run each work list against a real migrated database and let PostgreSQL
be the judge. Empty tables are fine — the point is that the statement parses
and binds, which is precisely what the fakes cannot test. Skips without one,
and CI has one (`.github/workflows/ci.yml`, the pgvector service).

Run with
`pytest apps/worker/tests/test_the_repair_queries_match_the_real_schema.py`.
"""
import os
import sys
from pathlib import Path

import pg8000.dbapi
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import job_main

DSN = os.environ.get("LOCAL_DATABASE_URL",
                     "postgresql://postgres:local@localhost:5432/dma_insights")


@pytest.fixture()
def worker_conn():
    host = DSN.split("@")[1].split(":")[0]
    try:
        conn = pg8000.dbapi.connect(
            user="dmai-worker@digital-maturity-assessor.iam",
            password="local", host=host, port=5432, database="dma_insights")
    except Exception:
        pytest.skip("no migrated local database")
    yield conn
    conn.rollback()
    conn.close()


def _still_usable(conn) -> bool:
    """Is the transaction still alive, or did that statement abort it?"""
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        return cur.fetchone() == [1] or cur.fetchone() == (1,)
    except Exception:
        return False


@pytest.mark.parametrize("forced", [False, True])
def test_the_evidence_repair_work_list_binds(worker_conn, forced):
    """The one that failed. `groups` is empty, so nothing is downloaded —
    only the work list runs, which is the half that was wrong."""
    job_main.backfill_evidence(worker_conn, "unused-token", {}, forced=forced)
    assert _still_usable(worker_conn), \
        "the evidence work list aborted the transaction; the scan that runs " \
        "after it will die 25P02"


@pytest.mark.parametrize("forced", [False, True])
def test_the_composite_repair_work_list_binds(worker_conn, forced):
    job_main.backfill_composite(worker_conn, "unused-token", {}, forced=forced)
    assert _still_usable(worker_conn)


def test_the_orphan_adoption_work_list_binds(worker_conn):
    job_main.adopt_orphan_runs(worker_conn, "unused-token", {})
    assert _still_usable(worker_conn)


def test_evidence_index_still_has_no_run_id(worker_conn):
    """The premise, pinned. If a migration ever adds `run_id` to
    `evidence_index` this test fails and someone re-reads the entity-scoped
    join above on purpose rather than by accident."""
    cur = worker_conn.cursor()
    cur.execute("""SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'evidence_index'""")
    cols = {r[0] for r in cur.fetchall()}
    assert "entity_id" in cols, "evidence_index lost the column the fill uses"
    assert "run_id" not in cols, \
        "evidence_index now carries run_id — the repair's entity-scoped " \
        "work list was written because it did not, and should be revisited"


# --------------------------------------------------------------------------
# not just the work list: the whole pass, against the real schema
# --------------------------------------------------------------------------

def test_the_whole_evidence_pass_runs_against_the_real_schema(worker_conn,
                                                              monkeypatch):
    """An empty work list proves the SELECT binds and nothing else. Seed one
    run with one URL-less citation and let the pass actually fill it, so the
    second-pass UPDATE and the observation INSERT are bound by PostgreSQL
    too — every statement the firing will issue, issued here first."""
    cur = worker_conn.cursor()
    cur.execute("""INSERT INTO entities (display_id, legal_name)
                   VALUES ('SCHEMA-PROBE','Schema Probe CU') RETURNING id""")
    entity_id = cur.fetchone()[0]
    cur.execute("""INSERT INTO runs (entity_id, request_id, run_seq,
                                     source_folder_id)
                   VALUES (%s,'REQ-SCHEMA-PROBE',1,'Schema Probe - DMA')
                RETURNING id""", (entity_id,))
    run_id = cur.fetchone()[0]
    cur.execute("""INSERT INTO evidence_index (e_id, entity_id, origin,
                                               source_name, source_url)
                   VALUES ('E-CC-991',%s,'package',
                           'A source [package evidence id E-001]', NULL)""",
                (entity_id,))
    worker_conn.commit()

    ledger = [{"e_id": "E-001", "source_name": "A source",
               "source_url": "https://example.test/a", "claim_type": "FACT",
               "excerpt": "Z" * 60}]
    monkeypatch.setattr(job_main.drive, "download", lambda t, fid: b"bytes")
    monkeypatch.setattr(job_main, "parse_evidence_master", lambda p: ledger)
    monkeypatch.setattr(job_main, "parse_scoring_workbook",
                        lambda p: type("W", (), {"scores": []})())
    monkeypatch.setattr(job_main, "mine_evidence_from_rationales",
                        lambda scores: {})

    from dma_worker.scan_diff import FileStat
    groups = job_main._package_groups([FileStat(
        file_id="wb", path_segments=("Schema Probe - DMA", "wb.xlsx"),
        name="DMA_Scoring_Workbook_probe.xlsx", checksum="c",
        size_bytes=10, mime_type="")])

    try:
        assert job_main.backfill_evidence(worker_conn, "tok", groups,
                                          forced=True) == 0
        assert _still_usable(worker_conn)
        cur = worker_conn.cursor()
        cur.execute("SELECT source_url FROM evidence_index WHERE e_id='E-CC-991'")
        assert cur.fetchone()[0] == "https://example.test/a", \
            "the row that named its workbook row did not get that row's URL"
        cur.execute("""SELECT count(*) FROM parser_observations
                        WHERE run_id = %s AND kind = 'evidence_reader_pass'""",
                    (run_id,))
        assert cur.fetchone()[0] == 1, "the pass was not recorded"
    finally:
        cur = worker_conn.cursor()
        cur.execute("DELETE FROM parser_observations WHERE run_id = %s", (run_id,))
        cur.execute("DELETE FROM evidence_index WHERE entity_id = %s", (entity_id,))
        cur.execute("DELETE FROM runs WHERE id = %s", (run_id,))
        cur.execute("DELETE FROM entities WHERE id = %s", (entity_id,))
        worker_conn.commit()
