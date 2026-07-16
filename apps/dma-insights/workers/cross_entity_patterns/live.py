"""cross_entity_patterns live IO — DB reads + writes.

Called from main.py when --dry-run is NOT set. Mirrors peer_patterns/live.py:
per (subvertical, catalogue_version) cohort, fetch the gap + open-issue
signals, compute the recurring patterns, and full-rewrite the cohort's rows.
"""
from __future__ import annotations

import json

from sqlalchemy import text

from app.database import get_sessionmaker
from workers.cross_entity_patterns.service import (
    GapRow,
    IssueRow,
    compute_patterns,
)


async def run(
    *, subvertical: str | None, all_subverticals: bool,
    catalogue_version: str | None,
) -> dict:
    sm = get_sessionmaker()
    summary = {"subverticals_processed": 0, "patterns_written": 0}
    async with sm() as session:
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
            entity_ids, gaps, issues, names = await _fetch_cohort(session, sv, ver)
            if not entity_ids:
                continue
            patterns = compute_patterns(
                entity_ids=entity_ids, gaps=gaps, issues=issues, names=names,
            )
            await _persist(session, sv, ver, patterns)
            summary["subverticals_processed"] += 1
            summary["patterns_written"] += len(patterns)
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


async def _fetch_cohort(session, sv: str, ver: str):
    ent_rows = (
        await session.execute(
            text(
                "SELECT e.id::text AS eid FROM entities e "
                "JOIN runs r ON r.entity_id = e.id "
                "WHERE r.status = 'ACTIVE' AND e.subvertical = :sv "
                "AND r.ccg_catalog_version = :ver"
            ),
            {"sv": sv, "ver": ver},
        )
    ).all()
    entity_ids = {r.eid for r in ent_rows}

    gap_rows = (
        await session.execute(
            text(
                """
                SELECT e.id::text AS eid, s.subcap_id AS subcap_id,
                       s.peer_gap::float AS peer_gap
                FROM subcap_scores s
                JOIN runs r ON r.id = s.run_id
                JOIN entities e ON e.id = r.entity_id
                WHERE r.status = 'ACTIVE' AND e.subvertical = :sv
                  AND r.ccg_catalog_version = :ver
                  AND s.peer_gap IS NOT NULL
                """
            ),
            {"sv": sv, "ver": ver},
        )
    ).all()
    gaps = [
        GapRow(entity_id=r.eid, subcap_id=r.subcap_id, peer_gap=r.peer_gap)
        for r in gap_rows
    ]

    issue_rows = (
        await session.execute(
            text(
                """
                SELECT e.id::text AS eid, sc AS subcap_id, i.severity AS severity
                FROM issue_register i
                JOIN runs r ON r.id = i.run_id
                JOIN entities e ON e.id = r.entity_id
                CROSS JOIN LATERAL unnest(i.linked_subcap_ids) AS sc
                WHERE r.status = 'ACTIVE' AND e.subvertical = :sv
                  AND r.ccg_catalog_version = :ver
                  AND i.resolved_on IS NULL
                """
            ),
            {"sv": sv, "ver": ver},
        )
    ).all()
    issues = [
        IssueRow(entity_id=r.eid, subcap_id=r.subcap_id, severity=r.severity or "")
        for r in issue_rows
    ]

    name_rows = (
        await session.execute(
            text("SELECT subcap_id, name FROM ccg_subcaps WHERE version = :ver"),
            {"ver": ver},
        )
    ).all()
    names = {r.subcap_id: r.name for r in name_rows}

    return entity_ids, gaps, issues, names


async def _persist(session, sv: str, ver: str, patterns) -> None:
    # Full rewrite per (subvertical, version) — simpler than diffing and the
    # table is tiny (a handful of rows per cohort).
    await session.execute(
        text(
            "DELETE FROM cross_entity_patterns "
            "WHERE subvertical = :sv AND catalogue_version = :ver"
        ),
        {"sv": sv, "ver": ver},
    )
    for p in patterns:
        await session.execute(
            text(
                """
                INSERT INTO cross_entity_patterns
                    (subvertical, catalogue_version, pattern_type, pattern_key,
                     pattern_label, primary_subcap_id, entity_count,
                     affected_entity_ids, severity_mix, median_peer_gap,
                     sample_subcap_ids)
                VALUES
                    (:sv, :ver, :pt, :pk, :lbl, :psc, :n,
                     CAST(:members AS uuid[]), CAST(:sevmix AS jsonb),
                     :mpg, CAST(:samples AS varchar[]))
                """
            ),
            {
                "sv": sv, "ver": ver, "pt": p.pattern_type, "pk": p.pattern_key,
                "lbl": p.pattern_label, "psc": p.primary_subcap_id,
                "n": p.entity_count, "members": p.affected_entity_ids,
                "sevmix": json.dumps(p.severity_mix),
                "mpg": p.median_peer_gap, "samples": p.sample_subcap_ids,
            },
        )
