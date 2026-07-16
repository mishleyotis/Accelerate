"""B-7/B-8/B-9 endpoints — insight annotations, focus-area KPI overrides,
notifications. Backed by migration 025 tables.

All three are net-new in the 2026-06 wireframe. Writes are role-gated to
AE+ (any authenticated user); annotations record the author identity from
the auth context so the InsightModal can show "who/when".
"""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.deps import CurrentUserDep, SessionDep
from app.schemas.write_surfaces import (
    AnnotationIn,
    AnnotationListResponse,
    AnnotationOut,
    KpiOverrideListResponse,
    KpiOverrideOut,
    KpiOverridePut,
    MarkReadRequest,
    NotificationListResponse,
    NotificationOut,
)


class FocusAreaOut(BaseModel):
    """Parsed focus area for an entity (table populated by the Client
    Profile parser, migration 018+023). Returned by
    `GET /entities/{id}/focus-areas` so the D3 focus-area surface can list
    them; KPI customisations are loaded separately via
    `GET /entities/{id}/focus-areas/{fa_id}/kpis` (B-8).

    `colors` is a deterministic 2-tuple gradient derived from the focus
    area id, so the React `.fa-card` renders distinct branding per area
    instead of every card sharing the same lavender→teal default. The
    derivation is a pure function of fa.id -- stable across runs, no
    parser/persist change required."""

    id: str
    title: str
    verbatim_quote: str
    source_path: str
    page_number: int | None = None
    involved_subcap_ids: list[str] = Field(default_factory=list)
    colors: list[str] = Field(default_factory=list)
    # Migration 052 (Part 6.1 grounding fix). All additive — None/empty
    # on rows persisted before the synthesizer rewrite.
    #
    # {representative_quote, evidence_e_ids, source_kind: docx|gemini|
    # heuristic} — synthesized rows finally carry real anchors.
    grounding: dict | None = None
    # Quantities match against the financial series (the wireframe
    # SOURCE block's financial reference).
    financial_ref: str | None = None
    # Server-computed catalogue-weight share per pillar (replaces the
    # FE count-share proxy).
    pillars_weight: dict | None = None
    # KPI rows for the CustomizableKpiStrip [{label, current, target,
    # delta, source_mode, evidence_e_id}] — seeded by
    # derive_focus_area_kpis into focus_area_kpi_overrides; [] until
    # derived (the per-FA override endpoint stays the write path).
    # evidence_e_id (migration 060) anchors the number to the evidence
    # row it was read from; None on AE-entered / legacy rows. Migration
    # 056 adds evidence_e_ids + rationale + provenance per row for
    # reasoned (current+target) KPIs.
    kpis: list[dict] = Field(default_factory=list)
    # Migration 056 (focus-enrichment wave). Layered linked insight cards:
    # [{id, ic_id, title, severity, linked_subcap_id, bases:[{kind,detail}],
    # e_ids, source}] — the union of (affects∩FA subcaps) + evidence
    # co-citation + prose similarity (deterministic) with Gemini
    # adjudication of empties. Each link carries its BASIS so the
    # FocusAreaView minicards render a link-basis chip.
    linked_insights: list[dict] = Field(default_factory=list)
    # Traceability envelope for the row's Gemini-derived fields —
    # {grounding:{source,surface,model_id,synthesized_at,evidence_e_ids},
    # linked_insights:{...}}. Drives the provenance badge.
    enrichment_provenance: dict | None = None


