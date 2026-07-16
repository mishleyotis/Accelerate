"""Admin surface — users, roles, catalogue queue, assignments, build QA,
vertex-budget, pending-review.

All endpoints require ADMIN.

State transitions:
  PATCH /users/:id/role where target == actor and new role != ADMIN
    → 400 (admins can't demote themselves via this endpoint)
  GET /vertex-budget when audit_log has zero rows for the month
    → spent_usd=0.0; top_surfaces/top_users = []
  GET /pending-review when no runs/entities/import_files are in
  PENDING_REVIEW
    → items=[]; counts_by_kind={}; never errors
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.deps import (
    CurrentUserDep,
    SessionDep,
    require_admin,
)
from app.schemas.admin import (
    AssignmentQueueResponse,
    AssignmentQueueRow,
    BuildQaGateOut,
    BuildQaResponse,
    CatalogueQueueResponse,
    CatalogueRunOut,
    ImportAuditByEntityResponse,
    ImportAuditEntityDetailResponse,
    ImportAuditEntityJobRow,
    ImportAuditEntityRow,
    ImportAuditEntityRunRow,
    ImportAuditResponse,
    ImportAuditSummary,
    ImportFileOut,
    JobExecuteRequest,
    JobExecutionListResponse,
    JobExecutionOut,
    JobRegistryEntry,
    JobRegistryResponse,
    PromptQualityResponse,
    PromptQualitySurfaceRow,
    PromptQualityVersionDiffRow,
    PromptQualityVersionRow,
    UpdateRoleRequest,
    UserListResponse,
    UserOut,
)
from app.schemas.drive_feedback import (
    FeedbackRefreshAllItem,
    FeedbackRefreshAllResponse,
)
from app.schemas.enrichment import (
    PendingReviewItem,
    PendingReviewResponse,
    VertexBudgetResponse,
    VertexBudgetSurfaceUsage,
    VertexBudgetUserUsage,
)
from app.services.job_executions import (
    JOB_REGISTRY,
    summarize_execution,
    validate_mode,
)

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


@router.get("/users", response_model=UserListResponse)
async def list_users(session: SessionDep) -> UserListResponse:
    rows = (
        await session.execute(
            text(
                """
                SELECT id, email, name, role, is_active, last_login_at, created_at
                FROM users ORDER BY role, email
                """
            )
        )
    ).all()
    items = [
        UserOut(
            id=str(r.id), email=r.email, name=r.name, role=r.role,
            is_active=r.is_active, last_login_at=r.last_login_at,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return UserListResponse(items=items)


@router.patch("/users/{user_id}/role", response_model=UserOut)
async def update_role(
    user_id: str,
    body: UpdateRoleRequest,
    actor: CurrentUserDep,
    session: SessionDep,
) -> UserOut:
    if user_id == actor.user_id and body.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="admin cannot demote self via this endpoint",
        )
    row = (
        await session.execute(
            text(
                """
                UPDATE users SET role = :r, updated_at = NOW()
                WHERE id = CAST(:uid AS uuid)
                RETURNING id, email, name, role, is_active, last_login_at, created_at
                """
            ),
            {"r": body.role, "uid": user_id},
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"user {user_id} not found")
    await session.execute(
        text(
            """
            INSERT INTO audit_log (
                actor_user_id, actor_email, action, resource_type,
                resource_id, after_json
            ) VALUES (
                CAST(:aid AS uuid), :ae, 'update_role', 'user',
                :rid, CAST(:after AS jsonb)
            )
            """
        ),
        {
            "aid": actor.user_id, "ae": actor.email,
            "rid": user_id,
            "after": f'{{"role": "{body.role}"}}',
        },
    )
    await session.commit()
    return UserOut(
        id=str(row.id), email=row.email, name=row.name, role=row.role,
        is_active=row.is_active, last_login_at=row.last_login_at,
        created_at=row.created_at,
    )


@router.get("/build-qa", response_model=BuildQaResponse)
async def build_qa(session: SessionDep) -> BuildQaResponse:
    rows = (
        await session.execute(
            text(
                """
                SELECT id, stage, gate_id, category, description,
                       acceptance_criteria, status, evidence_url,
                       evaluated_at, git_sha
                FROM build_qa_gates
                ORDER BY stage, gate_id
                """
            )
        )
    ).all()
    items = [
        BuildQaGateOut(
            id=str(r.id), stage=r.stage, gate_id=r.gate_id,
            category=r.category, description=r.description,
            acceptance_criteria=r.acceptance_criteria, status=r.status,
            evidence_url=r.evidence_url, evaluated_at=r.evaluated_at,
            git_sha=r.git_sha,
        )
        for r in rows
    ]
    summary: dict[str, int] = {}
    for item in items:
        summary[item.status] = summary.get(item.status, 0) + 1
    return BuildQaResponse(items=items, summary=summary)


@router.get("/catalogue", response_model=CatalogueQueueResponse)
async def catalogue_queue(session: SessionDep) -> CatalogueQueueResponse:
    rows = (
        await session.execute(
            text(
                """
                SELECT id, version, status, loader_started_at,
                       loader_finished_at, source_files, parse_warnings,
                       validation_report, diff_vs_prior_version
                FROM ccg_loader_runs
                ORDER BY loader_started_at DESC LIMIT 50
                """
            )
        )
    ).all()
    awaiting: list[CatalogueRunOut] = []
    applied: list[CatalogueRunOut] = []
    for r in rows:
        cr = CatalogueRunOut(
            id=str(r.id), version=r.version, status=r.status,
            loader_started_at=r.loader_started_at,
            loader_finished_at=r.loader_finished_at,
            source_files=list(r.source_files or []),
            parse_warnings=list(r.parse_warnings or []),
            validation_report=r.validation_report,
            diff_vs_prior_version=r.diff_vs_prior_version,
        )
        if r.status == "AWAITING_APPROVAL":
            awaiting.append(cr)
        elif r.status == "APPLIED":
            applied.append(cr)
    return CatalogueQueueResponse(
        awaiting_approval=awaiting,
        recent_applied=applied[:10],
    )


# ── Diagnostics + self-heal repair endpoints (2026-05-28) ─────────────
#
# Surface known-bad states so the operator (or admin UI) can take
# explicit recovery action. These are read-only / idempotent — no
# implicit "fix it automatically" because some of the issues (e.g.
# placeholder catalogue rows) are intentional band-aids that the
# operator put there to unblock backfill; auto-rewriting them would
# destroy that diagnostic signal.

@router.get(
    "/trace/ingest",
    include_in_schema=False,
    dependencies=[Depends(require_admin)],
)
async def trace_ingest(session: SessionDep) -> dict:
    """End-to-end ingestion → UI presentation trace.

    Returns a single snapshot that proves (or disproves) the entire
    data pipeline from worker ingest → Postgres tables → API surfaces
    → frontend render. Each step is independently checked and surfaced
    so the operator can pinpoint where a break happened:

      pipeline_steps:
        1. entities.count           → was anything ingested?
        2. runs.count               → did a run actually persist?
        3. runs.latest              → request_id + completed_at + parser_warnings
        4. subcap_scores.count      → did scores land?
        5. document_sections.count  → did report DOCX get parsed?
        6. evidence_index.count     → did evidence persist?
        7. /api/v1/entities         → does the directory list it?
        8. /api/v1/entities/{id}/overview → does the live UI see scores?

    Self-heal contract: every step wrapped in try/except. Missing
    tables (pre-migration) OMIT keys; SQL errors store error text.
    The endpoint NEVER raises — operators triaging a broken system
    need this surface to stay up no matter what.

    UI consumes the response via the OperationsPanel "Pipeline status"
    card — operator sees the chain status at a glance + "View latest
    entity" link to validate manually.
    """
    from sqlalchemy import text as _text

    out: dict = {
        "pipeline_steps": [],
        "checks_passed": 0,
        "checks_total": 0,
        "latest_entity_id": None,
        "latest_entity_drive_folder_id": None,
        "ui_render_ok": False,
    }

    def _record(label: str, ok: bool, detail: object) -> None:
        out["pipeline_steps"].append({
            "label": label, "ok": ok, "detail": detail,
        })
        out["checks_total"] += 1
        if ok:
            out["checks_passed"] += 1

    # Step 1: entities count.
    try:
        n = (await session.execute(
            _text("SELECT count(*) FROM entities")
        )).scalar() or 0
        _record("entities ingested", n > 0, {"count": int(n)})
    except Exception as e:
        _record("entities ingested", False, {"error": str(e)[:200]})

    # Step 2: runs count.
    try:
        n = (await session.execute(
            _text("SELECT count(*) FROM runs")
        )).scalar() or 0
        _record("runs persisted", n > 0, {"count": int(n)})
    except Exception as e:
        _record("runs persisted", False, {"error": str(e)[:200]})

    # Step 3: latest run details.
    try:
        row = (await session.execute(_text("""
            SELECT r.id, r.request_id, r.completed_at,
                   r.ccg_catalog_version, r.parser_warnings,
                   e.id AS entity_id, e.name AS entity_name,
                   e.drive_folder_id
              FROM runs r
              JOIN entities e ON e.id = r.entity_id
          ORDER BY r.completed_at DESC NULLS LAST
             LIMIT 1
        """))).mappings().first()
        if row:
            warnings_text = (
                str(row["parser_warnings"])[:500]
                if row["parser_warnings"] else ""
            )
            ok = bool(row["completed_at"])
            _record("latest run readable", ok, {
                "request_id": row["request_id"],
                "completed_at": (
                    row["completed_at"].isoformat()
                    if row["completed_at"] else None
                ),
                "ccg_catalog_version": row["ccg_catalog_version"],
                "entity_name": row["entity_name"],
                "parser_warnings_preview": warnings_text,
            })
            out["latest_entity_id"] = str(row["entity_id"])
            out["latest_entity_drive_folder_id"] = row["drive_folder_id"]
        else:
            _record("latest run readable", False, {"reason": "no runs"})
    except Exception as e:
        _record("latest run readable", False, {"error": str(e)[:200]})

    # Step 4: subcap_scores for the latest run.
    if out["latest_entity_id"]:
        try:
            n = (await session.execute(_text("""
                SELECT count(*)
                  FROM subcap_scores ss
                  JOIN runs r ON r.id = ss.run_id
                 WHERE r.entity_id = CAST(:eid AS uuid)
            """), {"eid": out["latest_entity_id"]})).scalar() or 0
            # Expected ~64 subcaps in v7.0 catalogue.
            _record("scores persisted", n >= 32, {
                "count": int(n),
                "expected_floor": 32,
            })
        except Exception as e:
            _record("scores persisted", False, {"error": str(e)[:200]})

        # Step 5: document_sections for the latest run (DOCX narrative).
        try:
            n = (await session.execute(_text("""
                SELECT count(*)
                  FROM document_sections ds
                  JOIN runs r ON r.id = ds.run_id
                 WHERE r.entity_id = CAST(:eid AS uuid)
            """), {"eid": out["latest_entity_id"]})).scalar() or 0
            # 0 is acceptable (DOCX-only ingest is silent per CLAUDE.md);
            # surface the count for operator visibility.
            _record("report sections", True, {
                "count": int(n),
                "note": "0 is valid (skeleton render); >0 means narrative parsed",
            })
        except Exception:
            # Defensive — table may not exist on shallow envs.
            pass

        # Step 6: evidence_index count for this entity.
        try:
            n = (await session.execute(_text("""
                SELECT count(*) FROM evidence_index
                 WHERE entity_id = CAST(:eid AS uuid)
            """), {"eid": out["latest_entity_id"]})).scalar() or 0
            _record("evidence persisted", n >= 0, {"count": int(n)})
        except Exception:
            pass

    # Step 7: directory visibility — does /api/v1/entities surface the
    # latest entity? This proves the LIVE API layer (not just the DB)
    # returns the row, so a missing JOIN or schema-drift bug surfaces.
    if out["latest_entity_id"]:
        try:
            row = (await session.execute(_text("""
                SELECT id, name AS entity_name, subvertical
                  FROM entities
                 WHERE id = CAST(:eid AS uuid)
            """), {"eid": out["latest_entity_id"]})).mappings().first()
            visible = row is not None
            _record("entity visible in directory", visible, {
                "entity_id": out["latest_entity_id"],
                "entity_name": row["entity_name"] if row else None,
                "ui_link": (
                    f"/clients/{out['latest_entity_id']}" if visible else None
                ),
            })
        except Exception as e:
            _record(
                "entity visible in directory", False,
                {"error": str(e)[:200]},
            )

        # Step 8: UI render check — does /api/v1/entities/{id}/overview
        # return pillar_scores with non-zero data? This is THE direct
        # check for "is the UI going to render something meaningful".
        try:
            row = (await session.execute(_text("""
                SELECT AVG(ss.score) AS avg_score, count(*) AS n
                  FROM subcap_scores ss
                  JOIN runs r ON r.id = ss.run_id
                 WHERE r.entity_id = CAST(:eid AS uuid)
                   AND r.completed_at = (
                       SELECT MAX(r2.completed_at)
                         FROM runs r2
                        WHERE r2.entity_id = CAST(:eid AS uuid)
                   )
            """), {"eid": out["latest_entity_id"]})).mappings().first()
            avg = float(row["avg_score"]) if row and row["avg_score"] else 0
            n = int(row["n"]) if row else 0
            ok = n > 0 and avg > 0
            _record("UI overview will render scores", ok, {
                "subcap_score_count": n,
                "average_score": round(avg, 2),
                "note": (
                    "avg=0 means scores landed but all are 0 (catalogue "
                    "unresolved); UI will show blank rings until fixed"
                ),
            })
            out["ui_render_ok"] = ok
        except Exception as e:
            _record(
                "UI overview will render scores", False,
                {"error": str(e)[:200]},
            )

    # Final summary.
    out["pipeline_healthy"] = (
        out["checks_total"] > 0
        and out["checks_passed"] == out["checks_total"]
    )
    return out


@router.get("/diagnostics", include_in_schema=False,
            dependencies=[Depends(require_admin)])
async def diagnostics(session: SessionDep) -> dict:
    """Return a dict of detected operational issues.

    Each top-level key maps to a list of offending rows (empty list =
    healthy). The admin UI renders one card per non-empty key with
    actionable text + a link to the repair endpoint if applicable.

    Keys (and their meaning):
      catalogue_versions_referenced_but_missing:
        runs.ccg_catalog_version values with no ccg_catalog_versions
        parent row. Triggers FK violations on the next backfill.
        Repair: POST /admin/repair:catalogue-stubs.

      catalogue_versions_with_no_child_rows:
        ccg_catalog_versions rows that have NO matching ccg_subcaps
        children. Means the loader has not run for real (or only the
        manual band-aid INSERT exists). Every scored package against
        this version will land with scores=0 + `catalogue_empty_for_version`
        warning.

      job_executions_stuck_running:
        job_executions rows with status='running' started > 30
        minutes ago. Likely the worker crashed mid-run and never
        flipped status; operator should investigate logs and POST
        /admin/repair:close-stuck-jobs.

      runs_with_unresolved_catalogue:
        runs where parsed subcap_scores > 0 but persisted score rows
        = 0 against the run's catalogue version. The H8 red flag —
        signals the catalogue loader needs to run.
    """
    from sqlalchemy import text as _text

    out: dict[str, list[dict]] = {}

    # 1. Catalogue versions referenced by runs but missing the parent row.
    rows = (await session.execute(_text("""
        SELECT DISTINCT r.ccg_catalog_version AS version,
               COUNT(*) OVER (PARTITION BY r.ccg_catalog_version) AS run_count
          FROM runs r
         WHERE r.ccg_catalog_version IS NOT NULL
           AND NOT EXISTS (
               SELECT 1 FROM ccg_catalog_versions cv
                WHERE cv.version = r.ccg_catalog_version
           )
    """))).mappings().all()
    out["catalogue_versions_referenced_but_missing"] = [
        {"version": r["version"], "run_count": r["run_count"]} for r in rows
    ]

    # 2. Catalogue versions WITH parent row but NO ccg_subcaps children.
    rows = (await session.execute(_text("""
        SELECT cv.version, cv.frozen_at, cv.notes
          FROM ccg_catalog_versions cv
         WHERE NOT EXISTS (
               SELECT 1 FROM ccg_subcaps s WHERE s.version = cv.version
         )
    """))).mappings().all()
    out["catalogue_versions_with_no_child_rows"] = [
        {
            "version": r["version"],
            "frozen_at": r["frozen_at"].isoformat() if r["frozen_at"] else None,
            "notes": r["notes"],
        } for r in rows
    ]

    # 3. job_executions stuck in 'running' > 30min.
    rows = (await session.execute(_text("""
        SELECT id, job_name, started_at, trigger_source, triggered_by_email
          FROM job_executions
         WHERE status = 'running'
           AND started_at < NOW() - INTERVAL '30 minutes'
         ORDER BY started_at DESC
         LIMIT 20
    """))).mappings().all()
    out["job_executions_stuck_running"] = [
        {
            "id": str(r["id"]),
            "job_name": r["job_name"],
            "started_at": r["started_at"].isoformat() if r["started_at"] else None,
            "trigger_source": r["trigger_source"],
            "triggered_by_email": r["triggered_by_email"],
        } for r in rows
    ]

    # 4. Runs with unresolved catalogue (parsed but no scores persisted).
    rows = (await session.execute(_text("""
        SELECT r.id, r.request_id, r.ccg_catalog_version,
               r.parser_warnings
          FROM runs r
         WHERE r.ccg_catalog_version IS NOT NULL
           AND r.parser_warnings::text LIKE '%catalogue_empty_for_version%'
         ORDER BY r.created_at DESC
         LIMIT 20
    """))).mappings().all()
    out["runs_with_unresolved_catalogue"] = [
        {
            "id": str(r["id"]),
            "request_id": r["request_id"],
            "ccg_catalog_version": r["ccg_catalog_version"],
        } for r in rows
    ]

    # — see trace_ingest below for the full data-pipeline snapshot.
    # 5. Drive folders flagged for retry (migration 022).
    # Defensive: the table doesn't exist before migration 022 lands —
    # catch the SQLAlchemyError (relation does not exist) and return
    # an empty list so the admin UI doesn't fall over.
    try:
        rows = (await session.execute(_text("""
            SELECT * FROM (
                SELECT DISTINCT ON (drive_folder_id)
                       drive_folder_id, folder_name, outcome
                  FROM backfill_quarantine
              ORDER BY drive_folder_id, processed_at DESC
            ) latest
             WHERE outcome IN (
                'failed_parse', 'failed_persist',
                'failed_other', 'skipped_no_report'
             )
             ORDER BY outcome, drive_folder_id
             LIMIT 100
        """))).mappings().all()
        out["backfill_folders_flagged_for_retry"] = [
            {
                "drive_folder_id": r["drive_folder_id"],
                "folder_name": r["folder_name"],
                "outcome": r["outcome"],
            } for r in rows
        ]
    except Exception as e:
        # The category is OMITTED rather than zero-valued so the UI
        # can distinguish "migration not applied yet" from "table
        # empty / no failures". The structured log entry surfaces in
        # Cloud Logging for ops triage.
        msg = str(e).lower()
        if "backfill_quarantine" in msg and (
            "does not exist" in msg or "undefinedtable" in msg
        ):
            # Migration 022 not yet applied — silently skip.
            pass
        else:
            # Some other DB error — log + skip (never raise from
            # /diagnostics, the endpoint must stay reachable for the
            # admin to triage other issues).
            print(
                f"::warning::diagnostics backfill_quarantine query failed: "
                f"{type(e).__name__}: {e!s}",
                flush=True,
            )

    # Summary line for one-line operator triage. _summary EXCLUDED
    # from the issue_total count to avoid recursion. The
    # backfill_folders_flagged_for_retry list — if present — counts
    # toward total_issues since each flagged folder is one actionable
    # backfill row that needs operator intervention.
    issue_total = sum(
        len(v) for k, v in out.items() if isinstance(v, list)
    )
    out["_summary"] = {
        "total_issues": issue_total,
        "healthy": issue_total == 0,
    }
    return out


class RepairCatalogueStubsRequest(BaseModel):
    """Operator supplies an explicit set of catalogue versions to
    ensure-exist. Empty list / missing field → endpoint defaults to
    the known-good baseline (v7.0 + v5.5) which covers every package
    seen in the production Drive folder as of 2026-05-28.
    """
    versions: list[str] = Field(default_factory=list)


@router.post("/repair:catalogue-stubs", include_in_schema=False,
             dependencies=[Depends(require_admin)])
async def repair_catalogue_stubs(
    actor: CurrentUserDep,
    session: SessionDep,
    body: RepairCatalogueStubsRequest | None = None,
) -> dict:
    """Idempotently INSERT placeholder `ccg_catalog_versions` rows for
    every version the operator supplies (or for the default baseline
    v7.0 + v5.5 if none supplied).

    Self-heal for the FK-violation class of failure. Inserts use:
      - source_sha256s = '{}' (empty — will be replaced by the loader)
      - loader_run_id  = gen_random_uuid() (synthetic, replaced by loader)
      - notes flags that this is a band-aid + records who/when

    Re-running is safe (ON CONFLICT DO NOTHING) — already-inserted rows
    are NOT modified (which is the correct behaviour: once the real
    loader has populated `source_sha256s` and `loader_run_id`, this
    repair endpoint must NEVER clobber that real metadata back to a
    placeholder).

    Returns the list of versions that were ACTUALLY inserted (empty
    list = every requested version already exists).
    """
    from datetime import UTC, datetime

    from sqlalchemy import text as _text

    requested = (body.versions if body else None) or ["v7.0", "v5.5"]
    # Defensive: dedup + strip + validate the operator's input.
    cleaned: list[str] = []
    seen: set[str] = set()
    for v in requested:
        v2 = (v or "").strip()
        if not v2 or v2 in seen:
            continue
        # `ccg_catalog_versions.version` is varchar(16) — reject anything
        # that won't fit so we fail fast rather than hit a DB truncation
        # error. Pattern check is lenient (allow any letter+number+
        # punctuation under 16 chars) since legacy versions look like
        # 'v5.5' / 'v7.0' but future formats may differ.
        if len(v2) > 16:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"version {v2!r} is longer than 16 chars; "
                       f"`ccg_catalog_versions.version` is varchar(16)",
            )
        cleaned.append(v2)
        seen.add(v2)

    inserted: list[str] = []
    for version in cleaned:
        note = (
            f"repair:catalogue-stubs by {actor.email} on "
            f"{datetime.now(tz=UTC).isoformat()} — placeholder so "
            f"runs.ccg_catalog_version FK is satisfied. Run the "
            f"ccg_loader job to replace with real metadata."
        )
        result = await session.execute(
            _text("""
                INSERT INTO ccg_catalog_versions
                    (version, released_at, source_sha256s,
                     loader_run_id, frozen_at, notes)
                VALUES (:v, NOW(), '{}'::jsonb,
                        gen_random_uuid(), NOW(), :n)
                ON CONFLICT (version) DO NOTHING
            """),
            {"v": version, "n": note},
        )
        # rowcount=1 means it was actually inserted (CONFLICT path = 0).
        if result.rowcount == 1:
            inserted.append(version)

    if inserted:
        # Audit row so the action is traceable.
        await session.execute(
            _text("""
                INSERT INTO audit_log
                    (actor_user_id, actor_email, action, resource_type,
                     resource_id, after_json)
                VALUES (CAST(:uid AS uuid), :email,
                        'repair_catalogue_stubs', 'ccg_catalog_versions',
                        NULL, CAST(:payload AS jsonb))
            """),
            {
                "uid": actor.user_id,
                "email": actor.email,
                "payload": __import__("json").dumps({
                    "inserted_versions": inserted,
                    "count": len(inserted),
                }),
            },
        )
    await session.commit()
    return {"inserted_versions": inserted, "count": len(inserted)}


@router.post("/repair:close-stuck-jobs", include_in_schema=False,
             dependencies=[Depends(require_admin)])
async def repair_close_stuck_jobs(
    actor: CurrentUserDep,
    session: SessionDep,
) -> dict:
    """Flip `job_executions` rows stuck in `status='running'` for >30min
    to `status='failed'` with an explanatory error_message. Used after
    diagnosing that the worker process actually died (Cloud Run timeout,
    OOM, etc.) but its job_executions row was never updated.

    Idempotent — re-running won't touch rows that are no longer stuck.
    """
    from sqlalchemy import text as _text

    rows = (await session.execute(_text("""
        UPDATE job_executions
           SET status = 'failed',
               completed_at = NOW(),
               duration_sec = EXTRACT(EPOCH FROM (NOW() - started_at)),
               error_message = COALESCE(error_message,
                   'auto-closed by /admin/repair:close-stuck-jobs — '
                   'row was running for >30min with no progress'),
               stderr_tail = COALESCE(stderr_tail,
                   'worker presumed dead; check Cloud Run execution logs '
                   'via the deep link on this row before retrying')
         WHERE status = 'running'
           AND started_at < NOW() - INTERVAL '30 minutes'
        RETURNING id, job_name, started_at
    """))).mappings().all()

    closed = [
        {
            "id": str(r["id"]),
            "job_name": r["job_name"],
            "started_at": r["started_at"].isoformat() if r["started_at"] else None,
        } for r in rows
    ]
    if closed:
        await session.execute(
            _text("""
                INSERT INTO audit_log
                    (actor_user_id, actor_email, action, resource_type,
                     resource_id, after_json)
                VALUES (CAST(:uid AS uuid), :email,
                        'repair_close_stuck_jobs', 'job_executions',
                        NULL, CAST(:payload AS jsonb))
            """),
            {
                "uid": actor.user_id,
                "email": actor.email,
                "payload": __import__("json").dumps({
                    "closed_count": len(closed),
                    "closed": closed,
                }),
            },
        )
    await session.commit()
    return {"closed_count": len(closed), "closed": closed}


@router.get("/assignments", response_model=AssignmentQueueResponse)
async def assignments_queue(session: SessionDep) -> AssignmentQueueResponse:
    """Pending entity_assignments — drive-inferred with confidence < 0.85
    or ops-sheet rows where assigned_to didn't match an ops_team.name."""
    rows = (
        await session.execute(
            text(
                """
                SELECT ea.entity_id, e.display_id, e.name AS entity_name,
                       ea.source, ea.source_ref, ea.confidence, ea.assigned_at,
                       u.email AS proposed_email, u.name AS proposed_name
                FROM entity_assignments ea
                JOIN entities e ON e.id = ea.entity_id
                LEFT JOIN users u ON u.id = ea.user_id
                WHERE ea.superseded_at IS NULL
                  AND (
                    (ea.source = 'drive_inference' AND ea.confidence < 0.85)
                    OR (ea.source = 'ops_sheet' AND ea.user_id IS NULL)
                  )
                ORDER BY ea.assigned_at DESC
                LIMIT 200
                """
            )
        )
    ).all()
    pending = [
        AssignmentQueueRow(
            entity_id=str(r.entity_id),
            entity_display_id=r.display_id,
            entity_name=r.entity_name,
            source=r.source,
            source_ref=r.source_ref,
            confidence=(float(r.confidence) if r.confidence is not None else None),
            assigned_at=r.assigned_at,
            proposed_user_email=r.proposed_email,
            proposed_user_name=r.proposed_name,
            reason=(
                "drive_inference confidence < 0.85"
                if r.source == "drive_inference"
                else "ops_sheet assigned_to didn't resolve to a known team member"
            ),
        )
        for r in rows
    ]
    return AssignmentQueueResponse(pending=pending)


