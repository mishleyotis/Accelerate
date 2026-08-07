"""The global alert queue and the alert-action write path (invariant 2).

Two behaviours carry the charter here. First, idempotency per TRD §19
verbatim: a replay with the same key and body returns the ORIGINAL
response and applies nothing; the same key with a different body is a
409; no key at all is a 400. Second, the write boundary: the only tables
any code path in dma_api.alerts writes are `alert_actions` and
`idempotency_keys` — asserted both against the module source and against
the SQL an exercised fake connection actually saw, with the serving-table
list taken from the writer spec rather than guessed.

No live DB, per the suite's style: a fake cursor speaks just enough of
the module's own SQL to drive it, and records every statement.
"""
import json
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_api.alerts import (ACTIONS, MAX_LIMIT, STATUSES,     # noqa: E402
                            WRITABLE_TABLES, act, decode_cursor,
                            encode_cursor, queue)
from dma_api.pages import ApiError                            # noqa: E402

T0 = datetime(2026, 8, 1, 9, 30, tzinfo=timezone.utc)
ACTOR = "9f2c1b7e-0000-4000-8000-000000000001"
KEY = "9f2c1b7e-aaaa-4aaa-8aaa-000000000001"
RUN = "11111111-1111-1111-1111-111111111111"


def _alert(i, status="open", severity="high", entity="acme-cu",
           created=None, state="UNWORKED"):
    return {"id": i, "subcap_id": f"P4C1.1.{i}", "severity": severity,
            "state": state, "score": 1.9, "confidence": "LOW",
            "evidence_count": 1, "runs_open": 1,
            "justification": "the one item licenses a floor, not a score",
            "closure_condition": "the FY2025 annual report's tech section",
            "created_at": created or (T0 + timedelta(minutes=i)),
            "run_id": RUN, "entity_id": "e-1", "display_id": entity,
            "legal_name": "Acme Credit Union", "sub_vertical": "SV2",
            "request_id": "REQ-1", "is_active": True, "status": status}


class _Conn:
    """Enough of a pg8000 connection to drive queue() and act(): the queue
    select, the idempotency-key lookup, the alert lookup, and the two
    workflow INSERTs. Every statement is recorded for the write-boundary
    assertion."""

    def __init__(self, alerts=(), actions=(), keys=None):
        self.alerts = list(alerts)
        self.actions = list(actions)
        self.keys = dict(keys or {})
        self.statements = []
        self._out = []

    def cursor(self):
        return self

    def _effective(self, a):
        last = self._last_action(a["id"])
        if last:
            if last["action"] in ("resolved", "waived"):
                return last["action"]
            if last["action"] == "reopened":
                return "open"
        return a["status"]

    def _last_action(self, alert_id):
        mine = [x for x in self.actions if x["alert_id"] == alert_id]
        return max(mine, key=lambda x: (x["occurred_at"], x["id"])) if mine else None

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        params = list(params or [])

        if "FROM heatmap_alerts a" in sql:          # the queue select
            rows = [a for a in self.alerts if a["is_active"]]
            # consume params in the exact order queue() appends them
            if ") = %s" in sql:                     # effective-status filter
                want = params.pop(0)
                rows = [a for a in rows if self._effective(a) == want]
            if "a.severity = %s" in sql:
                want = params.pop(0)
                rows = [a for a in rows if a["severity"] == want]
            if "d.display_id = %s" in sql:
                want = params.pop(0)
                rows = [a for a in rows if a["display_id"] == want]
            if "(a.created_at, a.id) < (%s, %s)" in sql:
                ts, i = params.pop(0), params.pop(0)
                ts = datetime.fromisoformat(ts)
                rows = [a for a in rows
                        if (a["created_at"], a["id"]) < (ts, i)]
            limit = params.pop(0)
            rows.sort(key=lambda a: (a["created_at"], a["id"]), reverse=True)
            out = []
            for a in rows[:limit]:
                la = self._last_action(a["id"])
                n = len([x for x in self.actions if x["alert_id"] == a["id"]])
                out.append((
                    a["id"], a["subcap_id"], a["severity"], a["state"],
                    a["score"], a["confidence"], a["evidence_count"],
                    a["runs_open"], a["justification"],
                    a["closure_condition"], a["created_at"], a["run_id"],
                    a["entity_id"], a["display_id"], a["legal_name"],
                    a["sub_vertical"], a["request_id"], self._effective(a),
                    la and la["action"], la and la["rationale"],
                    la and la["user_id"], la and la["occurred_at"], n))
            self._out = out

        elif "FROM idempotency_keys WHERE key = %s" in sql:
            row = self.keys.get(params[0])
            self._out = [row] if row else []

        elif "FROM heatmap_alerts WHERE id = %s" in sql:
            hit = [a for a in self.alerts if a["id"] == params[0]]
            self._out = [(a["id"], a["run_id"], a["status"]) for a in hit]

        elif "INSERT INTO alert_actions" in sql:
            alert_id, user_id, action, rationale, run_id = params
            row = {"id": len(self.actions) + 1, "alert_id": alert_id,
                   "user_id": user_id, "action": action,
                   "rationale": rationale, "run_id": run_id,
                   "occurred_at": T0 + timedelta(hours=len(self.actions) + 1)}
            self.actions.append(row)
            self._out = [(row["id"], row["occurred_at"])]

        elif "INSERT INTO idempotency_keys" in sql:
            key, user_id, request_hash, status_code, response = params
            assert key not in self.keys, "primary key on key"
            self.keys[key] = (request_hash, status_code, response)
            self._out = []

        else:                                        # pragma: no cover
            raise AssertionError(f"unexpected SQL: {sql}")

    def fetchall(self):
        return self._out


