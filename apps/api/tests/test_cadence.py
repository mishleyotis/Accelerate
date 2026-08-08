"""The 6-month refresh cadence: the date, its basis, the due date, the queue.

Four things carry the charter here.

1. A derived date can never render as a stated one. `cadence_for` always
   returns the rung that produced the date, and the vocabulary it reports is
   asserted against migration 0031's own source — the function and the API
   cannot drift apart silently.
2. Absent beats wrong (invariant 9). No assessment date means a NULL due date
   and NULL distances, never 0, never today, never a sentinel.
3. The distance is measured against a stated `as_of`, so every number in the
   response can be checked by hand.
4. The read path writes nothing. `dma_api.cadence` is asserted, against its
   own source AND against the SQL an exercised fake connection saw, to issue
   no INSERT/UPDATE/DELETE — the refresh request is written by the Job, whose
   own write is exercised separately below.

No live DB, per the suite's style: a fake cursor speaks just enough of the
module's own SQL to drive it, and records every statement.
"""
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_api.cadence import (BASIS_MEANING, CADENCE_STATUSES,  # noqa: E402
                             DATE_BASES, OPEN_REQUEST_STATUSES,
                             REQUEST_STATUSES, cadence_for, entity_cadence,
                             refresh_queue)
from dma_api.pages import ApiError                             # noqa: E402
from dma_api.refresh_job import request_refresh                # noqa: E402

MIGRATION_0031 = ROOT / "migrations" / "versions" / "0031_assessment_date_basis_and_due.py"
MIGRATION_0032 = ROOT / "migrations" / "versions" / "0032_refresh_requests.py"

AS_OF = date(2026, 8, 8)
RUN = "c1351d25-a612-4dbe-b498-127bccaf6810"
ENTITY = "22222222-2222-2222-2222-222222222222"


# ── the vocabulary is one vocabulary ───────────────────────────────────
def test_the_basis_vocabulary_is_the_migration_s_vocabulary():
    """0031's function is the only thing that produces a basis; this module
    is the only thing that explains one. A value in one and not the other is
    either an unexplained enum on a client page or a branch that never runs."""
    src = MIGRATION_0031.read_text(encoding="utf-8")
    in_sql = set(re.findall(r"'(STATED|DERIVED_[A-Z_]+|UNKNOWN)'", src))
    assert in_sql == set(DATE_BASES), (
        f"migration produces {sorted(in_sql)}, API reports {sorted(DATE_BASES)}")
    assert set(BASIS_MEANING) == set(DATE_BASES), \
        "every basis needs a sentence a reader can act on"


def test_the_request_status_vocabulary_is_the_migration_s_vocabulary():
    src = MIGRATION_0032.read_text(encoding="utf-8")
    check = re.search(r"CHECK \(status IN \(([^)]*)\)", src, re.S).group(1)
    in_sql = set(re.findall(r"'([A-Z_]+)'", check))
    assert in_sql == set(REQUEST_STATUSES)
    assert set(OPEN_REQUEST_STATUSES) <= set(REQUEST_STATUSES)


def test_the_six_months_is_stated_once_and_not_here():
    """The interval lives in the view (0031). Restating it in the API would
    be a second definition of the cadence, free to drift from the first."""
    api = (ROOT / "apps" / "api" / "dma_api" / "cadence.py").read_text(encoding="utf-8")
    assert "6 months" not in api and "180" not in api and "relativedelta" not in api
    assert "INTERVAL '6 months'" in MIGRATION_0031.read_text(encoding="utf-8")


# ── the derived date never renders as a stated one ─────────────────────
@pytest.mark.parametrize("basis,stated", [
    ("STATED", True),
    ("DERIVED_ARTEFACT_TIMESTAMP", False),
    ("DERIVED_REQUEST_ID_TOKEN", False),
    ("UNKNOWN", False),
])
def test_only_a_stated_date_is_marked_stated(basis, stated):
    block = cadence_for(date(2026, 3, 30), basis, "manifest.run_id",
                        date(2026, 9, 30), as_of=AS_OF)
    assert block["assessment_date_is_stated"] is stated
    assert block["assessment_date_basis"] == basis
    assert block["assessment_date_basis_note"] == BASIS_MEANING[basis]