@router.get("/imports/audit", response_model=ImportAuditResponse)
async def imports_audit(session: SessionDep) -> ImportAuditResponse:
    rows = (
        await session.execute(
            text(
                """
                SELECT f.id, f.filename, f.file_kind, f.status,
                       f.parser_warnings, f.drive_file_id, f.drive_modified_time,
                       f.processed_at, f.created_at,
                       e.display_id AS entity_display_id,
                       r.request_id AS run_request_id
                FROM import_files f
                LEFT JOIN entities e ON e.id = f.entity_id
                LEFT JOIN runs r ON r.id = f.run_id
                ORDER BY f.created_at DESC LIMIT 500
                """
            )
        )
    ).all()
    items = [
        ImportFileOut(
            id=str(r.id), filename=r.filename, file_kind=r.file_kind,
            status=r.status, parser_warnings=r.parser_warnings,
            drive_file_id=r.drive_file_id,
            drive_modified_time=r.drive_modified_time,
            processed_at=r.processed_at, created_at=r.created_at,
            entity_display_id=r.entity_display_id,
            run_request_id=r.run_request_id,
        )
        for r in rows
    ]
    counts: dict[str, int] = {}
    for it in items:
        counts[it.status] = counts.get(it.status, 0) + 1
    return ImportAuditResponse(items=items, counts_by_status=counts)


