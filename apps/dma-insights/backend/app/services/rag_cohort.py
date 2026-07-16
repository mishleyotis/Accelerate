"""RAG cohort router — three-mode cohort selection for the RAG API.

Per ADR 0006:
  - `single`        : entity has one subvertical + at most one LOB.
  - `multi_lob`     : entity has one subvertical but ≥2 LOBs.
  - `cross_vertical`: caller forces it, OR entity has multiple subverticals,
                      OR cohort N < 3 within subvertical.

Weights come from `ccg_subvertical_adjacency` (admin-editable, Redis-cached).
Per resolved decision 9 in the plan, weights are *not* hardcoded.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

import redis.asyncio as redis_async
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

CohortMode = Literal["single", "multi_lob", "cross_vertical"]


@dataclass
class EntityProfile:
    entity_id: str | None
    subvertical: str | None
    lobs: list[str] = field(default_factory=list)


@dataclass
class CohortSelection:
    mode: CohortMode
    subvertical: str | None
    lobs: list[str]
    weights: dict[str, float]  # subvertical_code → cohort_match weight
    n_estimated: int


class RagCohortRouter:
    def __init__(
        self,
        session: AsyncSession,
        redis: redis_async.Redis | None = None,
        adjacency_cache_ttl_seconds: int = 60,
    ) -> None:
        self.session = session
        self.redis = redis
        self.cache_ttl = adjacency_cache_ttl_seconds

    async def select(
        self,
        profile: EntityProfile,
        *,
        cross_vertical: str = "auto",  # "auto" | "true" | "false"
        min_cohort_n: int = 3,
    ) -> CohortSelection:
        # Hard caller overrides
        if cross_vertical == "false":
            return await self._single(profile)
        if cross_vertical == "true":
            return await self._cross_vertical(profile, force=True)

        # Auto routing
        if profile.subvertical is None:
            return await self._cross_vertical(profile, force=True)

        if len(profile.lobs) >= 2:
            return await self._multi_lob(profile)

        # Default: single, but escalate to cross_vertical if cohort is tiny.
        single = await self._single(profile)
        if single.n_estimated < min_cohort_n:
            return await self._cross_vertical(profile, force=False)
        return single

    async def _single(self, profile: EntityProfile) -> CohortSelection:
        sv = profile.subvertical
        weights: dict[str, float] = {}
        if sv is not None:
            weights[sv] = 1.0
        n = await self._count_entities_in_subvertical(sv) if sv else 0
        return CohortSelection(
            mode="single",
            subvertical=sv,
            lobs=profile.lobs,
            weights=weights,
            n_estimated=n,
        )

    async def _multi_lob(self, profile: EntityProfile) -> CohortSelection:
        sv = profile.subvertical
        weights: dict[str, float] = {sv: 1.0} if sv else {}
        # LOB-overlap weight applies to *other entities* matching any of these
        # LOBs irrespective of subvertical. We surface that as a synthetic
        # weight slot keyed under "__lob_overlap__".
        if profile.lobs:
            weights["__lob_overlap__"] = 0.7
        n = await self._count_entities_lob_overlap(sv, profile.lobs)
        return CohortSelection(
            mode="multi_lob",
            subvertical=sv,
            lobs=profile.lobs,
            weights=weights,
            n_estimated=n,
        )

    async def _cross_vertical(
        self, profile: EntityProfile, *, force: bool
    ) -> CohortSelection:
        sv = profile.subvertical
        weights = await self._load_adjacency_row(sv)
        n = await self._count_entities_total()
        return CohortSelection(
            mode="cross_vertical",
            subvertical=sv,
            lobs=profile.lobs,
            weights=weights,
            n_estimated=n,
        )

    # ---------- adjacency loader ----------

    async def _load_adjacency_row(self, from_code: str | None) -> dict[str, float]:
        if from_code is None:
            # No anchor — return uniform 0.3 for every known subvertical.
            return await self._load_adjacency_uniform()
        cached = await self._adjacency_cache_get(from_code)
        if cached is not None:
            return cached
        rows = (
            await self.session.execute(
                text(
                    """
                    SELECT to_code, weight
                    FROM ccg_subvertical_adjacency
                    WHERE from_code = :from_code
                    """
                ),
                {"from_code": from_code},
            )
        ).all()
        weights = {to_code: float(weight) for to_code, weight in rows}
        await self._adjacency_cache_put(from_code, weights)
        return weights

    async def _load_adjacency_uniform(self) -> dict[str, float]:
        rows = (
            await self.session.execute(
                text("SELECT code FROM ccg_subverticals WHERE status = 'active'")
            )
        ).all()
        return {row.code: 0.3 for row in rows}

    async def _adjacency_cache_get(self, from_code: str) -> dict[str, float] | None:
        if self.redis is None:
            return None
        raw = await self.redis.get(f"dma:adjacency:{from_code}")
        if raw is None:
            return None
        try:
            return {k: float(v) for k, v in json.loads(raw).items()}
        except (ValueError, TypeError):
            return None

    async def _adjacency_cache_put(self, from_code: str, weights: dict[str, float]) -> None:
        if self.redis is None:
            return
        await self.redis.set(
            f"dma:adjacency:{from_code}",
            json.dumps(weights),
            ex=self.cache_ttl,
        )

    # ---------- cohort size estimators ----------

    async def _count_entities_in_subvertical(self, subvertical: str | None) -> int:
        if subvertical is None:
            return 0
        n = (
            await self.session.execute(
                text(
                    "SELECT COUNT(*) FROM entities "
                    "WHERE subvertical = :sv AND status = 'ACTIVE'"
                ),
                {"sv": subvertical},
            )
        ).scalar_one_or_none()
        return int(n or 0)

    async def _count_entities_lob_overlap(
        self, subvertical: str | None, lobs: list[str]
    ) -> int:
        n = (
            await self.session.execute(
                text(
                    """
                    SELECT COUNT(*) FROM entities
                    WHERE status = 'ACTIVE' AND (
                      subvertical = :sv OR lobs && CAST(:lobs AS varchar[])
                    )
                    """
                ),
                {"sv": subvertical, "lobs": lobs},
            )
        ).scalar_one_or_none()
        return int(n or 0)

    async def _count_entities_total(self) -> int:
        n = (
            await self.session.execute(
                text("SELECT COUNT(*) FROM entities WHERE status = 'ACTIVE'")
            )
        ).scalar_one_or_none()
        return int(n or 0)
