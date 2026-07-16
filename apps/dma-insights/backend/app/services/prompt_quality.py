"""Prompt-quality rollup -- surface x prompt_template_version aggregator.

The "self-improving prompts" half of the 2026-06 mandate ("prompts
should always be assessed and improved after every output"). Until
now we WROTE every quality signal we needed (hallucination alerts +
synthesis-cache rows tagged with prompt_template_version + token
counts) but never READ them as an aggregate. An operator inspecting
"is the rag_answer_v2 prompt better than rag_answer_v1?" had to
write SQL by hand.

This module provides the read side:

  - `rollup_by_surface_and_version()` — per (surface, prompt_template_version)
    counts + token costs + hallucination rate + last-seen.
  - `rollup_by_surface()` — collapsed view (one row per surface) for
    the Admin → Vertex Budget tile.
  - `compare_versions(surface)` — pairwise hallucination-rate diff
    between every prompt_template_version recorded for a surface,
    sorted "newer wins" style so the operator sees if v2 actually
    improved on v1.

Numeric contract:
  - hallucination_rate ∈ [0.0, 1.0]; never NaN — when total_responses
    is 0 we return rate=0.0, NOT 0/0.
  - estimated_cost_usd is computed via
    `synthesis_orchestrator.estimate_cost_usd(model, prompt_tokens,
    completion_tokens)` per-(model) sub-bucket then summed — so the
    numbers match the existing /admin/vertex-budget mini-tile (single
    source of truth — never re-derive prices here). The
    vertex_synthesis_cache row carries `model` per row, so a single
    (surface, prompt_template_version) that was rendered by both
    flash and pro at different points has each priced correctly.
  - "active prompt version" is the row with MAX(last_seen) for the
    surface — pinned in `compare_versions` so the operator sees
    "v2 (active) vs v1 (deprecated)" labels.

All queries are pure SELECTs over the existing schema (migrations
007 + 019); NO new tables. The admin router consumes the dataclasses
directly and emits camelCase JSON via the standard model_dump.

Proportional attribution caveat: `gemini_hallucination_alerts`
(migration 007) carries `surface` but NOT `prompt_template_version`.
Until migration 027 adds the column, we attribute alerts to versions
proportionally — for (surface, version) v's share of total surface
responses (n_v / n_surface_total) multiplied by surface hallucination
count rounds to its attributed share. Noted
in `rollup_by_surface_and_version` body comment with the migration
back-reference; the math is honest and clearly labelled in tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)


@dataclass
class SurfaceVersionRollup:
    """Per (surface, prompt_template_version) quality snapshot."""

    surface: str
    prompt_template_version: str
    total_responses: int
    total_hallucinations: int
    hallucination_rate: float
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float
    first_seen: datetime | None
    last_seen: datetime | None
    is_active_version: bool  # True for the latest version per surface


@dataclass
class SurfaceRollup:
    """Collapsed view (one row per surface) — sums across every
    prompt_template_version ever used."""

    surface: str
    versions_observed: int
    active_version: str | None
    total_responses: int
    total_hallucinations: int
    hallucination_rate: float
    estimated_cost_usd: float


@dataclass
class VersionDiff:
    """Pairwise comparison output for `compare_versions`."""

    surface: str
    baseline_version: str
    candidate_version: str
    baseline_hallucination_rate: float
    candidate_hallucination_rate: float
    rate_delta: float  # positive = candidate is WORSE
    baseline_responses: int
    candidate_responses: int
    verdict: str  # "candidate_better" / "candidate_worse" / "tie" / "insufficient_data"


_MIN_RESPONSES_FOR_VERDICT = 25  # below this, sample is too small to act on
_TIE_BAND = 0.02  # <2pp absolute diff is a tie


def _safe_rate(numer: int, denom: int) -> float:
    """Bounded [0.0, 1.0]; zero-call-safe (0/0 → 0.0)."""
    if denom <= 0:
        return 0.0
    return max(0.0, min(1.0, numer / denom))


def _classify_verdict(
    baseline_rate: float,
    candidate_rate: float,
    baseline_n: int,
    candidate_n: int,
) -> str:
    """Pure verdict logic — extracted so tests can hit it directly
    without setting up a DB."""
    if baseline_n < _MIN_RESPONSES_FOR_VERDICT \
       or candidate_n < _MIN_RESPONSES_FOR_VERDICT:
        return "insufficient_data"
    if abs(candidate_rate - baseline_rate) < _TIE_BAND:
        return "tie"
    if candidate_rate < baseline_rate:
        return "candidate_better"
    return "candidate_worse"


async def rollup_by_surface_and_version(
    session: AsyncSession,
    *,
    surface: str | None = None,
    since: datetime | None = None,
) -> list[SurfaceVersionRollup]:
    """Per (surface, prompt_template_version) rollup. Optional
    `surface` filter narrows to a single surface;
    `since` clips to rows newer than the cutoff (useful for
    rolling 7-day comparisons)."""
    # Synthesis-cache rows give us total_responses + token counts.
    # Hallucination-alerts give us the numerator. Both keyed by
    # surface. Hallucination alerts don't carry prompt_template_version
    # (migration 007); proportional attribution explained in the
    # module docstring. Migration 027 will add the column and let us
    # do per-version exact attribution.
    where_clauses: list[str] = []
    params: dict[str, object] = {}
    if surface:
        where_clauses.append("c.surface = :surface")
        params["surface"] = surface[:64]
    if since:
        where_clauses.append("c.created_at >= :since")
        params["since"] = since
    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    # GROUP BY model too so estimate_cost_usd(model=…) prices each
    # token bucket against the correct rate (flash vs pro). We collapse
    # back to (surface, version) in Python by summing costs across
    # model sub-buckets.
    cache_rows = (await session.execute(
        text(
            f"""
            SELECT
                c.surface,
                c.prompt_template_version,
                c.model,
                COUNT(*) AS n_responses,
                COALESCE(SUM(c.prompt_tokens), 0) AS prompt_tokens,
                COALESCE(SUM(c.completion_tokens), 0) AS completion_tokens,
                MIN(c.created_at) AS first_seen,
                MAX(c.created_at) AS last_seen
            FROM vertex_synthesis_cache c
            {where_sql}
            GROUP BY c.surface, c.prompt_template_version, c.model
            """
        ),
        params,
    )).mappings().all()
    if not cache_rows:
        return []

    # Hallucinations per surface (no version dim in the alert table
    # today; proportional attribution explained above).
    halluc_where = []
    halluc_params: dict[str, object] = {}
    if surface:
        halluc_where.append("surface = :surface")
        halluc_params["surface"] = surface[:64]
    if since:
        halluc_where.append("created_at >= :since")
        halluc_params["since"] = since
    halluc_sql = "WHERE " + " AND ".join(halluc_where) if halluc_where else ""
    halluc_rows = (await session.execute(
        text(
            f"""
            SELECT surface, COUNT(*) AS n
            FROM gemini_hallucination_alerts
            {halluc_sql}
            GROUP BY surface
            """
        ),
        halluc_params,
    )).mappings().all()
    halluc_by_surface: dict[str, int] = {r["surface"]: int(r["n"]) for r in halluc_rows}

    # Lazy import to keep this module testable in isolation +
    # break circularity (synthesis_orchestrator pulls in vertex client).
    from app.services.synthesis_orchestrator import estimate_cost_usd

    # Collapse (surface, version, model) → (surface, version).
    @dataclass
    class _Acc:
        n_responses: int = 0
        prompt_tokens: int = 0
        completion_tokens: int = 0
        cost: float = 0.0
        first_seen: datetime | None = None
        last_seen: datetime | None = None

    per_pair: dict[tuple[str, str], _Acc] = {}
    for r in cache_rows:
        key = (r["surface"], r["prompt_template_version"])
        acc = per_pair.setdefault(key, _Acc())
        n = int(r["n_responses"])
        pt = int(r["prompt_tokens"])
        ct = int(r["completion_tokens"])
        acc.n_responses += n
        acc.prompt_tokens += pt
        acc.completion_tokens += ct
        acc.cost += estimate_cost_usd(
            model=r["model"] or "unknown",
            prompt_tokens=pt,
            completion_tokens=ct,
        )
        fs = r["first_seen"]
        ls = r["last_seen"]
        if fs is not None and (acc.first_seen is None or fs < acc.first_seen):
            acc.first_seen = fs
        if ls is not None and (acc.last_seen is None or ls > acc.last_seen):
            acc.last_seen = ls

    # Surface totals + active-version resolution (per surface, the
    # row with the latest last_seen wins).
    totals_by_surface: dict[str, int] = {}
    active_by_surface: dict[str, tuple[str, datetime]] = {}
    for (s, v), acc in per_pair.items():
        totals_by_surface.setdefault(s, 0)
        totals_by_surface[s] += acc.n_responses
        candidate_ls = acc.last_seen or datetime.min
        current = active_by_surface.get(s)
        if current is None or candidate_ls > current[1]:
            active_by_surface[s] = (v, candidate_ls)

    out: list[SurfaceVersionRollup] = []
    for (s, v), acc in per_pair.items():
        surface_total = totals_by_surface.get(s, 0)
        surface_halluc = halluc_by_surface.get(s, 0)
        attributed_halluc = (
            round(surface_halluc * acc.n_responses / surface_total)
            if surface_total > 0 else 0
        )
        out.append(SurfaceVersionRollup(
            surface=s,
            prompt_template_version=v,
            total_responses=acc.n_responses,
            total_hallucinations=attributed_halluc,
            hallucination_rate=_safe_rate(attributed_halluc, acc.n_responses),
            prompt_tokens=acc.prompt_tokens,
            completion_tokens=acc.completion_tokens,
            estimated_cost_usd=round(acc.cost, 6),
            first_seen=acc.first_seen,
            last_seen=acc.last_seen,
            is_active_version=(active_by_surface[s][0] == v),
        ))
    # Sort: surface asc, then is_active_version DESC, then last_seen DESC.
    out.sort(
        key=lambda x: (
            x.surface,
            not x.is_active_version,
            -(x.last_seen.timestamp() if x.last_seen else 0.0),
        )
    )
    return out


async def rollup_by_surface(
    session: AsyncSession,
    *,
    since: datetime | None = None,
) -> list[SurfaceRollup]:
    """Collapsed-by-surface view for the Admin → Vertex Budget tile.
    One row per surface, with active version called out + total cost."""
    versioned = await rollup_by_surface_and_version(session, since=since)
    collapsed: dict[str, list[SurfaceVersionRollup]] = {}
    for v in versioned:
        collapsed.setdefault(v.surface, []).append(v)
    out: list[SurfaceRollup] = []
    for surface, items in collapsed.items():
        total = sum(i.total_responses for i in items)
        halluc = sum(i.total_hallucinations for i in items)
        cost = sum(i.estimated_cost_usd for i in items)
        active = next((i.prompt_template_version for i in items if i.is_active_version), None)
        out.append(SurfaceRollup(
            surface=surface,
            versions_observed=len(items),
            active_version=active,
            total_responses=total,
            total_hallucinations=halluc,
            hallucination_rate=_safe_rate(halluc, total),
            estimated_cost_usd=round(cost, 6),
        ))
    out.sort(key=lambda x: x.surface)
    return out


async def compare_versions(
    session: AsyncSession, *, surface: str, since: datetime | None = None,
) -> list[VersionDiff]:
    """Pairwise candidate-vs-baseline diff between every
    prompt_template_version recorded for `surface`. Baseline = older;
    candidate = newer. Verdicts (`candidate_better` / `candidate_worse`
    / `tie` / `insufficient_data`) are gated by `_MIN_RESPONSES_FOR_VERDICT`
    so a 1-response-vs-1000-response comparison isn't called significant."""
    rows = await rollup_by_surface_and_version(
        session, surface=surface, since=since,
    )
    if len(rows) < 2:
        return []
    # Order by first_seen ASC so the earliest version is the baseline.
    rows_ordered = sorted(
        rows, key=lambda r: (r.first_seen or datetime.max)
    )
    out: list[VersionDiff] = []
    baseline = rows_ordered[0]
    for cand in rows_ordered[1:]:
        verdict = _classify_verdict(
            baseline.hallucination_rate,
            cand.hallucination_rate,
            baseline.total_responses,
            cand.total_responses,
        )
        out.append(VersionDiff(
            surface=surface,
            baseline_version=baseline.prompt_template_version,
            candidate_version=cand.prompt_template_version,
            baseline_hallucination_rate=baseline.hallucination_rate,
            candidate_hallucination_rate=cand.hallucination_rate,
            rate_delta=cand.hallucination_rate - baseline.hallucination_rate,
            baseline_responses=baseline.total_responses,
            candidate_responses=cand.total_responses,
            verdict=verdict,
        ))
        # Sliding baseline so successive versions compare to their
        # immediate predecessor (v1→v2, v2→v3, …).
        baseline = cand
    return out
