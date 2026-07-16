"""Thin-evidence alert producer (wireframe `buildAlerts` contract).

QA audit 2026-06-11: nothing wrote the `alerts` table — 0 rows for the
whole corpus while 53k subcap rows carried `is_thin_evidence=TRUE`.
The wireframe (01_data.js `buildAlerts`) derives one OPEN alert per
thin subcap of the entity's current run: severity HIGH when zero
evidence rows support it, MEDIUM when exactly one; recommended action
PROXY_ESCALATION (0) / TIER_UPGRADE (1).

Volume control: the real corpus's thin-rate is ~84% (sparse evidence
mappings in early packages), so a literal per-subcap derivation floods
~560 alerts per entity. Contract here:

  - per-subcap alert when the category carries ≤ AGG_THRESHOLD thin
    subcaps (content_key = subcap_id);
  - ONE aggregated alert per category above that (content_key =
    ``CAT:{category_id}``), severity = worst member, linked_subcap_ids
    capped at LINK_CAP.

State branches:
  derived            → row INSERTed (kind THIN_EVIDENCE, OPEN)
  waived_previously  → content_key has a CLOSED row for the entity —
                       skipped, a waive/escalate decision is never
                       resurrected by a re-derive
  re_derive          → all OPEN THIN_EVIDENCE rows for the entity are
                       DELETEd first (derived state, not user data),
                       then re-INSERTed from the current ACTIVE run
  no_thin_rows       → DELETE still runs (a re-ingest that fixed
                       evidence clears stale alerts), 0 inserts

Called from `package_persist.persist_package` (same transaction — the
caller commits) and from `app.scripts.derive_alerts` for the corpus
backfill. Pure SQL via the session; no ORM models.
"""
from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()

AGG_THRESHOLD = 5
LINK_CAP = 50
KIND = "THIN_EVIDENCE"


async def derive_thin_evidence_alerts(
    session: AsyncSession, *, run_id: str, entity_id: str,
) -> dict[str, int]:
    """Materialize THIN_EVIDENCE alerts for one run. Returns counters."""
    rows = (
        await session.execute(
            text(
                """
                SELECT s.subcap_id,
                       COALESCE(s.parent_category_id,
                                LEFT(s.subcap_id, 4)) AS category_id,
                       COALESCE(cs.name, s.subcap_id)  AS subcap_name,
                       COALESCE(ec.n, 0)               AS evidence_count
                FROM subcap_scores s
                LEFT JOIN ccg_subcaps cs
                       ON cs.subcap_id = s.subcap_id
                LEFT JOIN (
                    SELECT unnest(linked_subcap_ids) AS subcap_id,
                           COUNT(*) AS n
                    FROM evidence_index
                    WHERE run_id = CAST(:rid AS uuid)
                    GROUP BY 1
                ) ec ON ec.subcap_id = s.subcap_id
                WHERE s.run_id = CAST(:rid AS uuid)
                  AND s.is_thin_evidence
                """
            ),
            {"rid": run_id},
        )
    ).all()

    # Waive-preservation: a content_key the operator already closed for
    # this entity must not come back as a fresh OPEN row.
    closed_keys = {
        r.content_key
        for r in (
            await session.execute(
                text(
                    """
                    SELECT DISTINCT content_key FROM alerts
                    WHERE entity_id = CAST(:eid AS uuid)
                      AND kind = :kind
                      AND closed_at IS NOT NULL
                      AND content_key IS NOT NULL
                    """
                ),
                {"eid": entity_id, "kind": KIND},
            )
        ).all()
    }

    # Re-derive semantics: OPEN thin-evidence alerts are derived state.
    await session.execute(
        text(
            """
            DELETE FROM alerts
            WHERE entity_id = CAST(:eid AS uuid)
              AND kind = :kind
              AND closed_at IS NULL
            """
        ),
        {"eid": entity_id, "kind": KIND},
    )

    by_category: dict[str, list[Any]] = {}
    for r in rows:
        by_category.setdefault(r.category_id, []).append(r)

    inserted = 0
    skipped_closed = 0

    async def _insert(params: dict[str, Any]) -> None:
        await session.execute(
            text(
                """
                INSERT INTO alerts (
                    entity_id, run_id, kind, severity, title, body,
                    linked_subcap_ids, evidence_count,
                    recommended_action, proxy_searched, content_key
                ) VALUES (
                    CAST(:eid AS uuid), CAST(:rid AS uuid), :kind, :sev,
                    :title, :body, :subcaps, :ec, :action, :proxy, :key
                )
                """
            ),
            params,
        )

    for category_id, members in sorted(by_category.items()):
        if len(members) > AGG_THRESHOLD:
            key = f"CAT:{category_id}"
            if key in closed_keys:
                skipped_closed += 1
                continue
            zero = [m for m in members if m.evidence_count == 0]
            sev = "high" if zero else "medium"
            action = "PROXY_ESCALATION" if zero else "TIER_UPGRADE"
            ids = [m.subcap_id for m in members][:LINK_CAP]
            await _insert({
                "eid": entity_id, "rid": run_id, "kind": KIND, "sev": sev,
                "title": (
                    f"Thin evidence across {len(members)} subcaps "
                    f"in {category_id}"
                ),
                "body": (
                    f"{len(members)} subcaps in {category_id} are "
                    f"supported by fewer than 2 evidence rows in the "
                    f"active run ({len(zero)} with none). "
                    f"Recommended action: {action}."
                ),
                "subcaps": ids, "ec": min(
                    (m.evidence_count for m in members), default=0,
                ),
                "action": action, "proxy": False, "key": key,
            })
            inserted += 1
        else:
            for m in members:
                if m.subcap_id in closed_keys:
                    skipped_closed += 1
                    continue
                sev = "high" if m.evidence_count == 0 else "medium"
                action = (
                    "PROXY_ESCALATION" if m.evidence_count == 0
                    else "TIER_UPGRADE"
                )
                await _insert({
                    "eid": entity_id, "rid": run_id, "kind": KIND,
                    "sev": sev,
                    "title": f"Thin evidence: {m.subcap_name}",
                    "body": (
                        f"Only {m.evidence_count} evidence row(s) "
                        f"support {m.subcap_id} in the active run. "
                        f"Recommended action: {action}."
                    ),
                    "subcaps": [m.subcap_id],
                    "ec": int(m.evidence_count),
                    "action": action,
                    "proxy": bool(m.evidence_count > 1),
                    "key": m.subcap_id,
                })
                inserted += 1

    counters = {
        "thin_subcaps": len(rows),
        "alerts_inserted": inserted,
        "skipped_closed": skipped_closed,
        "categories": len(by_category),
    }
    log.info("alerts_producer.derived", entity_id=str(entity_id), **counters)
    return counters
