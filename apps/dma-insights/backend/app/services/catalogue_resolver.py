"""CatalogueResolver — single source of truth for catalogue lookups.

Every API/UI surface that touches a `subcap_id` reads through this service.
It handles:

  1. Per-run catalogue version pinning (`runs.ccg_catalog_version`).
  2. Cross-version alias bridging via `ccg_subcap_aliases` (a v5.0 score
     renders against v7.0 IDs at view time).
  3. In-process LRU cache + Redis read-through cache (60s default) for hot
     reads of `ccg_subcaps`, `ccg_categories`, `ccg_pillars`, etc.
  4. Bulk resolution helper used by heatmap / scoring endpoints (avoids N+1).

The resolver is *not* the loader — see workers/ccg_loader for ingest.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import redis.asyncio as redis_async
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class ResolvedSubcap:
    version: str
    subcap_id: str
    l1_id: str
    name: str
    description: str
    solution_type: str
    tier: str
    aliased_from_version: str | None = None
    aliased_from_subcap_id: str | None = None
    migration_action: str | None = None

    @property
    def was_aliased(self) -> bool:
        return self.aliased_from_subcap_id is not None


@dataclass(frozen=True)
class SubcapNotFound:
    requested_version: str
    requested_subcap_id: str
    reason: str


SubcapResult = ResolvedSubcap | SubcapNotFound


class CatalogueResolver:
    """One instance per request scope (held by FastAPI dependency)."""

    def __init__(
        self,
        session: AsyncSession,
        redis: redis_async.Redis | None = None,
        cache_ttl_seconds: int = 60,
    ) -> None:
        self.session = session
        self.redis = redis
        self.cache_ttl_seconds = cache_ttl_seconds
        self._memo: dict[tuple[str, str], SubcapResult] = {}

    async def resolve_subcap(
        self,
        scoring_subcap_id: str,
        run_catalog_version: str,
    ) -> SubcapResult:
        """Resolve a stored subcap_id against a target catalogue version.

        Strategy:
          1. Try (run_catalog_version, scoring_subcap_id) directly.
          2. If not found, look in ccg_subcap_aliases for a translation.
          3. Re-query the resolved (current_version, current_subcap_id).
          4. Return ResolvedSubcap or SubcapNotFound (never raises).
        """
        memo_key = (run_catalog_version, scoring_subcap_id)
        if memo_key in self._memo:
            return self._memo[memo_key]

        cached = await self._cache_get(memo_key)
        if cached is not None:
            self._memo[memo_key] = cached
            return cached

        direct = await self._fetch_subcap(run_catalog_version, scoring_subcap_id)
        if direct is not None:
            result: SubcapResult = direct
            await self._cache_put(memo_key, result)
            self._memo[memo_key] = result
            return result

        # Try alias bridge — note alias rows describe `prior → current`, so we
        # match prior_subcap_id and read current_*.
        row = (
            await self.session.execute(
                text(
                    """
                    SELECT current_version, current_subcap_id, migration_action
                    FROM ccg_subcap_aliases
                    WHERE prior_subcap_id = :sid
                    ORDER BY (current_version = :ver) DESC, current_version DESC
                    LIMIT 1
                    """
                ),
                {"sid": scoring_subcap_id, "ver": run_catalog_version},
            )
        ).first()

        if row is None:
            miss = SubcapNotFound(
                requested_version=run_catalog_version,
                requested_subcap_id=scoring_subcap_id,
                reason="no direct match and no alias bridge entry",
            )
            await self._cache_put(memo_key, miss)
            self._memo[memo_key] = miss
            return miss

        current_version, current_subcap_id, migration_action = row
        target = await self._fetch_subcap(current_version, current_subcap_id)
        if target is None:
            miss = SubcapNotFound(
                requested_version=run_catalog_version,
                requested_subcap_id=scoring_subcap_id,
                reason=f"alias pointed to {current_version}:{current_subcap_id} but row missing",
            )
            await self._cache_put(memo_key, miss)
            self._memo[memo_key] = miss
            return miss

        resolved = ResolvedSubcap(
            version=target.version,
            subcap_id=target.subcap_id,
            l1_id=target.l1_id,
            name=target.name,
            description=target.description,
            solution_type=target.solution_type,
            tier=target.tier,
            aliased_from_version=run_catalog_version,
            aliased_from_subcap_id=scoring_subcap_id,
            migration_action=migration_action,
        )
        await self._cache_put(memo_key, resolved)
        self._memo[memo_key] = resolved
        return resolved

    async def resolve_bulk(
        self,
        scoring_subcap_ids: list[str],
        run_catalog_version: str,
    ) -> dict[str, SubcapResult]:
        """Bulk resolution — minimizes DB round-trips for heatmap renders."""
        out: dict[str, SubcapResult] = {}
        for sid in scoring_subcap_ids:
            out[sid] = await self.resolve_subcap(sid, run_catalog_version)
        return out

    async def _fetch_subcap(
        self, version: str, subcap_id: str
    ) -> ResolvedSubcap | None:
        row = (
            await self.session.execute(
                text(
                    """
                    SELECT version, subcap_id, l1_id, name, description,
                           solution_type, tier
                    FROM ccg_subcaps
                    WHERE version = :ver AND subcap_id = :sid
                    """
                ),
                {"ver": version, "sid": subcap_id},
            )
        ).first()
        if row is None:
            return None
        return ResolvedSubcap(
            version=row.version,
            subcap_id=row.subcap_id,
            l1_id=row.l1_id,
            name=row.name,
            description=row.description,
            solution_type=row.solution_type,
            tier=row.tier,
        )

    # ---------- Redis cache helpers ----------

    def _cache_key(self, key: tuple[str, str]) -> str:
        version, subcap = key
        return f"dma:catalogue:resolve:{version}:{subcap}"

    async def _cache_get(self, key: tuple[str, str]) -> SubcapResult | None:
        if self.redis is None:
            return None
        raw = await self.redis.get(self._cache_key(key))
        if raw is None:
            return None
        try:
            obj = json.loads(raw)
            if obj.get("__kind__") == "miss":
                return SubcapNotFound(
                    requested_version=obj["requested_version"],
                    requested_subcap_id=obj["requested_subcap_id"],
                    reason=obj["reason"],
                )
            return ResolvedSubcap(**{k: v for k, v in obj.items() if k != "__kind__"})
        except (ValueError, TypeError, KeyError):
            return None

    async def _cache_put(self, key: tuple[str, str], value: SubcapResult) -> None:
        if self.redis is None:
            return
        payload: dict[str, Any]
        if isinstance(value, SubcapNotFound):
            payload = {
                "__kind__": "miss",
                "requested_version": value.requested_version,
                "requested_subcap_id": value.requested_subcap_id,
                "reason": value.reason,
            }
        else:
            payload = {
                "__kind__": "hit",
                "version": value.version,
                "subcap_id": value.subcap_id,
                "l1_id": value.l1_id,
                "name": value.name,
                "description": value.description,
                "solution_type": value.solution_type,
                "tier": value.tier,
                "aliased_from_version": value.aliased_from_version,
                "aliased_from_subcap_id": value.aliased_from_subcap_id,
                "migration_action": value.migration_action,
            }
        await self.redis.set(
            self._cache_key(key), json.dumps(payload), ex=self.cache_ttl_seconds
        )
