"""POST /api/v1/ingest/package — admin-only DMA package upload.

Accepts a `{Entity}_DMA_Complete_Package.zip` (the canonical bundle the
Claude project pipeline emits) and persists everything to the DB. This
is the production path for the user-driven "Re-run" flow and for
backfilling the 115 historical assessments.

Two endpoints:
  POST /api/v1/ingest/package
       Multipart form upload of a .zip; extracts to tempdir, parses,
       persists, returns the new run_id + counts.

  POST /api/v1/ingest/package/folder
       Admin-only sanity check: takes a JSON body `{"path": "/abs/path"}`
       pointing at an already-extracted package folder on disk (useful
       during development + the one-shot historical backfill worker).

State-branch contract:
  - happy path     → 201 IngestPackageAck with run_id + counts
  - bad zip        → 400 detail="invalid zip"
  - missing layout → 400 detail="no DMA package detected …"
  - parse warnings → 201 with warnings array (does NOT fail)
"""
from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.deps import SessionDep, require_admin
from app.services.parsers.dma_package import parse_package
from app.services.parsers.package_persist import (
    persist_package,
    publish_post_commit,
)

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])

# Real DMA Complete-Package zips emitted by the n8n pipeline reach
# ~100 MB compressed — `05_narrative_deck/*.pptx` is typically 55-65 MB
# on its own. We don't parse the deck, so the per-entry cap (now in
# app.services.zip_guard) evaluates the *post-prune* zip (deck
# excluded). The 100 MB ceiling bounds the compressed transport size.
_MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB compressed ceiling
_UPLOAD_CHUNK_BYTES = 1 * 1024 * 1024  # 1 MiB streaming reads

# Zip-extraction guards live in app.services.zip_guard (framework-free)
# because the WORKER backfill path shares them and the workers image
# does not install fastapi (2026-06-10 incident: importing this router
# from the worker crashed every Drive folder ingest). Re-exported here
# so existing imports/tests keep working.
from app.services.zip_guard import (  # noqa: E402
    _MAX_PER_ENTRY_UNCOMPRESSED_BYTES,
    _MAX_UNCOMPRESSED_TOTAL_BYTES,
    _zip_entry_should_skip,
)

# 2026-05-28 audit fix (Probe 14): folder ingest accepts a server-
# filesystem path -- without an allowlist an authenticated admin
# could traverse the container's filesystem. Restrict to: (a) local
# dev (anything goes), or (b) explicit allowlist of canonical paths
# in production. The allowlist below covers the directories the
# historical_backfill job extracts Drive folders to + the
# tests/fixtures path operators use for re-ingest debugging.
_FOLDER_INGEST_ALLOWLIST = (
    "/tmp/dma-backfill",
    "/var/dma/staging",
    "/home/app/tests/fixtures/dma_packages_sanitized",
)


def _folder_ingest_path_is_allowed(path: Path) -> bool:
    """Returns True when `path` is acceptable for /package/folder.

    Self-healing contract:
      - env=local / env=test  → accept any existing directory (dev/CI)
      - env=prod / env=dev    → accept only paths under
                                `_FOLDER_INGEST_ALLOWLIST` AND require
                                the resolved path to NOT escape via
                                symlinks (resolve() guards against
                                /tmp/dma-backfill -> /etc symlink).
    """
    from app.config import get_settings
    settings = get_settings()
    if settings.env in ("local", "test"):
        return True
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        return False
    for prefix in _FOLDER_INGEST_ALLOWLIST:
        prefix_resolved = Path(prefix).resolve()
        try:
            resolved.relative_to(prefix_resolved)
            return True
        except ValueError:
            continue
    return False


class IngestPackageAck(BaseModel):
    run_id: str
    request_id: str
    institution: str
    subcap_count: int
    evidence_count: int
    recommendation_count: int
    peer_count: int
    issue_count: int
    tech_count: int
    warnings: list[str] = Field(default_factory=list)


class FolderIngestRequest(BaseModel):
    path: str


def _ingest_from_path(path: Path):
    return parse_package(path)