# Zennify-palette gradient pairs (5B5BD6=lavender, 27BBAF=teal, FF8A4C=
# warm-org, 6A82FB=blue, FF8FB1=pink, FCB69F=peach). Each focus area gets
# ONE pair by hashing fa.id into the palette index. The palette
# guarantees no two adjacent FAs share a gradient on a typical 3-card
# row, and preserves the prototype's visual differentiation contract.
# The wireframe's canonical six focus-area gradients, verbatim from
# docs/wireframe-2026-06/src/01_data.js FOCUS_AREAS[].colors — every
# stop is a tokens.css variable (UI/UX brief: no off-palette color may
# reach a surface). QA audit 2026-06-11: the prior hash palette emitted
# raw web gradients (#FF8FB1 pink → #A86CFF violet, #38EF7D neon mint…)
# none of which exist in the brand system; pixel-sampling the rendered
# focus cards confirmed off-palette output (#28CC84 et al.).
_FA_GRADIENT_PALETTE: tuple[tuple[str, str], ...] = (
    ("var(--z-teal)", "var(--m-bld)"),     # FA-01 teal → building mint
    ("var(--z-dpur)", "var(--ph0)"),       # FA-02 deep purple
    ("var(--z-mid)", "var(--z-teal)"),     # FA-03 mid → teal
    ("var(--z-blue)", "var(--ph1)"),       # FA-04 blue
    ("var(--z-org)", "var(--m-act)"),      # FA-05 orange → activating
    ("var(--z-below)", "var(--m-act-t)"),  # FA-06 below-red → brown
)


def _focus_area_colors(position: int) -> list[str]:
    """Gradient pair for the focus area at `position` within the
    entity's rendered list (0-based, stable title order — the emitter
    sorts by title). Position-indexed like the wireframe (FA-01 teal,
    FA-02 purple, …) so cards keep the prototype's visual rhythm;
    deterministic across reloads because the underlying order is.
    Values are tokens.css var() references — the frontend drops them
    straight into linear-gradient(), so a future token change
    propagates without a backend deploy."""
    pair = _FA_GRADIENT_PALETTE[position % len(_FA_GRADIENT_PALETTE)]
    return [pair[0], pair[1]]


class FocusAreaListResponse(BaseModel):
    entity_display_id: str
    items: list[FocusAreaOut] = Field(default_factory=list)

entities_router = APIRouter(prefix="/api/v1/entities", tags=["write-surfaces"])
notifications_router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


async def _resolve_entity(session, display_id: str):
    ent = (
        await session.execute(
            text("SELECT id FROM entities WHERE display_id = :did"),
            {"did": display_id},
        )
    ).first()
    if ent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"entity {display_id} not found",
        )
    return ent


async def _active_run_id(session, entity_id: str) -> str | None:
    run = (
        await session.execute(
            text(
                "SELECT id FROM runs WHERE entity_id = :eid AND status = 'ACTIVE' "
                "ORDER BY completed_at DESC NULLS LAST LIMIT 1"
            ),
            {"eid": entity_id},
        )
    ).first()
    return str(run.id) if run else None


# ── B-7 insight annotations ───────────────────────────────────────────────
@entities_router.get(
    "/{display_id}/insights/{ic_id}/annotations",
    response_model=AnnotationListResponse,
)
async def list_annotations(
    display_id: str,
    ic_id: str,
    _user: CurrentUserDep,
    session: SessionDep,
) -> AnnotationListResponse:
    ent = await _resolve_entity(session, display_id)
    rows = (
        await session.execute(
            text(
                """
                SELECT id, ic_id, author, role, body, status, sf_opp_id,
                       created_at
                FROM insight_annotations
                WHERE entity_id = :eid AND ic_id = :ic
                ORDER BY created_at DESC
                """
            ),
            {"eid": ent.id, "ic": ic_id},
        )
    ).all()
    return AnnotationListResponse(
        entity_display_id=display_id,
        ic_id=ic_id,
        items=[
            AnnotationOut(
                id=str(r.id), ic_id=r.ic_id, author=r.author, role=r.role,
                body=r.body, status=r.status, sf_opp_id=r.sf_opp_id,
                created_at=r.created_at,
            )
            for r in rows
        ],
    )


