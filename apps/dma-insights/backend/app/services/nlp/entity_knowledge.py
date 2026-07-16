"""L1 — the shared per-entity knowledge state (the anti-silo core).

`EntityState` is assembled ONCE per entity from every authoritative signal the
DB holds — scored capabilities (with peer-gap), the embedded evidence corpus,
firmographics/financials/leadership/sentiment, the platform roster, the analyst
SCQA thesis, the dated why-now triggers — and is then read by EVERY surface
composer (Phase C). One fact surfaced on one surface is retrievable by any other,
so the finding's score, the platform card's opportunity, the focus KPI and the
exec thesis all agree (cohesion, no silos).

It sits ON TOP of the two lower primitives:
  * :mod:`app.services.nlp.semantic` — MiniLM (baked) / TF-IDF (cold) topical
    relevance, for support-checking a citation against a capability.
  * :mod:`app.services.nlp.knowledge` — the evidence-challenge + contradiction-
    resolution engine (L2): drop a cited E-ID that doesn't resolve, is peer-owned,
    or is topically misaligned; resolve same-subject opposing claims.

The state exposes the exact primitives the L3 grader + composer need:
  * ``in_scope(subcap)``            — G0 subvertical-scope gate.
  * ``catalogue_subcap_names``      — G1 (a title that is a bare catalogue label
                                      is not a thesis).
  * ``supporting_evidence(cap)``    — G2 topically-aligned, ownership-checked
                                      evidence for a capability.
  * ``evidence_excerpt(e_id)``      — G6 per-claim verification lookup.
  * ``ranked_gaps`` / ``ranked_strengths`` — finding/card selection by widest
                                      IN-SCOPE peer-gap / outperformance (never
                                      the numerically-lowest NA-1.0 cell).
  * ``knowledge`` (EntityKnowledge) — challenge()/resolve_contradictions().

Pure-read + tier-agnostic: it never raises on a cold regen (SemanticIndex falls
back to TF-IDF) and never calls Vertex.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.nlp.evidence_hygiene import clean_excerpt, primary_eid
from app.services.nlp.knowledge import EntityKnowledge, Evidence, classify_owned

# The analyst SCQA is persisted as a `document_sections` row (kind
# `executive_summary_scqa`) — package ingest stores `runs.scqa=None` (the prose
# lives in the DOCX/section). A 4-part shape ("## 1. Situation … ## 4. Answer")
# splits into keys the L4 storyline spine reads (``answer`` becomes the analyst
# thesis); a free-prose analyst summary is kept whole under ``narrative`` for the
# exec composer. Nothing is fabricated — absent section ⇒ None.
_SCQA_HEAD_RE = re.compile(
    r"^\s*#{1,4}\s*(?:\d+\.\s*)?(situation|complication|question|answer)\b[^\n]*$",
    re.I | re.M)
_SCQA_FOOTER_RE = re.compile(r"\n\s*\*[^\n]*derived from[^\n]*\*\s*$", re.I)


def parse_scqa_section(body: str | None) -> dict[str, str] | None:
    """Structure an ``executive_summary_scqa`` section body for the L4 spine.

    Returns a dict that always carries the whole ``narrative`` (whitespace-
    normalized) plus any of ``situation``/``complication``/``question``/``answer``
    recovered from a 4-part heading layout. Returns None for an empty body.
    """
    if not body or not body.strip():
        return None
    clean = _SCQA_FOOTER_RE.sub("", body.strip())
    out: dict[str, str] = {"narrative": re.sub(r"\s+", " ", clean).strip()}
    heads = list(_SCQA_HEAD_RE.finditer(clean))
    for i, m in enumerate(heads):
        key = m.group(1).lower()
        end = heads[i + 1].start() if i + 1 < len(heads) else len(clean)
        seg = re.sub(r"\s+", " ", clean[m.end():end]).strip(" .;")
        if len(seg) >= 8:
            out[key] = seg
    return out


@dataclass
class Capability:
    """One scored capability (subcap) with its peer standing and evidence."""
    subcap_id: str
    name: str
    score: float
    peer_median: float | None
    peer_gap: float | None       # score - peer_median (negative ⇒ a gap)
    pillar: str                  # P1..P4
    category: str                # P#C#
    rationale: str
    tier: str | None             # catalogue tier T1/T2/T3
    in_scope: bool
    evidence_ids: list[str] = field(default_factory=list)

    @property
    def is_gap(self) -> bool:
        return self.peer_gap is not None and self.peer_gap <= -0.3

    @property
    def is_strength(self) -> bool:
        return self.peer_gap is not None and self.peer_gap >= 0.5


@dataclass
class EntityState:
    """The one cohesive per-entity understanding read by every composer."""
    run_id: str
    entity_id: str
    name: str
    subvertical: str | None
    catalog_version: str | None
    capabilities: list[Capability]
    knowledge: EntityKnowledge
    firmographics: dict[str, Any]
    platforms: list[dict[str, Any]]
    tech_stack: list[str]
    scqa: dict[str, Any] | None
    top_findings: list[dict[str, Any]]
    why_now_signals: list[dict[str, Any]]
    na_subcap_ids: set[str]
    _by_subcap: dict[str, Capability] = field(default_factory=dict)
    _excerpt_by_eid: dict[str, str] = field(default_factory=dict)
    _catalogue_names: set[str] = field(default_factory=set)

    # ── scope + catalogue (G0/G1) ──────────────────────────────────────
    def in_scope(self, subcap_id: str | None) -> bool:
        """G0: a subcap applies to this entity's subvertical/LOB. Uses the
        explicit A5 NA list when persisted, then the LOB-family heuristic."""
        if not subcap_id:
            return True
        if subcap_id in self.na_subcap_ids:
            return False
        cap = self._by_subcap.get(subcap_id)
        if cap is not None:
            return cap.in_scope
        from app.services.focus_area_sanity import subcap_out_of_scope
        return not subcap_out_of_scope(
            subcap_id, subvertical=self.subvertical,
            na_subcap_ids=self.na_subcap_ids or None,
        )

    @property
    def catalogue_subcap_names(self) -> set[str]:
        """G1: the set of bare catalogue subcap labels — a title equal to one of
        these is a capability name, not a client-specific thesis."""
        return self._catalogue_names

    def capability(self, subcap_id: str | None) -> Capability | None:
        return self._by_subcap.get(subcap_id or "")

    # ── evidence grounding (G2/G6) ─────────────────────────────────────
    def supporting_evidence(
        self, capability: str, k: int = 5, min_score: float = 0.30,
    ) -> list[tuple[str, float]]:
        """G2: topically-aligned, ownership-checked evidence for a capability
        (delegates to the L2 EntityKnowledge retrieval primitive)."""
        return self.knowledge.supporting_evidence(
            capability, k=k, min_score=min_score, owned_only=True)

    def evidence_excerpt(self, e_id: str | None) -> str | None:
        """G6: the verbatim excerpt for a cited E-ID (verification lookup)."""
        return self._excerpt_by_eid.get(e_id or "")

    def evidence_for(self, subcap_id: str) -> list[str]:
        """A3-proxy: E-IDs the corpus links to this subcap (evidence_index
        linked_subcap_ids), tier-ordered as loaded."""
        cap = self._by_subcap.get(subcap_id)
        return list(cap.evidence_ids) if cap else []

    # ── ranked selection (finding/card anchors — NOT lowest-raw-score) ──
    @property
    def ranked_gaps(self) -> list[Capability]:
        """In-scope capabilities by widest negative peer-gap (the real binding
        gaps — never the subvertical-NA 1.0 cells)."""
        gaps = [c for c in self.capabilities
                if c.in_scope and c.peer_gap is not None and c.peer_gap < 0]
        return sorted(gaps, key=lambda c: (c.peer_gap, c.score))

    @property
    def ranked_strengths(self) -> list[Capability]:
        """In-scope capabilities by widest positive peer outperformance."""
        strengths = [c for c in self.capabilities
                     if c.in_scope and c.peer_gap is not None and c.peer_gap > 0]
        return sorted(strengths, key=lambda c: (-c.peer_gap, -c.score))

    @property
    def evidenced_anchors(self) -> list[Capability]:
        """The capabilities a gold card can actually be WRITTEN about: in-scope
        AND carrying A3-linked evidence with a NON-EMPTY excerpt, ranked by
        USABLE-evidence richness then strategic weight (|peer-gap|). The gold
        overlays anchor here — an evidence-rich strength/opportunity frames the
        story — NOT on the numerically-lowest unevidenced gap (which has no
        support to ground a claim, so it can only misattribute).

        The usable-excerpt requirement matters: a placeholder evidence row
        ("(no excerpt)" — 1013 such rows in the corpus) or an excerpt too short
        to carry a sentence cannot ground a claim, and NA catalogue-default cells
        (which all cite one such placeholder E-ID at score 1.0 / gap -2.0) would
        otherwise dominate the ranking and starve the real evidenced caps. The
        24-char floor matches the composer's own minimum lead-sentence length."""
        scored: list[tuple[Capability, int]] = []
        for c in self.capabilities:
            if not c.in_scope:
                continue
            usable = sum(1 for e in c.evidence_ids
                         if len((self.evidence_excerpt(e) or "").strip()) >= 24)
            if usable:
                scored.append((c, usable))
        scored.sort(key=lambda t: (-t[1], -abs(t[0].peer_gap or 0.0), -t[0].score))
        return [c for c, _ in scored]


