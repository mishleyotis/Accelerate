"""A package with no scored cell mints no run; a byte-identical retry mints none.

Measured 28-09-2026 (QA audit F-O13-030): goeasy-ltd held 18 runs under one
request id, 12 with `scored_cells = 0` and no catalogue version — every
rewrite of a research-stage workbook in the intake tree had new bytes,
passed the byte-identical guard and landed as a run. The refusal lives in
`persist_package`, before any write; the scan records it as a decided
outcome (no retry, no quarantine, no failed scan) and counts `runs_created`
from what was actually minted.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import job_main
from dma_worker import persist
from dma_worker.scan_diff import FileStat
from dma_worker.scan_runner import SCAN_SUCCEEDED
from dma_worker.workbook_parser import WorkbookParse


def _f(folder, name, checksum="abc"):
    return FileStat(file_id=f"{folder}/{name}", path_segments=(folder, name),
                    name=name, checksum=checksum, size_bytes=10, mime_type="")


TREE = [_f("goeasy - DMA", "run_manifest.json", "m1"),
        _f("goeasy - DMA", "DMA_Scoring_Workbook_goeasy.xlsx", "w1")]


class _NoWrites:
    """A connection that fails the test if anything asks it for a cursor."""
    def cursor(self):
        raise AssertionError("persist_package touched the database before refusing")

    def rollback(self):
        pass


def test_an_empty_workbook_is_refused_before_any_write():
    wb = WorkbookParse(scores=[], observations=[], toggled_out=[])
    with pytest.raises(persist.EmptyIngest) as exc:
        persist.persist_package(_NoWrites(), manifest={"run_id": "DMA-RES-GSY-20260830-0002"},
                                workbook=wb, source_folder_id="goeasy - DMA",
                                artefact_id="w1", artefact_checksum="abc")
    msg = str(exc.value)
    assert "0 scored cells" in msg and "DMA-RES-GSY-20260830-0002" in msg
    assert "goeasy - DMA" in msg and "F-O13-030" in msg


def test_remint_does_not_override_the_refusal():
    wb = WorkbookParse(scores=[], observations=[], toggled_out=[])
    with pytest.raises(persist.EmptyIngest):
        persist.persist_package(_NoWrites(), manifest={}, workbook=wb,
                                source_folder_id="x - DMA", remint=True)


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
    monkeypatch.setattr(job_main.drive, "walk_tree", lambda _i: tree)
    monkeypatch.setattr(job_main.drive, "metadata_token", lambda: "tok")
    monkeypatch.setattr(job_main, "_ingest_one", ingest)
    return job_main.main()


def test_the_scan_records_an_empty_ingest_as_decided_not_failed(monkeypatch, fakedb):
    """No run, no retry budget spent, no quarantine, the scan SUCCEEDS with
    the refusal named, and `runs_created` is 0."""
    def empty(conn, token, folder, parts, remint=False):
        raise persist.EmptyIngest(f"{folder}: the workbook carries 0 scored cells")
    requeued = []
    monkeypatch.setattr(job_main, "_requeue",
                        lambda *a, **k: requeued.append(a) or None)
    failures = []
    monkeypatch.setattr(job_main, "_record_package_failure",
                        lambda *a, **k: failures.append(a) or True)

    rc = _run_main(monkeypatch, fakedb, TREE, empty)

    assert rc == 0
    assert fakedb.scan["status"] == SCAN_SUCCEEDED
    assert fakedb.scan["runs_created"] == 0
    assert "1 package(s) refused: no scored cell" in (fakedb.scan["error"] or "")
    assert requeued == [] and failures == [], "a refusal is not a failure"


def test_a_resolved_retry_is_not_counted_as_a_created_run(monkeypatch, fakedb):
    """The byte-identical guard returns the run the package already produced;
    `runs_created` used to count it and the run was re-embedded every time."""
    res = persist.PersistResult("e", "run-1", 3, 706, 0, created=False)
    embedded = []
    monkeypatch.setenv("EMBED_MODEL_DIR", "/nonexistent")
    rc = _run_main(monkeypatch, fakedb, TREE,
                   lambda conn, token, folder, parts, remint=False: (res, {}),
                   EMBED_MODEL_DIR="/nonexistent")
    assert rc == 0
    assert fakedb.scan["status"] == SCAN_SUCCEEDED
    assert fakedb.scan["runs_created"] == 0
    assert embedded == []


def test_a_created_run_still_counts():
    assert persist.PersistResult("e", "r", 1, 10, 0).created is True
