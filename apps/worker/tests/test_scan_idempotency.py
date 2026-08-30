"""Stage 1.1 verification bullets against a real database:

- Every file is recorded — including skipped ones, with the rule that
  skipped them.
- Re-running the scanner on an unchanged tree processes nothing new.

Runs as the dmai-worker parity user (the same grants as Cloud SQL) when
LOCAL_DATABASE_URL points at a migrated database; skips otherwise.
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pg8000.dbapi

from dma_worker.scan_diff import FileStat
from dma_worker.scan_runner import run_scan

DSN = os.environ.get("LOCAL_DATABASE_URL", "postgresql://postgres:local@localhost:5432/dma_insights")


@pytest.fixture()
def worker_conn():
    host = DSN.split("@")[1].split(":")[0]
    try:
        conn = pg8000.dbapi.connect(user="dmai-worker@digital-maturity-assessor.iam",
                                    password="local", host=host, port=5432,
                                    database="dma_insights")
    except Exception:
        pytest.skip("no migrated local database")
    cur = conn.cursor()
    cur.execute("DELETE FROM parser_observations")
    cur.execute("DELETE FROM import_files")
    cur.execute("DELETE FROM import_scans")
    conn.commit()
    yield conn
    conn.rollback()
    cur = conn.cursor()
    cur.execute("DELETE FROM parser_observations")
    cur.execute("DELETE FROM import_files")
    cur.execute("DELETE FROM import_scans")
    conn.commit()
    conn.close()


TREE = [
    FileStat("f1", ("Assessments", "AlmaBank", "AlmaBank_Scoring_Workbook.xlsx"),
             "AlmaBank_Scoring_Workbook.xlsx", "aaa1", 100),
    FileStat("f2", ("Assessments", "AlmaBank", "04_reports", "Assessment_Report_AlmaBank.docx"),
             "Assessment_Report_AlmaBank.docx", "bbb2", 200),
    FileStat("f3", ("Assessments", "TEST rehearsal", "workbook.xlsx"),
             "workbook.xlsx", "ccc3", 50),
    FileStat("f4", ("Assessments", "AlmaBank", "notes.txt"), "notes.txt", "ddd4", 10),
]
NOW = datetime(2026, 8, 4, 9, 0, tzinfo=timezone.utc)


def test_every_file_recorded_including_skipped_with_rule(worker_conn):
    s = run_scan(worker_conn, TREE, NOW)
    assert s["files_seen"] == 4 and s["files_new"] == 4
    cur = worker_conn.cursor()
    cur.execute("SELECT excluded, exclusion_rule FROM import_files WHERE artefact_id='f3'")
    excluded, rule = cur.fetchone()
    assert excluded is True and rule == "test_marker"
    # unrecognised file recorded with no kind, not dropped
    cur.execute("SELECT classified_kind FROM import_files WHERE artefact_id='f4'")
    assert cur.fetchone()[0] is None
    cur.execute("SELECT classified_kind, source_priority FROM import_files WHERE artefact_id='f1'")
    assert list(cur.fetchone()) == ["scoring_workbook", 1]


def test_rerunning_on_unchanged_tree_processes_nothing(worker_conn):
    run_scan(worker_conn, TREE, NOW)
    s2 = run_scan(worker_conn, TREE, NOW)
    assert s2["files_new"] == 0 and s2["files_changed"] == 0 and s2["to_process"] == []
    cur = worker_conn.cursor()
    cur.execute("SELECT count(*) FROM import_files")
    assert cur.fetchone()[0] == 4          # no duplicate rows
    cur.execute("SELECT files_new, files_changed, runs_created FROM import_scans ORDER BY id DESC LIMIT 1")
    assert list(cur.fetchone()) == [0, 0, 0]


def test_changed_checksum_is_detected_and_reprocessed(worker_conn):
    run_scan(worker_conn, TREE, NOW)
    changed = [FileStat("f1", TREE[0].path_segments, TREE[0].name, "NEW-CHECKSUM", 120)] + TREE[1:]
    s2 = run_scan(worker_conn, changed, NOW)
    assert s2["files_changed"] == 1 and s2["files_new"] == 0
    assert [f.file_id for f in s2["to_process"]] == ["f1"]
