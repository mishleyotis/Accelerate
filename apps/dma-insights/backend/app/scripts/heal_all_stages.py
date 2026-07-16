"""All-stages self-healing gate (pipeline layer 3, every surface · all 94).

The firmographics healer (`heal_entities`) guarantees the Overview FIRMOGRAPHICS
panel. This script is the SUPERSET: it heals firmographics AND audits every
rendered surface (Directory, Overview, Insights, Heatmap, Platform, Context,
TechStack, Health) against `completeness_contract` so **no page, card, or
drilldown is empty for any of the 94** on deployment. The per-surface derives
(`apply_catalogue_platforms`, `derive_insights`, `derive_focus_areas`,
`derive_context`, ...) run earlier in the chain and fill their stages; this gate
re-heals firmographics, then asserts the whole picture is complete.

Modes (the self-healing-script contract):
  (default)      heal — fill-if-empty firmographics for every ACTIVE entity,
                 commit, then audit all surfaces.
  --verify-only  audit only (no writes); exit 1 if ANY surface has a
                 data-absence gap for ANY of the 94 (the no-empty-state gate).
  --diagnose     alias of --verify-only.

Usage:
  DATABASE_URL=... python -m app.scripts.heal_all_stages [--verify-only|--diagnose]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from sqlalchemy import text

from app.database import get_sessionmaker
from app.services import startup_enrich as se
from app.services.completeness_contract import (
    SURFACE_CONTRACTS,
    audit_completeness,
    scrub_insight_jargon,
)
from app.services.entity_healing import heal_entity

# insight_depth floors (mirror the completeness contract's insight_depth
# predicate: what_text >= 160, why_text >= 100). When a resolved
# catalogue name is shorter than the code it replaces, a field sitting
# on the floor could dip under it — the heal re-scrubs from the ORIGINAL
# in prefer_fallback mode, which never shrinks text.
_WHAT_FLOOR = 160
_WHY_FLOOR = 100

# Same predicate family as _SURFACE_GAP_SQL["insight_jargon"] (incl. its
# anchor-span stripping — [E-...] citations are structural, never
# rewritten), but returning the card rows to heal instead of the entity
# display_ids.
_JARGON_CARDS_SQL = r"""
    SELECT ic.id::text AS id, ic.title, ic.what_text, ic.why_text, ic.so_what_text
    FROM insight_cards ic
    JOIN runs r ON r.id = ic.run_id AND r.status='ACTIVE'
    JOIN entities e ON e.id = r.entity_id AND e.status='ACTIVE'
    WHERE regexp_replace(ic.what_text, '\[E-[^\]]*\]', '', 'g') ~ 'P[1-4]C[0-9]'
       OR regexp_replace(COALESCE(ic.why_text,''), '\[E-[^\]]*\]', '', 'g') ~ 'P[1-4]C[0-9]'
       OR regexp_replace(COALESCE(ic.so_what_text,''), '\[E-[^\]]*\]', '', 'g') ~ 'P[1-4]C[0-9]'
       OR ic.title ~ 'P[1-4]C[0-9]'
       OR (ic.what_text || ' ' || COALESCE(ic.why_text,'') || ' '
           || COALESCE(ic.so_what_text,'')) ~* 'peer[- ]cohort|priority lever|cross[- ]pillar|the pillar|\yM5\y'
       OR ic.title ~* 'sub-?cap'