def test_baxter_s_own_shape_is_disclosed_as_a_derivation():
    """The measured production case: the date every client page renders was
    parsed out of the token in DMA-ASM-BCU-20260330-0001."""
    block = cadence_for(date(2026, 3, 30), "DERIVED_REQUEST_ID_TOKEN",
                        "manifest.run_id", date(2026, 9, 30), as_of=AS_OF)
    assert block["assessment_date"] == "2026-03-30"
    assert block["assessment_date_is_stated"] is False
    assert "request id" in block["assessment_date_basis_note"]
    assert block["due_date"] == "2026-09-30"
    assert block["status"] == "SCHEDULED"
    assert block["days_until_due"] == 53
    assert block["weeks_until_due"] == 7      # whole weeks, toward zero
    assert block["weeks_overdue"] is None
    assert block["is_overdue"] is False
    assert block["as_of"] == "2026-08-08"


# ── absent beats wrong ─────────────────────────────────────────────────
def test_no_assessment_date_gives_no_due_date_and_no_number():
    block = cadence_for(None, "UNKNOWN", None, None, as_of=AS_OF)
    assert block["assessment_date"] is None
    assert block["due_date"] is None
    for k in ("days_until_due", "weeks_until_due", "weeks_overdue", "is_overdue"):
        assert block[k] is None, f"{k} must be absent, not 0"
    assert block["status"] == "UNKNOWN"
    assert block["unknown_reason"]
    assert block["status"] in CADENCE_STATUSES


def test_an_unrecognised_basis_degrades_to_unknown_rather_than_echoing():
    block = cadence_for(date(2026, 1, 1), "SOMETHING_NEW", "x", None, as_of=AS_OF)
    assert block["assessment_date_basis"] == "UNKNOWN"
    assert block["assessment_date_is_stated"] is False


@pytest.mark.parametrize("due,days,weeks_until,weeks_over,status", [
    (date(2026, 9, 30),  53,   7, None, "SCHEDULED"),
    (date(2026, 8, 8),    0,   0, None, "SCHEDULED"),
    (date(2026, 8, 7),   -1,   0,    0, "OVERDUE"),
    (date(2026, 7, 25), -14,  -2,    2, "OVERDUE"),
    (date(2026, 8, 15),   7,   1, None, "SCHEDULED"),
])
def test_the_distance_is_measured_not_banded(due, days, weeks_until,
                                             weeks_over, status):
    block = cadence_for(date(2026, 2, 8), "STATED", "manifest.assessment_date",
                        due, as_of=AS_OF)
    assert block["days_until_due"] == days
    assert block["weeks_until_due"] == weeks_until
    assert block["weeks_overdue"] == weeks_over
    assert block["status"] == status


def test_due_today_is_not_overdue():
    block = cadence_for(date(2026, 2, 8), "STATED", "f", AS_OF, as_of=AS_OF)
    assert block["is_overdue"] is False and block["status"] == "SCHEDULED"


def test_no_soon_band_is_invented():
    """A "due soon" threshold would be policy this codebase has not been
    given, and an invented one reads exactly like a measured one."""
    assert set(CADENCE_STATUSES) == {"SCHEDULED", "OVERDUE", "UNKNOWN"}


def test_a_datetime_is_accepted_where_the_driver_returns_one():
    block = cadence_for(datetime(2026, 3, 30, 12, tzinfo=timezone.utc),
                        "STATED", "f", datetime(2026, 9, 30, tzinfo=timezone.utc),
                        as_of=AS_OF)
    assert block["assessment_date"] == "2026-03-30"
    assert block["due_date"] == "2026-09-30"


