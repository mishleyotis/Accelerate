"""svc_api — walking-skeleton read API.

Serves live build state from the tables svc_api may read (catalogue +
serving tier). This skeleton exists so the production URL is real from
stage 2 onward; stage 4 replaces the internals with the full read API
(SQLAlchemy asyncpg, cursor pagination, ETag/304, Brotli) per TRD §19.
It performs no inference and serves only promoted or catalogue rows —
never staging, never ingested client material. Its only writes are the
charter's two exceptions (alert actions here; annotations when they
land), both into workflow tables behind Idempotency-Key — no endpoint
writes serving content (invariant 2).
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from .alerts import act as alert_act, queue as alert_queue
from .annotations import annotate_insight
from .answers import build_answers, search_answers
from .cadence import cadence_for, entity_cadence, refresh_queue
from .db import close as db_close, connect as db_connect
from .diff import build_diff
from .evidence import fetch as ev_fetch, redact_items as ev_redact
from .identity import ActorError, verified_actor
from .pages import ApiError, build_page, etag_for, resolve_run
from .redaction import normalise_audience
from .subverticals import SCOPE_TAG, scope_to_entity

_connect = db_connect


@asynccontextmanager
async def _lifespan(app):
    yield
    db_close()


app = FastAPI(title="DMA Insights API", lifespan=_lifespan)

# The serving tables the walking skeleton reports on. Counts are computed
# at request time from the tables themselves — never stored (invariant 8).
_PAGE_TABLES = {
    "overview": "overview_scores",
    "heatmap": "heatmap_workbook_scores",
    "insights": "insight_cards",
    "platform": "platform_story",
    "context": "context_timeline",
    "techstack": "techstack_items",
}


def _date_iso(v):
    """A DATE column as an ISO day, or None. Never a sentinel, never today."""
    return v.isoformat() if hasattr(v, "isoformat") else v


@app.get("/healthz")
def healthz():
    return {"ok": True, "service": "dmai-api", "stage": "walking-skeleton"}


"""Pillar display names as shipped in every assessment package's
Pillar_Summary tab (P2 varies by audience wording per sub-vertical; this
is the corpus default, overridden per run once run-scoped naming lands).
The catalogue itself carries no pillar display names."""
_PILLAR_NAMES = {
    "P1": ("Strategy, Governance & Culture", "Strategy"),
    "P2": ("Client Experience", "Client"),
    "P3": ("Operations, Risk & Compliance", "Operations"),
    "P4": ("Data, Analytics & Technology", "Data & Tech"),
}


# The sub-vertical vocabulary, as the Surface Specification names it. The
# serving tier stores the code (SV2), not the label, so the label has to come
# from the contract rather than from a code echoed back at the reader.
_SUBVERTICAL_NAMES = {
    "SV1": "Regional Banks", "SV2": "Credit Unions",
    "SV3": "Commercial Lending", "SV4": "CIB & Capital Markets",
    "SV5": "RIAs & Broker-Dealers", "SV6": "Asset Management",
    "SV7": "Insurance Brokers", "SV8": "Insurance Carriers",
    "SV9": "Farm Credit",
}


@app.get("/v1/catalogue")
def catalogue(entity: str | None = None, run: str | None = None):
    """The capability axis. Pinned to a RUN when one is named.

    It served the CURRENT version to every caller. Two promoted runs are
    pinned to v5.0, which has seventeen categories against v7.0's sixteen, so
    any surface drawing its axis from here dropped P1C5 for those runs
    silently — the killed ESG category, the same one every cross-version diff
    renders NOT_COMPARABLE. A grid whose axis comes from a different version
    than its cells is not a rendering difference; it is a column of scores
    with no header and a header with no column.

    `entity` (or `run`) pins it. Without either, the current version is
    served and `is_pinned` says so, because an unpinned axis is a legitimate
    answer to "what does the catalogue look like now" and an illegitimate one
    to "what does this client's grid mean".
    """
    conn = _connect()
    try:
        cur = conn.cursor()
        version, pinned_to = None, None
        if entity or run:
            cur.execute(
                """SELECT ccg_catalog_version, run_id FROM serving_directory
                    WHERE (%s IS NULL OR display_id = %s)
                      AND (%s IS NULL OR run_id::text = %s)
                    ORDER BY is_active DESC NULLS LAST, promoted_at DESC
                    LIMIT 1""", (entity, entity, run, run))
            row = cur.fetchone()
            if row is None:
                return JSONResponse(
                    {"error": "entity_not_found",
                     "detail": "no promoted run matches that entity or run"},
                    status_code=404)
            version, pinned_to = row[0], str(row[1])
        if not version:
            cur.execute("SELECT version FROM ccg_versions WHERE is_current")
            version = cur.fetchone()[0]
        cur.execute(
            """SELECT category_id, pillar_id, name FROM ccg_categories
                WHERE version = %s ORDER BY category_id""", (version,))
        rows = cur.fetchall()
        # v7.0's capability map puts the ID in its Category column, so the
        # catalogue ships no display names and the loader stored NULL rather
        # than an id masquerading as a name. The names DO exist — every
        # promoted run states them on its ceilings rows — so take the most
        # frequently stated name per category. That is a count over real
        # promoted data, not a guess, and it stops a grid of bare ids.
        cur.execute("""SELECT category_id, category_name, count(*) AS n
                         FROM overview_ceilings
                        WHERE category_name IS NOT NULL
                        GROUP BY category_id, category_name
                        ORDER BY category_id, n DESC, category_name""")
        stated: dict = {}
        for cid, cname, _n in cur.fetchall():
            stated.setdefault(cid, cname)
        categories = [{"id": c, "pillar": p, "name": n or stated.get(c) or c,
                       "name_source": ("catalogue" if n
                                       else ("stated" if stated.get(c) else None)),
                       "weight": None}
                      for c, p, n in rows]
        pillars = [{"id": pid, "name": n, "short": s}
                   for pid, (n, s) in _PILLAR_NAMES.items()]
        return {"version": version, "pillars": pillars,
                "categories": categories,
                # Stated rather than implied: a caller that did not pin has to
                # be able to tell that it did not.
                "is_pinned": pinned_to is not None, "pinned_to_run": pinned_to}
    finally:
        conn.close()


@app.get("/v1/directory")
def directory(audience: str | None = None, role: str | None = None):
    """Promoted entities from the one materialised view the directory is
    allowed to read (invariant 8; 0013). Shaped for the front-end's
    entity rows; anything the serving tier does not carry is null, never
    invented. Empty until the first promote is the correct state.

    The directory is a list of OTHER institutions. It took no audience at
    all and answered every caller with every client's legal name, sub-
    vertical, composite and pillar breakdown — the one response in this API
    where a customer-audience reader would learn about somebody else's
    assessment. There is no redacted form of that; a customer has an entity,
    not a directory, so the audience is refused rather than narrowed."""
    # Default-deny (dma_api.redaction): omitted or unknown resolves to
    # `customer`, the least privileged audience — never to `internal`.
    audience = normalise_audience(audience)
    if audience != "internal":
        return JSONResponse(
            {"error": "audience_forbidden",
             "detail": "the directory lists other institutions and is not "
                       "served to the customer audience"},
            status_code=403)
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT entity_id, display_id, legal_name, sub_vertical, size_tier,
                   run_id, request_id, run_seq, is_active, run_status,
                   composite, scored_cells, completed_at, promoted_at,
                   pillars, open_alerts, assessment_date,
                   assessment_date_basis, assessment_date_source,
                   refresh_due_date
              FROM serving_directory
             ORDER BY entity_id, run_seq DESC""")
        by_entity: dict = {}
        labels: dict = {}
        for (eid, display_id, name, sub_vertical, size_tier, run_id,
             request_id, run_seq, is_active, run_status, composite,
             scored_cells, completed_at, promoted_at, pillars,
             open_alerts, assessment_date, assessment_date_basis,
             assessment_date_source, refresh_due_date) in cur.fetchall():
            key = (sub_vertical or "UNKNOWN").upper().replace(" ", "_")
            labels[key] = _SUBVERTICAL_NAMES.get(key, sub_vertical or "Unknown")
            ent = by_entity.setdefault(str(eid), {
                "id": display_id, "slug": display_id, "name": name,
                "domain": None, "subvertical": key,
                "size_tier": (size_tier or "").upper() or None,
                "hq": None, "status": "ACTIVE",
                "data_source": "DRIVE_PARSE",
                "open_alerts": 0, "runs": [],
            })
            if is_active:
                ent["overall"] = float(composite) if composite is not None else None
                ent["assessment_id"] = request_id
                # The assessment date now comes from the run's own derivation
                # (0031) rather than from `completed_at`, and it travels with
                # the basis that produced it — the directory is where a reader
                # first sees the date, so it is where the qualification has to
                # start. NULL where nothing resolved, never today's date.
                ent["assessment_date"] = _date_iso(assessment_date)
                ent["assessment_date_basis"] = assessment_date_basis
                ent["assessment_date_source"] = assessment_date_source
                ent["assessment_date_is_stated"] = (
                    assessment_date_basis == "STATED")
                ent["cadence"] = cadence_for(
                    assessment_date, assessment_date_basis,
                    assessment_date_source, refresh_due_date)
                ent["open_alerts"] = open_alerts or 0
                ent["pillar_scores"] = {
                    p["pillar_id"]: p.get("score")
                    for p in (pillars or []) if p.get("pillar_id")}
            ent["runs"].append({
                "id": request_id, "run_id": str(run_id),
                "date": _date_iso(assessment_date),
                "assessment_date_basis": assessment_date_basis,
                "completed_at": (completed_at.date().isoformat()
                                 if completed_at else None),
                "status": "ACTIVE" if is_active else run_status,
                "data_source": "DRIVE_PARSE",
                "overall": float(composite) if composite is not None else None,
                "subcap_count": scored_cells,
                "promoted_at": promoted_at.isoformat() if promoted_at else None,
                "refresh_due_date": _date_iso(refresh_due_date),
            })
        return {"entities": list(by_entity.values()),
                "subvertical_labels": labels,
                "active_runs": [], "pending_review": []}
    finally:
        conn.close()


