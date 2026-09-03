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
    for decoy in ("Explorium_Tech_Stack_ALLIANT.xlsx",
                  "DMA_TechStack_Appendix_1st_Source_Bank.xlsx",
                  "A4_Technology_Stack_Summary_Explorium.xlsx",
                  "Tech_Stack_Appendix_Achieve.xlsx",
                  "Pillar1_Scoring_Toolkit.xlsx",
                  "Weight Summary.xlsx"):
        assert c(decoy) is None, decoy

    # The research workbook is its OWN artefact, not a decoy: it carries the
    # per-cell fact-grain linkage, the verbatim passage behind each fact, and
    # the ERS/date ledger the scoring workbook omits. Excluding it left every
    # ingested evidence item undated and unranked.
    assert c("DMA_Research_Workbook_ALLIANT.xlsx") == ("research", 0)
    # it must never be mistaken for the scoring workbook — a score comes from
    # 03_scoring_workbook and nowhere else
    assert c("DMA_Research_Workbook_ALLIANT.xlsx")[0] != "workbook"
    # a workbook under a research path is research material, not a score source
    assert c("DMA_Scoring_Workbook_X.xlsx",
             segs=("Client - DMA", "02_research_workbook")) == ("research", 1)

    # reports: the assessment report beats a bare report.docx; the research
    # Client Profile is a different artefact and never the report — but it
    # IS an artefact. It used to return None, which meant all eight of its
    # sections reached no table in the app while four page packs named it as
    # their source of truth. `classification.py` in this same service had
    # been classifying it as `client_profile` priority 3 the whole time:
    # classified, recorded, then dropped.
    assert c("DMA_Assessment_Report_BCU_20260330.docx") == ("report", 0)
    assert c("Report.docx") == ("report", 1)
    assert c("DMA_Client_Profile_BCU_20260330.docx") == ("profile", 0)
    assert c("Client_Profile_Research_Acme_2026-08-30.docx") == ("profile", 0)
    # and the profile is never mistaken FOR the report
    assert c("Client_Profile_Research_Acme_2026-08-30.docx") != ("report", 2)

    # a superseded package, archived inside the client folder when a second
    # run opened it, is not a candidate for anything: the scan reads the
    # whole tree at any depth and keeps one artefact per kind, so an
    # archived workbook could otherwise be chosen over the current one
    assert c("DMA_Scoring_Workbook_X.xlsx",
             segs=("Client - DMA", "_superseded", "R-OLD_2026-01-15")) is None
    assert c("DMA_Assessment_Report_X.docx",
             segs=("Client - DMA", "_superseded", "R-OLD")) is None


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


def test_packages_assemble_from_the_whole_tree_not_only_changed_files():
    """The diff decides WHICH folders to process; the package still needs
    all of its artefacts. Assembling from the changed set alone meant a
    folder whose workbook changed but whose report did not lost its report
    — which is why no run had ever landed its report sections."""
    tree = [
        _f("Client A - DMA", "run_manifest.json", checksum="m1"),
        _f("Client A - DMA", "DMA_Scoring_Workbook_A.xlsx", checksum="w2"),   # changed
        _f("Client A - DMA", "DMA_Assessment_Report_A.docx", checksum="r1"),
        _f("Client B - DMA", "run_manifest.json", checksum="m1"),
        _f("Client B - DMA", "DMA_Scoring_Workbook_B.xlsx", checksum="w1"),   # unchanged
    ]
    prior = {t.file_id: ("w1" if "Workbook_A" in t.name else t.checksum) for t in tree}
    d = diff_tree(tree, prior)
    assert [f.name for f in d.changed] == ["DMA_Scoring_Workbook_A.xlsx"]

    groups = _package_groups(tree)
    touched = {f.path_segments[0] for f in d.changed}
    packages = {k: v for k, v in groups.items() if "workbook" in v and k in touched}

    assert set(packages) == {"Client A - DMA"}, "only the touched folder processes"
    parts = packages["Client A - DMA"]
    # and it carries the artefacts that did NOT change
    assert "manifest" in parts and "report" in parts
    assert parts["report"].name == "DMA_Assessment_Report_A.docx"


class _BackfillCursor:
    """Enough of a cursor for backfill_sections: one SELECT of runs that
    hold no sections, then INSERTs into document_sections."""

    def __init__(self, runs):
        self._runs, self.inserted = runs, []
        self._rows = []

    def execute(self, sql, params=None):
        if "FROM runs r" in sql:
            assert "NOT EXISTS" in sql, "must only pick runs with no sections"
            self._rows = list(self._runs)
        elif "INSERT INTO document_sections" in sql:
            self.inserted.append(params)
        else:                                    # pragma: no cover
            raise AssertionError(f"unexpected sql: {sql[:60]}")

    def fetchall(self):
        return self._rows


