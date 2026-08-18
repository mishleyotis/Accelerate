"""The global alert queue and its one write path (invariant 2).

Two routes live here, wired in main.py:

  GET  /v1/alerts                     G4 — the corpus-wide thin-evidence
                                      queue, cursor-paginated (TRD §19)
  POST /v1/alerts/{alert_id}/actions  the second of the API's two write
                                      exceptions (TRD §08): alert
                                      lifecycle — workflow state, not
                                      assessment content

The write boundary, stated once and testable: this module INSERTs into
`alert_actions` and `idempotency_keys` — the two workflow tables svc_api
holds INSERT on (0007) — and nothing else. `heatmap_alerts` is a serving
table; svc_api holds SELECT only, so the alert's own `status` column is
never updated here. The queue's effective status is DERIVED at read from
the base status plus the latest action, which is how "last write wins on
status; both actions are retained in history" (TRD §12) holds without a
serving-table write: the action history is the record, the CASE below is
the interpretation.

Idempotency per TRD §19 verbatim: the key is stored with the response; a
replay with the same key and the same body returns the ORIGINAL response,
not a second action; the same key with a DIFFERENT body is a 409 — a
client bug, not a retry. The rare race of two first-attempts on one key
loses on the `idempotency_keys` primary key and rolls back whole; the
client's retry then finds the stored row and replays.

Actor identity arrives the same way `role` already does in main.py — a
request parameter standing in for the stage-4 session claim (TRD §12:
role is "a claim in the token, re-verified at the API"; the walking
skeleton has no token yet, and inventing a parallel header here would be
a second mechanism to unwind).
"""
from __future__ import annotations

import base64
import hashlib
import json
import uuid

from .pages import AUDIENCES, ApiError

# alert_action_t, verbatim (Backend Schema §11 / 0002). `assigned` carries
# no assignee column in the DDL — the actor and rationale are the record.
ACTIONS = ("acknowledged", "assigned", "waived", "resolved", "reopened")

# heatmap_alerts.status vocabulary (0008: "open · resolved · waived — the
# queue lifecycle alert_actions acts on"), lowercase per 0015. "all" skips
# the filter so the waived-alert register (G4) is reachable.
STATUSES = ("open", "resolved", "waived", "all")

# The only fields the write contract accepts. run_id is read from the
# alert row, occurred_at is now(), the id is allocated by the database —
# the server allocates identifiers (invariant 10).
_BODY_FIELDS = frozenset(("action", "rationale"))

DEFAULT_LIMIT = 50   # TRD §19: limit is mandatory, default 50
MAX_LIMIT = 200      # hard maximum 200

# The only tables any statement in this module may write. The test suite
# asserts this set against the module source AND against captured SQL.
WRITABLE_TABLES = frozenset(("alert_actions", "idempotency_keys"))

# Last write wins on status: the latest action decides; acknowledged and
# assigned mark work without closing it, so the base status stands.
_EFFECTIVE_STATUS = """CASE WHEN la.action IN ('resolved', 'waived') THEN la.action::text
            WHEN la.action = 'reopened' THEN 'open'
            ELSE a.status END"""

_QUEUE_COLS = ("id", "subcap_id", "severity", "state", "score", "confidence",
               "evidence_count", "runs_open", "justification",
               "closure_condition", "created_at", "run_id", "entity_id",
               "display_id", "legal_name", "sub_vertical", "request_id",
               "status", "last_action", "last_rationale", "last_user_id",
               "last_occurred_at", "action_count")

# One query for the rows and their action state. The action state is
# JOINed at read from the workflow table (TRD §08: "annotations and alert
# actions live in their own workflow tables and are joined at read time");
# action_count is computed over that table, never stored (invariant 8).
# Entity display fields come from serving_directory — the ONE view svc_api
# is granted for run resolution (0013); the join to the active run keeps
# this queue reconciled with the directory's own open_alerts count.
_QUEUE_SQL = f"""
SELECT a.id, a.subcap_id, a.severity, a.state, a.score, a.confidence,
       a.evidence_count, a.runs_open, a.justification, a.closure_condition,
       a.created_at, a.run_id, a.entity_id,
       d.display_id, d.legal_name, d.sub_vertical, d.request_id,
       {_EFFECTIVE_STATUS} AS status,
       la.action, la.rationale, la.user_id, la.occurred_at,
       (SELECT count(*) FROM alert_actions c WHERE c.alert_id = a.id)
           AS action_count
  FROM heatmap_alerts a
  JOIN serving_directory d ON d.run_id = a.run_id AND d.is_active
  LEFT JOIN LATERAL (
        SELECT x.action, x.rationale, x.user_id, x.occurred_at
          FROM alert_actions x
         WHERE x.alert_id = a.id
         ORDER BY x.occurred_at DESC, x.id DESC
         LIMIT 1) la ON TRUE
 WHERE {{where}}
 ORDER BY a.created_at DESC, a.id DESC
 LIMIT %s"""


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