@app.get("/v1/alerts")
def global_alerts(audience: str | None = None, role: str | None = None,
                  status: str = "open", severity: str | None = None,
                  entity: str | None = None, limit: int = 50,
                  cursor: str | None = None):
    """G4 — the corpus-wide thin-evidence queue, one row per alert on an
    active run with its action state joined at read. Cursor-paginated by
    row comparison, mandatory limit (TRD §19); internal audiences only."""
    # Default-deny (dma_api.redaction): omitted or unknown resolves to
    # `customer`, the least privileged audience — never to `internal`.
    audience = normalise_audience(audience)
    conn = _connect()
    try:
        cur = conn.cursor()
        try:
            return alert_queue(cur, audience=audience, role=role,
                               status=status, severity=severity,
                               entity=entity, limit=limit, cursor=cursor)
        except ApiError as e:
            return JSONResponse({"error": e.code, "detail": e.detail},
                                status_code=e.status)
    finally:
        conn.close()


@app.post("/v1/entities/{display_id}/insights/{ic_id}/annotation")
async def insight_annotation(display_id: str, ic_id: str, request: Request,
                             actor: str | None = None,
                             audience: str | None = None,
                             role: str | None = None):
    """The annotation half of invariant 2's two write exceptions: an
    accept/reject verdict on an insight card, anchored fail-closed to a card
    that exists on a promoted run. Idempotency-Key required; workflow tables
    only.

    The actor is the person named by the request's VERIFIED IAP assertion —
    not the `actor` parameter, which is now only compared and never believed
    (dma_api.identity). These rows feed the findings memory and, through it,
    skill refinement: a verdict attributed to a name the caller typed does not
    merely mislabel a row, it teaches."""
    # Default-deny (dma_api.redaction): omitted or unknown resolves to
    # `customer`, the least privileged audience — never to `internal`.
    audience = normalise_audience(audience)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "malformed_body",
                             "detail": "the request body must be a JSON object"},
                            status_code=400)
    try:
        actor_email = verified_actor(request, actor)
    except ActorError as e:
        return JSONResponse({"error": e.code, "detail": e.detail},
                            status_code=e.status)
    key = request.headers.get("idempotency-key")
    conn = _connect()
    try:
        cur = conn.cursor()
        try:
            status_code, payload = annotate_insight(
                cur, display_id, ic_id, body=body, idempotency_key=key,
                actor_email=actor_email, audience=audience, role=role)
        except ApiError as e:
            conn.rollback()
            return JSONResponse({"error": e.code, "detail": e.detail},
                                status_code=e.status)
        conn.commit()
        return JSONResponse(payload, status_code=status_code)
    finally:
        conn.close()