@entities_router.post(
    "/{display_id}/insights/{ic_id}/annotations",
    response_model=AnnotationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_annotation(
    display_id: str,
    ic_id: str,
    body: AnnotationIn,
    user: CurrentUserDep,
    session: SessionDep,
) -> AnnotationOut:
    ent = await _resolve_entity(session, display_id)
    run_id = await _active_run_id(session, str(ent.id))
    if run_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"entity {display_id} has no active run to annotate",
        )
    row = (
        await session.execute(
            text(
                """
                INSERT INTO insight_annotations
                  (run_id, entity_id, ic_id, author, role, body, status, sf_opp_id)
                VALUES
                  (CAST(:rid AS uuid), CAST(:eid AS uuid), :ic, :author, :role,
                   :body, :status, :sf)
                RETURNING id, ic_id, author, role, body, status, sf_opp_id,
                          created_at
                """
            ),
            {
                "rid": run_id, "eid": str(ent.id), "ic": ic_id,
                "author": user.email, "role": user.role,
                "body": body.body, "status": body.status,
                "sf": body.sf_opp_id,
            },
        )
    ).first()
    await session.commit()
    return AnnotationOut(
        id=str(row.id), ic_id=row.ic_id, author=row.author, role=row.role,
        body=row.body, status=row.status, sf_opp_id=row.sf_opp_id,
        created_at=row.created_at,
    )


