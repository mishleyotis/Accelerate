"""Users and roles — the roster Admin › Users & roles manages (TRD §19
`/api/v1/admin/users`, Backend Schema §03 `users` + `session_log`).

## The third write, and why it is allowed

Invariant 2 named two API writes: annotations and alert actions. User grants
are a third, adjudicated by the owner on 2026-10-07 ("users table" — the
schema's own home for roles, recorded in CLAUDE.md): a role, an active flag
and an invitation are WORKFLOW state about who may read, never assessment
content. Nothing here touches a serving table, and svc_api holds exactly the
grants this needs since 0003 (SELECT, INSERT, UPDATE on `users`; SELECT,
INSERT on `session_log`) and 0007 (INSERT on `idempotency_keys`).

Routes (wired in main.py):

  GET  /v1/me            the verified caller's grant (read-only)
  POST /v1/me            the same answer, after enrolling the caller: sign-in
                         and every document load call this, so everyone who
                         opens the app has a roster row with the role they
                         were allocated, and `last_seen_at` says when they
                         were last here (touched at most every 5 minutes)
  GET  /v1/admin/users   the roster · ADMIN
  POST /v1/admin/users   invite · change role · deactivate · reactivate ·
                         ADMIN, Idempotency-Key required

## Who may change what

The actor is the VERIFIED IAP assertion's email (dma_api.identity), never a
parameter. An actor is an admin when an active `users` row says ADMIN, or when
the email is on the deploy-time owner floor (`ADMIN_EMAILS`). The floor exists
so that nobody — not even an admin, not even by mistake — can remove the last
way in: a floor email cannot be demoted or deactivated here, and an admin
cannot demote or deactivate themself.

## The record

Every applied change writes one `session_log` row for the person it changed
(`event` = invited · role_changed · deactivated · reactivated, `role_at_event`
= the role after the change, so a later change does not rewrite history), and
one `idempotency_keys` row carrying the ACTOR's user id with the response.
The pair answers "who changed whose access, to what, when".
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid

from .pages import ApiError

ROLES = ("AE", "ANALYST", "ADMIN")
DOMAIN = "@zennify.com"

# The only tables any statement in this module may write. The test suite
# asserts this set against the module source.
WRITABLE_TABLES = frozenset(("users", "session_log", "idempotency_keys"))

_BODY_FIELDS = frozenset(("email", "role", "is_active"))
_COLS = ("email", "display_name", "role", "is_active", "created_at",
         "last_seen_at", "signed_in")


def owner_floor(env=None) -> list[str]:
    raw = (env if env is not None else os.environ).get("ADMIN_EMAILS", "")
    return [e.strip().lower() for e in raw.split(",") if e.strip()]


def display_name(email: str) -> str:
    local = email.split("@")[0]
    parts = [p for p in local.replace("_", ".").replace("-", ".").split(".") if p]
    if len(parts) == 1 and len(parts[0]) <= 3:
        return parts[0].upper()
    return " ".join(p[:1].upper() + p[1:] for p in parts) or email


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


def _row(r) -> dict:
    d = dict(zip(_COLS, r))
    d["email"] = str(d["email"]).lower()
    d["created_at"] = _iso(d["created_at"])
    d["last_seen_at"] = _iso(d["last_seen_at"])
    d["is_active"] = bool(d["is_active"]) if d["is_active"] is not None else True
    d["signed_in"] = bool(d["signed_in"])
    return d


_SELECT = ("SELECT email::text, display_name, role::text, is_active, created_at, "
           "last_seen_at, google_sub IS NOT NULL FROM users")


def me(cur, email: str, *, env=None) -> dict:
    """The verified caller's grant. A floor email is ADMIN whatever the row
    says; no row is the default @zennify.com reader, AE."""
    email = email.lower()
    cur.execute(_SELECT + " WHERE email = %s", (email,))
    rows = cur.fetchall()
    row = _row(rows[0]) if rows else None
    if email in owner_floor(env):
        return {"email": email, "role": "ADMIN", "is_active": True,
                "source": "owner_floor", "known": row is not None}
    if row is None:
        return {"email": email, "role": "AE", "is_active": True,
                "source": "default", "known": False}
    return {"email": email, "role": row["role"] or "AE",
            "is_active": row["is_active"], "source": "users", "known": True}


def analyst_grants(env=None) -> list[str]:
    raw = (env if env is not None else os.environ).get("ANALYST_EMAILS", "")
    return [e.strip().lower() for e in raw.split(",") if e.strip()]


def initial_role(email: str, env=None) -> str:
    """The role a first visit is allocated: the owner floor is ADMIN, the
    deploy-time analyst list is ANALYST, every other @zennify.com reader AE.
    Only a first visit — an existing row's role is the Admins' to change."""
    if email in owner_floor(env):
        return "ADMIN"
    if email in analyst_grants(env):
        return "ANALYST"
    return "AE"


TOUCH_MINUTES = 5
LOGIN_GAP_HOURS = 8   # the session cookie's life: a gap longer than it is a new sign-in


def enrol(cur, email: str, *, env=None) -> dict:
    """POST /v1/me — enrol the verified caller and answer their grant.

    Idempotent by construction: a row is inserted only when none exists for
    the email (the UNIQUE constraint backs this under a race), `last_seen_at`
    moves only when it is older than TOUCH_MINUTES, and a `login` row is
    written only for a first visit or a return after LOGIN_GAP_HOURS. A
    deactivated account writes one `denied` row per refused visit and is never
    reactivated by visiting."""
    email = email.lower()
    if not email.endswith(DOMAIN) or email.count("@") != 1:
        raise ApiError(403, "domain_forbidden", f"only {DOMAIN} addresses are enrolled")
    cur.execute("SELECT id, role::text, is_active, "
                f"last_seen_at IS NULL OR last_seen_at < now() - interval '{LOGIN_GAP_HOURS} hours', "
                f"last_seen_at IS NULL OR last_seen_at < now() - interval '{TOUCH_MINUTES} minutes' "
                "FROM users WHERE email = %s", (email,))
    rows = cur.fetchall()
    enrolled = False
    if not rows:
        role = initial_role(email, env)
        cur.execute("INSERT INTO users (email, display_name, role, is_active, last_seen_at) "
                    "VALUES (%s, %s, %s::user_role_t, true, now()) "
                    "ON CONFLICT (email) DO NOTHING RETURNING id",
                    (email, display_name(email), role))
        got = cur.fetchall()
        if got:
            cur.execute("INSERT INTO session_log (user_id, event, role_at_event) "
                        "VALUES (%s, %s, %s::user_role_t)", (got[0][0], "login", role))
            enrolled = True
    else:
        uid, role, active, gap, stale = rows[0]
        if active is False:
            cur.execute("INSERT INTO session_log (user_id, event, role_at_event) "
                        "VALUES (%s, %s, %s::user_role_t)", (uid, "denied", role or "AE"))
        elif stale:
            cur.execute("UPDATE users SET last_seen_at = now() WHERE id = %s", (uid,))
            if gap:
                cur.execute("INSERT INTO session_log (user_id, event, role_at_event) "
                            "VALUES (%s, %s, %s::user_role_t)", (uid, "login", role or "AE"))
    out = me(cur, email, env=env)
    out["enrolled"] = enrolled
    return out


def _admin_actor(cur, email: str, *, env=None) -> str:
    """The actor's users.id, or a refusal. Admin is an active ADMIN row or a
    floor email; either way a row must exist, because the change is recorded
    against it (0033 seeds the floor)."""
    cur.execute("SELECT id, role::text, is_active FROM users WHERE email = %s",
                (email,))
    rows = cur.fetchall()
    if not rows and email in owner_floor(env):
        # An owner who has never been enrolled still administers: enrol them
        # (as ADMIN) so the change has a row to be attributed to.
        enrol(cur, email, env=env)
        cur.execute("SELECT id, role::text, is_active FROM users WHERE email = %s",
                    (email,))
        rows = cur.fetchall()
    if not rows:
        raise ApiError(403, "unknown_actor",
                       "the verified signed-in email resolves to no user row; "
                       "the change cannot be attributed")
    uid, role, active = rows[0]
    if email in owner_floor(env) or (role == "ADMIN" and active is not False):
        return str(uid)
    raise ApiError(403, "admin_required", "managing users needs an ADMIN grant")


def list_users(cur, actor_email: str, *, env=None) -> dict:
    _admin_actor(cur, actor_email.lower(), env=env)
    cur.execute(_SELECT + " ORDER BY CASE role::text WHEN 'ADMIN' THEN 0 "
                "WHEN 'ANALYST' THEN 1 ELSE 2 END, email")
    return {"users": [_row(r) for r in cur.fetchall()],
            "owner_floor": owner_floor(env), "default_role": "AE"}


def _validate(body) -> tuple[str, str | None, bool | None]:
    if not isinstance(body, dict):
        raise ApiError(400, "malformed_body", "the body must be a JSON object")
    extra = set(body) - _BODY_FIELDS
    if extra:
        raise ApiError(400, "unknown_field",
                       f"not part of the contract: {', '.join(sorted(extra))}")
    email = str(body.get("email") or "").strip().lower()
    if not email.endswith(DOMAIN) or email.count("@") != 1 or len(email) > 254:
        raise ApiError(400, "invalid_email",
                       f"only {DOMAIN} addresses can be granted access")
    role = body.get("role")
    if role is not None:
        role = str(role).upper()
        if role not in ROLES:
            raise ApiError(400, "unknown_role", "role is one of " + " · ".join(ROLES))
    active = body.get("is_active")
    if active is not None and not isinstance(active, bool):
        raise ApiError(400, "invalid_is_active", "is_active is true or false")
    if role is None and active is None:
        raise ApiError(400, "nothing_to_change", "send a role, is_active, or both")
    return email, role, active


def set_user(cur, actor_email: str, *, body, idempotency_key: str | None,
             env=None) -> tuple[int, dict]:
    """POST /v1/admin/users — (status_code, response). Runs in the caller's
    transaction; the caller commits."""
    if not idempotency_key:
        raise ApiError(400, "idempotency_key_required",
                       "this write path tolerates retries only through the "
                       "Idempotency-Key header (TRD §19); send one")
    try:
        key = str(uuid.UUID(str(idempotency_key)))
    except ValueError:
        raise ApiError(400, "invalid_idempotency_key", "the key is a UUID")
    actor_email = actor_email.lower()
    actor_id = _admin_actor(cur, actor_email, env=env)
    email, role, active = _validate(body)
    floor = owner_floor(env)
    if email in floor and (role not in (None, "ADMIN") or active is False):
        raise ApiError(409, "owner_floor",
                       f"{email} is on the deploy-time owner list (ADMIN_EMAILS) "
                       "and stays an active Admin")
    if email == actor_email and (role not in (None, "ADMIN") or active is False):
        raise ApiError(409, "self_lockout",
                       "you cannot remove your own Admin access; ask another Admin")

    request_hash = hashlib.sha256(json.dumps(
        {"route": "admin/users", "actor": actor_id, "body": body},
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    cur.execute("SELECT request_hash, status_code, response "
                "FROM idempotency_keys WHERE key = %s", (key,))
    hit = cur.fetchall()
    if hit:
        stored_hash, stored_status, stored = hit[0]
        if stored_hash != request_hash:
            raise ApiError(409, "idempotency_key_reused",
                           "this Idempotency-Key was already used with a "
                           "different request; mint a new key")
        return int(stored_status), (json.loads(stored) if isinstance(stored, (str, bytes)) else stored)

    cur.execute("SELECT id, role::text, is_active FROM users WHERE email = %s", (email,))
    rows = cur.fetchall()
    if rows:
        uid, old_role, old_active = rows[0]
        old_active = old_active is not False
        new_role = role or old_role or "AE"
        new_active = old_active if active is None else active
        if not old_active and new_active:
            event = "reactivated"
        elif old_active and not new_active:
            event = "deactivated"
        elif new_role != old_role:
            event = "role_changed"
        else:
            event = None
        if event:
            cur.execute("UPDATE users SET role = %s::user_role_t, is_active = %s "
                        "WHERE id = %s", (new_role, new_active, uid))
        status = 200
    else:
        new_role, new_active = role or "AE", True if active is None else active
        cur.execute("INSERT INTO users (email, display_name, role, is_active) "
                    "VALUES (%s, %s, %s::user_role_t, %s) RETURNING id",
                    (email, display_name(email), new_role, new_active))
        uid = cur.fetchall()[0][0]
        event, status = "invited", 201
    if event:
        cur.execute("INSERT INTO session_log (user_id, event, role_at_event) "
                    "VALUES (%s, %s, %s::user_role_t)", (uid, event, new_role))

    cur.execute(_SELECT + " WHERE id = %s", (uid,))
    response = {"user": _row(cur.fetchall()[0]), "event": event,
                "changed_by": actor_email}
    cur.execute("INSERT INTO idempotency_keys "
                "(key, user_id, request_hash, status_code, response) "
                "VALUES (%s, %s, %s, %s, %s)",
                (key, actor_id, request_hash, status, json.dumps(response)))
    return status, response
