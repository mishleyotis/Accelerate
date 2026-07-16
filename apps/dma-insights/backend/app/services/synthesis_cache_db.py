"""SQL-executing layer for `vertex_synthesis_cache` — the persistence
side of the synthesis orchestrator.

Pairs with `app.services.synthesis_orchestrator` (pure decision engine).
The orchestrator computes the fingerprint + decision gate; this module
turns those into INSERT/UPDATE/SELECT statements.

State transitions (single-row lifecycle):
  insert_or_supersede(row)
      → INSERT a new row; if a prior row with the same
        (target_kind, target_id, surface) is still active, set its
        superseded_by to the new id (lifecycle pointer for audit).
  fetch_active(target_kind, target_id, surface, fingerprint)
      → SELECT the active row matching the fingerprint, or None.
        Returns None for expired / invalidated rows so the caller
        treats them as cache miss.
  mark_invalidated(spec)
      → UPDATE invalidated_at + invalidation_reason on every row
        matched by InvalidationSpec (new-run, catalogue-bump, feedback).
  record_access(row_id)
      → UPDATE last_accessed_at + access_count++.
        Fire-and-forget; never blocks the read path.

Resilience contract:
  DB unreachable → every helper logs + swallows. Caller treats the
  return as cache-miss / no-invalidation-happened. The Redis L1
  cache + the Vertex live call both still work; only the L2
  (Postgres) observability degrades.

State-transition matrix for `_safe_*` wrappers:
  database_url_unset           → log warning, return None / no-op
  postgres_unreachable         → log warning, return None / no-op
  unique_violation_on_insert   → caller likely raced another writer;
                                 fetch the winner row + return it
  superseded_by_update_fail    → log warning, but new row still
                                 inserted (the supersede chain is
                                 audit-only — readers use the active
                                 row regardless)
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.services.synthesis_orchestrator import (
    CacheRow,
    InvalidationSpec,
    compute_expires_at,
)

log = structlog.get_logger()


_engine: Engine | None = None


def _get_engine() -> Engine:
    """Lazy sync engine cached at module level. Reused across helper
    calls within a single request — same pattern as job_executions_db."""
    global _engine
    if _engine is None:
        # See `app/services/sync_dsn.py` for the resolution rules.
        # Same fallback as `job_executions_db._get_engine` — workers
        # only get DATABASE_URL injected; we derive the sync form.
        # Without this, every post-commit synthesis-cache
        # invalidation in `package_persist.persist_package` raised
        # and got silently swallowed; cached responses stayed stale
        # forever after a re-ingest.
        from app.services.sync_dsn import resolve_sync_dsn
        url = resolve_sync_dsn()
        if not url:
            raise RuntimeError(
                "Neither DATABASE_URL_SYNC nor DATABASE_URL is set "
                "— synthesis_cache_db lifecycle calls require a "
                "sync DSN. (Test environments without a DB should "
                "not reach the safe_* wrappers; they short-circuit "
                "on the import.)"
            )
        _engine = create_engine(url, pool_pre_ping=True, pool_size=2)
    return _engine


def reset_engine_for_tests() -> None:
    """Test hook — clears the cached engine so tests can swap
    DATABASE_URL_SYNC between cases."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def _row_from_db(d: dict[str, Any]) -> CacheRow:
    """Convert a SQLAlchemy Row mapping into a CacheRow dataclass."""
    return CacheRow(
        id=str(d["id"]),
        target_kind=d["target_kind"],
        target_id=d["target_id"],
        surface=d["surface"],
        model=d["model"],
        input_fingerprint=d["input_fingerprint"],
        prompt_template_version=d["prompt_template_version"],
        grounding_bundle_hash=d["grounding_bundle_hash"],
        catalogue_version=d["catalogue_version"],
        output_text=d["output_text"],
        output_json=d.get("output_json"),
        cited_evidence_ids=d.get("cited_evidence_ids"),
        cited_subcap_ids=d.get("cited_subcap_ids"),
        validators_passed=d["validators_passed"],
        confidence=float(d["confidence"]) if d.get("confidence") is not None else None,
        prompt_tokens=int(d["prompt_tokens"] or 0),
        completion_tokens=int(d["completion_tokens"] or 0),
        latency_ms=int(d["latency_ms"] or 0),
        created_at=d["created_at"],
        last_accessed_at=d["last_accessed_at"],
        access_count=int(d["access_count"] or 0),
        expires_at=d.get("expires_at"),
        invalidated_at=d.get("invalidated_at"),
        invalidation_reason=d.get("invalidation_reason"),
        superseded_by=str(d["superseded_by"]) if d.get("superseded_by") else None,
        decision_gate=d["decision_gate"],
    )