# ── focus-area list (read-only) ───────────────────────────────────────────
@entities_router.get(
    "/{display_id}/focus-areas",
    response_model=FocusAreaListResponse,
)
async def list_focus_areas(
    display_id: str,
    _user: CurrentUserDep,
    session: SessionDep,
    run: str | None = None,
) -> FocusAreaListResponse:
    """List the parsed focus areas for this entity. Source: `focus_areas`
    table (migration 018+023, populated by the Client Profile parser).

    `?run=<request_id>` scopes the list to that run (transitions audit
    #24: the D3 focus view used to IGNORE the ClientBar run selection and
    always render the active run's priorities). Absent/unknown `run`
    falls back to the most recent ACTIVE run."""
    ent = await _resolve_entity(session, display_id)
    # Resolve the run the same way the heatmap does so ?run= selections
    # stay consistent across the two surfaces.
    run_id: str | None = None
    if run:
        from app.services.run_resolver import maybe_resolve_entity_run
        resolved = await maybe_resolve_entity_run(
            session, display_id, run_request_id=run, allow_in_progress=True,
        )
        if resolved is not None:
            run_id = str(resolved.id)
    if run_id is None:
        active = (
            await session.execute(
                text(
                    "SELECT id FROM runs WHERE entity_id = :eid "
                    "AND status = 'ACTIVE' "
                    "ORDER BY completed_at DESC NULLS LAST LIMIT 1"
                ),
                {"eid": ent.id},
            )
        ).first()
        run_id = str(active.id) if active else None
    if run_id is None:
        return FocusAreaListResponse(entity_display_id=display_id, items=[])
    # Migration 052 (Part 6.1): grounding / financial_ref / pillars_weight
    # ride the same SELECT. Try with the new columns; fall back to the
    # legacy list for envs without migration 052 applied (the new
    # FocusAreaOut fields keep their None defaults).
    #
    # NB: rows are filtered by run_id ONLY. The run was resolved from
    # THIS entity's runs above, so an extra fa.entity_id predicate is
    # redundant — and it silently blanked the focus view whenever an
    # entity-twin merge left rows carrying the sibling twin's entity_id
    # (observed on the 4 *-synthetic twins during the 2026-07 re-ingest).
    # Three-tier column fallback: 056 (linked_insights + provenance) →
    # 052 (grounding/financial_ref/pillars_weight) → legacy 018. A missing
    # newer migration degrades one tier at a time (never loses the older
    # columns), and the FocusAreaOut defaults keep the response shape stable.
    async def _select(cols: str):
        return (
            await session.execute(
                text(
                    f"""
                    SELECT fa.id, fa.title, fa.verbatim_quote, fa.source_path,
                           fa.page_number, fa.involved_subcap_ids{cols}
                    FROM focus_areas fa
                    WHERE fa.run_id = CAST(:rid AS uuid)
                    ORDER BY fa.title
                    """
                ),
                {"rid": run_id},
            )
        ).all()

    try:
        rows = await _select(
            ", fa.grounding, fa.financial_ref, fa.pillars_weight,"
            " fa.linked_insights, fa.enrichment_provenance")
    except Exception:
        try:
            rows = await _select(
                ", fa.grounding, fa.financial_ref, fa.pillars_weight")
        except Exception:
            rows = await _select("")
    # A methodology heading the Client Profile parser mis-read as a focus
    # area ("Each finding is grounded in evidence…", Handoff-Package
    # scaffolding) is pipeline meta, not a client priority — drop it
    # (AlmaBank vetting sample, 2026-07-12).
    _META_TITLE = re.compile(
        r"^each finding\b|handoff package|salesforce account executive lens"
        r"|zennify relevance", re.I)
    rows = [r for r in rows if not _META_TITLE.search(str(r.title or ""))]
    # Rows mined from findings/gaps TABLES are research findings, not the
    # client's stated strategic objectives — never serve them as focus
    # areas (FCMA vetting, 2026-07-12: 'FCMA is nCino customer' rendered
    # as a focus area). The research tier supplies real objectives via
    # the G2 strategic-objectives clarification + 6-month validation.
    rows = [r for r in rows
            if "#findings" not in str(getattr(r, "source_path", "") or "")]
    # Derived KPI rows (Part 6.1b) — one query for every focus area of
    # this entity, grouped by the canonical 32-char fa key. Embedded on
    # FocusAreaOut.kpis so the pack surface serves the strip cold; the
    # per-FA override endpoints stay the write path.
    kpis_by_fa: dict[str, list[dict]] = {}
    # evidence_e_id (migration 060) rides each row so the KPI strip can
    # open the exact evidence its number was read from; migration 056
    # adds evidence_e_ids/rationale/provenance per row for reasoned
    # (current+target) KPIs. The tiered column fallback keeps every
    # older environment serving the strip (missing fields keep their
    # None/[] defaults — response shape stays stable).
    kpi_rows: list = []
    for cols in (
        # 055 + 056 (full column set)
        "fa_id, kpi_label, source_mode, current_value, target_value, "
        "delta, evidence_e_id, evidence_e_ids, rationale, provenance",
        # 056 without 055
        "fa_id, kpi_label, source_mode, current_value, target_value, "
        "delta, evidence_e_ids, rationale, provenance",
        # 055 without 056
        "fa_id, kpi_label, source_mode, current_value, "
        "target_value, delta, evidence_e_id",
        # legacy
        "fa_id, kpi_label, source_mode, current_value, target_value, delta",
    ):
        try:
            # SAVEPOINT per attempt: a missing-column failure must not
            # abort the request transaction before the fallback runs.
            async with session.begin_nested():
                kpi_rows = (
                    await session.execute(
                        text(
                            f"""
                            SELECT {cols}
                            FROM focus_area_kpi_overrides
                            WHERE entity_id = :eid
                            ORDER BY kpi_label
                            """
                        ),
                        {"eid": ent.id},
                    )
                ).all()
            break
        except Exception:
            kpi_rows = []
    for kr in kpi_rows:
        prov = getattr(kr, "provenance", None)
        # read-path: a persisted KPI-override label never renders an internal
        # register code ("Indio ISS-003 SF-Epic" -> "Indio SF-Epic",
        # 2026-07-13 corpus scan) — the derive path is cleaned too, this
        # guards the already-stored overrides
        _klabel = re.sub(r"\s*\b(?:ISS|URF|REQ|QA)-[\dA-Z-]+\b", "",
                         str(kr.kpi_label or "")).strip(" -—·") or kr.kpi_label
        kpis_by_fa.setdefault(kr.fa_id, []).append({
            "kpi_label": _klabel,
            "source_mode": kr.source_mode,
            "current_value": kr.current_value,
            "target_value": kr.target_value,
            "delta": getattr(kr, "delta", None),
            "evidence_e_id": getattr(kr, "evidence_e_id", None),
            "evidence_e_ids": list(getattr(kr, "evidence_e_ids", None) or []),
            "rationale": getattr(kr, "rationale", None),
            "provenance": prov if isinstance(prov, dict) else None,
        })
    # READ-path sanitation (focus_area_sanity): drop DOCX scaffolding
    # rows ("2 Top Findings…"), salvage bare-ID titles from the quote.
    # Rows stay in the table for audit; only rendering is filtered.
    from app.services.focus_area_sanity import clean_focus_area
    from app.services.focus_area_synthesizer import (
        build_linked_insights,
        kpi_fa_key,
    )

    # Linked insight cards (migration 056). The persisted union rides the
    # primary SELECT; when a row still has none (pre-backfill env), it is
    # computed on the fly from this run's insight cards so the pack surface
    # and live serve carry the layered links immediately.
    insight_cards: list[dict] = []
    try:
        ic_rows = (
            await session.execute(
                text(
                    """
                    SELECT id, ic_id, title, severity, what_text,
                           linked_subcap_id, affects, linked_e_ids
                    FROM insight_cards WHERE run_id = CAST(:rid AS uuid)
                    ORDER BY ic_id
                    """
                ),
                {"rid": run_id},
            )
        ).all()
        insight_cards = [{
            "id": str(c.id), "ic_id": c.ic_id, "title": c.title,
            "severity": c.severity, "what_text": c.what_text,
            "linked_subcap_id": c.linked_subcap_id,
            "affects": list(getattr(c, "affects", None) or []),
            "linked_e_ids": list(c.linked_e_ids or []),
        } for c in ic_rows]
    except Exception:
        insight_cards = []

    from app.services.startup_enrich import finalize_title_text
    items: list[FocusAreaOut] = []
    for r in rows:
        keep, display_title = clean_focus_area(r.title, r.verbatim_quote)
        if not keep:
            continue
        # read-time title hygiene: persisted rows predate producer fixes
        # (ellipses, inline E-ID markers, clip fragments) — serve clean
        display_title = finalize_title_text(
            re.sub(r"\[E-[^\]]*\]", "", str(display_title or "")),
            r.verbatim_quote or "") or display_title
        # a title that is a mid-phrase PREFIX of its own quote ("...Brand
        # vs Confirmed" / quote "...Brand vs Confirmed Internal GenAI
        # Deployment") is a clip artifact — re-clip from the quote at a
        # clean boundary
        _q = re.sub(r"\[E-[^\]]*\]", "", str(r.verbatim_quote or "")).strip()
        _t_words = [w for w in re.findall(r"[A-Za-z][\w/&'-]+",
                                          display_title or "") if len(w) > 2]
        _scrambled = (display_title and _q and display_title not in _q
                      and len(_t_words) >= 3
                      and sum(1 for w in _t_words
                              if w.lower() in _q[:160].lower())
                      >= max(3, int(len(_t_words) * 0.7)))
        if display_title and _q and (
                (_q.startswith(display_title)
                 and len(_q) > len(display_title) + 8
                 and not display_title.rstrip().endswith((".", "!", "?")))
                # scrambled derivative: the title's words all sit in the
                # quote head but the title is NOT a substring — an old
                # title-crafter mangle ("BSA/AML Re- Is Non"); rebuild
                or _scrambled):
            from app.services.startup_enrich import clip_clean
            display_title = finalize_title_text(
                clip_clean(_q, 96), _q) or display_title
        grounding = getattr(r, "grounding", None)
        grounding = grounding if isinstance(grounding, dict) else None
        pillars_weight = getattr(r, "pillars_weight", None)
        persisted_links = getattr(r, "linked_insights", None)
        linked_insights = (
            persisted_links if isinstance(persisted_links, list) and persisted_links
            else build_linked_insights(
                fa_subcap_ids=list(r.involved_subcap_ids or []),
                fa_evidence_e_ids=list((grounding or {}).get("evidence_e_ids") or []),
                fa_text=f"{display_title} {r.verbatim_quote or ''}",
                insight_cards=insight_cards,
            )
        )
        # persisted link titles predate the producer hygiene — wash at serve
        linked_insights = [
            {**li, "title": finalize_title_text(
                str(li.get("title") or ""), str(li.get("what_text") or ""))}
            if isinstance(li, dict) else li
            for li in (linked_insights or [])
        ]
        enrichment_prov = getattr(r, "enrichment_provenance", None)
        from app.services.narrative_polish import polish_narrative
        display_title = polish_narrative(
            display_title, target_kind="focus_area",
            target_id=f"{r.id}:title") or display_title
        items.append(FocusAreaOut(
            id=str(r.id), title=display_title,
            verbatim_quote=r.verbatim_quote,
            source_path=r.source_path, page_number=r.page_number,
            involved_subcap_ids=list(r.involved_subcap_ids or []),
            # position-indexed AFTER sanitation so visible cards walk
            # the palette in wireframe order with no gaps.
            colors=_focus_area_colors(len(items)),
            # Migration 052 fields — getattr keeps the legacy
            # column-list fallback path (pre-052 envs) shape-safe.
            grounding=grounding,
            financial_ref=getattr(r, "financial_ref", None),
            pillars_weight=(
                pillars_weight if isinstance(pillars_weight, dict) else None
            ),
            kpis=kpis_by_fa.get(kpi_fa_key(str(r.id)), []),
            linked_insights=linked_insights[:8],
            enrichment_provenance=(
                enrichment_prov if isinstance(enrichment_prov, dict) else None
            ),
        ))
    return FocusAreaListResponse(
        entity_display_id=display_id,
        items=items,
    )