def _body(action="acknowledged", **kw):
    return {"action": action, **kw}


def _act(conn, body, key=KEY, actor=ACTOR, alert_id=1, **kw):
    return act(conn.cursor(), alert_id, body=body, idempotency_key=key,
               actor=actor, **kw)


# ── idempotency ────────────────────────────────────────────────────────
def test_missing_idempotency_key_is_400():
    conn = _Conn(alerts=[_alert(1)])
    with pytest.raises(ApiError) as e:
        _act(conn, _body(), key=None)
    assert e.value.status == 400 and e.value.code == "idempotency_key_required"
    assert conn.actions == [], "nothing may be applied without a key"


def test_idempotent_replay_returns_the_original_response_and_applies_nothing():
    conn = _Conn(alerts=[_alert(1)])
    body = _body("resolved", rationale="closed by the FY2025 report")
    first_status, first = _act(conn, body)
    assert first_status == 201
    assert len(conn.actions) == 1

    second_status, second = _act(conn, dict(body))   # same key, same body
    assert (second_status, second) == (first_status, first), \
        "a replay returns the ORIGINAL response"
    assert len(conn.actions) == 1, "replayed, not re-applied"


def test_same_key_with_a_different_body_is_409():
    conn = _Conn(alerts=[_alert(1)])
    _act(conn, _body("acknowledged"))
    with pytest.raises(ApiError) as e:
        _act(conn, _body("resolved"))
    assert e.value.status == 409 and e.value.code == "idempotency_key_reused"
    assert len(conn.actions) == 1, "a client bug applies nothing"


def test_the_key_is_scoped_to_its_context_not_just_its_body():
    """The same key against a different alert or by a different actor is
    not a retry of the same request — the stored hash covers the route
    context, so it 409s instead of silently replaying a foreign result."""
    conn = _Conn(alerts=[_alert(1), _alert(2)])
    _act(conn, _body(), alert_id=1)
    with pytest.raises(ApiError) as e:
        _act(conn, _body(), alert_id=2)
    assert e.value.status == 409


def test_the_key_and_the_result_are_persisted_together():
    conn = _Conn(alerts=[_alert(1)])
    status, response = _act(conn, _body("acknowledged"))
    stored_hash, stored_status, stored_response = conn.keys[KEY]
    assert stored_status == status == 201
    assert json.loads(stored_response) == response, \
        "the stored response IS the replay (TRD §19: stored with the response)"


# ── the write contract ─────────────────────────────────────────────────
def test_waive_requires_a_rationale():
    conn = _Conn(alerts=[_alert(1)])
    with pytest.raises(ApiError) as e:
        _act(conn, _body("waived"))
    assert e.value.status == 400 and e.value.code == "rationale_required"
    status, response = _act(conn, _body("waived", rationale="cell is out of "
                                        "scope for this sub-vertical"))
    assert status == 201 and response["alert"]["status"] == "waived"


def test_unknown_action_and_unknown_field_are_refused():
    conn = _Conn(alerts=[_alert(1)])
    with pytest.raises(ApiError) as e:
        _act(conn, _body("snoozed"))
    assert e.value.status == 400 and e.value.code == "unknown_action"
    with pytest.raises(ApiError) as e:
        _act(conn, {"action": "resolved", "run_id": "attacker-chosen"})
    assert e.value.status == 400 and e.value.code == "unknown_field", \
        "run_id is recorded from the alert row, never accepted from the client"
    assert conn.actions == []


def test_the_run_is_recorded_from_the_alert_row():
    conn = _Conn(alerts=[_alert(1)])
    _status, response = _act(conn, _body("acknowledged"))
    assert response["action"]["run_id"] == RUN
    assert conn.actions[0]["run_id"] == RUN, \
        "the action stays attached to the run the alert belongs to"