def refuse(audience: str, role: str | None) -> None:
    """Alerts are D7/internal tier: heatmap.alerts is CUSTOMER_WITHHELD in
    the redaction map, so the corpus queue built from the same rows is
    refused to the customer audience whole — a locked state, not a partial
    page. An AE token is refused on Health by the API (Implementation Plan
    4.1), and this queue is the corpus-wide view of Health's alerts tab, so
    serving it to an AE would sidestep that refusal."""
    if audience not in AUDIENCES:
        raise ApiError(400, "unknown_audience",
                       f"audience must be one of {' · '.join(AUDIENCES)}")
    if audience == "customer":
        raise ApiError(403, "audience_forbidden",
                       "the alert queue is an internal operational surface "
                       "and is not served to the customer audience")
    if role and role.upper() == "AE":
        raise ApiError(403, "role_forbidden",
                       "role AE has no route to the alert queue — it is the "
                       "corpus-wide view of the Health surfaces an AE token "
                       "is refused on")


def _fingerprint(filters: dict) -> str:
    """A cursor from a different filter set is rejected (TRD §19):
    reinterpreting it silently produces a page belonging to neither query.
    The filter set rides inside the cursor as a fingerprint."""
    canon = json.dumps(filters, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()[:12]


def encode_cursor(created_at, row_id, fingerprint: str) -> str:
    """Base64 of the sort key — opaque to the client but deterministic,
    round-tripping the tiebreak so ties cannot repeat (TRD §19)."""
    payload = {"c": _iso(created_at), "i": row_id, "f": fingerprint}
    return base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()).decode()


def decode_cursor(cursor: str, fingerprint: str) -> dict:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        created_at, row_id, fp = payload["c"], payload["i"], payload["f"]
    except Exception:
        raise ApiError(400, "malformed_cursor",
                       "the cursor could not be decoded; request the first "
                       "page again without one")
    if fp != fingerprint:
        raise ApiError(400, "cursor_filter_mismatch",
                       "the cursor belongs to a different filter set; "
                       "request the first page of THIS filter set")
    return {"c": created_at, "i": row_id}


def queue(cur, *, audience: str = "internal", role: str | None = None,
          status: str = "open", severity: str | None = None,
          entity: str | None = None, limit: int = DEFAULT_LIMIT,
          cursor: str | None = None) -> dict:
    """G4 — one row per alert across every active run, with its action
    state joined at read. Keyset pagination in the row-comparison form
    `(a, b) < (x, y)` — the form that uses the composite index; the
    disjunction does not (TRD §19)."""
    refuse(audience, role)
    if status not in STATUSES:
        raise ApiError(400, "unknown_status",
                       f"status must be one of {' · '.join(STATUSES)}")
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        raise ApiError(400, "malformed_limit", "limit must be an integer")
    limit = max(1, min(limit, MAX_LIMIT))

    filters = {"status": status, "severity": severity, "entity": entity}
    fp = _fingerprint(filters)

    where, params = ["TRUE"], []
    if status != "all":
        where.append(f"({_EFFECTIVE_STATUS}) = %s")
        params.append(status)
    if severity:
        where.append("a.severity = %s")
        params.append(severity)
    if entity:
        where.append("d.display_id = %s")
        params.append(entity)
    if cursor:
        c = decode_cursor(cursor, fp)
        where.append("(a.created_at, a.id) < (%s, %s)")
        params += [c["c"], c["i"]]
    params.append(limit + 1)  # +1 detects has_more

    cur.execute(_QUEUE_SQL.format(where=" AND ".join(where)), params)
    fetched = cur.fetchall()
    page = fetched[:limit]

    alerts = []
    for r in page:
        d = dict(zip(_QUEUE_COLS, r))
        row = {
            "id": d["id"],
            "entity": {"display_id": d["display_id"],
                       "entity_name": d["legal_name"],
                       "sub_vertical": d["sub_vertical"]},
            "run": {"run_id": str(d["run_id"]) if d["run_id"] else None,
                    "request_id": d["request_id"]},
            "subcap_id": d["subcap_id"],
            "severity": d["severity"],
            "state": d["state"],
            "status": d["status"],
            "score": float(d["score"]) if d["score"] is not None else None,
            "confidence": d["confidence"],
            "evidence_count": d["evidence_count"],
            "runs_open": d["runs_open"],
            "justification": d["justification"],
            "closure_condition": d["closure_condition"],
            "created_at": _iso(d["created_at"]),
            "action_count": d["action_count"] or 0,
            "action_state": None,
        }
        if d["last_action"] is not None:
            row["action_state"] = {
                "action": d["last_action"],
                "rationale": d["last_rationale"],
                "user_id": str(d["last_user_id"]) if d["last_user_id"] else None,
                "occurred_at": _iso(d["last_occurred_at"]),
            }
        alerts.append(row)

    has_more = len(fetched) > limit
    next_cursor = None
    if has_more and page:
        last = dict(zip(_QUEUE_COLS, page[-1]))
        next_cursor = encode_cursor(last["created_at"], last["id"], fp)

    return {"audience": audience, "filters": filters, "alerts": alerts,
            "count": len(alerts), "has_more": has_more,
            "next_cursor": next_cursor}


