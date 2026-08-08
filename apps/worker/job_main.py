"""dmai-worker Cloud Run Job — the package scan (TRD §07, ten steps).

One execution: walk the intake tree, diff against import_scans, and for
every client folder whose scoring workbook is new or changed, assemble
the package (manifest + workbook + report), persist it into the ingested
tier and embed the bundle. Idempotent: an unchanged tree creates nothing.

Env: INTAKE_FOLDER_ID (the General DMAs tree), DB via the Cloud SQL
connector (or LOCAL_DATABASE_URL), EMBED_MODEL_DIR to enable the
embedding pass, MAX_PACKAGES to bound one execution (default 3 — the
Scheduler fires every 30 minutes; steady drain beats a marathon run).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
from datetime import datetime, timezone

from dma_worker import drive, intake_status
from dma_worker.persist import persist_package
from dma_worker.report_parser import parse_report
from dma_worker.scan_runner import (SCAN_FAILED, SCAN_SUCCEEDED, finish_scan,
                                    open_scan, run_scan)
from dma_worker.workbook_parser import (mine_evidence_from_rationales,
                                        parse_evidence_master,
                                        parse_grain_summaries,
                                        parse_peer_benchmarks,
                                        parse_recommendations,
                                        parse_research_workbook,
                                        parse_scoring_workbook)


def _connect():
    if os.environ.get("LOCAL_DATABASE_URL"):
        import pg8000.dbapi
        host = os.environ["LOCAL_DATABASE_URL"].split("@")[1].split(":")[0]
        return pg8000.dbapi.connect(
            user="dmai-worker@digital-maturity-assessor.iam",
            password="local", host=host, port=5432, database="dma_insights")
    from google.cloud.sql.connector import Connector
    return Connector().connect(
        os.environ["DB_INSTANCE_CONNECTION_NAME"], "pg8000",
        user=os.environ["DB_USER"], db=os.environ["DB_NAME"],
        enable_iam_auth=True, ip_type="PRIVATE")


# Artefact naming across the shipped corpus is not standardised — every
# synthesis run named its own files. These lists come from the intake tree
# itself (76 of 105 client folders were being skipped on naming alone).
_WB_DECOYS = ("research", "techstack", "tech_stack", "tech stack",
              "technology_stack", "technology stack", "explorium", "toolkit",
              "weight", "appendix", "template", "tracker")
_RPT_DECOYS = ("profile", "template")


def _classify_artefact(f):
    """(kind, rank) for a package artefact, or None. Lower rank wins when a
    folder holds more than one candidate of a kind: the canonical name beats
    a variant, and a scoring workbook beats an assessment workbook."""
    name = f.name.lower()
    if name.endswith(".json") and "manifest" in name:
        # run_manifest.json canonical; L1_run_manifest.json / MANIFEST.json seen.
        return "manifest", (0 if name == "run_manifest.json" else 1)
    if name.endswith((".xlsx", ".xlsm")):
        # The research workbook is its own artefact, not a decoy. It carries
        # the evidence tier's authority — per-subcap linkage at fact grain,
        # the verbatim passage behind each fact, and the ERS/date ledger the
        # scoring workbook omits — so excluding it left every ingested item
        # undated, unranked and with a scraped excerpt. It never supplies a
        # score; `scoring` remains the only authority for that.
        in_research_folder = any("research" in s.lower() for s in f.path_segments)
        if "research" in name or in_research_folder:
            if "workbook" in name or "research" in name:
                return "research", (0 if "research_workbook" in name else 1)
            return None
        if any(d in name for d in _WB_DECOYS):
            return None
        if "scoring" in name:
            return "workbook", 0
        if "assessment" in name:      # DMA_Assessment_Workbook_<client>.xlsx
            return "workbook", 1
        if "workbook" in name:        # DMA_Workbook_<client>.xlsx
            return "workbook", 2
        return None
    if name.endswith(".docx"):
        if any(d in name for d in _RPT_DECOYS):
            return None              # the research Client Profile is a different artefact
        if "assessment_report" in name or "assessment report" in name:
            return "report", 0
        if name == "report.docx":
            return "report", 1
        if "report" in name:
            return "report", 2
        return None
    return None


def package_key(tree):
    """A stable display key per client folder, from the tree as a whole.

    The key is the folder's NAME, because that is what `runs.source_folder_id`
    stores and what every downstream lookup (backfill, intake status,
    FORCE_FOLDER) matches on — except where a name is not unique. The
    production intake tree carries two distinct folders both called
    "Corporate America Credit Union - DMA", each with its own scoring
    workbook and its own report, and grouping by name merged them into one
    package: one client's workbook was silently discarded on every firing.
    A colliding name is qualified by its source folder id, so both packages
    ingest and both say which folder they came from.
    """
    ids_by_name: dict = {}
    for f in tree:
        name = f.path_segments[0] if f.path_segments else "?"
        ids_by_name.setdefault(name, set()).add(
            f.parent_ids[0] if f.parent_ids else None)
    collided = {n for n, ids in ids_by_name.items() if len(ids) > 1}

    def key(f):
        name = f.path_segments[0] if f.path_segments else "?"
        if name not in collided:
            return name
        return f"{name} [{(f.parent_ids[0] if f.parent_ids else '?')}]"
    key.collisions = {n: sorted(x for x in ids_by_name[n] if x)
                      for n in sorted(collided)}
    return key


def _package_groups(to_process, key=None):
    """Group changed files by client folder and keep the best candidate per
    artefact kind. Returns ALL groups — the caller splits ingestable packages
    from partial ones (a folder whose manifest arrived before its workbook
    must retry, not vanish)."""
    key = key or package_key(to_process)
    groups: dict = {}
    ranks: dict = {}
    for f in to_process:
        root = key(f)
        g = groups.setdefault(root, {"folder": root})
        r = ranks.setdefault(root, {})
        c = _classify_artefact(f)
        if not c:
            continue
        kind, rank = c
        if kind not in g or rank < r[kind]:
            g[kind], r[kind] = f, rank
    return groups


def _requeue(conn, parts, folder, reason):
    """Blank the stored checksums of this package's artefacts so the next
    scan classifies them as CHANGED and retries. Rows are kept (FKs from
    document_sections / parser_observations may point at them)."""
    ids = [parts[k].file_id for k in ("manifest", "workbook", "report")
           if k in parts]
    cur = conn.cursor()
    for fid in ids:
        cur.execute("UPDATE import_files SET checksum = '' WHERE artefact_id = %s",
                    (fid,))
    conn.commit()
    print(f"requeue: {folder} — {reason} ({len(ids)} artefact(s) rescan next firing)")


# A package that cannot be parsed cannot be parsed on the next firing either.
# Blanking its checksums every 30 minutes retried Zions Bancorporation 140
# times against the same ValueError and reported nothing anywhere. Three
# attempts, then the package is quarantined: recorded by name, left out of the
# diff, and surfaced by intake_status. A new upload changes the checksum and
# starts the budget over; FORCE_FOLDER retries it on demand.
MAX_INGEST_ATTEMPTS = int(os.environ.get("MAX_INGEST_ATTEMPTS", "3"))


def _prior_attempts(conn, artefact_id, checksum) -> int:
    """Failed ingests already recorded against this artefact AT THIS CHECKSUM.

    The requeue blanks the checksum, so the live value is '' between the
    failure and the next scan; both the blank and the real checksum count as
    the same package, and only a genuinely different checksum resets."""
    cur = conn.cursor()
    cur.execute(
        """SELECT detail FROM parser_observations
            WHERE artefact_id = %s AND kind = %s ORDER BY occurred_at""",
        (artefact_id, intake_status.PACKAGE_FAILURE_KIND))
    n = 0
    for (detail,) in cur.fetchall():
        d = json.loads(detail) if isinstance(detail, (str, bytes)) else (detail or {})
        if checksum and d.get("checksum") and d["checksum"] not in ("", checksum):
            n = 0                       # a different upload: budget starts over
            continue
        n += 1
    return n


def _record_package_failure(conn, parts, folder, exc) -> bool:
    """Record one failed ingest and decide whether to retry it.

    Returns True when the package was requeued, False when it was
    quarantined. Either way the failure is a row in parser_observations, so
    "why has this folder never produced a run" has an answer that outlives
    the log retention window.
    """
    wb = parts.get("workbook")
    error = f"{type(exc).__name__}: {exc}"[:400]
    attempts = 1
    if wb is not None:
        attempts = _prior_attempts(conn, wb.file_id, wb.checksum) + 1
    quarantined = attempts >= MAX_INGEST_ATTEMPTS
    if wb is not None:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO parser_observations (artefact_id, kind, detail, occurred_at)
               VALUES (%s,%s,%s, now())""",
            (wb.file_id, intake_status.PACKAGE_FAILURE_KIND,
             json.dumps({"folder": folder, "error": error, "attempt": attempts,
                         "checksum": wb.checksum, "quarantined": quarantined})))
        conn.commit()
    if quarantined:
        print(f"quarantine: {folder} — {error} (attempt {attempts} of "
              f"{MAX_INGEST_ATTEMPTS}; not requeued, named by intake status)")
        return False
    _requeue(conn, parts, folder, f"failed: {exc!r} (attempt {attempts} of "
                                  f"{MAX_INGEST_ATTEMPTS})")
    return True