@app.post("/v1/alerts/{alert_id}/actions")
async def alert_actions(alert_id: int, request: Request,
                        actor: str | None = None,
                        audience: str | None = None,
                        role: str | None = None):
    """The second of the API's two write exceptions (TRD §08): alert
    lifecycle — workflow state, not assessment content. Idempotency-Key
    required; a replay returns the ORIGINAL response, a reused key with a
    different body is 409. Writes alert_actions + idempotency_keys only;
    the alert's serving row is never touched (invariant 2).

    `alert_actions.user_id` is a user id, and the only identity this service
    can VERIFY is an email — so the assertion's email is resolved against
    `users` here and the resolved id is what is recorded. The `actor`
    parameter is no longer read: it named a row directly, which is the same
    forgery the annotation route carried."""
    # Default-deny (dma_api.redaction): omitted or unknown resolves to
    # `customer`, the least privileged audience — never to `internal`.
    audience = normalise_audience(audience)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "malformed_body",
                             "detail": "the request body must be a JSON object"},
                            status_code=400)
    try:
        actor_email = verified_actor(request)
    except ActorError as e:
        return JSONResponse({"error": e.code, "detail": e.detail},
                            status_code=e.status)
    key = request.headers.get("idempotency-key")
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE email = %s AND is_active",
                    (actor_email,))
        row = cur.fetchone()
        if row is None:
            # Same refusal annotations.py gives, for the same reason:
            # enrolment is not a write path, and creating the identity inside
            # the write that is checked against it is the check deleted.
            return JSONResponse(
                {"error": "unknown_actor",
                 "detail": "the verified signed-in email resolves to no "
                           "active user; user rows are the auth flow's to "
                           "create"}, status_code=403)
        try:
            status_code, payload = alert_act(
                cur, alert_id, body=body, idempotency_key=key, actor=str(row[0]),
                audience=audience, role=role)
        except ApiError as e:
            conn.rollback()
            return JSONResponse({"error": e.code, "detail": e.detail},
                                status_code=e.status)
        conn.commit()
        return JSONResponse(payload, status_code=status_code)
    finally:
        conn.close()