# ── the read path, on a fake connection ────────────────────────────────
_DIR_ROW = (ENTITY, "baxter-credit-union-bcu", "Baxter Credit Union (BCU)",
            "SV2", None, RUN, "DMA-ASM-BCU-20260330-0001", 1, True, "PROMOTED",
            2.71, 765, 836, "v5.0",
            datetime(2026, 3, 30, tzinfo=timezone.utc),
            datetime(2026, 8, 8, 7, 50, tzinfo=timezone.utc),
            date(2026, 3, 30), "DERIVED_REQUEST_ID_TOKEN", "manifest.run_id",
            date(2026, 9, 30))

_REQ_ROW = (1, ENTITY, RUN, "human", "ae@zennify.com", "client asked at QBR",
            "REQUESTED", None, datetime(2026, 8, 1, tzinfo=timezone.utc),
            datetime(2026, 8, 1, tzinfo=timezone.utc), None)


class _Conn:
    """Enough of a pg8000 connection to drive the cadence reads. Every
    statement is recorded for the write-boundary assertion."""

    def __init__(self, directory=(_DIR_ROW,), requests=(), undatable=0):
        self.directory = list(directory)
        self.requests = list(requests)
        self.undatable = undatable
        self.statements = []
        self._out = []

    def cursor(self):
        return self

    def execute(self, sql, params=None):
        self.statements.append((sql, list(params or [])))
        if "FROM serving_directory" in sql and "refresh_requests" not in sql:
            if "refresh_due_date IS NULL" in sql:
                self._out = [(self.undatable,)]
            elif "refresh_due_date <= %s" in sql:
                cutoff = params[0]
                self._out = [(r[1], r[2], r[5], r[6], r[7], r[16], r[17],
                              r[18], r[19], r[10])
                             for r in self.directory
                             if r[8] and r[19] and r[19] <= cutoff]
            else:
                want = params[0]
                self._out = [r for r in self.directory if r[1] == want]
        elif "FROM refresh_requests q" in sql:
            self._out = [tuple(q) + (_DIR_ROW[1], _DIR_ROW[2], _DIR_ROW[6],
                                     _DIR_ROW[16], _DIR_ROW[17], _DIR_ROW[18],
                                     _DIR_ROW[19])
                         for q in self.requests
                         if q[6] in OPEN_REQUEST_STATUSES]
        elif "FROM refresh_requests" in sql:
            self._out = [tuple(q) for q in self.requests]
        else:                                          # pragma: no cover
            raise AssertionError(f"unexpected SQL: {sql}")

    def fetchall(self):
        return self._out

    def fetchone(self):
        return self._out[0] if self._out else None


def _written(conn):
    return [s for s, _ in conn.statements
            if re.search(r"\b(INSERT|UPDATE|DELETE|TRUNCATE)\b", s, re.I)]


def test_entity_cadence_reports_the_run_the_pages_serve():
    conn = _Conn(requests=[_REQ_ROW])
    body = entity_cadence(conn.cursor(), "baxter-credit-union-bcu")
    assert body["run"]["run_id"] == RUN
    assert body["run"]["assessment_date"] == "2026-03-30"
    assert body["cadence"]["due_date"] == "2026-09-30"
    assert body["open_request"]["requested_by"] == "ae@zennify.com"
    assert body["requests_state"] is None
    assert _written(conn) == [], "the cadence read path writes nothing"


def test_the_page_header_and_the_cadence_cannot_disagree():
    """Both come from one `resolve_run`, so there is one date, not two."""
    conn = _Conn()
    body = entity_cadence(conn.cursor(), "baxter-credit-union-bcu")
    assert body["run"]["assessment_date"] == body["cadence"]["assessment_date"]
    assert body["run"]["assessment_date_basis"] == \
        body["cadence"]["assessment_date_basis"]
    assert body["run"]["refresh_due_date"] == body["cadence"]["due_date"]


def test_no_request_is_a_named_state_not_an_empty_list():
    conn = _Conn()
    body = entity_cadence(conn.cursor(), "baxter-credit-union-bcu")
    assert body["requests"] == []
    assert body["requests_state"]["kind"] == "no_requests"
    assert body["open_request"] is None