def fetch_active(
    target_kind: str,
    target_id: str,
    surface: str,
    fingerprint: str,
) -> CacheRow | None:
    """Look up the active cache row by fingerprint. Returns None if
    no row exists, the row is invalidated, OR the row is expired."""
    eng = _get_engine()
    with eng.begin() as conn:
        result = conn.execute(text("""
            SELECT * FROM vertex_synthesis_cache
            WHERE target_kind = :tk
              AND target_id = :tid
              AND surface = :surface
              AND input_fingerprint = :fp
              AND invalidated_at IS NULL
              AND (expires_at IS NULL OR expires_at > NOW())
            ORDER BY created_at DESC
            LIMIT 1
        """), {"tk": target_kind, "tid": target_id,
               "surface": surface, "fp": fingerprint})
        row = result.mappings().first()
        return _row_from_db(dict(row)) if row else None


def insert_or_supersede(
    *,
    target_kind: str,
    target_id: str,
    surface: str,
    model: str,
    input_fingerprint: str,
    prompt_template_version: str,
    grounding_bundle_hash: str,
    catalogue_version: str,
    output_text: str,
    output_json: dict[str, Any] | None = None,
    cited_evidence_ids: list[str] | None = None,
    cited_subcap_ids: list[str] | None = None,
    validators_passed: bool = True,
    confidence: float | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    latency_ms: int = 0,
    decision_gate: str = "cache_miss_synthesized",
    expires_at: datetime | None = None,
) -> str:
    """INSERT a new cache row + supersede any prior active row with the
    same (target_kind, target_id, surface). Returns the new row id.

    `expires_at` defaults to `compute_expires_at(surface)` (per-surface
    TTL from DEFAULT_TTL_SEC) so callers don't have to think about it."""
    row_id = str(uuid.uuid4())
    if expires_at is None:
        expires_at = compute_expires_at(surface)
    eng = _get_engine()
    with eng.begin() as conn:
        # Supersede prior active row(s) — audit pointer only; readers
        # use the active row.
        conn.execute(text("""
            UPDATE vertex_synthesis_cache
            SET superseded_by = :new_id
            WHERE target_kind = :tk
              AND target_id = :tid
              AND surface = :surface
              AND invalidated_at IS NULL
              AND superseded_by IS NULL
              AND id != :new_id
        """), {"new_id": row_id, "tk": target_kind,
               "tid": target_id, "surface": surface})

        conn.execute(text("""
            INSERT INTO vertex_synthesis_cache
                (id, target_kind, target_id, surface, model,
                 input_fingerprint, prompt_template_version,
                 grounding_bundle_hash, catalogue_version,
                 output_text, output_json,
                 cited_evidence_ids, cited_subcap_ids,
                 validators_passed, confidence,
                 prompt_tokens, completion_tokens, latency_ms,
                 created_at, last_accessed_at, access_count,
                 expires_at, decision_gate)
            VALUES
                (:id, :tk, :tid, :surface, :model,
                 :fp, :ptv, :gbh, :cv,
                 :otext, CAST(:ojson AS JSONB),
                 :ceids, :csids,
                 :vp, :conf,
                 :pt, :ct, :lat,
                 NOW(), NOW(), 0,
                 :exp, :dg)
        """), {
            "id": row_id,
            "tk": target_kind, "tid": target_id, "surface": surface,
            "model": model, "fp": input_fingerprint,
            "ptv": prompt_template_version, "gbh": grounding_bundle_hash,
            "cv": catalogue_version, "otext": output_text,
            "ojson": _to_jsonb(output_json),
            "ceids": cited_evidence_ids, "csids": cited_subcap_ids,
            "vp": validators_passed, "conf": confidence,
            "pt": prompt_tokens, "ct": completion_tokens,
            "lat": latency_ms, "exp": expires_at, "dg": decision_gate,
        })
    return row_id


