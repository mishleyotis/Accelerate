"""peer_patterns live IO — DB reads + writes.

Called from main.py when --dry-run is NOT set.
"""
from __future__ import annotations

import json

from sqlalchemy import text

from app.database import get_sessionmaker
from workers.peer_patterns.service import EntityVector, compute_archetypes


async def run(
    *, subvertical: str | None, all_subverticals: bool,
    catalogue_version: str | None,
) -> dict:
    sm = get_sessionmaker()
    summary = {"subverticals_processed": 0, "archetypes_written": 0}
    async with sm() as session:
        # Determine target subverticals
        if all_subverticals:
            rows = (
                await session.execute(
                    text(
                        "SELECT DISTINCT e.subvertical FROM entities e "
                        "JOIN runs r ON r.entity_id = e.id "
                        "WHERE r.status = 'ACTIVE' AND e.subvertical IS NOT NULL"
                    )
                )
            ).all()
            svs = [r.subvertical for r in rows]
        else:
            svs = [subvertical] if subvertical else []
        for sv in svs:
            ver = catalogue_version or await _resolve_version(session, sv)
            if not ver:
                continue
            entities = await _fetch_cohort(session, sv, ver)
            archetypes = compute_archetypes(entities)
            await _persist(session, sv, ver, archetypes)
            summary["subverticals_processed"] += 1
            summary["archetypes_written"] += len(archetypes)
        await session.commit()
    print(json.dumps(summary, indent=2))
    return summary


async def _resolve_version(session, sv: str) -> str | None:
    row = (
        await session.execute(
            text(
                "SELECT r.ccg_catalog_version FROM runs r "
                "JOIN entities e ON e.id = r.entity_id "
                "WHERE r.status = 'ACTIVE' AND e.subvertical = :sv "
                "ORDER BY r.completed_at DESC NULLS LAST LIMIT 1"
            ),
            {"sv": sv},
        )
    ).first()
    return row.ccg_catalog_version if row else None


async def _fetch_cohort(
    session, sv: str, ver: str,
) -> list[EntityVector]:
    rows = (
        await session.execute(
            text(
                """
                SELECT e.id::text AS eid,
                       array_agg(s.subcap_id ORDER BY s.subcap_id) AS subcaps,
                       array_agg(s.score::float ORDER BY s.subcap_id) AS scores
                FROM entities e
                JOIN runs r ON r.entity_id = e.id
                JOIN subcap_scores s ON s.run_id = r.id
                WHERE r.status = 'ACTIVE'
                  AND e.subvertical = :sv
                  AND r.ccg_catalog_version = :ver
                GROUP BY e.id
                """
            ),
            {"sv": sv, "ver": ver},
        )
    ).all()
    return [
        EntityVector(entity_id=r.eid, subcap_ids=list(r.subcaps),
                     scores=list(r.scores))
        for r in rows
    ]


async def _persist(session, sv: str, ver: str, archetypes) -> None:
    # Delete prior archetypes for this (subvertical, version) — full
    # rewrite is simpler than diffing and the table is small (≤6 rows
    # per subvertical).
    await session.execute(
        text(
            "DELETE FROM peer_archetypes "
            "WHERE subvertical = :sv AND catalogue_version = :ver"
        ),
        {"sv": sv, "ver": ver},
    )
    for a in archetypes:
        await session.execute(
            text(
                """
                INSERT INTO peer_archetypes
                    (subvertical, catalogue_version, archetype_label,
                     centroid_vector, defining_subcap_ids,
                     entity_ids_in_archetype, sample_count, silhouette_score)
                VALUES
                    (:sv, :ver, :lbl,
                     CAST(:centroid AS numeric[]),
                     CAST(:defining AS varchar[]),
                     CAST(:members AS uuid[]),
                     :n, :sil)
                """
            ),
            {
                "sv": sv, "ver": ver, "lbl": a.label,
                "centroid": a.centroid,
                "defining": a.defining_subcap_ids,
                "members": a.member_entity_ids,
                "n": a.sample_count, "sil": a.silhouette,
            },
        )