_SUBCAP_COLS = ("subcap_id", "capability_id", "category_id", "pillar_id",
                "subcap_name", "l3_platform_areas", "l4_features", "score",
                "confidence", "peer_median", "peer_n", "peer_basis",
                "proxy_disclosure", "delta", "linked_evidence_count",
                "is_thin_evidence", "source_cell")


# Declared BEFORE the generic {page} route, like /evidence.
@app.get("/v1/entities/{display_id}/subcaps")
def entity_subcaps(display_id: str, request: Request, response: Response,
                   audience: str | None = None, run: str | None = None,
                   role: str | None = None, history: bool = False):
    """The run's cell grain: every scored subcap, as the workbook stated it.

    Not a promoted section — a grain read, the same shape as the evidence
    store. The heatmap drills to four grains and the platform page names each
    gap's cell; both need this and the serving tier's H4 writer carries pillars
    and categories only. `delta` and `is_thin_evidence` are the base table's
    GENERATED columns: selected here, never recomputed (invariants 8 and 9).
    """
    # Default-deny (dma_api.redaction): omitted or unknown resolves to
    # `customer`, the least privileged audience — never to `internal`.
    audience = normalise_audience(audience)
    conn = _connect()
    try:
        cur = conn.cursor()
        try:
            _entity_id, entity, run_meta, _ = resolve_run(
                cur, display_id, run, history)
        except ApiError as e:
            return JSONResponse({"error": e.code, "detail": e.detail},
                                status_code=e.status)
        cur.execute(
            f"SELECT {', '.join(_SUBCAP_COLS)} FROM serving_subcaps "
            "WHERE run_id = %s ORDER BY subcap_id", (run_meta["run_id"],))
        rows = []
        # A sub-vertical VARIANT cell belonging to somebody else never
        # serves. The assessment workbook carries the whole variant set,
        # so a credit union's run measured (and ingested) insurance-carrier
        # and RIA cells; the ingested tier is read-only once scanned, which
        # makes this a read-time decision. See subverticals.py for the
        # derivation and the codes it deliberately does not treat as
        # foreign. Filtering HERE rather than in the SQL means one
        # vocabulary, shared with the value-chain derivation.
        for r in scope_to_entity(cur.fetchall(), entity.get("sub_vertical"),
                                 key=_SUBCAP_COLS.index("subcap_id")):
            d = dict(zip(_SUBCAP_COLS, r))
            for k in ("score", "peer_median", "delta"):
                d[k] = float(d[k]) if d[k] is not None else None
            if audience == "customer":
                # The proxy disclosure explains an internal peer-basis
                # decision; the customer sees the basis, not the workings.
                d.pop("proxy_disclosure", None)
            rows.append(d)
        tag = etag_for(run_meta, f"{audience}.subcaps.{SCOPE_TAG}")
        if request.headers.get("if-none-match") == tag:
            return Response(status_code=304, headers={"ETag": tag,
                                                      "Cache-Control": "private, max-age=0"})
        response.headers["ETag"] = tag
        response.headers["Cache-Control"] = "private, max-age=0"
        return {"entity": entity, "run": run_meta, "audience": audience,
                "subcaps": rows, "count": len(rows)}
    finally:
        conn.close()