def test_missing_actor_is_400_and_missing_alert_is_404():
    conn = _Conn(alerts=[_alert(1)])
    with pytest.raises(ApiError) as e:
        _act(conn, _body(), actor=None)
    assert e.value.status == 400 and e.value.code == "actor_required"
    with pytest.raises(ApiError) as e:
        _act(conn, _body(), alert_id=99)
    assert e.value.status == 404 and e.value.code == "alert_not_found"


def test_customer_audience_is_refused_on_both_paths():
    conn = _Conn(alerts=[_alert(1)])
    with pytest.raises(ApiError) as e:
        queue(conn.cursor(), audience="customer")
    assert e.value.status == 403 and e.value.code == "audience_forbidden"
    with pytest.raises(ApiError) as e:
        _act(conn, _body(), audience="customer")
    assert e.value.status == 403
    with pytest.raises(ApiError) as e:
        queue(conn.cursor(), audience="martian")
    assert e.value.status == 400 and e.value.code == "unknown_audience"
    # An AE token is refused on Health by the API (Implementation Plan
    # 4.1); this queue is Health's alerts tab at corpus scale.
    with pytest.raises(ApiError) as e:
        queue(conn.cursor(), role="AE")
    assert e.value.status == 403 and e.value.code == "role_forbidden"
    assert conn.actions == [] and conn.statements == [], \
        "refusals happen before any SQL runs"


# ── the write boundary (invariant 2) ───────────────────────────────────
def test_no_serving_table_is_written_by_any_code_path():
    """Asserted twice. Statically: every INSERT/UPDATE/DELETE in the module
    source targets a workflow table. Dynamically: drive the real flows and
    check every captured statement against the writer spec's serving-table
    list — the authoritative census of what promotion writes."""
    src = (ROOT / "apps" / "api" / "dma_api" / "alerts.py").read_text()
    writes = re.findall(
        r"(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(\w+)", src, re.I)
    assert writes, "the write path exists"
    assert set(writes) <= set(WRITABLE_TABLES) == {"alert_actions",
                                                   "idempotency_keys"}

    conn = _Conn(alerts=[_alert(1), _alert(2)])
    _act(conn, _body("resolved", rationale="done"))
    _act(conn, dict(_body("resolved", rationale="done")))       # replay
    queue(conn.cursor(), status="all")

    spec = json.loads((ROOT / "apps" / "api" / "dma_api" /
                       "writer_spec.json").read_text())
    serving = {w["table"] for p in spec["specs"] for w in p["writers"]}
    assert "heatmap_alerts" in serving, "the census covers the alerts table"
    for sql, _params in conn.statements:
        for table in re.findall(
                r"(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(\w+)", sql, re.I):
            assert table not in serving, f"serving table written: {table}"
            assert table in WRITABLE_TABLES, f"unexpected write target: {table}"


def test_status_moves_by_derivation_never_by_updating_the_serving_row():
    """Last write wins on status, both actions retained in history (TRD
    §12) — without one UPDATE: the queue derives the effective status from
    the latest action at read."""
    conn = _Conn(alerts=[_alert(1)])
    _act(conn, _body("resolved", rationale="found it"),
         key=str(uuid.uuid4()))
    _act(conn, _body("reopened", rationale="the closure did not hold"),
         key=str(uuid.uuid4()))
    assert len(conn.actions) == 2, "both actions are retained in history"
    assert conn.alerts[0]["status"] == "open", "the serving row never moved"

    out = queue(conn.cursor(), status="open")
    row = out["alerts"][0]
    assert row["status"] == "open", "reopened derives back to open"
    assert row["action_state"]["action"] == "reopened"
    assert row["action_count"] == 2, "computed over the actions table at read"


# ── the queue ──────────────────────────────────────────────────────────
def test_open_queue_excludes_alerts_whose_latest_action_closed_them():
    conn = _Conn(alerts=[_alert(1), _alert(2)])
    _act(conn, _body("resolved", rationale="done"), alert_id=1)
    out = queue(conn.cursor(), status="open")
    assert [a["id"] for a in out["alerts"]] == [2]
    waived = queue(conn.cursor(), status="resolved")
    assert [a["id"] for a in waived["alerts"]] == [1], \
        "the closed alert is a register entry, not gone"


def test_queue_row_carries_entity_cell_severity_count_and_action_state():
    conn = _Conn(alerts=[_alert(7, severity="critical")])
    row = queue(conn.cursor())["alerts"][0]
    assert row["entity"] == {"display_id": "acme-cu",
                             "entity_name": "Acme Credit Union",
                             "sub_vertical": "SV2"}
    assert row["subcap_id"] == "P4C1.1.7" and row["severity"] == "critical"
    assert row["evidence_count"] == 1, "H3's current count, as promoted"
    assert row["action_count"] == 0 and row["action_state"] is None
    assert row["run"]["run_id"] == RUN
    assert row["state"] == "UNWORKED", \
        "UNWORKED vs WORKED_ABSENT must survive to the queue"


