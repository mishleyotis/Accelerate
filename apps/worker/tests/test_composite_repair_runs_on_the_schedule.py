"""The composite repair has to RUN, not merely work.

MEASURED 2026-09-04 from the promoted client directory. goeasy Ltd.
(`DMA-RES-GSY-20260830-0002`) served `overall: null` beside its own four
pillar bars — P1 2.09, P2 2.19, P3 2.01, P4 2.16 — every one of which
resolved, and beside six other institutions every one of which showed a
maturity figure. The card rendered the word "maturity" over an empty slot.

`runs.composite` is written exactly ONCE, at INSERT, from the reader that ran
that day. goeasy's workbook was last read by this Job at 04:14:58 on
2026-09-03; `_stated_overall_grain`, the reader that can find the composite
in its generation, merged at 06:08 the same day. So the run was ingested
under a reader that could not see the figure, and nothing ever looked again:
the package scan is idempotent, so an unchanged tree re-reads nothing.

The repair existed the whole time. `backfill_composite` had three tests —
it fills, it declines to invent, it survives a bad workbook — and NOT ONE
that it is ever called. It sat behind `if os.environ.get(
"BACKFILL_COMPOSITE")`, which no schedule sets, and no worker firing has
ever logged a line from it.

That is the defect these tests pin, and it is not the reader: a capability
built, tested, and never reached. A test that a function works is not a test
that the system uses it.

Run with `pytest apps/worker/tests/test_composite_repair_runs_on_the_schedule.py`.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import job_main
from dma_worker.scan_diff import FileStat


def _f(folder, name, checksum="abc"):
    return FileStat(file_id=f"{folder}/{name}", path_segments=(folder, name),
                    name=name, checksum=checksum, size_bytes=10, mime_type="")


TREE = [_f("goeasy Ltd - DMA", "run_manifest.json", "m1"),
        _f("goeasy Ltd - DMA", "DMA_Scoring_Workbook_goeasy-ltd.xlsx", "w1")]


def _run_main(monkeypatch, db, tree, ingest=None, **env):
    monkeypatch.setenv("INTAKE_FOLDER_ID", "intake-root")
    monkeypatch.setenv("MAX_PACKAGES", "10")
    for k in ("DUMP_HEADERS", "LINK_PROPOSE_RUN_ID", "RESET_SCAN",
              "INTAKE_STATUS", "BACKFILL_SECTIONS", "BACKFILL_EVIDENCE",
              "BACKFILL_GRAINS", "BACKFILL_WBMETA", "BACKFILL_COMPOSITE",
              "EVIDENCE_URL_BACKFILL", "EVIDENCE_NAMESPACE",
              "EMBED_MODEL_DIR", "FORCE_FOLDER"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(job_main, "_connect", lambda: db)
    monkeypatch.setattr(job_main.drive, "walk_tree", lambda _i: tree)
    monkeypatch.setattr(job_main.drive, "metadata_token", lambda: "tok")
    monkeypatch.setattr(job_main, "_ingest_one", ingest or _ok_ingest)
    return job_main.main()


class _Res:
    """What `_scan_and_ingest` reads off a successful ingest."""
    run_id, scored_cells, observations = "run-gsy", 696, 0


def _ok_ingest(conn, token, folder, parts, remint=False):
    return _Res(), []


# ── the test that was missing ────────────────────────────────────────────

def test_the_scheduled_scan_runs_the_composite_repair(monkeypatch, fakedb):
    """THE POINT OF THIS FILE.

    Against the code that shipped, this fails: the only call to
    `backfill_composite` was inside `if os.environ.get("BACKFILL_COMPOSITE")`,
    and the scheduled firing sets no such variable.
    """
    calls = []
    monkeypatch.setattr(job_main, "backfill_composite",
                        lambda conn, token, groups, **kw: calls.append(kw) or 0)

    _run_main(monkeypatch, fakedb, TREE)

    assert calls, ("the scheduled scan never ran the composite repair — a run "
                   "ingested under an older reader stays null for ever")
    assert calls[0].get("forced") is False, (
        "the scheduled pass must be the incremental one; forced=True re-reads "
        "every workbook on every firing")


def test_a_repair_that_cannot_reach_drive_does_not_stop_the_scan(monkeypatch, fakedb):
    """The repair is a passenger. This Job exists to scan the intake tree, and
    a workbook download that fails must not cost that."""
    def boom(conn, token, groups, **kw):
        raise RuntimeError("drive 503")

    monkeypatch.setattr(job_main, "backfill_composite", boom)
    ingested = []

    def _spy(conn, token, folder, parts, remint=False):
        ingested.append(folder)
        return _Res(), []

    rc = _run_main(monkeypatch, fakedb, TREE, ingest=_spy)

    assert rc == 0, "a failed repair must not fail the scan"
    assert ingested, "the scan still ingested its package"


def test_the_manual_mode_still_forces_a_full_re_read(monkeypatch, fakedb):
    """BACKFILL_COMPOSITE is the human's escape hatch: re-read everything,
    including runs already recorded as stating none."""
    calls = []
    monkeypatch.setattr(job_main, "backfill_composite",
                        lambda conn, token, groups, **kw: calls.append(kw) or 0)

    _run_main(monkeypatch, fakedb, TREE, BACKFILL_COMPOSITE="1")

    assert calls, "the manual mode did not run"
    assert calls[0].get("forced", True) is True, \
        "the manual pass must ignore the already-looked-at record"


# ── the bound that makes running it on every firing affordable ───────────

class _Cursor:
    """Records the SELECT that builds the work list and every write."""

    def __init__(self, runs):
        self._runs, self.rows = runs, []
        self.selects, self.updated, self.observed = [], [], []
        self.refreshed = 0

    def execute(self, sql, params=None):
        if "refresh_serving_directory" in sql:
            self.refreshed += 1
        elif "FROM runs r" in sql:
            self.selects.append((sql, params))
            self.rows = list(self._runs)
        elif "UPDATE runs" in sql:
            self.updated.append(params)
        elif "parser_observations" in sql:
            self.observed.append(params)
        else:                                    # pragma: no cover
            raise AssertionError(f"unexpected sql: {sql[:60]}")

    def fetchall(self):
        # (run_id, folder, request_id) — the work list resolves a run's
        # package through a sibling under the same request id when the run
        # itself carries no folder.
        return [(r[0], r[1], r[2] if len(r) > 2 else "REQ-1") for r in self.rows]


class _Conn:
    def __init__(self, runs):
        self.cur = _Cursor(runs)
        self.commits = 0

    def cursor(self):
        return self.cur

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


def _stub_reader(monkeypatch, value, cell="Pillar_Summary!C6"):
    monkeypatch.setattr(job_main.drive, "download", lambda t, fid: b"bytes")
    monkeypatch.setattr(job_main.openpyxl, "load_workbook",
                        lambda p, **kw: type("W", (), {"close": lambda s: None})())
    monkeypatch.setattr(job_main, "_stated_overall_grain",
                        lambda wb: (value, cell))


def test_a_workbook_stating_none_is_recorded_so_it_is_not_re_read(monkeypatch):
    """Running on every firing is only affordable if "nothing here" is
    remembered. Otherwise every composite-less workbook is downloaded again
    every thirty minutes, for ever."""
    tree = [_f("Silent - DMA", "DMA_Scoring_Workbook_S.xlsx")]
    groups = job_main._package_groups(tree)
    _stub_reader(monkeypatch, None, None)

    conn = _Conn([("run-s", "Silent - DMA")])
    assert job_main.backfill_composite(conn, "t", groups, forced=False) == 0

    assert conn.cur.updated == [], "nothing was invented"
    assert len(conn.cur.observed) == 1, \
        "the determination was not recorded, so it will be paid for again"
    import json as _json
    detail = _json.loads(conn.cur.observed[0][1])
    assert detail["reader"] == job_main.composite_reader_fingerprint(), \
        "the record must name the reader that concluded it"


def test_the_incremental_work_list_excludes_what_this_reader_already_read(monkeypatch):
    tree = [_f("Silent - DMA", "DMA_Scoring_Workbook_S.xlsx")]
    groups = job_main._package_groups(tree)
    _stub_reader(monkeypatch, None, None)

    conn = _Conn([])
    job_main.backfill_composite(conn, "t", groups, forced=False)

    sql, params = conn.cur.selects[0]
    assert "composite_absent" in sql, "the work list does not exclude anything"
    assert job_main.composite_reader_fingerprint() in params, \
        "the exclusion must be scoped to the reader that made the record"
    assert params[0] is False, "forced must reach the query as False"


def test_a_better_reader_re_opens_every_run_it_had_given_up_on(monkeypatch):
    """The recurrence this whole change exists to prevent, arriving through
    its own fix. If the record were not stamped with the reader, improving
    `_stated_overall_grain` would reach new packages only and every existing
    run would stay silently empty."""
    before = job_main.composite_reader_fingerprint()

    from dma_worker import workbook_parser as wp
    monkeypatch.setattr(wp, "_OVERALL_LABELS",
                        wp._OVERALL_LABELS + ("overall_maturity",))
    after = job_main.composite_reader_fingerprint()

    assert after != before, (
        "the fingerprint ignored a change to the reader's own vocabulary, so "
        "every run recorded absent would stay excluded from the work list")


def test_a_backlog_is_capped_per_firing_and_says_what_it_deferred(monkeypatch, capsys):
    """No silent caps. A firing that cannot get through the backlog must name
    what is left, or the log reads as though there was nothing else."""
    from decimal import Decimal

    n = job_main.COMPOSITE_REPAIR_PER_FIRING + 3
    tree = [_f(f"Client {i} - DMA", f"DMA_Scoring_Workbook_{i}.xlsx")
            for i in range(n)]
    groups = job_main._package_groups(tree)
    _stub_reader(monkeypatch, Decimal("2.11"))

    conn = _Conn([(f"run-{i}", f"Client {i} - DMA") for i in range(n)])
    job_main.backfill_composite(conn, "t", groups, forced=False)

    assert len(conn.cur.updated) == job_main.COMPOSITE_REPAIR_PER_FIRING
    assert "3 deferred" in capsys.readouterr().out, \
        "the cap was silent, which reads as an empty backlog"


# ── and the repaired figure has to be PUBLISHED ──────────────────────────

def test_a_filled_composite_refreshes_the_directory(monkeypatch):
    """`serving_directory` is materialised. A repair that commits the value
    and stops has changed nothing anyone can see — the client card keeps its
    empty slot until some unrelated promote happens to rebuild the view."""
    from decimal import Decimal

    tree = [_f("goeasy Ltd - DMA", "DMA_Scoring_Workbook_goeasy.xlsx")]
    groups = job_main._package_groups(tree)
    _stub_reader(monkeypatch, Decimal("2.11"))

    conn = _Conn([("run-gsy", "goeasy Ltd - DMA")])
    job_main.backfill_composite(conn, "t", groups, forced=False)

    assert conn.cur.updated, "nothing was filled, so this test proves nothing"
    assert conn.cur.refreshed == 1, (
        "the composite was written but the materialised directory was never "
        "refreshed, so the card stays blank")


def test_a_pass_that_filled_nothing_does_not_rebuild_the_view(monkeypatch):
    """A refresh is a full rebuild of the view. Every firing paying for one
    when there was nothing to publish is a cost with no reader."""
    tree = [_f("Silent - DMA", "DMA_Scoring_Workbook_S.xlsx")]
    groups = job_main._package_groups(tree)
    _stub_reader(monkeypatch, None, None)

    conn = _Conn([("run-s", "Silent - DMA")])
    job_main.backfill_composite(conn, "t", groups, forced=False)

    assert conn.cur.updated == []
    assert conn.cur.refreshed == 0, "rebuilt the view for nothing"


# ── the run that serves is not always the run holding the folder ─────────

def test_the_work_list_reaches_a_run_that_carries_no_folder_of_its_own():
    """MEASURED 2026-09-04. goeasy Ltd. carries EIGHTEEN runs under one
    request id, every one with a null composite, and the first version of
    this work list — which required `r.source_folder_id IS NOT NULL` —
    matched exactly ONE run across the whole database. The promoted run, the
    only one the directory reads, was invisible to its own repair.

    A sibling under the same request id and entity is the same package by
    definition. Not the entity alone: two assessments of one client are two
    packages, and reading one's composite out of the other's workbook is a
    figure from the wrong run wearing the right name.
    """
    conn = _Conn([])
    job_main.backfill_composite(conn, "t", {}, forced=False)
    sql, _params = conn.cur.selects[0]

    assert "r.source_folder_id IS NOT NULL" not in sql, (
        "the work list still requires the run's own folder, so a re-ingested "
        "run that did not carry it forward can never be repaired")
    assert "COALESCE(r.source_folder_id" in sql, "no fallback to a sibling"
    assert "s.request_id = r.request_id" in sql, \
        "the sibling must be the same PACKAGE, not merely the same client"
    assert "s.entity_id = r.entity_id" in sql, \
        "a request id alone could collide across clients"


def test_a_skipped_run_is_named_not_merely_counted(monkeypatch, capsys):
    """The first production firing said "1 have no workbook artefact" and
    stopped there — which run, and under what key, went unsaid, and the key
    is exactly what goes wrong when a folder is renamed or a package moves."""
    _stub_reader(monkeypatch, None, None)
    conn = _Conn([("run-gsy", "goeasy Ltd. - DMA")])

    job_main.backfill_composite(conn, "t", {}, forced=False)

    out = capsys.readouterr().out
    assert "run-gsy" in out, "the skipped run was not named"
    assert "goeasy Ltd. - DMA" in out, "the key it looked under was not named"


# ── a run that does not know its own package ─────────────────────────────

class _AdoptCursor:
    def __init__(self, orphans):
        self._orphans, self.updated = orphans, []
        self.rows = []

    def execute(self, sql, params=None):
        if "source_folder_id IS NULL" in sql and "SELECT" in sql.split("WHERE")[0]:
            self.rows = list(self._orphans)
        elif "UPDATE runs SET source_folder_id" in sql:
            assert "source_folder_id IS NULL" in sql, \
                "must never overwrite a folder a run already records"
            self.updated.append(params)
        else:                                    # pragma: no cover
            raise AssertionError(f"unexpected sql: {sql[:70]}")

    @property
    def rowcount(self):
        return 1

    def fetchall(self):
        return self.rows


class _AdoptConn:
    def __init__(self, orphans):
        self.cur = _AdoptCursor(orphans)

    def cursor(self):
        return self.cur

    def commit(self):
        pass

    def rollback(self):
        pass


def _manifest_groups(monkeypatch, mapping):
    """{folder -> stated run_id}, served as the package's run_manifest.json."""
    groups, blobs = {}, {}
    for folder, run_id in mapping.items():
        stat = _f(folder, "run_manifest.json")
        groups[folder] = {"folder": folder, "manifest": stat}
        blobs[stat.file_id] = json.dumps({"run_id": run_id}).encode()
    monkeypatch.setattr(job_main.drive, "download",
                        lambda t, fid: blobs[fid])
    return groups