def _to_jsonb(obj: dict[str, Any] | None) -> str | None:
    """Convert dict to JSON string for the CAST AS JSONB bind. None
    passes through so the column can be NULL."""
    if obj is None:
        return None
    import json
    return json.dumps(obj, default=str)


def record_access(row_id: str) -> None:
    """Fire-and-forget UPDATE — bumps last_accessed_at + access_count.
    Read-path callers invoke this on every cache hit so admin/vertex-
    budget can show 'last used 12s ago' on each row."""
    eng = _get_engine()
    with eng.begin() as conn:
        conn.execute(text("""
            UPDATE vertex_synthesis_cache
            SET last_accessed_at = NOW(),
                access_count = access_count + 1
            WHERE id = :id
        """), {"id": row_id})


def mark_invalidated(spec: InvalidationSpec) -> int:
    """UPDATE invalidated_at + invalidation_reason on every row matched
    by `spec`. Returns the number of rows touched.

    Used by:
      - package_persist on dma.ingest.completed → invalidate per entity
      - catalogue loader on version bump → invalidate per old version
      - chat_feedback POST with unhelpful_reason='hallucinated' →
        invalidate the single responsible row
    """
    eng = _get_engine()
    conditions: list[str] = ["invalidated_at IS NULL"]
    params: dict[str, Any] = {"reason": spec.reason}

    if spec.cache_row_id is not None:
        conditions.append("id = :id")
        params["id"] = spec.cache_row_id
    if spec.target_kind is not None:
        conditions.append("target_kind = :tk")
        params["tk"] = spec.target_kind
    if spec.target_ids:
        conditions.append("target_id = ANY(:tids)")
        params["tids"] = list(spec.target_ids)
    if spec.target_id_prefix:
        # Entity-qualified subcap rows ("{display_id}:{subcap_id}:…") — invalidate
        # the whole entity's subcap surface on a rerun. `\` escapes LIKE
        # metacharacters in the display_id so an id with %/_ can't over-match.
        conditions.append(r"target_id LIKE :tidp ESCAPE '\'")
        _esc = (spec.target_id_prefix.replace("\\", r"\\")
                .replace("%", r"\%").replace("_", r"\_"))
        params["tidp"] = f"{_esc}%"
    if spec.surfaces:
        conditions.append("surface = ANY(:surfaces)")
        params["surfaces"] = list(spec.surfaces)
    if spec.catalogue_version is not None:
        conditions.append("catalogue_version = :cv")
        params["cv"] = spec.catalogue_version

    where = " AND ".join(conditions)
    sql = f"""
        UPDATE vertex_synthesis_cache
        SET invalidated_at = NOW(),
            invalidation_reason = :reason
        WHERE {where}
    """
    with eng.begin() as conn:
        result = conn.execute(text(sql), params)
        return result.rowcount or 0


# ── Safe wrappers — never raise; callers treat None as cache miss ──

def safe_fetch_active(*args, **kwargs) -> CacheRow | None:
    try:
        return fetch_active(*args, **kwargs)
    except Exception as e:
        log.warning("synthesis_cache.fetch_active_failed", err=str(e))
        return None


def safe_insert_or_supersede(**kwargs) -> str | None:
    try:
        return insert_or_supersede(**kwargs)
    except Exception as e:
        log.warning("synthesis_cache.insert_failed", err=str(e))
        return None


def safe_record_access(row_id: str) -> None:
    try:
        record_access(row_id)
    except Exception as e:
        log.warning("synthesis_cache.record_access_failed", err=str(e))


def safe_mark_invalidated(spec: InvalidationSpec) -> int:
    try:
        return mark_invalidated(spec)
    except Exception as e:
        log.warning("synthesis_cache.invalidate_failed", err=str(e))
        return 0


