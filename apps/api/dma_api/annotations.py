"""The first of the API's two write exceptions: annotations (invariant 2).

TRD §08: "Annotations and alert actions live in their own workflow tables and
are joined at read time. The invariant holds: content reaches a serving table
only through a promotion." This module is the annotation half; alerts.py is
the other. The shape mirrors alerts.act deliberately — one Idempotency-Key
discipline, one transaction posture, one refusal style — so a reader who has
audited one has audited both.

What an insight-card verdict IS here: an annotation with anchor_kind
`insight_card`, its body recording the action (ACCEPT | REJECT) and any note.
The DDL (0007) already enumerates the anchor kinds; nothing new was invented:

    annotations (id, user_id, entity_id, run_id, anchor_kind, anchor_id,
                 body, created_at)

Fail-closed anchoring: the anchor must RESOLVE — the ic_id must exist on the
entity's active run's insight_cards — or the write is refused. An annotation
on a card that does not exist is a dangling opinion; worse, a typo'd id would
silently attach a verdict to nothing.

The actor arrives as the SESSION's email (the BFF forwards the signed-in
user, never a client-supplied identity) and resolves against users.email —
which is CITEXT UNIQUE, the auth table's own join discipline. An email that
resolves to no active user is refused, not auto-created: user rows are the
auth flow's to make.

## The 403 was right, and the fix was upstream of here

Measured in production on 2026-08-08 against the live revision:

    POST /v1/entities/baxter-credit-union-bcu/insights/IC-1/annotation
         ?audience=internal&role=ADMIN&actor=dma%40zennify.com
    -> 403 {"error":"unknown_actor"}      SELECT count(*) FROM users -> 0

The refusal above is the correct behaviour for an unknown actor and it has NOT
been weakened. What changed is that the actor became known: migration 0033
materialises the deploy-time allowlist (`ADMIN_EMAILS` / `ANALYST_EMAILS`,
which `apps/web/lib/identity.js` already describes as a placeholder for "the
users table") as durable `users` rows. An email that is not on that allowlist
still resolves to no user and still takes the 403. Enrolment is not a write
path: creating the identity inside the write that is checked against it would
be the check deleted.

## What the 403 had been hiding

The moment the actor resolved, the next statement raised

    42501: permission denied for table entities

`svc_api` has never held a grant on `entities` or `runs`, so the anchor query
could not have succeeded on any request in the life of this endpoint — the
earlier refusal was standing in front of a statement that had never run. Both
the anchor and the reads below now resolve display_id through
`serving_directory`, which alerts.py already calls "the ONE view svc_api"
reads for entity display fields: it holds promoted runs only, promote
refreshes it inside the promote transaction, and default-deny survives
because svc_api gains nothing it did not already read.

## The read half

`annotations` had a reader nowhere in this repository — no endpoint, no MCP
tool, no worker job — while every insight card rendered an Accept/Reject pair
and the web adapter hardcoded `annotation: null`. `read_insight_annotations`
and `latest_verdicts` below are that reader.

Reading does not touch invariant 2. That invariant constrains the API's
WRITES — "content enters only through the connector" — and a SELECT adds no
content, creates no serving row and gives no endpoint a write it did not have.
The API's two write exceptions are unchanged: annotations and alert actions,
both behind `Idempotency-Key`. `svc_api` has held SELECT on `annotations`
since 0007 (line 265, in the `workflow` loop); the grant was never the blocker.

WIRING OWED (one line, in a file this module's author does not own):

    @app.get("/v1/entities/{display_id}/insights/annotations")
    def insight_annotations(display_id: str, ic_id: str | None = None,
                            audience: str = "internal", role: str | None = None,
                            limit: int = 100):
        conn = _connect(); cur = conn.cursor()
        try:
            return read_insight_annotations(cur, display_id, ic_id=ic_id,
                                            audience=audience, role=role,
                                            limit=limit)
        finally:
            conn.close()

Until that lands, the connector's `list_reviewer_feedback` tool is the working
read path and the consumer (`ingest_reviewer_feedback`) reads the table
directly. Both are proven against production.

`users.last_seen_at` is deliberately NOT touched on a successful write. It was
added and removed: `test_alerts.py` pins this path to exactly two written
tables, and another author's write-boundary test is worth more than a
convenience column. Binding `google_sub` and `last_seen_at` belongs to the
sign-in flow, which is where it was always owed.

## The actor: recorded here as unfixed, and now closed (MEM-0016)

This module used to end by recording that `main.py` accepted `actor` as a
QUERY PARAMETER — the BFF was the only intended caller and forwarded the
verified session email, but nothing in the API enforced it, so a principal
holding `roles/run.invoker` on `dmai-api` could name any allowlisted actor.

That is closed. `actor_email` now arrives from `dma_api.identity`, which
verifies the request's IAP assertion independently of the web tier — ES256
against Google's published key set, issuer and audience pinned — and refuses
the write outright when there is no assertion. The parameter is compared to
the verified identity and never believed; naming somebody else is a 403.

Nothing in THIS module changed for it, which is the point: attribution is a
property of the route that receives the request, and `actor_email` was always
the right shape for this function to take.
"""
from __future__ import annotations

