"""Drive crawler entrypoint (Cloud Run Job).

Live continuous ingestion loop. Cloud Scheduler triggers this every 6h.
Each invocation:

  1. Builds a Drive v3 service (ADC).
  2. Lists `{Client} - DMA` folders under the configured root.
  3. Reconciles every folder against the DATABASE LEDGER: a folder whose
     `drive_folder_id` already has an ACTIVE ingested run is done; a
     folder with NO ACTIVE run is a candidate REGARDLESS of its
     `modifiedTime` (2026-07-06 fix — never-ingested folders must never
     be invisible to the crawler). `--since` is a fast-path override
     that narrows the scan by modifiedTime; it is an optimization, not
     the source of truth.
  4. Additionally EXCLUDES folders that map (by normalized name) to a
     seeded client whose ledger key is `local:…` / NULL — those can
     never match a real Drive id, and re-ingesting them duplicated the
     seeded corpus (2026-06-18 incident). `--since` opts out of both
     exclusions (full re-pull).
  5. For each remaining (new) folder — up to DMA_CRAWLER_MAX_FOLDERS,
     CONCURRENCY downloads in flight, under a hard DEADLINE_SEC — it is
     download + parse + persist only (the deterministic derive/heal
     scripts process the rows afterwards). It NEVER blocks the deploy:
     production runs it `--async`, and the cap + deadline make any run
     finite regardless.
  6. Writes one `import_scans` audit row at the end with
     `folders_seen / folders_new / folders_changed / files_parsed /
      parser_warnings`.

Design contract (2026-06-18): this worker must NEVER interfere with the
frontend or the deploy — it only adds new clients to the DB in the
background. Bounds are env-overridable: DMA_CRAWLER_MAX_FOLDERS (25),
DMA_CRAWLER_CONCURRENCY (4), DMA_CRAWLER_DEADLINE_SEC (900).

State-branch contract:
  - cold_start          → no prior import_scans → every folder treated
                          as new.
  - watermark_advance   → some folders have prior scans → only those
                          with modifiedTime > watermark re-ingest.
  - no_new_files        → all watermarks current → empty audit row only.
  - quota_exceeded      → Drive HttpError 429/403 → partial audit row
                          with `parser_warnings.quota_exceeded=true`.

CLI:
  --once       single pass then exit (Cloud Run Job mode; default)
  --since      ISO date — override the watermark for every folder
  --dry-run    list candidate folders + watermark deltas; no parse

Exit codes (documented in infra/EXIT_CODES.md § drive_crawler):
  0  success — including PARTIAL-OK: at least one folder ingested OK
     while others failed. Per-folder failures are counted in
     `files_errored`, logged with ✗ lines, and self-heal: a failed
     folder has no ACTIVE run, so the ledger reconciliation re-picks
     it on the next 6h crawl. One flaky folder must not poison the
     run status.
  2  DRIVE_ROOT_FOLDER_ID not set
  3  import failure (backend modules unavailable)
  4  ADC unavailable (no Drive service)
  5  list_dma_folders failed (root listing)
  6  invalid --since value
  7  SYSTEMIC ingest failure — folders were attempted, ≥1 failed and
     ZERO ingested OK (e.g. every download dying on a broken network
     path — the 2026-07-06 incident shape). Honest failure: the run's
     entire ingest workload failed, so the job execution is marked
     FAILED and the scheduler alert fires.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime

from app.config import get_settings
from workers._runner import track_job_execution

# ── Bounds (env-overridable) ────────────────────────────────────────────────
# The crawler must NEVER hang the deploy or starve the derive chain (it used to
# run a SEQUENTIAL cold-start re-ingest of ALL ~100 folders inside the blocking
# deploy critical path). These caps make every run fast + finite: at most
# MAX_FOLDERS new folders per pass (the rest roll to the next 6h crawl),
# CONCURRENCY downloads in flight at once, and a hard DEADLINE_SEC wall-clock
# after which no new folder is started. Production runs it --async, so even the
# deadline never blocks a deploy — these are defense-in-depth.
CRAWLER_MAX_FOLDERS = int(os.environ.get("DMA_CRAWLER_MAX_FOLDERS", "25"))
CRAWLER_CONCURRENCY = int(os.environ.get("DMA_CRAWLER_CONCURRENCY", "4"))
CRAWLER_DEADLINE_SEC = int(os.environ.get("DMA_CRAWLER_DEADLINE_SEC", "900"))


def _norm_client_key(s: str | None) -> str:
    """Normalize a client / folder / display-id string to a comparison key.

    Collapses the three shapes that all denote the same client to one token:
      - a Drive folder name      'Haventree Bank - DMA'
      - a local-seed folder id   'local:Haventree Bank DMA - DMA'
      - a display_id slug        'haventree-bank-0001'
    …all → 'haventreebank'. Strategy: drop the 'local:' seed prefix, every
    'DMA' folder-marker token, the trailing '-0001' display-id ordinal, and all
    non-alphanumerics, then lowercase. Pure (no IO) so it is unit-testable.
    """
    s = (s or "").strip().lower()
    if s.startswith("local:"):
        s = s[len("local:"):]
    s = re.sub(r"\bdma\b", " ", s)        # DMA folder-marker token(s)
    s = re.sub(r"[-_ ]\d{2,}\s*$", "", s)  # trailing display-id ordinal (-0001)
    s = re.sub(r"[^a-z0-9]+", "", s)       # alnum only
    return s


def _folder_is_known(folder_name: str | None, known_keys: set[str]) -> bool:
    """True iff this Drive folder maps to a client already ACTIVE in the DB.

    Exact normalized-key match (the local-seed folder ids mirror the Drive
    folder names, so this is reliable for the seeded 94). Pure / testable.
    """
    key = _norm_client_key(folder_name)
    return bool(key) and key in known_keys


def _load_known_active_keys() -> set[str]:
    """Normalized keys for ACTIVE entities that the drive-folder-id LEDGER
    cannot cover: the seeded corpus (drive_folder_id='local:…') and any
    row with a NULL drive_folder_id.

    The crawler skips any Drive folder matching one of these so it 'strictly
    adds new clients in the background' and never re-ingests (and thereby
    DUPLICATES) the seeded corpus — the seeded 94 carry
    drive_folder_id='local:…' keys the crawler's real Drive ids can never
    match, so without this filter every deploy-time crawl re-created them as
    fresh ACTIVE rows (the live dashboard's '100 entities' / junk-named
    duplicates).

    2026-07-06 narrowing: entities ingested FROM Drive carry a real
    drive_folder_id and are reconciled precisely by
    `_load_ingested_folder_ids` — keeping their name-keys here made any
    never-ingested folder whose normalized name collided with an ACTIVE
    entity permanently invisible. Name matching is now only the fallback
    for rows the id ledger can't reach.

    Best-effort: a DB hiccup returns an empty set (crawler still runs; the
    post-ingest material-hash skip + repark_junk_entities are the
    backstops)."""
    import asyncio

    from sqlalchemy import text

    from app.database import get_sessionmaker

    keys: set[str] = set()

    async def _q() -> None:
        sm = get_sessionmaker()
        async with sm() as session:
            rows = (await session.execute(text(
                "SELECT name, display_id, drive_folder_id "
                "FROM entities WHERE status = 'ACTIVE' "
                "AND (drive_folder_id IS NULL "
                "     OR drive_folder_id LIKE 'local:%')"
            ))).all()
        for name, display_id, dfid in rows:
            for raw in (name, display_id, dfid):
                k = _norm_client_key(raw)
                if k:
                    keys.add(k)

    try:
        asyncio.run(_q())
    except Exception as e:
        # Best-effort: a DB hiccup must never block the crawl (the post-ingest
        # material-hash skip + repark_junk_entities are the backstops).
        print(f"drive_crawler: could not load known-entity keys ({e}); "
              f"proceeding without exclude-existing filter", file=sys.stderr)
    return keys


def _load_ingested_folder_ids() -> set[str]:
    """The DATABASE LEDGER: every drive_folder_id that already has an
    ACTIVE ingested run.

    This is the same source of truth `historical_backfill._ingest_folder`
    reconciles against (its prior-run lookup joins
    entities.drive_folder_id → runs). A folder in this set is done; a
    folder NOT in this set is a candidate REGARDLESS of modifiedTime —
    the 2026-07-06 fix for genuinely-new folders that predate any
    watermark/checkpoint and were therefore never picked up.

    Best-effort: a DB hiccup returns an empty set — the crawler then
    falls through to `_ingest_folder`'s own per-folder 'already ingested
    + unchanged' skip (the Capital Farm path), which stays authoritative
    as the backstop."""
    import asyncio

    from sqlalchemy import text

    from app.database import get_sessionmaker

    ids: set[str] = set()

    async def _q() -> None:
        sm = get_sessionmaker()
        async with sm() as session:
            rows = (await session.execute(text(
                "SELECT DISTINCT e.drive_folder_id "
                "FROM entities e JOIN runs r ON r.entity_id = e.id "
                "WHERE r.status = 'ACTIVE' "
                "AND e.drive_folder_id IS NOT NULL"
            ))).all()
        for (dfid,) in rows:
            if dfid:
                ids.add(str(dfid))

    try:
        asyncio.run(_q())
    except Exception as e:
        print(f"drive_crawler: could not load ingested-folder ledger ({e}); "
              f"falling back to per-folder skip checks", file=sys.stderr)
    return ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DMA Insights drive crawler")
    parser.add_argument("--once", action="store_true",
                        help="Single pass then exit (default)")
    parser.add_argument("--since", help="ISO date — override watermark")
    parser.add_argument("--dry-run", action="store_true",
                        help="List candidate folders; no parse/write")
    args = parser.parse_args(argv)
    mode = "delta" if not args.since else "full"

    s = get_settings()
    if not s.drive_root_folder_id:
        print("DRIVE_ROOT_FOLDER_ID not set", file=sys.stderr)
        return 2

    with track_job_execution("drive_crawler", mode=mode) as ex:
        rc = _main_body(args, s, ex)
        if rc != 0:
            # Raise INSIDE the tracking context so the runner flips the
            # job_executions row to FAILED ("exited with code N") — a
            # plain `return rc` exits the context cleanly and the row
            # would read SUCCEEDED while Cloud Run reports the execution
            # failed (dishonest admin pill).
            raise SystemExit(rc)
        return rc


def _main_body(args: argparse.Namespace, s, ex) -> int:
    """Wrapped body — `ex` is the runner's execution tracker; call
    `ex.update(...)` with counters as work progresses."""
    if args.dry_run:
        summary = {
            "mode": "dry-run",
            "drive_root_folder_id": s.drive_root_folder_id,
            "since": args.since,
            "state_branches": [
                "cold_start", "watermark_advance",
                "no_new_files", "quota_exceeded",
            ],
            "next_step": (
                "Live IO requires a Google Drive service account in "
                "Secret Manager (dma-insights-drive-sa-key). Once mounted, "
                "the crawler will:\n"
                "1) list_dma_folders(root) for '{Client Name} - DMA';\n"
                "2) for each folder, compare modifiedTime to the "
                "   max(import_scans.completed_at) watermark;\n"
                "3) download + dispatch via ./dispatch.py + persist;\n"
                "4) publish dma.ingest.completed;\n"
                "5) write one import_scans row capturing the cycle."
            ),
        }
        print(json.dumps(summary, indent=2))
        return 0

    # Live mode — exercises the shared drive_client helpers + delegates
    # ingest to historical_backfill._ingest_folder per folder past its
    # watermark. The crawler IS the ingest path; historical_backfill
    # is now only invoked for one-shot bulk re-ingest from the CLI.
    try:
        from app.scripts.historical_backfill import _ingest_folder
        from app.services.drive_client import (
            build_drive_service,
            folder_is_newer_than_watermark,
            is_transient_drive_error,
            list_dma_folders,
            run_with_transient_retries,
        )
    except Exception as e:
        print(f"drive_crawler: import failed: {e}", file=sys.stderr)
        return 3

    try:
        service = build_drive_service()
    except Exception as e:
        print(
            f"drive_crawler: ADC unavailable — {e}. Run with --dry-run "
            f"to see configured root + state matrix.",
            file=sys.stderr,
        )
        return 4

    started_at = datetime.now(tz=UTC)
    try:
        folders = list_dma_folders(service, s.drive_root_folder_id)
    except Exception as e:
        print(f"drive_crawler: list_dma_folders failed: {e}", file=sys.stderr)
        return 5

    since_dt = None
    if args.since:
        try:
            since_dt = datetime.fromisoformat(args.since.replace("Z", "+00:00"))
        except ValueError:
            print(f"drive_crawler: invalid --since '{args.since}'", file=sys.stderr)
            return 6

    # `--since` is a fast-path OPTIMIZATION only: it narrows the scan by
    # modifiedTime when the operator explicitly asks for it. Without it,
    # every folder stays in scope — modifiedTime must never hide a
    # never-ingested folder (2026-07-06: 43 genuinely-new folders showed
    # folders_new=0 while the backfill ingested them an hour later).
    changed = [f for f in folders if folder_is_newer_than_watermark(f, since_dt)]

    # ── reconcile against the DB ledger + exclude the seeded corpus ──
    # 1. LEDGER (authoritative): a folder whose drive_folder_id already
    #    has an ACTIVE ingested run is done; every other folder is a
    #    candidate regardless of modifiedTime. Same source of truth as
    #    historical_backfill's per-folder prior-run check.
    # 2. NAME KEYS (fallback): folders mapping to seeded clients whose
    #    ledger key is 'local:…'/NULL — those ids can never match, and
    #    re-ingesting them duplicated the corpus (2026-06-18 incident).
    # `--since` (full re-ingest) opts out of both — the operator is
    # explicitly asking to re-pull everything.
    ledger = set() if args.since else _load_ingested_folder_ids()
    known = set() if args.since else _load_known_active_keys()
    already_ingested = sum(1 for f in changed if (f.get("id") or "") in ledger)
    new = [
        f for f in changed
        if (f.get("id") or "") not in ledger
        and not _folder_is_known(f.get("name"), known)
    ]
    excluded_existing = len(changed) - len(new)

    # ── bound ────────────────────────────────────────────────────────
    # Cap NEW folders per run so a cold start (everything "new") can't
    # balloon into an unbounded sweep; the remainder rolls to the next
    # 6h crawl. Deterministic order (by name) so the cap is stable.
    new.sort(key=lambda f: (f.get("name") or ""))
    capped = len(new) > CRAWLER_MAX_FOLDERS
    if capped:
        new = new[:CRAWLER_MAX_FOLDERS]

    ex.update(folders_seen=len(folders), folders_new=len(new))
    print(json.dumps({
        "mode": "live",
        "folders_seen": len(folders),
        "folders_changed": len(changed),
        "folders_already_ingested": already_ingested,
        "folders_existing_skipped": excluded_existing,
        "folders_new_to_ingest": len(new),
        "capped_to_max": CRAWLER_MAX_FOLDERS if capped else None,
        "concurrency": CRAWLER_CONCURRENCY,
        "deadline_sec": CRAWLER_DEADLINE_SEC,
        "started_at": started_at.isoformat(),
    }, indent=2))

    if args.dry_run or not new:
        return 0

    # Per-folder ingest. Wraps in TemporaryDirectory so partial
    # downloads are cleaned up regardless of outcome. Counters flush
    # live so the Admin UI tile reflects progress without waiting for
    # the whole sweep.
    import asyncio
    import tempfile
    import time
    from pathlib import Path

    # Counters live in a shared dict so they survive a deadline-driven
    # cancellation (we still report what completed before the cut-off).
    counts = {"ok": 0, "skipped": 0, "failed": 0}

    async def _run_ingests() -> None:
        sem = asyncio.Semaphore(max(1, CRAWLER_CONCURRENCY))
        deadline = time.monotonic() + CRAWLER_DEADLINE_SEC
        with tempfile.TemporaryDirectory() as td:
            tmp_root = Path(td)

            async def _one(i: int, folder: dict) -> None:
                name = folder.get("name")
                # Soft deadline: don't START new work past the cut-off
                # (in-flight downloads finish; the rest rolls to next crawl).
                if time.monotonic() >= deadline:
                    return
                async with sem:
                    if time.monotonic() >= deadline:
                        return
                    print(f"[{i}/{len(new)}] {name}", flush=True)
                    # Per-task Drive service — googleapiclient service
                    # objects are NOT safe for concurrent requests (see the
                    # NOTE on drive_client.download_file_async). Sharing the
                    # listing service across CRAWLER_CONCURRENCY tasks
                    # corrupted its TLS session: every download died with
                    # 'SSLError: [SSL] record layer failure' / 'TimeoutError:
                    # The read operation timed out' (2026-07-06 execution
                    # 7sdfs) while the backfill — one service per folder
                    # task — read the same root cleanly. Mirror the
                    # backfill's _run_folder pattern.
                    try:
                        task_service = (
                            await asyncio.to_thread(build_drive_service)
                            if CRAWLER_CONCURRENCY > 1 else service
                        )
                    except Exception as e:
                        task_service = None
                        res = (f"ERROR:drive:{name}: could not build Drive "
                               f"service: {type(e).__name__}: {e}")
                    if task_service is not None:
                        # Folder-level retry with backoff on transient Drive/
                        # network errors (429/5xx, SSL, read timeout) — the
                        # backfill's _run_folder attempt loop, shared via
                        # drive_client. Retries never start past the soft
                        # deadline; _ingest_folder is idempotent so a retry
                        # pass fast-skips already-persisted work.
                        try:
                            res = await run_with_transient_retries(
                                lambda: _ingest_folder(
                                    task_service, folder, tmp_root,
                                ),
                                attempts=3,
                                label=str(name),
                                is_retryable=lambda e: (
                                    time.monotonic() < deadline
                                    and is_transient_drive_error(e)
                                ),
                            )
                        except Exception as e:
                            res = (f"ERROR:top-level:{name}: "
                                   f"{type(e).__name__}: {e}")
                    if res.startswith("OK:"):
                        print(f"   ✓ {name} run_id={res[3:]}", flush=True)
                        counts["ok"] += 1
                    elif res.startswith("SKIP:"):
                        print(f"   → {name} {res[5:]}", flush=True)
                        counts["skipped"] += 1
                    else:
                        print(f"   ✗ {res}", flush=True)
                        counts["failed"] += 1
                    # NB: folders_new is NOT updated here — it was set once
                    # to the new-candidate count above. The old code
                    # overwrote it with the OK count, so a run where every
                    # download failed reported folders_new=0 even though 25
                    # genuinely-new folders were attempted (2026-07-06
                    # execution 7sdfs audit row).
                    ex.update(
                        files_parsed=counts["ok"],
                        files_skipped=counts["skipped"],
                        files_errored=counts["failed"],
                    )

            # Bounded-concurrency fan-out (was a strictly sequential loop).
            await asyncio.gather(*(_one(i, f) for i, f in enumerate(new, 1)))

    timed_out = False
    try:
        # Hard backstop: even a single wedged download can't outrun this.
        asyncio.run(asyncio.wait_for(
            _run_ingests(), timeout=CRAWLER_DEADLINE_SEC + 30,
        ))
    except TimeoutError:  # asyncio.TimeoutError is an alias since py3.11
        timed_out = True
        print(f"drive_crawler: hit hard deadline ({CRAWLER_DEADLINE_SEC}s); "
              f"stopped — remainder rolls to the next crawl.",
              file=sys.stderr, flush=True)

    ok, skipped, failed = counts["ok"], counts["skipped"], counts["failed"]
    print(
        f"drive_crawler: {ok}/{len(new)} ingested, {skipped} skipped, "
        f"{failed} failed{' (deadline cut)' if timed_out else ''}.",
        flush=True,
    )
    # Exit contract (infra/EXIT_CODES.md § drive_crawler): PARTIAL-OK is
    # success — failures are counted in files_errored and the failed
    # folders (no ACTIVE run) are re-picked by the ledger reconciliation
    # next crawl, so one flaky folder never poisons the run status. Only
    # a SYSTEMIC failure (≥1 failed, ZERO ingested OK — every download
    # dying, the 2026-07-06 incident shape) exits 7 and marks the job
    # execution FAILED.
    if failed == 0 or ok > 0:
        return 0
    return 7


if __name__ == "__main__":
    raise SystemExit(main())
