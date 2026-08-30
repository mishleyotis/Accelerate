"""The refresh cadence: when the assessment was made, when it comes due, and
what has been asked for.

Three routes, wired in main.py:

  GET /v1/entities/{display_id}/refresh   one client's cadence state
  GET /v1/ops/refresh-queue               what the synthesis routine drains
  GET /v1/ops/refresh-due                 (same handler, `due` half only)

Read-only, every one of them. Nothing in this module writes: a refresh
request reaches the database through the `dmai-refresh` Cloud Run Job, which
runs as the ingest identity, because invariant 2 enumerates the API's writes
as annotations and alert actions and a refresh request is neither. The
trade-off and the alternative are argued in migration 0032's docstring.

## What is computed here, and what is not

The assessment date and the six-month due date are NOT computed here. They
come from `serving_directory`, which carries them from `run_assessment_date`
(migration 0031) — one derivation, evaluated in one place, reported with the
basis that produced it. Restating the six months in this process would be a
second definition of the cadence that could drift from the first.

What IS computed here is the only part that cannot be stored: the distance
between the due date and now. A clock reading frozen into a materialised view
is a lie that ages, so `days_until_due` is measured at request time against
`as_of`, which is returned with it so the number can be checked.

## Absent beats wrong

A run whose assessment date resolved to nothing has `basis = 'UNKNOWN'`, a
NULL date, a NULL due date, and every distance NULL — never 0, never "today",
never a sentinel (invariant 9). The status says `UNKNOWN` and the reason says
why, which is a fact a surface can render honestly.

And a date the package never stated is reported as derived, with the rung that
produced it, so no surface can present a token parsed out of a request id as
an assessment the client confirmed.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from .pages import AUDIENCES, ApiError, resolve_run

#: `run_assessment_date`'s basis vocabulary (migration 0031), verbatim. The
#: test suite asserts these four strings against the migration source, so the
#: API cannot drift from the function it reports.
DATE_BASES = ("STATED", "DERIVED_ARTEFACT_TIMESTAMP",
              "DERIVED_REQUEST_ID_TOKEN", "UNKNOWN")

#: What each rung means to a reader. The API ships the sentence rather than the
#: enum alone: a surface that renders "DERIVED_REQUEST_ID_TOKEN" beside a date
#: has disclosed nothing.
BASIS_MEANING = {
    "STATED": "the assessment package states this date",
    "DERIVED_ARTEFACT_TIMESTAMP": (
        "the package states no assessment date; this is when the package file "
        "itself was written"),
    "DERIVED_REQUEST_ID_TOKEN": (
        "the package states no assessment date; this is the date token inside "
        "the run's own request id"),
    "UNKNOWN": "nothing in the package resolves to a date",
}

#: refresh_requests.status (migration 0032), verbatim.
REQUEST_STATUSES = ("REQUESTED", "ACKNOWLEDGED", "FULFILLED", "CANCELLED")
OPEN_REQUEST_STATUSES = ("REQUESTED", "ACKNOWLEDGED")

#: Cadence status. Deliberately three values and no "due soon" band: a
#: threshold on "soon" would be a policy this codebase has not been given, and
#: an invented one reads to a client exactly like a measured one. The signed
#: distance is returned instead, and the surface bands it.
CADENCE_STATUSES = ("SCHEDULED", "OVERDUE", "UNKNOWN")

MAX_LIMIT = 200
DEFAULT_LIMIT = 50

_REQUEST_COLS = ("id", "entity_id", "observed_run_id", "origin", "requested_by",
                 "reason", "status", "fulfilled_by_run_id", "requested_at",
                 "updated_at", "note")


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


def _as_date(v):
    """A DATE, whatever shape it arrived in — the driver hands back `date`,
    `resolve_run` has already turned it into an ISO day, and a timestamp
    column arrives as `datetime`. One coercion, so the block does not depend
    on which caller it came from. Anything unparseable is absent, not today."""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str) and v.strip():
        try:
            return date.fromisoformat(v.strip()[:10])
        except ValueError:
            return None
    return None


def _whole_weeks(days: int) -> int:
    """Whole completed weeks in `days`, toward zero.

    53 days is "7 weeks", not "8": rounding up would tell a reader they have
    longer than they do on the way in, and less trouble than they have on the
    way out. `days_until_due` is returned alongside so a surface can say
    "3 days" where weeks would round to nothing.
    """
    return int(abs(days) // 7) * (1 if days >= 0 else -1)


def cadence_for(assessment_date, basis, source_field, due_date,
                as_of: date | None = None) -> dict:
    """The cadence block, from the view's four columns plus a clock.

    Pure — every input is data, which is what makes it testable without a
    database and what keeps `as_of` honest in the response.
    """
    as_of = as_of or datetime.now(timezone.utc).date()
    assessment_date = _as_date(assessment_date)
    due_date = _as_date(due_date)
    basis = basis if basis in DATE_BASES else "UNKNOWN"

    block = {
        "assessment_date": _iso(assessment_date),
        "assessment_date_basis": basis,
        "assessment_date_source": source_field,
        "assessment_date_is_stated": basis == "STATED",
        "assessment_date_basis_note": BASIS_MEANING[basis],
        "due_date": _iso(due_date),
        "as_of": _iso(as_of),
        "days_until_due": None,
        "weeks_until_due": None,
        "weeks_overdue": None,
        "is_overdue": None,
        "status": "UNKNOWN",
        "unknown_reason": None,
    }
    if due_date is None:
        block["unknown_reason"] = (
            "no due date, because " + BASIS_MEANING["UNKNOWN"]
            if basis == "UNKNOWN"
            else "no due date: the run carries no assessment date")
        return block

    days = (due_date - as_of).days
    block["days_until_due"] = days
    block["weeks_until_due"] = _whole_weeks(days)
    block["is_overdue"] = days < 0
    block["weeks_overdue"] = _whole_weeks(-days) if days < 0 else None
    block["status"] = "OVERDUE" if days < 0 else "SCHEDULED"
    return block


def _requests(cur, entity_id, limit: int = 10) -> list[dict]:
    cur.execute(
        f"SELECT {', '.join(_REQUEST_COLS)} FROM refresh_requests "
        "WHERE entity_id = %s ORDER BY requested_at DESC, id DESC LIMIT %s",
        (entity_id, limit))
    out = []
    for row in cur.fetchall():
        d = dict(zip(_REQUEST_COLS, row))
        for k in ("entity_id", "observed_run_id", "fulfilled_by_run_id"):
            d[k] = str(d[k]) if d[k] is not None else None
        for k in ("requested_at", "updated_at"):
            d[k] = _iso(d[k])
        d["is_open"] = d["status"] in OPEN_REQUEST_STATUSES
        out.append(d)
    return out


def entity_cadence(cur, display_id: str, audience: str = "internal",
                   run: str | None = None, role: str | None = None,
                   allow_history: bool = False,
                   as_of: date | None = None) -> dict:
    """One client's cadence state, on the run the pages are serving.

    Resolved through `resolve_run` rather than through a second query, so the
    date on this response and the date in the page header cannot disagree.
    """
    if audience not in AUDIENCES:
        raise ApiError(400, "unknown_audience",
                       f"audience must be one of {' · '.join(AUDIENCES)}")
    entity_id, entity, run_meta, _ = resolve_run(cur, display_id, run,
                                                 allow_history)
    block = cadence_for(run_meta.get("assessment_date"),
                        run_meta.get("assessment_date_basis"),
                        run_meta.get("assessment_date_source"),
                        run_meta.get("refresh_due_date"), as_of=as_of)

    body = {"entity": entity, "run": run_meta, "audience": audience,
            "cadence": block}

    if audience == "customer":
        # Who asked for a rerun, when, and why is internal workflow — the
        # same class of fact as an alert action's rationale. Default-deny:
        # withheld as a named state rather than an empty list, so blank and
        # withheld do not look the same.
        body["requests"] = None
        body["requests_state"] = {
            "kind": "withheld_for_audience",
            "reason": ("refresh requests are internal workflow and are not "
                       "served to the customer audience")}
        return body

    rows = _requests(cur, entity_id)
    body["requests"] = rows
    body["open_request"] = next((r for r in rows if r["is_open"]), None)
    body["requests_state"] = None if rows else {
        "kind": "no_requests",
        "reason": "no refresh has been requested for this client"}
    return body


def refresh_queue(cur, audience: str = "internal", role: str | None = None,
                  within_days: int = 0, limit: int = DEFAULT_LIMIT,
                  as_of: date | None = None) -> dict:
    """What the scheduled synthesis routine reads to learn there is work.

    Two independent lists, deliberately not merged: a client somebody ASKED to
    refresh, and a client whose six months have RUN OUT. They answer different
    questions and a producer treats them differently — the first names a human
    and a reason, the second names only a date.

    Internal only: it names actors and reasons across every client.
    """
    if audience != "internal":
        raise ApiError(403, "audience_forbidden",
                       "the refresh queue is internal workflow and is not "
                       "served to the customer audience")
    limit = max(1, min(int(limit), MAX_LIMIT))
    within_days = max(0, min(int(within_days), 3650))
    as_of = as_of or datetime.now(timezone.utc).date()

    cur.execute(
        f"""SELECT {', '.join('q.' + c for c in _REQUEST_COLS)},
                   d.display_id, d.legal_name, d.request_id, d.assessment_date,
                   d.assessment_date_basis, d.assessment_date_source,
                   d.refresh_due_date
              FROM refresh_requests q
              LEFT JOIN serving_directory d
                     ON d.entity_id = q.entity_id AND d.is_active
             WHERE q.status = ANY(%s)
             ORDER BY q.requested_at ASC, q.id ASC
             LIMIT %s""",
        (list(OPEN_REQUEST_STATUSES), limit))
    requested = []
    for row in cur.fetchall():
        d = dict(zip(_REQUEST_COLS, row[:len(_REQUEST_COLS)]))
        for k in ("entity_id", "observed_run_id", "fulfilled_by_run_id"):
            d[k] = str(d[k]) if d[k] is not None else None
        for k in ("requested_at", "updated_at"):
            d[k] = _iso(d[k])
        tail = row[len(_REQUEST_COLS):]
        d["display_id"], d["entity_name"], d["request_id"] = tail[0], tail[1], tail[2]
        d["cadence"] = cadence_for(tail[3], tail[4], tail[5], tail[6], as_of=as_of)
        requested.append(d)

    cur.execute(
        """SELECT display_id, legal_name, run_id, request_id, run_seq,
                  assessment_date, assessment_date_basis,
                  assessment_date_source, refresh_due_date, composite
             FROM serving_directory
            WHERE is_active AND refresh_due_date IS NOT NULL
              AND refresh_due_date <= %s
            ORDER BY refresh_due_date ASC, display_id ASC
            LIMIT %s""",
        (as_of.fromordinal(as_of.toordinal() + within_days), limit))
    due = []
    for (display_id, name, run_id, request_id, run_seq, adate, basis, source,
         due_date, composite) in cur.fetchall():
        due.append({
            "display_id": display_id, "entity_name": name,
            "run_id": str(run_id), "request_id": request_id,
            "run_seq": run_seq,
            "composite": float(composite) if composite is not None else None,
            "cadence": cadence_for(adate, basis, source, due_date, as_of=as_of),
        })

    # An entity whose assessment date never resolved has no due date and can
    # never appear in `due`. Silence there would read as "nothing is due";
    # it is counted so the routine can say what it could not judge.
    cur.execute(
        """SELECT count(*) FROM serving_directory
            WHERE is_active AND refresh_due_date IS NULL""")
    undatable = cur.fetchone()[0]

    open_ids = {r["display_id"] for r in requested if r["display_id"]}
    return {
        "as_of": _iso(as_of),
        "within_days": within_days,
        "requested": requested,
        "due": due,
        "counts": {
            "requested_open": len(requested),
            "due": len(due),
            "overdue": sum(1 for x in due if x["cadence"]["is_overdue"]),
            "due_and_also_requested": sum(1 for x in due
                                          if x["display_id"] in open_ids),
            "active_runs_with_no_assessment_date": undatable,
        },
        "note": ("`requested` names a human and a reason; `due` names only a "
                 "date. Neither is a queue of work already started — nothing "
                 "in this response has been claimed."),
    }
