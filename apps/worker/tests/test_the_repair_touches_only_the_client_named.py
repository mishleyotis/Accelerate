"""The evidence repair may touch one named client, and no other.

MEASURED 2026-09-04T13:13:20Z, the first production firing that could run
this pass at all:

    backfill-evidence: 5 run(s) (reader 0482f3992715d21e, 94 deferred …)
    backfill-evidence: 1st Security Bank - DMA -> 113 row(s) filled
    backfill-evidence: Amalgamated Bank - DMA -> 34 row(s) filled
    backfill-evidence: Amalgamated Bank - DMA -> 34 row(s) filled
    backfill-evidence: ATB - DMA -> 352 row(s) filled
    backfill-evidence: ATB - DMA -> 352 row(s) filled

Ninety-nine runs of work across the corpus, worked from the top of the
alphabet. The client anybody had actually asked about — Golden 1 Credit
Union — was hours down that list, and three clients nobody had asked about
were repaired instead. Owner's instruction the same day: strictly Golden 1,
do not add clients.

Two things this file pins.

ONE: unset means OFF. `EVIDENCE_REPAIR_ONLY` naming nobody must repair
nobody — not "everybody", which is the default that produced the log above.

TWO: one workbook per client. Amalgamated and ATB each appear twice because
each has two runs, and the fill is entity-scoped — every UPDATE keys on
`entity_id`, since `evidence_index` has no run column — so the second run's
1.5 MB download exists only to discover there is nothing left to give.

Run with
`pytest apps/worker/tests/test_the_repair_touches_only_the_client_named.py`.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import job_main
from dma_worker.scan_diff import FileStat


def _f(folder, name, checksum="abc"):
    return FileStat(file_id=f"{folder}/{name}", path_segments=(folder, name),
                    name=name, checksum=checksum, size_bytes=10, mime_type="")


CORPUS = [
    ("run-a1", "ent-a", "1st Security Bank - DMA", 1),
    ("run-b1", "ent-b", "Amalgamated Bank - DMA", 1),
    ("run-b2", "ent-b", "Amalgamated Bank - DMA", 2),
    ("run-c1", "ent-c", "ATB - DMA", 1),
    ("run-c2", "ent-c", "ATB - DMA", 2),
    ("run-g1", "ent-g", "Golden 1 Credit Union - DMA", 1),
    ("run-g2", "ent-g", "Golden 1 Credit Union - DMA", 2),
]

TREE = [_f(folder, "DMA_Scoring_Workbook.xlsx")
        for folder in sorted({r[2] for r in CORPUS})]


class _Cursor:
    """Applies the work list's own filter, so the SQL is under test too."""

    def __init__(self, corpus):
        self._corpus = corpus
        self._rows: list = []
        self.observed: list = []
        self.rowcount = 0

    def execute(self, sql, params=None):
        if sql.startswith(("SAVEPOINT", "RELEASE", "ROLLBACK")):
            return
        if "FROM runs r" in sql:
            forced, _reader, only, _like = params
            self._rows = [r for r in self._corpus
                          if not only or only.lower() in r[2].lower()]
        elif "SELECT e_id, source_name, excerpt" in sql:
            self._rows = []
        elif "UPDATE evidence_index" in sql:
            self.rowcount = 1
        elif "parser_observations" in sql:
            kind = sql.split("'")[1] if "'" in sql else "?"
            self.observed.append((kind, params))
        else:                                            # pragma: no cover
            raise AssertionError(f"unexpected sql: {sql[:70]}")

    def fetchall(self):
        return self._rows


class _Conn:
    def __init__(self, corpus):
        self.cur = _Cursor(corpus)

    def cursor(self):
        return self.cur

    def commit(self):
        pass

    def rollback(self):                                  # pragma: no cover
        pass


LEDGER = [{"e_id": "E-001", "source_name": "A source",
           "source_url": "https://example.test/a", "claim_type": "FACT",
           "excerpt": "Z" * 60}]


@pytest.fixture()
def workbook(monkeypatch):
    seen = []
    monkeypatch.setattr(job_main.drive, "download",
                        lambda t, fid: seen.append(fid) or b"bytes")
    monkeypatch.setattr(job_main, "parse_evidence_master", lambda p: LEDGER)
    monkeypatch.setattr(job_main, "parse_scoring_workbook",
                        lambda p: type("W", (), {"scores": []})())
    monkeypatch.setattr(job_main, "mine_evidence_from_rationales",
                        lambda scores: {})
    return seen


def _folders_touched(cur):
    return [p[0] for kind, p in cur.observed if kind == "evidence_reader_pass"]