async def _read_capped(file: UploadFile, limit: int) -> bytes:
    """Stream the upload in `_UPLOAD_CHUNK_BYTES` chunks, raising 413
    the moment cumulative bytes exceed `limit`.

    Why not just `await file.read()`: when the caller uses chunked
    transfer encoding (Transfer-Encoding: chunked) the Content-Length
    header is absent and `file.size` is None. The earlier code happily
    buffered the entire body into memory before checking the cap --
    a hostile caller could OOM the Cloud Run instance by streaming a
    multi-GB body. Streaming + per-chunk accounting fail-closes the
    moment the limit is crossed; the connection is dropped server-side
    via the exception.
    """
    buf = io.BytesIO()
    total = 0
    while True:
        chunk = await file.read(_UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=(
                    f"upload exceeds {limit // (1024 * 1024)} MB "
                    f"(streamed past cap at {total // (1024 * 1024)} MB)"
                ),
            )
        buf.write(chunk)
    return buf.getvalue()


@router.post(
    "/package",
    response_model=IngestPackageAck,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def ingest_package_zip(
    session: SessionDep,
    file: UploadFile = File(..., description="DMA package zip"),  # noqa: B008 — FastAPI Depends
) -> IngestPackageAck:
    # Pre-flight via Content-Length when available (chunked uploads
    # report size=None). _read_capped enforces the same limit on the
    # streamed body regardless.
    if file.size is not None and file.size > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"upload exceeds {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )
    blob = await _read_capped(file, _MAX_UPLOAD_BYTES)
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile as e:
        raise HTTPException(status_code=400, detail=f"invalid zip: {e!s}") from e

    # Collect parser warnings from extraction phase (duplicate entries
    # etc.) so they can be merged into the persist_package warnings
    # downstream.
    pre_extract_warnings: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        # Strict extraction — reject zip-slip, oversize-per-entry,
        # symlinks, AND cumulative-decompression bomb.
        # 2026-05-28 audit fix (Probe 14): added symlink rejection +
        # duplicate-filename warning. The previous loop only checked
        # path-traversal via filename + per-entry size; symlink entries
        # passed because `Path.is_relative_to` doesn't follow them.
        # A symlink inside a zip can point at any path on the host
        # filesystem when extracted -- including /etc/passwd or
        # /cloudsql/* — so we explicitly reject them.
        cumulative_uncompressed = 0
        seen_names: set[str] = set()
        # Two-pass extraction: first VALIDATE every entry; then EXTRACT
        # only the entries we don't skip. Skipping decks before the
        # per-entry size gate is what lets a real complete DMA package
        # (with a 59 MB pptx) ingest cleanly.
        entries_to_extract = []
        for info in zf.infolist():
            target = td_path / info.filename
            if not target.resolve().is_relative_to(td_path.resolve()):
                raise HTTPException(status_code=400, detail="zip slip detected")
            # ZIP external_attr encodes Unix file mode in bits 16-31;
            # symlink mode is 0o120000 (S_IFLNK). Reject any entry
            # carrying that mode.
            unix_mode = (info.external_attr >> 16) & 0xFFFF
            if unix_mode and (unix_mode & 0o170000) == 0o120000:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"zip entry `{info.filename}` is a symlink — "
                        "rejected (would escape extraction sandbox)"
                    ),
                )
            if info.filename in seen_names:
                # Duplicates aren't fatal (zipfile extractall just
                # overwrites) but we surface them so an operator can
                # spot a malformed package vs an intentional layered
                # zip. parser_warnings is the canonical surface.
                pre_extract_warnings.append(
                    f"duplicate_zip_entry:{info.filename}"
                )
            seen_names.add(info.filename)
            # Skip non-ingested artifacts (decks, slides) BEFORE size
            # gates. Real DMA packages carry 50-65 MB pptx decks which
            # the parsers never touch; rejecting them at upload would
            # block every real complete package.
            if _zip_entry_should_skip(info.filename):
                pre_extract_warnings.append(
                    f"skipped_non_ingested_artifact:{info.filename}"
                )
                continue
            if info.file_size > _MAX_PER_ENTRY_UNCOMPRESSED_BYTES:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"oversize zip entry `{info.filename}` "
                        f"({info.file_size // (1024 * 1024)} MB > "
                        f"{_MAX_PER_ENTRY_UNCOMPRESSED_BYTES // (1024 * 1024)} MB "
                        "per-parsed-entry cap)"
                    ),
                )
            cumulative_uncompressed += info.file_size
            if cumulative_uncompressed > _MAX_UNCOMPRESSED_TOTAL_BYTES:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"cumulative decompressed size exceeds "
                        f"{_MAX_UNCOMPRESSED_TOTAL_BYTES // (1024 * 1024)} MB "
                        "(zip-bomb defence)"
                    ),
                )
            entries_to_extract.append(info)
        # Extract ONLY the validated, non-skipped entries. extractall()
        # would re-extract the deck PPTX we just skipped, so iterate.
        for info in entries_to_extract:
            zf.extract(info, td_path)
        try:
            pkg = _ingest_from_path(td_path)
        except (FileNotFoundError, ValueError) as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        # 2026-05-29 audit fix: fold extraction-phase warnings into the
        # parsed package's parser_warnings BEFORE persist so they land on
        # `runs.parser_warnings` (Admin Import Audit + D1 chip). Prior
        # code only added them to the HTTP response payload, so the
        # operator-visible audit trail dropped skipped-deck +
        # duplicate-zip-entry warnings forever.
        pkg.parser_warnings = list(pkg.parser_warnings) + pre_extract_warnings
        # Strict ingest gate (operator mandate 2026-06-10): ONLY fully-
        # scored deliverables are ingested. A 0-subcap-score package
        # would only render hollow/partial surfaces, so reject here;
        # the backfill paths apply the identical gate
        # (app/scripts/historical_backfill.py::_is_pre_subcap_framework)
        # and quarantine the folder for automatic Drive re-pick once
        # the scored deliverable lands.
        if not (pkg.subcap_scores or []):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "dropped: package has 0 subcap scores (pre-subcap DMA "
                    "framework — not ingested)"
                ),
            )
        run_id, warnings = await persist_package(session, pkg)
        # `warnings` now already includes pre_extract_warnings (via the
        # pkg.parser_warnings merge above + persist_package's own warnings).
        warnings = list(warnings)
        await _persist_mined_knowledge(session, run_id=run_id, pkg=pkg,
                                       warnings=warnings)
        await session.commit()
        await _emit_ingest_completed(session, run_id=run_id, pkg=pkg)

    return IngestPackageAck(
        run_id=run_id,
        request_id=pkg.run_manifest.run_id,
        institution=pkg.run_manifest.institution_name,
        subcap_count=len(pkg.subcap_scores),
        evidence_count=len(pkg.evidence),
        recommendation_count=len(pkg.recommendations),
        peer_count=len(pkg.peers),
        issue_count=len(pkg.issue_register),
        tech_count=len(pkg.tech_stack),
        warnings=warnings,
    )


