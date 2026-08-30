#!/usr/bin/env python3
"""Which ingested runs should be synthesised next, and which must not be.

THE GAP THIS FILLS. The package scan fills a queue every thirty minutes and
nothing drains it: measured 2026-08-16, 286 runs at INGESTED across 171
entities, none synthesised. Ingest is not the constraint — synthesis is, and
the scheduling the charter places in stages 2-3 has to start by knowing WHICH
run to hand a producer.

That is not "every pending run", and getting it wrong is expensive in a way
that is hard to see afterwards:

  * 105 of the 171 entities carry MORE THAN ONE pending run — 286 for 171
    clients — because an ingest guard keyed on the Drive file id could not
    tell a re-uploaded workbook from a new assessment. One entity holds three
    runs at run_seq 1, 2 and 3 with the same request id, composite and cell
    count. A loop that walked the queue naively would synthesise the same
    assessment three times, spend three producers on it, and leave the
    directory to pick between identical candidates.
  * A run someone is already working carries a live claim. Handing it out
    again means two producers writing the same six pages.
  * A run whose entity already serves is a RERUN, and the skill requires a
    rerun be produced knowing what the last one said — a different job from a
    first synthesis, and one a scheduler should not start blind.

So this selects, and states its reason for every run it skips. Nothing here
writes: it reads the connector's own view and prints a plan.

    python scripts/synthesis_queue.py --pending <list_pending_runs.json>
                                      [--limit N] [--json]

`--pending` is the raw `list_pending_runs` result. Kept as a file argument
rather than a live call so the selection can be re-run, diffed and tested
against a captured queue without touching production.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict

#: Reasons a pending run is not offered to a producer. Stated, never silent —
#: a queue that quietly drops work is indistinguishable from an empty one.
SKIP_CLAIMED = "another session holds a live claim on this entity"
SKIP_SUPERSEDED = "a newer run_seq exists for this entity"
#: A DIFFERENT request for an entity already in the plan. Distinguished from
#: SKIP_SUPERSEDED because they are not the same event: an obsolete re-ingest
#: has nobody waiting on it, and a second request has a requester who is
#: never told their ask was absorbed into someone else's (AUD-0072).
SKIP_ABSORBED = ("a different request for the same entity is already in the "
                 "plan — this one is DEFERRED, not obsolete; re-queue it "
                 "once the entity's current run is promoted")
SKIP_NO_DATE = "no assessment date; ordering it against the others would guess"


def _seq(run: dict) -> int:
    """`run_seq` if the caller supplied it, else 0. `list_pending_runs` does
    not return it, so callers that care pass an enriched list; ordering falls
    back to `completed_at` and then to the request id, which is stable."""
    try:
        return int(run.get("run_seq") or 0)
    except (TypeError, ValueError):
        return 0


def _newer(a: dict, b: dict) -> dict:
    """The run of two that a producer should work.

    run_seq first where both carry one — it is the ingest's own ordering.
    Then completed_at. Then the run id, purely so the answer is STABLE: an
    arbitrary-but-fixed choice can be reproduced and argued with, and a
    different answer on every run cannot.
    """
    if _seq(a) != _seq(b):
        return a if _seq(a) > _seq(b) else b
    ca, cb = a.get("completed_at") or "", b.get("completed_at") or ""
    if ca != cb:
        return a if ca > cb else b
    return a if str(a.get("run_id")) > str(b.get("run_id")) else b


def _key(run: dict):
    return run.get("display_id") or run.get("run_id")


def select(pending: list, limit: int | None = None) -> dict:
    """Split the pending queue into what to work and what to skip, with why.

    THE CLAIM IS AN ENTITY-LEVEL FACT, NOT A RUN-LEVEL ONE, and the ordering of
    these two steps is the whole correctness of this function.

    An earlier version partitioned claimed from unclaimed FIRST and deduped the
    remainder, which quietly reintroduced the duplicate it exists to prevent:
    the claimed run never entered the pool, so the entity's SECOND-newest run
    won `best` and was handed out as if the entity were free. Measured on
    2026-08-21: `t-rowe-price-group-inc` seq 4 was live-claimed and seq 3 — a
    different request, three days older — was offered. 105 of 171 entities
    carry more than one pending run, so this is the common shape, not an edge.

    The other direction is the same harm: an older run under a live claim while
    a newer one is offered puts two producers on one entity's six pages. Both
    promote, and the directory chooses between them. So a live claim ANYWHERE
    in an entity's runs holds the WHOLE entity, and every one of its runs is
    skipped naming that claim.
    """
    # One run per entity: the newest, chosen over ALL pending runs including
    # claimed ones. Deduping first is what makes the claim check meaningful.
    best: dict = {}
    for run in pending:
        key = _key(run)
        best[key] = run if key not in best else _newer(best[key], run)

    held = {_key(r) for r in pending if (r.get("claim") or {}).get("live")}

    claimed = [r for r in pending if _key(r) in held]
    superseded = [r for r in pending
                  if _key(r) not in held and r is not best.get(_key(r))]

    # AUD-0072: the dedupe grain is the ENTITY, and that is correct — the
    # docstring above is the measured reason. What was missing is the
    # distinction inside `superseded`. Two runs of the SAME request are a
    # re-ingest and the older one is genuinely obsolete. Two runs of
    # DIFFERENT requests are two people who each asked for an assessment, and
    # collapsing them silently means the second requester is never told their
    # request was absorbed into someone else's.
    #
    # The grain does not change — two producers on one entity's six pages
    # both promote and the directory picks between them, which is the harm
    # this function exists to prevent. The ABSORPTION is now named, so a
    # human or a routine can see it and re-queue.
    absorbed = [r for r in superseded
                if r.get("request_id")
                and (best.get(_key(r)) or {}).get("request_id")
                and r["request_id"] != best[_key(r)]["request_id"]]
    absorbed_ids = {id(r) for r in absorbed}
    superseded = [r for r in superseded if id(r) not in absorbed_ids]

    ready = [r for k, r in best.items() if k not in held]
    # Newest assessment first: a six-week-old DMA is worth more to a client
    # conversation than a six-month-old one, and the queue is long enough that
    # the order decides what actually gets done.
    ready.sort(key=lambda r: (r.get("completed_at") or "", str(r.get("run_id"))),
               reverse=True)
    undated = [r for r in ready if not r.get("completed_at")]
    dated = [r for r in ready if r.get("completed_at")]

    plan = dated + undated
    if limit is not None:
        plan = plan[:limit]

    return {
        "counts": {
            "pending": len(pending),
            "entities": len({r.get("display_id") for r in pending}),
            # Runs held back because their ENTITY carries a live claim — which
            # is more runs than carry the claim themselves, and deliberately so.
            "claimed": len(claimed),
            "held_entities": len(held),
            "superseded": len(superseded),
            # A DIFFERENT request for an entity already in the plan. Not an
            # obsolete re-ingest — a second asker, whose request is being
            # deferred rather than served.
            "absorbed_requests": len(absorbed),
            "ready": len(ready),
            "undated": len(undated),
            "selected": len(plan),
        },
        "selected": [{"run_id": r["run_id"], "display_id": r.get("display_id"),
                      "completed_at": r.get("completed_at"),
                      "request_id": r.get("request_id")} for r in plan],
        "skipped": (
            [{"run_id": r["run_id"], "display_id": r.get("display_id"),
              "why": SKIP_CLAIMED} for r in claimed]
            + [{"run_id": r["run_id"], "display_id": r.get("display_id"),
                "why": SKIP_SUPERSEDED} for r in superseded]
            + [{"run_id": r["run_id"], "display_id": r.get("display_id"),
                "request_id": r.get("request_id"),
                "absorbed_into": (best.get(_key(r)) or {}).get("run_id"),
                "absorbed_into_request": (best.get(_key(r)) or {}
                                          ).get("request_id"),
                "why": SKIP_ABSORBED} for r in absorbed]),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pending", required=True,
                    help="raw list_pending_runs JSON")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    doc = json.loads(open(args.pending).read())
    pending = doc.get("pending") if isinstance(doc, dict) else doc
    out = select(pending or [], args.limit)

    if args.json:
        print(json.dumps(out, indent=1))
        return 0

    c = out["counts"]
    print(f"pending          {c['pending']} runs across {c['entities']} entities")
    print(f"  claimed        {c['claimed']} run(s) across {c['held_entities']} "
          f"entity(ies)  ({SKIP_CLAIMED})")
    print(f"  superseded     {c['superseded']}  ({SKIP_SUPERSEDED})")
    print(f"  ready          {c['ready']}   of which undated {c['undated']}")
    print(f"  SELECTED       {c['selected']}\n")
    for r in out["selected"]:
        print(f"  {(r['completed_at'] or 'undated')[:10]}  {r['run_id']}  "
              f"{r['display_id']}")
    if c["superseded"]:
        print(f"\n{c['superseded']} superseded run(s) are NOT work: they are the "
              "duplicate ingests of an assessment already selected above. "
              "Synthesising one spends a producer to produce a second copy of "
              "a page set the directory then has to choose between.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