def _ingest_one(conn, token, folder, parts, remint=False):
    """Download, parse and persist one package. Atomic: persist_package
    commits once at the end, so an exception anywhere leaves nothing."""
    with tempfile.TemporaryDirectory() as td:
        # The scoring workbook is the authority; a package that ships no
        # manifest still ingests, with identity from the folder name (the
        # cascade's signal 4 → PENDING_REVIEW) and an observation recorded.
        if "manifest" in parts:
            # utf-8-sig: some shipped manifests carry a BOM
            manifest = json.loads(
                drive.download(token, parts["manifest"].file_id).decode("utf-8-sig"))
        else:
            manifest = {}
        wb_path = os.path.join(td, "wb.xlsx")
        with open(wb_path, "wb") as fh:
            fh.write(drive.download(token, parts["workbook"].file_id))
        sections = []
        if "report" in parts:
            rp = os.path.join(td, "report.docx")
            with open(rp, "wb") as fh:
                fh.write(drive.download(token, parts["report"].file_id))
            sections = parse_report(rp)

        research = {}
        companion: list = []
        if "research" in parts:
            rw_path = os.path.join(td, "research.xlsx")
            with open(rw_path, "wb") as fh:
                fh.write(drive.download(token, parts["research"].file_id))
            research = parse_research_workbook(rw_path, companion)
            print(f"ingest: {folder} research workbook — "
                  f"{len(research.get('ledger') or [])} ledger rows, "
                  f"{len(research.get('links') or [])} linked cells, "
                  f"{len(research.get('absent') or [])} recorded absences")

        wb = parse_scoring_workbook(wb_path)
        # Every companion tab appends what it could not read to one list; the
        # persist writes them as parser_observations against the run, so a tab
        # the parser did not recognise leaves a record naming the tab, the
        # column and the spelling it expected — not an absent section.
        res = persist_package(
            conn,
            manifest=manifest,
            workbook=wb,
            source_folder_id=folder,
            evidence=parse_evidence_master(wb_path, companion),
            peers=parse_peer_benchmarks(wb_path, companion),
            recommendations=parse_recommendations(wb_path, companion),
            companion_observations=companion,
            artefact_id=parts["workbook"].file_id,
            # The bytes this run was read from. A requeue blanks the live
            # checksum in import_files, so the run keeps its own copy and a
            # retry of an unchanged package resolves to the run it already
            # produced instead of minting a second one.
            artefact_checksum=parts["workbook"].checksum,
            remint=remint,
            sections=sections,
            report_artefact_id=(parts["report"].file_id
                                if "report" in parts else None),
            grains=parse_grain_summaries(wb_path),
            research=research,
        )
        rationales = {s.subcap_id: s.rationale for s in wb.scores if s.rationale}
        return res, rationales