# ── Focus-area synthesis (Gemini-powered intelligence fallback) ─────────
# Operators called this out as the "level of intelligence I need" — when
# the Client Profile DOCX didn't ship strategic priorities, synthesize
# them from the run's actual evidence + recommendations via Gemini, then
# match each focus area back to the recommendations that unlock it.
# Falls back to a deterministic heuristic clustering when Vertex is
# unavailable so the contract holds in every environment.
@entities_router.post(
    "/{display_id}/focus-areas:synthesize",
)
async def synthesize_focus_areas_endpoint(
    display_id: str,
    _user: CurrentUserDep,
    session: SessionDep,
) -> dict:
    """Synthesize focus areas via Gemini + match to recommendations.

    Idempotent: re-running replaces only rows tagged
    `source_path LIKE 'synthesized:%'` — the canonical DOCX-parsed rows
    (if any) stay untouched so the AE can tell synthesized priorities
    from operator-confirmed ones.

    Returns the synthesized focus areas + the recommendation IDs each
    one matches + diagnostic metadata (data_source, reason, message)."""
    from app.services.focus_area_synthesizer import synthesize_focus_areas
    return await synthesize_focus_areas(session, entity_display_id=display_id)


# ── B-8 focus-area KPI overrides ──────────────────────────────────────────
@entities_router.get(
    "/{display_id}/focus-areas/{fa_id}/kpis",
    response_model=KpiOverrideListResponse,
)
async def list_kpi_overrides(
    display_id: str,
    fa_id: str,
    _user: CurrentUserDep,
    session: SessionDep,
) -> KpiOverrideListResponse:
    # `focus_area_kpi_overrides.fa_id` is VARCHAR(32) but the frontend
    # keys by the 36-char hyphenated focus_areas UUID — raw writes used
    # to 500 with StringDataRightTruncation and reads matched nothing.
    # Both endpoints + the synthesizer's KPI seeding key through
    # `kpi_fa_key` (UUID → 32-char hex) so read/write/seed agree.
    from app.services.focus_area_synthesizer import kpi_fa_key

    ent = await _resolve_entity(session, display_id)
    # evidence_e_id (migration 060) with a column-less fallback so
    # pre-060 environments keep serving; the field defaults to None.
    rows: list = []
    for cols in (
        "fa_id, kpi_label, source_mode, current_value, target_value, "
        "evidence_e_id, updated_at",
        "fa_id, kpi_label, source_mode, current_value, target_value, "
        "updated_at",
    ):
        try:
            async with session.begin_nested():
                rows = (
                    await session.execute(
                        text(
                            f"""
                            SELECT {cols}
                            FROM focus_area_kpi_overrides
                            WHERE entity_id = :eid AND fa_id = :fa
                            ORDER BY kpi_label
                            """
                        ),
                        {"eid": ent.id, "fa": kpi_fa_key(fa_id)},
                    )
                ).all()
            break
        except Exception:
            rows = []
    return KpiOverrideListResponse(
        entity_display_id=display_id,
        fa_id=fa_id,
        items=[
            KpiOverrideOut(
                fa_id=r.fa_id, kpi_label=r.kpi_label, source_mode=r.source_mode,
                current_value=r.current_value, target_value=r.target_value,
                evidence_e_id=getattr(r, "evidence_e_id", None),
                updated_at=r.updated_at,
            )
            for r in rows
        ],
    )