class _BackfillConn:
    def __init__(self, runs):
        self.cur = _BackfillCursor(runs)
        self.commits = 0

    def cursor(self):
        return self.cur

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


def test_backfill_fills_only_runs_whose_folder_ships_a_report(monkeypatch):
    """Additive recovery for runs ingested before the assembly fix: the
    sections land against the EXISTING run, and a folder with no report
    artefact is reported rather than failed."""
    import job_main
    from dma_worker.report_parser import ReportSection

    tree = [_f("Has Report - DMA", "DMA_Scoring_Workbook_A.xlsx"),
            _f("Has Report - DMA", "DMA_Assessment_Report_A.docx"),
            _f("No Report - DMA", "DMA_Scoring_Workbook_B.xlsx")]
    groups = job_main._package_groups(tree)

    monkeypatch.setattr(job_main.drive, "download", lambda t, fid: b"docx-bytes")
    monkeypatch.setattr(job_main, "parse_report", lambda p: [
        ReportSection(section_kind="executive_summary", pillar_id=None,
                      heading="Executive Summary", body="Body.", page=None),
        ReportSection(section_kind="pillar_narrative", pillar_id="P1",
                      heading="Strategy", body="Body.", page=None)])

    conn = _BackfillConn([("run-a", "Has Report - DMA"),
                          ("run-b", "No Report - DMA")])
    rc = job_main.backfill_sections(conn, "token", groups)

    assert rc == 0
    assert len(conn.cur.inserted) == 2, "only run-a's two sections insert"
    assert {row[0] for row in conn.cur.inserted} == {"run-a"}
    assert conn.commits == 1, "one commit per backfilled run"


def test_backfill_returns_before_the_scan_consumes_the_diff():
    """run_scan stores the new checksums. A backfill executed after it
    would swallow that firing's diff, so the changed packages would never
    be ingested — the backfill branch must precede the scan call."""
    src = (Path(__file__).resolve().parents[1] / "job_main.py").read_text()
    assert src.index("BACKFILL_SECTIONS") < src.index("summary = run_scan(")


class _GrainCursor:
    """Enough of a cursor for backfill_grains: one SELECT of runs holding no
    stated pillar grain, then UPDATEs of run_manifest."""

    def __init__(self, runs):
        self._runs, self.updated = runs, []
        self._rows = []

    def execute(self, sql, params=None):
        if "FROM runs r" in sql:
            assert "workbook_grains" in sql and "jsonb_array_length" in sql, \
                "must only pick runs whose stated pillar grain is empty"
            self._rows = list(self._runs)
        elif "UPDATE run_manifest" in sql:
            assert "jsonb_set" in sql and "'{workbook_grains}'" in sql, \
                "only the workbook_grains key may be written"
            self.updated.append(params)
        else:                                    # pragma: no cover
            raise AssertionError(f"unexpected sql: {sql[:60]}")

    def fetchall(self):
        return self._rows


class _GrainConn:
    def __init__(self, runs):
        self.cur = _GrainCursor(runs)
        self.commits = 0

    def cursor(self):
        return self.cur

    def commit(self):
        self.commits += 1

    def rollback(self):                          # pragma: no cover
        pass


def test_backfill_grains_fills_the_run_that_lost_its_stated_pillars(monkeypatch):
    """Golden 1's own case. The workbook states 2.40/2.11/2.25/2.25; the run
    stored none because its reader wanted a column named `score` in a tab
    that names it `Weighted_Score`. The recovery updates the EXISTING run."""
    import json as _json

    import job_main

    tree = [_f("Golden 1 Credit Union - DMA", "DMA_Scoring_Workbook_G1.xlsx"),
            _f("No Workbook - DMA", "DMA_Assessment_Report_X.docx")]
    groups = job_main._package_groups(tree)

    stated = {"pillars": [{"pillar_id": "P1", "score": 2.4,
                           "peer_median": 3.1, "source_cell": "Pillar_Summary!C2"},
                          {"pillar_id": "P2", "score": 2.11,
                           "peer_median": 3.0, "source_cell": "Pillar_Summary!C3"},
                          {"pillar_id": "P3", "score": 2.25,
                           "peer_median": 3.0, "source_cell": "Pillar_Summary!C4"},
                          {"pillar_id": "P4", "score": 2.25,
                           "peer_median": 3.1, "source_cell": "Pillar_Summary!C5"}],
              "categories": [{"category_id": "P1C1", "score": 2.9}]}
    monkeypatch.setattr(job_main.drive, "download", lambda t, fid: b"xlsx-bytes")
    monkeypatch.setattr(job_main, "parse_grain_summaries",
                        lambda p, obs=None: stated)

    conn = _GrainConn([("run-g1", "Golden 1 Credit Union - DMA"),
                       ("run-x", "No Workbook - DMA")])
    rc = job_main.backfill_grains(conn, "token", groups)

    assert rc == 0
    assert len(conn.cur.updated) == 1, "only the folder shipping a workbook"
    payload, run_id = conn.cur.updated[0]
    assert run_id == "run-g1"
    got = _json.loads(payload)
    assert [p["score"] for p in got["pillars"]] == [2.4, 2.11, 2.25, 2.25]
    assert conn.commits == 1