def backfill_sections(conn, token, groups) -> int:
    """One-time recovery for runs ingested before packages were assembled
    from the whole tree: those runs hold no document_sections because their
    report was never in the changed set. Re-parsing the report and
    inserting the sections against the EXISTING run is additive — nothing
    else in the ingested tier is touched, and no duplicate run is created.

    Matched on runs.source_folder_id, which stores the client folder's
    name. A run that already has sections is left alone (idempotent), and
    so is a folder that ships no report."""
    cur = conn.cursor()
    cur.execute("""SELECT r.id, r.source_folder_id
                     FROM runs r
                    WHERE r.source_folder_id IS NOT NULL
                      AND NOT EXISTS (SELECT 1 FROM document_sections d
                                       WHERE d.run_id = r.id)
                    ORDER BY r.source_folder_id""")
    todo = cur.fetchall()
    print(f"backfill: {len(todo)} run(s) with no report sections")
    filled = skipped = failed = 0
    for run_id, folder in todo:
        parts = groups.get(folder) or {}
        if "report" not in parts:
            skipped += 1
            continue
        try:
            with tempfile.TemporaryDirectory() as td:
                rp = os.path.join(td, "report.docx")
                with open(rp, "wb") as fh:
                    fh.write(drive.download(token, parts["report"].file_id))
                sections = parse_report(rp)
            for sec in sections:
                cur.execute(
                    """INSERT INTO document_sections
                         (run_id, section_kind, pillar_id, heading, body, page,
                          artefact_id)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (run_id, sec.section_kind, sec.pillar_id, sec.heading,
                     sec.body, sec.page, parts["report"].file_id))
            conn.commit()
            print(f"backfill: {folder} -> {len(sections)} sections")
            filled += 1
        except Exception as exc:  # noqa: BLE001 — one bad report must not sink the pass
            conn.rollback()
            failed += 1
            print(f"backfill FAILED: {folder}: {exc!r}")
    print(f"backfill: {filled} filled, {skipped} have no report artefact, "
          f"{failed} failed")
    return 1 if failed else 0


def backfill_evidence(conn, token, groups) -> int:
    """Fill in the evidence text that already-ingested rows never got.

    Evidence rows insert with ON CONFLICT DO NOTHING, so re-ingesting a
    package cannot repair one — and every row ingested before the ledger's real
    column names were understood holds a tier and nothing else. This re-parses
    each run's workbook and fills ONLY the columns that are still null:
    source_name, source_url, excerpt, claim_type. A value the package already
    stated is never overwritten, so the pass is additive and idempotent.

    Matched on runs.source_folder_id, which stores the client folder's name.
    """
    cur = conn.cursor()
    cur.execute("""SELECT r.id, r.entity_id, r.source_folder_id, r.run_seq
                     FROM runs r
                    WHERE r.source_folder_id IS NOT NULL
                    ORDER BY r.source_folder_id""")
    todo = cur.fetchall()
    print(f"backfill-evidence: {len(todo)} run(s)")
    filled = skipped = failed = 0
    for run_id, entity_id, folder, run_seq in todo:
        parts = groups.get(folder) or {}
        if "workbook" not in parts:
            skipped += 1
            continue
        try:
            with tempfile.TemporaryDirectory() as td:
                p = os.path.join(td, "wb.xlsx")
                with open(p, "wb") as fh:
                    fh.write(drive.download(token, parts["workbook"].file_id))
                ledger = parse_evidence_master(p)
                wb = parse_scoring_workbook(p)
            mined = mine_evidence_from_rationales(wb.scores)
            n = clashes = 0
            for ev in ledger:
                m = mined.get(ev["e_id"]) or {}
                excerpt = ev.get("excerpt") or m.get("excerpt")
                # Match on ORIGIN and the id's numeric suffix, not on a
                # reconstructed entity token: the ingest takes the token from
                # the manifest, which the backfill does not read, and reading
                # one back off an arbitrary existing id picks up the
                # connector's own E-CC-nnn namespace instead. origin='package'
                # is exactly the set the ingest created from this ledger.
                suffix = ev["e_id"].split("-")[-1]
                # A savepoint per row: filling in an excerpt can collide with
                # the (entity_id, content_hash) dedup index when two ledger
                # rows cite the same url and fact. That is a real duplicate,
                # recorded and skipped — it must not sink the whole run.
                cur.execute("SAVEPOINT ev_row")
                try:
                    cur.execute(
                        """UPDATE evidence_index
                              SET source_name = COALESCE(source_name, %s),
                                  source_url  = COALESCE(source_url, %s),
                                  excerpt     = COALESCE(excerpt, %s),
                                  claim_type  = COALESCE(claim_type, %s)
                            WHERE entity_id = %s
                              AND origin = 'package'
                              AND split_part(e_id, '-', 3) = %s""",
                        (ev.get("source_name"), ev.get("source_url"), excerpt,
                         ev.get("claim_type"), entity_id, suffix))
                    n += cur.rowcount or 0
                    cur.execute("RELEASE SAVEPOINT ev_row")
                except Exception:       # noqa: BLE001 — one row, not the run
                    cur.execute("ROLLBACK TO SAVEPOINT ev_row")
                    clashes += 1
            if clashes:
                cur.execute(
                    """INSERT INTO parser_observations (run_id, kind, detail, occurred_at)
                       VALUES (%s,'evidence_backfill_dedup_clash',%s, now())""",
                    (run_id, json.dumps({"rows_skipped": clashes,
                                         "reason": "filling the excerpt would "
                                                   "duplicate (entity, content_hash)"})))
            conn.commit()
            print(f"backfill-evidence: {folder} -> {n} row(s) filled "
                  f"({sum(1 for v in mined.values() if v.get('excerpt'))} mined "
                  f"excerpts{f', {clashes} dedup clash(es)' if clashes else ''})")
            filled += 1
        except Exception as exc:  # noqa: BLE001 — one bad workbook sinks nothing
            conn.rollback()
            failed += 1
            print(f"backfill-evidence FAILED: {folder}: {exc!r}")
    print(f"backfill-evidence: {filled} runs filled, {skipped} without a "
          f"workbook, {failed} failed")
    return 1 if failed else 0



def dump_headers(token, groups, needle: str) -> int:
    """Print every tab's first non-empty rows for one package's workbook.

    A diagnostic, not a pipeline step: the corpus does not standardise column
    names any more than it standardises file names, and a parser cannot be
    made tolerant of spellings nobody has read. Prints the first three rows of
    each tab so a header row that sits under a title row is still visible.
    """
    import openpyxl
    matches = [k for k in groups if needle.lower() in k.lower()
               and "workbook" in groups[k]]
    if not matches:
        print(f"dump: no package folder matching {needle!r}")
        return 1
    folder = sorted(matches)[0]
    print(f"dump: {folder}")
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "wb.xlsx")
        with open(p, "wb") as fh:
            fh.write(drive.download(token, groups[folder]["workbook"].file_id))
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        try:
            print(f"dump: tabs = {wb.sheetnames}")
            for name in wb.sheetnames:
                ws = wb[name]
                print(f"--- {name}")
                for i, row in enumerate(
                        ws.iter_rows(min_row=1, max_row=3, values_only=True), 1):
                    cells = [str(v).strip() for v in row if v is not None
                             and str(v).strip()]
                    if cells:
                        print(f"    r{i}: {cells[:22]}")
        finally:
            wb.close()
    return 0


def report_intake_status(conn, tree) -> int:
    """Name every intake folder that is not yet serving, and why.

    The routine's first question — "is there anything to synthesise, and is
    anything stuck?" — had no answer anywhere in the system: the folder list
    lives in Drive and the progress lives in Postgres, and nothing joined
    them. INTAKE_STATUS=1 (or =json) prints that join.
    """
    artefacts = {k: set(v) for k, v in _package_groups(tree).items()}
    states = intake_status.intake_status(conn, sorted(artefacts), artefacts)
    if (os.environ.get("INTAKE_STATUS") or "").lower() == "json":
        print(intake_status.as_json(states))
    else:
        print(intake_status.render(states))
    return 0


def main() -> int:
    intake = os.environ["INTAKE_FOLDER_ID"]
    limit = int(os.environ.get("MAX_PACKAGES", "3"))

    # The header dump touches Drive and nothing else, so it runs before the
    # connection and before the scan lock. Taking the lock for a read-only
    # diagnostic just means it loses a race with the Scheduler and reports
    # nothing.
    if os.environ.get("DUMP_HEADERS"):
        print(f"scan: walking intake tree {intake}")
        tree = drive.walk_tree(intake)
        return dump_headers(drive.metadata_token(), _package_groups(tree),
                            os.environ["DUMP_HEADERS"])

    conn = _connect()

    # One scan at a time: the Scheduler fires every 30 minutes and manual
    # executions overlap it. The session-level lock releases when this
    # connection closes (or the container dies) — a second execution
    # exits clean instead of racing the diff into duplicate runs.
    cur = conn.cursor()
    cur.execute("SELECT pg_try_advisory_lock(815002)")
    if not cur.fetchone()[0]:
        print("scan: another execution holds the scan lock; exiting")
        conn.close()
        return 0

    # W2 — evidence→subcap link proposals: an ON-DEMAND pass for the
    # scheduled session, never part of the scan flow. LINK_PROPOSE_RUN_ID=
    # <run uuid> (plus LINK_PROPOSE_DRY_RUN=1 to report without writing)
    # runs the propose-only matcher against that run and exits without
    # touching the intake tree. CLI equivalent:
    # python -m dma_worker.link_propose --run-id <uuid>.
    if os.environ.get("LINK_PROPOSE_RUN_ID"):
        from dma_worker.link_propose import run_from_env
        rc = run_from_env(conn)
        conn.close()
        return rc

    if os.environ.get("RESET_SCAN"):
        # One-time recovery: blank every stored checksum so the whole tree
        # rescans as CHANGED. Rows are kept — FKs may point at them, and
        # already-ingested artefacts re-persist as a new run only if their
        # packages truly reprocess.
        cur = conn.cursor()
        cur.execute("UPDATE import_files SET checksum = ''")
        conn.commit()
        print(f"RESET_SCAN: blanked {cur.rowcount} stored checksums; "
              "full tree rescans this execution")

    # Read-only pass over the intake tree and the ingested tier: what has
    # not been processed, by folder name and with the blocker named. Runs
    # before the scan row is opened — it is a question, not a firing.
    if os.environ.get("INTAKE_STATUS"):
        print(f"scan: walking intake tree {intake}")
        rc = report_intake_status(conn, drive.walk_tree(intake))
        conn.close()
        return rc

    # A backfill is not a scan and must not write a scan row; everything
    # else from here on is one, and gets its row BEFORE the walk so a walk
    # that dies is recorded rather than invisible (the 403 that killed the
    # tree recursion left no import_scans row at all).
    diagnostic = bool(os.environ.get("BACKFILL_SECTIONS")
                      or os.environ.get("BACKFILL_EVIDENCE"))
    started_at = datetime.now(timezone.utc)
    scan_id = None if diagnostic else open_scan(conn, started_at)
    tally = {"ingested": 0, "failed": 0, "deferred": 0, "quarantined": []}
    try:
        print(f"scan: walking intake tree {intake}")
        tree = drive.walk_tree(intake)
        print(f"scan: {len(tree)} files")

        # Assemble packages from the WHOLE tree, and let the diff decide which
        # folders to process. Assembling from the changed set only meant a
        # folder whose workbook changed but whose report did not lost its
        # report — no run has ever landed its twelve report sections — and a
        # folder with a changed report but an unchanged workbook looked
        # incomplete on every firing.
        key = package_key(tree)
        groups = _package_groups(tree, key)
        for name, ids in key.collisions.items():
            print(f"folder-name collision: {name!r} is {len(ids)} distinct "
                  f"folders ({', '.join(ids)}); each ingests under its own "
                  "id-qualified key rather than one overwriting the other")

        # Backfill runs BEFORE the scan and returns: run_scan stores the new
        # checksums, so a backfill executed after it would swallow that
        # firing's diff and the changed packages would never be ingested.
        if os.environ.get("BACKFILL_SECTIONS"):
            rc = backfill_sections(conn, drive.metadata_token(), groups)
            conn.close()
            return rc

        if os.environ.get("BACKFILL_EVIDENCE"):
            rc = backfill_evidence(conn, drive.metadata_token(), groups)
            conn.close()
            return rc

        _scan_and_ingest(conn, scan_id, tree, groups, started_at, limit, tally,
                         key)
    except BaseException as exc:            # noqa: BLE001 — record, then re-raise
        # Anything that escapes — the Drive walk that 403'd mid-recursion, the
        # empty-tree guard, a diff that could not commit — closes the scan row
        # as failed with the exception naming itself. This is the whole point:
        # a scan row must never say `succeeded` about an execution that raised.
        traceback.print_exc()
        try:
            finish_scan(conn, scan_id, status=SCAN_FAILED,
                        error=f"{type(exc).__name__}: {exc}"[:2000],
                        runs_created=tally["ingested"])
        except Exception as inner:          # noqa: BLE001
            print(f"scan: could not record the failure: {inner!r}")
        conn.close()
        if isinstance(exc, Exception):
            return 1
        raise

    # The traversal completed. It "succeeded" only if nothing inside it
    # failed: a package that raised is a failed firing, named in the row.
    reasons = []
    if tally["failed"]:
        reasons.append(f"{tally['failed']} package(s) failed to ingest")
    if tally["quarantined"]:
        reasons.append("quarantined: " + ", ".join(sorted(tally["quarantined"])))
    finish_scan(conn, scan_id,
                status=SCAN_FAILED if tally["failed"] else SCAN_SUCCEEDED,
                error="; ".join(reasons)[:2000] or None,
                runs_created=tally["ingested"])
    conn.close()
    print(f"done: {tally['ingested']} ingested, {tally['failed']} failed, "
          f"{tally['deferred']} deferred, {len(tally['quarantined'])} quarantined")
    return 1 if tally["failed"] else 0


def _scan_and_ingest(conn, scan_id, tree, groups, started_at, limit, tally,
                     key=None) -> None:
    """The diff and the ingest loop. Counters land in `tally` as they happen,
    so a mid-loop exception still reports the runs it had already created."""
    summary = run_scan(conn, tree, started_at, scan_id=scan_id)
    print(f"scan: new={summary['files_new']} changed={summary['files_changed']}")
    key = key or package_key(tree)
    touched = {key(f) for f in summary["to_process"]}
    # Re-ingest one named folder even though its tree has not changed. The
    # diff is the right default — an unchanged tree must create nothing — but
    # after a parser fix the tree is unchanged and the extraction is not, and
    # RESET_SCAN is too blunt: it rescans every client and mints runs for
    # whichever three the bound happens to reach. Substring match, so the
    # folder's display name is enough.
    force = (os.environ.get("FORCE_FOLDER") or "").strip()
    forced: set = set()
    if force:
        matched = {k for k in groups if force.lower() in k.lower()}
        forced = set(matched)
        if matched:
            touched |= matched
            print(f"FORCE_FOLDER={force!r}: re-ingesting {sorted(matched)}")
        else:
            print(f"FORCE_FOLDER={force!r}: no folder matched; nothing forced")
    # The scoring workbook is what makes a package ingestable; the manifest
    # and report are enriching, not gating.
    packages = {k: v for k, v in groups.items() if "workbook" in v and k in touched}
    partial = {k: v for k, v in groups.items()
               if k in touched and "workbook" not in v
               and any(a in v for a in ("manifest", "report"))}
    if not packages and not partial:
        print("scan: nothing to ingest (unchanged tree creates nothing)")
        return

    token = drive.metadata_token()
    encoder = None
    for folder, parts in sorted(packages.items()):
        if tally["ingested"] >= limit:
            _requeue(conn, parts, folder, "over per-execution bound")
            tally["deferred"] += 1
            continue
        print(f"ingest: {folder}")
        try:
            # A named re-ingest is a deliberate re-read after a parser fix
            # and mints a run. Everything else is the scan retrying itself,
            # and an unchanged package must resolve to the run it already
            # produced rather than duplicate it.
            res, rationales = _ingest_one(conn, token, folder, parts,
                                          remint=folder in forced)
        except Exception as exc:  # noqa: BLE001 — one bad package must not sink the batch
            conn.rollback()
            tally["failed"] += 1
            traceback.print_exc()
            if not _record_package_failure(conn, parts, folder, exc):
                tally["quarantined"].append(folder)
            continue
        print(f"ingest: {folder} -> run {res.run_id} "
              f"({res.scored_cells} cells, {res.observations} observations)")
        tally["ingested"] += 1

        # Embedding failures never requeue: the run is persisted, and V4
        # abstains (recorded NOT_RUN) where centroids are thin. Requeueing
        # here would re-persist the package as a duplicate run.
        if os.environ.get("EMBED_MODEL_DIR"):
            try:
                if encoder is None:
                    from dma_worker.embed import minilm_encoder
                    encoder = minilm_encoder(os.environ["EMBED_MODEL_DIR"])
                from dma_worker.embed import embed_run
                stats = embed_run(conn, res.run_id, encoder, rationales)
                print(f"embed: {stats['embeddings']} vectors, "
                      f"{stats['centroids']} centroids")
            except Exception as exc:  # noqa: BLE001
                conn.rollback()
                print(f"embed FAILED (run kept, V4 will abstain): {folder}: {exc!r}")

    for folder, parts in sorted(partial.items()):
        # NOT requeued: the folder holds no scoring workbook at all, and
        # blanking its checksums would re-detect the same folder on every
        # firing forever. A real change in Drive puts it back in the diff.
        print(f"no workbook: {folder} — {sorted(k for k in parts if k != 'folder')} "
              "present, nothing to score")


if __name__ == "__main__":
    sys.exit(main())