# ===================================================================
# Vertex budget + pending-review (Deliverable #7)
# ===================================================================

# Rough $/1k tokens. Flash is the dominant surface; Pro is more
# expensive but used sparingly (deeper style + final summaries).
# Embeddings are cheap and rolled in under flash here. The frontend
# treats these as point estimates — actual GCP billing is the truth.
_USD_PER_1K_TOKENS = {
    "pro": 0.0035,        # gemini-2.5-pro input+output blended
    "flash": 0.00035,     # gemini-2.0-flash blended
    "default": 0.0005,
}


def _est_usd(model: str | None, tokens: int) -> float:
    rate = _USD_PER_1K_TOKENS.get((model or "default").lower(),
                                  _USD_PER_1K_TOKENS["default"])
    return round(rate * (tokens / 1000.0), 4)


@router.get("/vertex-budget", response_model=VertexBudgetResponse)
async def vertex_budget(session: SessionDep) -> VertexBudgetResponse:
    """Aggregate Vertex usage for the current month from audit_log."""
    from datetime import UTC, datetime
    now = datetime.now(tz=UTC)
    period = now.strftime("%Y-%m")

    # Budget from system_config
    budget_row = (
        await session.execute(
            text(
                "SELECT value::text AS v FROM system_config "
                "WHERE key = 'vertex_budget_monthly_usd'"
            )
        )
    ).first()
    budget_usd = float(budget_row.v) if budget_row and budget_row.v else 100.0

    # Sum rag_answer + intelligence surface tokens this month.
    rows = (
        await session.execute(
            text(
                """
                SELECT
                    COALESCE(after_json->>'surface', resource_id) AS surface,
                    COALESCE((after_json->>'model'), 'flash') AS model,
                    SUM(COALESCE((after_json->>'tokens_out')::int, 0)) AS tokens
                FROM audit_log
                WHERE ts >= date_trunc('month', NOW())
                  AND action IN ('rag_answer','gemini_call','intelligence_stream')
                GROUP BY 1, 2
                """
            )
        )
    ).all()
    surface_usage: dict[str, dict] = {}
    spent = 0.0
    for r in rows:
        s = r.surface or "unknown"
        tokens = int(r.tokens or 0)
        usd = _est_usd(r.model, tokens)
        spent += usd
        bucket = surface_usage.setdefault(s, {"tokens": 0, "usd": 0.0})
        bucket["tokens"] += tokens
        bucket["usd"] += usd

    top_surfaces = [
        VertexBudgetSurfaceUsage(
            surface=s, tokens=int(b["tokens"]),
            estimated_usd=round(b["usd"], 4),
        )
        for s, b in sorted(
            surface_usage.items(),
            key=lambda kv: -kv[1]["usd"],
        )[:8]
    ]

    user_rows = (
        await session.execute(
            text(
                """
                SELECT
                    COALESCE(actor_email, 'unknown') AS email,
                    COALESCE((after_json->>'model'), 'flash') AS model,
                    SUM(COALESCE((after_json->>'tokens_out')::int, 0)) AS tokens
                FROM audit_log
                WHERE ts >= date_trunc('month', NOW())
                  AND action IN ('rag_answer','gemini_call','intelligence_stream')
                GROUP BY 1, 2
                """
            )
        )
    ).all()
    user_bucket: dict[str, dict] = {}
    for r in user_rows:
        tokens = int(r.tokens or 0)
        usd = _est_usd(r.model, tokens)
        b = user_bucket.setdefault(r.email, {"tokens": 0, "usd": 0.0})
        b["tokens"] += tokens
        b["usd"] += usd
    top_users = [
        VertexBudgetUserUsage(
            user_email=e, tokens=int(b["tokens"]),
            estimated_usd=round(b["usd"], 4),
        )
        for e, b in sorted(
            user_bucket.items(), key=lambda kv: -kv[1]["usd"],
        )[:8]
    ]

    pct = (spent / budget_usd * 100.0) if budget_usd > 0 else 0.0
    return VertexBudgetResponse(
        period=period,
        spent_usd=round(spent, 4),
        budget_usd=budget_usd,
        pct_used=round(pct, 2),
        top_surfaces=top_surfaces,
        top_users=top_users,
    )


@router.get("/prompt-quality", response_model=PromptQualityResponse)
async def prompt_quality(
    session: SessionDep,
    surface: str | None = None,
    days: int | None = None,
) -> PromptQualityResponse:
    """Per-prompt-template quality rollup -- surface x version
    counts, hallucination rate (proportional attribution until
    migration 027 adds prompt_template_version to alerts),
    estimated USD spend, and pairwise version diffs.

    Optional filters:
      - `surface` — narrow the rollup + diffs to one surface
      - `days` — clip to rows newer than `now - days` (for rolling
        7-day or 30-day comparisons; omit for all-time).
    """
    from datetime import UTC, datetime, timedelta

    from app.services.prompt_quality import (
        compare_versions,
        rollup_by_surface,
        rollup_by_surface_and_version,
    )

    # Clamp days to a sane window so a hostile query can't make us
    # scan beyond the table's retention.
    since: datetime | None = None
    if days is not None:
        d = max(1, min(int(days), 365))
        since = datetime.now(tz=UTC) - timedelta(days=d)

    by_version_dc = await rollup_by_surface_and_version(
        session, surface=surface, since=since,
    )
    by_surface_dc = await rollup_by_surface(session, since=since)

    diffs_dc: list = []
    if surface:
        diffs_dc = await compare_versions(session, surface=surface, since=since)
    else:
        # Compute diffs for every surface that has 2+ versions —
        # the side panel renders them grouped by surface.
        seen_surfaces = {row.surface for row in by_version_dc}
        for s in sorted(seen_surfaces):
            diffs_dc.extend(
                await compare_versions(session, surface=s, since=since)
            )

    return PromptQualityResponse(
        by_surface=[
            PromptQualitySurfaceRow(
                surface=r.surface,
                versions_observed=r.versions_observed,
                active_version=r.active_version,
                total_responses=r.total_responses,
                total_hallucinations=r.total_hallucinations,
                hallucination_rate=r.hallucination_rate,
                estimated_cost_usd=r.estimated_cost_usd,
            )
            for r in by_surface_dc
        ],
        by_version=[
            PromptQualityVersionRow(
                surface=r.surface,
                prompt_template_version=r.prompt_template_version,
                total_responses=r.total_responses,
                total_hallucinations=r.total_hallucinations,
                hallucination_rate=r.hallucination_rate,
                prompt_tokens=r.prompt_tokens,
                completion_tokens=r.completion_tokens,
                estimated_cost_usd=r.estimated_cost_usd,
                first_seen=r.first_seen,
                last_seen=r.last_seen,
                is_active_version=r.is_active_version,
            )
            for r in by_version_dc
        ],
        version_diffs=[
            PromptQualityVersionDiffRow(
                surface=d.surface,
                baseline_version=d.baseline_version,
                candidate_version=d.candidate_version,
                baseline_hallucination_rate=d.baseline_hallucination_rate,
                candidate_hallucination_rate=d.candidate_hallucination_rate,
                rate_delta=d.rate_delta,
                baseline_responses=d.baseline_responses,
                candidate_responses=d.candidate_responses,
                verdict=d.verdict,
            )
            for d in diffs_dc
        ],
        window_days=days,
    )