@router.post(
    "/package/folder",
    response_model=IngestPackageAck,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def ingest_package_folder(
    body: FolderIngestRequest, session: SessionDep,
) -> IngestPackageAck:
    p = Path(body.path)
    if not p.exists() or not p.is_dir():
        raise HTTPException(status_code=404, detail=f"folder not found: {p}")
    # 2026-05-28 audit fix (Probe 14): in prod, accept only paths under
    # the documented allowlist. Without this an authenticated admin
    # could feed `/etc` or `/cloudsql/...` and read whatever the parser
    # happened to surface in error messages. is_dir() alone is not a
    # sufficient gate.
    if not _folder_ingest_path_is_allowed(p):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"folder path not in allowlist (prod). Allowed prefixes: "
                f"{', '.join(_FOLDER_INGEST_ALLOWLIST)}. For ad-hoc "
                "operator ingests use the gcloud Cloud Run Job exec "
                "path documented in DEPLOYMENT.md §0.9."
            ),
        )
    try:
        pkg = _ingest_from_path(p)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    run_id, warnings = await persist_package(session, pkg)
    warnings = list(warnings)
    await _persist_mined_knowledge(session, run_id=run_id, pkg=pkg,
                                   warnings=warnings)
    await session.commit()
    await _emit_ingest_completed(session, run_id=run_id, pkg=pkg)
    return IngestPackageAck(
        run_id=run_id,
        request_id=pkg.run_manifest.run_id,
        institution=pkg.run_manifest.institution_name,
        subcap_count=len(pkg.subcap_scores),
        evidence_count=len(pkg.evidence),
        recommendation_count=len(pkg.recommendations),
        peer_count=len(pkg.peers),
        issue_count=len(pkg.issue_register),
        tech_count=len(pkg.tech_stack),
        warnings=warnings,
    )