import json

from .pages import ApiError

ACTIONS = ("ACCEPT", "REJECT")


def _refuse(audience: str, role: str | None) -> None:
    if audience != "internal":
        raise ApiError(403, "audience_forbidden",
                       "annotations are internal workflow; the customer "
                       "audience has no write route")
    # Any internal role may annotate — an AE's accept/reject on an insight
    # card is precisely the feedback loop the surface exists for.


def annotate_insight(cur, display_id: str, ic_id: str, *, body,
                     idempotency_key: str | None, actor_email: str | None,
                     audience: str = "internal",
                     role: str | None = None) -> tuple[int, dict]:
    """POST /v1/entities/{display_id}/insights/{ic_id}/annotation.

    Runs inside the caller's transaction; the caller commits. Two INSERTs
    (annotations + idempotency_keys), both workflow tables — no serving
    table is touched, and svc_api holds no grant that would allow it.
    """
    _refuse(audience, role)
    if not idempotency_key:
        raise ApiError(400, "idempotency_key_required",
                       "this write path tolerates retries only through the "
                       "Idempotency-Key header (TRD §19); send one")
    if not actor_email:
        raise ApiError(400, "actor_required",
                       "an annotation must be attributable; the BFF forwards "
                       "the session's email")
    if not isinstance(body, dict):
        raise ApiError(400, "malformed_body", "the body must be a JSON object")
    action = str(body.get("action") or "").upper()
    if action not in ACTIONS:
        raise ApiError(400, "unknown_action",
                       f"action must be one of {'|'.join(ACTIONS)}")
    note = body.get("note")
    if note is not None and not isinstance(note, str):
        raise ApiError(400, "malformed_note", "note must be a string")

    # ── Idempotency: replay returns the ORIGINAL response; a reused key
    #    with a different request is a client bug (TRD §19) ─────────────
    import uuid as _uuid
    try:
        _uuid.UUID(str(idempotency_key))
    except ValueError:
        raise ApiError(400, "malformed_idempotency_key",
                       "Idempotency-Key must be a UUID")
    cur.execute("SELECT request_hash, response FROM idempotency_keys "
                "WHERE key = %s", (idempotency_key,))
    row = cur.fetchone()
    req_hash = json.dumps({"display_id": display_id, "ic_id": ic_id,
                           "action": action, "note": note,
                           "actor": actor_email}, sort_keys=True)
    if row is not None:
        stored_hash, stored_response = row
        if stored_hash != req_hash:
            raise ApiError(409, "idempotency_key_reused",
                           "this key was used for a DIFFERENT request — that "
                           "is a client bug, not a retry")
        out = stored_response if isinstance(stored_response, dict) \
            else json.loads(stored_response)
        out["replayed"] = True
        return 200, out

    # ── The actor must be a real, active user ──────────────────────────
    cur.execute("SELECT id FROM users WHERE email = %s AND is_active",
                (actor_email,))
    u = cur.fetchone()
    if u is None:
        raise ApiError(403, "unknown_actor",
                       "the session's email resolves to no active user; "
                       "user rows are the auth flow's to create")
    user_id = u[0]

    # ── Fail-closed anchor: the card must exist on the entity's active
    #    run. A verdict attached to nothing is refused, not stored. ─────
    #
    #    Resolved through `serving_directory`, not through `entities` and
    #    `runs`. Measured 2026-08-08, the moment the 403 above stopped firing:
    #    the next statement raised 42501 `permission denied for table entities`
    #    — svc_api has never held a grant on `entities` or `runs`, so this
    #    anchor query could not have succeeded on any request, ever. The
    #    earlier refusal had been hiding it.
    #
    #    The fix is the codebase's own idiom rather than a new grant:
    #    `serving_directory` is "the ONE view svc_api" reads for entity display
    #    fields (alerts.py), it carries display_id beside run_id, it holds
    #    PROMOTED runs only — so `promoted_at IS NOT NULL` is the view's own
    #    definition and not a filter this query has to remember — and promote
    #    refreshes it inside the promote transaction (promote.py:172), so it
    #    cannot be stale relative to a card that exists. Default-deny survives:
    #    svc_api gains nothing it did not already read.
    cur.execute(
        """SELECT ic.run_id, ic.entity_id
             FROM insight_cards ic
             JOIN serving_directory d ON d.run_id = ic.run_id
            WHERE d.display_id = %s AND ic.ic_id = %s
            ORDER BY d.promoted_at DESC
            LIMIT 1""", (display_id, ic_id))
    anchor = cur.fetchone()
    if anchor is None:
        raise ApiError(404, "anchor_not_found",
                       f"insight card {ic_id!r} does not exist on a promoted "
                       f"run of {display_id!r} — an annotation on nothing is "
                       "a dangling opinion and is refused")
    run_id, entity_id = anchor

    cur.execute(
        """INSERT INTO annotations
             (user_id, entity_id, run_id, anchor_kind, anchor_id, body,
              created_at)
           VALUES (%s, %s, %s, 'insight_card', %s, %s, now())
           RETURNING id, created_at""",
        (user_id, entity_id, run_id, ic_id,
         json.dumps({"action": action, "note": note})))
    ann_id, created_at = cur.fetchone()

    response = {"annotation_id": ann_id, "ic_id": ic_id, "action": action,
                "created_at": str(created_at), "replayed": False}
    cur.execute(
        """INSERT INTO idempotency_keys (key, user_id, request_hash,
                                         status_code, response, created_at)
           VALUES (%s, %s, %s, 201, %s, now())""",
        (idempotency_key, user_id, req_hash, json.dumps(response)))
    return 201, response


