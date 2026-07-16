"""D2 Insights + Evidence drawer endpoints."""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import text

from app.deps import CurrentUserDep, SessionDep, ViewModeDep
from app.schemas.insights import (
    EvidenceDrawerItem,
    EvidenceDrawerResponse,
    InsightCardOut,
    InsightListResponse,
)
from app.services.audience_strip import strip_and_respond
from app.services.parsers.section_analysis import (
    LEGACY_COUNTER_NOTE,
    counter_evidence_note,
)
from app.services.section_routing import (
    build_narrative_insights,
    load_sections_for_run,
)

# Shared presentation twins — the SAME helpers the offline pack patcher
# (apply_startup_data_fixes._enrich_insights) uses, so pack==live on the
# flag/pillar keys (qa_pack_parity structural contract).
from app.services.startup_enrich import flag_from_severity, pillar_of

router = APIRouter(prefix="/api/v1/entities", tags=["insights"])

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


@router.get("/{display_id}/insights", response_model=InsightListResponse)
async def insights(
    display_id: str,
    _user: CurrentUserDep,
    session: SessionDep,
    view: ViewModeDep,
    run: str | None = None,
) -> InsightListResponse:
    # 2026-06-05: closed the "run selector decorative" QA finding -- the
    # ClientBar run dropdown writes ?run=REQ-XXX but pre-fix this route
    # only ever read the latest ACTIVE run. resolve_entity_run handles
    # both: explicit request_id wins; absent -> ACTIVE fallback. The
    # resolved request_id round-trips on `run_request_id` so the
    # frontend can confirm which run actually rendered.
    from app.services.run_resolver import resolve_entity_run
    resolved = await resolve_entity_run(
        session, display_id, run_request_id=run,
    )
    # Migration 046 (Part 5.1): affects / platforms / interconnections /
    # theme ride the same SELECT. Try with the new columns; fall back to
    # the legacy list for envs without migration 046 applied (the new
    # InsightCardOut fields keep their []/None defaults).
    try:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT id, ic_id, severity, title, what_text, why_text,
                           so_what_text, linked_subcap_id, linked_e_ids,
                           source_rec_id,
                           affects, platforms, interconnections, theme
                    FROM insight_cards
                    WHERE run_id = :rid
                    """
                ),
                {"rid": resolved.id},
            )
        ).all()
    except Exception:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT id, ic_id, severity, title, what_text, why_text,
                           so_what_text, linked_subcap_id, linked_e_ids,
                           source_rec_id
                    FROM insight_cards
                    WHERE run_id = :rid
                    """
                ),
                {"rid": resolved.id},
            )
        ).all()
    # Grounding contract (fail-closed): an insight card with no linked
    # evidence is an uncited argument — it never ships. The deepen repair
    # pass relinks from inline citations / anchor-subcap evidence and
    # files a G3 clarification for the rest; this filter is the
    # last-line guarantee for both the live route and the pack bake.
    rows = [r for r in rows if r.linked_e_ids]
    # Pre-fetch evidence for the entire run so we can compute confidence
    # bands + counter-signal E-IDs per insight without N+1 queries.
    # `linked_e_ids` are the SUPPORTING evidence; counter-signals are
    # any same-subcap evidence whose signal_direction disagrees with
    # the insight severity (high severity = "negative" claim about the
    # subcap; if any evidence on that subcap is signal_direction='positive',
    # it counters the headline).
    ev_rows = (
        await session.execute(
            text(
                """
                SELECT e_id, tier, claim_type, linked_subcap_ids, excerpt
                FROM evidence_index
                WHERE run_id = :rid
                """
            ),
            {"rid": resolved.id},
        )
    ).all()
    # Map subcap_id -> list[(e_id, tier, claim_type)]
    evidence_by_subcap: dict[str, list[tuple]] = {}
    evidence_by_eid: dict[str, tuple] = {}
    excerpt_by_eid: dict[str, str] = {}
    for ev in ev_rows:
        evidence_by_eid[ev.e_id] = (ev.tier, ev.claim_type)
        excerpt_by_eid[ev.e_id] = ev.excerpt or ""
        for scid in (ev.linked_subcap_ids or []):
            evidence_by_subcap.setdefault(scid, []).append(
                (ev.e_id, ev.tier, ev.claim_type),
            )

    # Recs for this run → the "Related recommendation" callout (A1: works on
    # existing data, no re-ingest). Prefix-aware match: insight anchors are
    # often coarse (P#C#) while recs carry leaf target_subcap_ids (P#C#.x.y)
    # — mirrors the grounding fallback in dma_package.
    rec_rows = (
        await session.execute(
            text(
                """
                SELECT rec_id, target_subcap_ids
                FROM recommendations
                WHERE run_id = :rid
                """
            ),
            {"rid": resolved.id},
        )
    ).all()
    rec_targets: list[tuple[str, list[str]]] = [
        (rr.rec_id, list(rr.target_subcap_ids or [])) for rr in rec_rows
    ]

    def _related_rec_ids(anchor: str) -> list[str]:
        if not anchor:
            return []
        matched: list[str] = []
        for rec_id, subs in rec_targets:
            if (rec_id not in matched
                    and any(s == anchor or s.startswith(anchor + ".") for s in subs)):
                matched.append(rec_id)
        return sorted(matched)

    def _confidence_band(linked_e_ids: list[str]) -> str:
        """Derive the band from supporting evidence count + tier mix.

        Contract (locked by `test_insights_confidence_band`):
          high   = ≥ 3 evidence rows, all tier ≥ 4
          medium = ≥ 2 evidence rows OR mixed-tier 3-row set
          low    = single evidence row OR any tier ≤ 2 in the set
        """
        if not linked_e_ids:
            return "low"
        tiers = [evidence_by_eid.get(eid, (0, ""))[0] for eid in linked_e_ids]
        tiers = [t for t in tiers if t is not None and t > 0]
        if not tiers:
            return "low"
        if len(tiers) == 1:
            return "low"
        if min(tiers) <= 2:
            return "low"
        if len(tiers) >= 3 and min(tiers) >= 4:
            return "high"
        return "medium"

    def _counter_e_ids(linked_subcap_id: str, supporting: list[str],
                       severity: str) -> list[str]:
        """Counter-signal E-IDs for the insight's subcap.

        Heuristic for the "argue, not just render" contract:
          - For a HIGH/CRITICAL insight (the subcap is a gap), any
            evidence on that same subcap whose `claim_type` is
            'strength' or 'positive' is a counter-signal.
          - For a LOW/MEDIUM insight (the subcap is a strength claim),
            any evidence whose `claim_type` is 'risk' / 'gap' counters.
          - Supporting E-IDs (already in linked_e_ids) are excluded.

        Returns up to 5 E-IDs; ordered by tier DESC then alpha. Empty
        means the model identified no contradicting evidence — UI
        renders "no counter-signals identified" rather than nothing.
        """
        on_subcap = evidence_by_subcap.get(linked_subcap_id, [])
        is_gap = severity in ("critical", "high")
        positive_terms = {"strength", "positive", "win"}
        negative_terms = {"risk", "gap", "weakness", "negative", "concern"}
        target = positive_terms if is_gap else negative_terms
        counters = [
            (e_id, tier) for (e_id, tier, ct) in on_subcap
            if e_id not in set(supporting)
               and ct
               and ct.lower() in target
        ]
        counters.sort(key=lambda x: (-(x[1] or 0), x[0]))
        return [e for (e, _) in counters[:5]]

    from app.services.narrative_polish import polish_narrative

    def _polish(text, rid, field):
        out = polish_narrative(text, target_kind="insight_card",
                               target_id=f"{rid}:{field}") or ""
        # read-path guarantee: a card body never renders markdown emphasis
        # ("(2) **'Lending" -> "(2) 'Lending") or an internal register code,
        # even if a persisted row (kept gold rung / gate-fail) still carries
        # it (2026-07-13 corpus scan)
        if "**" in out:
            out = out.replace("**", "")
        out = re.sub(r"\s*[(\[]?(?:ISS|URF|REQ|QA)-[\dA-Z-]+[)\]]?", "", out)
        return re.sub(r"\s{2,}", " ", out).strip() if out else out

    items: list[InsightCardOut] = []
    for r in rows:
        supporting = list(r.linked_e_ids or [])
        interconnections = getattr(r, "interconnections", None)
        # Derive-time counter-signals (interconnection mining, plan 5.1)
        # win when persisted — they run nlp.polarity over the excerpts,
        # so they catch the corpus's neutral claim_type labels
        # (EVIDENCE/FACT ≈ 40%) that the read-time claim-type heuristic
        # below cannot classify. Read-time stays as the fallback for
        # rows persisted before the re-derivation.
        stored_counters = [
            e
            for ic in (interconnections
                       if isinstance(interconnections, list) else [])
            if isinstance(ic, dict) and ic.get("kind") == "counter_evidence"
            for e in (ic.get("e_ids") or [])
            if isinstance(e, str)
        ]
        counters_final = stored_counters[:5] or _counter_e_ids(
            r.linked_subcap_id, supporting, r.severity,
        )
        # "But also…" must ANALYZE the counter-evidence content (2026-07-06
        # mandate) — compose/upgrade the counter_evidence note from the
        # rows' actual excerpts (verbatim-quoted, E-ID-attributed). Rows
        # persisted with the legacy stub label are upgraded at read time;
        # a real analyzed note (future derive runs) is served as stored.
        inter_list = list(interconnections) if isinstance(
            interconnections, list) else []
        if counters_final:
            note = counter_evidence_note(
                [{"e_id": e, "excerpt": excerpt_by_eid.get(e, "")}
                 for e in counters_final],
                r.severity,
            )
            if note:
                upgraded, has_counter_entry = [], False
                for ic in inter_list:
                    if isinstance(ic, dict) and ic.get("kind") == "counter_evidence":
                        has_counter_entry = True
                        if str(ic.get("note") or "").strip() in (
                                "", LEGACY_COUNTER_NOTE):
                            ic = {**ic, "note": note}
                    upgraded.append(ic)
                if not has_counter_entry:
                    upgraded.append({
                        "kind": "counter_evidence",
                        "target_id": r.linked_subcap_id,
                        "note": note, "e_ids": counters_final,
                    })
                inter_list = upgraded
        items.append(
            InsightCardOut(
                id=str(r.id), ic_id=r.ic_id, severity=r.severity,
                title=_polish(r.title, r.id, "title"),
                what_text=_polish(r.what_text, r.id, "what"),
                why_text=_polish(r.why_text, r.id, "why"),
                so_what_text=_polish(r.so_what_text, r.id, "so_what"),
                linked_subcap_id=r.linked_subcap_id,
                linked_e_ids=supporting,
                counter_e_ids=counters_final,
                confidence_band=_confidence_band(supporting),
                source_rec_id=r.source_rec_id,
                related_rec_ids=_related_rec_ids(r.linked_subcap_id),
                # Migration 046 fields — getattr keeps the legacy
                # column-list fallback path (pre-046 envs) shape-safe.
                affects=list(getattr(r, "affects", None) or []),
                platforms=list(getattr(r, "platforms", None) or []),
                interconnections=inter_list,
                theme=getattr(r, "theme", None),
                pillar=pillar_of(r.linked_subcap_id),
                flag=flag_from_severity(r.severity),
            )
        )
    items.sort(key=lambda i: (_SEVERITY_ORDER.get(i.severity, 9), i.ic_id))

    # Narrative — populated from document_sections per pillar deep-dive.
    sections = await load_sections_for_run(session, resolved.id, entity_id=resolved.entity_id)
    narrative = build_narrative_insights(sections)

    payload = InsightListResponse(
        entity_display_id=display_id, run_request_id=resolved.request_id,
        items=items, narrative=narrative,
    )
    # Audience-strip server-side as defense-in-depth. Customer view
    # drops insight rationale_internal / analyst_note nested fields
    # plus any future internal-only key surfaced via this response.
    return strip_and_respond(payload, view.audience, InsightListResponse)