def test_backfill_grains_writes_nothing_when_the_workbook_states_none(monkeypatch):
    """A workbook that genuinely states no grain is reported, not written —
    an empty grain object must never overwrite the manifest."""
    import job_main

    tree = [_f("Silent - DMA", "DMA_Scoring_Workbook_S.xlsx")]
    groups = job_main._package_groups(tree)
    monkeypatch.setattr(job_main.drive, "download", lambda t, fid: b"xlsx-bytes")
    monkeypatch.setattr(job_main, "parse_grain_summaries",
                        lambda p, obs=None: {"pillars": [], "categories": []})

    conn = _GrainConn([("run-s", "Silent - DMA")])
    assert job_main.backfill_grains(conn, "token", groups) == 0
    assert conn.cur.updated == [], "no UPDATE for a workbook stating nothing"
    assert conn.commits == 0


def test_backfill_grains_survives_one_unreadable_workbook(monkeypatch):
    """One bad workbook must not sink the pass, and must be reported."""
    import job_main

    tree = [_f("Bad - DMA", "DMA_Scoring_Workbook_B.xlsx"),
            _f("Good - DMA", "DMA_Scoring_Workbook_G.xlsx")]
    groups = job_main._package_groups(tree)
    monkeypatch.setattr(job_main.drive, "download", lambda t, fid: b"xlsx-bytes")

    def _parse(p, obs=None):
        _parse.n += 1
        if _parse.n == 1:
            raise ValueError("not a zip file")
        return {"pillars": [{"pillar_id": "P1", "score": 2.4}], "categories": []}
    _parse.n = 0
    monkeypatch.setattr(job_main, "parse_grain_summaries", _parse)

    conn = _GrainConn([("run-bad", "Bad - DMA"), ("run-good", "Good - DMA")])
    rc = job_main.backfill_grains(conn, "token", groups)

    assert rc == 1, "a failure is reported in the exit code"
    assert len(conn.cur.updated) == 1, "the good run still lands"
    assert conn.cur.updated[0][1] == "run-good"


class _CompositeCursor:
    """Enough of a cursor for backfill_composite: one SELECT of runs holding
    no composite, then UPDATEs of runs."""

    def __init__(self, runs):
        self._runs, self.updated = runs, []
        self._rows = []

    def execute(self, sql, params=None):
        if "FROM runs r" in sql:
            assert "r.composite IS NULL" in sql, \
                "must only pick runs whose composite is unset"
            self._rows = list(self._runs)
        elif "UPDATE runs" in sql:
            assert "SET composite" in sql, "only the composite may be written"
            self.updated.append(params)
        else:                                    # pragma: no cover
            raise AssertionError(f"unexpected sql: {sql[:60]}")

    def fetchall(self):
        return self._rows


class _CompositeConn:
    def __init__(self, runs):
        self.cur = _CompositeCursor(runs)
        self.commits = 0

    def cursor(self):
        return self.cur

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


def _stub_overall(monkeypatch, value, cell="Pillar_Summary!C6"):
    """The reader and the workbook load are both stubbed: these tests are
    about the backfill's own decisions, and the reader has its own suite."""
    import job_main

    monkeypatch.setattr(job_main.drive, "download", lambda t, fid: b"xlsx-bytes")
    monkeypatch.setattr(job_main.openpyxl, "load_workbook",
                        lambda p, **kw: type("W", (), {"close": lambda s: None})())
    monkeypatch.setattr(job_main, "_stated_overall_grain",
                        lambda wb: (value, cell))