# ── the read half ───────────────────────────────────────────────────────
def _refuse_read(audience: str) -> None:
    """Annotations are internal workflow. A customer audience has no read
    route for them any more than it has a write route — an analyst's private
    verdict on a claim is not part of the client's report."""
    if audience != "internal":
        raise ApiError(403, "audience_forbidden",
                       "annotations are internal workflow; the customer "
                       "audience has no read route")


def _parse_body(raw):
    """The body is TEXT holding the JSON this module wrote. A body that will
    not parse is surfaced as `unparsed`, never silently rendered as an empty
    verdict — "I could not read this" and "there was nothing here" are
    different facts (invariant 9)."""
    if isinstance(raw, dict):
        return raw
    try:
        out = json.loads(raw or "")
        return out if isinstance(out, dict) else {"unparsed": str(raw)[:400]}
    except (TypeError, ValueError):
        return {"unparsed": str(raw)[:400]}


def read_insight_annotations(cur, display_id: str, *, ic_id: str | None = None,
                             audience: str = "internal",
                             role: str | None = None,
                             limit: int = 100) -> dict:
    """Every insight-card verdict on an entity, newest first, with the actor.

    Runs on the index 0033 added — (entity_id, anchor_kind, anchor_id,
    created_at DESC) — so this is a lookup, not the sequential scan the table
    offered before it had any index but its primary key.
    """
    _refuse_read(audience)
    limit = max(1, min(int(limit or 100), 500))
    # display_id -> entity through `serving_directory`, the one view svc_api
    # reads for entity display fields. `entities` is not readable by this role
    # and does not need to be (see the anchor query above).
    params = [display_id]
    where = ("a.entity_id = (SELECT entity_id FROM serving_directory "
             "WHERE display_id = %s LIMIT 1) "
             "AND a.anchor_kind = 'insight_card'")
    if ic_id:
        where += " AND a.anchor_id = %s"
        params.append(ic_id)
    cur.execute(
        f"""SELECT a.id, a.anchor_id, a.body, a.created_at, u.email,
                   u.display_name, u.role::text, a.run_id
              FROM annotations a
              LEFT JOIN users u ON u.id = a.user_id
             WHERE {where}
             ORDER BY a.created_at DESC, a.id DESC
             LIMIT %s""", (*params, limit))
    rows = []
    for aid, anchor, body, created, email, name, urole, run_id in cur.fetchall():
        parsed = _parse_body(body)
        rows.append({
            "annotation_id": aid, "ic_id": anchor,
            "action": parsed.get("action"), "note": parsed.get("note"),
            "unparsed": parsed.get("unparsed"),
            "by": {"email": email, "name": name, "role": urole},
            "run_id": str(run_id) if run_id else None,
            "created_at": created.isoformat() if created else None,
        })
    return {"display_id": display_id, "ic_id": ic_id, "count": len(rows),
            "annotations": rows}


def latest_verdicts(cur, display_id: str, ic_ids=None, *,
                    audience: str = "internal") -> dict:
    """The shape the card adapter needs: {ic_id: {action, note, by, at}} — the
    LATEST verdict per card, so `annotation: null` can stop being a constant.

    The latest verdict per card, not a list: the card renders one state. The
    full history is `read_insight_annotations`, and it is the history that
    teaches — which is why the connector consumes every row rather than this
    projection.
    """
    _refuse_read(audience)
    params = [display_id]
    filt = ""
    if ic_ids:
        filt = " AND a.anchor_id = ANY(%s)"
        params.append(list(ic_ids))
    cur.execute(
        f"""SELECT DISTINCT ON (a.anchor_id)
                   a.anchor_id, a.body, a.created_at, u.email, u.display_name
              FROM annotations a
              LEFT JOIN users u ON u.id = a.user_id
             WHERE a.entity_id = (SELECT entity_id FROM serving_directory
                                   WHERE display_id = %s LIMIT 1)
               AND a.anchor_kind = 'insight_card'{filt}
             ORDER BY a.anchor_id, a.created_at DESC, a.id DESC""",
        tuple(params))
    out = {}
    for anchor, body, created, email, name in cur.fetchall():
        parsed = _parse_body(body)
        out[anchor] = {"action": parsed.get("action"),
                       "note": parsed.get("note"),
                       "by": name or email,
                       "at": created.isoformat() if created else None}
    return out
