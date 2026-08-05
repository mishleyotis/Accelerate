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


def _package_paths(to_process):
    """Group changed files by client folder (the first path segment) and
    keep the ones a package needs, by artefact kind."""
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
    return {k: v for k, v in groups.items() if "manifest" in v and "workbook" in v}


def main() -> int:
    intake = os.environ["INTAKE_FOLDER_ID"]
    limit = int(os.environ.get("MAX_PACKAGES", "3"))
    conn = _connect()

    print(f"scan: walking intake tree {intake}")
    tree = drive.walk_tree(intake)
    print(f"scan: {len(tree)} files")
    summary = run_scan(conn, tree, datetime.now(timezone.utc))
    print(f"scan: new={summary['files_new']} changed={summary['files_changed']}")

    packages = _package_paths(summary["to_process"])
    if not packages:
        print("scan: nothing to ingest (unchanged tree creates nothing)")
        return 0

    token = drive.metadata_token()
    done = 0
    encoder = None
    for folder, parts in sorted(packages.items()):
        if done >= limit:
            print(f"bounded: {len(packages) - done} package(s) left for the "
                  "next firing")
            break
        print(f"ingest: {folder}")
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

            res = persist_package(
                conn,
                manifest=manifest,
                workbook=parse_scoring_workbook(wb_path),
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
            print(f"ingest: {folder} -> run {res.run_id} "
                  f"({res.scored_cells} cells, {res.observations} observations)")

            if os.environ.get("EMBED_MODEL_DIR"):
                if encoder is None:
                    from dma_worker.embed import minilm_encoder
                    encoder = minilm_encoder(os.environ["EMBED_MODEL_DIR"])
                from dma_worker.embed import embed_run
                wb = parse_scoring_workbook(wb_path)
                rationales = {s.subcap_id: s.rationale
                              for s in wb.scores if s.rationale}
                stats = embed_run(conn, res.run_id, encoder, rationales)
                print(f"embed: {stats['embeddings']} vectors, "
                      f"{stats['centroids']} centroids")
            done += 1

    conn.close()
    print(f"done: {done} package(s) ingested")
    return 0


if __name__ == "__main__":
    sys.exit(main())