@entities_router.put(
    "/{display_id}/focus-areas/{fa_id}/kpis",
    response_model=KpiOverrideListResponse,
)
async def put_kpi_overrides(
    display_id: str,
    fa_id: str,
    body: KpiOverridePut,
    _user: CurrentUserDep,
    session: SessionDep,
) -> KpiOverrideListResponse:
    from app.services.focus_area_synthesizer import kpi_fa_key

    ent = await _resolve_entity(session, display_id)
    # Migration 055 honesty rule: an AE override REPLACES the derived
    # numbers, so the derived evidence anchor no longer describes them —
    # clear evidence_e_id on update. Probed (not assumed) so pre-055
    # environments keep the legacy statement.
    has_ev_col = (
        await session.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'focus_area_kpi_overrides' "
                "  AND column_name = 'evidence_e_id'"
            )
        )
    ).first() is not None
    ev_clause = ", evidence_e_id = NULL" if has_ev_col else ""
    for ov in body.overrides:
        await session.execute(
            text(
                f"""
                INSERT INTO focus_area_kpi_overrides
                  (entity_id, fa_id, kpi_label, source_mode, current_value,
                   target_value, updated_at)
                VALUES
                  (CAST(:eid AS uuid), :fa, :label, :mode, :cur, :tgt, NOW())
                ON CONFLICT (entity_id, fa_id, kpi_label) DO UPDATE SET
                  source_mode = EXCLUDED.source_mode,
                  current_value = EXCLUDED.current_value,
                  target_value = EXCLUDED.target_value,
                  updated_at = NOW(){ev_clause}
                """
            ),
            {
                # kpi_fa_key: fa_id column is VARCHAR(32); see GET above.
                "eid": str(ent.id), "fa": kpi_fa_key(fa_id),
                "label": ov.kpi_label,
                "mode": ov.source_mode, "cur": ov.current_value,
                "tgt": ov.target_value,
            },
        )
    await session.commit()
    return await list_kpi_overrides(display_id, fa_id, _user, session)


