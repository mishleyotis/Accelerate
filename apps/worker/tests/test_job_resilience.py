"""The package scan must drain the whole intake tree across firings —
one bad package sinks nothing and retries later (prod regression: the
first execution recorded all 8,041 files as seen, so any package it did
not process this time would never have retried).

- _package_groups keeps partial groups (manifest before workbook) so the
  caller can requeue them instead of dropping them.
- _requeue blanks stored checksums; the next scan's diff then classifies
  those artefacts as CHANGED, closing the retry loop.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_worker.scan_diff import FileStat, diff_tree
from job_main import _package_groups, _requeue


def _f(folder, name, fid=None, checksum="abc"):
    return FileStat(file_id=fid or f"{folder}/{name}",
                    path_segments=(folder, name), name=name,
                    checksum=checksum, size_bytes=10, mime_type="")


class _Cursor:
    def __init__(self, store):
        self.store = store
        self.rowcount = 0

    def execute(self, sql, params=None):
        assert "UPDATE import_files SET checksum = ''" in sql
        (fid,) = params
        if fid in self.store:
            self.store[fid] = ""
            self.rowcount = 1


class _Conn:
    def __init__(self, store):
        self.store = store
        self.commits = 0

    def cursor(self):
        return _Cursor(self.store)

    def commit(self):
        self.commits += 1


def test_package_groups_keep_partial_packages():
    files = [
        _f("Complete Client - DMA", "run_manifest.json"),
        _f("Complete Client - DMA", "Complete Client Scoring Workbook.xlsx"),
        _f("Complete Client - DMA", "Report.docx"),
        _f("Early Client - DMA", "run_manifest.json"),   # workbook not uploaded yet
        _f("Noise Folder", "notes.txt"),
    ]
    groups = _package_groups(files)
    complete = {k: v for k, v in groups.items() if "manifest" in v and "workbook" in v}
    partial = {k: v for k, v in groups.items() if k not in complete
               and any(a in v for a in ("manifest", "workbook", "report"))}
    assert set(complete) == {"Complete Client - DMA"}
    assert set(partial) == {"Early Client - DMA"}
    assert "Noise Folder" in groups and "Noise Folder" not in partial


def test_requeue_makes_the_next_scan_retry_the_package():
    parts = {
        "manifest": _f("Failing Client - DMA", "run_manifest.json"),
        "workbook": _f("Failing Client - DMA", "Failing Client Scoring Workbook.xlsx"),
        "folder": "Failing Client - DMA",
    }
    # Prior scan state: both artefacts recorded with their live checksums
    # (this is exactly what run_scan commits before ingestion starts).
    prior = {parts["manifest"].file_id: "abc", parts["workbook"].file_id: "abc"}
    conn = _Conn(prior)

    _requeue(conn, parts, "Failing Client - DMA", "failed: boom")
    assert conn.commits == 1

    tree = [parts["manifest"], parts["workbook"]]
    d = diff_tree(tree, prior)
    assert {f.file_id for f in d.changed} == set(prior)   # both retry
    assert d.unchanged == []


def test_requeue_without_report_touches_only_present_artefacts():
    parts = {"workbook": _f("X - DMA", "X Scoring Workbook.xlsx"), "folder": "X - DMA"}
    prior = {parts["workbook"].file_id: "abc", "unrelated": "zzz"}
    conn = _Conn(prior)
    _requeue(conn, parts, "X - DMA", "incomplete package")
    assert prior[parts["workbook"].file_id] == ""
    assert prior["unrelated"] == "zzz"