# Declared BEFORE the generic {page} route, like /evidence and /subcaps.
@app.get("/v1/entities/{display_id}/refresh")
def entity_refresh(display_id: str, request: Request, response: Response,
                   audience: str | None = None, run: str | None = None,
                   role: str | None = None, history: bool = False):
    """The client's refresh cadence: the assessment date WITH the basis that
    produced it, the six-month due date, the distance to it measured now, and
    what has been requested.

    Read-only. A refresh request is recorded by the `dmai-refresh` Cloud Run
    Job (the ingest identity), not here — invariant 2 enumerates the API's
    writes as annotations and alert actions, and a refresh request is neither.

    Deliberately NOT ETagged on the run: the body carries a distance measured
    against today, so a tag keyed on the promotion would serve yesterday's
    "due in N weeks" unchanged tomorrow."""
    # Default-deny (dma_api.redaction): omitted or unknown resolves to
    # `customer`, the least privileged audience — never to `internal`.
    audience = normalise_audience(audience)
    conn = _connect()
    try:
        cur = conn.cursor()
        try:
            body = entity_cadence(cur, display_id, audience=audience, run=run,
                                  role=role, allow_history=history)
        except ApiError as e:
            return JSONResponse({"error": e.code, "detail": e.detail},
                                status_code=e.status)
        response.headers["Cache-Control"] = "private, max-age=0"
        return body
    finally:
        conn.close()