def test_the_customer_audience_never_sees_who_asked():
    conn = _Conn(requests=[_REQ_ROW])
    body = entity_cadence(conn.cursor(), "baxter-credit-union-bcu",
                          audience="customer")
    assert body["requests"] is None
    assert body["requests_state"]["kind"] == "withheld_for_audience"
    blob = repr(body)
    assert "ae@zennify.com" not in blob and "QBR" not in blob
    # the client's own assessment date IS theirs to see, with its basis
    assert body["cadence"]["assessment_date"] == "2026-03-30"
    assert body["cadence"]["assessment_date_is_stated"] is False


def test_an_unknown_audience_is_refused_before_any_query():
    conn = _Conn()
    with pytest.raises(ApiError) as e:
        entity_cadence(conn.cursor(), "baxter-credit-union-bcu", audience="public")
    assert e.value.status == 400
    assert conn.statements == []


def test_the_queue_is_internal_only():
    conn = _Conn()
    with pytest.raises(ApiError) as e:
        refresh_queue(conn.cursor(), audience="customer")
    assert e.value.status == 403
    assert conn.statements == []


def test_the_queue_separates_what_was_asked_from_what_came_due():
    conn = _Conn(requests=[_REQ_ROW], undatable=3)
    q = refresh_queue(conn.cursor(), within_days=60, as_of=AS_OF)
    assert [r["display_id"] for r in q["requested"]] == ["baxter-credit-union-bcu"]
    assert [r["display_id"] for r in q["due"]] == ["baxter-credit-union-bcu"]
    assert q["counts"]["requested_open"] == 1
    assert q["counts"]["due"] == 1
    assert q["counts"]["overdue"] == 0
    assert q["counts"]["due_and_also_requested"] == 1
    assert q["counts"]["active_runs_with_no_assessment_date"] == 3
    assert q["as_of"] == "2026-08-08"
    assert _written(conn) == [], "the queue read path writes nothing"


def test_a_client_not_yet_due_is_not_in_the_due_list():
    conn = _Conn()
    q = refresh_queue(conn.cursor(), within_days=0, as_of=AS_OF)
    assert q["due"] == []
    assert q["counts"]["due"] == 0


def test_runs_with_no_assessment_date_are_counted_not_silently_absent():
    """They can never appear in `due` — silence there would read as
    'nothing is due' when the truth is 'this could not be judged'."""
    conn = _Conn(undatable=41)
    q = refresh_queue(conn.cursor(), within_days=3650, as_of=AS_OF)
    assert q["counts"]["active_runs_with_no_assessment_date"] == 41


def test_the_read_module_contains_no_write_statement():
    src = (ROOT / "apps" / "api" / "dma_api" / "cadence.py").read_text(encoding="utf-8")
    body = "\n".join(line for line in src.splitlines()
                     if not line.strip().startswith("#"))
    for verb in ("INSERT INTO", "UPDATE ", "DELETE FROM"):
        assert verb not in body, f"{verb} in the cadence read path"


# ── the write path: the Job, not the API ───────────────────────────────
class _JobConn:
    """The refresh Job's connection: entities, runs, refresh_requests."""

    def __init__(self, entity=ENTITY, run=RUN, requests=None):
        self.entity, self.run = entity, run
        self.requests = list(requests or [])
        self.statements = []
        self.commits = 0
        self._out = []

    def cursor(self):
        return self

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass

    def execute(self, sql, params=None):
        self.statements.append((sql, list(params or [])))
        if "FROM entities WHERE display_id" in sql:
            self._out = [(self.entity,)] if self.entity else []
        elif "FROM runs" in sql:
            self._out = [(self.run,)] if self.run else []
        elif "FROM refresh_requests" in sql:
            self._out = [tuple(r) for r in self.requests
                         if r[6] in OPEN_REQUEST_STATUSES]
        elif "INSERT INTO refresh_requests" in sql:
            entity_id, run_id, actor, reason = params
            row = (len(self.requests) + 1, entity_id, run_id, "human", actor,
                   reason, "REQUESTED", None,
                   datetime(2026, 8, 8, tzinfo=timezone.utc),
                   datetime(2026, 8, 8, tzinfo=timezone.utc), None)
            self.requests.append(row)
            self._out = [(row[0], row[8])]
        elif "UPDATE refresh_requests" in sql:
            note, rid = params
            self.requests = [
                (r[0], r[1], r[2], r[3], r[4], r[5], "CANCELLED", r[7], r[8],
                 r[9], note) if r[0] == rid else r for r in self.requests]
            self._out = []
        else:                                          # pragma: no cover
            raise AssertionError(f"unexpected SQL: {sql}")

    def fetchone(self):
        return self._out[0] if self._out else None

    def fetchall(self):
        return self._out


