"""Shared entity-run resolver.

Closes the "run selector is decorative" QA finding (2026-06-05): every
entity-scoped read endpoint (overview / insights / heatmap / platforms /
context / health) had its own ad-hoc run-resolution snippet that ignored
the `?run=<request_id>` selector the operator picked in ClientBar. The
operator could switch between Run A and Run B in the URL but every page
silently kept rendering the ACTIVE run.

This module centralises the resolution in one place so every endpoint
opts in via a single helper call:

    run = await resolve_entity_run(
        session, display_id, run_request_id=run_query_param,
    )

Resolution matrix (`run_request_id` semantics):

  None                         -> latest ACTIVE run (the default; matches
                                   pre-2026-06-05 silent behaviour)
  None + no ACTIVE             -> latest PENDING_REVIEW; else latest IN_PROGRESS
  REQ-12345678                 -> exact match on runs.request_id for this entity;
                                   404 if no match (operator made a typo or the
                                   run belongs to a different entity)
  Anything else                -> 422 with a clear "expected REQ-{8 hex} or
                                   DMA-ASM-..." message

The returned object exposes `id` (UUID), `request_id` (REQ-...), and
`status` (ACTIVE / PENDING_REVIEW / SUPERSEDED / IN_PROGRESS / etc.).
Callers should ALWAYS surface `run_request_id` in their response so the
frontend can confirm the resolution back to the user.

Resilient against the various DMA structures we ingest:
  - bot-originated runs (request_id = REQ-{8 hex})
  - project-originated runs (request_id = DMA-ASM-{ENTITY}-{YYYYMMDD}-{NNNN})
  - historical_backfill runs (status = SUPERSEDED + data_source =
    DRIVE_BACKFILL)
  - rerun chains (parent_request_id set; the selected run may itself be
    a rerun whose parent has different scoring).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import structlog
from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

# Accept the THREE canonical run-id forms emitted by the DMA pipeline,
# matching `app/services/parsers/run_id.py` exactly:
#   REQ-{8 hex}                          bot-originated (canonical)
#   DMA-ASM-{ENTITY}-{YYYYMMDD}-{NNNN}   project assessment delivery
#   DMA-RES-{ENTITY}-{YYYYMMDD}-{NNNN}   project research delivery (sibling
#                                        of ASM; e.g. AmeriCU's seeded run
#                                        is DMA-RES-AMERICU-20260427-0001).
# Pre-2026-06-05 the RES prefix was missing from this list -- the
# seeded AmeriCU fixture's run id was rejected as 422 invalid in
# `?run=DMA-RES-...` paths.  Also drop the never-emitted `DMA-ASSESS-...`
# variant: the legacy Amalgamated fixture uses it, but real production
# runs only ever produce ASM/RES (per parse_run_id). Keep ASSESS in the
# regex anyway for backward-compat with the existing Amalgamated test
# fixture which writes `DMA-ASSESS-AMAL-...` literally.
_REQUEST_ID_PATTERNS = (
    re.compile(r"^REQ-[0-9A-F]{8}$"),
    re.compile(r"^DMA-(ASM|RES|ASSESS)-[A-Z0-9]+-\d{8}-\d{4}$"),
)


@dataclass(frozen=True)
class ResolvedRun:
    """Minimal projection -- callers do their own joins for run-scoped
    data (subcap_scores, evidence_index, etc.).

    `ccg_catalog_version` is populated when present on the row (most
    run inserts carry it); None for legacy runs without the column
    being set. Heatmap aggregation needs it to pin the catalogue
    version it resolves subcap_ids against.
    """

    id: str
    request_id: str
    status: str
    entity_id: str
    ccg_catalog_version: str | None = None


def _looks_like_request_id(value: str) -> bool:
    return any(p.match(value) for p in _REQUEST_ID_PATTERNS)


def audit_route_composition_safety(app, logger) -> int:
    """Scan every registered route for the Query-sentinel anti-pattern.

    Returns the number of offending handlers (0 = clean). Logs each
    offender as a `route_composition_audit.unsafe_default` warning so
    the operator can see them in Cloud Logging without crashing the
    revision.

    The anti-pattern: an HTTP handler declares
        run: str | None = Query(default=None)
    AND another handler in the same router composes that handler via
    a direct Python call. Python uses the literal `Query(default=None)`
    sentinel as the parameter value, which has no `.strip()` method,
    triggering AttributeError when the resolver tries to validate it.

    Detection: walk app.routes, find every async handler with a `run`
    parameter, check if its default is a `fastapi.params.Query`
    instance. Bare `None` defaults are safe.
    """
    import inspect

    from fastapi import params as fastapi_params

    offenders = 0
    for route in getattr(app, "routes", []):
        endpoint = getattr(route, "endpoint", None)
        path = getattr(route, "path", "")
        if endpoint is None or not callable(endpoint):
            continue
        try:
            sig = inspect.signature(endpoint)
        except (TypeError, ValueError):
            continue
        if "run" not in sig.parameters:
            continue
        default = sig.parameters["run"].default
        if isinstance(default, fastapi_params.Query):
            offenders += 1
            logger.warning(
                "route_composition_audit.unsafe_default",
                path=path,
                handler=getattr(endpoint, "__qualname__", repr(endpoint)),
                default_type=type(default).__name__,
                fix=(
                    "Change `run: str | None = Query(default=None)` to "
                    "`run: str | None = None`. Query() is only required "
                    "for advanced metadata (regex, alias, ge/le, etc.) -- "
                    "plain None is safe under direct Python composition."
                ),
            )
    if offenders == 0:
        logger.info(
            "route_composition_audit.clean",
            scanned=len(getattr(app, "routes", [])),
        )
    else:
        logger.warning(
            "route_composition_audit.summary",
            offenders=offenders,
            recommendation=(
                "fix each offender before next deploy; the runtime "
                "resolver coerces Query sentinels to None defensively, "
                "but the structural fix is to drop the Query() wrapper."
            ),
        )
    return offenders


def _coerce_run_request_id(value: object) -> str | None:
    """Defensive coercion: accept None, str, or anything-else-treated-as-None.

    The 2026-06-05 stage-7 production 500 was caused by a
    `fastapi.params.Query` sentinel landing here when one router
    composed another via direct Python call. The original code did
    `value.strip()` which raised AttributeError on the sentinel
    (Query has no .strip method) -> generic 500 Internal Server Error.

    This coercion makes the resolver structurally tolerant of ANY
    non-string input: a Query sentinel, an int, a UUID, a dict --
    none of them are valid request_ids, so we treat them as "no
    selection" and fall through to the default ACTIVE-run resolution.
    A structured log emits when this happens so we can spot a future
    misuse without crashing prod.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    # Anything else is a programming bug at a route composition site
    # (Query sentinel is the canonical example). Log loudly + coerce
    # to None so the user-facing response stays clean.
    log.warning(
        "run_resolver.non_string_run_request_id_coerced_to_none",
        observed_type=type(value).__name__,
        observed_repr=repr(value)[:120],
    )
    return None