def test_a_folderless_run_is_adopted_by_the_package_that_names_it(monkeypatch):
    """THE ONE THAT MATTERS FOR goeasy. Its promoted run records no source
    folder, so every folder-keyed repair in this file is blind to it. The
    package's own manifest states the run id the ingest stored as
    `request_id` — the package saying which run it produced."""
    groups = _manifest_groups(monkeypatch, {
        "goeasy Ltd. - DMA": "DMA-RES-GSY-20260830-0002",
        "Golden 1 Credit Union - DMA HYBRID": "DMA-2026-GOLDEN1-001",
    })
    conn = _AdoptConn([("run-gsy", "DMA-RES-GSY-20260830-0002")])

    job_main.adopt_orphan_runs(conn, "t", groups)

    assert conn.cur.updated == [("goeasy Ltd. - DMA", "run-gsy")], \
        "the run was not adopted by the package that names it"


def test_two_packages_claiming_one_run_id_adopt_neither(monkeypatch, capsys):
    """Ambiguity is refused, not resolved by order. Attaching a run to the
    wrong client's workbook is worse than leaving it unplaced."""
    groups = _manifest_groups(monkeypatch, {
        "Client A - DMA": "DMA-DUPE-0001",
        "Client B - DMA": "DMA-DUPE-0001",
    })
    conn = _AdoptConn([("run-x", "DMA-DUPE-0001")])

    job_main.adopt_orphan_runs(conn, "t", groups)

    assert conn.cur.updated == [], "adopted an ambiguous run"
    assert "REFUSED" in capsys.readouterr().out, "the refusal was silent"