"""


async def _load_catalogue_names(session) -> dict[str, str]:
    """{code: business name} from ccg_subcaps + ccg_categories (all
    versions; later versions win). Empty dict on a catalogue-less DB —
    the scrubber then falls back to neutral phrasing."""
    names: dict[str, str] = {}
    for sql in (
        "SELECT category_id AS code, name FROM ccg_categories ORDER BY version",
        "SELECT subcap_id AS code, name FROM ccg_subcaps ORDER BY version",
    ):
        try:
            for row in (await session.execute(text(sql))).all():
                if row.code and row.name:
                    names[str(row.code).strip()] = str(row.name).strip()
        except Exception:  # pragma: no cover - catalogue-less DB
            continue
    return names


async def _heal_insight_jargon(session) -> int:
    """Rewrite jargon-bearing insight_cards to plain business language.

    Deterministic remedy for the insight_jargon gate (see
    completeness_contract.scrub_insight_jargon). Returns cards updated.
    """
    names = await _load_catalogue_names(session)
    rows = (await session.execute(text(_JARGON_CARDS_SQL))).all()
    updated = 0
    for row in rows:
        fields = {
            "title": row.title or "",
            "what_text": row.what_text or "",
            "why_text": row.why_text or "",
            "so_what_text": row.so_what_text or "",
        }
        scrubbed = {k: scrub_insight_jargon(v, names) for k, v in fields.items()}
        if (len(scrubbed["what_text"]) < _WHAT_FLOOR and
                len(fields["what_text"]) >= _WHAT_FLOOR) or \
           (len(scrubbed["why_text"]) < _WHY_FLOOR and
                len(fields["why_text"]) >= _WHY_FLOOR):
            # A short catalogue name shrank a floor-sitting field —
            # re-scrub from the originals in the never-shrink mode.
            scrubbed = {
                k: scrub_insight_jargon(v, names, prefer_fallback=True)
                for k, v in fields.items()
            }
        if scrubbed != fields:
            await session.execute(text(
                "UPDATE insight_cards SET title=:t, what_text=:w, "
                "why_text=:y, so_what_text=:s WHERE id=CAST(:i AS uuid)"
            ), {"t": scrubbed["title"], "w": scrubbed["what_text"],
                "y": scrubbed["why_text"], "s": scrubbed["so_what_text"],
                "i": row.id})
            updated += 1
    return updated


async def _amain() -> int:
    ap = argparse.ArgumentParser(description="All-stages completeness heal + gate")
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--diagnose", action="store_true")
    ap.add_argument("--corpus-dir", default=None)
    args = ap.parse_args()
    verify = args.verify_only or args.diagnose

    if not os.environ.get("DATABASE_URL"):
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2

    sm = get_sessionmaker()
    healed = 0
    subverticals = 0
    firmo_sanitised = 0
    jargon_healed = 0
    errors = 0
    async with sm() as session:
        if not verify:
            # Heal firmographics fill-if-empty + classify any NULL subvertical
            # (other surfaces are filled by their derives earlier in the chain).
            # Per-entity savepoints so one bad value can't roll back the batch.
            rows = (await session.execute(text(
                """
                SELECT e.id::text AS id, e.display_id, e.name, e.drive_folder_id, e.subvertical
                FROM entities e WHERE e.status='ACTIVE' ORDER BY e.display_id
                """
            ))).all()
            for r in rows:
                try:
                    async with session.begin_nested():
                        # heal_entity classifies any NULL subvertical FIRST (so its
                        # subvertical-default regulator fill fires), persists it, and
                        # reports it back — see entity_healing.heal_entity.
                        rep = await heal_entity(
                            session, entity_id=r.id, drive_folder_id=r.drive_folder_id,
                            corpus_dir=args.corpus_dir, dry_run=False, subvertical=r.subvertical,
                            name=r.name,
                        )
                        if rep["filled"]:
                            healed += 1
                        if rep.get("subvertical_classified"):
                            subverticals += 1
                        sv_now = rep.get("subvertical") or (r.subvertical or "").strip()
                        # Firmographics QUALITY sanitise (2026-06-25 Overview
                        # remediation, shared helper): null/repair the fabricated
                        # values the deep audit found — implausible AUM ($103T, or
                        # a 1000x units error '$21M'→$21B recovery), sentinel/
                        # dict-repr regulator ('Role'), out-of-bounds headcount,
                        # dict-repr address. The SAME se.sanitize_firmographics the
                        # offline patcher and the QA gate use, so the canonical DB,
                        # the committed snapshot and the gate all agree. Runs after
                        # heal_entity so it sanitises the final, healed values; the
                        # per-entity savepoint isolates any bad row.
                        fq = (await session.execute(text(
                            "SELECT aum_usd, primary_regulator, headcount, hq_address "
                            "FROM firmographics WHERE entity_id=CAST(:e AS uuid)"
                        ), {"e": r.id})).first()
                        if fq is not None:
                            fd = {
                                "aum_usd": float(fq.aum_usd) if fq.aum_usd is not None else None,
                                "primary_regulator": fq.primary_regulator,
                                "headcount": fq.headcount,
                                "hq_address": fq.hq_address,
                            }
                            if se.sanitize_firmographics(fd, sv_now):
                                await session.execute(text(
                                    "UPDATE firmographics SET aum_usd=:a, "
                                    "primary_regulator=:p, headcount=:h, hq_address=:q "
                                    "WHERE entity_id=CAST(:e AS uuid)"
                                ), {"a": fd["aum_usd"], "p": fd["primary_regulator"],
                                    "h": fd["headcount"], "q": fd["hq_address"], "e": r.id})
                                firmo_sanitised += 1
                except Exception as exc:  # isolate, report, continue
                    errors += 1
                    print(f"  ERROR {r.display_id}: {type(exc).__name__}: {exc}", flush=True)
            # Insight-card jargon heal: the deterministic remedy for the
            # insight_jargon gate (raw taxonomy codes / consultant-speak
            # in user-facing WHAT/WHY/SO-WHAT/title). Runs in heal mode
            # only; --verify-only stays read-only so the qa audit's
            # mutation check holds.
            try:
                jargon_healed = await _heal_insight_jargon(session)
            except Exception as exc:
                errors += 1
                jargon_healed = 0
                print(f"  ERROR insight_jargon heal: {type(exc).__name__}: {exc}",
                      flush=True)
            await session.commit()

        report = await audit_completeness(session)

    print(f"# heal_all_stages: active={report.active} healed_firmographics={healed} "
          f"subverticals_set={subverticals} firmographics_sanitised={firmo_sanitised} "
          f"insight_jargon_healed={jargon_healed if not verify else 'n/a'} "
          f"surface_gaps={report.total_gaps} errors={errors} "
          f"surfaces={len(SURFACE_CONTRACTS)}"
          + (" [VERIFY]" if verify else ""), flush=True)
    for surface in sorted(report.gaps):
        ids = report.gaps[surface]
        print(f"  GAP {surface}: {len(ids)} -> {', '.join(ids[:12])}"
              + (" ..." if len(ids) > 12 else ""), flush=True)
    if errors:
        return 2
    if verify and report.total_gaps:
        return 1
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()
