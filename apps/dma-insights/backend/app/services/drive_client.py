"""Shared Google Drive v3 client primitives.

Used by both `app/scripts/historical_backfill.py` (one-shot bulk loader)
and `workers/drive_crawler/main.py` (live continuous crawl every 6h).

The functions delegate to the original `historical_backfill` private
helpers — this module exists to give those helpers a stable public name
without duplicating their bodies. When the deploy graduates and we
retire the script in favor of the live crawler, this module is the
only stable interface.

State-branch contract (`crawl_for_new_folders`):
  - cold_start          → no `import_scans` rows exist for any folder
                          → every folder is "new"; full ingest.
  - watermark_advance   → some folders have completed_at watermarks; only
                          folders with modifiedTime > watermark re-ingest.
  - no_new_files        → all folder watermarks are current; crawler
                          writes an empty `import_scans` audit row and
                          returns (folders_new=0, folders_changed=0).
  - quota_exceeded      → Drive API HttpError 429/403 → the call raises
                          and the caller writes a partial import_scans
                          row with `parser_warnings.quota_exceeded=true`.
"""
from __future__ import annotations

import importlib
import ssl
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class DriveFolder:
    id: str
    name: str
    modified_time: datetime | None = None


@dataclass
class DriveFile:
    id: str
    name: str
    mime_type: str | None = None
    size: int | None = None
    modified_time: datetime | None = None
    relative_path: str | None = None


def _hb():
    """Lazy-load the historical_backfill module so we don't pull in
    Google API client at import time of this lightweight wrapper."""
    return importlib.import_module("app.scripts.historical_backfill")


def build_drive_service() -> Any:
    """Build a Drive v3 service via Application Default Credentials."""
    return _hb()._build_drive()


def current_service_account_email() -> str | None:
    return _hb()._current_sa_email()


def list_dma_folders(service: Any, root_id: str) -> list[dict]:
    """Direct sub-folders of `root_id` whose name ends with ' - DMA'."""
    return _hb()._list_dma_folders(service, root_id)


def list_folder_files(service: Any, folder_id: str) -> list[dict]:
    """Direct (non-folder) file children of `folder_id`."""
    return _hb()._list_folder_files(service, folder_id)


def list_subfolders(service: Any, folder_id: str) -> list[dict]:
    return _hb()._list_subfolders(service, folder_id)


def walk_drive_tree(
    service: Any, folder_id: str, max_depth: int = 4,
) -> list[dict]:
    """Recursive enumeration of every file under `folder_id`."""
    return _hb()._walk_drive_tree(service, folder_id, depth=0, max_depth=max_depth)


def download_file(service: Any, file_meta: dict, dest: Any) -> None:
    """Blocking download of one Drive file (binary or Google-native
    export) to ``dest``. Delegates to the hardened
    ``historical_backfill._download_file`` (chunked, retrying,
    export-ceiling aware)."""
    _hb()._download_file(service, file_meta, dest)


async def download_file_async(
    service: Any, file_meta: dict, dest: Any,
) -> None:
    """Async wrapper: run the blocking Drive media transfer in a worker
    thread so it never starves the event loop (Part 12.4 — the measured
    backfill hot spot was blocking downloads inside the loop).

    NOTE: googleapiclient service objects are not safe for CONCURRENT
    requests — callers wanting parallel downloads must use one service
    per concurrent task (see historical_backfill.main's per-folder
    service pattern)."""
    import asyncio

    await asyncio.to_thread(_hb()._download_file, service, file_meta, dest)


# ── Transient-failure classification + folder-level retry ──────────────────
# 2026-07-06 incident (execution dma-insights-drive-crawler-7sdfs): every
# scheduled crawl failed all its downloads with
# `SSLError: [SSL] record layer failure` / `TimeoutError: The read operation
# timed out` while historical_backfill read the SAME Drive root cleanly an
# hour later. The crawler shared ONE googleapiclient service object across
# its concurrent folder tasks (service objects are NOT safe for concurrent
# requests — see `download_file_async` NOTE), corrupting the underlying TLS
# session; and it had no folder-level retry, so every corrupted download
# failed the folder outright. These helpers give the crawler the same
# robustness as the backfill's `_run_folder` attempt loop: a pure transient
# classifier + an injectable-backoff retry wrapper, both unit-testable
# without GCP credentials.

