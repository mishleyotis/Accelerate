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
    cur.execute(
        """SELECT ic.run_id, e.id
             FROM insight_cards ic
             JOIN entities e ON e.id = ic.entity_id
             JOIN runs r ON r.id = ic.run_id
            WHERE e.display_id = %s AND ic.ic_id = %s
              AND r.promoted_at IS NOT NULL
            ORDER BY r.promoted_at DESC
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
