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
from datetime import datetime, timezone

from dma_worker import drive
from dma_worker.persist import persist_package
from dma_worker.report_parser import parse_report
from dma_worker.scan_runner import run_scan
from dma_worker.workbook_parser import (parse_evidence_master,
                                        parse_grain_summaries,
                                        parse_peer_benchmarks,
                                        parse_recommendations,
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


def _package_groups(to_process):
    """Group changed files by client folder (the first path segment) and
    keep the ones a package needs, by artefact kind. Returns ALL groups —
    the caller splits complete packages from partial ones (a folder whose
    manifest arrived before its workbook must retry, not vanish)."""
    groups: dict = {}
    for f in to_process:
        root = f.path_segments[0] if f.path_segments else "?"
        g = groups.setdefault(root, {})
        name = f.name.lower()
        if name == "run_manifest.json":
            g["manifest"] = f
        elif (name.endswith(".xlsx") and "scoring" in name
              and not any("research" in s.lower() for s in f.path_segments)):
            g["workbook"] = f
        elif name == "report.docx":
            g["report"] = f
        g.setdefault("folder", root)
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


def _ingest_one(conn, token, folder, parts):
    """Download, parse and persist one package. Atomic: persist_package
    commits once at the end, so an exception anywhere leaves nothing."""
    with tempfile.TemporaryDirectory() as td:
        manifest = json.loads(drive.download(token, parts["manifest"].file_id))
        wb_path = os.path.join(td, "wb.xlsx")
        with open(wb_path, "wb") as fh:
            fh.write(drive.download(token, parts["workbook"].file_id))
        sections = []
        if "report" in parts:
            rp = os.path.join(td, "report.docx")
            with open(rp, "wb") as fh:
                fh.write(drive.download(token, parts["report"].file_id))
            sections = parse_report(rp)

        wb = parse_scoring_workbook(wb_path)
        res = persist_package(
            conn,
            manifest=manifest,
            workbook=wb,
            source_folder_id=folder,
            evidence=parse_evidence_master(wb_path),
            peers=parse_peer_benchmarks(wb_path),
            recommendations=parse_recommendations(wb_path),
            artefact_id=parts["workbook"].file_id,
            sections=sections,
            report_artefact_id=(parts["report"].file_id
                                if "report" in parts else None),
            grains=parse_grain_summaries(wb_path),
        )
        rationales = {s.subcap_id: s.rationale for s in wb.scores if s.rationale}
        return res, rationales


def main() -> int:
    intake = os.environ["INTAKE_FOLDER_ID"]
    limit = int(os.environ.get("MAX_PACKAGES", "3"))
    conn = _connect()

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

    print(f"scan: walking intake tree {intake}")
    tree = drive.walk_tree(intake)
    print(f"scan: {len(tree)} files")
    summary = run_scan(conn, tree, datetime.now(timezone.utc))
    print(f"scan: new={summary['files_new']} changed={summary['files_changed']}")

    groups = _package_groups(summary["to_process"])
    packages = {k: v for k, v in groups.items()
                if "manifest" in v and "workbook" in v}
    partial = {k: v for k, v in groups.items() if k not in packages
               and any(a in v for a in ("manifest", "workbook", "report"))}
    if not packages and not partial:
        print("scan: nothing to ingest (unchanged tree creates nothing)")
        conn.close()
        return 0

    token = drive.metadata_token()
    done = failed = deferred = 0
    encoder = None
    for folder, parts in sorted(packages.items()):
        if done >= limit:
            _requeue(conn, parts, folder, "over per-execution bound")
            deferred += 1
            continue
        print(f"ingest: {folder}")
        try:
            res, rationales = _ingest_one(conn, token, folder, parts)
        except Exception as exc:  # noqa: BLE001 — one bad package must not sink the batch
            conn.rollback()
            failed += 1
            _requeue(conn, parts, folder, f"failed: {exc!r}")
            continue
        print(f"ingest: {folder} -> run {res.run_id} "
              f"({res.scored_cells} cells, {res.observations} observations)")
        done += 1

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
        _requeue(conn, parts, folder, "incomplete package (waiting for the rest)")

    conn.close()
    print(f"done: {done} ingested, {failed} failed (requeued), "
          f"{deferred} deferred, {len(partial)} incomplete")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
