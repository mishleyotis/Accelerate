"""chat_learning rollup Cloud Run Job entrypoint.

Nightly job. Usage:
  python -m workers.chat_learning.main --dry-run
  python -m workers.chat_learning.main --since 2026-05-01

State transitions:
  --dry-run
    → prints summary; no DB writes; STILL writes a job_executions row
      (mode=dry-run) so the operator audit shows the nightly cron ran
  no chat_messages exist
    → exits 0; no chat_learning_signals rows written; job_executions row
      flips to status=succeeded with files_parsed=0
  embeddings missing on some messages
    → live mode embeds them inline via Vertex; counters incremented
  Vertex unreachable / DB unreachable
    → exception propagates; `track_job_execution` writes status=failed
      with the traceback's last 30 lines for Admin → Import Audit
"""
from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="DMA Insights chat_learning rollup")
    p.add_argument("--since", help="ISO date — only consider feedback since")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    # Wrap the entire run in track_job_execution so failures land in
    # `job_executions` (admin UI sees them) and success counters land
    # too. Before this change, chat_learning was the only worker that
    # bypassed _runner — a silent observability gap (a nightly run
    # that crashed at 03:00 left no admin trace).
    from workers._runner import track_job_execution

    mode = "dry-run" if args.dry_run else "live"
    with track_job_execution("chat_learning", mode=mode) as ex:
        if args.dry_run:
            print(json.dumps({
                "mode": "dry-run",
                "since": args.since,
                "next_step": "Without --dry-run, the worker reads chat_messages "
                             "+ chat_feedback, embeds missing rows, clusters "
                             "questions, and writes chat_learning_signals.",
            }, indent=2))
            ex.update(files_parsed=0, rows_added=0)
            return 0

        import asyncio

        from workers.chat_learning.live import run

        result = asyncio.run(run(since=args.since))
        # `run` is best-effort — return a dict shape so we can log
        # counters into job_executions; absent counters → 0.
        if isinstance(result, dict):
            ex.update(
                rows_added=int(result.get("rows_added", 0)),
                files_parsed=int(result.get("messages_processed", 0)),
                files_skipped=int(result.get("messages_skipped", 0)),
            )
        return 0


if __name__ == "__main__":
    sys.exit(main())
