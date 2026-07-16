"""Tech-stack taxonomy heal, grounding + report backfill (self-healing).

The 2026-06 tech-stack audit measured ~224 noise rows shipped verbatim
into ``tech_stack_entries`` (21 programming languages, 4 operating
systems, ~25 generic labels, ~124 prose fragments — including a person
and a bare date) because the parsers persisted source cells as-is. The
parse path is now gated by ``nlp.taxonomy`` via
``package_techstack.sanitize_tech_rows``; THIS script runs the exact
same gate over the EXISTING corpus so the derive chain heals the seeded
DB without a full re-ingest.

Per ACTIVE entity, for every stored row (split_cell → classify):

  noise               → DELETE (languages/OS handled below; prose,
                        persons, dates, generic labels die here).
  platform            → canonicalise IN PLACE (taxonomy vendor +
                        canonical product + layer_hint + l3 link), or
                        REPLACE the row with one row per canonical
                        platform when the cell held several.
  engineering_signal  → keep, flagged status='ENGINEERING_SIGNAL'
                        (excluded from the AE platform surface by the
                        router — proof the entity builds software).
  unknown_vendor      → keep, flagged status='UNKNOWN_VENDOR' (review
                        queue; not AE-rendered).

Then (carried over from the original cleanup): backfill real tech named
in the report prose for thinned entities, and ground every entry with
evidence E-IDs + the capability subcaps its platform family addresses.

Legacy free-form statuses ('active') are normalised onto the stored
enum (evidence-backed → CONFIRMED, else DETECTED — mirrors migration
044). Idempotent: canonical/flagged rows re-classify to themselves, so
a second run is a no-op.

Usage: DATABASE_URL=... python -m app.scripts.clean_techstack
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from collections import Counter

from sqlalchemy import text

from app.database import get_sessionmaker
from app.schemas.package import TechStackRow
from app.services.parsers.package_techstack import (
    STATUS_ENGINEERING_SIGNAL,
    STATUS_UNKNOWN_VENDOR,
    sanitize_tech_rows,
)
from app.services.parsers.tech_linker import _TECH

# Metadata labels the Explorium ingest turned into "vendors" — kept as a
# cheap pre-filter (the taxonomy classifies most of these as noise too,
# but the sheet-metadata labels below aren't all in its deny-list).
# Extended per Part 9.2 with the audit's generic-label families.
_JUNK = re.compile(
    r"^(source|discovery method|data sources?|confidence framework|deployment status|"
    r"reconciliation|notes?|status|tier|category|layer|vendor|product|evidence|method|"
    r"type|date|summary|overview|legend|key|total|n/?a|tbd|unknown|placeholder|sample|—|-|\s*|"
    r"various|other|none|misc(ellaneous)?|software|technology|tools|general|internal|"
    r"unspecified( vendor)?|multiple|see notes?|not specified|not applicable)$",
    re.I,
)

_STORED_ENUM = frozenset({
    "DETECTED", "CONFIRMED", "CONFIRMED_REMOVED",
    STATUS_ENGINEERING_SIGNAL, STATUS_UNKNOWN_VENDOR,
})
_VALID_LAYERS = frozenset({"foundation", "platform", "application", "intelligence"})

# E-ID token shape. `evidence_index.e_id` cells are not always a single
# clean id: some hold multi-value strings ("E-023, E-036"), factor-annotated
# ids ("E-024:F5"), or truncated stubs ("E-"). Extracting the canonical
# `E-<alnum>` token from each cell drops the `:F5` suffix, splits multi-value
# cells, and discards empties — the 2026-07-06 clean_techstack crash was a
# malformed PG array literal built by bare-joining those dirty cells.
_EID_TOKEN_RE = re.compile(r"E-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*")


def _clean_eids(raw: list[str]) -> list[str]:
    """Canonical, de-duplicated E-ID tokens mined from raw evidence cells."""
    out: list[str] = []
    seen: set[str] = set()
    for cell in raw:
        for tok in _EID_TOKEN_RE.findall(cell or ""):
            if tok not in seen:
                seen.add(tok)
                out.append(tok)
    return out


def _pg_text_array(values: list[str]) -> str:
    """A Postgres text[] array literal with every element double-quoted, so a
    comma / colon / space inside a value can never corrupt the literal.
    Returns "" (the UPDATE's no-op sentinel) when there is nothing to write."""
    clean = [v.strip() for v in values if v and v.strip()]
    if not clean:
        return ""
    esc = [v.replace("\\", "\\\\").replace('"', '\\"') for v in clean]
    return "{" + ",".join(f'"{v}"' for v in esc) + "}"


def normalize_stored_status(status: str | None, has_evidence: bool) -> str:
    """Legacy free-form statuses → the stored enum (mirrors migration 044)."""
    s = (status or "").strip().upper()
    if s in _STORED_ENUM:
        return s
    return "CONFIRMED" if has_evidence else "DETECTED"


def plan_heal(
    *, vendor: str | None, product: str | None, status: str | None,
    source: str | None, has_evidence: bool,
) -> list[TechStackRow]:
    """Pure heal decision for one stored row — the SAME taxonomy gate the
    parse path runs (``sanitize_tech_rows``), so parse and heal can never
    disagree. Returns the desired canonical/flagged rows; [] ⇒ delete."""
    v = (vendor or "").strip()
    if not v or _JUNK.match(v):
        return []
    return sanitize_tech_rows([TechStackRow(
        vendor=v[:128],
        product=(product or v)[:255],
        source=(source or "Explorium")[:64],
        status=normalize_stored_status(status, has_evidence),
    )])


def _tech_id(vendor: str, product: str | None) -> str:
    """Persist-path tech_id convention (package_persist)."""
    return re.sub(r"[^A-Za-z0-9]+", "_", f"{vendor}_{product or ''}")[:64]


async def _status_distribution(session) -> Counter:
    rows = (await session.execute(text(
        "SELECT status, COUNT(*) FROM tech_stack_entries GROUP BY status"
    ))).all()
    return Counter({r[0]: r[1] for r in rows})


async def _noise_count(session) -> int:
    """Audit acceptance counter (target 0 after heal): rows on the RENDERED
    (non-flagged) surface that the taxonomy gate rejects outright — prose /
    persons / dates / generic labels (plan → delete) and languages / OS
    (plan → engineering-signal flag only). Legit unknown vendors are NOT
    noise; they move to the review queue."""
    rows = (await session.execute(text(
        "SELECT vendor, product, status, source, "
        "       COALESCE(cardinality(evidence_e_ids), 0) > 0 AS has_ev "
        "FROM tech_stack_entries WHERE status NOT IN (:es, :uv)"
    ), {"es": STATUS_ENGINEERING_SIGNAL, "uv": STATUS_UNKNOWN_VENDOR})).all()
    n = 0
    for r in rows:
        desired = plan_heal(
            vendor=r.vendor, product=r.product, status=r.status,
            source=r.source, has_evidence=bool(r.has_ev),
        )
        if not desired or all(
            d.status == STATUS_ENGINEERING_SIGNAL for d in desired
        ):
            n += 1
    return n


async def _amain() -> int:
    if not os.environ.get("DATABASE_URL"):
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2
    sm = get_sessionmaker()
    deleted = canonicalised = replaced = flagged = backfilled = 0
    ev_linked = sub_linked = 0
    async with sm() as session:
        before_noise = await _noise_count(session)
        before_dist = await _status_distribution(session)

        rows = (await session.execute(text(
            "SELECT e.id::text eid, e.display_id, r.id::text rid "
            "FROM entities e JOIN runs r ON r.entity_id=e.id AND r.status='ACTIVE' "
            "WHERE e.status='ACTIVE' ORDER BY e.display_id"
        ))).all()

        for row in rows:
            # ── 1) taxonomy heal per stored row ────────────────────────
            cur = (await session.execute(text(
                "SELECT id::text id, tech_id, vendor, product, layer, status, "
                "       source, detected_at, "
                "       COALESCE(cardinality(evidence_e_ids), 0) > 0 AS has_ev "
                "FROM tech_stack_entries WHERE entity_id=CAST(:e AS uuid)"
            ), {"e": row.eid})).all()
            present_ids = {t.tech_id for t in cur}
            present: set[str] = set()

            for t in cur:
                desired = plan_heal(
                    vendor=t.vendor, product=t.product, status=t.status,
                    source=t.source, has_evidence=bool(t.has_ev),
                )
                if not desired:
                    await session.execute(
                        text("DELETE FROM tech_stack_entries WHERE id=CAST(:id AS uuid)"),
                        {"id": t.id},
                    )
                    present_ids.discard(t.tech_id)
                    deleted += 1
                    continue

                def _keep_layer(d: TechStackRow, current: str | None) -> str:
                    if d.layer in _VALID_LAYERS:
                        return d.layer  # taxonomy layer_hint
                    return current if current in _VALID_LAYERS else "application"

                def _mark_present(d: TechStackRow, _present=present) -> None:
                    # Track BOTH the taxonomy vendor ("Early Warning
                    # Services") and the canonical product ("Zelle") so the
                    # prose backfill below never re-inserts a vendor the
                    # heal just canonicalised under its taxonomy owner.
                    if d.status not in (STATUS_ENGINEERING_SIGNAL,
                                        STATUS_UNKNOWN_VENDOR):
                        _present.add(d.vendor.strip().lower())
                        if d.product:
                            _present.add(d.product.strip().lower())

                if len(desired) == 1 and (
                    desired[0].vendor.strip().lower() == (t.vendor or "").strip().lower()
                    and (desired[0].product or "").strip().lower()
                    == (t.product or "").strip().lower()
                ):
                    # Same tech — canonicalise/flag in place (keeps id,
                    # grounding arrays and detected_at). The UPDATE's WHERE
                    # guard makes re-runs no-ops.
                    d = desired[0]
                    new_layer = _keep_layer(d, t.layer)
                    res = await session.execute(text(
                        "UPDATE tech_stack_entries SET "
                        "  status=:st, layer=:l, "
                        "  l3_id=COALESCE(CAST(:l3 AS varchar), l3_id) "
                        "WHERE id=CAST(:id AS uuid) "
                        "AND (status != :st OR layer != :l OR "
                        "     l3_id IS DISTINCT FROM COALESCE(CAST(:l3 AS varchar), l3_id))"
                    ), {"st": d.status, "l": new_layer,
                        "l3": d.l3_id, "id": t.id})
                    if res.rowcount:
                        if d.status in (STATUS_ENGINEERING_SIGNAL,
                                        STATUS_UNKNOWN_VENDOR):
                            flagged += 1
                        else:
                            canonicalised += 1
                    _mark_present(d)
                    continue

                # Different canonical shape (renamed / multi-vendor cell) —
                # replace the row with the canonical rows.
                await session.execute(
                    text("DELETE FROM tech_stack_entries WHERE id=CAST(:id AS uuid)"),
                    {"id": t.id},
                )
                present_ids.discard(t.tech_id)
                replaced += 1
                for d in desired:
                    _mark_present(d)
                    tid = _tech_id(d.vendor, d.product)
                    if tid in present_ids:
                        continue
                    present_ids.add(tid)
                    res = await session.execute(text(
                        "INSERT INTO tech_stack_entries "
                        "  (entity_id, tech_id, vendor, product, layer, status, "
                        "   source, l3_id, detected_at) "
                        "VALUES (CAST(:e AS uuid), :tid, :v, :p, :l, :st, :src, "
                        "        :l3, COALESCE(:dt, NOW())) "
                        "ON CONFLICT (entity_id, tech_id) DO NOTHING"
                    ), {"e": row.eid, "tid": tid, "v": d.vendor[:128],
                        "p": (d.product or d.vendor)[:255],
                        "l": _keep_layer(d, t.layer), "st": d.status,
                        "src": (d.source or t.source or "Explorium")[:64],
                        "l3": d.l3_id, "dt": t.detected_at})
                    if res.rowcount and d.status in (
                        STATUS_ENGINEERING_SIGNAL, STATUS_UNKNOWN_VENDOR,
                    ):
                        flagged += 1

            # ── 2) backfill real tech named in the report prose ────────
            prose = (await session.execute(text(
                "SELECT string_agg(body, ' ') FROM document_sections WHERE run_id=CAST(:rid AS uuid)"
            ), {"rid": row.rid})).scalar() or ""
            for vendor, (layer, _fam) in _TECH.items():
                if vendor.lower() in present:
                    continue
                if not re.search(rf"\b{re.escape(vendor)}\b", prose):
                    continue
                # Insert the CANONICAL form straight away (same taxonomy
                # gate as everything else) so the next pass is a no-op —
                # e.g. a prose "Zelle" lands as vendor 'Early Warning
                # Services' / product 'Zelle' immediately.
                for d in plan_heal(vendor=vendor, product=None,
                                   status="DETECTED", source="report_mention",
                                   has_evidence=False):
                    if (
                        d.status in (STATUS_ENGINEERING_SIGNAL,
                                     STATUS_UNKNOWN_VENDOR)
                        or d.vendor.strip().lower() in present
                        or (d.product or "").strip().lower() in present
                    ):
                        continue
                    tid = _tech_id(d.vendor, d.product)
                    res = await session.execute(text(
                        """
                        INSERT INTO tech_stack_entries (entity_id, tech_id, vendor, product, layer, status, source, detected_at)
                        VALUES (CAST(:e AS uuid), :tid, :v, :p, :l, 'DETECTED', 'report_mention', NOW())
                        ON CONFLICT (entity_id, tech_id) DO NOTHING
                        """), {"e": row.eid, "tid": tid, "v": d.vendor[:128],
                               "p": (d.product or d.vendor)[:255],
                               "l": d.layer if d.layer in _VALID_LAYERS else layer})
                    present.add(d.vendor.strip().lower())
                    if d.product:
                        present.add(d.product.strip().lower())
                    if res.rowcount:
                        backfilled += 1
                present.add(vendor.lower())

            # ── 3) ground every entry: evidence E-IDs + subcap links ───
            entries = (await session.execute(text(
                "SELECT id::text id, vendor, product FROM tech_stack_entries "
                "WHERE entity_id=CAST(:e AS uuid) AND status NOT IN (:es, :uv)"
            ), {"e": row.eid, "es": STATUS_ENGINEERING_SIGNAL,
                "uv": STATUS_UNKNOWN_VENDOR})).all()
            for t in entries:
                # Match vendor OR product — the 2026-07-04 deep search found
                # rows with an empty vendor whose PRODUCT name is what the
                # evidence actually cites ("Tableau", "nCino"); vendor-only
                # matching left 14 clients with zero evidence-linked rows.
                v = (t.vendor or "").strip()
                prod = (getattr(t, "product", "") or "").strip()
                probe = v if len(v) >= 3 else prod
                if len(probe) < 3:
                    continue
                eids = [r2.e_id for r2 in (await session.execute(text(
                    "SELECT e_id FROM evidence_index WHERE entity_id=CAST(:e AS uuid) "
                    "AND excerpt ILIKE '%'||:v||'%' LIMIT 5"
                ), {"e": row.eid, "v": probe})).all()]
                if not eids and prod and prod != probe and len(prod) >= 4:
                    eids = [r2.e_id for r2 in (await session.execute(text(
                        "SELECT e_id FROM evidence_index WHERE entity_id=CAST(:e AS uuid) "
                        "AND excerpt ILIKE '%'||:v||'%' LIMIT 5"
                    ), {"e": row.eid, "v": prod})).all()]
                from app.services.parsers.tech_linker import family_for_vendor
                fam = family_for_vendor(v)
                subs: list[str] = []
                if fam:
                    subs = [r3.subcap_id for r3 in (await session.execute(text(
                        "SELECT subcap_id FROM subcap_scores WHERE run_id=CAST(:rid AS uuid) "
                        "AND :fam = ANY(platform_tags) ORDER BY score LIMIT 8"
                    ), {"rid": row.rid, "fam": fam})).all()]
                if eids or subs:
                    await session.execute(text(
                        "UPDATE tech_stack_entries SET "
                        "evidence_e_ids=CASE WHEN :ev='' THEN evidence_e_ids ELSE CAST(:ev AS varchar[]) END, "
                        "linked_subcap_ids=CASE WHEN :sb='' THEN linked_subcap_ids ELSE CAST(:sb AS varchar[]) END "
                        "WHERE id=CAST(:id AS uuid)"
                    ), {"id": t.id,
                        "ev": _pg_text_array(_clean_eids(eids)),
                        "sb": _pg_text_array(subs)})
                    if eids:
                        ev_linked += 1
                    if subs:
                        sub_linked += 1
        await session.commit()

        after_noise = await _noise_count(session)
        after_dist = await _status_distribution(session)

    def _fmt(dist: Counter) -> str:
        return " ".join(f"{k}={v}" for k, v in sorted(dist.items()))

    print(f"# clean_techstack: noise_rows_rendered {before_noise} -> {after_noise} "
          f"(target 0)", flush=True)
    print(f"# clean_techstack: status_before [{_fmt(before_dist)}]", flush=True)
    print(f"# clean_techstack: status_after  [{_fmt(after_dist)}]", flush=True)
    print(f"# clean_techstack: noise_deleted={deleted} canonicalised={canonicalised} "
          f"replaced_multi_cells={replaced} flagged={flagged} "
          f"backfilled_from_report={backfilled} "
          f"evidence_linked={ev_linked} subcaps_linked={sub_linked}", flush=True)
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()