def test_backfill_composite_fills_the_run_whose_card_showed_no_maturity(monkeypatch):
    """Golden 1's own case. The workbook states 2.25 at Pillar_Summary!C6;
    the run stored NULL because its generation has no 2_Scorecard tab, and
    the directory card rendered the word "maturity" over an empty slot."""
    from decimal import Decimal

    import job_main

    tree = [_f("Golden 1 Credit Union - DMA", "DMA_Scoring_Workbook_G1.xlsx"),
            _f("No Workbook - DMA", "DMA_Assessment_Report_X.docx")]
    groups = job_main._package_groups(tree)
    _stub_overall(monkeypatch, Decimal("2.25"))

    conn = _CompositeConn([("run-g1", "Golden 1 Credit Union - DMA"),
                           ("run-x", "No Workbook - DMA")])
    rc = job_main.backfill_composite(conn, "token", groups)

    assert rc == 0
    assert len(conn.cur.updated) == 1, "only the folder shipping a workbook"
    value, run_id = conn.cur.updated[0]
    assert run_id == "run-g1"
    assert value == Decimal("2.25")
    assert conn.commits == 1


def test_backfill_composite_writes_nothing_when_the_workbook_states_none(monkeypatch):
    """Absent beats invented: a workbook stating no OVERALL leaves the column
    NULL rather than acquiring a mean of the pillars."""
    import job_main

    tree = [_f("Silent - DMA", "DMA_Scoring_Workbook_S.xlsx")]
    groups = job_main._package_groups(tree)
    _stub_overall(monkeypatch, None, None)

    conn = _CompositeConn([("run-s", "Silent - DMA")])
    assert job_main.backfill_composite(conn, "token", groups) == 0
    assert conn.cur.updated == [], "no UPDATE for a workbook stating nothing"
    assert conn.commits == 0


def test_backfill_composite_survives_one_unreadable_workbook(monkeypatch):
    """One bad workbook must not sink the pass, and must be reported."""
    from decimal import Decimal

    import job_main

    tree = [_f("Bad - DMA", "DMA_Scoring_Workbook_B.xlsx"),
            _f("Good - DMA", "DMA_Scoring_Workbook_G.xlsx")]
    groups = job_main._package_groups(tree)
    monkeypatch.setattr(job_main.drive, "download", lambda t, fid: b"xlsx-bytes")
    monkeypatch.setattr(job_main.openpyxl, "load_workbook",
                        lambda p, **kw: type("W", (), {"close": lambda s: None})())

    def _read(wb):
        _read.n += 1
        if _read.n == 1:
            raise ValueError("not a zip file")
        return Decimal("3.10"), "Pillar_Rollup!C6"
    _read.n = 0
    monkeypatch.setattr(job_main, "_stated_overall_grain", _read)

    conn = _CompositeConn([("bad", "Bad - DMA"), ("good", "Good - DMA")])
    rc = job_main.backfill_composite(conn, "token", groups)

    assert rc == 1, "a failure must be reported in the exit code"
    assert len(conn.cur.updated) == 1, "the good workbook still lands"
    assert conn.cur.updated[0][1] == "good"


class _MetaCursor:
    """Enough of a cursor for backfill_workbook_metadata: one SELECT of runs
    holding no workbook metadata, then UPDATEs of run_manifest and runs."""

    def __init__(self, runs, completed_at_rowcount=1):
        self._runs = runs
        self.meta_updates, self.date_updates = [], []
        self._rows = []
        self.rowcount = completed_at_rowcount

    def execute(self, sql, params=None):
        if "FROM runs r" in sql and "SELECT" in sql:
            assert "'workbook_metadata' IS NULL" in sql, \
                "must only pick runs whose workbook metadata is unset"
            self._rows = list(self._runs)
        elif "UPDATE run_manifest" in sql:
            assert "'{workbook_metadata}'" in sql, \
                "only the workbook_metadata key may be written"
            assert "manifest" not in sql.split("jsonb_set")[1][:60], \
                "the package's own manifest must never be edited"
            self.meta_updates.append(params)
        elif "UPDATE runs" in sql:
            assert "completed_at IS NULL" in sql, \
                "a stated completion date must never be overwritten"
            self.date_updates.append(params)
        else:                                    # pragma: no cover
            raise AssertionError(f"unexpected sql: {sql[:60]}")

    def fetchall(self):
        return self._rows


class _MetaConn:
    def __init__(self, runs, **kw):
        self.cur = _MetaCursor(runs, **kw)
        self.commits = 0

    def cursor(self):
        return self.cur

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