# Declared BEFORE the generic {page} route, like /evidence and /subcaps.
@app.get("/v1/entities/{display_id}/diff")
def entity_diff(display_id: str, request: Request, response: Response,
                audience: str | None = None, base: str | None = None,
                target: str | None = None, role: str | None = None,
                limit: int = 2000):
    """Run-to-run movement at the cell grain — the read the version-diff
    surface needs and has never had.

    Both ends are promoted runs; with only one promoted run the response is an
    explicit `no_base_run` state and no cells, because a base run is never
    derived from the target (dma_api.diff)."""
    # Default-deny (dma_api.redaction): omitted or unknown resolves to
    # `customer`, the least privileged audience — never to `internal`.
    audience = normalise_audience(audience)
    conn = _connect()
    try:
        cur = conn.cursor()
        try:
            body = build_diff(cur, display_id, audience=audience, base=base,
                              target=target, role=role, limit=limit)
        except ApiError as e:
            return JSONResponse({"error": e.code, "detail": e.detail},
                                status_code=e.status)
        # Both ends are promoted and immutable, so the pair identifies the
        # body exactly; the run's own promoted_epoch tag would not, because
        # the base can change without the target being re-promoted.
        tag = (f'W/"{body["target"]["run_id"]}.'
               f'{(body.get("base") or {}).get("run_id") or "none"}.{audience}"')
        if request.headers.get("if-none-match") == tag:
            return Response(status_code=304,
                            headers={"ETag": tag,
                                     "Cache-Control": "private, max-age=0"})
        response.headers["ETag"] = tag
        response.headers["Cache-Control"] = "private, max-age=0"
        return body
    finally:
        conn.close()


# Declared BEFORE the generic {page} route, like /evidence and /subcaps.
@app.get("/v1/entities/{display_id}/answers/search")
def entity_answer_search(display_id: str, q: str, request: Request,
                         response: Response, audience: str | None = None,
                         run: str | None = None, role: str | None = None,
                         history: bool = False, limit: int = 5):
    """One question against one run, answered from promoted content only.

    Ranks and selects; composes nothing. The result is either an answer the
    producer wrote, or the run's own passages verbatim under a frame that
    says what they are, or an explicit no-match. No model runs here — the
    ranking is `ts_rank_cd`/pg_trgm in the database, or the same
    deterministic rule in this process when the passage index has not been
    built yet (invariant 1).

    Deliberately NOT ETagged on the run alone: the response varies with the
    question, and a tag that ignored `q` would serve one question's answer
    for another on a 304."""
    # Default-deny (dma_api.redaction): omitted or unknown resolves to
    # `customer`, the least privileged audience — never to `internal`.
    audience = normalise_audience(audience)
    conn = _connect()
    try:
        cur = conn.cursor()
        try:
            body = search_answers(cur, display_id, q, audience=audience,
                                  run=run, role=role, allow_history=history,
                                  limit=limit)
        except ApiError as e:
            return JSONResponse({"error": e.code, "detail": e.detail},
                                status_code=e.status)
        response.headers["Cache-Control"] = "private, max-age=0"
        return body
    finally:
        conn.close()


@app.get("/v1/entities/{display_id}/answers")
def entity_answers(display_id: str, request: Request, response: Response,
                   audience: str | None = None, run: str | None = None,
                   role: str | None = None, history: bool = False,
                   surface: str | None = None):
    """The pre-computed answer set: the questions an AE asks on each surface,
    answered ahead of time from promoted prose with the citations behind it.

    A lookup, not an inference — which is why it can be served on the same
    ETag as the pages it is built from: the answers change exactly when the
    run's promotion does."""
    # Default-deny (dma_api.redaction): omitted or unknown resolves to
    # `customer`, the least privileged audience — never to `internal`.
    audience = normalise_audience(audience)
    conn = _connect()
    try:
        cur = conn.cursor()
        try:
            body = build_answers(cur, display_id, audience=audience, run=run,
                                 role=role, allow_history=history,
                                 surface=surface)
        except ApiError as e:
            return JSONResponse({"error": e.code, "detail": e.detail},
                                status_code=e.status)
        tag = etag_for(body["run"], f"{audience}.answers.{surface or 'all'}")
        if request.headers.get("if-none-match") == tag:
            return Response(status_code=304,
                            headers={"ETag": tag,
                                     "Cache-Control": "private, max-age=0"})
        response.headers["ETag"] = tag
        response.headers["Cache-Control"] = "private, max-age=0"
        return body
    finally:
        conn.close()


