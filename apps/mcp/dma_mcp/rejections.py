"""The rejection ledger — a refused payload gets a name, a queue and a way back.

A submission that fails validation supersedes the passing row for its page and
then sits there. `get_run_progress` will show it, but only for one run and
only if somebody asks; nothing lists refusals across the corpus, so a producer
session that ends leaves no trace that anything is outstanding. Measured on
this build three times in one day — a heatmap that dropped `cell_evidence` and
failed CG-01, an overview refused twice on ET-07 and ET-09 — and every one was
found by a human reading a verdict.

The identifier is the point. A rejection is keyed on (run, page, gate, path),
so the row a refined copy clears is the row it was opened against, and "did
the repair land" is answerable without diffing payloads. Rows close by
EVIDENCE: a later submission for the same page closes every open rejection
whose gate no longer fires, and a gate that still fires keeps its row and
increments `attempts` — which is how "this is the fourth attempt at the same
reason" becomes visible instead of being rediscovered each session.
"""
from __future__ import annotations

# A refusal is a reason to repair the page. SG is the charter's disclosed
# exception (invariant 12): it renders to the client and does not block, so it
# is not an outstanding repair and never opens a ticket.
def _blocking(reasons) -> list:
    out = []
    for r in reasons or []:
        if not isinstance(r, dict):
            continue
        if str(r.get("severity", "block")).lower() != "block":
            continue
        if str(r.get("gate_id", "")).startswith("SG"):
            continue
        out.append(r)
    return out


def _key(r: dict) -> tuple:
    return (str(r.get("gate_id") or ""), str(r.get("path") or ""))


def record_verdict(conn, run_id, page: str, submission_id, reasons,
                   producer_version: str = "") -> dict:
    """Open, re-open, bump or close, from one verdict. Idempotent.

    Called on EVERY submit, pass or fail — a pass is what closes the tickets
    the last failure opened, and doing that anywhere else would leave a queue
    that only ever grows.
    """
    cur = conn.cursor()
    blocking = _blocking(reasons)
    seen = {_key(r) for r in blocking}

    opened, bumped = [], []
    for r in blocking:
        gate, path = _key(r)
        cur.execute(
            """INSERT INTO rejection_ledger
                 (run_id, page, section, gate_id, path, severity, message,
                  opened_by, producer_version)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (run_id, page, gate_id, path)
                 WHERE closed_at IS NULL
               DO UPDATE SET attempts = rejection_ledger.attempts + 1,
                             last_seen_at = now(),
                             message = EXCLUDED.message,
                             producer_version = COALESCE(EXCLUDED.producer_version,
                                                         rejection_ledger.producer_version)
               RETURNING rejection_id, attempts""",
            (run_id, page, r.get("section"), gate, path,
             str(r.get("severity") or "block"), str(r.get("message") or "")[:4000],
             submission_id, producer_version or None))
        rid, attempts = cur.fetchone()
        (bumped if attempts > 1 else opened).append(
            {"rejection_id": str(rid), "gate_id": gate, "path": path,
             "attempts": attempts})

    # CLOSE BY EVIDENCE. Every open ticket on this page whose gate did not
    # fire in this verdict is closed by this submission. A ticket that fires
    # again was bumped above and is excluded here by its own key.
    cur.execute("""SELECT rejection_id, gate_id, path FROM rejection_ledger
                    WHERE run_id = %s AND page = %s AND closed_at IS NULL""",
                (run_id, page))
    closed = []
    for rid, gate, path in list(cur.fetchall()):
        if (gate, path) in seen:
            continue
        cur.execute("""UPDATE rejection_ledger
                          SET closed_by = %s, closed_at = now()
                        WHERE rejection_id = %s""", (submission_id, rid))
        closed.append({"rejection_id": str(rid), "gate_id": gate, "path": path})

    return {"opened": opened, "reopened_or_bumped": bumped, "closed": closed,
            "open_after": len(opened) + len(bumped)}


def open_for_run(conn, run_id) -> list:
    cur = conn.cursor()
    cur.execute("""SELECT rejection_id, page, section, gate_id, path, message,
                          attempts, opened_at
                     FROM rejection_ledger
                    WHERE run_id = %s AND closed_at IS NULL
                    ORDER BY attempts DESC, opened_at""", (run_id,))
    cols = ("rejection_id", "page", "section", "gate_id", "path", "message",
            "attempts", "opened_at")
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def open_corpus_wide(conn, display_id: str = "", page: str = "",
                     limit: int = 200) -> list:
    """The read that did not exist: what is outstanding ACROSS runs.

    This is the queue a scheduled producer session reads to know there is work,
    without having to already know which run to ask about — which is the whole
    reason refusals went unnoticed.
    """
    cur = conn.cursor()
    sql = ["SELECT rejection_id, run_id, display_id, legal_name, page, section,",
           "       gate_id, path, message, attempts, opened_at, open_for",
           "  FROM open_rejections WHERE TRUE"]
    args = []
    if display_id:
        sql.append(" AND display_id = %s"); args.append(display_id)
    if page:
        sql.append(" AND page = %s"); args.append(page)
    sql.append(" LIMIT %s"); args.append(max(1, min(int(limit or 200), 1000)))
    cur.execute("\n".join(sql), tuple(args))
    cols = ("rejection_id", "run_id", "display_id", "legal_name", "page",
            "section", "gate_id", "path", "message", "attempts", "opened_at",
            "open_for")
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def summary(rows: list) -> dict:
    """What a caller needs to decide whether to act, in three numbers.

    `looping` is the one to read first: a ticket past two attempts means the
    repair is not landing, and the next attempt should change approach rather
    than repeat."""
    looping = [r for r in rows if (r.get("attempts") or 1) > 2]
    return {
        "open": len(rows),
        "looping": len(looping),
        "pages": sorted({r["page"] for r in rows}),
        "worst": rows[0] if rows else None,
        "done": not rows,
    }
