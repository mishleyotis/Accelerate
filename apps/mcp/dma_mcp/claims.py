"""Claim leases and run progress (stage 2.5 lease / 2.6 progress).

One session per run: the claim is an exclusive lease with an expiry so a
dead session cannot block a run permanently. Staged work survives a
lapsed lease — re-claim and continue (the skill's step 2).
"""
from __future__ import annotations

from datetime import timedelta

DEFAULT_TTL_MINUTES = 90

PAGES = ("heatmap", "overview", "insights", "platform", "context", "techstack")


def claim_run(conn, run_id: str, held_by: str, producer_version: str,
              ttl_minutes: int = DEFAULT_TTL_MINUTES) -> dict:
    """Take (or renew) the exclusive lease. Refused while another live
    session holds it; a lapsed lease is taken over silently — the staged
    rows are the state, the lease is only mutual exclusion."""
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO run_claims (run_id, held_by, claimed_at, expires_at,
                                   producer_version)
           VALUES (%s, %s, now(), now() + %s, %s)
           ON CONFLICT (run_id) DO UPDATE
             SET held_by = EXCLUDED.held_by,
                 claimed_at = EXCLUDED.claimed_at,
                 expires_at = EXCLUDED.expires_at,
                 producer_version = EXCLUDED.producer_version
             WHERE run_claims.held_by = EXCLUDED.held_by   -- renewal
                OR run_claims.expires_at < now()           -- lapsed
           RETURNING held_by, expires_at""",
        (run_id, held_by, timedelta(minutes=ttl_minutes), producer_version))
    row = cur.fetchone()
    if row:
        conn.commit()
        return {"claimed": True, "held_by": row[0],
                "expires_at": row[1].isoformat()}
    conn.rollback()
    cur.execute("SELECT held_by, expires_at FROM run_claims WHERE run_id = %s",
                (run_id,))
    holder = cur.fetchone()
    return {"claimed": False, "held_by": holder[0],
            "expires_at": holder[1].isoformat(),
            "hint": "another session holds this run; check get_run_progress "
                    "rather than working in parallel"}


def release_claim(conn, run_id: str, held_by: str) -> dict:
    cur = conn.cursor()
    cur.execute("DELETE FROM run_claims WHERE run_id = %s AND held_by = %s",
                (run_id, held_by))
    conn.commit()
    return {"released": cur.rowcount == 1}


def get_run_progress(conn, run_id: str) -> dict:
    """Per-page status and what is blocking (Implementation Plan 2.6).
    A resuming session sees where it left off without inferring it from
    verdicts; pages already passing must not be re-synthesised."""
    cur = conn.cursor()
    cur.execute(
        """SELECT s.page, s.status, s.id, s.submitted_at, s.promoted_at,
                  v.reasons
             FROM submissions s
             LEFT JOIN LATERAL (SELECT reasons FROM submission_verdicts
                                 WHERE submission_id = s.id
                                 ORDER BY id DESC LIMIT 1) v ON TRUE
            WHERE s.run_id = %s AND s.superseded_at IS NULL""", (run_id,))
    live = {r[0]: r for r in cur.fetchall()}
    pages = {}
    blocking = []
    for page in PAGES:
        if page not in live:
            pages[page] = {"status": "missing"}
            blocking.append({"page": page, "why": "no live submission"})
            continue
        _, status, sid, submitted_at, promoted_at, reasons = live[page]
        pages[page] = {
            "status": status,
            "submission_id": str(sid),
            "submitted_at": submitted_at.isoformat() if submitted_at else None,
            "promoted_at": promoted_at.isoformat() if promoted_at else None,
        }
        if status != "PASS":   # submission_status_t: PASS | FAIL
            blocking.append({"page": page, "why": f"latest verdict: {status}",
                             "reasons": reasons or []})
    cur.execute("""SELECT held_by, expires_at, expires_at > now()
                     FROM run_claims WHERE run_id = %s""", (run_id,))
    claim = cur.fetchone()
    return {
        "run_id": str(run_id),
        "pages": pages,
        "blocking": blocking,
        "promotable": not blocking,
        "claim": (None if not claim else
                  {"held_by": claim[0], "expires_at": claim[1].isoformat(),
                   "live": bool(claim[2])}),
    }