# ── B-9 notifications ─────────────────────────────────────────────────────
@notifications_router.get("", response_model=NotificationListResponse)
async def list_notifications(
    user: CurrentUserDep,
    session: SessionDep,
) -> NotificationListResponse:
    rows = (
        await session.execute(
            text(
                """
                SELECT id, kind, title, body, entity_id, route, seen_at,
                       created_at
                FROM notifications
                WHERE user_id = CAST(:uid AS uuid)
                ORDER BY created_at DESC LIMIT 100
                """
            ),
            {"uid": user.user_id},
        )
    ).all()
    items = [
        NotificationOut(
            id=str(r.id), kind=r.kind, title=r.title, body=r.body,
            entity_id=str(r.entity_id) if r.entity_id else None,
            route=r.route, seen_at=r.seen_at, created_at=r.created_at,
        )
        for r in rows
    ]
    unseen = sum(1 for i in items if i.seen_at is None)
    return NotificationListResponse(items=items, unseen_count=unseen)


@notifications_router.post(":mark-read")
async def mark_notifications_read(
    body: MarkReadRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, int]:
    if body.ids:
        result = await session.execute(
            text(
                """
                UPDATE notifications SET seen_at = NOW()
                WHERE user_id = CAST(:uid AS uuid)
                  AND seen_at IS NULL
                  AND id = ANY(CAST(:ids AS uuid[]))
                """
            ),
            {"uid": user.user_id, "ids": body.ids},
        )
    else:
        result = await session.execute(
            text(
                "UPDATE notifications SET seen_at = NOW() "
                "WHERE user_id = CAST(:uid AS uuid) AND seen_at IS NULL"
            ),
            {"uid": user.user_id},
        )
    await session.commit()
    return {"marked_read": int(result.rowcount or 0)}