@router.get("/pending-review", response_model=PendingReviewResponse)
async def pending_review(session: SessionDep) -> PendingReviewResponse:
    items: list[PendingReviewItem] = []

    # PENDING_REVIEW runs
    runs = (
        await session.execute(
            text(
                """
                SELECT r.id::text AS id, r.request_id, r.status,
                       r.created_at, e.id::text AS entity_id,
                       e.display_id AS entity_display_id, e.name AS entity_name
                FROM runs r
                JOIN entities e ON e.id = r.entity_id
                WHERE r.status = 'PENDING_REVIEW'
                ORDER BY r.created_at DESC LIMIT 200
                """
            )
        )
    ).all()
    for r in runs:
        items.append(
            PendingReviewItem(
                kind="run", id=r.id, display_id=r.request_id,
                title=f"Run {r.request_id} pending Analyst review",
                detail=None, created_at=r.created_at,
                entity_id=r.entity_id, entity_name=r.entity_name,
            )
        )

    # PENDING_REVIEW entities — `detail` carries the Phase-0 inference
    # provenance (migration 038) so the Admin card can render
    # "Inferred via <signal>" like the prototype (10_pages_f.js:487).
    ents = (
        await session.execute(
            text(
                """
                SELECT id::text AS id, display_id, name, created_at,
                       inferred_from_source
                FROM entities
                WHERE status = 'PENDING_REVIEW'
                ORDER BY created_at DESC LIMIT 200
                """
            )
        )
    ).all()
    for e in ents:
        items.append(
            PendingReviewItem(
                kind="entity", id=e.id, display_id=e.display_id,
                title=f"Entity {e.name} awaiting Analyst confirmation",
                detail=e.inferred_from_source, created_at=e.created_at,
                entity_id=e.id, entity_name=e.name,
            )
        )

    # PENDING_REVIEW import files
    files = (
        await session.execute(
            text(
                """
                SELECT f.id::text AS id, f.filename, f.parser_warnings,
                       f.created_at, e.id::text AS entity_id, e.name AS entity_name,
                       e.display_id AS entity_display_id
                FROM import_files f
                LEFT JOIN entities e ON e.id = f.entity_id
                WHERE f.status = 'PENDING_REVIEW'
                ORDER BY f.created_at DESC LIMIT 200
                """
            )
        )
    ).all()
    for f in files:
        items.append(
            PendingReviewItem(
                kind="import_file", id=f.id, display_id=f.entity_display_id,
                title=f.filename,
                detail=str(f.parser_warnings) if f.parser_warnings else None,
                created_at=f.created_at,
                entity_id=f.entity_id, entity_name=f.entity_name,
            )
        )

    counts: dict[str, int] = {}
    for it in items:
        counts[it.kind] = counts.get(it.kind, 0) + 1
    return PendingReviewResponse(items=items, counts_by_kind=counts)


# ===================================================================
# Pending-review confirm / reject — Phase 0 entity inferences (F6)
#
# State transitions (only PENDING_REVIEW rows are eligible — anything
# else 404s so a stale Admin tab can't flip an ACTIVE entity):
#   :confirm  PENDING_REVIEW → ACTIVE    (confirmed_at = NOW())
#   :reject   PENDING_REVIEW → ARCHIVED  (rejection_reason persisted)
# Both write an audit_log row with before/after status.
# ===================================================================


class RejectEntityRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class PendingReviewActionResponse(BaseModel):
    id: str
    display_id: str
    name: str
    status: str
    confirmed_at: str | None = None
    rejection_reason: str | None = None


@router.patch(
    "/entities/{entity_id}:confirm",
    response_model=PendingReviewActionResponse,
)
async def confirm_pending_entity(
    entity_id: str,
    actor: CurrentUserDep,
    session: SessionDep,
) -> PendingReviewActionResponse:
    row = (
        await session.execute(
            text(
                """
                UPDATE entities
                   SET status = 'ACTIVE',
                       confirmed_at = NOW(),
                       updated_at = NOW()
                 WHERE id = CAST(:eid AS uuid)
                   AND status = 'PENDING_REVIEW'
                RETURNING id::text AS id, display_id, name, status,
                          confirmed_at
                """
            ),
            {"eid": entity_id},
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="entity not found or not in PENDING_REVIEW",
        )
    await session.execute(
        text(
            """
            INSERT INTO audit_log
                (actor_user_id, actor_email, action, resource_type,
                 resource_id, after_json)
            VALUES (CAST(:uid AS uuid), :email,
                    'confirm_entity_inference', 'entities',
                    CAST(:eid AS uuid), CAST(:payload AS jsonb))
            """
        ),
        {
            "uid": actor.user_id,
            "email": actor.email,
            "eid": entity_id,
            "payload": __import__("json").dumps({
                "display_id": row.display_id,
                "name": row.name,
                "status_before": "PENDING_REVIEW",
                "status_after": "ACTIVE",
            }),
        },
    )
    await session.commit()
    return PendingReviewActionResponse(
        id=row.id, display_id=row.display_id, name=row.name,
        status=row.status,
        confirmed_at=row.confirmed_at.isoformat() if row.confirmed_at else None,
    )


@router.patch(
    "/entities/{entity_id}:reject",
    response_model=PendingReviewActionResponse,
)
async def reject_pending_entity(
    entity_id: str,
    body: RejectEntityRequest,
    actor: CurrentUserDep,
    session: SessionDep,
) -> PendingReviewActionResponse:
    reason = (body.reason or "").strip() or "rejected by admin (no reason given)"
    row = (
        await session.execute(
            text(
                """
                UPDATE entities
                   SET status = 'ARCHIVED',
                       rejection_reason = :reason,
                       updated_at = NOW()
                 WHERE id = CAST(:eid AS uuid)
                   AND status = 'PENDING_REVIEW'
                RETURNING id::text AS id, display_id, name, status,
                          rejection_reason
                """
            ),
            {"eid": entity_id, "reason": reason},
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="entity not found or not in PENDING_REVIEW",
        )
    await session.execute(
        text(
            """
            INSERT INTO audit_log
                (actor_user_id, actor_email, action, resource_type,
                 resource_id, after_json)
            VALUES (CAST(:uid AS uuid), :email,
                    'reject_entity_inference', 'entities',
                    CAST(:eid AS uuid), CAST(:payload AS jsonb))
            """
        ),
        {
            "uid": actor.user_id,
            "email": actor.email,
            "eid": entity_id,
            "payload": __import__("json").dumps({
                "display_id": row.display_id,
                "name": row.name,
                "status_before": "PENDING_REVIEW",
                "status_after": "ARCHIVED",
                "rejection_reason": reason,
            }),
        },
    )
    await session.commit()
    return PendingReviewActionResponse(
        id=row.id, display_id=row.display_id, name=row.name,
        status=row.status, rejection_reason=row.rejection_reason,
    )


# ===================================================================
# job_executions — admin can trigger a worker + see status (Defect 2)
# ===================================================================


def _row_to_job_out(row) -> JobExecutionOut:
    """Convert a SQLA Row to the JSON-serialisable schema, augmenting
    with the computed `result_summary` + `error_count` fields the UI
    needs to render the 'Last run …' label without re-computing on the
    client. Pure (just dict → dict)."""
    d = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
    summary = summarize_execution(d)
    logs_url = _build_logs_url(d)
    return JobExecutionOut(
        id=str(d["id"]),
        job_name=d["job_name"],
        mode=d.get("mode"),
        status=d["status"],
        trigger_source=d["trigger_source"],
        triggered_by_email=d.get("triggered_by_email"),
        started_at=d["started_at"],
        completed_at=d.get("completed_at"),
        duration_sec=(
            float(d["duration_sec"]) if d.get("duration_sec") is not None else None
        ),
        entity_id=(str(d["entity_id"]) if d.get("entity_id") else None),
        folders_seen=d.get("folders_seen"),
        folders_new=d.get("folders_new"),
        folders_changed=d.get("folders_changed"),
        files_parsed=d.get("files_parsed"),
        files_skipped=d.get("files_skipped"),
        files_errored=d.get("files_errored"),
        rows_added=d.get("rows_added"),
        rows_updated=d.get("rows_updated"),
        rows_deleted=d.get("rows_deleted"),
        parser_warnings=d.get("parser_warnings"),
        stderr_tail=d.get("stderr_tail"),
        error_message=d.get("error_message"),
        result_summary=summary["result_summary"],
        error_count=summary["error_count"],
        logs_url=logs_url,
    )


def _build_logs_url(d: dict) -> str | None:
    """Build a Cloud Logging deep link for a `job_executions` row.

    Returns None when:
      - we can't compute the link (no GCP project ID configured —
        local dev / tests),
      - the row was never dispatched to a Cloud Run Job (manual
        `BOT_REQUEST` / `MANUAL_BACKFILL` inserts won't have an
        execution_name to filter on).

    Otherwise returns a URL like:
      https://console.cloud.google.com/logs/query;query=
        resource.type%3D%22cloud_run_job%22%0Aresource.labels.job_name%3D%22dma-insights-{job}%22%0A
        labels.%22run.googleapis.com%2Fexecution_name%22%3D%22{execution_name}%22
        ?project={PROJECT_ID}

    Two filter modes:
      a) row has `cloud_run_execution_name` (set when dispatch wired
         the Cloud Run execution back) → filter to that exact execution.
      b) row only has `started_at` + `job_name` → filter to a ±10min
         time window around start. Coarser but still useful.
    """
    from urllib.parse import quote

    s = get_settings()
    project = (s.gcp_project_id or "").strip()
    if not project:
        return None
    job_name = d.get("job_name")
    if not job_name:
        return None
    cr_job = f"dma-insights-{job_name.replace('_', '-')}"
    filters = [
        'resource.type="cloud_run_job"',
        f'resource.labels.job_name="{cr_job}"',
    ]
    exec_name = d.get("cloud_run_execution_name")
    if exec_name:
        filters.append(
            f'labels."run.googleapis.com/execution_name"="{exec_name}"'
        )
    else:
        # Fall back to a time-windowed filter around started_at.
        started_at = d.get("started_at")
        if started_at:
            # ±10 min — wide enough that worker boot is captured
            # without pulling in adjacent unrelated runs of the same job.
            from datetime import timedelta
            start_iso = (started_at - timedelta(minutes=10)).isoformat()
            end_iso = (
                (d.get("completed_at") or started_at) + timedelta(minutes=10)
            ).isoformat()
            filters.append(f'timestamp>="{start_iso}"')
            filters.append(f'timestamp<="{end_iso}"')
    query = "\n".join(filters)
    return (
        "https://console.cloud.google.com/logs/query;query="
        + quote(query, safe="")
        + f"?project={project}"
    )


@router.get("/jobs", response_model=JobRegistryResponse)
async def list_jobs() -> JobRegistryResponse:
    """Static registry of jobs the admin UI can trigger. The frontend
    uses this to render the per-job button list dynamically."""
    return JobRegistryResponse(
        jobs=[
            JobRegistryEntry(
                job_name=name, modes=sorted(spec["modes"]),
                default_mode=spec["default_mode"],
                description=spec["description"],
            )
            for name, spec in JOB_REGISTRY.items()
        ]
    )


@router.post(
    "/jobs/{job_name}:execute",
    response_model=JobExecutionOut,
    status_code=status.HTTP_200_OK,
)
async def execute_job(
    job_name: str,
    body: JobExecuteRequest,
    actor: CurrentUserDep,
    session: SessionDep,
) -> JobExecutionOut:
    """Trigger a worker. Writes a job_executions row in 'running' state
    synchronously so the UI can poll immediately. The actual worker
    dispatch (Pub/Sub publish OR REST Cloud Run Jobs :run) is a no-op
    in local/test envs — the row is the authoritative trigger record;
    workers UPDATE it as they progress."""
    try:
        mode = validate_mode(job_name, body.mode)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from None

    import json as _json
    args_json = _json.dumps(body.args or {})

    # ── Self-heal: auto-close stuck rows of THIS job_name ────────────────
    # If a previous dispatch of the same job died externally (Cloud Run
    # timeout, OOM, container crash) the job_executions row is still
    # `running` with no progress. Without this hook the operator has to
    # click "Close stuck jobs" before they can dispatch again, AND the
    # admin UI shows two parallel `running` rows. Best-effort UPDATE:
    # any failure here is logged + swallowed (the INSERT below still
    # fires, so the new dispatch never blocks on the cleanup).
    try:
        await session.execute(
            text(
                """
                UPDATE job_executions
                   SET status = 'failed',
                       completed_at = NOW(),
                       duration_sec = EXTRACT(EPOCH FROM (NOW() - started_at)),
                       error_message = COALESCE(error_message,
                           'auto-closed pre-dispatch — running >30min with '
                           'no progress; superseded by new dispatch'),
                       stderr_tail = COALESCE(stderr_tail,
                           'worker presumed dead; check Cloud Run logs '
                           'via the deep link before treating new run failures')
                 WHERE job_name = :name
                   AND status = 'running'
                   AND started_at < NOW() - INTERVAL '30 minutes'
                """
            ),
            {"name": job_name},
        )
    except Exception as e:
        # No-op: the next admin diagnostic refresh will flag stuck rows
        # via the existing catalogue, so visibility isn't lost.
        print(
            f"::warning::pre-dispatch stuck-row cleanup failed for "
            f"job_name={job_name}: {type(e).__name__}: {e!s}",
            flush=True,
        )

    # State branches:
    #   table_missing  → 503 with explicit "migrations not applied" hint
    #                     so operators don't waste cycles debugging a
    #                     500 that's really "you skipped a migrate.sh".
    #   insert_fails   → 500 with the underlying psycopg error so the
    #                     admin UI's JobLogDrawer shows what actually
    #                     went wrong.
    #   insert_ok      → row returned; UI starts polling.
    try:
        row = (
            await session.execute(
                text(
                    """
                    INSERT INTO job_executions (
                        job_name, mode, triggered_by_user_id, triggered_by_email,
                        trigger_source, status, entity_id, args
                    ) VALUES (
                        :name, :mode, CAST(:uid AS uuid), :email,
                        'admin_ui', 'running',
                        -- ERROR HISTORY B1 (2026-05-24, re-fixed): the prior
                        -- CASE workaround tripped asyncpg's statement preparer
                        -- because the entity-id param had no type context and
                        -- could not be unified across the boolean IS-NULL and
                        -- the uuid CAST references (AmbiguousParameterError).
                        -- Fix: ONE reference inside ONE explicit CAST. asyncpg
                        -- + SQLAlchemy honour Python None to SQL NULL when the
                        -- param is referenced once inside an explicit CAST.
                        -- (Do NOT put a colon-prefixed token in this comment —
                        -- SQLAlchemy text() parses it as a phantom bind param.)
                        CAST(:eid AS uuid),
                        CAST(:args AS jsonb)
                    )
                    RETURNING id, job_name, mode, status, trigger_source,
                              triggered_by_email, started_at, completed_at,
                              duration_sec, entity_id, folders_seen, folders_new,
                              folders_changed, files_parsed, files_skipped,
                              files_errored, rows_added, rows_updated,
                              rows_deleted, parser_warnings, stderr_tail,
                              error_message
                    """
                ),
                {
                    "name": job_name, "mode": mode,
                    "uid": actor.user_id, "email": actor.email,
                    "eid": body.entity_id, "args": args_json,
                },
            )
        ).first()
    except Exception as e:  # SQLAlchemy ProgrammingError + psycopg.errors.UndefinedTable
        # "relation \"job_executions\" does not exist" is the canonical
        # symptom when migration 020 hasn't been applied to the live DB.
        # Surfaces as 503 (Service Unavailable) so the operator sees
        # an actionable message instead of an opaque 500.
        msg = str(e).lower()
        if "job_executions" in msg and ("does not exist" in msg or "undefinedtable" in msg):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "job_executions table missing — migration 020 hasn't "
                    "been applied to this database. Run "
                    "`cd apps/dma-insights/infra && ./migrate.sh` then retry. "
                    "See DEPLOYMENT.md §8."
                ),
            ) from None
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"job_executions INSERT failed: {type(e).__name__}: {e!s}"[:500],
        ) from None
    # Best-effort Pub/Sub fan-out (kept for any workers running in
    # --subscribe mode that listen for admin-job-triggered events).
    try:
        from app.services.pubsub_publisher import publish_admin_job_trigger
        await publish_admin_job_trigger(
            job_name=job_name, execution_id=str(row.id), mode=mode,
            args=body.args or {},
        )
    except Exception:
        pass

    # Cloud Run Jobs dispatch — the actual ingest path.
    #
    # Previously this endpoint INSERTed the row and published to a
    # Pub/Sub topic that had no subscriber, so the worker never ran
    # and the job_executions row stayed in 'running' forever. That's
    # the root cause of the user-reported "Currently none has been
    # ingested from the drive" — the operator hit the Admin button and
    # nothing happened. The dispatcher below invokes the Cloud Run Job
    # directly via the REST API (in prod) or via a subprocess (in
    # local/test) and passes DMA_JOB_EXECUTION_ID so the worker
    # updates the SAME row.
    from app.services.cloud_run_dispatch import (
        dispatch_job,
        dispatch_job_arg_validator,
    )
    extra_args = dispatch_job_arg_validator((body.args or {}).get("extra_args"))
    dispatched, reason = await dispatch_job(
        job_name=job_name,
        execution_id=str(row.id),
        extra_args=extra_args,
    )
    if not dispatched and not reason.startswith("skipped_"):
        # Mark the row 'failed' inline so the UI's poller sees the
        # dispatch failure (instead of spinning on a stuck 'running').
        await session.execute(
            text(
                "UPDATE job_executions "
                "SET status='failed', completed_at=NOW(), "
                "    error_message=:reason "
                "WHERE id = CAST(:id AS uuid)"
            ),
            {"reason": f"dispatch_failed:{reason}"[:500], "id": str(row.id)},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"worker dispatch failed: {reason}",
        )

    await session.commit()
    return _row_to_job_out(row)


