"""Tech-stack read model (Part 9) — status honesty, ABSENT gap rows,
peer coverage, real `since`, and the L1-L5 layer ladder.

Everything here is derived at READ time from persisted rows — nothing is
fabricated. The module powers the three techstack endpoints in
``app/routers/context.py`` (and, through them, the committed startup-pack
``techstack.json`` snapshots, since the exporter replays the same routes).

Contract highlights
-------------------
* Only ``ENGINEERING_SIGNAL`` rows (programming/scripting languages, written
  by the taxonomy sanitizer + the clean_techstack heal pass) are EXCLUDED from
  the AE-facing ``items``; the response carries honest counts + the
  engineering-signal names instead. ``UNKNOWN_VENDOR`` rows (real vendor/product
  tech not in the curated catalogue) ARE surfaced — they are the client's actual
  stack (2026-07-09 QA fix).
* 4-state status (:func:`derive_status`): CONFIRMED (source-asserted
  deployment OR T1-T3 evidence) / CLAIMED (only T4-T5 marketing-tier
  evidence) / INFERRED (technographic/job/press detection, no confirming
  evidence) / ABSENT (synthesized scored-family gap rows), plus
  CONFIRMED_REMOVED for decommissioned tech.
* ABSENT gap rows (:func:`build_absent_rows`) are generated per scored
  platform family missing from the detected stack — the exact regex rule
  the frontend's displacement banner used (now mirrored server-side in
  ``tech_linker.SCORED_PLATFORM_FAMILIES``) — carrying the catalogue's
  addressable subcaps for the active run, a ``primary_gap`` flag, and the
  cohort's real ``peer_coverage``.
* ``peer_coverage`` on ALL rows = share of cohort entities (same
  subvertical when ≥3 cohort entities carry tech data, else the whole
  corpus) with the same canonical vendor (family share for family-linked
  rows).
* ``since`` (:func:`derive_since`) = a real date mined via ``nlp.dates``
  from the detection-evidence sentences that mention the vendor; omitted
  (None) when no dated sentence exists — the UI then shows "Detected
  {ingest date}" instead of a misleading "Since".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.context import (
    TechPeerDeployment,
    TechStackEntryOut,
    TechSubcapImpact,
)
from app.services.nlp.dates import resolve_event_date
from app.services.nlp.segment import sentences
from app.services.parsers.tech_linker import (
    FAMILY_LAYER,
    SCORED_PLATFORM_FAMILIES,
    absent_families,
)

# Taxonomy-flagged statuses — persisted, never AE-rendered. ONLY programming/
# scripting-language engineering signals are hidden; UNKNOWN_VENDOR (real vendor/
# product tech not in the curated catalogue) is surfaced as the client's stack
# (2026-07-09 QA — it was over-filtering the whole "tech Zennify doesn't sell").
FLAGGED_STATUSES: tuple[str, ...] = ("ENGINEERING_SIGNAL",)

# Backend layer → (layer_code, layer_full, default DMA pillar). The
# prototype's L1 Strategy rung has no stored layer (the DB CHECK allows 4
# values); it is restored where the catalogue implies it — a row whose
# linked subcaps are predominantly P1 is strategy/governance tooling.
LAYER_LADDER: dict[str, tuple[str, str, str]] = {
    "platform": ("L2", "Operations & core banking", "P3"),
    "application": ("L3", "Customer engagement", "P2"),
    "intelligence": ("L4", "Data & analytics", "P4"),
    "foundation": ("L5", "Infrastructure & cloud", "P4"),
}
L1_LADDER: tuple[str, str, str] = ("L1", "Strategy & governance", "P1")

_QUARTER_BY_MONTH = {2: 1, 5: 2, 8: 3, 11: 4}


def derive_status(stored: str | None, evidence_tiers: list[int]) -> str:
    """Honest 4-state mapping from the stored enum + linked evidence tiers.

    CONFIRMED ← the source inventory asserted deployment (stored
    CONFIRMED), or any linked evidence is tier T1-T3. CLAIMED ← the only
    linked evidence is marketing-tier T4-T5. INFERRED ← everything else
    (technographic/job/press detection). CONFIRMED_REMOVED passes through.
    Legacy free-form values ('active', '') resolve through the same
    evidence ladder.
    """
    s = (stored or "").strip().upper()
    if s == "CONFIRMED_REMOVED":
        return "CONFIRMED_REMOVED"
    if s == "CONFIRMED":
        return "CONFIRMED"
    tiers = [t for t in evidence_tiers if t is not None]
    if tiers:
        if min(tiers) <= 3:
            return "CONFIRMED"
        if all(4 <= t <= 5 for t in tiers):
            return "CLAIMED"
    return "INFERRED"


def derive_since(vendor: str, excerpts: list[str]) -> str | None:
    """Mine a real deployment date from evidence sentences naming the vendor.

    Only sentences that mention the vendor are considered (an excerpt's
    unrelated dates — founding years, fiscal periods — must not become a
    deployment date). Precision maps to the prototype's display forms:
    day/month → "YYYY-MM", quarter → "YYYY-Qn", year → "YYYY". Returns
    None when nothing dated exists — never falls back to the ingest
    timestamp (that mislabel was the audit's "Since {detected_at}" defect).
    """
    v = (vendor or "").strip().lower()
    if not v:
        return None
    for excerpt in excerpts:
        if not excerpt:
            continue
        for sent in sentences(excerpt):
            if v not in sent.lower():
                continue
            resolved, precision = resolve_event_date(sent)
            if resolved is None or precision in ("publish_fallback", "none"):
                continue
            if precision in ("day", "month"):
                return f"{resolved.year}-{resolved.month:02d}"
            if precision == "quarter":
                q = _QUARTER_BY_MONTH.get(resolved.month)
                return f"{resolved.year}-Q{q}" if q else str(resolved.year)
            return str(resolved.year)
    return None


def compose_note(
    *, vendor: str, product: str | None, evidence_count: int,
    subcap_count: int, source: str | None,
) -> str | None:
    """Clean one-line row descriptor from REAL fields (never the raw cell)."""
    bits: list[str] = []
    if product and product.strip() and product.strip().lower() != vendor.strip().lower():
        bits.append(product.strip())
    if evidence_count:
        bits.append(f"{evidence_count} evidence item{'s' if evidence_count != 1 else ''}")
    if subcap_count:
        bits.append(
            f"addresses {subcap_count} sub-capabilit{'ies' if subcap_count != 1 else 'y'}"
        )
    if not bits and source:
        bits.append(f"Detected via {source}")
    return " · ".join(bits) or None


_PILLAR_RE = re.compile(r"^(P[1-4])")


def dominant_pillar(subcap_ids: list[str]) -> str | None:
    """Majority pillar of the row's linked subcaps (ties → first seen)."""
    counts: dict[str, int] = {}
    order: list[str] = []
    for sid in subcap_ids or []:
        m = _PILLAR_RE.match(sid or "")
        if not m:
            continue
        p = m.group(1)
        if p not in counts:
            order.append(p)
        counts[p] = counts.get(p, 0) + 1
    if not counts:
        return None
    return max(order, key=lambda p: counts[p])


def layer_ladder_fields(
    layer: str | None, subcap_ids: list[str],
) -> tuple[str | None, str | None, str | None]:
    """(layer_code, layer_full, dma_pillar) — restores L1 Strategy where the
    catalogue implies it (dominant linked pillar = P1)."""
    pillar = dominant_pillar(subcap_ids)
    if pillar == "P1":
        code, full, _p = L1_LADDER
        return code, full, "P1"
    ladder = LAYER_LADDER.get((layer or "").strip())
    if ladder is None:
        return None, None, pillar
    code, full, default_pillar = ladder
    return code, full, pillar or default_pillar


@dataclass
class CohortCoverage:
    """Cross-entity deployment shares for one cohort."""

    cohort_size: int
    cohort_label: str
    subvertical: str | None
    vendor_share: dict[str, float] = field(default_factory=dict)
    family_share: dict[str, float] = field(default_factory=dict)


async def load_cohort_coverage(
    session: AsyncSession, *, subvertical: str | None,
) -> CohortCoverage:
    """Compute per-vendor + per-family deployment shares for the cohort.

    Cohort = ACTIVE entities of the same subvertical that carry any
    (non-flagged) tech rows; falls back to the whole corpus when fewer
    than 3 such entities exist. Family shares mirror the frontend's
    scored-family regexes over "vendor product".
    """
    async def _load(sv: str | None) -> tuple[int, list, list]:
        params: dict = {"sv": sv}
        cohort_sql = (
            "SELECT t.entity_id, lower(t.vendor) AS v, "
            "       lower(t.vendor || ' ' || COALESCE(t.product, '')) AS vp "
            "FROM tech_stack_entries t "
            "JOIN entities e ON e.id = t.entity_id AND e.status = 'ACTIVE' "
            "WHERE t.status <> 'ENGINEERING_SIGNAL' "
            "AND (CAST(:sv AS varchar) IS NULL OR e.subvertical = :sv)"
        )
        denom = (await session.execute(
            text(f"SELECT COUNT(DISTINCT entity_id) FROM ({cohort_sql}) b"),
            params,
        )).scalar_one()
        if not denom:
            return 0, [], []
        vendor_rows = (await session.execute(
            text(
                f"SELECT v, COUNT(DISTINCT entity_id) AS n "
                f"FROM ({cohort_sql}) b GROUP BY v"
            ),
            params,
        )).all()
        fam_filters = ", ".join(
            f"COUNT(DISTINCT entity_id) FILTER (WHERE vp ~* :rx_{fid}) AS {fid}"
            for fid, _name, _rx in SCORED_PLATFORM_FAMILIES
        )
        fam_params = dict(params)
        for fid, _name, rx in SCORED_PLATFORM_FAMILIES:
            fam_params[f"rx_{fid}"] = rx.pattern
        fam_row = (await session.execute(
            text(f"SELECT {fam_filters} FROM ({cohort_sql}) b"), fam_params,
        )).first()
        return int(denom), vendor_rows, [fam_row]

    denom, vendor_rows, fam_rows = await _load(subvertical)
    label = f"{subvertical} cohort" if subvertical else "all assessed clients"
    if denom < 3 and subvertical is not None:
        denom, vendor_rows, fam_rows = await _load(None)
        label = "all assessed clients"
    cov = CohortCoverage(
        cohort_size=denom, cohort_label=label,
        subvertical=subvertical if label != "all assessed clients" else None,
    )
    if not denom:
        return cov
    cov.vendor_share = {r.v: round(r.n / denom, 4) for r in vendor_rows}
    if fam_rows and fam_rows[0] is not None:
        m = fam_rows[0]._mapping
        cov.family_share = {
            fid: round((m[fid] or 0) / denom, 4)
            for fid, _name, _rx in SCORED_PLATFORM_FAMILIES
        }
    return cov


def row_peer_coverage(
    cov: CohortCoverage, *, vendor: str | None, l3_id: str | None,
) -> float | None:
    """Family share when the row links a scored family, else vendor share."""
    if l3_id and l3_id in cov.family_share:
        return cov.family_share[l3_id]
    v = (vendor or "").strip().lower()
    return cov.vendor_share.get(v)


async def load_evidence_meta(
    session: AsyncSession, *, entity_id: str, e_ids: list[str],
) -> dict[str, tuple[int | None, str | None]]:
    """e_id → (tier, excerpt) for this entity's linked evidence."""
    if not e_ids:
        return {}
    rows = (await session.execute(
        text(
            "SELECT e_id, tier, excerpt FROM evidence_index "
            "WHERE entity_id = CAST(:eid AS uuid) AND e_id = ANY(:ids)"
        ),
        {"eid": str(entity_id), "ids": list(dict.fromkeys(e_ids))},
    )).all()
    return {r.e_id: (r.tier, r.excerpt) for r in rows}


async def load_addressable_subcaps(
    session: AsyncSession, *, run_id: str | None, family: str, limit: int = 8,
) -> list[dict]:
    """The run's scored subcaps the family addresses, weakest-score-first.

    Grounded in ``subcap_scores.platform_tags`` (the catalogue's
    platform↔subcap mapping promoted at ingest). Empty when no run.
    """
    if not run_id:
        return []
    rows = (await session.execute(
        text(
            "SELECT subcap_id, score, peer_median, is_thin_evidence "
            "FROM subcap_scores "
            "WHERE run_id = CAST(:rid AS uuid) AND :fam = ANY(platform_tags) "
            "ORDER BY score LIMIT :lim"
        ),
        {"rid": str(run_id), "fam": family, "lim": limit},
    )).all()
    return [
        {
            "subcap_id": r.subcap_id,
            "score": float(r.score) if r.score is not None else None,
            "peer_median": float(r.peer_median) if r.peer_median is not None else None,
            "thin": bool(r.is_thin_evidence),
        }
        for r in rows
    ]


async def load_subcap_names(
    session: AsyncSession, *, catalog_version: str | None, subcap_ids: list[str],
) -> dict[str, str]:
    if not subcap_ids:
        return {}
    rows = (await session.execute(
        text(
            "SELECT subcap_id, name FROM ccg_subcaps "
            "WHERE (CAST(:cv AS varchar) IS NULL OR version = :cv) "
            "AND subcap_id = ANY(:ids)"
        ),
        {"cv": catalog_version, "ids": list(dict.fromkeys(subcap_ids))},
    )).all()
    return {r.subcap_id: r.name for r in rows}


def absent_gap_row(
    *, family: str, display_name: str, subcaps: list[dict],
    peer_coverage: float | None,
) -> TechStackEntryOut:
    """One real ABSENT gap row for a scored family missing from the stack."""
    layer, pillar = FAMILY_LAYER.get(family, ("application", "P2"))
    code, full, _p = LAYER_LADDER[layer]
    sub_ids = [s["subcap_id"] for s in subcaps]
    note_bits = [f"No {display_name} detected in the stack"]
    if sub_ids:
        note_bits.append(
            f"addresses {len(sub_ids)} scored sub-capabilit"
            f"{'ies' if len(sub_ids) != 1 else 'y'}"
        )
    if peer_coverage is not None:
        note_bits.append(f"{round(peer_coverage * 100)}% of cohort peers deploy it")
    return TechStackEntryOut(
        id=f"absent-{family}", tech_id=f"absent-{family}",
        vendor=display_name, product=f"{display_name} platform family",
        product_name=f"{display_name} platform family",
        layer=layer, status="ABSENT", l3_id=family,
        source="derived:gap_analysis",
        evidence_e_ids=[], linked_subcap_ids=sub_ids, detected_at=None,
        since=None,
        note=" · ".join(note_bits),
        peer_coverage=peer_coverage,
        # Catalogue-grounded: the family is a primary gap when it addresses
        # scored sub-capabilities in the active run.
        primary_gap=bool(sub_ids),
        layer_code=code, layer_full=full, dma_pillar=pillar,
    )


async def build_absent_rows(
    session: AsyncSession, *, run_id: str | None,
    detected_haystack: str, cov: CohortCoverage,
) -> list[TechStackEntryOut]:
    """Real ABSENT rows for every scored platform family not detected."""
    out: list[TechStackEntryOut] = []
    for family, display_name in absent_families(detected_haystack):
        subcaps = await load_addressable_subcaps(
            session, run_id=run_id, family=family,
        )
        out.append(absent_gap_row(
            family=family, display_name=display_name, subcaps=subcaps,
            peer_coverage=cov.family_share.get(family),
        ))
    return out


def to_entry_out(
    row, *, evidence_meta: dict[str, tuple[int | None, str | None]],
    cov: CohortCoverage,
) -> TechStackEntryOut:
    """Map one stored row onto the honest read model."""
    e_ids = list(row.evidence_e_ids or [])
    tiers = [evidence_meta[e][0] for e in e_ids if e in evidence_meta]
    excerpts = [evidence_meta[e][1] or "" for e in e_ids if e in evidence_meta]
    sub_ids = list(row.linked_subcap_ids or [])
    product = row.product or row.vendor
    code, full, pillar = layer_ladder_fields(row.layer, sub_ids)
    return TechStackEntryOut(
        id=str(row.id), tech_id=row.tech_id, vendor=row.vendor,
        product=product, product_name=product,
        layer=row.layer,
        status=derive_status(row.status, tiers),
        l3_id=getattr(row, "l3_id", None),
        source=row.source,
        evidence_e_ids=e_ids,
        linked_subcap_ids=sub_ids,
        detected_at=row.detected_at,
        since=derive_since(row.vendor, excerpts),
        note=compose_note(
            vendor=row.vendor, product=row.product,
            evidence_count=len(e_ids), subcap_count=len(sub_ids),
            source=row.source,
        ),
        peer_coverage=row_peer_coverage(
            cov, vendor=row.vendor, l3_id=getattr(row, "l3_id", None),
        ),
        layer_code=code, layer_full=full, dma_pillar=pillar,
    )


def gap_zones_for(
    entry: TechStackEntryOut, impacts: list[TechSubcapImpact],
    cohort_label: str,
) -> list[str]:
    """Grounded gap-zone bullets for an ABSENT row (prototype s42 block).

    Every line traces to real data: the weakest addressed subcaps with
    their run scores, and the cohort deployment share. No fabricated
    prerequisite claims.
    """
    if entry.status != "ABSENT":
        return []
    zones: list[str] = []
    for imp in impacts[:4]:
        label = f"{imp.name} ({imp.subcap_id})" if imp.name else imp.subcap_id
        score_bit = f" scored {imp.score:.1f}" if imp.score is not None else ""
        peer_bit = (
            f" vs peer median {imp.peer_median:.1f}"
            if imp.peer_median is not None else ""
        )
        zones.append(
            f"{label}{score_bit}{peer_bit} — the {entry.vendor} family "
            "addresses this capability (catalogue platform mapping)."
        )
    if entry.peer_coverage is not None:
        zones.append(
            f"{round(entry.peer_coverage * 100)}% of {cohort_label} deploy "
            f"{entry.vendor} — greenfield/displacement conversation available."
        )
    return zones


async def load_peer_deployments(
    session: AsyncSession, *, entity_id: str, subvertical: str | None,
    vendor: str, l3_id: str | None, limit: int = 6,
) -> list[TechPeerDeployment]:
    """Named cohort peers with a real adoption flag for the detail page."""
    rx = None
    if l3_id:
        for fid, _name, pattern in SCORED_PLATFORM_FAMILIES:
            if fid == l3_id:
                rx = pattern.pattern
                break
    rows = (await session.execute(
        text(
            "SELECT e.name, EXISTS ("
            "  SELECT 1 FROM tech_stack_entries t WHERE t.entity_id = e.id "
            "  AND t.status <> 'ENGINEERING_SIGNAL' "
            "  AND (lower(t.vendor) = lower(:v) "
            "       OR (CAST(:rx AS varchar) IS NOT NULL "
            "           AND (t.vendor || ' ' || COALESCE(t.product,'')) ~* :rx))"
            ") AS has_tech "
            "FROM entities e "
            "WHERE e.status = 'ACTIVE' AND e.id != CAST(:self AS uuid) "
            "AND (CAST(:sv AS varchar) IS NULL OR e.subvertical = :sv) "
            "AND EXISTS (SELECT 1 FROM tech_stack_entries tx "
            "            WHERE tx.entity_id = e.id) "
            "ORDER BY has_tech DESC, e.name LIMIT :lim"
        ),
        {"v": vendor, "rx": rx, "self": str(entity_id), "sv": subvertical,
         "lim": limit},
    )).all()
    return [TechPeerDeployment(name=r.name, has_tech=bool(r.has_tech)) for r in rows]


async def load_impacts(
    session: AsyncSession, *, run_id: str | None, subcap_ids: list[str],
    catalog_version: str | None,
) -> list[TechSubcapImpact]:
    """Real per-subcap impact rows (score / peer median / thin) for the
    detail page's DMA-assessment-impact card."""
    if not subcap_ids:
        return []
    names = await load_subcap_names(
        session, catalog_version=catalog_version, subcap_ids=subcap_ids,
    )
    scores: dict[str, dict] = {}
    if run_id:
        rows = (await session.execute(
            text(
                "SELECT subcap_id, score, peer_median, is_thin_evidence "
                "FROM subcap_scores "
                "WHERE run_id = CAST(:rid AS uuid) AND subcap_id = ANY(:ids)"
            ),
            {"rid": str(run_id), "ids": list(dict.fromkeys(subcap_ids))},
        )).all()
        scores = {
            r.subcap_id: {
                "score": float(r.score) if r.score is not None else None,
                "peer_median": (
                    float(r.peer_median) if r.peer_median is not None else None
                ),
                "thin": bool(r.is_thin_evidence),
            }
            for r in rows
        }
    out: list[TechSubcapImpact] = []
    for sid in subcap_ids:
        s = scores.get(sid, {})
        out.append(TechSubcapImpact(
            subcap_id=sid, name=names.get(sid),
            score=s.get("score"), peer_median=s.get("peer_median"),
            thin=bool(s.get("thin", False)),
        ))
    return out


def detected_haystack(entries: list[TechStackEntryOut]) -> str:
    """The family-presence haystack over the rendered (detected) rows."""
    return " · ".join(
        f"{e.vendor or ''} {e.product or ''}" for e in entries
        if e.status != "ABSENT"
    )


@dataclass
class StackTriage:
    """Split of stored rows into surface / engineering / review buckets."""

    surfaced: list = field(default_factory=list)
    engineering: list = field(default_factory=list)
    review: list = field(default_factory=list)
    last_detected_at: datetime | None = None


def triage_rows(rows: list) -> StackTriage:
    t = StackTriage()
    for r in rows:
        status = (r.status or "").strip().upper()
        # Exclude ONLY programming/scripting-language "engineering signals"
        # (Python/Java/JS/…). UNKNOWN_VENDOR — real platforms/SaaS/infra/vendors
        # that simply aren't in Zennify's curated catalogue (Cvent, GitHub,
        # Dynatrace, …) — is the client's actual stack and MUST surface, not sit
        # in a hidden review queue (2026-07-09 QA: ~1,150 real rows were hidden).
        if status == "ENGINEERING_SIGNAL":
            t.engineering.append(r)
        else:
            t.surfaced.append(r)
        if r.detected_at and (
            t.last_detected_at is None or r.detected_at > t.last_detected_at
        ):
            t.last_detected_at = r.detected_at
    return t