def test_the_job_records_the_request_with_the_run_it_was_asked_against():
    conn = _JobConn()
    out = request_refresh(conn, "baxter-credit-union-bcu", "ae@zennify.com",
                          reason="client asked at QBR")
    assert out["ok"] and out["action"] == "requested"
    assert out["status"] == "REQUESTED"
    assert out["observed_run_id"] == RUN
    assert conn.commits == 1


def test_the_job_promises_no_schedule():
    """The toast it replaces said "Rerun queued — first batch in ~3 min" with
    no mechanism behind it. Nothing here may state a time."""
    conn = _JobConn()
    out = request_refresh(conn, "baxter-credit-union-bcu", "ae@zennify.com")
    blob = " ".join(str(v) for v in out.values()).lower()
    for promise in ("min", "queued", "eta", "shortly", "batch"):
        assert promise not in blob, f"the response promises {promise!r}"


def test_a_second_click_returns_the_open_request_rather_than_a_second_row():
    conn = _JobConn(requests=[_REQ_ROW])
    out = request_refresh(conn, "baxter-credit-union-bcu", "someone@zennify.com")
    assert out["action"] == "already_open"
    assert out["request_id"] == 1
    assert out["requested_by"] == "ae@zennify.com"
    assert len(conn.requests) == 1
    assert not any("INSERT" in s for s, _ in conn.statements)


def test_an_unknown_entity_is_refused_and_writes_nothing():
    conn = _JobConn(entity=None)
    out = request_refresh(conn, "no-such-client", "ae@zennify.com")
    assert out["ok"] is False and out["error"] == "entity_not_found"
    assert not any("INSERT" in s for s, _ in conn.statements)


def test_cancel_closes_the_open_request_and_creates_nothing():
    conn = _JobConn(requests=[_REQ_ROW])
    out = request_refresh(conn, "baxter-credit-union-bcu", "ae@zennify.com",
                          cancel=True)
    assert out["action"] == "cancelled"
    assert conn.requests[0][6] == "CANCELLED"
    assert not any("INSERT" in s for s, _ in conn.statements)


def test_cancel_with_nothing_open_is_not_an_error():
    conn = _JobConn()
    out = request_refresh(conn, "baxter-credit-union-bcu", "ae@zennify.com",
                          cancel=True)
    assert out["ok"] and out["action"] == "nothing_to_cancel"


def test_the_job_writes_exactly_one_table():
    conn = _JobConn()
    request_refresh(conn, "baxter-credit-union-bcu", "ae@zennify.com")
    written = {re.search(r"(?:INSERT INTO|UPDATE)\s+(\w+)", s, re.I).group(1)
               for s, _ in conn.statements
               if re.search(r"\b(INSERT INTO|UPDATE)\b", s, re.I)}
    assert written == {"refresh_requests"}


def test_the_api_holds_no_grant_that_would_let_an_endpoint_write_the_queue():
    """Invariant 2 is enforced by the grant, not by this module's manners:
    svc_api gets SELECT and nothing else on refresh_requests (0032)."""
    src = MIGRATION_0032.read_text(encoding="utf-8")
    api_grants = re.findall(r"GRANT ([A-Z, ]+) ON refresh_requests TO svc_api", src)
    assert api_grants == ["SELECT "] or api_grants == ["SELECT"], api_grants
    assert "GRANT SELECT, INSERT, UPDATE ON refresh_requests TO svc_worker" in src
