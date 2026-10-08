"""Users and roles (dma_api.users) — the third API write, owner-adjudicated
2026-10-07. What is asserted:

1. The roster and the write are ADMIN-only: an AE, an inactive Admin and an
   email with no row are refused, and a floor email is an Admin whatever its
   row says.
2. Nobody can remove the last way in: a floor email cannot be demoted or
   deactivated, and an Admin cannot demote or deactivate themself.
3. Every applied change writes one session_log row for the person it changed
   and one idempotency_keys row for the actor; a replay returns the original
   response without a second write, and a reused key with a different body
   is a 409.
4. The module writes only users, session_log and idempotency_keys.
5. Enrolment (POST /v1/me): a first visit gets a row with its allocated role
   (floor ADMIN, ANALYST_EMAILS ANALYST, else AE) and one `login` row; a
   return inside five minutes writes nothing; a return after the cookie's
   eight hours touches last_seen_at and logs `login`; a deactivated account
   is logged `denied` and never reactivated by visiting; an existing role is
   never overwritten by the allocation lists.
"""
import re
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_api.pages import ApiError  # noqa: E402
from dma_api.users import (WRITABLE_TABLES, display_name, enrol, list_users,  # noqa: E402
                           me, set_user)

FLOOR = {"ADMIN_EMAILS": "owner@zennify.com"}


class FakeDb:
    """A tiny in-memory users / session_log / idempotency_keys store that
    answers the statements dma_api.users issues."""

    def __init__(self, users):
        self.users = {}
        for email, role, active in users:
            self.users[email] = {"id": str(uuid.uuid4()), "email": email, "role": role,
                                 "is_active": active, "display_name": display_name(email),
                                 "google_sub": None, "seen": None}
        self.session_log, self.keys, self.writes = [], {}, []
        self._out = []

    def _row(self, u):
        return (u["email"], u["display_name"], u["role"], u["is_active"], None, None,
                u["google_sub"] is not None)

    def cursor(self):
        return self

    def execute(self, sql, params=()):
        s = " ".join(sql.split())
        m = re.match(r"(INSERT INTO|UPDATE) (\w+)", s)
        if m:
            self.writes.append(m.group(2))
        if s.startswith("SELECT id, role::text, is_active, last_seen_at IS NULL"):
            u = self.users.get(params[0])
            seen = u["seen"] if u else None
            self._out = [(u["id"], u["role"], u["is_active"], seen is None or seen > 480,
                          seen is None or seen > 5)] if u else []
        elif s.startswith("UPDATE users SET last_seen_at"):
            for u in self.users.values():
                if u["id"] == params[0]:
                    u["seen"] = 0
        elif s.startswith("SELECT id, role::text, is_active FROM users WHERE email"):
            u = self.users.get(params[0])
            self._out = [(u["id"], u["role"], u["is_active"])] if u else []
        elif s.startswith("SELECT email::text") and "WHERE email" in s:
            u = self.users.get(params[0])
            self._out = [self._row(u)] if u else []
        elif s.startswith("SELECT email::text") and "WHERE id" in s:
            self._out = [self._row(u) for u in self.users.values() if u["id"] == params[0]]
        elif s.startswith("SELECT email::text"):
            self._out = [self._row(u) for u in self.users.values()]
        elif s.startswith("SELECT request_hash"):
            k = self.keys.get(params[0])
            self._out = [k] if k else []
        elif s.startswith("UPDATE users"):
            role, active, uid = params
            for u in self.users.values():
                if u["id"] == uid:
                    u["role"], u["is_active"] = role, active
        elif s.startswith("INSERT INTO users") and "ON CONFLICT" in s:
            email, name, role = params
            if email in self.users:
                self._out = []
            else:
                uid = str(uuid.uuid4())
                self.users[email] = {"id": uid, "email": email, "role": role, "is_active": True,
                                     "display_name": name, "google_sub": None, "seen": 0}
                self._out = [(uid,)]
        elif s.startswith("INSERT INTO users"):
            email, name, role, active = params
            uid = str(uuid.uuid4())
            self.users[email] = {"id": uid, "email": email, "role": role, "is_active": active,
                                 "display_name": name, "google_sub": None, "seen": None}
            self._out = [(uid,)]
        elif s.startswith("INSERT INTO session_log"):
            self.session_log.append(params)
        elif s.startswith("INSERT INTO idempotency_keys"):
            key, uid, h, status, resp = params
            self.keys[key] = (h, status, resp)
        else:
            raise AssertionError(f"unexpected SQL: {s}")

    def fetchall(self):
        out, self._out = self._out, []
        return out


def db():
    return FakeDb([("owner@zennify.com", "ADMIN", True),
                   ("admin@zennify.com", "ADMIN", True),
                   ("gone@zennify.com", "ADMIN", False),
                   ("ae@zennify.com", "AE", True)])