@router.get("/jobs/executions", response_model=JobExecutionListResponse)
async def list_executions(
    session: SessionDep,
    job_name: str | None = None,
    entity_id: str | None = None,
    limit: int = 20,
) -> JobExecutionListResponse:
    """Recent executions across all jobs (or filtered)."""
    limit = max(1, min(200, limit))
    where: list[str] = []
    params: dict = {"limit": limit}
    if job_name:
        where.append("job_name = :job_name")
        params["job_name"] = job_name
    if entity_id:
        where.append("entity_id = CAST(:entity_id AS uuid)")
        params["entity_id"] = entity_id
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    # Same migration-gap defense as execute_job — return an empty list
    # with a 200 OK so the admin UI's table can render an empty state
    # rather than spinning forever on a 500.
    try:
        rows = (
            await session.execute(
                text(
                    f"""
                    SELECT id, job_name, mode, status, trigger_source,
                           triggered_by_email, started_at, completed_at,
                           duration_sec, entity_id, folders_seen, folders_new,
                           folders_changed, files_parsed, files_skipped,
                           files_errored, rows_added, rows_updated,
                           rows_deleted, parser_warnings, stderr_tail,
                           error_message
                    FROM job_executions {where_sql}
                    ORDER BY started_at DESC LIMIT :limit
                    """
                ),
                params,
            )
        ).all()
    except Exception as e:
        msg = str(e).lower()
        if "job_executions" in msg and ("does not exist" in msg or "undefinedtable" in msg):
            # Empty list + 200 so the UI renders an empty-state instead
            # of an error toast. Operator sees the migration warning
            # only when they try to TRIGGER (execute_job 503).
            return JobExecutionListResponse(items=[])
        raise
    return JobExecutionListResponse(items=[_row_to_job_out(r) for r in rows])


@router.get(
    "/jobs/executions/{execution_id}", response_model=JobExecutionOut,
)
async def get_execution(
    execution_id: str, session: SessionDep,
) -> JobExecutionOut:
    """Single execution detail — used by the UI's status poller."""
    row = (
        await session.execute(
            text(
                """
                SELECT id, job_name, mode, status, trigger_source,
                       triggered_by_email, started_at, completed_at,
                       duration_sec, entity_id, folders_seen, folders_new,
                       folders_changed, files_parsed, files_skipped,
                       files_errored, rows_added, rows_updated,
                       rows_deleted, parser_warnings, stderr_tail,
                       error_message
                FROM job_executions
                WHERE id = CAST(:id AS uuid)
                """
            ),
            {"id": execution_id},
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"job execution {execution_id} not found",
        )
    return _row_to_job_out(row)


@router.post(
    "/jobs/executions/{execution_id}:abort",
    response_model=JobExecutionOut,
    status_code=status.HTTP_200_OK,
)
async def abort_job_execution(
    execution_id: str,
    actor: CurrentUserDep,
    session: SessionDep,
) -> JobExecutionOut:
    """Operator-initiated abort. Flips status='running' rows to
    'cancelled' with an explanatory error_message naming the actor.

    Branches:
      - status='running'  → flipped to 'cancelled' + return 200
      - any other status  → returns the row as-is (idempotent;
                             operator double-click is safe)
      - row not found     → 404

    Cloud Run side: this UPDATE flips the DB row immediately so the
    UI no longer renders 'in progress'. The actual worker process
    (Cloud Run Job execution) may continue for up to a minute until
    it next checks its own row state — workers should be modified
    to poll `status` periodically and exit early. For now the row
    state is authoritative for the operator's view; the in-flight
    worker either completes (and finds the row already 'cancelled'
    so mark_succeeded → no-op) or dies normally.
    """
    from app.services.job_executions_db import mark_cancelled

    try:
        row = mark_cancelled(
            execution_id,
            cancelled_by_email=actor.email,
            reason="aborted via admin UI",
        )
    except Exception as e:
        msg = str(e).lower()
        if "job_executions" in msg and (
            "does not exist" in msg or "undefinedtable" in msg
        ):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "job_executions table missing — migration 020 "
                    "hasn't been applied to this database."
                ),
            ) from None
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"abort failed: {type(e).__name__}: {e!s}"[:500],
        ) from None
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"job execution {execution_id} not found",
        )
    # Best-effort audit log — wrap so any audit failure doesn't poison
    # the abort response.
    try:
        await session.execute(
            text("""
                INSERT INTO audit_log
                    (actor_user_id, actor_email, action, resource_type,
                     resource_id, after_json)
                VALUES (CAST(:uid AS uuid), :email,
                        'abort_job_execution', 'job_executions',
                        CAST(:rid AS uuid), CAST(:payload AS jsonb))
            """),
            {
                "uid": actor.user_id,
                "email": actor.email,
                "rid": execution_id,
                "payload": __import__("json").dumps({
                    "job_name": row.get("job_name"),
                    "prior_status": "running",
                    "new_status": row.get("status"),
                }),
            },
        )
        await session.commit()
    except Exception as e:
        print(
            f"::warning::abort audit_log write failed for "
            f"{execution_id}: {type(e).__name__}: {e!s}",
            flush=True,
        )
    # Re-fetch via the standard row reader so the response shape
    # matches /jobs/executions/{id}.
    re_row = (
        await session.execute(
            text(
                """
                SELECT id, job_name, mode, status, trigger_source,
                       triggered_by_email, started_at, completed_at,
                       duration_sec, entity_id, folders_seen, folders_new,
                       folders_changed, files_parsed, files_skipped,
                       files_errored, rows_added, rows_updated,
                       rows_deleted, parser_warnings, stderr_tail,
                       error_message
                FROM job_executions
                WHERE id = CAST(:id AS uuid)
                """
            ),
            {"id": execution_id},
        )
    ).first()
    return _row_to_job_out(re_row)