def _uuid_param(value, name: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        raise ApiError(400, f"malformed_{name}", f"{name} must be a UUID")


def _validate_body(body) -> tuple[str, str | None]:
    if not isinstance(body, dict):
        raise ApiError(400, "malformed_body",
                       "the request body must be a JSON object")
    unknown = sorted(set(body) - _BODY_FIELDS)
    if unknown:
        raise ApiError(400, "unknown_field",
                       "the action contract accepts `action` and `rationale` "
                       "only — run_id is recorded from the alert row and the "
                       "server allocates identifiers; got: "
                       + ", ".join(unknown))
    action = body.get("action")
    if action not in ACTIONS:
        raise ApiError(400, "unknown_action",
                       f"action must be one of {' · '.join(ACTIONS)}")
    rationale = body.get("rationale")
    if rationale is not None and not isinstance(rationale, str):
        raise ApiError(400, "malformed_rationale", "rationale must be a string")
    if action == "waived" and not (rationale and rationale.strip()):
        # Backend Schema §11: REQUIRED on waive. A waiver without a reason
        # is indistinguishable from neglect.
        raise ApiError(400, "rationale_required",
                       "a waiver without a reason is indistinguishable from "
                       "neglect — rationale is required on waive")
    return action, rationale


def act(cur, alert_id: int, *, body, idempotency_key: str | None,
        actor: str | None, audience: str = "internal",
        role: str | None = None) -> tuple[int, dict]:
    """POST /v1/alerts/{alert_id}/actions — returns (status_code, response).

    Runs inside the caller's transaction; the caller commits. Both INSERTs
    are workflow tables — nothing here touches a serving table, and svc_api
    has no grant that would let it (invariant 2).
    """
    refuse(audience, role)
    if not idempotency_key:
        raise ApiError(400, "idempotency_key_required",
                       "this write path tolerates retries only through the "
                       "Idempotency-Key header (TRD §19); send one")
    key = _uuid_param(idempotency_key, "idempotency_key")
    if not actor:
        raise ApiError(400, "actor_required",
                       "an alert action must be attributable; pass the "
                       "acting user's id (the stage-4 session claim)")
    actor = _uuid_param(actor, "actor")
    action, rationale = _validate_body(body)

    # The hash covers the route context as well as the body: the same key
    # replayed against a different alert or by a different actor is not a
    # retry of the same request.
    request_hash = hashlib.sha256(json.dumps(
        {"alert_id": alert_id, "actor": actor, "body": body},
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    cur.execute("SELECT request_hash, status_code, response "
                "FROM idempotency_keys WHERE key = %s", (key,))
    hit = cur.fetchall()
    if hit:
        stored_hash, stored_status, stored_response = hit[0]
        if stored_hash != request_hash:
            raise ApiError(409, "idempotency_key_reused",
                           "this Idempotency-Key was already used with a "
                           "different request — that is a client bug, not a "
                           "retry; mint a new key")
        if isinstance(stored_response, (str, bytes)):
            stored_response = json.loads(stored_response)
        return int(stored_status), stored_response  # replayed, not re-applied

    cur.execute("SELECT id, run_id, status FROM heatmap_alerts WHERE id = %s",
                (alert_id,))
    found = cur.fetchall()
    if not found:
        raise ApiError(404, "alert_not_found", f"no alert {alert_id}")
    _aid, run_id, base_status = found[0]

    # run_id comes from the alert row, never the client: the action stays
    # attached to the run the alert belongs to (Backend Schema §11).
    cur.execute(
        "INSERT INTO alert_actions "
        "(alert_id, user_id, action, rationale, run_id, occurred_at) "
        "VALUES (%s, %s, %s::alert_action_t, %s, %s, now()) "
        "RETURNING id, occurred_at",
        (alert_id, actor, action, rationale, run_id))
    action_id, occurred_at = cur.fetchall()[0]

    effective = {"resolved": "resolved", "waived": "waived",
                 "reopened": "open"}.get(action, base_status)
    response = {
        "action": {"id": action_id, "alert_id": alert_id, "action": action,
                   "rationale": rationale,
                   "run_id": str(run_id) if run_id else None,
                   "user_id": actor, "occurred_at": _iso(occurred_at)},
        "alert": {"id": alert_id, "status": effective},
    }

    # Stored WITH the response (TRD §19), same transaction as the action:
    # either both rows land or neither does.
    cur.execute(
        "INSERT INTO idempotency_keys "
        "(key, user_id, request_hash, status_code, response) "
        "VALUES (%s, %s, %s, %s, %s)",
        (key, actor, request_hash, 201, json.dumps(response)))
    return 201, response