def put(d, actor, body, key=None):
    return set_user(d, actor, body=body, idempotency_key=key or str(uuid.uuid4()), env=FLOOR)


# ── 1. who may read and write ─────────────────────────────────────────────
@pytest.mark.parametrize("actor,code", [("ae@zennify.com", "admin_required"),
                                        ("gone@zennify.com", "admin_required"),
                                        ("stranger@zennify.com", "unknown_actor")])
def test_non_admins_are_refused(actor, code):
    for call in (lambda d: list_users(d, actor, env=FLOOR),
                 lambda d: put(d, actor, {"email": "x@zennify.com", "role": "AE"})):
        with pytest.raises(ApiError) as e:
            call(db())
        assert e.value.code == code and e.value.status == 403


def test_floor_email_is_admin_whatever_its_row_says():
    d = db()
    d.users["owner@zennify.com"]["role"] = "AE"
    assert me(d, "owner@zennify.com", env=FLOOR)["role"] == "ADMIN"
    assert list_users(d, "owner@zennify.com", env=FLOOR)["owner_floor"] == ["owner@zennify.com"]


def test_me_defaults_and_deactivation():
    d = db()
    assert me(d, "new@zennify.com", env=FLOOR) == {
        "email": "new@zennify.com", "role": "AE", "is_active": True,
        "source": "default", "known": False}
    assert me(d, "gone@zennify.com", env=FLOOR)["is_active"] is False
    assert me(d, "ae@zennify.com", env=FLOOR)["role"] == "AE"


# ── 2. lockout guards ─────────────────────────────────────────────────────
@pytest.mark.parametrize("body,code", [
    ({"email": "owner@zennify.com", "role": "AE"}, "owner_floor"),
    ({"email": "owner@zennify.com", "is_active": False}, "owner_floor"),
    ({"email": "admin@zennify.com", "role": "ANALYST"}, "self_lockout"),
    ({"email": "admin@zennify.com", "is_active": False}, "self_lockout"),
    ({"email": "x@gmail.com", "role": "AE"}, "invalid_email"),
    ({"email": "x@zennify.com", "role": "M5"}, "unknown_role"),
    ({"email": "x@zennify.com"}, "nothing_to_change"),
    ({"email": "x@zennify.com", "role": "AE", "team": "x"}, "unknown_field"),
])
def test_refusals(body, code):
    d = db()
    with pytest.raises(ApiError) as e:
        put(d, "admin@zennify.com", body)
    assert e.value.code == code
    assert d.writes == [], "a refusal writes nothing"


def test_idempotency_key_required():
    with pytest.raises(ApiError) as e:
        set_user(db(), "admin@zennify.com", body={"email": "x@zennify.com", "role": "AE"},
                 idempotency_key=None, env=FLOOR)
    assert e.value.code == "idempotency_key_required"


# ── 3. the record ────────────────────────────────────────────────────────
def test_invite_change_deactivate_reactivate_are_each_recorded():
    d = db()
    s, r = put(d, "admin@zennify.com", {"email": "New.Person@zennify.com", "role": "ANALYST"})
    assert s == 201 and r["event"] == "invited"
    assert r["user"]["email"] == "new.person@zennify.com" and r["user"]["role"] == "ANALYST"
    assert r["user"]["display_name"] == "New Person"
    s, r = put(d, "admin@zennify.com", {"email": "new.person@zennify.com", "role": "ADMIN"})
    assert (s, r["event"]) == (200, "role_changed")
    s, r = put(d, "admin@zennify.com", {"email": "new.person@zennify.com", "is_active": False})
    assert r["event"] == "deactivated" and r["user"]["is_active"] is False
    s, r = put(d, "admin@zennify.com", {"email": "new.person@zennify.com", "is_active": True})
    assert r["event"] == "reactivated"
    assert [e[1] for e in d.session_log] == ["invited", "role_changed", "deactivated", "reactivated"]
    assert [e[2] for e in d.session_log] == ["ANALYST", "ADMIN", "ADMIN", "ADMIN"]
    assert len(d.keys) == 4 and r["changed_by"] == "admin@zennify.com"


def test_no_op_change_logs_nothing():
    d = db()
    s, r = put(d, "admin@zennify.com", {"email": "ae@zennify.com", "role": "AE"})
    assert r["event"] is None and d.session_log == []


def test_replay_returns_the_original_and_a_reused_key_is_a_409():
    d = db()
    key = str(uuid.uuid4())
    body = {"email": "ae@zennify.com", "role": "ANALYST"}
    first = put(d, "admin@zennify.com", body, key)
    again = put(d, "admin@zennify.com", body, key)
    assert again == first and len(d.session_log) == 1
    with pytest.raises(ApiError) as e:
        put(d, "admin@zennify.com", {"email": "ae@zennify.com", "role": "ADMIN"}, key)
    assert e.value.code == "idempotency_key_reused" and e.value.status == 409