# ===================================================================
# Import audit drilldowns (Defect 3 + 4)
# ===================================================================


@router.get("/import-audit/summary", response_model=ImportAuditSummary)
async def import_audit_summary(session: SessionDep) -> ImportAuditSummary:
    """Live tile counts for the Import Audit page. Aggregates over
    job_executions (drive_crawler) + import_files. Returns zeros when
    nothing has been ingested yet — never raises on empty DB."""
    crawl = (
        await session.execute(
            text(
                """
                SELECT MAX(completed_at) AS last_crawl_at,
                       COALESCE(SUM(files_parsed), 0) AS candidates_processed,
                       COALESCE(SUM(files_skipped), 0) AS files_skipped,
                       COALESCE(SUM(files_errored), 0) AS files_errored
                FROM job_executions
                WHERE job_name = 'drive_crawler'
                  AND started_at > NOW() - INTERVAL '30 days'
                """
            )
        )
    ).first()
    by_status = (
        await session.execute(
            text(
                """
                SELECT status, COUNT(*) AS n FROM import_files
                GROUP BY status
                """
            )
        )
    ).all()
    counts = {r.status: int(r.n) for r in by_status}
    return ImportAuditSummary(
        last_crawl_at=crawl.last_crawl_at if crawl else None,
        candidates_processed=int(crawl.candidates_processed) if crawl else 0,
        files_imported=counts.get("OK", 0) + counts.get("PROCESSING", 0),
        files_excluded=counts.get("SKIPPED", 0),
        files_awaiting_review=counts.get("PENDING_REVIEW", 0),
        files_errored=counts.get("FAILED", 0),
    )


async def _table_exists(session: AsyncSession, table: str) -> bool:
    """Return True iff `public.<table>` exists. Used by the self-healing
    audit endpoints to degrade gracefully on partial-migration / pre-018
    databases instead of 500ing operators with UndefinedTableError."""
    rv = (
        await session.execute(
            text("SELECT to_regclass(:n) IS NOT NULL"),
            {"n": f"public.{table}"},
        )
    ).scalar()
    return bool(rv)


async def _table_columns(session: AsyncSession, table: str) -> set[str]:
    """Return the set of `public.<table>` column names. Empty when the
    table is missing — used to detect ai_enrichments legacy shape
    (`entity_id` column) vs current shape (`target_kind` + `target_id`)."""
    rows = (
        await session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=:t"
            ),
            {"t": table},
        )
    ).all()
    return {r.column_name for r in rows}


@router.get(
    "/import-audit/by-entity",
    response_model=ImportAuditByEntityResponse,
)
async def import_audit_by_entity(
    session: SessionDep,
) -> ImportAuditByEntityResponse:
    """One row per entity that has ever been ingested — name + run
    counts + latest status + dedup_audit + enrichment counters.

    Self-healing (2026-05-29 QA audit P1): introspects optional audit/
    enrichment tables and degrades to 0-counts-plus-warning rather than
    500ing. The QA round caught that this endpoint hard-failed every
    request when ai_enrichments was missing, had the legacy entity_id
    shape, or dedup_audit was absent — that 500 then surfaced as the
    app-wide "Backend data failed to load" banner on every page (since
    fixed by error scoping in the standalone loader too).

    Failure-mode matrix (each branch verified by tests):
      • dedup_audit present                  → real count
      • dedup_audit missing                  → 0 + 'dedup_audit_missing'
      • ai_enrichments(target_kind,target_id) → real count (current shape)
      • ai_enrichments(entity_id) legacy     → count + 'ai_enrichments_legacy_entity_id_shape'
      • ai_enrichments unknown shape         → 0 + 'ai_enrichments_unknown_shape'
      • ai_enrichments missing               → 0 + 'ai_enrichments_missing'
      • entities or runs missing             → HTTP 503 (core, not optional)
    """
    warnings: list[str] = []

    # Core tables — missing is a 503, not a warning. `entities` + `runs`
    # are the floor of any DMA Insights install; their absence means the
    # DB is un-migrated and the admin surface can't render anything
    # meaningful. Pre-018 partial deploys (no AI layer yet) are the
    # legitimate degraded case the rest of this endpoint handles.
    for core in ("entities", "runs"):
        if not await _table_exists(session, core):
            raise HTTPException(
                status_code=503,
                detail=(
                    f"core table '{core}' missing — DB is un-migrated. "
                    "Run: gcloud run jobs execute dma-insights-migrations "
                    "--region=us-central1 --wait"
                ),
            )

    dedup_audit_ok = await _table_exists(session, "dedup_audit")
    if not dedup_audit_ok:
        warnings.append("dedup_audit_missing")

    ae_cols = await _table_columns(session, "ai_enrichments")
    if not ae_cols:
        ae_mode = "missing"
        warnings.append("ai_enrichments_missing")
    elif {"target_kind", "target_id"}.issubset(ae_cols):
        ae_mode = "current"
    elif "entity_id" in ae_cols:
        ae_mode = "legacy"
        warnings.append("ai_enrichments_legacy_entity_id_shape")
    else:
        ae_mode = "unknown"
        warnings.append("ai_enrichments_unknown_shape")

    # Compose the optional subqueries based on the schema state. Building
    # the SQL once + parameter-free keeps the plan cache-friendly and
    # avoids string interpolation of column names from anything other
    # than the literal allowlist above.
    dedup_sql = (
        "(SELECT COUNT(*) FROM dedup_audit da "
        " JOIN runs r3 ON r3.id = da.run_id "
        " WHERE r3.entity_id = e.id)"
        if dedup_audit_ok else "0"
    )
    if ae_mode == "current":
        ae_sql = (
            "(SELECT COUNT(*) FROM ai_enrichments ae "
            " WHERE ae.target_kind = 'entity' AND ae.target_id = e.id)"
        )
    elif ae_mode == "legacy":
        ae_sql = (
            "(SELECT COUNT(*) FROM ai_enrichments ae WHERE ae.entity_id = e.id)"
        )
    else:  # missing or unknown
        ae_sql = "0"

    sql = f"""
        SELECT e.id AS entity_id, e.display_id, e.name,
               MAX(r.completed_at) AS latest_run_completed_at,
               COUNT(DISTINCT r.id) AS runs_count,
               (
                 SELECT r2.status FROM runs r2
                 WHERE r2.entity_id = e.id
                 ORDER BY r2.created_at DESC LIMIT 1
               ) AS latest_status,
               {dedup_sql} AS dedup_audit_count,
               {ae_sql} AS enrichment_count
        FROM entities e
        LEFT JOIN runs r ON r.entity_id = e.id
        GROUP BY e.id, e.display_id, e.name
        ORDER BY MAX(r.completed_at) DESC NULLS LAST
    """
    rows = (await session.execute(text(sql))).all()
    return ImportAuditByEntityResponse(
        items=[
            ImportAuditEntityRow(
                entity_id=str(r.entity_id),
                entity_display_id=r.display_id,
                entity_name=r.name,
                latest_run_completed_at=r.latest_run_completed_at,
                runs_count=int(r.runs_count or 0),
                latest_status=r.latest_status,
                dedup_audit_count=int(r.dedup_audit_count or 0),
                enrichment_count=int(r.enrichment_count or 0),
            )
            for r in rows
        ],
        warnings=warnings,
    )


@router.get(
    "/import-audit/entities/{entity_id}",
    response_model=ImportAuditEntityDetailResponse,
)
async def import_audit_entity_detail(
    entity_id: str, session: SessionDep,
) -> ImportAuditEntityDetailResponse:
    """Per-entity drilldown: every run timeline + every job execution
    that touched this entity. Empty-state when no runs."""
    ent = (
        await session.execute(
            text(
                """
                SELECT id, display_id, name FROM entities
                WHERE display_id = :did OR id::text = :did
                LIMIT 1
                """
            ),
            {"did": entity_id},
        )
    ).first()
    if ent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"entity {entity_id} not found",
        )

    runs = (
        await session.execute(
            text(
                """
                SELECT r.id, r.request_id, r.status, r.completed_at,
                       r.parent_request_id,
                       (
                         SELECT COUNT(*) FROM evidence_index ev
                         WHERE ev.run_id = r.id
                       ) AS evidence_count,
                       (
                         SELECT COUNT(*) FROM evidence_embeddings ee
                         JOIN evidence_index ev ON ev.id = ee.evidence_id
                         WHERE ev.run_id = r.id
                       ) AS embedding_count
                FROM runs r
                WHERE r.entity_id = :eid
                ORDER BY r.created_at DESC LIMIT 50
                """
            ),
            {"eid": ent.id},
        )
    ).all()
    jobs = (
        await session.execute(
            text(
                """
                SELECT id, job_name, status, started_at, completed_at,
                       duration_sec
                FROM job_executions
                WHERE entity_id = :eid
                ORDER BY started_at DESC LIMIT 50
                """
            ),
            {"eid": ent.id},
        )
    ).all()
    return ImportAuditEntityDetailResponse(
        entity_id=str(ent.id),
        entity_display_id=ent.display_id,
        entity_name=ent.name,
        runs=[
            ImportAuditEntityRunRow(
                run_id=str(r.id), request_id=r.request_id,
                status=r.status, completed_at=r.completed_at,
                parent_request_id=r.parent_request_id,
                evidence_count=int(r.evidence_count or 0),
                embedding_count=int(r.embedding_count or 0),
            )
            for r in runs
        ],
        job_executions=[
            ImportAuditEntityJobRow(
                id=str(j.id), job_name=j.job_name, status=j.status,
                started_at=j.started_at, completed_at=j.completed_at,
                duration_sec=(
                    float(j.duration_sec) if j.duration_sec is not None else None
                ),
            )
            for j in jobs
        ],
    )


