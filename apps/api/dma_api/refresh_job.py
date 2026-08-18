"""`dmai-refresh` — the Cloud Run Job that records a refresh request.

    python -m dma_api.refresh_job --entity <display_id> --actor <email>
                                  [--reason "..."] [--cancel]

## Why this is a Job and not an endpoint

Invariant 2 enumerates the API's writes: annotations and alert actions, both
behind an Idempotency-Key. A refresh request is neither. It is workflow state
of exactly the same class — a person asked for something, here is who and
when and what became of it — and `POST /v1/entities/{id}/refresh` would be
the better piece of engineering: synchronous, replayable on a key, no cold
start. It is not built, because building it means widening an enumeration the
charter states, and that is the user's call to make, not a decision to take
quietly inside a feature.

So the write happens where writes of this kind already happen. The web
service fires this Job the same way its admin "Run scan now" button already
fires `dmai-worker`, and the Job connects as `dmai-worker` — svc_worker, the
only role granted INSERT on `refresh_requests` (0032). svc_api holds SELECT
and nothing else, which is not documentation but a grant: an endpoint that
tried to write this table would fail on permissions, in production, with a
database error naming the table.

What that costs, stated plainly: a cold start between the click and the row
(seconds, not milliseconds), no synchronous confirmation — the web polls
`GET /v1/entities/{id}/refresh` — one Job execution per click, and no
Idempotency-Key, so the double-click is collapsed by a partial unique index
instead (one open request per entity). A second click while a request is open
returns that request rather than creating another, and says so.

## What it will not do

It records a request. It does not create a run, does not schedule anything,
does not promise a time, and prints nothing that could be read as one — the
"Rerun queued — first batch in ~3 min" toast this replaces was a sentence with
no mechanism behind it. The synthesis routine reads
`GET /v1/ops/refresh-queue` and decides; a request that nothing has picked up
yet stays REQUESTED, visibly.
"""
from __future__ import annotations

import argparse
import json
import sys

from .db import close as db_close, connect

OPEN = ("REQUESTED", "ACKNOWLEDGED")

_COLS = ("id", "entity_id", "observed_run_id", "origin", "requested_by",
         "reason", "status", "fulfilled_by_run_id", "requested_at",
         "updated_at", "note")


def _out(payload: dict) -> None:
    """One line of JSON on stdout: this runs as a Cloud Run Job, so its log
    IS its response. Structured so the caller can read it back."""
    print(json.dumps(payload, default=str), flush=True)


def _resolve(cur, display_id: str):
    """entity id and the run in force, from the ingested tier svc_worker
    reads. Not from `serving_directory` — svc_worker holds no grant on it,
    and an entity with no promoted run can still be asked for."""
    cur.execute("SELECT id FROM entities WHERE display_id = %s", (display_id,))
    row = cur.fetchone()
    if not row:
        return None, None
    entity_id = row[0]
    cur.execute(
        """SELECT id FROM runs
            WHERE entity_id = %s AND promoted_at IS NOT NULL
            ORDER BY is_active DESC NULLS LAST, promoted_at DESC LIMIT 1""",
        (entity_id,))
    run = cur.fetchone()
    return entity_id, (run[0] if run else None)


def _open_request(cur, entity_id):
    cur.execute(
        f"SELECT {', '.join(_COLS)} FROM refresh_requests "
        "WHERE entity_id = %s AND status = ANY(%s) "
        "ORDER BY requested_at DESC, id DESC LIMIT 1",
        (entity_id, list(OPEN)))
    row = cur.fetchone()
    return dict(zip(_COLS, row)) if row else None


def request_refresh(conn, display_id: str, actor: str,
                    reason: str | None = None, cancel: bool = False) -> dict:
    cur = conn.cursor()
    entity_id, run_id = _resolve(cur, display_id)
    if entity_id is None:
        return {"ok": False, "error": "entity_not_found",
                "detail": f"no entity with display_id {display_id!r}",
                "display_id": display_id}

    existing = _open_request(cur, entity_id)

    if cancel:
        if not existing:
            return {"ok": True, "action": "nothing_to_cancel",
                    "display_id": display_id,
                    "detail": "no open refresh request for this client"}
        cur.execute(
            "UPDATE refresh_requests SET status = 'CANCELLED', updated_at = now(), "
            "note = %s WHERE id = %s",
            (f"cancelled by {actor}", existing["id"]))
        conn.commit()
        return {"ok": True, "action": "cancelled", "display_id": display_id,
                "request_id": existing["id"]}

    if existing:
        # The double-click, and the second person asking for the same thing.
        # Neither creates a second row, and the answer says which it is.
        conn.rollback()
        return {"ok": True, "action": "already_open", "display_id": display_id,
                "request_id": existing["id"],
                "status": existing["status"],
                "requested_by": existing["requested_by"],
                "requested_at": str(existing["requested_at"]),
                "detail": ("a refresh is already open for this client; a "
                           "second request would not make it happen sooner")}

    cur.execute(
        """INSERT INTO refresh_requests
             (entity_id, observed_run_id, origin, requested_by, reason, status)
           VALUES (%s, %s, 'human', %s, %s, 'REQUESTED')
        RETURNING id, requested_at""",
        (entity_id, run_id, actor, reason))
    new_id, requested_at = cur.fetchone()
    conn.commit()
    return {"ok": True, "action": "requested", "display_id": display_id,
            "request_id": new_id, "status": "REQUESTED",
            "requested_by": actor, "reason": reason,
            "observed_run_id": str(run_id) if run_id else None,
            "requested_at": str(requested_at),
            "detail": ("recorded. Nothing is scheduled by this row: the "
                       "synthesis routine reads /v1/ops/refresh-queue and "
                       "decides.")}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="dma_api.refresh_job")
    p.add_argument("--entity", required=True, help="entity display_id (slug)")
    p.add_argument("--actor", required=True,
                   help="the signed-in email asking; a request with no "
                        "requester is an anonymous instruction and the table "
                        "refuses it")
    p.add_argument("--reason", default=None)
    p.add_argument("--cancel", action="store_true",
                   help="close the open request for this client")
    args = p.parse_args(argv)

    if not args.actor.strip():
        _out({"ok": False, "error": "actor_required"})
        return 2

    conn = connect()
    try:
        result = request_refresh(conn, args.entity.strip(), args.actor.strip(),
                                 reason=args.reason, cancel=args.cancel)
    except Exception as e:                                    # noqa: BLE001
        conn.rollback()
        # The class and message, never the connection string or the identity.
        _out({"ok": False, "error": "write_failed",
              "detail": f"{type(e).__name__}: {str(e)[:300]}"})
        return 1
    finally:
        conn.close()
        db_close()

    _out(result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