async def maybe_resolve_entity_run(
    session: AsyncSession,
    display_id: str,
    *,
    run_request_id: str | None = None,
    allow_in_progress: bool = False,
) -> ResolvedRun | None:
    """Soft variant of `resolve_entity_run` for endpoints that have a
    no-runs branch (context, health -- they render entity-level data
    even when no run has completed yet).

    Behaviour matches `resolve_entity_run` EXCEPT it returns None
    instead of 404 when the entity has zero runs. Entity-not-found
    and malformed-request_id still raise.
    """
    try:
        return await resolve_entity_run(
            session,
            display_id,
            run_request_id=run_request_id,
            allow_in_progress=allow_in_progress,
        )
    except HTTPException as e:
        # 404 from "entity X has no runs yet" -> None (soft branch).
        # 404 from "entity X not found" -> re-raise (operator typo).
        # 404 from "run YYY not found for entity X" -> re-raise (the
        # operator picked a specific run; honour the strict failure).
        if (
            e.status_code == status.HTTP_404_NOT_FOUND
            and isinstance(e.detail, str)
            and "has no runs yet" in e.detail
        ):
            return None
        raise


async def resolve_entity_run(
    session: AsyncSession,
    display_id: str,
    *,
    run_request_id: str | None = None,
    allow_in_progress: bool = False,
) -> ResolvedRun:
    """Resolve the run for `display_id`.

    See module docstring for semantics. Raises:
      - 404 when the entity doesn't exist
      - 422 when run_request_id is malformed
      - 404 when run_request_id is well-formed but no matching run
      - 404 when no run resolvable at all (entity has zero runs)

    For the soft variant (no-runs returns None), use
    `maybe_resolve_entity_run` above.
    """
    ent = (
        await session.execute(
            text("SELECT id FROM entities WHERE display_id = :did"),
            {"did": display_id},
        )
    ).first()
    if ent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"entity {display_id!r} not found",
        )
    entity_uuid = str(ent.id)

    # Defensive coercion: tolerate Query() sentinels / wrong types so
    # we NEVER 500 here even if a caller violates the str|None contract.
    # The structural guard at startup (app.main) catches the upstream
    # issue; this is the runtime safety net.
    run_request_id = _coerce_run_request_id(run_request_id)

    if run_request_id is not None:
        rrid = run_request_id.strip()
        if not rrid:
            run_request_id = None
        elif not _looks_like_request_id(rrid):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"run={rrid!r} is not a valid request_id; expected "
                    "REQ-XXXXXXXX or DMA-ASM-...-YYYYMMDD-NNNN"
                ),
            )
        else:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT id, request_id, status, ccg_catalog_version
                        FROM runs
                        WHERE entity_id = :eid
                          AND request_id = :rrid
                        LIMIT 1
                        """
                    ),
                    {"eid": entity_uuid, "rrid": rrid},
                )
            ).first()
            if row is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=(
                        f"run {rrid!r} not found for entity {display_id!r}. "
                        "It may belong to a different entity or have been "
                        "deleted; check GET /api/v1/entities/{display_id}/runs."
                    ),
                )
            return ResolvedRun(
                id=str(row.id),
                request_id=row.request_id,
                status=row.status,
                entity_id=entity_uuid,
                ccg_catalog_version=row.ccg_catalog_version,
            )

    # No run_request_id supplied -> fall back to the canonical pick.
    # Priority: ACTIVE -> PENDING_REVIEW -> (IN_PROGRESS if allowed) ->
    # most-recent-of-anything. Keeps historic SUPERSEDED runs visible
    # via explicit selection without making them the default render.
    fallback_statuses: list[str] = ["ACTIVE", "PENDING_REVIEW"]
    if allow_in_progress:
        fallback_statuses.append("IN_PROGRESS")
    placeholders = ", ".join(f":s{i}" for i in range(len(fallback_statuses)))
    params: dict[str, object] = {"eid": entity_uuid}
    for i, s in enumerate(fallback_statuses):
        params[f"s{i}"] = s
    row = (
        await session.execute(
            text(
                f"""
                SELECT id, request_id, status, ccg_catalog_version
                FROM runs
                WHERE entity_id = :eid
                  AND status IN ({placeholders})
                ORDER BY
                    CASE status
                        {' '.join(f"WHEN '{s}' THEN {i}"
                                   for i, s in enumerate(fallback_statuses))}
                        ELSE 99
                    END,
                    completed_at DESC NULLS LAST,
                    created_at DESC
                LIMIT 1
                """
            ),
            params,
        )
    ).first()
    if row is None:
        # Last-resort: pick the most-recent run regardless of status so
        # the operator at least sees SUPERSEDED data instead of a 404
        # when an entity exists but has no live run.
        row = (
            await session.execute(
                text(
                    """
                    SELECT id, request_id, status, ccg_catalog_version
                    FROM runs
                    WHERE entity_id = :eid
                    ORDER BY completed_at DESC NULLS LAST, created_at DESC
                    LIMIT 1
                    """
                ),
                {"eid": entity_uuid},
            )
        ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"entity {display_id!r} has no runs yet",
        )
    return ResolvedRun(
        id=str(row.id),
        request_id=row.request_id,
        status=row.status,
        entity_id=entity_uuid,
        ccg_catalog_version=row.ccg_catalog_version,
    )