def parse_e_ids(raw: str | None, *, cap: int = 100) -> list[str]:
    """Comma-separated `?e_ids=` → ordered de-duped list (pure; unit-tested).

    Bounded at `cap` so a hostile query string can't inflate the ANY()
    array — the drawer's realistic payload is a card's citation list
    (single digits). Non-str input (e.g. the FastAPI Query sentinel under
    direct route-to-route Python composition — see
    tests/test_query_sentinel_regression.py) coerces to [].
    """
    if not isinstance(raw, str) or not raw:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for tok in raw.split(","):
        t = tok.strip()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
        if len(out) >= cap:
            break
    return out


# Hierarchical subcap predicate — exact tag OR prefix roll-up in BOTH
# directions, matching attach_evidence_ladder's derive-time semantics
# (section_analysis.py): a category anchor (P2C1) matches leaf-tagged rows
# (P2C1.1.6) and a leaf anchor inherits category-tagged rows. Pre-fix the
# filter was exact-match `:sid = ANY(linked_subcap_ids)`, so 72% of insight
# cards opened a zero-row drawer (2026-07-06 diagnosis, 10-client sample).
_SUBCAP_MATCH_SQL = (
    "EXISTS (SELECT 1 FROM unnest(linked_subcap_ids) AS tag "
    "WHERE tag = :sid OR tag LIKE :sid_kids OR :sid LIKE tag || '.%')"
)