# Mirrors historical_backfill._RETRYABLE_DRIVE_STATUS (the chunk-level
# retry) so the folder-level wrapper and the chunk loop agree on what
# "transient" means. 403 is deliberately absent: it is usually a permanent
# permission / export-ceiling error, and the quota-exceeded flavor already
# has its own state branch (`quota_exceeded`) at the listing layer.
TRANSIENT_DRIVE_STATUS = frozenset({429, 500, 502, 503, 504})


def http_status_of(exc: BaseException) -> int | None:
    """Duck-typed status extraction for googleapiclient HttpError.

    Same extraction as `historical_backfill._download_file` — but duck-
    typed (`status_code` attr, else `resp.status`) so this lightweight
    module never imports googleapiclient and tests can use plain stubs.
    """
    code = getattr(exc, "status_code", None)
    if code is None:
        code = getattr(getattr(exc, "resp", None), "status", None)
    try:
        return int(code) if code is not None else None
    except (TypeError, ValueError):
        return None


def is_transient_drive_error(exc: BaseException) -> bool:
    """Pure classifier: True iff `exc` is a transient Drive/network
    failure worth a backoff + retry.

    Covers:
      - googleapiclient HttpError with status 429/500/502/503/504
      - ssl.SSLError        — '[SSL] record layer failure' on a dropped
                              or corrupted TLS session
      - TimeoutError        — 'The read operation timed out'
                              (socket.timeout is an alias since py3.10)
      - ConnectionError     — reset / aborted mid-stream
    """
    if isinstance(exc, TimeoutError | ssl.SSLError | ConnectionError):
        return True
    return http_status_of(exc) in TRANSIENT_DRIVE_STATUS


async def run_with_transient_retries(
    make_call: Callable[[], Awaitable[Any]],
    *,
    attempts: int = 3,
    max_delay: float = 16.0,
    label: str = "",
    is_retryable: Callable[[BaseException], bool] | None = None,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> Any:
    """Await ``make_call()`` with exponential backoff on transient failures.

    Folder-level analogue of ``historical_backfill._run_folder``'s attempt
    loop (2^attempt seconds, capped at ``max_delay``). ``make_call`` must be
    safely re-invocable — the ingest path is idempotent, so a retry pass
    fast-skips whatever already persisted. ``sleep`` and ``is_retryable``
    are injectable for tests (no real Drive calls, no real waiting).

    Non-transient errors and the final failed attempt re-raise unchanged
    so callers keep the original exception type + message.
    """
    import asyncio

    check = is_retryable if is_retryable is not None else is_transient_drive_error
    do_sleep = sleep if sleep is not None else asyncio.sleep
    attempt = 0
    while True:
        attempt += 1
        try:
            return await make_call()
        except Exception as e:
            if attempt >= attempts or not check(e):
                raise
            delay = min(2.0 ** attempt, max_delay)
            print(
                f"   ⟳ {label or 'drive call'}: attempt {attempt}/{attempts} "
                f"hit {type(e).__name__}: {str(e)[:120]} — retrying in "
                f"{delay:.0f}s",
                flush=True,
            )
            await do_sleep(delay)


def parse_drive_timestamp(value: str | None) -> datetime | None:
    """Drive returns RFC3339 timestamps like '2025-09-19T19:24:12.345Z'.

    This helper is pure — no Drive imports — so it can be unit-tested
    by the crawler module without GCP credentials.
    """
    if not value:
        return None
    s = value.replace("Z", "+00:00") if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def folder_is_newer_than_watermark(
    folder: dict, watermark: datetime | None,
) -> bool:
    """Pure helper: True iff folder.modifiedTime > watermark.

    `folder` is a Drive v3 file dict (with `modifiedTime`); `watermark`
    is `import_scans.completed_at` for that folder (None when no prior
    scan). Used by the drive_crawler to decide whether to re-ingest.
    """
    if watermark is None:
        return True  # cold_start branch
    mt = parse_drive_timestamp(folder.get("modifiedTime"))
    if mt is None:
        return True  # be conservative — if we can't parse, re-ingest
    # Drop tz aliasing — both sides must be timezone-aware.
    if watermark.tzinfo is None and mt.tzinfo is not None:
        from datetime import UTC
        watermark = watermark.replace(tzinfo=UTC)
    return mt > watermark
