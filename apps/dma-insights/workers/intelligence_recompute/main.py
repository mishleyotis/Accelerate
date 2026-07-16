"""intelligence_recompute Cloud Run entrypoint.

Two execution modes:

  --entity-id <UUID>   one-shot Cloud Run Job: recompute the named entity.
  --subscribe          long-lived Cloud Run Service: subscribe to the
                       `dma.ingest.completed` Pub/Sub topic and dispatch
                       a recompute per inbound message.

State branches when dispatching (mirror service.classify_worker_state):

  message has entity_id      → recompute_entity(entity_id)
  message has only run_id    → resolve entity via runs table → recompute
  message missing both       → ack + log warning (skip)
  recompute_entity raises    → NACK (Pub/Sub redelivers)
  recompute_entity returns   → ACK; subsequent deliveries idempotent-skip
                               when nothing has changed.
  ADC / project missing      → subscriber returns 3 before subscribing
"""
from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="DMA Insights intelligence_recompute")
    p.add_argument("--entity-id", help="UUID of entity to recompute")
    p.add_argument("--all", action="store_true",
                   help="Backfill: recompute every ACTIVE entity")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--subscribe", action="store_true",
                   help="Subscribe to dma.ingest.completed topic")
    p.add_argument("--subscription",
                   default="dma-ingest-completed-intelligence",
                   help="Pub/Sub subscription ID (subscribe mode only)")
    args = p.parse_args(argv)

    if args.dry_run:
        print(json.dumps({
            "mode": "dry-run",
            "entity_id": args.entity_id,
            "all": args.all,
            "subscribe": args.subscribe,
            "next_step": (
                "Without --dry-run the worker loads runs + evidence + "
                "existing profile, calls Vertex Pro for the summary, "
                "embeds via text-embedding-004, and UPSERTs the row in "
                "customer_intelligence_profiles."
            ),
        }, indent=2))
        return 0

    if args.subscribe:
        return _run_subscriber(subscription_id=args.subscription)

    if not args.entity_id and not args.all:
        print("intelligence_recompute: one of --entity-id, --all, or "
              "--subscribe required", file=sys.stderr)
        return 2

    import asyncio

    from workers.intelligence_recompute.live import recompute_entity

    if args.all:
        return asyncio.run(_recompute_all())
    state = asyncio.run(recompute_entity(entity_id=args.entity_id))
    print(f"intelligence_recompute: entity={args.entity_id} state={state}")
    return 0


async def _recompute_all() -> int:
    """Iterate every ACTIVE entity and recompute its profile."""
    from sqlalchemy import text as _text

    from app.database import get_sessionmaker
    from workers.intelligence_recompute.live import recompute_entity

    sm = get_sessionmaker()
    async with sm() as session:
        rows = (
            await session.execute(
                _text(
                    "SELECT id::text AS id FROM entities "
                    "WHERE status = 'ACTIVE' ORDER BY updated_at DESC"
                )
            )
        ).all()
    ids = [r.id for r in rows]
    print(f"intelligence_recompute: backfill over {len(ids)} entities")
    state_counts: dict[str, int] = {}
    # Best-effort tracker for admin pill counter updates.
    try:
        from workers._runner import get_current_tracker
        _ex = get_current_tracker()
    except Exception:
        _ex = None
    succeeded = errored = 0
    for eid in ids:
        try:
            state = await recompute_entity(entity_id=eid)
            succeeded += 1
        except Exception as e:
            print(
                f"intelligence_recompute: entity={eid} FAILED — {type(e).__name__}: {e}",
                file=sys.stderr,
            )
            state = "error"
            errored += 1
        state_counts[state] = state_counts.get(state, 0) + 1
        # Flush per-entity so the admin pill ticks instead of waiting
        # for the whole backfill to finish.
        if _ex is not None:
            import contextlib
            with contextlib.suppress(Exception):
                _ex.update(rows_updated=succeeded, files_errored=errored)
    print(f"intelligence_recompute: done — {state_counts}")
    return 0


def _run_subscriber(*, subscription_id: str) -> int:
    """Long-lived Pub/Sub consumer for `dma.ingest.completed`."""
    import asyncio

    from app.config import get_settings

    settings = get_settings()
    project_id = settings.gcp_project_id
    if not project_id:
        print(
            "intelligence_recompute: GCP_PROJECT_ID required for --subscribe",
            file=sys.stderr,
        )
        return 3

    try:
        from google.cloud import pubsub_v1
    except Exception as e:
        print(
            f"intelligence_recompute: google-cloud-pubsub not installed: {e}",
            file=sys.stderr,
        )
        return 3

    subscriber = pubsub_v1.SubscriberClient()
    sub_path = subscriber.subscription_path(project_id, subscription_id)

    from workers.intelligence_recompute.live import recompute_entity

    async def _resolve_entity_from_run(run_id: str) -> str | None:
        from sqlalchemy import text as _text

        from app.database import get_sessionmaker

        sm = get_sessionmaker()
        async with sm() as session:
            row = (
                await session.execute(
                    _text("SELECT entity_id::text AS eid FROM runs "
                          "WHERE id = CAST(:r AS uuid)"),
                    {"r": run_id},
                )
            ).first()
            return row.eid if row else None

    def handle(message) -> None:
        try:
            payload = json.loads(message.data.decode("utf-8"))
        except Exception as e:
            print(f"intelligence_recompute: bad payload — {e}", file=sys.stderr)
            message.ack()
            return
        entity_id = payload.get("entity_id")
        run_id = payload.get("run_id")
        if not entity_id and not run_id:
            print(
                "intelligence_recompute: message missing entity_id and run_id "
                "— ack+skip",
                file=sys.stderr,
            )
            message.ack()
            return
        try:
            if not entity_id and run_id:
                entity_id = asyncio.run(_resolve_entity_from_run(run_id))
                if not entity_id:
                    message.ack()
                    return
            state = asyncio.run(recompute_entity(entity_id=entity_id))
            print(
                f"intelligence_recompute: entity={entity_id} state={state}",
                flush=True,
            )
            message.ack()
        except Exception as e:
            print(
                f"intelligence_recompute: entity={entity_id} FAILED — "
                f"{type(e).__name__}: {e}",
                file=sys.stderr, flush=True,
            )
            message.nack()

    future = subscriber.subscribe(sub_path, callback=handle)
    print(f"intelligence_recompute: subscribed to {sub_path}", flush=True)
    try:
        future.result()
    except KeyboardInterrupt:
        future.cancel()
    return 0


if __name__ == "__main__":
    from workers._runner import track_job_execution
    with track_job_execution("intelligence_recompute"):
        raise SystemExit(main())