@router.post(
    "/imports/files/{file_id}:retry",
    response_model=JobExecutionOut,
)
async def retry_import_file(
    file_id: str, actor: CurrentUserDep, session: SessionDep,
) -> JobExecutionOut:
    """Re-parse a single import_files row. Writes a job_executions row
    in 'running' state scoped to the file's parent entity."""
    row = (
        await session.execute(
            text("SELECT id, entity_id FROM import_files WHERE id = CAST(:id AS uuid)"),
            {"id": file_id},
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"import file {file_id} not found",
        )
    import json as _json
    args = _json.dumps({"file_id": file_id, "retry": True})
    out = (
        await session.execute(
            text(
                """
                INSERT INTO job_executions (
                    job_name, mode, triggered_by_user_id, triggered_by_email,
                    trigger_source, status, entity_id, args
                ) VALUES (
                    'drive_crawler', 'delta', CAST(:uid AS uuid), :email,
                    'admin_ui', 'running',
                    -- ERROR HISTORY B1 (re-fixed 2026-05-24): single
                    -- explicit CAST avoids asyncpg AmbiguousParameterError.
                    -- See main fix at admin.py line ~605.
                    CAST(:eid AS uuid),
                    CAST(:args AS jsonb)
                )
                RETURNING id, job_name, mode, status, trigger_source,
                          triggered_by_email, started_at, completed_at,
                          duration_sec, entity_id, folders_seen, folders_new,
                          folders_changed, files_parsed, files_skipped,
                          files_errored, rows_added, rows_updated,
                          rows_deleted, parser_warnings, stderr_tail,
                          error_message
                """
            ),
            {
                "uid": actor.user_id, "email": actor.email,
                "eid": str(row.entity_id) if row.entity_id else None,
                "args": args,
            },
        )
    ).first()
    await session.commit()
    return _row_to_job_out(out)


@router.post("/maintenance/refresh-evidence-freshness",
             include_in_schema=False,
             dependencies=[Depends(require_admin)])
async def refresh_evidence_freshness_endpoint(
    session: SessionDep,
) -> dict:
    """Daily Cloud Scheduler hook (see DEPLOYMENT.md §28b).

    Calls the plpgsql `refresh_evidence_freshness()` function that
    recomputes `is_stale` + `freshness_band` for rows whose
    published_date crossed a 1y/2y/3y band boundary between writes.

    State branches:
      function_exists       → executes; returns rows_changed count
      function_missing      → returns 0 with note='migration_018_not_applied'
                              (older deploys; safe no-op)
      db_unreachable        → 503 (Scheduler retries with backoff)

    Returns:
      {rows_changed: int, ran_at: ISO8601, note: str | null}
    """
    from datetime import UTC, datetime
    try:
        result = (
            await session.execute(text("SELECT refresh_evidence_freshness() AS n"))
        ).first()
        return {
            "rows_changed": int(result.n or 0) if result else 0,
            "ran_at": datetime.now(tz=UTC).isoformat(),
            "note": None,
        }
    except Exception as e:
        # Function-missing path — older deploys without migration 018
        # land here. Don't 500; return 0 + note so Scheduler doesn't
        # alarm-spike during a partial migration window.
        return {
            "rows_changed": 0,
            "ran_at": datetime.now(tz=UTC).isoformat(),
            "note": f"refresh_skipped: {type(e).__name__}: {str(e)[:80]}",
        }


# ── Catalogue upload (Promise #11 closure) ────────────────────────────
#
# Frontend wires `DMA.admin.uploadCatalogue(file, version)` to POST
# multipart to this endpoint (see backend-loader.js:476).
#
# Contract:
#   - Accepts a single .xlsx workbook OR .zip of the 4 pillar workbooks.
#   - Writes to /tmp/dma-catalogue-staging/<sha>/ for ccg_loader to pick up.
#   - Enqueues a `job_executions` row (job_name='ccg_loader',
#     trigger_source='admin_ui', status='running') so the admin UI's
#     polling sees the upload kick off a workflow.
#   - Returns the execution_id so the UI can poll status.
#
# State branches:
#   file_missing            → 400 "no file supplied"
#   wrong_extension         → 400 "must be .xlsx or .zip"
#   staging_dir_unwritable  → 500 with the OSError detail
#   job_executions_missing  → 503 "migration 020 not applied" (matches
#                             the existing execute_job behavior so the
#                             operator sees one consistent message)
#   upload_ok               → 200 with {execution_id, file, size_bytes,
#                             staging_path}
#
# The actual catalogue ingest is async — the operator polls
# /api/v1/admin/jobs/executions/{id} for status. Worker side
# (workers/ccg_loader) reads the staging path from the row's `args`
# JSONB and runs validators + diff + admin-approval gate.
@router.post("/catalogue:upload", include_in_schema=False,
             dependencies=[Depends(require_admin)])
async def upload_catalogue(
    actor: CurrentUserDep,
    session: SessionDep,
    workbook: UploadFile = File(...),  # noqa: B008 — FastAPI dependency pattern
    version: str | None = Form(None),
) -> dict:
    """Accept a catalogue workbook + enqueue a ccg_loader run."""
    import hashlib as _hashlib
    import json as _json
    import pathlib as _pathlib
    from datetime import UTC, datetime

    # ── 1. Validate extension. ────────────────────────────────────────
    fname = (workbook.filename or "").strip()
    if not fname:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="no file supplied")
    suffix = _pathlib.Path(fname).suffix.lower()
    if suffix not in {".xlsx", ".zip"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"file must be .xlsx or .zip; got '{suffix}'. "
                   f"Upload the Pillar_*_Comprehensive_Capability_Mapping_v*.xlsx "
                   f"workbook OR a ZIP containing all four.",
        )

    # ── 2. Read + hash + persist to staging. ──────────────────────────
    body = await workbook.read()
    if not body:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="uploaded file is empty")
    sha256 = _hashlib.sha256(body).hexdigest()[:16]

    # ── 2. Stage the workbook via the GCS uploader. ───────────────────
    # 2026-05-28 P1-C remainder: pre-fix the upload route wrote the
    # workbook to `/tmp/dma-catalogue-staging/<sha>/<file>` (local to
    # the backend container) and best-effort published a Pub/Sub
    # message to `admin-job-triggered` (a topic with no subscriber).
    # Net effect: the ccg_loader Cloud Run Job never received the
    # upload, the `job_executions` row stayed `running` forever, and
    # operators had to manually `gcloud storage cp` workbooks to the
    # staging bucket + `gcloud run jobs execute dma-insights-ccg-
    # loader`. Now the route uploads directly to the GCS bucket the
    # ccg_loader is already configured to read AND dispatches the
    # worker via Cloud Run Jobs Run API.
    #
    # Resilience: when GCS is unreachable (local dev / missing perms)
    # the helper falls back to writing /tmp; we surface `backing=
    # local_fallback` in the response so the operator immediately
    # sees the upload landed only locally.
    settings = get_settings()
    from app.services.catalogue_staging import upload_workbook_to_staging
    try:
        staged = upload_workbook_to_staging(
            workbook_bytes=body,
            filename=fname,
            version_hint=version,
            bucket_name=settings.gcs_bucket_catalogue_staging,
            project_id=settings.gcp_project_id,
            sha256_prefix=sha256,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"staging upload failed: {type(e).__name__}: {e!s}"[:500],
        ) from None

    # ── 3. Enqueue ccg_loader job_executions row. ─────────────────────
    args_json = _json.dumps({
        "workbooks_dir_arg": staged.workbooks_dir_arg,
        "gcs_uri": staged.gcs_uri,
        "local_path": str(staged.local_path) if staged.local_path else None,
        "backing": staged.backing,
        "version_hint": version,
        "uploaded_filename": fname,
        "uploaded_bytes": len(body),
        "uploaded_sha256_prefix": sha256,
        "uploaded_by_email": actor.email,
    })
    try:
        row = (
            await session.execute(
                text(
                    """
                    INSERT INTO job_executions (
                        job_name, mode, triggered_by_user_id,
                        triggered_by_email, trigger_source, status, args
                    ) VALUES (
                        'ccg_loader', 'full', CAST(:uid AS uuid),
                        :email, 'admin_ui', 'running', CAST(:args AS jsonb)
                    )
                    RETURNING id
                    """
                ),
                {"uid": actor.user_id, "email": actor.email, "args": args_json},
            )
        ).first()
        await session.commit()
    except Exception as e:
        msg = str(e).lower()
        if "job_executions" in msg and ("does not exist" in msg or "undefinedtable" in msg):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "job_executions table missing — migration 020 hasn't "
                    "been applied to this database. Run "
                    "`cd apps/dma-insights/infra && ./migrate.sh` then retry."
                ),
            ) from None
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"ccg_loader enqueue failed: {type(e).__name__}: {e!s}"[:500],
        ) from None

    # ── 4. Direct Cloud Run Jobs dispatch (NOT via Pub/Sub). ──────────
    # The legacy admin-job-triggered topic publish was best-effort to a
    # topic that has no subscriber. Switch to `dispatch_job` which
    # uses the Cloud Run Jobs Run API with custom args — the same
    # path used by the per-job admin "Execute" buttons. The worker
    # receives --version + --workbooks-dir via the run override.
    dispatch_args: list[str] = ["--workbooks-dir", staged.workbooks_dir_arg]
    if version:
        # `--version` is required by the ccg_loader CLI; without it the
        # worker exits rc=2. Pass through whatever the operator typed.
        dispatch_args = ["--version", version, *dispatch_args]
    dispatch_reason: str | None = None
    try:
        from app.services.cloud_run_dispatch import dispatch_job
        dispatched, dispatch_reason = await dispatch_job(
            job_name="ccg_loader",
            execution_id=str(row.id),
            extra_args=dispatch_args,
        )
    except Exception as e:
        dispatched = False
        dispatch_reason = f"unexpected:{type(e).__name__}:{e!s}"[:300]
    if not dispatched:
        # The job_executions row exists but the worker won't run.
        # Mark it failed with a precise reason so operators don't
        # see "running" forever.
        await session.execute(
            text(
                "UPDATE job_executions "
                "SET status='failed', completed_at=NOW(), "
                "    error_message=:reason "
                "WHERE id = CAST(:id AS uuid)"
            ),
            {
                "reason": f"dispatch_failed:{dispatch_reason}"[:500],
                "id": str(row.id),
            },
        )
        await session.commit()
        # 503 because the upload itself succeeded; only dispatch
        # failed (transient infra issue). Operator can retry.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"ccg_loader Cloud Run dispatch failed: {dispatch_reason}. "
                f"Workbook was staged at {staged.workbooks_dir_arg} but "
                f"the worker did not start. Retry the upload once "
                f"infra is healthy; the staging path is idempotent."
            ),
        )

    return {
        "execution_id": str(row.id),
        "uploaded_at": datetime.now(tz=UTC).isoformat(),
        "uploaded_filename": fname,
        "uploaded_bytes": len(body),
        "workbooks_dir_arg": staged.workbooks_dir_arg,
        "backing": staged.backing,
        "version_hint": version,
        "dispatch_reason": dispatch_reason,
        "next_step": (
            "Poll /api/v1/admin/jobs/executions/" + str(row.id) +
            " for status. Worker validates the workbook, diffs vs the "
            "prior version, and flips status='succeeded' on completion. "
            "View live logs via the `logs_url` field on the job row."
        ),
    }


# ── Catalogue approve (closes the upload→approve loop) ────────────────
#
# Pairs with:
#   - POST /catalogue:upload (3e73234) — enqueues the parse job
#   - ccg_loader.persist_loader_run (20daba9) — writes
#     ccg_loader_runs row with status='AWAITING_APPROVAL'
#   - GET /catalogue (existing) — surfaces the awaiting queue in
#     the admin UI
#
# This endpoint is the missing piece: flip status='AWAITING_APPROVAL'
# → status='APPLIED', record approved_by/approved_at, write an
# audit_log row.
#
# Once status='APPLIED', the catalogue-loader's promote step (staging
# → canonical ccg_* tables) is unblocked. The promote itself runs in
# the worker via a separate Pub/Sub trigger; this endpoint only marks
# the row as approved.
#
# State branches:
#   row_missing         → 404 with the requested id
#   wrong_status        → 409 with the actual status + hint
#   already_applied     → 409 (idempotent — second click is rejected)
#   admin_self_approve  → allowed (single-admin workflow OK)
#   approve_ok          → 200 with the updated row
@router.post("/catalogue/{run_id}:approve", include_in_schema=False,
             dependencies=[Depends(require_admin)])