def test_backfill_wbmeta_fills_the_run_that_served_no_date(monkeypatch):
    """Golden 1's own case: no manifest date key, no YYYYMMDD token in
    `DMA-2026-GOLDEN1-001`, and `last_written_at` sitting unread on the
    workbook's own Run_Metadata tab."""
    import json as _json

    import job_main

    tree = [_f("Golden 1 Credit Union - DMA HYBRID", "DMA_Scoring_Workbook_G1.xlsx"),
            _f("No Workbook - DMA", "DMA_Assessment_Report_X.docx")]
    groups = job_main._package_groups(tree)
    monkeypatch.setattr(job_main.drive, "download", lambda t, fid: b"xlsx-bytes")
    monkeypatch.setattr(job_main, "parse_run_metadata",
                        lambda p: {"run_id": "DMA-2026-GOLDEN1-001",
                                   "last_written_at": "2026-08-31T09:33:59Z"})

    conn = _MetaConn([("run-g1", "Golden 1 Credit Union - DMA HYBRID"),
                      ("run-x", "No Workbook - DMA")])
    assert job_main.backfill_workbook_metadata(conn, "token", groups) == 0

    assert len(conn.cur.meta_updates) == 1, "only the folder shipping a workbook"
    payload, run_id = conn.cur.meta_updates[0]
    assert run_id == "run-g1"
    assert _json.loads(payload)["last_written_at"] == "2026-08-31T09:33:59Z"

    assert len(conn.cur.date_updates) == 1, (
        "the date the evidence bands hang off must be filled in the same pass")
    stamp, dated_run = conn.cur.date_updates[0]
    assert dated_run == "run-g1"
    assert stamp.startswith("2026-08-31")


def test_backfill_wbmeta_writes_no_date_when_the_tab_states_none(monkeypatch):
    """A Run_Metadata tab without any date key still lands as metadata, but
    must not invent a completion date."""
    import job_main

    tree = [_f("Undated - DMA", "DMA_Scoring_Workbook_U.xlsx")]
    groups = job_main._package_groups(tree)
    monkeypatch.setattr(job_main.drive, "download", lambda t, fid: b"xlsx-bytes")
    monkeypatch.setattr(job_main, "parse_run_metadata",
                        lambda p: {"scope_mode": "FULL"})

    conn = _MetaConn([("run-u", "Undated - DMA")])
    assert job_main.backfill_workbook_metadata(conn, "token", groups) == 0
    assert len(conn.cur.meta_updates) == 1
    assert conn.cur.date_updates == [], "no date key means no completed_at"


def test_backfill_wbmeta_writes_nothing_for_a_workbook_with_no_tab(monkeypatch):
    """An empty read is a fact about the workbook, not something to store."""
    import job_main

    tree = [_f("Bare - DMA", "DMA_Scoring_Workbook_B.xlsx")]
    groups = job_main._package_groups(tree)
    monkeypatch.setattr(job_main.drive, "download", lambda t, fid: b"xlsx-bytes")
    monkeypatch.setattr(job_main, "parse_run_metadata", lambda p: {})

    conn = _MetaConn([("run-b", "Bare - DMA")])
    assert job_main.backfill_workbook_metadata(conn, "token", groups) == 0
    assert conn.cur.meta_updates == [] and conn.cur.date_updates == []
    assert conn.commits == 0


def test_the_worker_and_the_sql_walk_the_same_date_candidates():
    """0031's rule, pinned. `_stated_completed_at` and the probe array in
    `run_assessment_date` must name the same fields in the same order, or a
    run's `completed_at` and its served `assessment_date` disagree — the same
    date resolved twice, differently, from one document.

    Both sides are read from what actually RUNS: the worker's own source, and
    the SQL the migration emits (not its source, which also mentions the field
    in the template that inserts it).
    """
    import importlib.util as _u
    import inspect
    import os as _os
    import re
    import sys as _sys
    import types as _types

    from dma_worker import persist

    src = inspect.getsource(persist._stated_completed_at)
    # `a.get("date")` is the nested `assessment.date`; the flat keys follow.
    worker = ["assessment.date"] + re.findall(r'manifest\.get\("([a-z_]+)"\)', src)
    worker = [k for k in worker if k != "assessment"]

    mig = _os.path.join(_os.path.dirname(__file__), "..", "..", "..",
                        "migrations", "versions",
                        "0058_workbook_metadata_dates.py")
    _sys.modules.setdefault("alembic", _types.SimpleNamespace(
        op=_types.SimpleNamespace(execute=lambda *a: None)))
    spec = _u.spec_from_file_location("_m0058", mig)
    mod = _u.module_from_spec(spec)
    spec.loader.exec_module(mod)
    probe = re.findall(r"\['([a-z_.]+)',\s+'[A-Z_]+'\]", mod._fn(True))

    assert worker == probe, (
        f"the worker walks {worker} and the SQL walks {probe}; 0031 requires "
        "one candidate list in one order")