async def _persist_mined_knowledge(
    session, *, run_id: str, pkg, warnings: list[str],
) -> None:
    """One-call knowledge persistence hand-off (Part 12.5/12.6).

    `parse_package` rides the mined knowledge envelope on the package
    as `_mined_knowledge`; the historical backfill already persists it,
    but the LIVE /ingest/package route dropped it on the floor — a
    freshly uploaded package had zero `client_knowledge_sections` rows
    (and no `runs.uncertainty_bands`) until the next backfill, so the
    D2 zennify-opportunity cards and the RAG knowledge array lagged.

    Best-effort within the caller's transaction (before commit so the
    sections land atomically with the run). Failure appends a DEGRADED
    warning and never blocks the ingest ack.
    """
    knowledge = getattr(pkg, "_mined_knowledge", None)
    if knowledge is None:
        return
    from sqlalchemy import text as _t
    try:
        row = (
            await session.execute(
                _t("SELECT entity_id::text AS eid FROM runs "
                   "WHERE id = CAST(:rid AS uuid)"),
                {"rid": str(run_id)},
            )
        ).first()
        if row is None:
            return
        from app.services.parsers.knowledge_artifacts import persist_knowledge
        kres = await persist_knowledge(
            session, entity_id=row.eid, run_id=str(run_id),
            knowledge=knowledge,
        )
        inserted = kres.get("sections_inserted", 0)
        if inserted:
            warnings.append(f"knowledge_sections_persisted: {inserted}")
    except Exception as e:
        warnings.append(
            f"DEGRADED/knowledge_persist_failed: "
            f"{type(e).__name__}: {str(e)[:160]}"
        )


async def _emit_ingest_completed(session, *, run_id: str, pkg) -> None:
    """Resolve entity_id + catalogue version from the freshly-committed
    run, then (1) fire `dma.ingest.completed` Pub/Sub AND (2) directly
    dispatch the derived-data workers (embedder, intelligence_recompute)
    so section_embeddings + customer_intelligence_profiles populate
    even when nothing consumes the Pub/Sub topic.

    Best-effort: any failure is logged and swallowed so the HTTP
    response still goes back as 201 to the caller.

    State branches (see package_persist.publish_post_commit +
    post_commit_workers.dispatch_post_commit_workers):
      run row missing post-commit (impossible barring corruption)
        → skip publish + dispatch; warn-log
      publisher disabled / unauthed
        → publish_post_commit returns (False, None, reason); we log
      publish succeeds
        → embedder Pub/Sub subscription would pick up IF anyone was
          subscribed (no one is today — the workers are Jobs not
          Services); we still do (2) below to actually populate
          derived data
      direct dispatch (2026-05-29 QA audit P1 fix)
        → INSERTs 2 job_executions rows (embedder + intelligence_
          recompute) + invokes the Cloud Run Jobs with --run-id=
          <this run>. Operator audit-trail: Admin → Job history.
        → failure flips the row's status to 'failed' inline; the
          ingest still returns 201; the scheduled reconciliation
          (Cloud Scheduler hourly per Terraform) catches up.
    """
    from sqlalchemy import text as _t

    try:
        row = (
            await session.execute(
                _t(
                    "SELECT entity_id::text AS eid, ccg_catalog_version, "
                    "       parent_request_id "
                    "FROM runs WHERE id = CAST(:rid AS uuid)"
                ),
                {"rid": run_id},
            )
        ).first()
    except Exception:
        row = None
    if row is None:
        return
    await publish_post_commit(
        db_run_id=run_id,
        entity_id=row.eid,
        request_id=pkg.run_manifest.run_id,
        ccg_catalog_version=row.ccg_catalog_version or "unknown",
        is_rerun=bool(row.parent_request_id),
        parent_request_id=row.parent_request_id,
    )
    # 2026-05-29 QA audit P1 fix — direct dispatch of derived-data
    # workers so section_embeddings + customer_intelligence_profiles
    # actually populate. Pub/Sub fan-out above is retained for any
    # future --subscribe Service deployment; this dispatch is the
    # working contract today.
    try:
        from app.services.post_commit_workers import (
            dispatch_post_commit_workers,
        )
        await dispatch_post_commit_workers(
            session, run_id=run_id, entity_id=row.eid,
        )
    except Exception:
        # The dispatcher already best-efforts its own failures;
        # this catch covers truly unexpected import/runtime errors
        # so the API still returns 201.
        pass
