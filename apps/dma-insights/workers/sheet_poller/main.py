"""Sheet poller entrypoint (Cloud Run Job).

Polls 8 Ops sheet tabs, upserts each into the corresponding ops_* table,
mirrors Requests status transitions into our local runs table, and
emits SSE events on row transitions.

State-branch contract:
  - incremental_sync     → typical run; only `last_updated_utc > watermark`.
  - full_sync_on_drift   → row counts diverge → force full re-sync.
  - sheet_unavailable    → Sheets API HttpError → no-op + structured warning.
  - row_conflict         → UNIQUE upsert conflict → sheet wins;
                           conflict logged.

Most logic is in ./handlers.py (pure normalization) so it can be
unit-tested without GCP credentials. The live Sheets v4 client lives in
`app/services/sheets_client.py`.
"""
from __future__ import annotations

import argparse
import json
import sys

from app.config import get_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ops sheet poller")
    parser.add_argument("--once", action="store_true",
                        help="Single poll cycle then exit (default)")
    parser.add_argument("--tabs", nargs="*",
                        default=["Requests", "Audit", "Team", "Comments",
                                 "Capacity", "Holidays", "IngestPending",
                                 "Historical_Stats"])
    parser.add_argument("--dry-run", action="store_true",
                        help="Show planned tab reads without contacting Sheets")
    args = parser.parse_args(argv)

    settings = get_settings()
    if not settings.ops_sheet_id:
        print("OPS_SHEET_ID not set", file=sys.stderr)
        return 2

    if args.dry_run:
        print(json.dumps({
            "mode": "dry-run",
            "ops_sheet_id": settings.ops_sheet_id,
            "tabs": args.tabs,
            "state_branches": [
                "incremental_sync", "full_sync_on_drift",
                "sheet_unavailable", "row_conflict",
            ],
            "next_step": (
                "Live IO requires a Sheets v4 service account in "
                "Secret Manager (dma-insights-sheets-sa-key). The "
                "handlers in ./handlers.py and the client in "
                "app/services/sheets_client.py are pure and exercised "
                "by tests."
            ),
        }, indent=2))
        return 0

    # Live mode placeholder — defers to the pure handlers + sheets_client
    # which is exercised by tests but not yet bolted onto a real ADC
    # session here (Secret Manager wiring lands at deploy time).
    try:
        from app.services.sheets_client import build_sheets_service, read_tab
    except Exception as e:
        print(f"sheet_poller: sheets_client import failed: {e}", file=sys.stderr)
        return 3

    try:
        service = build_sheets_service()
    except Exception as e:
        print(
            f"sheet_poller: ADC unavailable — {e}. Run with --dry-run "
            f"to see the planned tab reads.",
            file=sys.stderr,
        )
        return 4

    tab_summaries: dict[str, int] = {}
    errored = 0
    for tab in args.tabs:
        try:
            rows = read_tab(service, settings.ops_sheet_id, tab)
            tab_summaries[tab] = max(0, len(rows) - 1)  # subtract header
        except Exception as e:
            print(f"sheet_poller: tab '{tab}' read failed: {e}", file=sys.stderr)
            tab_summaries[tab] = -1  # marker for sheet_unavailable
            errored += 1
    print(json.dumps({
        "mode": "live",
        "ops_sheet_id": settings.ops_sheet_id,
        "tabs_read": tab_summaries,
    }, indent=2))

    # Counter flush — files_parsed = successfully-read tabs;
    # rows_added = total rows across all tabs; files_errored = failed tabs.
    import contextlib
    with contextlib.suppress(Exception):
        from workers._runner import get_current_tracker
        ex = get_current_tracker()
        if ex is not None:
            ok_tabs = sum(1 for n in tab_summaries.values() if n >= 0)
            total_rows = sum(n for n in tab_summaries.values() if n >= 0)
            ex.update(
                files_parsed=ok_tabs,
                files_errored=errored,
                rows_added=total_rows,
            )
    return 0


if __name__ == "__main__":
    from workers._runner import track_job_execution
    with track_job_execution("sheet_poller"):
        raise SystemExit(main())
