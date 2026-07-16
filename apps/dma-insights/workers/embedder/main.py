"""Embedder Cloud Run Job entrypoint.

Usage (local):
  python -m workers.embedder.main --run-id <UUID>
  python -m workers.embedder.main --since '2026-05-01' --batch-size 32
  python -m workers.embedder.main --dry-run --run-id <UUID>
  python -m workers.embedder.main --subscribe          # long-lived

Production trigger: Pub/Sub message from `ingest_assessment` (the ingest
router publishes `dma.ingest.completed` with the run_id after a successful
upsert). Cloud Run Eventarc subscription invokes this job with the run_id.

When run with --subscribe the worker stays up and dispatches
incoming Pub/Sub messages from the `dma.ingest.completed` topic to the
same live-path embed_run() entrypoint. Idempotency is handled by the
embedder service (it skips already-embedded rows under the same
model_version, so concurrent triggers for the same run_id collapse
to a single set of writes).

This module wires the pure service helpers in ./service.py to:
  - SQLAlchemy session for reads + UPSERTs
  - Vertex text-embedding-004 via the injectable VertexClient.embed()

The Vertex call is *lazy*: --dry-run skips it and prints the candidate
texts. Live wiring lands when Vertex creds are mounted in the Cloud Run
Job; until then the dry-run flow is fully exercisable.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC

from app.config import get_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DMA Insights embedder")
    parser.add_argument("--run-id", help="UUID of a single run to embed")
    parser.add_argument("--since", help="ISO date — embed runs completed since this date")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--model-version", default=None,
                        help="Override Vertex model id (default: settings.vertex_embedding_model)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print candidates but don't call Vertex or write")
    parser.add_argument("--subscribe", action="store_true",
                        help="Long-lived: subscribe to dma.ingest.completed "
                        "and dispatch embed_run per message.")
    parser.add_argument("--subscription",
                        default="dma-ingest-completed-embedder",
                        help="Pub/Sub subscription ID (subscribe mode only).")
    # `--once`: admin "Embeddings" button + Cloud Run Job default arg.
    # Means "process every run completed within the last 24h that doesn't
    # yet have section_embeddings rows". Without it the worker errored out
    # with argparse: unrecognized arguments: --once (2026-05-29 audit).
    parser.add_argument("--once", action="store_true",
                        help="Single pass: embed every run from the last 24h "
                        "that lacks section_embeddings rows, then exit.")
    args = parser.parse_args(argv)
    # `--once` is equivalent to `--since` 24h ago when no other selector
    # is supplied. An explicit --run-id or --since wins. Use `.date()`
    # — the live path parses with `date.fromisoformat()` (line ~112) which
    # REJECTS full datetime strings with `ValueError: Invalid isoformat`.
    # Without this, every --once invocation crashes at run-selection
    # (2026-05-29 QA audit P1 trap).
    if args.once and not args.run_id and not args.since:
        from datetime import datetime, timedelta
        args.since = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()

    settings = get_settings()
    model_version = args.model_version or settings.vertex_embedding_model

    if args.subscribe:
        return _run_subscriber(
            subscription_id=args.subscription,
            batch_size=args.batch_size,
            model_version=model_version,
        )

    if not args.run_id and not args.since:
        print(
            "embedder: one of --run-id, --since, or --subscribe is required",
            file=sys.stderr,
        )
        return 2

    if args.dry_run:
        # Dry-run summary path — show the configuration so an operator can
        # confirm the scope before flipping to a live run.
        summary = {
            "mode": "dry-run",
            "run_id": args.run_id,
            "since": args.since,
            "batch_size": args.batch_size,
            "model_version": model_version,
            "next_step": (
                "Without --dry-run, the worker will read candidate "
                "evidence/insights/recommendations from the DB, call "
                "Vertex text-embedding-005 in batches of "
                f"{args.batch_size}, and UPSERT into the *_embeddings "
                "tables. Run the live path only after seeding the DB."
            ),
        }
        print(json.dumps(summary, indent=2))
        return 0

    # Live path — requires Postgres (DATABASE_URL env) + Vertex creds.
    import asyncio
    from datetime import date as _date

    from workers.embedder.live import embed_run

    since_date: _date | None = None
    if args.since:
        since_date = _date.fromisoformat(args.since)

    total = asyncio.run(
        embed_run(
            run_id=args.run_id,
            since=since_date,
            batch_size=args.batch_size,
            model_version=model_version,
        )
    )
    print(f"embedder: done — {total} embeddings written.", flush=True)
    return 0


def _run_subscriber(
    *,
    subscription_id: str,
    batch_size: int,
    model_version: str,
) -> int:
    """Long-lived Pub/Sub consumer for `dma.ingest.completed`.

    State branches:
      message has run_id        → dispatch embed_run(run_id=…)
      message has no run_id     → ack + log warning (skip)
      embed_run raises          → NACK; Pub/Sub redelivers
      embed_run succeeds        → ACK; idempotent on next delivery
                                   (embedder skips already-embedded rows)
      ADC / project missing     → return 3 (exit before subscribing)
    """
    import asyncio

    settings = get_settings()
    project_id = settings.gcp_project_id
    if not project_id:
        print("embedder: GCP_PROJECT_ID required for --subscribe", file=sys.stderr)
        return 3
    try:
        from google.cloud import pubsub_v1
    except Exception as e:
        print(f"embedder: google-cloud-pubsub not installed: {e}", file=sys.stderr)
        return 3

    subscriber = pubsub_v1.SubscriberClient()
    sub_path = subscriber.subscription_path(project_id, subscription_id)

    from workers.embedder.live import embed_run

    def handle(message) -> None:
        try:
            payload = json.loads(message.data.decode("utf-8"))
        except Exception as e:
            print(f"embedder: bad payload — {e}", file=sys.stderr)
            message.ack()
            return
        run_id = payload.get("run_id")
        if not run_id:
            print("embedder: message missing run_id — ack+skip", file=sys.stderr)
            message.ack()
            return
        try:
            n = asyncio.run(
                embed_run(
                    run_id=run_id, since=None,
                    batch_size=batch_size,
                    model_version=model_version,
                )
            )
            print(f"embedder: run={run_id} embedded {n}", flush=True)
            message.ack()
        except Exception as e:
            print(f"embedder: run={run_id} FAILED — {type(e).__name__}: {e}",
                  file=sys.stderr, flush=True)
            message.nack()

    future = subscriber.subscribe(sub_path, callback=handle)
    print(f"embedder: subscribed to {sub_path}", flush=True)
    try:
        future.result()  # blocks
    except KeyboardInterrupt:
        future.cancel()
    return 0


if __name__ == "__main__":
    from workers._runner import track_job_execution
    with track_job_execution("embedder"):
        raise SystemExit(main())