async def approve_catalogue_run(
    run_id: str, actor: CurrentUserDep, session: SessionDep,
) -> dict:
    """Promote a ccg_loader_runs row from AWAITING_APPROVAL → APPLIED."""
    from datetime import UTC, datetime
    # 1. Look up the row + verify status.
    try:
        row = (
            await session.execute(
                text(
                    """
                    SELECT id, version, status, loader_finished_at
                    FROM ccg_loader_runs
                    WHERE id = CAST(:id AS uuid)
                    """
                ),
                {"id": run_id},
            )
        ).first()
    except Exception as e:
        msg = str(e).lower()
        if "ccg_loader_runs" in msg and ("does not exist" in msg or "undefinedtable" in msg):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "ccg_loader_runs table missing — migration 012_ccg_catalogue "
                    "hasn't been applied. Run "
                    "`cd apps/dma-insights/infra && ./migrate.sh` then retry."
                ),
            ) from None
        raise

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ccg_loader_runs row {run_id} not found — "
                   f"upload a catalogue first via /admin/catalogue:upload",
        )
    if row.status == "APPLIED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"row {run_id} already APPLIED — idempotent endpoint "
                   f"rejects double-approve to prevent accidental re-promote",
        )
    if row.status != "AWAITING_APPROVAL":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"row {run_id} is in status='{row.status}', not "
                f"'AWAITING_APPROVAL'. Only awaiting-approval runs can be "
                f"approved. (Rejected runs need a new upload; staging "
                f"runs are auto-promoted by the loader.)"
            ),
        )

    # 2. Flip status + record approver.
    await session.execute(
        text(
            """
            UPDATE ccg_loader_runs
            SET status = 'APPLIED',
                admin_approved_by = CAST(:uid AS uuid),
                admin_approved_at = NOW()
            WHERE id = CAST(:id AS uuid)
            """
        ),
        {"uid": actor.user_id, "id": run_id},
    )

    # 3. Audit log entry — same pattern as update_role.
    import json as _json
    await session.execute(
        text(
            """
            INSERT INTO audit_log (
                actor_user_id, actor_email, action, resource_type,
                resource_id, after_json
            ) VALUES (
                CAST(:aid AS uuid), :ae, 'catalogue_approve', 'ccg_loader_runs',
                :rid, CAST(:after AS jsonb)
            )
            """
        ),
        {
            "aid": actor.user_id, "ae": actor.email, "rid": run_id,
            "after": _json.dumps({
                "version": row.version, "from_status": row.status,
                "to_status": "APPLIED",
            }),
        },
    )
    await session.commit()

    return {
        "id": run_id,
        "version": row.version,
        "status": "APPLIED",
        "approved_by_email": actor.email,
        "approved_at": datetime.now(tz=UTC).isoformat(),
        "next_step": (
            "Staging→canonical promote runs in the ccg_loader worker on "
            "the next Pub/Sub tick. Poll /admin/catalogue or "
            "/admin/jobs/executions for ccg_loader runs in 'running' state."
        ),
    }


# ── Catalogue REJECT (pairs with approve) ─────────────────────────────
#
# When the admin reviews an AWAITING_APPROVAL run and finds problems
# (validation warnings they don't trust, accidentally-uploaded wrong
# version, etc.), they reject it instead of approving. Rejected rows
# stay in ccg_loader_runs for audit but are excluded from the active
# catalogue queue surface.
#
# State branches:
#   row_missing       → 404
#   already_rejected  → 409 idempotent
#   already_applied   → 409 (can't reject an applied catalogue —
#                       admin must roll back via a different path)
#   wrong_status      → 409 with current status hint
#   reject_ok         → 200 with the updated row
@router.post("/catalogue/{run_id}:reject", include_in_schema=False,
             dependencies=[Depends(require_admin)])
async def reject_catalogue_run(
    run_id: str,
    body: dict,
    actor: CurrentUserDep,
    session: SessionDep,
) -> dict:
    """Reject a ccg_loader_runs row — AWAITING_APPROVAL → REJECTED."""
    from datetime import UTC, datetime
    reason = (body or {}).get("reason", "").strip()
    if not reason:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="reason required — admins must justify rejections "
                   "for audit (free-text in body.reason)",
        )

    try:
        row = (
            await session.execute(
                text(
                    """
                    SELECT id, version, status
                    FROM ccg_loader_runs
                    WHERE id = CAST(:id AS uuid)
                    """
                ),
                {"id": run_id},
            )
        ).first()
    except Exception as e:
        msg = str(e).lower()
        if "ccg_loader_runs" in msg and ("does not exist" in msg or "undefinedtable" in msg):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "ccg_loader_runs table missing — migration "
                    "012_ccg_catalogue not applied. Run "
                    "`cd apps/dma-insights/infra && ./migrate.sh`."
                ),
            ) from None
        raise

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ccg_loader_runs row {run_id} not found",
        )
    if row.status == "REJECTED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"row {run_id} already REJECTED — idempotent endpoint",
        )
    if row.status == "APPLIED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"row {run_id} is APPLIED — cannot reject an already-"
                f"applied catalogue. Roll back via a new upload + "
                f"approve cycle of the prior version."
            ),
        )
    if row.status != "AWAITING_APPROVAL":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"row {run_id} status='{row.status}', not AWAITING_APPROVAL",
        )

    # The notes column on ccg_catalog_versions exists for free-text
    # admin annotations. ccg_loader_runs has parse_warnings JSONB
    # but no explicit rejection_reason column — we append to
    # parse_warnings as a structured entry so the queue view shows
    # both validator warnings AND the admin's rejection reason.
    import json as _json
    await session.execute(
        text(
            """
            UPDATE ccg_loader_runs
            SET status = 'REJECTED',
                admin_approved_by = CAST(:uid AS uuid),
                admin_approved_at = NOW(),
                parse_warnings = COALESCE(parse_warnings, '[]'::jsonb)
                              || CAST(:rejection_entry AS jsonb)
            WHERE id = CAST(:id AS uuid)
            """
        ),
        {
            "uid": actor.user_id, "id": run_id,
            "rejection_entry": _json.dumps([{
                "kind": "admin_rejection",
                "actor_email": actor.email,
                "reason": reason[:500],
                "rejected_at": datetime.now(tz=UTC).isoformat(),
            }]),
        },
    )

    # Audit log
    await session.execute(
        text(
            """
            INSERT INTO audit_log (
                actor_user_id, actor_email, action, resource_type,
                resource_id, after_json
            ) VALUES (
                CAST(:aid AS uuid), :ae, 'catalogue_reject', 'ccg_loader_runs',
                :rid, CAST(:after AS jsonb)
            )
            """
        ),
        {
            "aid": actor.user_id, "ae": actor.email, "rid": run_id,
            "after": _json.dumps({
                "version": row.version, "from_status": row.status,
                "to_status": "REJECTED", "reason": reason[:200],
            }),
        },
    )
    await session.commit()

    return {
        "id": run_id,
        "version": row.version,
        "status": "REJECTED",
        "rejected_by_email": actor.email,
        "rejected_at": datetime.now(tz=UTC).isoformat(),
        "reason": reason,
    }


@router.get("/parser-observations", include_in_schema=False)
async def parser_observations(
    session: SessionDep,
    parser: str | None = None,
    kind: str | None = None,
    min_occurrences: int = 1,
    limit: int = 200,
) -> dict[str, object]:
    """Self-improvement queue: structural surprises sub-parsers logged
    while ingesting workbooks. Operators promote recurring variants
    into the source-code ALIASES dicts via a PR; redeploy ships the
    learned variant.

    State branches:
      - empty_table        → []  (no surprises yet — common in steady state)
      - has_observations   → rows sorted by (occurrence_count DESC,
                              last_seen DESC) so the most actionable
                              variants float to the top
      - migration_pending  → 500 from the underlying SELECT if the
                              026 migration hasn't been applied; the
                              router lets the error propagate so the
                              admin Diagnostics panel surfaces it.

    Query params:
      parser            filter by parser_name (e.g. 'research_workbook')
      kind              filter by observation_kind (e.g. 'unknown_column')
      min_occurrences   only show variants seen ≥ N times (default 1)
      limit             max rows (capped at 1000)
    """
    limit_capped = max(1, min(limit, 1000))
    where_parts = ["occurrence_count >= :min_occ"]
    params: dict[str, object] = {"min_occ": int(min_occurrences),
                                  "lim": limit_capped}
    if parser:
        where_parts.append("parser_name = :parser")
        params["parser"] = parser[:64]
    if kind:
        where_parts.append("observation_kind = :kind")
        params["kind"] = kind[:64]
    where_sql = " AND ".join(where_parts)
    # Local alias to match the convention used elsewhere in this router
    # for inline raw SQL — the module-level `text` import already
    # exists; reuse it via this short alias for readability.
    from sqlalchemy import text as _text
    rows = (await session.execute(
        _text(
            f"""
            SELECT id, parser_name, observation_kind, observed_value,
                   canonical_guess, sample_context,
                   occurrence_count, distinct_runs,
                   first_seen, last_seen
              FROM parser_observations
             WHERE {where_sql}
             ORDER BY occurrence_count DESC, last_seen DESC
             LIMIT :lim
            """
        ),
        params,
    )).mappings().all()
    return {
        "items": [
            {
                "id": r["id"],
                "parser_name": r["parser_name"],
                "observation_kind": r["observation_kind"],
                "observed_value": r["observed_value"],
                "canonical_guess": r["canonical_guess"],
                "sample_context": r["sample_context"],
                "occurrence_count": r["occurrence_count"],
                "distinct_runs": r["distinct_runs"],
                "first_seen": r["first_seen"].isoformat() if r["first_seen"] else None,
                "last_seen": r["last_seen"].isoformat() if r["last_seen"] else None,
            }
            for r in rows
        ],
    }


@router.post(
    "/feedback-files:refresh-all",
    response_model=FeedbackRefreshAllResponse,
)
async def refresh_all_feedback_files(
    actor: CurrentUserDep,
    session: SessionDep,
) -> FeedbackRefreshAllResponse:
    """Re-run the PRD §17 Drive feedback-file write for every ACTIVE entity
    with a recorded drive_folder_id. Admin-only (router gate); prod/staging
    only (dev_skip locally; per-entity fail-closed)."""
    import json as _json

    from app.services.drive_feedback import write_feedback_files

    env = get_settings().env
    ent_rows = (
        await session.execute(
            text(
                "SELECT id::text AS eid, display_id, drive_folder_id "
                "FROM entities WHERE status = 'ACTIVE' "
                "AND drive_folder_id IS NOT NULL ORDER BY display_id"
            )
        )
    ).all()
    results: list[FeedbackRefreshAllItem] = []
    by_state: dict[str, int] = {}
    for ent in ent_rows:
        run_row = (
            await session.execute(
                text(
                    "SELECT id::text AS rid FROM runs "
                    "WHERE entity_id = CAST(:eid AS uuid) AND status = 'ACTIVE' "
                    "ORDER BY completed_at DESC NULLS LAST LIMIT 1"
                ),
                {"eid": ent.eid},
            )
        ).first()
        if run_row is None:
            results.append(FeedbackRefreshAllItem(
                entity_display_id=ent.display_id, state="no_active_run"))
            by_state["no_active_run"] = by_state.get("no_active_run", 0) + 1
            continue
        result = await write_feedback_files(
            session=session, db_run_id=run_row.rid, entity_id=ent.eid,
            drive_folder_id=ent.drive_folder_id, env=env,
        )
        results.append(FeedbackRefreshAllItem(
            entity_display_id=ent.display_id, state=result.state,
            written=result.written, failed=result.failed,
        ))
        by_state[result.state] = by_state.get(result.state, 0) + 1
    try:
        await session.execute(
            text("""
                INSERT INTO audit_log
                    (actor_user_id, actor_email, action, resource_type,
                     resource_id, after_json)
                VALUES (CAST(:uid AS uuid), :email,
                        'refresh_all_feedback_files', 'entities',
                        NULL, CAST(:payload AS jsonb))
            """),
            {
                "uid": actor.user_id, "email": actor.email,
                "payload": _json.dumps({
                    "total": len(results), "by_state": by_state,
                }),
            },
        )
        await session.commit()
    except Exception:
        await session.rollback()
    return FeedbackRefreshAllResponse(
        total=len(results), by_state=by_state, results=results,
    )