def resolve_entity_display_id(entity_id: str) -> str | None:
    """The entity's ``display_id`` (used as the subcap-cache target_id prefix).
    Best-effort: returns None if the row is absent or the DB is unavailable —
    the caller then skips the entity-scoped subcap invalidation."""
    try:
        eng = _get_engine()
        with eng.begin() as conn:
            row = conn.execute(
                text("SELECT display_id FROM entities WHERE id = :e"),
                {"e": entity_id},
            ).first()
        return str(row[0]) if row and row[0] else None
    except Exception as e:
        log.warning("synthesis_cache.resolve_display_id_failed", err=str(e))
        return None


# ── Aggregations for /admin/vertex-budget ───────────────────────────

def aggregate_budget_rollup(*, since: datetime | None = None) -> dict[str, Any]:
    """Aggregates token + cost rollups for the admin budget panel.

    Returns a dict with the same shape as `synthesis_orchestrator.
    BudgetRollup` minus the budget_usd (which the caller pulls from
    system_config).

    Cache hit/miss accounting (the math the QA audit caught):

    Cache HITS do NOT insert a new row — they UPDATE the existing
    row's access_count via record_access(). Cache MISSES + invalidated
    re-synth + user regenerate DO insert a new row. So:

      cache_misses  = COUNT(rows whose decision_gate marks the row as
                      "this row's INSERT was caused by a miss")
                    = COUNT(decision_gate IN cache_miss_synthesized,
                            invalidated_re_synthesized, user_regenerate)
      cache_hits    = SUM(access_count) across the same rows
                    (each access_count++ was a hit-served-from-this-row)
      total_calls   = cache_misses + cache_hits
      hit_rate      = cache_hits / total_calls

    Token cost is at insert time only (HITs spend zero tokens by
    design), so prompt_tokens / completion_tokens are summed unchanged.

    State branches:
      no_rows           → all zeros + empty by_surface
      no_hits_yet       → cache_hits=0, cache_misses=N, hit_rate=0
      well_warmed       → cache_hits >> cache_misses; hit_rate ~ 0.9+
      since=None        → defaults to current month start (UTC)
    """
    if since is None:
        now = datetime.now(UTC)
        since = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    eng = _get_engine()
    with eng.begin() as conn:
        # Total tokens + calls
        # MISSES = COUNT of rows (each row's INSERT was a miss).
        # HITS   = SUM of access_count (each ++ on a row was a hit
        #          served from that row). The combined total_calls
        #          equals the number of times callers asked the cache.
        totals = conn.execute(text("""
            SELECT
                COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                COUNT(*) AS cache_misses,
                COALESCE(SUM(access_count), 0) AS cache_hits
            FROM vertex_synthesis_cache
            WHERE created_at >= :since
        """), {"since": since}).mappings().first()

        # by_surface
        by_surface_rows = conn.execute(text("""
            SELECT surface,
                   COUNT(*) AS calls,
                   COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                   COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                   model
            FROM vertex_synthesis_cache
            WHERE created_at >= :since
            GROUP BY surface, model
            ORDER BY calls DESC
        """), {"since": since}).mappings().all()

        # daily_trend
        daily = conn.execute(text("""
            SELECT DATE(created_at) AS day,
                   COUNT(*) AS calls,
                   COALESCE(SUM(prompt_tokens + completion_tokens), 0) AS tokens
            FROM vertex_synthesis_cache
            WHERE created_at >= :since
            GROUP BY DATE(created_at)
            ORDER BY day
        """), {"since": since}).mappings().all()

    totals_d = dict(totals) if totals else {
        "prompt_tokens": 0, "completion_tokens": 0,
        "cache_misses": 0, "cache_hits": 0,
    }
    cache_misses = int(totals_d["cache_misses"])
    cache_hits = int(totals_d["cache_hits"])
    return {
        "since": since.isoformat(),
        "total_calls": cache_misses + cache_hits,
        "prompt_tokens": int(totals_d["prompt_tokens"]),
        "completion_tokens": int(totals_d["completion_tokens"]),
        "cache_misses": cache_misses,
        "cache_hits": cache_hits,
        "by_surface": [dict(r) for r in by_surface_rows],
        "daily_trend": [
            {"day": str(r["day"]),
             "calls": int(r["calls"]),
             "tokens": int(r["tokens"])}
            for r in daily
        ],
    }