# Declared BEFORE the generic {page} route: FastAPI matches in declaration
# order, and "evidence" would otherwise be read as a page name.
@app.get("/v1/entities/{display_id}/evidence")
def entity_evidence(display_id: str, request: Request, response: Response,
                    audience: str | None = None, run: str | None = None,
                    e_ids: str | None = None, role: str | None = None,
                    history: bool = False):
    """The evidence drawer's read path.

    Entity-scoped and fail-closed (invariant 4): an id that belongs to another
    entity comes back under `foreign`, never as a row. `e_ids` is a
    comma-separated filter — the drawer asks for exactly the ids a card cites,
    so the response is the resolution verdict for those ids and nothing else.
    """
    # Default-deny (dma_api.redaction): omitted or unknown resolves to
    # `customer`, the least privileged audience — never to `internal`.
    audience = normalise_audience(audience)
    conn = _connect()
    try:
        cur = conn.cursor()
        try:
            entity_id, entity, run_meta, _ = resolve_run(
                cur, display_id, run, history)
        except ApiError as e:
            return JSONResponse({"error": e.code, "detail": e.detail},
                                status_code=e.status)
        wanted = [x.strip() for x in (e_ids or "").split(",") if x.strip()]
        res = ev_fetch(cur, entity_id, wanted or None,
                       run_id=run_meta["run_id"])
        res["items"] = ev_redact(res["items"], audience)
        tag = etag_for(run_meta, f"{audience}.evidence")
        if request.headers.get("if-none-match") == tag:
            return Response(status_code=304, headers={"ETag": tag,
                                                      "Cache-Control": "private, max-age=0"})
        response.headers["ETag"] = tag
        response.headers["Cache-Control"] = "private, max-age=0"
        return {"entity": entity, "run": run_meta, "audience": audience, **res}
    finally:
        conn.close()


@app.get("/v1/entities/{display_id}/{page}")
def entity_page(display_id: str, page: str, request: Request,
                response: Response, audience: str | None = None,
                run: str | None = None, role: str | None = None,
                history: bool = False):
    """One promoted page for one entity, redacted for the audience.
    ETag is run_id.promoted_epoch.audience; a matching If-None-Match gets
    304 with no body (TRD §19)."""
    # Default-deny (dma_api.redaction): omitted or unknown resolves to
    # `customer`, the least privileged audience — never to `internal`.
    audience = normalise_audience(audience)
    conn = _connect()
    try:
        cur = conn.cursor()
        try:
            body = build_page(cur, page, display_id, audience=audience,
                              run=run, role=role, allow_history=history)
        except ApiError as e:
            return JSONResponse({"error": e.code, "detail": e.detail},
                                status_code=e.status)
        tag = etag_for(body["run"], body["audience"])
        if request.headers.get("if-none-match") == tag:
            return Response(status_code=304, headers={"ETag": tag,
                                                      "Cache-Control": "private, max-age=0"})
        response.headers["ETag"] = tag
        response.headers["Cache-Control"] = "private, max-age=0"
        return body
    finally:
        conn.close()


@app.get("/v1/ops/refresh-queue")
def ops_refresh_queue(audience: str | None = None, role: str | None = None,
                      within_days: int = 0, limit: int = 50):
    """What the scheduled synthesis routine reads to learn there is work.

    Two lists that answer different questions: clients somebody ASKED to
    refresh (a human and a reason), and clients whose six months have RUN OUT
    (a date and nothing else). Neither has been claimed by anything.

    This is the routine's external input — before it, the routine had none: it
    fired every three hours and stopped when the package scan had created
    nothing."""
    # Default-deny (dma_api.redaction): omitted or unknown resolves to
    # `customer`, the least privileged audience — never to `internal`.
    audience = normalise_audience(audience)
    conn = _connect()
    try:
        cur = conn.cursor()
        try:
            return refresh_queue(cur, audience=audience, role=role,
                                 within_days=within_days, limit=limit)
        except ApiError as e:
            return JSONResponse({"error": e.code, "detail": e.detail},
                                status_code=e.status)
    finally:
        conn.close()