def subcap_matches(scope: str, tags: list[str] | None) -> bool:
    """Python twin of ``_SUBCAP_MATCH_SQL`` (kept adjacent so the two can
    never drift; the frontend drawer applies the same rule client-side)."""
    return any(
        t == scope or t.startswith(scope + ".") or scope.startswith(t + ".")
        for t in (tags or [])
    )


@router.get("/{display_id}/evidence", response_model=EvidenceDrawerResponse)
async def evidence(
    display_id: str,
    _user: CurrentUserDep,
    session: SessionDep,
    view: ViewModeDep,
    subcap_id: str | None = Query(default=None),
    min_tier: int = Query(default=8, ge=1, le=8),
    limit: int = Query(default=100, ge=1, le=500),
    # Exact single E-ID lookup (?e_id=E-047, 2026-07-06): a citation click
    # must ALWAYS resolve its evidence row — scope widens run → entity.
    e_id: str | None = Query(default=None, max_length=16),
    # Comma-separated E-IDs cited by the opening card. These rows are
    # UNIONED into the result regardless of the subcap/tier filters —
    # the drawer must always be able to show what the card cites.
    e_ids: str | None = Query(default=None),
    # Plain None default (not Query) so the handler stays safe under
    # route-to-route Python composition; see app/routers/heatmap.py
    # comment + tests/test_query_sentinel_regression.py.
    run: str | None = None,
) -> EvidenceDrawerResponse:
    # 2026-06-05: honour the operator's ?run= selection for evidence too --
    # without this the evidence drawer always rendered the ACTIVE-run
    # corpus regardless of which run was selected in the heatmap above.
    from app.services.run_resolver import resolve_entity_run
    resolved = await resolve_entity_run(
        session, display_id, run_request_id=run,
    )
    # NULL tier = "source states no canonical tier" (migration 055),
    # treated as WEAKER than any known tier: visible at the loosest
    # filter (default min_tier=8) but excluded once the operator
    # tightens to "Tier N or better" — an unknown tier can't honestly
    # claim to qualify.
    cited = parse_e_ids(e_ids)
    if e_id is not None:
        # 2026-07-06: exact E-ID lookup (?e_id=E-047) — a citation click must
        # ALWAYS resolve its evidence row, even when it falls outside the
        # drawer's current subcap scope or belongs to a different run of the
        # same entity. Scope widens run → entity for this mode; rows from the
        # resolved run still sort first so the freshest copy renders on top.
        scope = ["entity_id = :ent_id", "e_id = :e_id",
                 "COALESCE(tier, 8) <= :min_tier"]
        params: dict[str, object] = {
            "ent_id": resolved.entity_id, "e_id": e_id,
            "min_tier": min_tier, "lim": limit, "rid": resolved.id,
        }
        if subcap_id is not None:
            scope.append(_SUBCAP_MATCH_SQL)
            params["sid"] = subcap_id
            params["sid_kids"] = subcap_id + ".%"
        where_sql = " AND ".join(scope)
        order = ("(run_id = :rid) DESC, COALESCE(tier, 8) ASC, "
                 "published_date DESC NULLS LAST")
    else:
        scope = ["COALESCE(tier, 8) <= :min_tier"]
        params = {"rid": resolved.id, "min_tier": min_tier, "lim": limit}
        if subcap_id is not None:
            scope.append(_SUBCAP_MATCH_SQL)
            params["sid"] = subcap_id
            params["sid_kids"] = subcap_id + ".%"
        predicate = " AND ".join(scope)
        order = "COALESCE(tier, 8) ASC, published_date DESC NULLS LAST"
        if cited:
            # Cited rows bypass every filter AND sort first, so they can never
            # be pushed past :lim by an unrelated low-tier pile-up.
            predicate = f"(({predicate}) OR e_id = ANY(:eids))"
            params["eids"] = cited
            order = f"(e_id = ANY(:eids)) DESC, {order}"
        where_sql = f"run_id = :rid AND ({predicate})"
    rows = (
        await session.execute(
            text(
                f"""
                SELECT id, e_id, source_name, source_url, excerpt,
                       claim_type, tier, recency_months, published_date,
                       linked_subcap_ids
                FROM evidence_index
                WHERE {where_sql}
                ORDER BY {order}
                LIMIT :lim
                """
            ),
            params,
        )
    ).all()
    def _served_excerpt(r) -> str:
        # Every drawer row shows a real excerpt or an EXPLICIT honest
        # state — never a bare "(no excerpt)" token. The 2026-07-12
        # sweep found 1,030/10,346 active rows whose ingest carried no
        # excerpt text; the source artifact re-mine is the warm-path
        # fill, and each affected entity carries a G3 clarification.
        ex = (r.excerpt or "").strip()
        if ex and ex not in ("(no excerpt)", "N/A", "-") and len(ex) >= 15:
            return ex
        src = (r.source_name or "the cited source").strip()
        return (f"No excerpt on file for this citation of {src} — "
                f"flagged for corroborating research (G3); the source "
                f"link remains the anchor.")

    items = [
        EvidenceDrawerItem(
            id=str(r.id), e_id=r.e_id, source_name=r.source_name,
            source_url=r.source_url, excerpt=_served_excerpt(r),
            claim_type=r.claim_type,
            tier=r.tier,
            recency_months=r.recency_months,
            published_date=str(r.published_date) if r.published_date else None,
            linked_subcap_ids=list(r.linked_subcap_ids or []),
        )
        for r in rows
    ]
    payload = EvidenceDrawerResponse(
        entity_display_id=display_id, run_request_id=resolved.request_id,
        filter_subcap_id=subcap_id, filter_min_tier=min_tier,
        filter_e_id=e_id, filter_e_ids=cited, items=items,
    )
    # Audience-strip — drops rationale_internal / analyst_note / any
    # other internal-only key that future EvidenceDrawerItem extensions
    # might surface.
    return strip_and_respond(payload, view.audience, EvidenceDrawerResponse)


async def _active_run(session, display_id: str):
    ent = (
        await session.execute(
            text("SELECT id FROM entities WHERE display_id = :did"),
            {"did": display_id},
        )
    ).first()
    if ent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"entity {display_id} not found")
    return (
        await session.execute(
            text(
                """
                SELECT id, request_id
                FROM runs
                WHERE entity_id = :eid AND status = 'ACTIVE'
                ORDER BY completed_at DESC NULLS LAST LIMIT 1
                """
            ),
            {"eid": ent.id},
        )
    ).first()