def test_naming_one_client_reads_that_client_and_no_other(workbook):
    """The instruction, enforced where the work is chosen."""
    conn = _Conn(CORPUS)
    job_main.backfill_evidence(conn, "tok", job_main._package_groups(TREE),
                               forced=False, only="Golden 1")

    assert len(workbook) == 1, \
        f"{len(workbook)} workbooks were downloaded for a one-client repair"
    assert sorted(_folders_touched(conn.cur)) == ["run-g1", "run-g2"], \
        "the repair reached a client it was not asked to touch"


def test_one_workbook_per_client_not_per_run(workbook):
    """Golden 1 has two runs and one workbook. The fill is entity-scoped, so
    the second download can only re-learn what the first already did."""
    conn = _Conn(CORPUS)
    job_main.backfill_evidence(conn, "tok", job_main._package_groups(TREE),
                               forced=False, only="Golden 1")

    assert len(workbook) == 1
    # …and BOTH runs are recorded, or the one left unstamped comes back on
    # the next firing asking for the same download.
    assert sorted(_folders_touched(conn.cur)) == ["run-g1", "run-g2"]


def test_the_per_firing_cap_counts_clients_not_runs(workbook, monkeypatch):
    """Five runs of one client used to spend the whole budget. The cap is on
    downloads, because downloads are what cost."""
    monkeypatch.setattr(job_main, "EVIDENCE_REPAIR_PER_FIRING", 2)
    conn = _Conn(CORPUS)
    job_main.backfill_evidence(conn, "tok", job_main._package_groups(TREE),
                               forced=False)

    assert len(workbook) == 2, \
        "the cap counted runs again, so a client with several runs starves " \
        "the rest of the queue"


def test_the_scheduled_scan_repairs_nobody_when_nobody_is_named(monkeypatch,
                                                                fakedb, capsys):
    """UNSET IS OFF. This is the default that sent the first firing off to
    repair three clients nobody had asked about; it must never mean
    "everyone" again."""
    called = []
    monkeypatch.setattr(job_main, "backfill_evidence",
                        lambda *a, **kw: called.append(kw) or 0)
    monkeypatch.setenv("INTAKE_FOLDER_ID", "intake-root")
    monkeypatch.delenv("EVIDENCE_REPAIR_ONLY", raising=False)
    for k in ("BACKFILL_EVIDENCE", "BACKFILL_COMPOSITE", "RESET_SCAN",
              "INTAKE_STATUS", "BACKFILL_SECTIONS", "BACKFILL_GRAINS",
              "BACKFILL_WBMETA", "EVIDENCE_URL_BACKFILL", "EVIDENCE_NAMESPACE",
              "EMBED_MODEL_DIR", "FORCE_FOLDER", "DUMP_HEADERS",
              "LINK_PROPOSE_RUN_ID"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(job_main, "_connect", lambda: fakedb)
    monkeypatch.setattr(job_main.drive, "walk_tree", lambda _i: TREE)
    monkeypatch.setattr(job_main.drive, "metadata_token", lambda: "tok")
    monkeypatch.setattr(job_main, "_ingest_one",
                        lambda *a, **kw: (type("R", (), {
                            "run_id": "r", "scored_cells": 1,
                            "observations": 0})(), []))

    job_main.main()

    assert called == [], \
        "the repair ran with no client named; unset must be off, not " \
        "'every client in the corpus'"
    assert "names no client" in capsys.readouterr().out, \
        "the firing did not say why it repaired nothing"


def test_the_scheduled_scan_passes_the_name_through(monkeypatch, fakedb):
    """And when a client IS named, that name reaches the pass."""
    called = []
    monkeypatch.setattr(job_main, "backfill_evidence",
                        lambda *a, **kw: called.append(kw) or 0)
    monkeypatch.setenv("INTAKE_FOLDER_ID", "intake-root")
    monkeypatch.setenv("EVIDENCE_REPAIR_ONLY", "Golden 1")
    for k in ("BACKFILL_EVIDENCE", "BACKFILL_COMPOSITE", "RESET_SCAN",
              "INTAKE_STATUS", "BACKFILL_SECTIONS", "BACKFILL_GRAINS",
              "BACKFILL_WBMETA", "EVIDENCE_URL_BACKFILL", "EVIDENCE_NAMESPACE",
              "EMBED_MODEL_DIR", "FORCE_FOLDER", "DUMP_HEADERS",
              "LINK_PROPOSE_RUN_ID"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(job_main, "_connect", lambda: fakedb)
    monkeypatch.setattr(job_main.drive, "walk_tree", lambda _i: TREE)
    monkeypatch.setattr(job_main.drive, "metadata_token", lambda: "tok")
    monkeypatch.setattr(job_main, "_ingest_one",
                        lambda *a, **kw: (type("R", (), {
                            "run_id": "r", "scored_cells": 1,
                            "observations": 0})(), []))

    job_main.main()

    assert called and called[0].get("only") == "Golden 1"
    assert called[0].get("forced") is False
