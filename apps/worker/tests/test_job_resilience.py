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


def test_artefact_classification_matches_the_shipped_corpus():
    """Naming is not standardised across the corpus — these are the real
    names from the intake tree (76 of 105 folders were skipped on naming
    alone). Decoys must never be mistaken for the scoring workbook."""
    from job_main import _classify_artefact

    def c(name, segs=("Client - DMA",)):
        return _classify_artefact(FileStat(file_id=name, path_segments=(*segs, name),
                                           name=name, checksum="a", size_bytes=1,
                                           mime_type=""))

    # manifests: canonical wins over variants
    assert c("run_manifest.json") == ("manifest", 0)
    assert c("L1_run_manifest.json") == ("manifest", 1)
    assert c("MANIFEST.json") == ("manifest", 1)
    assert c("PACKAGE_MANIFEST.md") is None          # markdown is not a manifest

    # workbooks: scoring beats assessment; every decoy rejected
    assert c("DMA_Scoring_Workbook_BCU_20260330.xlsx") == ("workbook", 0)
    assert c("ATB_SF_nCino_Scoring_Workbook.xlsx") == ("workbook", 0)
    assert c("DMA_Assessment_Workbook_Achieve.xlsx") == ("workbook", 1)
    assert c("DMA_Workbook_CISBH.xlsx") == ("workbook", 2)
    for decoy in ("DMA_Research_Workbook_ALLIANT.xlsx",
                  "Explorium_Tech_Stack_ALLIANT.xlsx",
                  "DMA_TechStack_Appendix_1st_Source_Bank.xlsx",
                  "A4_Technology_Stack_Summary_Explorium.xlsx",
                  "Tech_Stack_Appendix_Achieve.xlsx",
                  "Pillar1_Scoring_Toolkit.xlsx",
                  "Weight Summary.xlsx"):
        assert c(decoy) is None, decoy
    # a scoring workbook under a research path is research material
    assert c("DMA_Scoring_Workbook_X.xlsx", segs=("Client - DMA", "02_research_workbook")) is None

    # reports: the assessment report beats a bare report.docx; the research
    # Client Profile is a different artefact and never the report
    assert c("DMA_Assessment_Report_BCU_20260330.docx") == ("report", 0)
    assert c("Report.docx") == ("report", 1)
    assert c("DMA_Client_Profile_BCU_20260330.docx") is None


def test_workbook_alone_is_ingestable_and_best_candidate_wins():
    """A package that ships no manifest still ingests (identity falls to the
    folder name, PENDING_REVIEW); and where a folder holds two candidates of
    a kind, the canonical one is chosen."""
    files = [
        _f("Two Candidates - DMA", "L1_run_manifest.json"),
        _f("Two Candidates - DMA", "run_manifest.json"),
        _f("Two Candidates - DMA", "DMA_Assessment_Workbook_X.xlsx"),
        _f("Two Candidates - DMA", "DMA_Scoring_Workbook_X.xlsx"),
        _f("Two Candidates - DMA", "DMA_Assessment_Report_X.docx"),
        _f("No Manifest - DMA", "ATB_SF_nCino_Scoring_Workbook.xlsx"),
        _f("Manifest Only - DMA", "run_manifest.json"),
    ]
    groups = _package_groups(files)
    g = groups["Two Candidates - DMA"]
    assert g["manifest"].name == "run_manifest.json"
    assert g["workbook"].name == "DMA_Scoring_Workbook_X.xlsx"
    assert g["report"].name == "DMA_Assessment_Report_X.docx"

    ingestable = {k: v for k, v in groups.items() if "workbook" in v}
    partial = {k: v for k, v in groups.items() if k not in ingestable
               and any(a in v for a in ("manifest", "workbook", "report"))}
    assert set(ingestable) == {"Two Candidates - DMA", "No Manifest - DMA"}
    assert set(partial) == {"Manifest Only - DMA"}
