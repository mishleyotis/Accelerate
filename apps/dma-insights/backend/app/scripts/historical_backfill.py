"""
Historical DMA backfill — reads DMA folders DIRECTLY from Google Drive.

Iterates every '* - DMA' sub-folder under the DMA Assets root folder,
downloads each file to a temp directory, and runs the standard parse +
persist pipeline. No GCS bucket or zip download required.

Idempotent: re-running is a no-op for already-ingested folders (the
persist layer upserts on the `request_id` / `drive_folder_id` key).

Usage (Cloud Run Job — DRIVE_ROOT_FOLDER_ID set via env):
    python -m app.scripts.historical_backfill

Usage (local dev, override root folder):
    python -m app.scripts.historical_backfill [DRIVE_ROOT_FOLDER_ID]

Auth: Uses Application Default Credentials with drive.readonly scope.
The Cloud Run Job runs as the Compute Engine default SA, which must have
Viewer access on the Drive root folder (see DEPLOYMENT.md §17).
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import concurrent.futures.process
import json
import os
import re
import ssl
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import google.auth
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
from sqlalchemy import text

from app.database import get_sessionmaker
from app.services.parsers.dma_package import parse_package
from app.services.parsers.package_persist import (
    persist_package,
    publish_post_commit,
)

# Original binding — used to detect test monkeypatches of
# ``hb.parse_package`` (patched parsers must run in-process, not in the
# parse worker pool, or the patch would silently not apply).
_PARSE_PACKAGE_ORIG = parse_package


def _parse_package_subprocess(root_str: str):
    """Top-level (picklable) parse entrypoint for the worker pool.

    Parse is pure filesystem work (no DB), so it parallelizes cleanly
    across processes — the measured corpus is CPU-bound in python-docx /
    spaCy / openpyxl, which the GIL serializes under threads."""
    from pathlib import Path as _P

    from app.services.parsers.dma_package import parse_package as _pp
    return _pp(_P(root_str))


# ── Part 12 re-architecture knobs ────────────────────────────────────────
def _backfill_concurrency() -> int:
    """Bounded package-loop concurrency (env DMA_BACKFILL_CONCURRENCY,
    default 6). Each package keeps its own session/transaction; the
    per-entity + per-run advisory locks inside persist_package serialize
    genuine key collisions, and catalogue upserts are ON CONFLICT-safe."""
    try:
        return max(1, int(os.environ.get("DMA_BACKFILL_CONCURRENCY", "6")))
    except ValueError:
        return 6


def _allow_hollow() -> bool:
    """DMA_ALLOW_HOLLOW=1 → the fail-loud zero-evidence/zero-recs gate
    records the DATA_LOSS warning but keeps the run ACTIVE (used for the
    committed test corpus, whose baseline includes hollow packages)."""
    return os.environ.get("DMA_ALLOW_HOLLOW", "") in ("1", "true", "yes")


def _store_raw_enabled(*, dir_mode: bool, flag: bool | None) -> bool:
    """Raw-artifact persistence gate. Priority: env DMA_STORE_RAW
    (0/1) > --store-raw flag > default (ON for --dir mode, OFF for
    Drive runs unless explicitly requested)."""
    env = os.environ.get("DMA_STORE_RAW")
    if env is not None:
        return env not in ("0", "false", "no", "")
    if flag is not None:
        return flag
    return dir_mode


def _is_retryable_db_error(e: Exception) -> bool:
    """Deadlock / serialization blips under the concurrent package loop
    are retried once with a fresh session."""
    s = f"{type(e).__name__}: {e}".lower()
    return "deadlock" in s or "could not serialize" in s


def _parse_process_workers(concurrency: int) -> int:
    """Parse worker-pool size (env DMA_PARSE_PROCESSES; 0 disables the
    pool → parse falls back to asyncio.to_thread). Default: min(cores,
    package concurrency) — parse is the CPU-bound stage the GIL
    serializes under threads."""
    raw = os.environ.get("DMA_PARSE_PROCESSES")
    if raw is not None:
        try:
            return max(0, int(raw))
        except ValueError:
            pass
    return max(1, min(os.cpu_count() or 2, concurrency))


def _hollow_reason(pkg) -> str | None:
    """Fail-loud gate predicate (Part 12.1): a SCORED package that
    parsed with zero evidence rows or zero recommendations is hollow —
    it must never go silently live."""
    if not (pkg.subcap_scores or []):
        return None
    missing = []
    if not (getattr(pkg, "evidence", None) or []):
        missing.append("zero_evidence")
    if not (getattr(pkg, "recommendations", None) or []):
        missing.append("zero_recommendations")
    return "+".join(missing) if missing else None


async def _apply_post_persist(
    session,
    *,
    run_id: str,
    pkg,
    root: Path | None,
    all_warnings: list[str],
    stage_ms: dict[str, int],
    store_raw: bool,
) -> dict:
    """Post-persist enrichment, SAME transaction as persist_package
    (caller commits): knowledge-section persistence, raw-artifact store,
    the fail-loud hollow gate, and the structured-warnings envelope.

    runs.parser_warnings becomes a JSONB DICT:
      {"warnings": [strings…],          ← backward-compat (substring
                                          consumers + admin previews)
       "structured": [{code,severity,detail}…],
       "severity_counts": {...},
       "pattern_gaps": [...],
       "needs_review": bool,
       "stage_ms": {download,parse,persist,post}}
    The overview endpoint + snapshot scrubber already accept dict-or-
    list parser_warnings.
    """
    from app.services.parsers.dma_package import (
        SEVERITY_DATA_LOSS,
        severity_counts,
        structure_warnings,
    )

    summary: dict = {"knowledge_sections": 0, "raw_stored": 0,
                     "needs_review": False}
    row = (await session.execute(
        text("SELECT entity_id::text AS eid FROM runs "
             "WHERE id = CAST(:rid AS uuid)"),
        {"rid": str(run_id)},
    )).first()
    entity_id = row.eid if row is not None else None

    # 1. Client-knowledge sections + runs.uncertainty_bands (Part 12.6).
    knowledge = getattr(pkg, "_mined_knowledge", None)
    if knowledge is not None and entity_id:
        try:
            from app.services.parsers.knowledge_artifacts import (
                persist_knowledge,
            )
            kres = await persist_knowledge(
                session, entity_id=entity_id, run_id=str(run_id),
                knowledge=knowledge,
            )
            summary["knowledge_sections"] = kres.get("sections_inserted", 0)
            summary["uncertainty_bands"] = kres.get(
                "uncertainty_bands_written", 0,
            )
        except Exception as e:
            all_warnings.append(
                f"DEGRADED/knowledge_persist_failed: "
                f"{type(e).__name__}: {str(e)[:160]}"
            )

    # 2. Raw-artifact store (Part 12.2) — compressed originals.
    if store_raw and entity_id and root is not None:
        try:
            from app.services.raw_artifact_store import store_package
            rres = await store_package(
                session, entity_id=entity_id, run_id=str(run_id),
                root_path=root,
            )
            summary["raw_stored"] = rres.get("stored", 0)
            summary["raw_deduped"] = rres.get("deduped", 0)
        except Exception as e:
            all_warnings.append(
                f"DEGRADED/raw_artifact_store_failed: "
                f"{type(e).__name__}: {str(e)[:160]}"
            )

    # 3. Fail-loud gate (Part 12.1): DATA_LOSS classes never go
    #    silently live. DMA_ALLOW_HOLLOW=1 keeps the run ACTIVE for the
    #    committed baseline corpus but still records the warning.
    hollow = _hollow_reason(pkg)
    if hollow:
        all_warnings.append(
            f"{SEVERITY_DATA_LOSS}/hollow_package: scored package "
            f"parsed with {hollow}; "
            + ("kept ACTIVE (DMA_ALLOW_HOLLOW=1)" if _allow_hollow()
               else "run routed to PENDING_REVIEW")
        )
        if not _allow_hollow():
            await session.execute(
                text(
                    "UPDATE runs SET status='PENDING_REVIEW', "
                    "updated_at=NOW() WHERE id = CAST(:rid AS uuid)"
                ),
                {"rid": str(run_id)},
            )
            summary["needs_review"] = True

    # 4. Structured-warnings envelope onto runs.parser_warnings JSONB.
    structured = structure_warnings(all_warnings)
    envelope = {
        "warnings": [str(w) for w in all_warnings],
        "structured": structured,
        "severity_counts": severity_counts(structured),
        "pattern_gaps": (
            list(knowledge.pattern_gaps) if knowledge is not None else []
        ),
        "needs_review": summary["needs_review"],
        "stage_ms": dict(stage_ms),
    }
    await session.execute(
        text(
            "UPDATE runs SET parser_warnings = CAST(:pw AS JSONB), "
            "updated_at = NOW() WHERE id = CAST(:rid AS uuid)"
        ),
        {"pw": json.dumps(envelope, ensure_ascii=False, default=str),
         "rid": str(run_id)},
    )
    summary["severity_counts"] = envelope["severity_counts"]
    return summary


def _is_pre_subcap_framework(pkg) -> bool:
    """True when a parsed package carries ZERO subcap scores.

    Operator mandate (2026-06-10, supersedes the short-lived
    narrative-first refinement): ONLY fully-scored deliverables are
    ingested. A package without subcap scores — whatever narrative it
    carries — is SKIPPED (not persisted) and recorded in
    backfill_quarantine so it is re-picked from Drive automatically
    the moment the scored deliverable lands. Partial ingests created
    hollow/partial entities (empty ScoreRing, blank heatmap, wrong-
    looking directory cards) on the live app; the operator's call is
    that incomplete reports stay OUT of the app until complete.

    This also re-aligns every ingest entry point: the live
    POST /ingest/package endpoint has always 422-rejected 0-score
    packages (app/routers/ingest_package.py); the backfill paths now
    apply the identical gate.

    The predicate keys on the PARSED package's subcap_scores ONLY —
    never penalise a selective re-ingest that *skips* an unchanged
    (but populated) scoring table.
    """
    return not bool(pkg.subcap_scores or [])

# Zennify DMA Assets root folder — all '* - DMA' sub-folders live here.
DEFAULT_ROOT_FOLDER_ID = "1uvt3kh8vPIygFwUNfKQSol0m5OYj2O0P"

# Module-level flag flipped by main() when invoked with --parse-only.
# _ingest_folder reads this AFTER parse_package returns and short-
# circuits before persist when True, emitting a JSON line on stdout
# describing the parse outcome (subcap_count, evidence_count,
# parser_warnings) per folder. The DB is never written in this mode.
# Operators use this for the "50-sample audit": parse a representative
# slice of the live Drive folder + verify the parser robustness across
# the production input distribution before pushing parser changes.
_PARSE_ONLY_MODE = False

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# Extensions worth downloading for DMA parsing (skip screenshots, thumbnails).
INGEST_EXTENSIONS = frozenset({".xlsx", ".docx", ".json", ".pdf", ".csv"})

# Subfolders that aren't part of the structured DMA package and add no
# value to ingestion. `05_narrative_deck/` contains the Google Slides
# deliverable (huge, often 50+ MB) which:
#   - has nothing the parsers consume (no scoring data, no evidence)
#   - hits Drive's "file too large to be exported" 403 ceiling per slide
#   - bottlenecks the backfill because each presentation export takes
#     30-60 s and may end up downloading nothing anyway
# Operator confirmed: "The narrative deck subfolder is not important.
# Most of the information is in the scoring workbook and the reports
# folder." Skip the whole tree under these names.
SKIP_SUBFOLDER_NAMES = frozenset({
    "05_narrative_deck",
    "narrative_deck",
    "narrative deck",
    "presentations",
    "decks",
})

# File extensions that ALSO get skipped even if they appear in an
# allowed subfolder (defensive — sometimes operators drop a stray
# pptx into 04_reports/ etc.).
SKIP_EXTENSIONS = frozenset({".pptx", ".ppt", ".key", ".mp4", ".mov"})


def _build_drive():
    """Build Drive v3 service using Application Default Credentials."""
    creds, _ = google.auth.default(scopes=DRIVE_SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _current_sa_email() -> str | None:
    """Best-effort: return the SA email used to authenticate (for error
    messages). Returns None if not introspectable."""
    try:
        creds, _ = google.auth.default(scopes=DRIVE_SCOPES)
        # service_account.Credentials.service_account_email exists; ADC
        # might be user creds with no email attribute.
        email = getattr(creds, "service_account_email", None)
        if email:
            return str(email)
        # Fall back to GCE metadata server (we're in Cloud Run).
        import urllib.request
        req = urllib.request.Request(
            "http://metadata.google.internal/computeMetadata/v1/instance/"
            "service-accounts/default/email",
            headers={"Metadata-Flavor": "Google"},
        )
        with urllib.request.urlopen(req, timeout=2) as r:
            return r.read().decode().strip()
    except Exception:
        return None


def _count_all_children(drive, root_id: str) -> int:
    """Count ALL direct children (any mimeType) of `root_id`. Used to
    distinguish 'empty folder' from 'folder visible but children hidden'.

    Uses Shared Drive parameters so it sees content stored in Shared
    Drives, not just My Drive. The default `corpora=user` excludes
    Shared Drive content entirely — silently returning 0.
    """
    try:
        resp = drive.files().list(
            q=f"'{root_id}' in parents and trashed=false",
            fields="files(id)",
            pageSize=1000,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            corpora="allDrives",
        ).execute()
        return len(resp.get("files", []))
    except HttpError:
        return -1


_DMA_NAME_RE = re.compile(
    # Permissive matcher — every Drive folder we've seen in the real
    # bucket so far. The original strict " - DMA" suffix matched ZERO
    # of the operator-uploaded packages (RegionsBank_DMA_20260518,
    # Amalgamated_Bank_DMA_2026, ANB_DMA_Complete_Bundle,
    # WSFS_DMA_Engagement_Package, AmeriCU_DMA_Deliverable_2026-04-29).
    # Match any folder that contains the token "DMA" surrounded by
    # word/path boundaries (case-insensitive). The operator can
    # override via DRIVE_FOLDER_NAME_INCLUDE / --include-pattern.
    r"(?i)(?:^|[\s_\-])dma(?:[\s_\-]|$)"
)


def _name_is_dma_candidate(name: str, include_pattern: re.Pattern | None = None) -> bool:
    """True if a Drive folder name looks like a DMA package.

    Strategy (per PRD §10 — "flat pool of candidate artifacts, no
    assumed folder structure"):
      1. Operator override via include_pattern wins.
      2. Otherwise the permissive _DMA_NAME_RE matches any name
         containing the token "DMA".
    """
    if not name:
        return False
    if include_pattern is not None:
        return bool(include_pattern.search(name))
    return bool(_DMA_NAME_RE.search(name))


def _list_dma_folders(
    drive, root_id: str, include_pattern: re.Pattern | None = None,
) -> list[dict]:
    """Return all direct sub-folders that look like DMA packages.

    Uses Shared Drive parameters so it sees content stored in Shared
    Drives. Without `supportsAllDrives=True` +
    `includeItemsFromAllDrives=True` + `corpora=allDrives`, Drive API
    returns 0 results for Shared Drive folders even when the SA has
    Viewer access — this was the bug causing 'found 0 folders' on a
    folder that clearly had 100+ DMA sub-folders.

    Folder-name filter is permissive (`_name_is_dma_candidate`) —
    matches any folder containing the token "DMA". The original strict
    " - DMA" suffix dropped every operator-uploaded package.
    """
    folders: list[dict] = []
    page_token: str | None = None
    q = (
        f"'{root_id}' in parents"
        " and mimeType='application/vnd.google-apps.folder'"
        " and trashed=false"
    )
    while True:
        resp = (
            drive.files()
            .list(
                q=q,
                fields="nextPageToken, files(id, name, modifiedTime)",
                pageSize=200,
                pageToken=page_token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                corpora="allDrives",
            )
            .execute()
        )
        for f in resp.get("files", []):
            if _name_is_dma_candidate(f["name"].strip(), include_pattern):
                folders.append(f)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return folders


def _list_folder_files(drive, folder_id: str) -> list[dict]:
    """Return all non-folder, non-trashed files directly inside a Drive folder.

    Uses Shared Drive parameters — see comment on `_list_dma_folders`."""
    files: list[dict] = []
    page_token: str | None = None
    q = (
        f"'{folder_id}' in parents"
        " and mimeType!='application/vnd.google-apps.folder'"
        " and trashed=false"
    )
    while True:
        resp = (
            drive.files()
            .list(
                q=q,
                fields="nextPageToken, files(id, name, mimeType, size, modifiedTime)",
                pageSize=200,
                pageToken=page_token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                corpora="allDrives",
            )
            .execute()
        )
        files.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return files


def _list_subfolders(drive, folder_id: str) -> list[dict]:
    """Return all direct sub-folders of `folder_id` (any name)."""
    folders: list[dict] = []
    page_token: str | None = None
    q = (
        f"'{folder_id}' in parents"
        " and mimeType='application/vnd.google-apps.folder'"
        " and trashed=false"
    )
    while True:
        resp = (
            drive.files()
            .list(
                q=q,
                fields="nextPageToken, files(id, name)",
                pageSize=200,
                pageToken=page_token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                corpora="allDrives",
            )
            .execute()
        )
        folders.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return folders


# Google native MIME types → export MIME type + filename extension to use
# when downloading. Drive's `files.get_media` 403s on native types; you
# must use `files.export_media(fileId, mimeType=<export-format>)` instead.
GOOGLE_EXPORT_MAP: dict[str, tuple[str, str]] = {
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".pptx",
    ),
}


def _walk_drive_tree(drive, folder_id: str, depth: int = 0, max_depth: int = 4) -> list[dict]:
    """Recursively enumerate every file under `folder_id` (DFS, capped depth).

    Returns a flat list of file dicts with an extra `_path` key showing the
    relative path of where the file lives (e.g. 'subfolder/file.xlsx').

    Why recursion: many DMA folders organize artifacts into subfolders
    (`Scoring/`, `Research/`, `Evidence/`, `01_evidence/`, etc.) instead
    of dumping everything at the root. The pre-refactor scan only saw
    the root level so 105 of 115 folders looked "empty".

    SKIP_SUBFOLDER_NAMES are pruned at the traversal layer (matched
    case-insensitively against the folder name with whitespace
    normalised) so we never even enumerate their contents — that's
    where the bulk of the slow Google Slides exports were being attempted.
    """
    if depth > max_depth:
        return []
    results: list[dict] = []
    for f in _list_folder_files(drive, folder_id):
        f["_path"] = f["name"]
        results.append(f)
    for sub in _list_subfolders(drive, folder_id):
        sub_norm = sub["name"].strip().lower().replace("-", "_").replace(" ", "_")
        if sub_norm in SKIP_SUBFOLDER_NAMES:
            continue
        for child in _walk_drive_tree(drive, sub["id"], depth + 1, max_depth):
            child["_path"] = f"{sub['name']}/{child.get('_path', child['name'])}"
            results.append(child)
    return results


def _classify_drive_comments(drive, file_ids: list[str]):
    """Return the comment-classification summary for the given files.

    Delegates to the Batch 9 classifier in
    ``workers.historical_backfill_comments``. The classifier fetches
    each comment body (in addition to the timestamp the legacy
    ``_latest_comment_time`` probe captured) and partitions the
    comments into MATERIAL (re-score / fix / wrong / etc.) vs
    COSMETIC (LGTM / +1 / chatter).

    The backfill skip-check uses the partition to decide whether to
    fold the comment timestamp into the change signal:

      - latest MATERIAL comment > prior run → re-ingest (mandate
        2026-06: "comments that may influence the DMA presentation"
        trigger re-ingest)
      - only COSMETIC comments newer than prior run → SKIP +
        ``e_comment_cosmetic_skipped`` observation (mandate 2026-06:
        "If it was a cosmetic change, this can just be dropped")
      - no comments newer than prior run → SKIP (no observation)

    Best-effort: comment probing is bounded + every error is swallowed
    so a Drive comments-API hiccup never blocks a backfill.
    """
    from app.services.drive_comment_materiality import (
        classify_comments,
        extract_comment_records,
    )

    records = extract_comment_records(drive, file_ids)
    return classify_comments(records)


def _latest_comment_time(drive, file_ids: list[str]) -> datetime | None:
    """Back-compat shim. Returns the latest MATERIAL comment timestamp,
    or None when no material comments were found. Cosmetic-only
    comments do NOT bump the change signal under the Batch 9
    contract — they emit a ``e_comment_cosmetic_skipped`` observation
    instead. Callers wanting the full breakdown should use
    ``_classify_drive_comments`` directly.
    """
    summary = _classify_drive_comments(drive, file_ids)
    return summary.latest_material_at


def _is_ingestable(f: dict) -> bool:
    """A Drive file is ingestable if EITHER:
      - its filename suffix is in INGEST_EXTENSIONS (.xlsx/.docx/.json/.pdf/.csv)
      - OR it's a Google native format we can export (Sheets → xlsx, Docs → docx)
      - OR it's a .zip file (containing a full DMA package)

    AND its extension is NOT in SKIP_EXTENSIONS (.pptx/.ppt/.key/.mp4/.mov).

    The narrative-deck pruning at the traversal layer (_walk_drive_tree)
    handles 99% of the bad downloads; this extension filter catches
    stray presentations that landed in other subfolders.

    Google native PRESENTATIONS (vnd.google-apps.presentation) are also
    skipped here — even though they're in GOOGLE_EXPORT_MAP, slides
    decks are universally not parsed by our pipeline and routinely 403
    on `files.export_media` with 'file too large to be exported'.
    """
    name = f.get("name", "")
    mime = f.get("mimeType", "")
    suffix = Path(name).suffix.lower()
    if suffix in SKIP_EXTENSIONS:
        return False
    if mime == "application/vnd.google-apps.presentation":
        return False
    if suffix in INGEST_EXTENSIONS:
        return True
    if mime in GOOGLE_EXPORT_MAP:
        return True
    return name.lower().endswith(".zip")


class ExportTooLargeError(Exception):
    """Google-native export hit Drive's 10 MB export ceiling.

    `files.export_media` (Docs→docx, Sheets→xlsx, Slides→pptx) is hard-
    capped at 10 MB by the Drive API regardless of the file's real size.
    Binary files uploaded to Drive (a real DMA workbook is a native
    `.xlsx`, not a Google Sheet) go through `get_media` which streams at
    ANY size — so this only fires when an operator stored the source as a
    Google-native doc that, when exported, exceeds 10 MB. The caller
    surfaces this as a parser_warning instead of aborting the folder."""


# Transient Drive errors worth retrying mid-download. Large files are the
# most likely to hit a mid-stream 500/502/503 (the connection is open
# longer), so retry is essential for "ingest files no matter the size".
_RETRYABLE_DRIVE_STATUS = frozenset({429, 500, 502, 503, 504})
_DOWNLOAD_MAX_ATTEMPTS = 5

# Socket-level transient failures worth the same mid-chunk retry as a
# 5xx. Observed in production (2026-07-06 drive_crawler execution 7sdfs):
# 'SSLError: [SSL] record layer failure' and 'TimeoutError: The read
# operation timed out' mid-download. These are NOT HttpError subclasses,
# so the status-code branch below never saw them and a single blip
# aborted the whole file. Mirrors drive_client.is_transient_drive_error.
_TRANSIENT_NETWORK_ERRORS: tuple[type[BaseException], ...] = (
    TimeoutError,     # socket.timeout is an alias since py3.10
    ssl.SSLError,
    ConnectionError,  # reset / aborted mid-stream
)


def _download_file(drive, f: dict, dest: Path) -> None:
    """Download a Drive file to `dest`. Handles binary, Google native, and
    Workspace export quirks. `f` must include `id`, `name`, `mimeType`.

    Robustness contract — "ingest files no matter the size":
      - Binary files (`get_media`) stream in 8 MiB chunks with no size
        ceiling. A 500 MB evidence PDF downloads fine.
      - Each `next_chunk()` retries up to `_DOWNLOAD_MAX_ATTEMPTS` times
        with exponential backoff on transient 429/5xx — large downloads
        keep the HTTP connection open longer and are the most likely to
        hit a mid-stream blip.
      - Google-native exports that exceed Drive's hard 10 MB export
        ceiling raise `ExportTooLargeError` so the caller can record a
        parser_warning + keep ingesting the rest of the folder, rather
        than failing the whole entity.
    """
    import time

    mime = f.get("mimeType", "")
    if mime in GOOGLE_EXPORT_MAP:
        # Google native — must export to a downloadable format
        export_mime, export_ext = GOOGLE_EXPORT_MAP[mime]
        if dest.suffix.lower() != export_ext:
            dest = dest.with_suffix(export_ext)
        request = drive.files().export_media(fileId=f["id"], mimeType=export_mime)
    else:
        request = drive.files().get_media(fileId=f["id"])

    with open(dest, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request, chunksize=8 * 1024 * 1024)
        done = False
        while not done:
            attempt = 0
            while True:
                attempt += 1
                try:
                    _, done = downloader.next_chunk()
                    break
                except HttpError as e:
                    code = getattr(e, "status_code", None) or getattr(
                        getattr(e, "resp", None), "status", None
                    )
                    try:
                        code = int(code) if code is not None else None
                    except (TypeError, ValueError):
                        code = None
                    reason = str(getattr(e, "reason", e)).lower()
                    # Google-native export over the 10 MB ceiling: don't
                    # retry — it will never succeed. Surface a typed error.
                    if code == 403 and (
                        "exportsizelimit" in reason
                        or "too large to be exported" in reason
                        or "this file is too large" in reason
                    ):
                        raise ExportTooLargeError(
                            f"{f.get('name', f['id'])} exceeds Drive's 10 MB "
                            f"export ceiling (Google-native source)"
                        ) from e
                    # Transient 429/5xx → backoff + retry.
                    if code in _RETRYABLE_DRIVE_STATUS and attempt < _DOWNLOAD_MAX_ATTEMPTS:
                        backoff = min(2 ** attempt, 16)
                        print(
                            f"   ↻ transient HTTP {code} on "
                            f"{f.get('name', f['id'])} chunk "
                            f"(attempt {attempt}/{_DOWNLOAD_MAX_ATTEMPTS}); "
                            f"retrying in {backoff}s",
                            flush=True,
                        )
                        time.sleep(backoff)
                        continue
                    # Non-retryable or out of attempts → propagate.
                    raise
                except _TRANSIENT_NETWORK_ERRORS as e:
                    # Socket-level blip (SSL record-layer failure, read
                    # timeout, connection reset) mid-chunk → same backoff
                    # + retry as a transient 5xx. next_chunk() re-issues
                    # the ranged request, so a retried chunk is safe.
                    if attempt < _DOWNLOAD_MAX_ATTEMPTS:
                        backoff = min(2 ** attempt, 16)
                        print(
                            f"   ↻ transient {type(e).__name__} on "
                            f"{f.get('name', f['id'])} chunk "
                            f"(attempt {attempt}/{_DOWNLOAD_MAX_ATTEMPTS}); "
                            f"retrying in {backoff}s",
                            flush=True,
                        )
                        time.sleep(backoff)
                        continue
                    raise


def _download_batch(
    drive, downloadable: list[dict], work_dir: Path, folder_name: str,
) -> tuple[int, list[str]]:
    """Sync download loop for one folder (runs inside asyncio.to_thread
    so blocking Drive media transfers never starve the event loop).

    Sequential WITHIN the folder — googleapiclient service objects are
    not safe for concurrent requests; cross-folder parallelism comes
    from the bounded folder gather in main() (one service per task)."""
    downloaded = 0
    download_warnings: list[str] = []
    for f in downloadable:
        # Preserve subfolder paths so the parser sees the same shape as
        # the original Drive layout (parsers expect `01_evidence/foo.csv`
        # etc., not all files flattened to root).
        rel = f.get("_path", f["name"])
        dest = work_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            _download_file(drive, f, dest)
            downloaded += 1
        except ExportTooLargeError as e:
            # Google-native source > 10 MB export ceiling. Not fatal —
            # record it and keep ingesting the rest of the folder.
            download_warnings.append(f"export_too_large:{rel}")
            print(f"   ⚠ {folder_name}/{rel}: {e}", flush=True)
        except HttpError as e:
            download_warnings.append(
                f"download_failed:{rel}:HTTP_"
                f"{getattr(e, 'status_code', '?')}"
            )
            print(
                f"   ⚠ Could not download {folder_name}/{rel}: HTTP "
                f"{getattr(e, 'status_code', '?')} {getattr(e, 'reason', e)}",
                flush=True,
            )
    return downloaded, download_warnings


def _extract_zips(work_dir: Path) -> tuple[int, list[str]]:
    """If any *.zip files exist in `work_dir`, unzip them in-place + delete
    the originals. Returns (extracted_count, warnings) where warnings is a
    list of structured strings safe to surface in `parser_warnings`.

    Many DMA folders contain a single `{Entity}_DMA_Complete_Package.zip`
    rather than the unpacked tree — the parser walks the unpacked tree
    so we expand first.

    Safety contract (mirrors `/api/v1/ingest/package` extractor):
      - zip-slip rejected (entry resolving outside `zp.parent`)
      - symlink entries rejected (Unix mode 0o120000)
      - per-entry uncompressed cap (50 MB) for entries we EXTRACT
      - cumulative uncompressed cap (200 MB) per archive
      - `05_narrative_deck/*` + other deck artifacts skipped before
        size gates fire — real DMA zips carry 60 MB pptx decks
      - `extractall()` is NEVER called; only validated entries extract
    """
    import zipfile

    # From app.services.zip_guard, NOT app.routers.ingest_package: the
    # router imports fastapi, which the workers image does not install
    # (2026-06-10: that import crashed every Drive folder ingest with
    # ModuleNotFoundError and stalled the deploy backfill at 45/124).
    from app.services.zip_guard import (
        _MAX_PER_ENTRY_UNCOMPRESSED_BYTES,
        _MAX_UNCOMPRESSED_TOTAL_BYTES,
        _zip_entry_should_skip,
    )

    extracted = 0
    warnings: list[str] = []
    for zp in list(work_dir.glob("**/*.zip")):
        try:
            with zipfile.ZipFile(zp) as zf:
                parent = zp.parent.resolve()
                cumulative = 0
                entries_to_extract = []
                for info in zf.infolist():
                    target = (parent / info.filename).resolve()
                    if not target.is_relative_to(parent):
                        warnings.append(
                            f"drive_zip_slip:{zp.name}:{info.filename}"
                        )
                        raise zipfile.BadZipFile(
                            f"zip-slip in {zp.name}:{info.filename}"
                        )
                    unix_mode = (info.external_attr >> 16) & 0xFFFF
                    if unix_mode and (unix_mode & 0o170000) == 0o120000:
                        warnings.append(
                            f"drive_zip_symlink_rejected:{zp.name}:{info.filename}"
                        )
                        raise zipfile.BadZipFile(
                            f"symlink entry in {zp.name}:{info.filename}"
                        )
                    if _zip_entry_should_skip(info.filename):
                        warnings.append(
                            f"drive_zip_skipped_deck:{zp.name}:{info.filename}"
                        )
                        continue
                    if info.file_size > _MAX_PER_ENTRY_UNCOMPRESSED_BYTES:
                        warnings.append(
                            f"drive_zip_oversize_entry:{zp.name}:{info.filename}"
                        )
                        raise zipfile.BadZipFile(
                            f"oversize entry in {zp.name}:{info.filename}"
                        )
                    cumulative += info.file_size
                    if cumulative > _MAX_UNCOMPRESSED_TOTAL_BYTES:
                        warnings.append(
                            f"drive_zip_bomb_guard:{zp.name}"
                        )
                        raise zipfile.BadZipFile(
                            f"cumulative decompressed exceeds "
                            f"{_MAX_UNCOMPRESSED_TOTAL_BYTES // (1024 * 1024)} MB "
                            f"in {zp.name}"
                        )
                    entries_to_extract.append(info)
                for info in entries_to_extract:
                    zf.extract(info, parent)
            zp.unlink()
            extracted += 1
        except zipfile.BadZipFile as e:
            # Leave the file in place — parser will skip it; structured
            # warning gives the operator enough to triage.
            warnings.append(f"drive_zip_failed:{zp.name}:{e}")
    return extracted, warnings


async def _ingest_folder(drive, folder: dict, tmp_root: Path) -> str:
    """
    Download all ingest-worthy files from one DMA folder, parse, and persist.

    Returns:
        'OK:<run_id>'     on success
        'SKIP:<reason>'   if nothing to do (no files, already ingested,
                           or matched R07 test-case pattern)
        'ERROR:<reason>'  on parse or DB failure
    """
    folder_id = folder["id"]
    folder_name = folder["name"]
    folder_modified = folder.get("modifiedTime")  # ISO8601 from Drive API

    # ── F6 R-rules: test-case quarantine ─────────────────────────────
    # R07 fires deterministically against folder + entity name patterns
    # (Nyumba Zetu, sample-bank, etc.). A `skip` action means we never
    # ingest — the audit trail surfaces in `import_files.parser_warnings`
    # for operator override via the admin queue.
    # Other rules (R05 client-provided, R06 pre-v5.5) need file-level
    # metadata or DOCX content and run later in the parser pipeline.
    from app.services.parsers.r_rules import (
        detect_r07_test_case,
        hits_to_audit_payload,
    )
    test_hit = detect_r07_test_case(folder_name=folder_name)
    if test_hit and test_hit.action == "skip":
        # Persist a single import_files audit row so the skip is
        # auditable + operator-overridable from the admin queue.
        try:
            sm0 = get_sessionmaker()
            async with sm0() as audit_session:
                await audit_session.execute(
                    text("""
                        INSERT INTO import_files (
                            drive_file_id, filename, file_kind,
                            status, parser_warnings
                        ) VALUES (
                            :fid, :name, 'folder_marker',
                            'SKIPPED', CAST(:warn AS JSONB)
                        )
                        ON CONFLICT (drive_file_id, drive_modified_time)
                        DO NOTHING
                    """),
                    {
                        "fid": folder_id, "name": folder_name,
                        "warn": json.dumps(hits_to_audit_payload([test_hit])),
                    },
                )
                await audit_session.commit()
        except Exception:
            # Audit is best-effort; never block a skip on logging failure.
            pass
        return f"SKIP:{folder_name} — R07 test case ({test_hit.reason})"

    # ── Idempotency check ────────────────────────────────────────────
    # Operator: "Ensure reloads skip already uploaded DMAs, or even
    # advanced versioning techniques for clients with multiple DMAs."
    # The `entities` table has a UNIQUE(drive_folder_id) index. If
    # we've already persisted a run for this folder AND the folder's
    # modifiedTime is older than the most recent run's completed_at,
    # the source hasn't changed since we ingested it — skip cleanly.
    # If the modifiedTime is NEWER, treat as a versioned re-ingest:
    # parse + persist as a new run (parent_request_id chain via the
    # supersede logic in persist_package).
    #
    # 2026-06 operator mandate: "if new edits are made on the reports
    # on Google Drive or notes or comments are placed, it should adjust
    # accordingly". Drive's folder `modifiedTime` updates on item
    # add/remove but NOT on edits to existing files (those update the
    # FILE's own `modifiedTime`). We compute `max(folder_mtime, max(
    # file_mtimes))` to detect any in-folder edit and trigger a
    # re-ingest. The recursive walk happens before the skip check so
    # the comparison sees per-file mtimes.
    work_dir = tmp_root / folder_id
    work_dir.mkdir(parents=True, exist_ok=True)

    # Recursive walk — many DMA folders nest artifacts in subfolders
    # (`01_evidence/`, `Scoring/`, etc.) rather than at the root.
    # Off the event loop: the walk issues one blocking Drive API list
    # call per subfolder.
    all_files = await asyncio.to_thread(_walk_drive_tree, drive, folder_id)
    downloadable = [f for f in all_files if _is_ingestable(f)]

    sm = get_sessionmaker()
    async with sm() as session:
        prior = (await session.execute(
            text(
                "SELECT r.completed_at, r.request_id, r.status FROM runs r "
                "JOIN entities e ON e.id = r.entity_id "
                "WHERE e.drive_folder_id = :fid "
                "ORDER BY r.completed_at DESC NULLS LAST LIMIT 1"
            ),
            {"fid": folder_id},
        )).first()
        # 2026-06 operator mandate: "Ensure all backfills get ingested
        # and go live. All backfills are pre v7 of the catalogue." If
        # the prior run is PENDING_REVIEW (a stuck v5/v6 catalogue
        # state under the old gate), ALWAYS re-ingest so the new
        # auto-bootstrap code path resolves it — even if the folder
        # mtime hasn't moved. The supersede logic flips the prior
        # PENDING_REVIEW row to SUPERSEDED and the fresh row goes
        # ACTIVE.
        prior_is_stuck = (
            prior is not None
            and (prior.status or "").upper() == "PENDING_REVIEW"
        )
        if prior is not None and prior.completed_at and not prior_is_stuck:

            def _to_dt(iso: str | None):
                if not iso:
                    return None
                try:
                    return datetime.fromisoformat(iso.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    return None

            mtimes: list = []
            folder_dt = _to_dt(folder_modified)
            if folder_dt is not None:
                mtimes.append(folder_dt)
            for f in downloadable:
                ft = _to_dt(f.get("modifiedTime"))
                if ft is not None:
                    mtimes.append(ft)
            # 2026-06 mandate: a new Drive COMMENT (which doesn't bump
            # file mtime) on any package file must also trigger a
            # re-ingest IFF the comment is materially actionable
            # ("re-score P3C2", "fix the heatmap", "wrong subcap"). A
            # cosmetic chatter comment ("LGTM", "+1") emits a
            # ``e_comment_cosmetic_skipped`` observation but does NOT
            # block the SKIP path.
            comment_summary = await asyncio.to_thread(
                _classify_drive_comments,
                drive, [f["id"] for f in downloadable if f.get("id")],
            )
            comment_dt = comment_summary.latest_material_at
            if comment_dt is not None:
                mtimes.append(comment_dt)
            if mtimes:
                latest_change = max(mtimes)
                prior_ts = prior.completed_at
                if latest_change <= prior_ts:
                    # File / folder mtimes + material-comment timestamps
                    # all pre-date the prior run. If COSMETIC chatter
                    # comments newer than the prior run exist, surface
                    # the observation in the SKIP log so the operator
                    # can audit and the next material ingest can
                    # persist a parser_observations row.
                    if (
                        comment_summary.has_only_cosmetic()
                        and comment_summary.latest_cosmetic_at is not None
                        and comment_summary.latest_cosmetic_at > prior_ts
                    ):
                        snip = (
                            comment_summary.sample_cosmetic[0][1][:60]
                            if comment_summary.sample_cosmetic else ""
                        )
                        return (
                            f"SKIP:{folder_name} — already ingested "
                            f"(run {prior.request_id} on {prior_ts.date()}; "
                            f"e_comment_cosmetic_skipped: "
                            f"{comment_summary.cosmetic_count} chatter "
                            f"comments since "
                            f"{comment_summary.latest_cosmetic_at.date()}"
                            f"{(' — ' + repr(snip)) if snip else ''})"
                        )
                    return (
                        f"SKIP:{folder_name} — already ingested "
                        f"(run {prior.request_id} on {prior_ts.date()}; "
                        f"folder + files + comments unchanged since)"
                    )
                if comment_dt is not None and comment_dt == latest_change:
                    snip = (
                        comment_summary.sample_material[0][1][:60]
                        if comment_summary.sample_material else ""
                    )
                    print(
                        f"   ↻ {folder_name}: e_comment_material_re_ingest "
                        f"— {comment_summary.material_count} material "
                        f"comment(s) since {comment_dt.date()} "
                        f"(>  last run {prior_ts.date()})"
                        f"{(' — ' + repr(snip)) if snip else ''}",
                        flush=True,
                    )
                # At least one file (or the folder itself) has been
                # modified since the last successful run → versioned
                # re-ingest. The supersede logic in persist_package
                # handles the SUPERSEDED → ACTIVE swap.
                print(
                    f"   ↻ latest change {latest_change.date()} > last run "
                    f"{prior_ts.date()} — re-ingesting as new version",
                    flush=True,
                )
        elif prior_is_stuck:
            print(
                f"   ↻ {folder_name} — prior run {prior.request_id} is "
                f"PENDING_REVIEW (pre-v7 catalogue stall); re-ingesting "
                f"to auto-bootstrap from workbook taxonomy",
                flush=True,
            )

    if not downloadable:
        # Surface what WAS there to help diagnose why nothing matched.
        sample = ", ".join(
            f"{f.get('_path', f.get('name', '?'))} ({f.get('mimeType', '?')})"
            for f in all_files[:5]
        ) or "<empty tree>"
        return (
            f"SKIP:{folder_name} — no ingest-worthy files "
            f"({len(all_files)} files seen; sample: {sample})"
        )

    # Downloads run OFF the event loop (Part 12.4: the blocking Drive
    # media transfers previously starved every other coroutine). The
    # batch stays sequential WITHIN a folder — Drive service objects are
    # not thread-safe for concurrent requests — but the folder loop
    # itself overlaps folders via the bounded gather in main().
    _t_download = time.monotonic()
    downloaded, download_warnings = await asyncio.to_thread(
        _download_batch, drive, downloadable, work_dir, folder_name,
    )

    if downloaded == 0:
        return f"SKIP:{folder_name} — all downloads failed"

    # If the folder contained `.zip` archives of the complete package,
    # extract them so the parser walks the unpacked tree. Uses the same
    # safe extractor as `/api/v1/ingest/package` — zip-slip + symlink +
    # per-entry + cumulative caps enforced; decks skipped before size
    # gates.
    _extracted_count, _zip_warnings = await asyncio.to_thread(
        _extract_zips, work_dir,
    )
    # _zip_warnings get folded into the parser/persist warnings below
    # so the operator-visible trace surfaces what was skipped/rejected
    # during extraction. Variable is intentionally suppressed here when
    # empty; non-empty values are appended after persist returns.
    _stage_ms: dict[str, int] = {
        "download": int((time.monotonic() - _t_download) * 1000),
    }

    try:
        _t_parse = time.monotonic()
        pkg = await asyncio.to_thread(parse_package, work_dir)
        _stage_ms["parse"] = int((time.monotonic() - _t_parse) * 1000)
        # ── --parse-only short-circuit ────────────────────────────────
        # Operator audit mode: parse-and-report only; never persist.
        # Emit one JSON line per folder so the operator can pipe stdout
        # to a file and grep / jq it. Keeps the rest of the loop intact
        # for the standard ingest path.
        if _PARSE_ONLY_MODE:
            try:
                summary = {
                    "folder_id": folder_id,
                    "folder_name": folder_name,
                    "run_id": pkg.run_manifest.run_id,
                    "institution": pkg.run_manifest.institution_name,
                    "subcap_count": len(pkg.subcap_scores),
                    "evidence_count": len(pkg.evidence),
                    "recommendation_count": len(pkg.recommendations),
                    "peers_count": len(pkg.peers),
                    "parser_warnings_count": len(pkg.parser_warnings),
                    "parser_warnings": pkg.parser_warnings[:10],
                    "parser_observations_count": len(pkg.parser_observations),
                }
                print(
                    "PARSEONLY " + json.dumps(summary, ensure_ascii=False),
                    flush=True,
                )
            except Exception as report_exc:  # pragma: no cover
                # Reporting must never raise — the parse succeeded; we
                # just couldn't summarise. Log a degraded marker line.
                print(
                    f"PARSEONLY_REPORT_ERROR {folder_name}: "
                    f"{type(report_exc).__name__}: {report_exc}",
                    flush=True,
                )
            return f"OK:parse_only:{folder_name}"
    except ValueError as e:
        # "no run manifest found" / "no scoring workbook" / similar
        # structural-completeness failures are NOT errors — they mean the
        # Drive folder doesn't contain a complete DMA package (just a
        # report PDF, just slides, raw research, etc.). Demote to SKIP
        # so they don't make the job exit non-zero.
        msg = str(e)
        if (
            "no run manifest" in msg.lower()
            or "no scoring" in msg.lower()
            or "no manifest" in msg.lower()
        ):
            return f"SKIP:{folder_name} — incomplete package ({msg})"
        return f"ERROR:parse:{folder_name}: {type(e).__name__}: {e}"
    except Exception as e:
        return f"ERROR:parse:{folder_name}: {type(e).__name__}: {e}"

    # Strict ingest gate (operator mandate 2026-06-10): only fully-
    # scored deliverables are persisted. The wording below must NOT
    # contain "already ingested"/"unchanged" — _classify_outcome maps
    # this to `skipped_no_report`, which --retry-failed-only re-picks.
    if _is_pre_subcap_framework(pkg):
        return (
            f"SKIP:{folder_name} — incomplete: 0 subcap scores; "
            f"will be re-picked from Drive when the scored "
            f"deliverable lands"
        )

    sm = get_sessionmaker()
    _post_summary: dict = {}
    async with sm() as session:
        try:
            _t_persist = time.monotonic()
            run_id, warnings = await persist_package(
                session,
                pkg,
                requester_user_id=None,
                data_source="DRIVE_BACKFILL",
                drive_folder_id=folder_id,
            )
            _stage_ms["persist"] = int(
                (time.monotonic() - _t_persist) * 1000,
            )
            # Part 12 post-persist enrichment (same transaction):
            # knowledge sections + raw-artifact store + fail-loud hollow
            # gate + structured-warnings envelope. The envelope folds in
            # the backfill-layer warnings (download / zip) so the run
            # row carries the complete trace.
            _t_post = time.monotonic()
            _all_w = (
                list(warnings) + list(download_warnings)
                + list(_zip_warnings)
            )
            _post_summary = await _apply_post_persist(
                session, run_id=str(run_id), pkg=pkg, root=work_dir,
                all_warnings=_all_w, stage_ms=_stage_ms,
                store_raw=_store_raw_enabled(dir_mode=False, flag=None),
            )
            _stage_ms["post"] = int((time.monotonic() - _t_post) * 1000)
            await session.commit()
        except Exception as e:
            await session.rollback()
            return f"ERROR:persist:{folder_name}: {type(e).__name__}: {e}"

        # Best-effort Pub/Sub publish + direct worker dispatch: same
        # envelope shape as the live /ingest/package path. The direct
        # dispatch is the post-commit derived-data path (2026-05-29
        # QA audit P1) — without it, backfilled runs would never get
        # section_embeddings + customer_intelligence_profiles.
        try:
            row = (await session.execute(
                _backfill_text(
                    "SELECT entity_id::text AS eid, ccg_catalog_version, "
                    "parent_request_id FROM runs WHERE id = CAST(:rid AS uuid)"
                ),
                {"rid": run_id},
            )).first()
            if row is not None:
                await publish_post_commit(
                    db_run_id=run_id,
                    entity_id=row.eid,
                    request_id=pkg.run_manifest.run_id,
                    ccg_catalog_version=row.ccg_catalog_version or "unknown",
                    is_rerun=bool(row.parent_request_id),
                    parent_request_id=row.parent_request_id,
                )
                try:
                    from app.services.post_commit_workers import (
                        dispatch_post_commit_workers,
                    )
                    await dispatch_post_commit_workers(
                        session, run_id=run_id, entity_id=row.eid,
                    )
                except Exception as de:
                    print(
                        f"   ⚠ post-commit worker dispatch failed (non-fatal): "
                        f"{type(de).__name__}: {de}",
                        flush=True,
                    )
        except Exception as e:
            print(f"   ⚠ pubsub publish failed (non-fatal): {type(e).__name__}: {e}", flush=True)

    # Operator trace: the structured envelope (parser + download + zip
    # warnings, severity counts, stage timings) was already written onto
    # runs.parser_warnings inside the persist transaction by
    # `_apply_post_persist` — here we only print the summary line.
    all_warnings = list(warnings) + list(download_warnings) + list(_zip_warnings)
    if all_warnings:
        print(
            f"   ⚠ {len(all_warnings)} warning(s) "
            f"({len(download_warnings)} download, {len(_zip_warnings)} zip, "
            f"{len(warnings)} parse) severity={_post_summary.get('severity_counts')} "
            f"sample: {all_warnings[:5]}",
            flush=True,
        )
    print(
        f"   ⏱ stage-ms {_stage_ms} knowledge="
        f"{_post_summary.get('knowledge_sections', 0)} "
        f"raw={_post_summary.get('raw_stored', 0)}"
        f"(+{_post_summary.get('raw_deduped', 0)} dedup)"
        + (" status=PENDING_REVIEW(hollow)"
           if _post_summary.get("needs_review") else ""),
        flush=True,
    )
    return f"OK:{run_id}"


def _backfill_text(sql: str):
    """Indirection so the import sits where the linter expects it."""
    from sqlalchemy import text as _t
    return _t(sql)


def _classify_outcome(res: str) -> tuple[str, str, str | None, str | None]:
    """Map a folder result string to (outcome, reason, ingested_run_id, error_message).

    Output convention (one of):
      ok                         → res starts with 'OK:'
      skipped_no_report          → res starts with 'SKIP:' and contains
                                   parser-domain markers ("no DMA package
                                   detected", "no run manifest", "incomplete
                                   package", "downloads failed")
      skipped_already_ingested   → res starts with 'SKIP:' and mentions
                                   'already_ingested' or 'idempotent'
      failed_parse               → 'ERROR:parse:' prefix
      failed_persist             → 'ERROR:persist:' prefix
      failed_other               → anything else starting with 'ERROR'

    Pure function — no DB, no I/O. Tests cover every branch directly.
    """
    if res.startswith("OK:"):
        return ("ok", "ingested", res[3:].strip(), None)
    if res.startswith("SKIP:"):
        body = res[5:].strip()
        body_low = body.lower()
        # The emitter at `_ingest_folder` produces `SKIP:{folder} — already
        # ingested (run REQ-… on …)` with a SPACE. Earlier classifier only
        # checked the underscore variant, so every idempotent skip was
        # misclassified as `skipped_no_report` and re-attempted on retry.
        # Accept both shapes; future emitters that prefer the underscore
        # form (matches the outcome key) still classify correctly.
        if (
            "already_ingested" in body_low
            or "already ingested" in body_low
            or "idempotent" in body_low
            or "folder unchanged since" in body_low
        ):
            return ("skipped_already_ingested", body, None, None)
        return ("skipped_no_report", body, None, None)
    # Any ERROR: variant.
    if res.startswith("ERROR:parse:"):
        return ("failed_parse", "parse_failed", None, res[len("ERROR:parse:"):])
    if res.startswith("ERROR:persist:"):
        return ("failed_persist", "persist_failed", None, res[len("ERROR:persist:"):])
    if res.startswith("ERROR"):
        return ("failed_other", "other", None, res)
    # Unrecognised — record as failed_other so the operator sees it
    # in the quarantine list instead of silently swallowing.
    return ("failed_other", "unrecognized_result", None, res)


_QUARANTINE_INSERT_SQL = """
    INSERT INTO backfill_quarantine
        (run_id, drive_folder_id, folder_name, outcome,
         reason, error_message, ingested_run_id, processed_at)
    VALUES
        (CAST(:rid AS uuid), :dfid, :fname, :outcome,
         :reason, :err, CAST(NULLIF(:ingested, '') AS uuid), NOW())
"""


def _write_quarantine_row(
    run_id: str | None,
    drive_folder_id: str,
    folder_name: str,
    outcome: str,
    reason: str,
    error_message: str | None,
    ingested_run_id: str | None,
) -> None:
    """Best-effort sync INSERT into backfill_quarantine. Swallows every
    exception (DB unreachable, schema not yet migrated, etc.) so a
    quarantine-write failure NEVER blocks the backfill loop.

    Sync (not async) so it works both inside the worker's async loop
    AND from synchronous CLI contexts. Uses the shared sync-DSN
    resolver — same fallback as job_executions_db.
    """
    if not run_id:
        # The backfill produces a job_executions row at startup; if
        # it's None we're in a pre-fix worker env or a unit test —
        # skip writes (no row to FK back to).
        return
    try:
        from sqlalchemy import create_engine
        from sqlalchemy import text as _t

        from app.services.sync_dsn import resolve_sync_dsn
        url = resolve_sync_dsn()
        if not url:
            return
        eng = create_engine(url, pool_pre_ping=True, pool_size=1)
        try:
            with eng.begin() as conn:
                conn.execute(_t(_QUARANTINE_INSERT_SQL), {
                    "rid": run_id,
                    "dfid": drive_folder_id[:64],
                    "fname": folder_name,
                    "outcome": outcome,
                    "reason": reason[:500] if reason else None,
                    "err": (error_message or "")[:1000] or None,
                    "ingested": ingested_run_id or "",
                })
        finally:
            eng.dispose()
    except Exception as e:
        print(
            f"::warning::quarantine row write failed "
            f"(folder={drive_folder_id} outcome={outcome}): "
            f"{type(e).__name__}: {e!s}",
            flush=True,
        )


def _check_aborted(execution_id: str | None) -> bool:
    """Return True iff the operator clicked 'Abort' on this row.

    Reads `job_executions.status` for the worker's own execution row.
    If it's been flipped to 'cancelled' (by /admin/jobs/executions/
    {id}:abort), the worker exits early.

    Best-effort contract: any error here returns False so a DB blip
    doesn't crash the worker mid-loop. Worst case: the operator's
    abort click takes longer than expected to land — but the row IS
    cancelled in the DB so the admin UI still reflects the operator
    intent immediately.
    """
    if not execution_id:
        return False
    try:
        from sqlalchemy import create_engine
        from sqlalchemy import text as _t

        from app.services.sync_dsn import resolve_sync_dsn
        url = resolve_sync_dsn()
        if not url:
            return False
        eng = create_engine(url, pool_pre_ping=True, pool_size=1)
        try:
            with eng.begin() as conn:
                row = conn.execute(_t(
                    "SELECT status FROM job_executions "
                    "WHERE id = CAST(:id AS uuid)"
                ), {"id": execution_id}).first()
                return bool(row) and row[0] == "cancelled"
        finally:
            eng.dispose()
    except Exception:
        return False


def _load_retry_targets() -> set[str]:
    """Return the set of drive_folder_id values that should be
    retried, based on the LATEST quarantine row per folder.

    "Should retry" = latest outcome is one of:
      - failed_parse / failed_persist / failed_other   (operator may
        have fixed the parser bug or the catalogue)
      - skipped_no_report                              (operator may
        have added a DMA report DOCX to the folder)

    NEVER retried:
      - ok                       (already ingested)
      - skipped_already_ingested (intentional skip)

    On any DB error returns an empty set — the caller treats this as
    "no targets" and exits 0 (better than blowing up the backfill
    mid-flight).
    """
    try:
        from sqlalchemy import create_engine
        from sqlalchemy import text as _t

        from app.services.sync_dsn import resolve_sync_dsn
        url = resolve_sync_dsn()
        if not url:
            return set()
        eng = create_engine(url, pool_pre_ping=True, pool_size=1)
        try:
            with eng.begin() as conn:
                # DISTINCT ON gives us one row per drive_folder_id —
                # the most recent one, by processed_at DESC.
                rows = conn.execute(_t("""
                    SELECT DISTINCT ON (drive_folder_id)
                           drive_folder_id, outcome
                      FROM backfill_quarantine
                  ORDER BY drive_folder_id, processed_at DESC
                """)).all()
        finally:
            eng.dispose()
        retry_outcomes = {
            "failed_parse", "failed_persist", "failed_other",
            "skipped_no_report",
        }
        return {r[0] for r in rows if r[1] in retry_outcomes}
    except Exception as e:
        print(
            f"::warning::could not load retry targets: "
            f"{type(e).__name__}: {e!s}; --retry-failed-only is a no-op",
            flush=True,
        )
        return set()


_LOCAL_CANON_RE = re.compile(r"^(0[1-8]_|09_|1[01]_)")


def _find_local_package_roots(base: Path) -> list[Path]:
    """Find DMA package roots under a local directory tree.

    Mirrors the deploy-corpus layout
    `dma_packages_batches/batch_NN/<Client> - DMA/[<nested>/]`. A root
    is the deepest dir that holds canonical `NN_*` subfolders; falls
    back to the client dir for report-only packages.
    """
    roots: list[Path] = []
    # Two levels: base/<batch>/<client>
    for batch in sorted(base.iterdir()):
        if not batch.is_dir():
            continue
        for client in sorted(batch.iterdir()):
            if not client.is_dir():
                continue
            chosen = client
            for sub in [client] + [d for d in client.rglob("*") if d.is_dir()]:
                try:
                    kids = {x.name for x in sub.iterdir() if x.is_dir()}
                except OSError:
                    continue
                if any(_LOCAL_CANON_RE.match(k) for k in kids):
                    chosen = sub
                    break
            roots.append(chosen)
    return roots


def _local_max_mtime(root: Path) -> datetime | None:
    """Latest file-mtime under a local package root (change signal)."""
    latest: float = 0.0
    for f in root.rglob("*"):
        if f.is_file():
            try:
                latest = max(latest, f.stat().st_mtime)
            except OSError:
                continue
    if latest <= 0:
        return None
    return datetime.fromtimestamp(latest, tz=UTC)


async def _process_local_root(
    root: Path,
    *,
    sm,
    force: bool,
    exec_id: str | None,
    store_raw: bool,
    parse_pool=None,
) -> tuple[str, dict[str, int]]:
    """One package's full local pipeline: manifest → skip-check → parse
    → strict gate → persist (+ post-persist enrichment). Returns
    ``(outcome, stage_ms)`` where outcome ∈ ok | skip |
    skipped_unscored | error. Runs under the caller's semaphore; owns
    its DB sessions so packages stay transaction-isolated."""
    from app.services.artifact_manifest import (
        compute_package_manifest,
    )

    stage_ms: dict[str, int] = {}
    t0 = time.monotonic()

    # client dir name = the `<Client> - DMA` folder (root may be nested)
    client_name = root.name
    for parent in [root, *root.parents]:
        if parent.name.endswith(" - DMA") or parent.name.endswith("- DMA"):
            client_name = parent.name
            break
    folder_key = f"local:{client_name}"
    # Compute the material manifest hash from the on-disk package.
    # Pure-function file IO + hashing — run off the event loop.
    manifest = await asyncio.to_thread(compute_package_manifest, root)
    material_hash = manifest.material_manifest_hash
    # Per-file manifest for the selective re-ingest diff (Batch 2).
    current_manifest_json = [
        {"rel_path": e.rel_path, "cls": e.cls,
         "content_hash": e.content_hash, "size_bytes": e.size_bytes}
        for e in manifest.entries
    ]
    max_mtime = await asyncio.to_thread(_local_max_mtime, root)
    stage_ms["manifest"] = int((time.monotonic() - t0) * 1000)
    try:
        async with sm() as session:
            # Prior-run lookup: by the entity's folder key OR by the exact
            # material manifest hash. The hash arm closes two permanent
            # re-ingest loops found in the 2026-07-10 redeployment QA:
            # (a) two package roots resolving to ONE entity flip-flop its
            # drive_folder_id each sweep, so the folder-keyed lookup misses
            # ("Pentegra Retirement[ Services] - DMA"); (b) a run persisted
            # onto a pre-existing entity with a different folder binding
            # (seed_ci's synthetic Regions) is invisible to the folder key.
            # Identical material hash == identical package content already
            # persisted — skipping is correct regardless of which entity row
            # carries the folder binding, and stops every deploy from
            # re-parsing + cache-invalidating those clients.
            prior = (await session.execute(
                text(
                    "SELECT r.completed_at, r.request_id, "
                    "    r.material_manifest_hash, "
                    "    r.artifact_manifest_json "
                    "FROM runs r "
                    "JOIN entities e ON e.id = r.entity_id "
                    "WHERE e.drive_folder_id = :fid "
                    "   OR (r.material_manifest_hash IS NOT NULL "
                    "       AND r.material_manifest_hash = :mh) "
                    "ORDER BY (r.material_manifest_hash = :mh) DESC, "
                    "    r.completed_at DESC NULLS LAST LIMIT 1"
                ),
                {"fid": folder_key, "mh": material_hash},
            )).first()
            # Intelligent skip: prior run + non-null prior hash +
            # equal current material hash → no MATERIAL change.
            # --force bypasses the skip so deployers can retroactively
            # re-process packages after an ingest-semantics change.
            if (
                not force
                and prior is not None
                and getattr(prior, "material_manifest_hash", None)
                and material_hash
                and prior.material_manifest_hash == material_hash
            ):
                # Warm-up the artifact_manifest_json on prior runs that
                # pre-date migration 034 (Batch 2) — see docstring.
                if not getattr(prior, "artifact_manifest_json", None):
                    async with sm() as warmup:
                        await warmup.execute(
                            text(
                                "UPDATE runs r SET "
                                "  artifact_manifest_json "
                                "    = CAST(:m AS JSONB) "
                                "FROM entities e "
                                "WHERE r.entity_id = e.id "
                                "  AND e.drive_folder_id = :fid "
                                "  AND r.request_id = :rid "
                                "  AND r.artifact_manifest_json "
                                "      IS NULL"
                            ),
                            {
                                "m": json.dumps(current_manifest_json),
                                "fid": folder_key,
                                "rid": prior.request_id,
                            },
                        )
                        await warmup.commit()
                print(
                    f"SKIP:{client_name} — already ingested "
                    f"(run {prior.request_id}; "
                    f"material content unchanged: "
                    f"{manifest.material_count} mat / "
                    f"{manifest.cosmetic_count} cos / "
                    f"{manifest.unknown_count} unk)",
                    flush=True,
                )
                await asyncio.to_thread(
                    _write_quarantine_row,
                    exec_id, folder_key, client_name,
                    "skipped_already_ingested",
                    f"material unchanged (run {prior.request_id})",
                    None, None,
                )
                return "skip", stage_ms
            # Legacy mtime fallback: when prior run pre-dates
            # migration 033, prior.material_manifest_hash is NULL —
            # keep the old folder-mtime safety net + hash warm-up.
            if (
                not force
                and prior is not None
                and prior.completed_at is not None
                and max_mtime is not None
                and max_mtime <= prior.completed_at
                and not getattr(prior, "material_manifest_hash", None)
            ):
                if material_hash:
                    async with sm() as warmup:
                        await warmup.execute(
                            text(
                                "UPDATE runs r SET "
                                "    material_manifest_hash = :h, "
                                "    artifact_manifest_json "
                                "      = CAST(:m AS JSONB) "
                                "FROM entities e "
                                "WHERE r.entity_id = e.id "
                                "  AND e.drive_folder_id = :fid "
                                "  AND r.request_id = :rid"
                            ),
                            {"h": material_hash, "fid": folder_key,
                             "rid": prior.request_id,
                             "m": json.dumps(current_manifest_json)},
                        )
                        await warmup.commit()
                print(
                    f"SKIP:{client_name} — already ingested "
                    f"(run {prior.request_id}; "
                    f"unchanged [legacy mtime path; "
                    f"manifest hash warmed])",
                    flush=True,
                )
                await asyncio.to_thread(
                    _write_quarantine_row,
                    exec_id, folder_key, client_name,
                    "skipped_already_ingested",
                    f"unchanged, legacy mtime (run {prior.request_id})",
                    None, None,
                )
                return "skip", stage_ms
        # Selective re-ingest diff (Batch 2): when the prior run has
        # a per-file artifact_manifest_json, deserialize + diff
        # against current; affected_tables gives us the skip_tables
        # set to pass into persist_package.
        # --force always treats the diff as "everything changed" so
        # skip_tables is empty -> every persist block re-fires.
        skip_tables_for_this_run: set[str] = set()
        diff_summary = "(no prior manifest)" if not force else "(--force)"
        if (
            not force
            and prior is not None
            and getattr(prior, "artifact_manifest_json", None)
        ):
            from app.services.artifact_manifest import (
                ArtifactEntry,
                PackageManifest,
                diff_manifests,
                skip_tables_for_diff,
                summarize_diff,
            )
            prior_entries = [
                ArtifactEntry(
                    rel_path=r.get("rel_path", ""),
                    cls=r.get("cls", "unknown"),
                    content_hash=r.get("content_hash", ""),
                    size_bytes=int(r.get("size_bytes", 0)),
                )
                for r in (prior.artifact_manifest_json or [])
                if isinstance(r, dict)
            ]
            prior_manifest = PackageManifest(entries=prior_entries)
            diff = diff_manifests(prior_manifest, manifest)
            skip_tables_for_this_run = skip_tables_for_diff(diff)
            diff_summary = summarize_diff(diff)
        # Parse OFF the event loop. Preferred lane: the process pool
        # (true multi-core — the corpus parse is CPU-bound in
        # python-docx/spaCy/openpyxl, which the GIL serializes under
        # threads). Falls back to a thread when the pool is disabled,
        # when tests monkeypatch ``parse_package``, or when the pool
        # breaks mid-run.
        t_parse = time.monotonic()
        if parse_pool is not None and parse_package is _PARSE_PACKAGE_ORIG:
            loop = asyncio.get_running_loop()
            try:
                pkg = await loop.run_in_executor(
                    parse_pool, _parse_package_subprocess, str(root),
                )
            except concurrent.futures.process.BrokenProcessPool:
                print(
                    f"   ⚠ {client_name}: parse worker pool broke — "
                    f"falling back to in-process parse",
                    flush=True,
                )
                pkg = await asyncio.to_thread(parse_package, root)
        else:
            pkg = await asyncio.to_thread(parse_package, root)
        stage_ms["parse"] = int((time.monotonic() - t_parse) * 1000)
    except ValueError as e:
        msg = str(e).lower()
        if "no run manifest" in msg or "no manifest" in msg or "no scoring" in msg:
            await asyncio.to_thread(
                _write_quarantine_row,
                exec_id, folder_key, client_name,
                "skipped_no_report", f"incomplete package ({e})",
                None, None,
            )
            return "skip", stage_ms
        print(f"ERROR:parse:{client_name}: {e}", flush=True)
        await asyncio.to_thread(
            _write_quarantine_row,
            exec_id, folder_key, client_name,
            "failed_parse", "parse ValueError", str(e), None,
        )
        return "error", stage_ms
    except Exception as e:
        print(f"ERROR:parse:{client_name}: {type(e).__name__}: {e}", flush=True)
        await asyncio.to_thread(
            _write_quarantine_row,
            exec_id, folder_key, client_name,
            "failed_parse", type(e).__name__, str(e), None,
        )
        return "error", stage_ms
    # Strict ingest gate (operator mandate 2026-06-10): only fully-
    # scored deliverables are persisted. Unscored/partial packages
    # are SKIPPED (quarantined as skipped_no_report) and re-picked
    # automatically once the scored deliverable lands.
    if _is_pre_subcap_framework(pkg):
        print(
            f"SKIP:{client_name} — incomplete: 0 subcap scores; "
            f"will be re-picked from Drive when the scored "
            f"deliverable lands",
            flush=True,
        )
        await asyncio.to_thread(
            _write_quarantine_row,
            exec_id, folder_key, client_name,
            "skipped_no_report",
            "incomplete: 0 subcap scores; re-pick when scored",
            None, None,
        )
        return "skipped_unscored", stage_ms
    # Persist with ONE retry on deadlock/serialization blips — the
    # concurrent package loop can (rarely) interleave catalogue /
    # peer-benchmark upserts across packages.
    t_persist = time.monotonic()
    post_summary: dict = {}
    last_error: Exception | None = None
    for attempt in (1, 2):
        try:
            async with sm() as session:
                run_id, _w = await persist_package(
                    session, pkg, requester_user_id=None,
                    data_source="MANUAL_BACKFILL", drive_folder_id=folder_key,
                    skip_tables=skip_tables_for_this_run,
                )
                # Persist the material manifest hash so the next backfill
                # can short-circuit when material content is unchanged.
                if material_hash:
                    await session.execute(
                        text(
                            "UPDATE runs SET "
                            "  material_manifest_hash = :h, "
                            "  artifact_manifest_json = CAST(:m AS JSONB) "
                            "WHERE id = :rid"
                        ),
                        {"h": material_hash, "rid": run_id,
                         "m": json.dumps(current_manifest_json)},
                    )
                # Part 12 post-persist enrichment (same transaction):
                # knowledge sections, raw-artifact store, fail-loud
                # hollow gate, structured-warnings envelope.
                stage_ms["persist"] = int(
                    (time.monotonic() - t_persist) * 1000,
                )
                t_post = time.monotonic()
                post_summary = await _apply_post_persist(
                    session, run_id=str(run_id), pkg=pkg, root=root,
                    all_warnings=list(_w), stage_ms=stage_ms,
                    store_raw=store_raw,
                )
                stage_ms["post"] = int((time.monotonic() - t_post) * 1000)
                await session.commit()
            last_error = None
            break
        except Exception as e:
            last_error = e
            if attempt == 1 and _is_retryable_db_error(e):
                print(
                    f"   ⟳ {client_name}: retryable DB error "
                    f"({type(e).__name__}) — retrying persist once",
                    flush=True,
                )
                await asyncio.sleep(0.5)
                continue
            break
    if last_error is not None:
        e = last_error
        print(f"ERROR:persist:{client_name}: {type(e).__name__}: {e}", flush=True)
        await asyncio.to_thread(
            _write_quarantine_row,
            exec_id, folder_key, client_name,
            "failed_persist", type(e).__name__, str(e), None,
        )
        return "error", stage_ms
    review_note = " status=PENDING_REVIEW(hollow)" if post_summary.get(
        "needs_review") else ""
    print(
        f"OK:{client_name}:{run_id} "
        f"[mat={manifest.material_count} cos={manifest.cosmetic_count} "
        f"unk={manifest.unknown_count}] "
        f"diff:{diff_summary} skip_tables:{len(skip_tables_for_this_run)} "
        f"knowledge={post_summary.get('knowledge_sections', 0)} "
        f"raw={post_summary.get('raw_stored', 0)}"
        f"(+{post_summary.get('raw_deduped', 0)} dedup) "
        f"ms[parse={stage_ms.get('parse', 0)} "
        f"persist={stage_ms.get('persist', 0)} "
        f"post={stage_ms.get('post', 0)}]"
        f"{review_note}",
        flush=True,
    )
    await asyncio.to_thread(
        _write_quarantine_row,
        exec_id, folder_key, client_name,
        "ok", diff_summary, None, str(run_id),
    )
    return ("pending_review" if post_summary.get("needs_review") else "ok"), \
        stage_ms


def _dedupe_variant_roots(
    roots: list[Path],
) -> tuple[list[Path], list[tuple[Path, str, Path]]]:
    """Collapse candidate roots that declare the SAME run_manifest run_id to
    one canonical root per run_id.

    Winner per group: most files, then lexicographically-last root name —
    both stable across sweeps, so the sweep CONVERGES (winner hash-skips on
    the next pass; losers are reported, never ingested). Roots without a
    readable run_manifest run_id are always kept. Returns
    ``(kept_roots, [(loser_root, run_id, winner_root), ...])``.
    """
    rid_of: dict[Path, str | None] = {}
    for root in roots:
        rid: str | None = None
        try:
            mf = next(iter(sorted(root.rglob("run_manifest.json"))), None)
            if mf is not None and mf.stat().st_size < 1_000_000:
                data = json.loads(mf.read_text(encoding="utf-8", errors="replace"))
                raw_rid = data.get("run_id") or data.get("request_id") or ""
                rid = str(raw_rid).strip() or None
        except Exception:
            rid = None
        rid_of[root] = rid
    groups: dict[str, list[Path]] = {}
    for root in roots:
        rid = rid_of[root]
        if rid:
            groups.setdefault(rid, []).append(root)

    def _rank(r: Path) -> tuple[int, str]:
        try:
            n_files = sum(1 for p in r.rglob("*") if p.is_file())
        except Exception:
            n_files = 0
        return (n_files, r.name)

    losers: list[tuple[Path, str, Path]] = []
    drop: set[Path] = set()
    for rid, group in groups.items():
        if len(group) < 2:
            continue
        winner = max(group, key=_rank)
        for r in group:
            if r is not winner:
                drop.add(r)
                losers.append((r, rid, winner))
    return [r for r in roots if r not in drop], losers


async def _ingest_local_dir(
    base: Path, *, force: bool = False, store_raw: bool | None = None,
) -> dict[str, int]:
    """Deploy-time / offline ingestion of a committed corpus directory.

    Renders the committed DMA corpus into the DB WITHOUT Drive — used by
    the deploy step so the reports load + render on deployment even when
    Drive isn't reachable from the runtime.

    INTELLIGENT change-aware ingest (per the 2026-06-07 operator mandate
    "the backfill should be super intelligent to avoid just
    reingesting"):

    1. Per-artifact materiality classification via
       ``services.artifact_manifest.compute_package_manifest``. Decks
       (05_narrative_deck/*), embedded PNG illustrations, audit search
       logs, and OS cruft are classified COSMETIC; scoring CSVs/XLSX,
       evidence indexes, assessment DOCX, run_manifest, qa_verdict,
       caps_applied_log, recommendations, and peer JSONs are MATERIAL.

    2. A deterministic ``material_manifest_hash`` (SHA256 over sorted
       material content hashes) is persisted on each successful run.
       The skip-check compares the current hash to the prior run's:
         - equal           → SKIP (no DMA-influencing change)
         - different       → re-ingest
         - prior null      → first ingest, or pre-migration-033 run;
                             fall back to the legacy mtime check.

    3. A folder-mtime touch from a deck swap or PNG reupload alone
       no longer triggers re-ingest. Operator can confirm via the diff
       summary printed alongside each SKIP line.

    Part 12.4 (2026-07): the package loop runs with BOUNDED CONCURRENCY
    (asyncio.Semaphore; default 6; env DMA_BACKFILL_CONCURRENCY). Each
    package keeps its own session + transaction; per-stage timings
    (manifest/parse/persist/post ms) aggregate into the summary line +
    job_executions.parser_warnings.

    Keyed on ``drive_folder_id = f"local:{client_dir_name}"`` so a
    re-run upserts the same entity/run (never duplicates).
    """
    roots = _find_local_package_roots(base)
    # Same-run_id variant dedup (2026-07-10 redeployment QA): the corpus can
    # carry TWO roots for one deliverable (e.g. "Pentegra Retirement - DMA"
    # and "Pentegra Retirement Services - DMA" — same run_manifest run_id,
    # cosmetic layout differences). Ingesting both made them overwrite the
    # SAME run row each sweep with alternating material hashes, so the
    # intelligent skip never engaged and every deploy re-parsed + cache-
    # invalidated the client forever. Collapse each run_id group to ONE
    # canonical root (most files, then lexicographically-last name — stable
    # across sweeps); the variants are reported as skips.
    roots, variant_skips = _dedupe_variant_roots(roots)
    counts = {
        "ok": 0, "skip": len(variant_skips), "skipped_unscored": 0, "error": 0,
        "pending_review": 0,
        "total": len(roots) + len(variant_skips),
    }
    for loser, rid, winner in variant_skips:
        print(
            f"SKIP:{loser.name} — duplicate variant of run_id {rid} "
            f"(canonical root: {winner.name})",
            flush=True,
        )
    sm = get_sessionmaker()
    # Quarantine wiring (2026-06-10): every outcome lands one
    # backfill_quarantine row keyed on the local folder key. The
    # execution id comes from track_job_execution (set in __main__);
    # bare library calls without a tracker degrade to no quarantine
    # writes (same contract as _write_quarantine_row's run_id guard).
    try:
        from workers._runner import get_current_tracker
        _trk = get_current_tracker()
        _exec_id = _trk.execution_id if _trk is not None else None
    except Exception:
        _trk = None
        _exec_id = None

    resolved_store_raw = _store_raw_enabled(dir_mode=True, flag=store_raw)
    concurrency = _backfill_concurrency()
    sem = asyncio.Semaphore(concurrency)
    stage_totals: dict[str, int] = {
        "manifest": 0, "parse": 0, "persist": 0, "post": 0,
    }
    wall_t0 = time.monotonic()
    # Parse worker pool: true multi-core for the CPU-bound parse stage.
    # Disabled (None) when DMA_PARSE_PROCESSES=0 or when a test has
    # monkeypatched ``parse_package`` (the patch can't cross a process
    # boundary — _process_local_root detects this per-call too).
    n_parse_procs = _parse_process_workers(concurrency)
    parse_pool = None
    if n_parse_procs > 0 and parse_package is _PARSE_PACKAGE_ORIG:
        import multiprocessing as _mp
        try:
            parse_pool = concurrent.futures.ProcessPoolExecutor(
                max_workers=n_parse_procs,
                mp_context=_mp.get_context("spawn"),
            )
        except Exception as pe:  # pragma: no cover — env without procs
            print(
                f"::warning:: parse worker pool unavailable "
                f"({type(pe).__name__}: {pe}); using threads",
                flush=True,
            )
            parse_pool = None
    print(
        f"LOCAL BACKFILL: {len(roots)} package roots, "
        f"concurrency={concurrency}, parse_procs="
        f"{n_parse_procs if parse_pool is not None else 0}, "
        f"store_raw={resolved_store_raw}, "
        f"allow_hollow={_allow_hollow()}",
        flush=True,
    )

    async def _one(root: Path) -> None:
        async with sem:
            try:
                outcome, stage_ms = await _process_local_root(
                    root, sm=sm, force=force, exec_id=_exec_id,
                    store_raw=resolved_store_raw, parse_pool=parse_pool,
                )
            except Exception as e:  # belt-and-suspenders: never lose a root
                print(
                    f"ERROR:pipeline:{root.name}: {type(e).__name__}: {e}",
                    flush=True,
                )
                outcome, stage_ms = "error", {}
        if outcome == "pending_review":
            counts["pending_review"] += 1
            counts["ok"] += 1          # persisted, just gated from live
        elif outcome in counts:
            counts[outcome] += 1
        for k, v in stage_ms.items():
            stage_totals[k] = stage_totals.get(k, 0) + int(v)

    try:
        await asyncio.gather(*(_one(root) for root in roots))
    finally:
        if parse_pool is not None:
            parse_pool.shutdown(wait=False, cancel_futures=True)

    wall_s = time.monotonic() - wall_t0
    print(
        f"\nLOCAL BACKFILL: {counts['ok']} ingested "
        f"({counts['pending_review']} gated PENDING_REVIEW), "
        f"{counts['skip']} skipped "
        f"(unchanged/incomplete), {counts['skipped_unscored']} skipped "
        f"(unscored — re-picked when the scored deliverable lands), "
        f"{counts['error']} error / {counts['total']} total "
        f"in {wall_s:.1f}s "
        f"[Σstage-ms manifest={stage_totals.get('manifest', 0)} "
        f"parse={stage_totals.get('parse', 0)} "
        f"persist={stage_totals.get('persist', 0)} "
        f"post={stage_totals.get('post', 0)}; concurrency={concurrency}]",
        flush=True,
    )
    # Per-stage aggregate onto the job_executions row (JSONB column).
    if _trk is not None:
        import contextlib
        with contextlib.suppress(Exception):
            _trk.update(
                folders_seen=counts["total"], folders_new=counts["ok"],
                files_skipped=counts["skip"] + counts["skipped_unscored"],
                files_errored=counts["error"],
                parser_warnings={
                    "stage_ms_totals": stage_totals,
                    "wall_seconds": round(wall_s, 1),
                    "concurrency": concurrency,
                    "store_raw": resolved_store_raw,
                    "pending_review": counts["pending_review"],
                },
                flush=True,
            )
    return counts


async def main() -> None:
    # --dir <path>: deploy-time / offline local-corpus ingestion. Runs
    # the idempotent + change-aware local path and returns early (no
    # Drive). Accept `--dir=PATH` and `--dir PATH` shapes.
    #
    # --force: bypass the intelligent material_manifest_hash + mtime
    # skip checks; re-persist every package in scope. Used after a
    # code change that affects ingest semantics (e.g. Batch 3's
    # shallow alias bridge) to retroactively re-process packages
    # whose prior runs predate the code change. Idempotent UPSERTs +
    # the DELETE-INSERT blocks both behave correctly under --force.
    # --store-raw / --no-store-raw: raw-artifact store gate (Part 12.2).
    # Default: ON for --dir mode, OFF for Drive scans; env DMA_STORE_RAW
    # overrides both (see _store_raw_enabled).
    _raw = sys.argv[1:]
    _dir_val: str | None = None
    _force = "--force" in _raw
    _store_raw_flag: bool | None = None
    if "--store-raw" in _raw:
        _store_raw_flag = True
    elif "--no-store-raw" in _raw:
        _store_raw_flag = False
    for i, a in enumerate(_raw):
        if a.startswith("--dir="):
            _dir_val = a.split("=", 1)[1]
            break
        if a == "--dir" and i + 1 < len(_raw):
            _dir_val = _raw[i + 1]
            break
    if _dir_val:
        base = Path(_dir_val)
        if not base.is_dir():
            print(f"FATAL: --dir path is not a directory: {base}", flush=True)
            sys.exit(2)
        await _ingest_local_dir(base, force=_force, store_raw=_store_raw_flag)
        return

    # Parse positional + flag args. Positional = Drive root folder ID
    # (defaults to DEFAULT_ROOT_FOLDER_ID); --retry-failed-only filters
    # the candidate set to drive_folder_ids whose latest backfill
    # outcome was failed_* or skipped_no_report.
    #
    # 2026-06 operator audit mode:
    #   --parse-only          parse every selected folder but DO NOT
    #                         persist; emit one JSON line per folder to
    #                         stdout summarising subcap_count + evidence
    #                         + parser_warnings. The DB is read-only;
    #                         no rows written.
    #   --sample N            after listing the candidate folders, take
    #                         a random shuffle and process at most N.
    #                         When combined with --parse-only, this is
    #                         the "50-sample dry run" audit the operator
    #                         uses to validate parser robustness against
    #                         the production input distribution before
    #                         pushing a code change.
    #
    # The two flags are independently useful: --parse-only alone walks
    # every folder reporting parse outcomes; --sample N alone runs the
    # full ingest path on a random subset (useful for spot-checking that
    # a deploy didn't regress persistence).
    raw_flags = sys.argv[1:]
    flags = {a for a in raw_flags if a.startswith("--") and "=" not in a}
    flag_kv = {
        a.split("=", 1)[0]: a.split("=", 1)[1]
        for a in raw_flags
        if a.startswith("--") and "=" in a
    }
    retry_failed_only = "--retry-failed-only" in flags
    parse_only = "--parse-only" in flags
    # --sample N -- accept both `--sample=N` and `--sample N` shapes.
    # Track which argv index (if any) the space-form value lives at so
    # we can exclude it from positional discovery below -- without this,
    # `--sample 50` would leak `50` as the DRIVE_ROOT_FOLDER_ID positional
    # and the scan would target Drive folder "50" (nonexistent → 404)
    # instead of the configured root.
    sample_value_idx: int | None = None
    sample_n: int | None = None
    if "--sample" in flag_kv:
        sample_n = int(flag_kv["--sample"])
    elif "--sample" in flags:
        # space-separated: locate it in argv and read next non-flag token
        try:
            idx = sys.argv.index("--sample")
            sample_n = int(sys.argv[idx + 1])
            sample_value_idx = idx + 1
        except (ValueError, IndexError):
            print(
                "FATAL: --sample requires an integer (e.g. --sample 50 or "
                "--sample=50)",
                file=sys.stderr, flush=True,
            )
            sys.exit(2)

    # Positional args = anything that isn't a flag AND isn't the value
    # consumed by a space-form `--sample N`. We compute this AFTER the
    # --sample parser so the exclusion index is known.
    args = [
        a for i, a in enumerate(sys.argv[1:], start=1)
        if not a.startswith("--") and i != sample_value_idx
    ]

    # Flip the module-level flag so _ingest_folder can short-circuit
    # before persist. We use a global flag (not function-parameter
    # threading) to keep the existing _ingest_folder signature stable --
    # workers/_runner reads it via the same module import.
    global _PARSE_ONLY_MODE
    _PARSE_ONLY_MODE = parse_only
    if parse_only:
        print(
            "historical_backfill: --parse-only — DB persistence disabled; "
            "emitting per-folder JSON to stdout",
            flush=True,
        )

    root_folder_id = (
        args[0] if args
        else os.environ.get("DRIVE_ROOT_FOLDER_ID", DEFAULT_ROOT_FOLDER_ID)
    )

    retry_targets: set[str] | None = None
    if retry_failed_only:
        retry_targets = _load_retry_targets()
        print(
            f"historical_backfill: --retry-failed-only — "
            f"{len(retry_targets)} folder(s) flagged for retry "
            f"(failed_* or skipped_no_report latest outcome)",
            flush=True,
        )
        if not retry_targets:
            print(
                "historical_backfill: nothing to retry; exiting 0",
                flush=True,
            )
            return
        # Activate parser lenient mode for the entire retry run. This
        # tells parse_package to fall through to the deep-extract chain
        # (DOCX text scrape → OCR → PDF OCR → folder-name-only) when
        # the canonical workbook layout is missing. Operator's intent
        # is "be more thorough than the first pass" — this is the BE
        # half of that mandate (Drive retry-with-backoff is the FE).
        os.environ["DMA_INGEST_LENIENT"] = "1"
        print(
            "historical_backfill: DMA_INGEST_LENIENT=1 — parser will "
            "fall through to deep extraction (DOCX text → OCR → PDF "
            "OCR → folder-name) when canonical layout is missing.",
            flush=True,
        )

    print(f"historical_backfill: scanning Drive folder {root_folder_id}", flush=True)
    drive = _build_drive()

    # ── Pre-flight: verify the SA can actually SEE the root folder ──────
    # The operator must share the DMA Assets folder with the Cloud Run SA
    # in Google Drive (DEPLOYMENT.md §9). Drive uses Workspace ACLs, not
    # Cloud IAM — `roles/drive.reader` doesn't grant per-folder access.
    # If the SA wasn't added to the folder's share list, `files().list`
    # with `'<id>' in parents` returns an EMPTY array (no error, no
    # warning), making this silent failure look like "the folder is
    # empty". This pre-flight uses `files().get` which DOES error 404 /
    # 403 when the SA can't see the folder — turning the silent failure
    # into a loud, actionable one.
    try:
        meta = drive.files().get(
            fileId=root_folder_id,
            fields="id,name,mimeType,owners,permissions",
            supportsAllDrives=True,
        ).execute()
        print(
            f"historical_backfill: root folder accessible — "
            f"name='{meta.get('name')}', mimeType='{meta.get('mimeType')}'",
            flush=True,
        )
        if meta.get("mimeType") != "application/vnd.google-apps.folder":
            print(
                f"::error:: DRIVE_ROOT_FOLDER_ID={root_folder_id} is not a folder "
                f"(got mimeType={meta.get('mimeType')}). Verify the ID.",
                file=sys.stderr,
            )
            sys.exit(1)
    except HttpError as e:
        sa_email = _current_sa_email() or "<unable to detect — check Cloud Run job config>"
        print("", file=sys.stderr)
        print(
            "::error:: cannot read Drive folder "
            f"https://drive.google.com/drive/folders/{root_folder_id}",
            file=sys.stderr,
        )
        print(
            f"::error:: HTTP {getattr(e, 'status_code', '?')}: "
            f"{getattr(e, 'reason', str(e))}",
            file=sys.stderr,
        )
        print("", file=sys.stderr)
        print(
            "The Cloud Run service account does NOT have Viewer access to the folder.",
            file=sys.stderr,
        )
        print(
            "Drive permissions are NOT Cloud IAM — they're per-folder ACLs in Drive.",
            file=sys.stderr,
        )
        print("", file=sys.stderr)
        print("To fix (one-time):", file=sys.stderr)
        print(
            f"  1. Open https://drive.google.com/drive/folders/{root_folder_id}",
            file=sys.stderr,
        )
        print("  2. Right-click → Share", file=sys.stderr)
        print(f"  3. Add `{sa_email}` as Viewer", file=sys.stderr)
        print("  4. Uncheck 'Notify people' (SAs have no inbox)", file=sys.stderr)
        print("  5. Save", file=sys.stderr)
        print("", file=sys.stderr)
        print(
            "Then re-run:  gcloud run jobs execute dma-insights-historical-backfill "
            "--region=us-central1 --wait",
            file=sys.stderr,
        )
        sys.exit(2)

    include_env = os.environ.get("DRIVE_FOLDER_NAME_INCLUDE")
    include_pattern = re.compile(include_env) if include_env else None
    folders = _list_dma_folders(drive, root_folder_id, include_pattern=include_pattern)
    pattern_desc = (
        include_pattern.pattern if include_pattern
        else '(default: contains the token "DMA")'
    )
    print(
        f"historical_backfill: found {len(folders)} candidate folder(s) "
        f"matching pattern {pattern_desc}",
        flush=True,
    )

    # --retry-failed-only narrows the candidate set to the folders whose
    # MOST RECENT quarantine row is a 'failed_*' or 'skipped_no_report'
    # state. 'ok' / 'skipped_already_ingested' folders are skipped (already
    # done) — the operator gets back exactly the 60 retry-targets out of
    # the 115-folder original set. Idempotent on re-run.
    if retry_targets is not None:
        pre = len(folders)
        folders = [f for f in folders if f["id"] in retry_targets]
        print(
            f"historical_backfill: --retry-failed-only filtered "
            f"{pre} → {len(folders)} folder(s)",
            flush=True,
        )
    # ── --sample N: random subset for audit / spot-check runs ────────
    # Operator-controlled: take a deterministic-but-shuffled slice of
    # the candidate set so repeated runs against the same Drive state
    # cover different folders. Combined with --parse-only this is the
    # "50-sample audit" the operator uses to validate parser robustness
    # before deploying changes.
    if sample_n is not None:
        import random as _random
        if sample_n <= 0:
            print(
                "FATAL: --sample N must be > 0",
                file=sys.stderr, flush=True,
            )
            sys.exit(2)
        pre = len(folders)
        # Stable seed when DMA_SAMPLE_SEED is set so the same set is
        # picked across multiple runs (useful for diffing a parser
        # change's effect on identical input). Otherwise a per-process
        # random seed gives fresh coverage per invocation.
        seed_env = os.environ.get("DMA_SAMPLE_SEED")
        if seed_env:
            _random.seed(seed_env)
        _random.shuffle(folders)
        folders = folders[:sample_n]
        print(
            f"historical_backfill: --sample {sample_n} narrowed "
            f"{pre} → {len(folders)} folder(s) "
            f"(seed={'pinned' if seed_env else 'random'})",
            flush=True,
        )
    if not folders:
        # Pre-flight succeeded but no '* - DMA' folders inside. Could mean:
        #   - the folder is genuinely empty (unlikely for the DMA Assets root)
        #   - the SA can see the folder but not its children (Drive
        #     permissions are folder-by-folder; sharing the root folder
        #     usually inherits to children, but check the "advanced"
        #     share settings if you see this)
        total_children = _count_all_children(drive, root_folder_id)
        if total_children == 0:
            print(
                "::warning:: the folder is accessible but contains zero children. "
                "Either the wrong folder ID is set, or the DMA folders haven't "
                "been uploaded yet.",
                flush=True,
            )
        else:
            print(
                f"::warning:: the folder has {total_children} children but none "
                "match the DMA-name pattern. The matcher accepts any folder "
                "containing the token 'DMA' (case-insensitive). Override via "
                "DRIVE_FOLDER_NAME_INCLUDE=<regex> if your folders use a "
                "different naming convention.",
                flush=True,
            )
        print("Nothing to do.", flush=True)
        return

    # Per-folder progress so the operator has live visibility on the
    # CLI instead of staring at a blank terminal for 20+ minutes.
    # Print a [N/M] prefix on every line + an ETA based on rolling
    # average folder time. Best-effort tracker flush so the admin UI
    # also sees progress (when run with DMA_JOB_EXECUTION_ID set).
    import contextlib
    import time as _time
    try:
        from workers._runner import get_current_tracker
        _ex = get_current_tracker()
    except Exception:
        _ex = None
    ok = skipped = failed = 0
    total = len(folders)
    start_ts = _time.monotonic()
    if _ex is not None:
        # flush=True so the admin UI immediately knows the total set
        # size — otherwise the counter stays NULL until the first
        # 5-folder batch completes (could be 60+ seconds).
        with contextlib.suppress(Exception):
            _ex.update(folders_seen=total, flush=True)
    # ── Cloud Run task sharding (2026-06-11 prod timeout fix) ────────
    # The serial crawl of the full corpus (~113 folders x ~45s) blows the
    # 900s Cloud Run task ceiling (execution wx7jb died twice at 900s).
    # Cloud Run Jobs natively inject CLOUD_RUN_TASK_INDEX/COUNT when the
    # job runs with --tasks N --parallelism N: each task processes the
    # disjoint slice idx % COUNT == INDEX — Nx throughput with no shared
    # Drive client, no shared session, per-task quarantine rows, and
    # byte-identical per-folder behavior. Local/manual runs (COUNT=1)
    # are unchanged. DEPLOYMENT.md §2c documents the job update.
    _task_count = max(1, int(os.environ.get("CLOUD_RUN_TASK_COUNT", "1")))
    _task_index = int(os.environ.get("CLOUD_RUN_TASK_INDEX", "0"))
    if _task_count > 1:
        sharded = [f for i, f in enumerate(folders) if i % _task_count == _task_index]
        print(
            f"shard {_task_index + 1}/{_task_count}: "
            f"{len(sharded)}/{len(folders)} folders", flush=True,
        )
        folders = sharded
        total = len(folders)

    # ── Bounded-concurrency folder loop (Part 12.4) ──────────────────
    # The per-folder pipeline (Drive walk → downloads → parse → persist)
    # runs under an asyncio.Semaphore (default 6; env
    # DMA_BACKFILL_CONCURRENCY). Every task builds its OWN Drive service
    # — googleapiclient service objects are not safe for concurrent
    # requests — and every package keeps its own DB session/transaction.
    # Counters mutate only in the single-threaded event loop, so no lock
    # is needed; quarantine/tracker writes happen per completed folder
    # exactly as before.
    concurrency = _backfill_concurrency()
    sem = asyncio.Semaphore(concurrency)
    abort_event = asyncio.Event()
    done = 0
    print(
        f"historical_backfill: folder concurrency={concurrency}",
        flush=True,
    )

    async def _run_folder(folder: dict, tmp_root: Path) -> str:
        """One folder's attempt loop → the result string. Retry mode is
        MORE robust than the first pass (3 attempts + backoff + full
        traceback into quarantine error_message)."""
        attempts = 3 if retry_failed_only else 1
        # Transient network faults ALWAYS get retries (2026-07-11 prod
        # diagnosis: every scheduled crawl for days failed folders on
        # one-shot SSLError/TimeoutError — attempts=1 turned a single
        # TLS blip into a failed folder, ~18 per run).
        net_attempts = max(attempts, 3)
        res = ""
        # Per-task Drive service: thread/coroutine isolation.
        # ALWAYS a fresh per-folder service — never the shared module-level
        # one. httplib2 keeps its keep-alive socket after an SSL fault, so
        # one corrupted TLS stream on a shared service poisons EVERY
        # subsequent request ([SSL] record layer failure in milliseconds,
        # folder after folder — observed across serial prod crawls).
        try:
            task_drive = await asyncio.to_thread(_build_drive)
        except Exception as be:
            return (
                f"ERROR:drive:{folder['name']}: could not build Drive "
                f"service: {type(be).__name__}: {be}"
            )
        for attempt in range(1, net_attempts + 1):
            try:
                res = await _ingest_folder(task_drive, folder, tmp_root)
                break
            except HttpError as he:
                # Drive transient — backoff + retry.
                status_code = getattr(he, "status_code", None) or 0
                transient = status_code in (403, 429, 500, 502, 503, 504)
                if attempt < attempts and transient:
                    delay = 2 ** attempt
                    print(
                        f"   ⟳ attempt {attempt}/{attempts} hit Drive "
                        f"HTTP {status_code} — retrying in {delay}s",
                        flush=True,
                    )
                    await asyncio.sleep(delay)
                    continue
                # Capture full traceback on terminal attempt.
                import traceback as _tb
                res = (
                    f"ERROR:drive:{folder['name']}: "
                    f"HTTP {status_code} "
                    f"{getattr(he, 'reason', str(he))} "
                    f"(attempt {attempt}/{attempts})\n"
                    f"{_tb.format_exc()[:2000]}"
                )
                break
            except Exception as e:
                # Network-level faults (SSLError/TimeoutError ⊂ OSError;
                # ResponseNotReady ⊂ http.client.HTTPException) retry in
                # EVERY mode with a REBUILT service — the old connection's
                # TLS state is unusable after the fault. Other errors keep
                # the retry-mode-only budget.
                import http.client as _hc
                _is_net = isinstance(e, OSError | _hc.HTTPException)
                _budget = net_attempts if _is_net else attempts
                if attempt < _budget:
                    delay = 2 ** attempt
                    print(
                        f"   ⟳ attempt {attempt}/{_budget} hit "
                        f"{type(e).__name__}: {e} — retrying in {delay}s"
                        f"{' with fresh Drive service' if _is_net else ''}",
                        flush=True,
                    )
                    if _is_net:
                        with contextlib.suppress(Exception):
                            task_drive = await asyncio.to_thread(_build_drive)
                    await asyncio.sleep(delay)
                    continue
                import traceback as _tb
                res = (
                    f"ERROR:top-level:{folder['name']}: "
                    f"{type(e).__name__}: {e} "
                    f"(attempt {attempt}/{attempts})\n"
                    f"{_tb.format_exc()[:2000]}"
                )
                break
        return res

    async def _one_folder(folder: dict, tmp_root: Path) -> None:
        nonlocal ok, skipped, failed, done
        if abort_event.is_set():
            return
        async with sem:
            if abort_event.is_set():
                return
            res = await _run_folder(folder, tmp_root)
        done += 1
        elapsed = _time.monotonic() - start_ts
        avg = elapsed / max(1, done)
        eta_sec = int(avg * (total - done))
        print(
            f"[{done}/{total}] {folder['name']} "
            f"(ok={ok} skip={skipped} fail={failed}, "
            f"ETA {eta_sec // 60}m {eta_sec % 60}s)",
            flush=True,
        )
        if res.startswith("OK:"):
            print(f"   ✓ run_id={res[3:]}", flush=True)
            ok += 1
        elif res.startswith("SKIP:"):
            print(f"   → {res[5:]}", flush=True)
            skipped += 1
        else:
            print(f"   ✗ {res}", flush=True)
            failed += 1

        # Best-effort quarantine row — pure-classification + sync
        # INSERT (in a worker thread so it never blocks the loop).
        # Swallows every exception so a quarantine-write failure NEVER
        # blocks the backfill; --retry-failed-only re-picks exactly the
        # failed_* / skipped_no_report folders.
        try:
            _q_outcome, _q_reason, _q_ingested, _q_err = _classify_outcome(res)
            await asyncio.to_thread(
                _write_quarantine_row,
                (_ex.execution_id if _ex is not None else None),
                folder["id"],
                folder["name"],
                _q_outcome,
                _q_reason,
                _q_err,
                _q_ingested,
            )
        except Exception as e:
            print(
                f"   ::warning::quarantine classify/write failed: "
                f"{type(e).__name__}: {e!s}",
                flush=True,
            )

        # Flush counters AFTER EVERY FOLDER (admin UI liveness) + poll
        # the operator Abort signal — when the row flips to 'cancelled',
        # stop launching new folders (in-flight ones finish + write
        # their quarantine rows).
        if _ex is not None:
            with contextlib.suppress(Exception):
                _ex.update(
                    folders_new=ok, files_parsed=ok,
                    files_skipped=skipped, files_errored=failed,
                    flush=True,
                )
            if await asyncio.to_thread(_check_aborted, _ex.execution_id):
                abort_event.set()

    with tempfile.TemporaryDirectory() as td:
        tmp_root = Path(td)
        await asyncio.gather(
            *(_one_folder(folder, tmp_root) for folder in folders)
        )

    if abort_event.is_set():
        print(
            f"\nhistorical_backfill: ABORT signal received "
            f"(row flipped to 'cancelled' by operator). "
            f"Stopped after [{done}/{total}]. "
            f"{ok} ingested, {skipped} skipped, {failed} failed.",
            flush=True,
        )
        # Exit code 0 — the cancellation was intentional.
        return

    print(
        f"\nhistorical_backfill: {ok}/{total} ingested, "
        f"{skipped} skipped, {failed} failed in "
        f"{int((_time.monotonic() - start_ts) // 60)}m "
        f"{int((_time.monotonic() - start_ts) % 60)}s.",
        flush=True,
    )
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    # ── Deploy-time dispatch (2026-06-18) ─────────────────────────────
    # post-deploy-refresh.sh needs to run OTHER backend-image modules
    # (run_derive_chain, export_startup_data --check) as Cloud Run Job
    # executions. It previously did so via `gcloud run jobs execute
    # --command python --args -m,<mod>` — but overriding the job's
    # `command` on `execute` silently failed in prod (the jobs WITHOUT an
    # override — drive_crawler/embedder — ran fine; the ones WITH it all
    # logged ✗ "lazy path covers"), so the derive chain never ran and the
    # live DB kept its junk-named entities (the operator's "old frontend"
    # / 100-entity dashboard). We instead dispatch via DMA_POST_DEPLOY_RUN,
    # set with `--update-env-vars` (the override mechanism that DOES work —
    # §3 cache-invalidation already relies on it). This runs the requested
    # module ON THIS BACKEND IMAGE, which has app.scripts.* + the v7.0
    # catalogue docs the chain needs.
    _post_deploy_run = os.environ.get("DMA_POST_DEPLOY_RUN", "").strip()
    if _post_deploy_run:
        _dispatch = {
            "derive_chain": ("app.scripts.run_derive_chain", []),
            "export_check": (
                "app.scripts.export_startup_data",
                ["--check", "--out", "/home/app/startup-data"],
            ),
            # Post-deploy Gemini surface gate against the LIVE DB
            # (infra/post-deploy-refresh.sh §2c) — asserts enrich_corpus
            # + intelligence_recompute actually persisted Vertex output
            # after run_derive_chain warmed them.
            "qa_gemini_baked": (
                "app.scripts.qa_gemini_surfaces",
                ["--mode", "baked"],
            ),
            # Committed-corpus seed (post-deploy-refresh.sh §2b). The
            # prior --args="--dir,…" execute-override is the SAME
            # silently-broken mechanism this dispatch table exists to
            # replace (2026-07-04 line audit) — worse, when the override
            # dropped, the job ran its no-args default: a FULL Drive
            # backfill under --wait. Dir comes from DMA_SEED_CORPUS_DIR
            # (set via --update-env-vars, which works), defaulting to the
            # image-baked fixtures path.
            "seed_corpus": (
                "app.scripts.historical_backfill",
                ["--dir",
                 os.environ.get(
                     "DMA_SEED_CORPUS_DIR",
                     "/home/app/tests/fixtures/dma_packages_batches")],
            ),
        }
        if _post_deploy_run not in _dispatch:
            print(f"historical_backfill: unknown DMA_POST_DEPLOY_RUN="
                  f"{_post_deploy_run!r}", file=sys.stderr, flush=True)
            raise SystemExit(2)
        import runpy
        _mod, _extra = _dispatch[_post_deploy_run]
        print(f"historical_backfill: DMA_POST_DEPLOY_RUN={_post_deploy_run} "
              f"→ python -m {_mod} {' '.join(_extra)}".rstrip(), flush=True)
        # Clear the dispatch var BEFORE re-entry: seed_corpus dispatches
        # back to THIS module, which would otherwise re-read it and
        # recurse forever.
        os.environ.pop("DMA_POST_DEPLOY_RUN", None)
        sys.argv = [sys.argv[0], *_extra]
        runpy.run_module(_mod, run_name="__main__")  # the module raises SystemExit itself
        raise SystemExit(0)

    # Wrap in track_job_execution so admin-dispatched runs (which set
    # DMA_JOB_EXECUTION_ID) update the same job_executions row instead
    # of creating a parallel one. Scheduler/CLI invocations get a fresh
    # row with trigger_source='scheduler' or 'cli'.
    try:
        from workers._runner import track_job_execution
    except Exception:
        track_job_execution = None  # type: ignore[assignment]
    if track_job_execution is not None:
        with track_job_execution("historical_backfill", mode="full"):
            asyncio.run(main())
    else:
        asyncio.run(main())