@app.get("/v1/ops/enrichment-loop")
def ops_enrichment_loop(limit: int = 10):
    """Is the enrichment loop alive, and what did it last do?

    Owner, 2026-08-15: "confirm that this enrichment loop happens robustly as
    the web app runs." A routine nobody can see is a routine nobody can trust,
    and until this endpoint the only way to answer the question was to read a
    Cloud Run log. This is the answer as data.

    `healthy` is computed here rather than stored, and it is deliberately
    strict: a job that never closed, a job that errored, and a job that scanned
    zero runs are all UNHEALTHY. The last one matters most — a loop that finds
    nothing to look at reports the same numbers as a loop with nothing to do,
    and only one of those is fine.
    """
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("""SELECT id, started_at, finished_at, trigger, runs_scanned,
                              gaps_found, resolved, not_run, failed, error
                         FROM enrichment_jobs
                        ORDER BY started_at DESC LIMIT %s""", (max(1, min(limit, 50)),))
        jobs = [{"id": r[0], "started_at": r[1], "finished_at": r[2],
                 "trigger": r[3], "runs_scanned": r[4], "gaps_found": r[5],
                 "resolved": r[6], "not_run": r[7], "failed": r[8],
                 "error": r[9]} for r in cur.fetchall()]
        last = jobs[0] if jobs else None
        healthy = bool(last and last["finished_at"] and not last["error"]
                       and last["runs_scanned"] > 0)
        why = ("no enrichment job has ever run" if not last
               else "the last job never finished" if not last["finished_at"]
               else f"the last job errored: {last['error']}" if last["error"]
               else "the last job scanned zero runs, which is a failure to "
                    "look rather than a clean result" if not last["runs_scanned"]
               else None)
        # The open worklist, computed from the latest attempt per field so a
        # gap closed last hour stops being reported this hour.
        cur.execute("""SELECT DISTINCT ON (run_id, field)
                              field, status, value, reason
                         FROM enrichment_attempts
                        ORDER BY run_id, field, attempted_at DESC""")
        rows = cur.fetchall()
        return {"healthy": healthy, "unhealthy_because": why,
                "last_job": last, "jobs": jobs,
                "open_gaps": sum(1 for r in rows if r[1] != "RESOLVED"),
                "resolved_awaiting_producer": sum(1 for r in rows if r[1] == "RESOLVED")}
    finally:
        conn.close()


@app.get("/v1/ops/import-scans")
def import_scans(limit: int = 20):
    """Recent package-scan executions — the REAL job history the admin
    Import & jobs page renders (counts come from the scan ledger itself;
    nothing here is narrative content)."""
    limit = max(1, min(int(limit), 100))
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT id, started_at, finished_at, status, folders_seen,
                      files_seen, files_new, files_changed, runs_created
                 FROM import_scans ORDER BY id DESC LIMIT %s""", (limit,))
        scans = [{
            "id": r[0],
            "started_at": r[1].isoformat() if r[1] else None,
            "finished_at": r[2].isoformat() if r[2] else None,
            "status": r[3],
            "folders_seen": r[4], "files_seen": r[5],
            "files_new": r[6], "files_changed": r[7],
            "runs_created": r[8],
        } for r in cur.fetchall()]
        return {"scans": scans}
    finally:
        conn.close()


@app.get("/v1/meta")
def meta():
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("""SELECT version, cell_count, category_count, is_current
                         FROM ccg_versions ORDER BY version""")
        catalogues = [{"version": v, "cells": c, "categories": g,
                       "current": bool(cur_flag)}
                      for v, c, g, cur_flag in cur.fetchall()]
        pages = {}
        promoted = set()
        for page, table in _PAGE_TABLES.items():
            cur.execute(f"SELECT count(*), count(DISTINCT run_id) FROM {table}")
            rows, runs = cur.fetchone()
            pages[page] = {"rows": rows, "runs": runs}
            if runs:
                cur.execute(f"SELECT DISTINCT run_id FROM {table}")
                promoted.update(str(r[0]) for r in cur.fetchall())
        return {"catalogues": catalogues,
                "serving": {"pages": pages, "promoted_runs": len(promoted)},
                "note": ("empty serving tables are correct until the first "
                         "run promotes — content enters only through the "
                         "connector")}
    finally:
        conn.close()