def test_pagination_is_stable_under_inserts_while_paging():
    """The reason for keyset pagination (TRD §19): offset pagination on a
    table receiving inserts skips and repeats rows. A new alert arriving
    between pages must shift nothing."""
    conn = _Conn(alerts=[_alert(i) for i in range(1, 8)])
    page1 = queue(conn.cursor(), limit=3)
    assert [a["id"] for a in page1["alerts"]] == [7, 6, 5]
    assert page1["has_more"] is True and page1["next_cursor"]

    # an alert lands at the top of the queue mid-paging
    conn.alerts.append(_alert(99, created=T0 + timedelta(hours=9)))

    page2 = queue(conn.cursor(), limit=3, cursor=page1["next_cursor"])
    assert [a["id"] for a in page2["alerts"]] == [4, 3, 2], \
        "no repeats, no skips"
    page3 = queue(conn.cursor(), limit=3, cursor=page2["next_cursor"])
    assert [a["id"] for a in page3["alerts"]] == [1]
    assert page3["has_more"] is False and page3["next_cursor"] is None


def test_the_predicate_is_the_row_comparison_form_with_a_tiebreak():
    """Two alerts created in the same millisecond page unstably without the
    unique tiebreak; the disjunction form abandons the composite index."""
    same = T0 + timedelta(hours=1)
    conn = _Conn(alerts=[_alert(1, created=same), _alert(2, created=same),
                         _alert(3, created=same)])
    page1 = queue(conn.cursor(), limit=2)
    page2 = queue(conn.cursor(), limit=2, cursor=page1["next_cursor"])
    assert ([a["id"] for a in page1["alerts"]] +
            [a["id"] for a in page2["alerts"]]) == [3, 2, 1]

    sql = next(s for s, _ in conn.statements if "heatmap_alerts a" in s
               and "(a.created_at, a.id) < (%s, %s)" in s)
    assert "ORDER BY a.created_at DESC, a.id DESC" in sql
    assert " OR " not in sql, "row comparison, not the disjunction"

    src = (ROOT / "apps" / "api" / "dma_api" / "alerts.py").read_text()
    assert "OFFSET" not in src, "cursor, never offset"


def test_a_cursor_from_a_different_filter_set_is_rejected():
    conn = _Conn(alerts=[_alert(i) for i in range(1, 4)])
    page1 = queue(conn.cursor(), limit=1, severity="high")
    with pytest.raises(ApiError) as e:
        queue(conn.cursor(), limit=1, severity="critical",
              cursor=page1["next_cursor"])
    assert e.value.status == 400 and e.value.code == "cursor_filter_mismatch"
    with pytest.raises(ApiError) as e:
        queue(conn.cursor(), cursor="not-base64!!")
    assert e.value.status == 400 and e.value.code == "malformed_cursor"
    # and the round trip itself holds
    c = encode_cursor(T0, 8812, "fp")
    assert decode_cursor(c, "fp") == {"c": T0.isoformat(), "i": 8812}


def test_limit_is_bounded_and_status_vocabulary_is_closed():
    conn = _Conn(alerts=[_alert(i) for i in range(1, 6)])
    out = queue(conn.cursor(), limit=10 ** 9)
    _sql, params = conn.statements[-1]
    assert params[-1] == MAX_LIMIT + 1, "hard maximum 200, +1 for has_more"
    assert out["count"] == 5
    with pytest.raises(ApiError) as e:
        queue(conn.cursor(), status="OPEN")
    assert e.value.code == "unknown_status", \
        "the vocabulary is lowercase (0015) and closed: " + " · ".join(STATUSES)


def test_enum_matches_the_migrations_alert_action_t():
    """The five actions come from alert_action_t (0002) verbatim — a value
    invented here would abort the INSERT with 22P02 at the enum cast."""
    src = (ROOT / "migrations" / "versions" / "0002_enumerated_types.py").read_text()
    m = re.search(r'"alert_action_t": \(\[([^\]]+)\]', src)
    assert m, "alert_action_t exists in 0002"
    assert tuple(x.strip().strip('"') for x in m.group(1).split(",")) == ACTIONS


# ── route wiring ───────────────────────────────────────────────────────
def test_routes_are_wired_with_the_trd_verbs():
    import dma_api.main as m
    routes = {r.path: r.methods for r in m.app.routes if hasattr(r, "methods")}
    assert "GET" in routes["/v1/alerts"]
    assert "POST" in routes["/v1/alerts/{alert_id}/actions"], \
        "TRD §08: POST /api/v1/alerts/{alert_id}/actions"
    post_routes = [p for p, methods in routes.items() if "POST" in methods]
    assert post_routes == ["/v1/alerts/{alert_id}/actions"], \
        "alert actions are the API's only write route so far (invariant 2)"