# ── 4. the write boundary ────────────────────────────────────────────────
def test_writes_only_its_three_tables():
    src = (ROOT / "apps" / "api" / "dma_api" / "users.py").read_text()
    targets = set(re.findall(r'"(?:INSERT INTO|UPDATE) (\w+)', src))
    assert targets == set(WRITABLE_TABLES) == {"users", "session_log", "idempotency_keys"}
    d = db()
    put(d, "admin@zennify.com", {"email": "x@zennify.com", "role": "AE"})
    assert set(d.writes) <= set(WRITABLE_TABLES)


def test_routes_use_the_verified_actor():
    import dma_api.main as m
    routes = {}
    for r in m.app.routes:
        if hasattr(r, "methods"):
            routes.setdefault(r.path, set()).update(r.methods)
    assert "GET" in routes["/v1/me"]
    assert {"GET", "POST"} <= routes["/v1/admin/users"]
    src = (ROOT / "apps" / "api" / "dma_api" / "main.py").read_text()
    body = src[src.index("def _actor_or_error"):src.index("_SUBCAP_COLS = (")]
    assert "verified_actor(request)" in body and "actor:" not in body


# ── 5. enrolment on visit ────────────────────────────────────────────────
ENV = {**FLOOR, "ANALYST_EMAILS": "analyst@zennify.com"}


@pytest.mark.parametrize("email,role", [("new.owner@zennify.com", "AE"),
                                        ("analyst@zennify.com", "ANALYST"),
                                        ("someone@zennify.com", "AE")])
def test_first_visit_enrols_with_the_allocated_role(email, role):
    d = db()
    out = enrol(d, email, env=ENV)
    assert out["enrolled"] is True and out["role"] == role and out["known"] is True
    assert d.users[email]["role"] == role and d.users[email]["display_name"]
    assert [e[1:] for e in d.session_log] == [("login", role)]


def test_an_owner_with_no_row_can_still_invite_an_admin():
    """The owner floor administers even before its first enrolment: the row
    is created (as ADMIN) so the change has someone to be attributed to."""
    d = FakeDb([])
    s, r = put(d, "owner@zennify.com", {"email": "new.admin@zennify.com", "role": "ADMIN"})
    assert s == 201 and r["user"]["role"] == "ADMIN"
    assert d.users["owner@zennify.com"]["role"] == "ADMIN"
    s, r = put(d, "owner@zennify.com", {"email": "an.analyst@zennify.com", "role": "ANALYST"})
    assert r["user"]["role"] == "ANALYST"


def test_floor_email_with_no_row_enrols_as_admin():
    d = FakeDb([])
    out = enrol(d, "owner@zennify.com", env=ENV)
    assert out["role"] == "ADMIN" and d.users["owner@zennify.com"]["role"] == "ADMIN"


def test_return_visits_are_throttled():
    d = db()
    enrol(d, "someone@zennify.com", env=ENV)
    writes = len(d.writes)
    out = enrol(d, "someone@zennify.com", env=ENV)
    assert out["enrolled"] is False and len(d.writes) == writes, "a reload inside 5 min writes nothing"
    d.users["someone@zennify.com"]["seen"] = 30
    enrol(d, "someone@zennify.com", env=ENV)
    assert d.users["someone@zennify.com"]["seen"] == 0
    assert [e[1] for e in d.session_log] == ["login"], "a touch inside 8h is not a new sign-in"
    d.users["someone@zennify.com"]["seen"] = 600
    enrol(d, "someone@zennify.com", env=ENV)
    assert [e[1] for e in d.session_log] == ["login", "login"]


def test_existing_role_is_never_overwritten_by_the_lists():
    d = db()
    d.users["ae@zennify.com"]["seen"] = 600
    out = enrol(d, "ae@zennify.com", env={**ENV, "ANALYST_EMAILS": "ae@zennify.com"})
    assert out["role"] == "AE" and d.users["ae@zennify.com"]["role"] == "AE"


def test_deactivated_visit_is_denied_and_stays_deactivated():
    d = db()
    out = enrol(d, "gone@zennify.com", env=ENV)
    assert out["is_active"] is False and d.users["gone@zennify.com"]["is_active"] is False
    assert [e[1] for e in d.session_log] == ["denied"]


def test_enrolment_refuses_other_domains_and_writes_only_its_tables():
    d = db()
    with pytest.raises(ApiError) as e:
        enrol(d, "x@gmail.com", env=ENV)
    assert e.value.code == "domain_forbidden" and d.writes == []
    enrol(d, "fresh@zennify.com", env=ENV)
    assert set(d.writes) <= {"users", "session_log"}