_PILLAR_LABEL = {"P1": "strategy & governance", "P2": "customer experience",
                 "P3": "operations & process", "P4": "data & technology"}


async def load_entity_state(
    session: AsyncSession, *, entity_display_id: str,
) -> EntityState | None:
    """Assemble the shared per-entity state from the DB. Returns None when the
    entity has no active run. One query per source (no N+1)."""
    ent = (await session.execute(
        text("""
            SELECT e.id AS entity_id, e.name, e.subvertical,
                   r.id AS run_id, r.ccg_catalog_version,
                   r.scqa, r.why_now_signals, r.top_findings, r.coverage_stats
              FROM entities e
              JOIN runs r ON r.entity_id = e.id
             WHERE e.display_id = :did
               AND r.status IN ('ACTIVE', 'PENDING_REVIEW', 'IN_PROGRESS')
             ORDER BY CASE r.status
                        WHEN 'ACTIVE' THEN 0
                        WHEN 'PENDING_REVIEW' THEN 1
                        ELSE 2 END,
                      r.completed_at DESC NULLS LAST
             LIMIT 1
        """),
        {"did": entity_display_id},
    )).first()
    if ent is None:
        return None
    run_id, entity_id = str(ent.run_id), str(ent.entity_id)

    # ── evidence corpus (the challenge/support engine) ─────────────────
    ev_rows = (await session.execute(
        text("""
            SELECT e_id, excerpt, tier, published_date, linked_subcap_ids,
                   entity_id AS row_entity_id
              FROM evidence_index
             WHERE run_id = :rid
             ORDER BY tier ASC, e_id ASC
        """),
        {"rid": run_id},
    )).all()
    evidence: list[Evidence] = []
    excerpt_by_eid: dict[str, str] = {}
    eids_by_subcap: dict[str, list[str]] = {}
    seen_eids: set[str] = set()
    # A cited E-ID must resolve on drilldown (evidence_index lookup is an EXACT
    # e_id match). Nearly every clean id already exists as its own canonical row
    # alongside the malformed fragment rows, so gating on the raw-key set keeps
    # citations clean AND clickable; a clean id with no standalone row is skipped.
    resolvable_raw = {r.e_id for r in ev_rows if r.e_id}
    for r in ev_rows:
        # Normalize the ingest annotation before anything reads it: recover the
        # citable E-ID (first complete token — a comma cell's trailing id is
        # column-cut) and strip the "[CEILING…] [E-…] Title (T#, STATUS): …
        # [PRESENCE…]" wrappers, so the fact / title / verification see the
        # human sentence, and citations render a clean "E-072" not "E-072:F2,".
        eid = primary_eid(r.e_id, r.excerpt)
        if not eid or eid not in resolvable_raw:
            continue
        excerpt = clean_excerpt(r.excerpt)
        if eid not in seen_eids:
            # Peer/benchmark ownership fence (L2): an excerpt whose subject is a
            # peer/industry figure, or a row owned by ANOTHER entity (cross-entity
            # dedup pull-in), is NOT the client's own evidence — so the challenge
            # engine will not let it ground a client claim (the peer-NPS fence).
            # classify_owned is high-precision (defaults True); the entity-id guard
            # is defense-in-depth (0 such rows in the current corpus).
            same_entity = (
                r.row_entity_id is None or str(r.row_entity_id) == entity_id)
            owned = same_entity and classify_owned(excerpt, entity_name=ent.name)
            evidence.append(Evidence(
                e_id=eid, text=excerpt,
                tier=int(r.tier) if r.tier is not None else 8,
                year=r.published_date.year if r.published_date else None,
                owned=owned,
            ))
            excerpt_by_eid[eid] = excerpt
            seen_eids.add(eid)
        elif excerpt and not excerpt_by_eid.get(eid):
            excerpt_by_eid[eid] = excerpt
        for sid in (r.linked_subcap_ids or []):
            lst = eids_by_subcap.setdefault(sid, [])
            if eid not in lst:
                lst.append(eid)
    knowledge = EntityKnowledge(evidence)

    # ── A5 NA subcaps (persisted by ingest when available) ─────────────
    na_subcap_ids: set[str] = set()
    cov = ent.coverage_stats if isinstance(ent.coverage_stats, dict) else {}
    for sid in (cov.get("subvertical_na_subcaps") or []):
        if isinstance(sid, str):
            na_subcap_ids.add(sid)

    # ── scored capabilities (with peer-gap) + catalogue names ──────────
    cap_rows = (await session.execute(
        text("""
            SELECT ss.subcap_id, ss.score, ss.rationale,
                   ss.peer_median, ss.peer_gap,
                   sc.name AS cat_name, sc.tier AS cat_tier
              FROM subcap_scores ss
              LEFT JOIN ccg_subcaps sc
                     ON sc.subcap_id = ss.subcap_id
                    AND sc.version = :cv
             WHERE ss.run_id = :rid AND ss.score IS NOT NULL
        """),
        {"rid": run_id, "cv": ent.ccg_catalog_version},
    )).all()
    from app.services.focus_area_sanity import subcap_out_of_scope
    capabilities: list[Capability] = []
    by_subcap: dict[str, Capability] = {}
    catalogue_names: set[str] = set()
    for r in cap_rows:
        sid = r.subcap_id
        # category = the P#C# prefix (first dot-segment); pillar = P#
        category = sid.split(".", 1)[0]
        pillar = sid[:2] if len(sid) >= 2 else sid
        oos = subcap_out_of_scope(
            sid, subvertical=ent.subvertical,
            na_subcap_ids=na_subcap_ids or None)
        cap = Capability(
            subcap_id=sid,
            name=(r.cat_name or "").strip(),
            score=float(r.score),
            peer_median=float(r.peer_median) if r.peer_median is not None else None,
            peer_gap=float(r.peer_gap) if r.peer_gap is not None else None,
            pillar=pillar,
            category=category,
            rationale=(r.rationale or "").strip(),
            tier=r.cat_tier,
            in_scope=not oos,
            evidence_ids=eids_by_subcap.get(sid, []),
        )
        capabilities.append(cap)
        by_subcap[sid] = cap
        if cap.name:
            catalogue_names.add(cap.name.lower())

    # ── firmographics (financials / leadership / sentiment / narrative) ─
    firm_row = (await session.execute(
        text("""
            SELECT aum_usd, revenue_usd, headcount, hq_address,
                   primary_regulator, leadership, sentiment, narrative_md,
                   financial_highlights, parsed_facts
              FROM firmographics WHERE entity_id = :eid
        """),
        {"eid": entity_id},
    )).first()
    firmographics: dict[str, Any] = {}
    if firm_row is not None:
        firmographics = {
            "aum_usd": float(firm_row.aum_usd) if firm_row.aum_usd is not None else None,
            "revenue_usd": float(firm_row.revenue_usd) if firm_row.revenue_usd is not None else None,
            "headcount": firm_row.headcount,
            "hq_address": firm_row.hq_address,
            "primary_regulator": firm_row.primary_regulator,
            "leadership": firm_row.leadership,
            "sentiment": firm_row.sentiment,
            "narrative_md": firm_row.narrative_md,
            "financial_highlights": firm_row.financial_highlights or {},
            "parsed_facts": firm_row.parsed_facts or {},
        }
        # A5 NA can also ride in parsed_facts (parser-owned, no migration).
        for sid in ((firm_row.parsed_facts or {}).get("subvertical_na_subcaps") or []):
            if isinstance(sid, str):
                na_subcap_ids.add(sid)

    # ── platform roster + tech stack ───────────────────────────────────
    plat_rows = (await session.execute(
        text("""
            SELECT platform_id, fit_score, readiness_index,
                   addressable_subcap_ids, fit_breakdown, sequence_rank
              FROM platform_scores WHERE run_id = :rid
             ORDER BY sequence_rank ASC NULLS LAST, fit_score DESC
        """),
        {"rid": run_id},
    )).all()
    platforms = [{
        "platform_id": r.platform_id,
        "fit_score": float(r.fit_score) if r.fit_score is not None else None,
        "readiness_index": r.readiness_index,
        "addressable_subcap_ids": list(r.addressable_subcap_ids or []),
        "fit_breakdown": r.fit_breakdown,
        "sequence_rank": r.sequence_rank,
    } for r in plat_rows]
    tech_rows = (await session.execute(
        text("""
            SELECT DISTINCT vendor, product FROM tech_stack_entries
             WHERE entity_id = :eid
        """),
        {"eid": entity_id},
    )).all() if await _table_exists(session, "tech_stack_entries") else []
    tech_stack = sorted({
        (r.product or r.vendor) for r in tech_rows if (r.product or r.vendor)
    })

    # ── analyst SCQA spine ─────────────────────────────────────────────
    # Prefer a structured runs.scqa when present; else recover the analyst
    # narrative from the executive_summary_scqa document_section (package ingest
    # stores runs.scqa=None, so on this corpus it is 0/95 — without this the L4
    # storyline spine never sees the analyst's own thesis).
    scqa: dict[str, Any] | None = ent.scqa if isinstance(ent.scqa, dict) and ent.scqa else None
    if scqa is None:
        sec = (await session.execute(
            text("""
                SELECT body FROM document_sections
                 WHERE run_id = :rid AND section_kind = 'executive_summary_scqa'
                   AND COALESCE(body, '') <> ''
                 ORDER BY char_length(body) DESC
                 LIMIT 1
            """),
            {"rid": run_id},
        )).first()
        if sec is not None:
            scqa = parse_scqa_section(sec.body)

    return EntityState(
        run_id=run_id,
        entity_id=entity_id,
        name=ent.name,
        subvertical=ent.subvertical,
        catalog_version=ent.ccg_catalog_version,
        capabilities=capabilities,
        knowledge=knowledge,
        firmographics=firmographics,
        platforms=platforms,
        tech_stack=tech_stack,
        scqa=scqa,
        top_findings=list(ent.top_findings or []) if isinstance(ent.top_findings, list) else [],
        why_now_signals=list(ent.why_now_signals or []) if isinstance(ent.why_now_signals, list) else [],
        na_subcap_ids=na_subcap_ids,
        _by_subcap=by_subcap,
        _excerpt_by_eid=excerpt_by_eid,
        _catalogue_names=catalogue_names,
    )


async def _table_exists(session: AsyncSession, name: str) -> bool:
    row = (await session.execute(
        text("SELECT to_regclass(:n) AS t"), {"n": f"public.{name}"},
    )).first()
    return bool(row and row.t)
