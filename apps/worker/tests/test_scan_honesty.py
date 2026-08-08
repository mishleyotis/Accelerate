"""The scan ledger must describe the execution that happened.

Production, 2026-08-08: 150 rows in `import_scans`, every one of them
`status='succeeded'`, every one with `runs_created = 0` and
`finished_at = started_at` — while the Cloud Run Job exited 1 on all 140
of its scheduled firings and 130 runs existed in the database. The cause
was one line: `run_scan` wrote `succeeded` at the end of the DIFF, before
a single package had been downloaded, and nothing ever revised it. Two
real failure modes were invisible behind that:

    ValueError: unrecognised scoring workbook generation:
      tabs=['Scoring_Workbook', 'Calculation_Chain', 'Run_Metadata']
      — dma_worker/workbook_parser.py:149, via job_main.py _ingest_one

    urllib HTTPError inside drive.walk_tree — died before the scan row
      was even inserted, so those firings left no ledger row at all.

These tests pin the shape that makes both impossible to hide again.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import job_main
from dma_worker.scan_diff import FileStat
from dma_worker.scan_runner import (SCAN_FAILED, SCAN_RUNNING, SCAN_SUCCEEDED,
                                    EmptyTreeError, finish_scan, open_scan,
                                    run_scan)

NOW = datetime(2026, 8, 8, 6, 0, tzinfo=timezone.utc)


def _f(folder, name, checksum="abc"):
    return FileStat(file_id=f"{folder}/{name}", path_segments=(folder, name),
                    name=name, checksum=checksum, size_bytes=10, mime_type="")


TREE = [_f("Zions Bancorporation - DMA", "run_manifest.json", "m1"),
        _f("Zions Bancorporation - DMA", "DMA_Scoring_Workbook_Zions.xlsx", "w1"),
        _f("Zions Bancorporation - DMA", "DMA_Assessment_Report_Zions.docx", "r1")]


# --------------------------------------------------------------- run_scan

def test_run_scan_never_declares_success(fakedb):
    """The diff is not the traversal. run_scan records counts and leaves the
    row `running`; only finish_scan may write a terminal status."""
    summary = run_scan(fakedb, TREE, NOW)

    assert fakedb.scan["status"] == SCAN_RUNNING
    assert fakedb.closes == [], "run_scan closed the scan row"
    assert not any("'succeeded'" in s or "succeeded" in str(s)
                   for s in fakedb.statements if "UPDATE import_scans SET status" in s)
    assert summary["files_seen"] == 3 and summary["files_new"] == 3
    assert fakedb.scan["files_seen"] == 3


def test_finish_scan_is_the_only_writer_of_a_terminal_status(fakedb):
    scan_id = open_scan(fakedb, NOW)
    assert fakedb.scan["status"] == SCAN_RUNNING
    finish_scan(fakedb, scan_id, status=SCAN_SUCCEEDED, runs_created=2)
    assert fakedb.scan["status"] == SCAN_SUCCEEDED
    assert fakedb.scan["runs_created"] == 2
    assert fakedb.scan["finished_at"] is not None
    assert fakedb.scan["finished_at"] != fakedb.scan["started_at"], \
        "finished_at is when it finished, not when it started"


def test_a_failed_scan_must_name_its_reason(fakedb):
    scan_id = open_scan(fakedb, NOW)
    with pytest.raises(ValueError):
        finish_scan(fakedb, scan_id, status=SCAN_FAILED)          # no reason
    with pytest.raises(ValueError):
        finish_scan(fakedb, scan_id, status="running")            # not terminal
    finish_scan(fakedb, scan_id, status=SCAN_FAILED, error="boom")
    assert fakedb.scan["status"] == SCAN_FAILED
    assert fakedb.scan["error"] == "boom"


def test_zero_files_against_a_known_non_empty_tree_is_a_failure(fakedb):
    """A walk that returns nothing writes the same counters as a healthy scan
    of an empty tree. The last scan's artefacts are the only thing that tells
    them apart, so an empty walk on a known-non-empty tree refuses."""
    fakedb.files(*TREE)
    with pytest.raises(EmptyTreeError) as e:
        run_scan(fakedb, [], NOW)
    assert "known non-empty" in str(e.value)
    assert fakedb.scan["status"] == SCAN_RUNNING, "left open for the caller to fail"
    # and the prior artefacts are untouched — an empty walk deletes nothing
    assert {k: v["checksum"] for k, v in fakedb.import_files.items()} == \
        {f.file_id: f.checksum for f in TREE}


def test_an_empty_tree_with_no_history_is_still_a_clean_scan(fakedb):
    summary = run_scan(fakedb, [], NOW)
    assert summary["files_seen"] == 0
    assert fakedb.scan["status"] == SCAN_RUNNING


# ----------------------------------------------------------------- main()

def _run_main(monkeypatch, db, tree, ingest, **env):
    monkeypatch.setenv("INTAKE_FOLDER_ID", "intake-root")
    monkeypatch.setenv("MAX_PACKAGES", env.pop("MAX_PACKAGES", "10"))
    for k in ("DUMP_HEADERS", "LINK_PROPOSE_RUN_ID", "RESET_SCAN", "INTAKE_STATUS",
              "BACKFILL_SECTIONS", "BACKFILL_EVIDENCE", "EMBED_MODEL_DIR",
              "FORCE_FOLDER"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(job_main, "_connect", lambda: db)
    monkeypatch.setattr(job_main.drive, "walk_tree",
                        (lambda _i: tree) if not callable(tree) else tree)
    monkeypatch.setattr(job_main.drive, "metadata_token", lambda: "tok")
    monkeypatch.setattr(job_main, "_ingest_one", ingest)
    return job_main.main()


def test_a_package_that_raises_records_a_failed_scan(monkeypatch, fakedb):
    """The exact production shape: the tree walks, the diff commits, and the
    workbook parser raises. Before this change the row said `succeeded`."""
    def boom(conn, token, folder, parts):
        raise ValueError("unrecognised scoring workbook generation: "
                         "tabs=['Scoring_Workbook', 'Calculation_Chain', "
                         "'Run_Metadata']")

    rc = _run_main(monkeypatch, fakedb, TREE, boom)

    assert rc == 1
    assert fakedb.scan["status"] == SCAN_FAILED
    assert "1 package(s) failed to ingest" in fakedb.scan["error"]
    assert fakedb.scan["runs_created"] == 0
    assert fakedb.closes == [SCAN_FAILED], "closed exactly once, as failed"


def test_a_walk_that_dies_still_leaves_a_failed_row(monkeypatch, fakedb):
    """drive.walk_tree died on an HTTP error in production and the execution
    left NO import_scans row at all — 0 evidence of a firing. The row now
    opens before the walk, so the failure has somewhere to land."""
    def dead_walk(_intake):
        raise OSError("HTTP Error 403: insufficient permissions")

    rc = _run_main(monkeypatch, fakedb, dead_walk, lambda *a: None)

    assert rc == 1
    assert fakedb.import_scans, "the firing must be recorded even so"
    assert fakedb.scan["status"] == SCAN_FAILED
    assert "OSError" in fakedb.scan["error"] and "403" in fakedb.scan["error"]


def test_an_empty_walk_is_recorded_as_failed_not_succeeded(monkeypatch, fakedb):
    fakedb.files(*TREE)
    rc = _run_main(monkeypatch, fakedb, [], lambda *a: None)
    assert rc == 1
    assert fakedb.scan["status"] == SCAN_FAILED
    assert "EmptyTreeError" in fakedb.scan["error"]


def test_a_clean_pass_records_success_with_the_real_run_count(monkeypatch, fakedb):
    class _Res:
        run_id, scored_cells, observations = "run-1", 706, 3

    rc = _run_main(monkeypatch, fakedb, TREE,
                   lambda conn, token, folder, parts: (_Res(), {}))

    assert rc == 0
    assert fakedb.scan["status"] == SCAN_SUCCEEDED
    assert fakedb.scan["error"] is None
    assert fakedb.scan["runs_created"] == 1, \
        "runs_created was hardcoded 0 in the INSERT and never revised"


def test_an_unchanged_tree_succeeds_and_creates_nothing(monkeypatch, fakedb):
    fakedb.files(*TREE)
    rc = _run_main(monkeypatch, fakedb, TREE,
                   lambda *a: pytest.fail("nothing should ingest"))
    assert rc == 0
    assert fakedb.scan["status"] == SCAN_SUCCEEDED
    assert fakedb.scan["runs_created"] == 0


# ------------------------------------------------------------- quarantine

def test_a_package_retries_then_quarantines_instead_of_churning(monkeypatch, fakedb):
    """140 firings blanked the same three checksums and re-attempted the same
    ValueError. Three attempts, then the package is named and left alone."""
    def boom(conn, token, folder, parts):
        raise ValueError("unrecognised scoring workbook generation")

    monkeypatch.setattr(job_main, "MAX_INGEST_ATTEMPTS", 3)
    outcomes, rows = [], []
    for _ in range(4):                       # the tree itself never changes
        _run_main(monkeypatch, fakedb, TREE, boom)
        outcomes.append(fakedb.import_files[TREE[1].file_id]["checksum"])
        rows.append(dict(fakedb.scan))

    # attempts 1 and 2 requeue (checksum blanked); attempt 3 quarantines
    assert outcomes[:2] == ["", ""]
    assert outcomes[2] == TREE[1].checksum, "quarantined packages are not requeued"
    assert "quarantined: Zions Bancorporation - DMA" in rows[2]["error"]
    assert [r["status"] for r in rows] == [SCAN_FAILED, SCAN_FAILED,
                                           SCAN_FAILED, SCAN_SUCCEEDED], \
        "the firing after a quarantine is genuinely clean — it attempts nothing"
    kinds = [o["detail"] for o in fakedb.observations]
    assert [d["attempt"] for d in kinds][:3] == [1, 2, 3]
    assert kinds[2]["quarantined"] is True
    assert kinds[0]["quarantined"] is False


def test_a_re_uploaded_workbook_starts_the_retry_budget_over(monkeypatch, fakedb):
    def boom(conn, token, folder, parts):
        raise ValueError("unrecognised scoring workbook generation")

    monkeypatch.setattr(job_main, "MAX_INGEST_ATTEMPTS", 2)
    _run_main(monkeypatch, fakedb, TREE, boom)          # attempt 1, requeued
    _run_main(monkeypatch, fakedb, TREE, boom)          # attempt 2, quarantined
    assert fakedb.observations[-1]["detail"]["quarantined"] is True

    fixed = [TREE[0], _f("Zions Bancorporation - DMA",
                         "DMA_Scoring_Workbook_Zions.xlsx", "w2-NEW"), TREE[2]]
    assert job_main._prior_attempts(fakedb, fixed[1].file_id, "w2-NEW") == 0, \
        "a different upload is a different package"
