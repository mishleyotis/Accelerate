"""withdraw_run — take a promoted run off the client surface, with a reason.

## The thing this replaces

`UPDATE runs SET is_active = FALSE` was the only lever, and it is not
suppression. `serving_directory` carries every run with a non-null
`promoted_at`, so the row survives the demotion: `/v1/directory` keeps
publishing the client's name, slug, sub-vertical and a run entry — while
every page beneath it 404s. What that produces is not "one fewer client",
it is one client and one named ghost, listed and unopenable.

0042 adds `runs.withdrawn_at` and puts `AND r.withdrawn_at IS NULL` in the
view, so a withdrawal removes the run from the ONE window svc_api reads.
Directory, alert queue, cadence, diff, annotations and every page resolve
through that view, so one predicate closes all of them at once — and none
of them needs to learn a new rule.

## What withdrawal does NOT do

It does not delete. Promoted rows are retained the way staging rows are
(invariant 3), and the reason is recorded on the run rather than in a
transcript. Alert rows are left untouched: `heatmap_alerts.status` is
open · resolved · waived, every one of which is a statement about the
FINDING, and writing `waived` here would fabricate a human decision that
belongs in `alert_actions` with somebody's name on it. The alerts leave
the queue because the queue joins the view, and they come back — still
open, still unactioned — when the run does.

## Reversal is a promote

`promote_run` clears `withdrawn_at`. There is deliberately no restore
tool: a run is withdrawn because what it served was wrong, and the honest
way back onto a client's screen is a promotion that passes the gates
again. A restore would be a way to un-withdraw without fixing anything.
"""
from __future__ import annotations

# A reason short enough to be a shrug is not a reason. Same floor the
# findings store puts on `measurement`, for the same reason: the field
# exists to be read by somebody who was not here.
_REASON_FLOOR = 30


def withdraw_run(conn, run_id: str, reason: str, actor: str) -> dict:
    """Withdraw one promoted run. Idempotent: withdrawing a withdrawn run
    reports the withdrawal already on it rather than restamping it, so a
    retry never overwrites the first reason with a vaguer second one."""
    reason = (reason or "").strip()
    actor = (actor or "").strip()
    if len(reason) < _REASON_FLOOR:
        return {"withdrawn": False, "error": "reason_required",
                "message": f"withdraw_run needs a reason of at least "
                           f"{_REASON_FLOOR} characters saying what is wrong "
                           f"with what this run serves; got {len(reason)}"}
    if not actor:
        return {"withdrawn": False, "error": "actor_required",
                "message": "name the agent or person withdrawing the run"}

    cur = conn.cursor()
    try:
        cur.execute(
            """SELECT r.entity_id, e.display_id, r.promoted_at, r.withdrawn_at,
                      r.withdrawn_reason, r.withdrawn_by
                 FROM runs r JOIN entities e ON e.id = r.entity_id
                WHERE r.id = %s
                  FOR UPDATE OF r""", (run_id,))
        row = cur.fetchone()
        if row is None:
            conn.rollback()
            return {"withdrawn": False, "error": "unknown_run"}
        entity_id, display_id, promoted_at, already, prev_reason, prev_by = row

        if promoted_at is None:
            conn.rollback()
            return {"withdrawn": False, "error": "not_promoted",
                    "message": f"run {run_id} has never promoted, so there is "
                               f"nothing on a client surface to withdraw"}
        if already is not None:
            conn.rollback()
            return {"withdrawn": True, "already": True,
                    "display_id": display_id,
                    "withdrawn_at": already.isoformat(),
                    "reason": prev_reason, "withdrawn_by": prev_by}

        cur.execute(
            """UPDATE runs
                  SET withdrawn_at = now(), withdrawn_reason = %s,
                      withdrawn_by = %s, is_active = FALSE,
                      status = 'WITHDRAWN'
                WHERE id = %s
            RETURNING withdrawn_at""", (reason, actor, run_id))
        withdrawn_at = cur.fetchone()[0]

        # Whether the ENTITY is still listed is the question the caller
        # actually has, and it is not answerable from the run row. Read it
        # from the same view the directory reads, inside this transaction,
        # so the answer is the one the next request will get.
        cur.execute(
            """SELECT count(*) FROM runs
                WHERE entity_id = %s AND promoted_at IS NOT NULL
                  AND withdrawn_at IS NULL""", (entity_id,))
        remaining = cur.fetchone()[0]
        conn.commit()

        # After commit, like promote: the matview sees the withdrawal. A
        # refresh failure never un-withdraws — it is reported, and until the
        # refresh lands the run is STILL SERVING, which is the one thing a
        # caller must not have to guess about.
        refresh_error = None
        try:
            cur.execute("SELECT refresh_serving_directory()")
            conn.commit()
        except Exception as e:                # noqa: BLE001 — reported, never silent
            conn.rollback()
            refresh_error = str(e)[:200]

        out = {"withdrawn": True, "already": False,
               "run_id": str(run_id), "display_id": display_id,
               "withdrawn_at": withdrawn_at.isoformat(),
               "reason": reason, "withdrawn_by": actor,
               "entity_still_listed": remaining > 0,
               "remaining_promoted_runs": remaining,
               "returns_by": "promote_run, which clears withdrawn_at; there "
                             "is no restore tool"}
        if refresh_error:
            out["directory_refresh_error"] = refresh_error
            out["still_serving"] = True
        return out
    except Exception:
        conn.rollback()
        raise


def list_withdrawn(conn) -> dict:
    """Every currently withdrawn run, with its reason. A run withheld from
    clients for a reason nobody can find is a run that comes back for a
    reason nobody can find either."""
    cur = conn.cursor()
    cur.execute(
        """SELECT r.id, e.display_id, e.legal_name, r.request_id,
                  r.withdrawn_at, r.withdrawn_by, r.withdrawn_reason
             FROM runs r JOIN entities e ON e.id = r.entity_id
            WHERE r.withdrawn_at IS NOT NULL
            ORDER BY r.withdrawn_at DESC""")
    return {"withdrawn": [
        {"run_id": str(a), "display_id": b, "legal_name": c, "request_id": d,
         "withdrawn_at": e.isoformat() if e else None,
         "withdrawn_by": f, "reason": g}
        for a, b, c, d, e, f, g in cur.fetchall()]}