def test_a_run_whose_request_id_no_package_states_is_left_alone(monkeypatch):
    groups = _manifest_groups(monkeypatch, {"Other - DMA": "DMA-OTHER-1"})
    conn = _AdoptConn([("run-y", "DMA-NOBODY-1")])

    job_main.adopt_orphan_runs(conn, "t", groups)

    assert conn.cur.updated == [], "invented a package for an unplaced run"


def test_the_scheduled_scan_adopts_before_it_repairs(monkeypatch, fakedb):
    """Order is the point: a run that does not know its package cannot be
    repaired by a pass that looks it up by package."""
    order = []
    monkeypatch.setattr(job_main, "adopt_orphan_runs",
                        lambda *a, **k: order.append("adopt") or 0)
    monkeypatch.setattr(job_main, "backfill_composite",
                        lambda *a, **k: order.append("repair") or 0)

    _run_main(monkeypatch, fakedb, TREE)

    assert order == ["adopt", "repair"], f"ran in the wrong order: {order}"


# ── the other half of "non-fatal" ────────────────────────────────────────

def test_a_failed_repair_rolls_back_so_the_scan_still_runs(monkeypatch, fakedb,
                                                           capsys):
    """MEASURED IN PRODUCTION 2026-09-04T12:13:20Z.

    The repairs were already wrapped in `except Exception: print(...)`, and
    that was believed to be enough. It is not. A statement that fails leaves
    PostgreSQL's transaction ABORTED, so every command after it dies `25P02
    current transaction is aborted, commands ignored until end of transaction
    block` — and the very next command is the scan's own
    `SELECT artefact_id, checksum FROM import_files`. One wrong column name
    in the evidence work list took the whole job down with a traceback while
    printing the reassuring line "evidence repair skipped this firing".

    Catching is half. Rolling back is the other half. `FakeDB` models the
    aborted state (`failed_transaction`), so this fails without the rollback
    rather than merely counting a call somebody else might have made."""

    def boom(conn, *a, **kw):
        # exactly what a bad column name does: the statement fails AND the
        # transaction is left aborted behind it.
        conn.failed_transaction = True
        raise RuntimeError("column i.run_id does not exist")

    monkeypatch.setattr(job_main, "backfill_evidence", boom)

    ingested = []

    def _spy(conn, token, folder, parts, remint=False):
        ingested.append(folder)
        return _Res(), []

    rc = _run_main(monkeypatch, fakedb, TREE, ingest=_spy)

    assert ingested == ["goeasy Ltd - DMA"], \
        "the failed repair left the transaction aborted, so the scan after " \
        "it died 25P02 and the job did nothing it exists to do"
    assert rc == 0
    assert fakedb.rollbacks, "nothing rolled the aborted transaction back"
    assert "evidence repair skipped this firing" in capsys.readouterr().out
