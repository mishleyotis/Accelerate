"""Focus-area synthesis service — Gemini-powered fallback when the
Client Profile DOCX didn't ship explicit strategic priorities.

The contract:

  • Operators ingest a DMA package via /api/v1/ingest/package. If the
    `04_reports/{Entity}_Client_Profile_Research_Report.docx` is
    present, `parsers/client_profile.parse_client_profile_path`
    extracts focus areas verbatim from the strategic-priorities
    section. These are the canonical focus areas — `data-source="docx"`.

  • If no Client Profile DOCX shipped, `focus_areas` is empty for the
    run. The heatmap defaults to Focus Areas view and renders an empty
    state. AEs are stranded.

  • This module fills the gap. `synthesize_focus_areas(...)`:
      1. Pulls the entity's per-pillar score gaps (peer median minus entity).
      2. Pulls the run's recommendations + the subcaps each targets.
      3. Asks Gemini Flash to cluster the 5-10 most actionable
         subcap_ids into 3-5 strategic focus areas, each with a title,
         description, and list of involved_subcap_ids.
      4. Validates the response: every involved_subcap_id MUST exist in
         the run's subcap_scores set (no hallucinations); each focus
         area MUST cluster ≥2 subcaps to qualify.
      5. Matches each focus area back to the recommendations whose
         `target_subcap_ids` overlap — so the FE can show "this focus
         area unlocks recs IC-005, IC-012, …".
      6. Persists into focus_areas + (sentinel) source_path
         "synthesized:gemini-flash-v1" so re-runs of the same
         (run_id, fingerprint) hit the synthesis_orchestrator cache and
         cost 0 tokens.

  • Falls back to a deterministic heuristic when Vertex creds are
    absent (local dev): clusters subcaps by pillar (P1/P2/P3/P4) and
    picks the N lowest-scoring ones per pillar. The output is
    `data-source="heuristic"` so the FE can label it differently.

This is the "intelligence" the operator asked for — focus areas are
synthesized from the run's actual evidence + scores, then matched back
to recommendations so the AE sees a cohesive narrative ("modernize
member experience" + the 3 recs that get them there).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

# Focus areas / strategic objectives are re-validated + refreshed HALF-YEARLY
# once loaded (operator mandate 2026-07-08): the report's stated priorities and
# the Gemini-extracted ones both go stale, and the heatmap must never serve
# months-old strategy. The periodic recompute cadence re-runs synthesis for any
# focus row older than this; the synthesis cache TTL matches so a refresh is a
# genuine re-extraction, not a cache replay.
FOCUS_REFRESH_DAYS = 182


def focus_needs_refresh(loaded_at: object, today: object | None = None) -> bool:
    """True when persisted focus areas are older than the half-yearly window and
    must be re-validated / re-extracted. Pure + timezone-tolerant."""
    from datetime import UTC, datetime
    if loaded_at is None:
        return True
    if isinstance(loaded_at, str):
        try:
            loaded_at = datetime.fromisoformat(loaded_at.replace("Z", "+00:00"))
        except ValueError:
            return True
    now = today if isinstance(today, datetime) else datetime.now(UTC)
    if getattr(loaded_at, "tzinfo", None) is None:
        loaded_at = loaded_at.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return (now - loaded_at).days >= FOCUS_REFRESH_DAYS


@dataclass
class SynthesizedFocusArea:
    title: str
    description: str
    involved_subcap_ids: list[str]
    matched_recommendation_ids: list[str] = field(default_factory=list)
    data_source: str = "gemini-flash"  # | "heuristic"
    rationale: str = ""
    # Migration 052 (Part 6.1 grounding fix): real anchors on every row.
    grounding: dict[str, Any] | None = None
    financial_ref: str | None = None
    pillars_weight: dict[str, int] | None = None
    kpis: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
            "involved_subcap_ids": list(self.involved_subcap_ids),
            "matched_recommendation_ids": list(self.matched_recommendation_ids),
            "data_source": self.data_source,
            "rationale": self.rationale,
            "grounding": self.grounding,
            "financial_ref": self.financial_ref,
            "pillars_weight": self.pillars_weight,
            "kpis": list(self.kpis),
        }


@dataclass
class _RunContext:
    """Read-only snapshot of the run state the synthesizer needs."""
    run_id: str
    entity_id: str
    entity_name: str
    subvertical: str | None
    pillar_means: dict[str, float]            # {"P1": 2.3, ...}
    low_scoring_subcaps: list[dict[str, Any]] # [{"subcap_id":..., "score":..., "rationale":...}]
    recommendations: list[dict[str, Any]]     # [{"rec_id":..., "title":..., "target_subcap_ids":[...]}]
    all_subcap_ids: set[str]                  # for hallucination validation
    catalog_version: str | None = None        # run-pinned ccg version (pillars_weight tiers)
    # The client's OWN strategic signals from ALL sources (thought-leadership,
    # financials, the firmographics narrative, the analyst SCQA) — so when the
    # research report is thin the synthesizer still grounds strategic objectives
    # in the client's actual priorities, not a generic pillar fallback.
    strategic_signals: list[str] = field(default_factory=list)


async def _load_run_context(
    session: AsyncSession, *, entity_display_id: str,
) -> _RunContext | None:
    """Build the run context the synthesizer needs. Returns None when
    the entity has no run (we don't synthesize for empty entities)."""
    ent = (await session.execute(
        text("""
            SELECT e.id AS entity_id, e.name, e.subvertical,
                   r.id AS run_id, r.ccg_catalog_version
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

    pillar_rows = (await session.execute(
        text("""
            SELECT LEFT(ss.subcap_id, 2) AS pillar_id,
                   AVG(ss.score)::float AS mean_score
              FROM subcap_scores ss
             WHERE ss.run_id = :rid
             GROUP BY LEFT(ss.subcap_id, 2)
        """),
        {"rid": ent.run_id},
    )).all()
    pillar_means = {row.pillar_id: round(float(row.mean_score), 2) for row in pillar_rows}

    # Lowest-scoring subcaps — these are the gaps we want to cluster.
    # Pull up to 24 (4 pillars x 6 subcaps) so the LLM has a real
    # signal but the prompt stays within token budget.
    low_rows = (await session.execute(
        text("""
            SELECT ss.subcap_id, ss.score, ss.rationale
              FROM subcap_scores ss
             WHERE ss.run_id = :rid
               AND ss.score IS NOT NULL
             ORDER BY ss.score ASC, ss.subcap_id ASC
             LIMIT 24
        """),
        {"rid": ent.run_id},
    )).all()
    low_subcaps = [{
        "subcap_id": r.subcap_id,
        "score": round(float(r.score), 2) if r.score is not None else None,
        "rationale": (r.rationale or "")[:280],
    } for r in low_rows]

    all_ids_rows = (await session.execute(
        text("SELECT DISTINCT subcap_id FROM subcap_scores WHERE run_id = :rid"),
        {"rid": ent.run_id},
    )).all()
    all_ids = {row.subcap_id for row in all_ids_rows}

    # Drop subvertical-NA subcaps so they never seed a focus area: an
    # insurance-carrier overlay leaf (".IC1" — "AI Claims Estimation") scored 1
    # on a Farm-Credit entity survived into clustering because it wasn't
    # skipped at persist (score 1, not the 0 the NA filter drops). A5-NA /
    # LOB-mismatch subcaps are out of scope for THIS subvertical.
    from app.services.focus_area_sanity import subcap_out_of_scope
    _oos = {
        sid for sid in all_ids
        if subcap_out_of_scope(sid, subvertical=ent.subvertical)
    }
    if _oos:
        all_ids -= _oos
        low_subcaps = [s for s in low_subcaps if s["subcap_id"] not in _oos]

    rec_rows = (await session.execute(
        text("""
            SELECT rec_id, title, description, target_subcap_ids, platform_id
              FROM recommendations
             WHERE run_id = :rid
             ORDER BY rec_id
        """),
        {"rid": ent.run_id},
    )).all()
    recs = [{
        "rec_id": r.rec_id,
        "title": r.title or "",
        "description": (r.description or "")[:240],
        "target_subcap_ids": list(r.target_subcap_ids or []),
        "platform_id": r.platform_id,
    } for r in rec_rows]

    # The client's OWN strategic signals from ALL sources — used to ground the
    # synthesis when the research report is thin (the operator ask: "if this
    # misses in the research report, get it from the entity financials, reports,
    # interviews, publications, thought-leadership"). All entity-scoped, so no
    # peer contamination; capped so the bundle stays under the token budget.
    signals: list[str] = []
    firm = (await session.execute(text(
        "SELECT narrative_md, financial_highlights, thought_leadership "
        "FROM firmographics WHERE entity_id = :eid"),
        {"eid": str(ent.entity_id)})).first()
    if firm is not None:
        if firm.narrative_md:
            signals.append(f"PROFILE: {str(firm.narrative_md)[:600]}")
        fh = firm.financial_highlights if isinstance(firm.financial_highlights, dict) else {}
        for line in (fh.get("lines") or [])[:4]:
            signals.append(f"FINANCIAL: {str(line)[:200]}")
        tl = firm.thought_leadership
        tl_items = tl if isinstance(tl, list) else (tl.get("items") if isinstance(tl, dict) else [])
        for item in (tl_items or [])[:4]:
            t = item.get("title") or item.get("headline") if isinstance(item, dict) else str(item)
            if t:
                signals.append(f"THOUGHT-LEADERSHIP: {str(t)[:200]}")
    sc = (await session.execute(text(
        "SELECT body FROM document_sections WHERE run_id = :rid "
        "AND section_kind IN ('executive_summary_scqa','roadmap','recommendations') "
        "AND COALESCE(body,'') <> '' ORDER BY ordinal LIMIT 2"),
        {"rid": ent.run_id})).all()
    for s in sc:
        signals.append(f"ANALYST: {str(s.body)[:500]}")

    return _RunContext(
        run_id=str(ent.run_id),
        entity_id=str(ent.entity_id),
        entity_name=ent.name,
        subvertical=ent.subvertical,
        pillar_means=pillar_means,
        low_scoring_subcaps=low_subcaps,
        recommendations=recs,
        all_subcap_ids=all_ids,
        catalog_version=ent.ccg_catalog_version,
        strategic_signals=signals,
    )


def _build_prompt(ctx: _RunContext) -> str:
    """Render the structured Gemini prompt. Deliberately compact so we
    stay well under the 16k bundle cap."""
    return (
        "You are a strategy consultant clustering capability gaps into "
        "executable focus areas for a financial services client.\n\n"
        f"CLIENT: {ctx.entity_name} (subvertical: {ctx.subvertical or 'unknown'})\n"
        f"PILLAR_MEANS: {json.dumps(ctx.pillar_means)}\n\n"
        "LOW_SCORING_SUBCAPS (the gaps to cluster):\n"
        + "\n".join(
            f"  - {s['subcap_id']}  score={s['score']}  "
            f"why={s['rationale'][:160] or '(no rationale)'}"
            for s in ctx.low_scoring_subcaps[:18]
        )
        + "\n\nEXISTING_RECOMMENDATIONS (already proposed):\n"
        + "\n".join(
            f"  - {r['rec_id']}  {r['title'][:80]}  targets={r['target_subcap_ids']}"
            for r in ctx.recommendations[:8]
        )
        + (("\n\nCLIENT_STRATEGIC_SIGNALS (this client's OWN priorities from its "
            "profile, financials, thought-leadership and the analyst narrative — "
            "ground the focus areas in THESE, not generic pillar themes):\n"
            + "\n".join(f"  - {s}" for s in ctx.strategic_signals[:10]))
           if ctx.strategic_signals else "")
        + "\n\nReturn a JSON object with shape:\n"
        '{ "focus_areas": [ { "title": "<≤8 word strategic priority>", '
        '"description": "<one paragraph, ≤320 chars, describes the bet>", '
        '"involved_subcap_ids": ["<subcap_id from LOW_SCORING_SUBCAPS>", ...], '
        '"rationale": "<why these cluster — ≤200 chars>" } ] }\n\n'
        "Rules:\n"
        " - 3 to 5 focus areas total. NO MORE.\n"
        " - Each focus area MUST involve at least 2 subcap_ids from the "
        "LOW_SCORING_SUBCAPS list. Do NOT invent new subcap_ids.\n"
        " - Focus areas should be NON-OVERLAPPING — each subcap_id "
        "appears in at most ONE focus area.\n"
        " - Titles are operator-readable strategic bets, not capability "
        "names ('Modernize member experience' not 'P2C1.1.1 fix').\n"
    )


# Concrete (non-scaffolding) pillar-domain headlines — the fallback when no
# subcap rationale yields a grounded opportunity title. "Sharpen strategic
# posture" was pure scaffolding; these at least name the pillar's domain.
_PILLAR_FALLBACK_TITLE = {
    "P1": "Close governance & digital-strategy gaps",
    "P2": "Modernize customer experience",
    "P3": "Operationalize process automation",
    "P4": "Build the data foundation",
}
_PILLAR_BODY = {
    "P1": "Reset enterprise priorities + governance cadence to close the "
          "{n} P1 capability gaps that surfaced in this assessment.",
    "P2": "Unify the {n} member-facing capability gaps in P2 into a single "
          "channel + servicing modernization track.",
    "P3": "Address the {n} P3 capability gaps as one operations + automation "
          "programme — payments, lending ops, and core.",
    "P4": "Treat the {n} P4 gaps as the prerequisite layer — data + AI cannot "
          "land without modern foundation, integration, and governance.",
}


def _concrete_cluster_title(subs: list[dict[str, Any]], pillar: str) -> str:
    """Name the CONCRETE opportunity a cluster represents from its subcaps'
    own score rationales (nlp.titlecraft SVO) — never a scaffolding headline
    like 'Sharpen strategic posture'. Falls back to a concrete pillar-domain
    headline when no rationale yields a clean title."""
    from app.services.focus_area_sanity import is_fragment_title
    from app.services.nlp.titlecraft import make_title

    for s in subs:
        rationale = (s.get("rationale") or "").strip()
        if len(rationale) < 20:
            continue
        try:
            cand = make_title(rationale)
        except Exception:
            cand = ""
        if cand and len(cand) >= _MIN_TITLE_LEN and not is_fragment_title(cand):
            return cand[:128]
    return _PILLAR_FALLBACK_TITLE.get(pillar, f"Close the {pillar} capability gaps")


def _heuristic_focus_areas(ctx: _RunContext) -> list[SynthesizedFocusArea]:
    """Deterministic fallback when Vertex is unavailable. Cluster the
    lowest-scoring subcaps per pillar into a single focus area each, titled by
    the concrete opportunity its subcaps describe (not a scaffolding phrase)."""
    # Cluster by whatever pillars the scores actually carry — a future
    # P5 falls through to the generic title rather than vanishing
    # (2026-06-10 resilience audit, CRITICAL #5).
    by_pillar: dict[str, list[dict[str, Any]]] = {}
    for s in ctx.low_scoring_subcaps:
        p = (s["subcap_id"] or "")[:2]
        if p.startswith("P") and len(p) == 2:
            by_pillar.setdefault(p, []).append(s)
    out: list[SynthesizedFocusArea] = []
    for pillar in sorted(by_pillar):
        subs = by_pillar[pillar]
        if len(subs) < 2:
            continue
        title = _concrete_cluster_title(subs, pillar)
        body_tpl = _PILLAR_BODY.get(
            pillar, "Prioritise the {n} lowest-scoring " + pillar
            + " capabilities surfaced by this assessment.")
        out.append(SynthesizedFocusArea(
            title=title,
            description=body_tpl.format(n=len(subs)),
            involved_subcap_ids=[s["subcap_id"] for s in subs[:6]],
            data_source="heuristic",
            rationale=f"Lowest-scoring {min(6, len(subs))} subcaps under {pillar}.",
        ))
    return out


def _validate_and_dedupe(
    raw_areas: list[dict[str, Any]],
    valid_subcap_ids: set[str],
) -> list[SynthesizedFocusArea]:
    """Reject focus areas that:
      - reference unknown subcap_ids (hallucination check)
      - cluster <2 valid subcaps
      - overlap subcaps already claimed by an earlier area
    """
    claimed: set[str] = set()
    out: list[SynthesizedFocusArea] = []
    for raw in raw_areas:
        if not isinstance(raw, dict):
            continue
        title = (raw.get("title") or "").strip()
        desc = (raw.get("description") or "").strip()
        ids_raw = raw.get("involved_subcap_ids") or []
        if not isinstance(ids_raw, list) or not title or not desc:
            continue
        # Keep only subcap_ids that exist on this run AND haven't been
        # claimed by an earlier area.
        ids = [s for s in ids_raw if isinstance(s, str) and s in valid_subcap_ids and s not in claimed]
        if len(ids) < 2:
            continue
        claimed.update(ids)
        out.append(SynthesizedFocusArea(
            title=title[:128],
            description=desc[:512],
            involved_subcap_ids=ids[:8],
            data_source="gemini-flash",
            rationale=(raw.get("rationale") or "")[:240],
        ))
        if len(out) >= 5:
            break
    return out


def _match_recommendations(
    areas: list[SynthesizedFocusArea],
    recommendations: list[dict[str, Any]],
) -> None:
    """For each focus area, attach the recommendations whose
    target_subcap_ids overlap with the area's involved_subcap_ids."""
    for area in areas:
        targets = set(area.involved_subcap_ids)
        matches = []
        for rec in recommendations:
            rec_targets = set(rec.get("target_subcap_ids") or [])
            if targets & rec_targets:
                matches.append(rec["rec_id"])
        area.matched_recommendation_ids = matches[:8]


# ═══════════════════════════════════════════════════════════════════════
# Grounding · pillars_weight · financial_ref · KPI derivation (Part 6.1)
#
# The 2026-06 heatmap audit measured: synthesized focus rows persist
# page_number NULL + verbatim_quote = a GENERATED paragraph (no grounding),
# pillars_weight was a frontend count-share proxy, and the KPI strip was
# 100% manual (focus_area_kpi_overrides had no derivation and no delta).
# Everything below is deterministic + NLP-platform-backed (nlp.quotes /
# nlp.quantities), so it runs identically Vertex-hot or cold.
# ═══════════════════════════════════════════════════════════════════════

# ── Title + quote hygiene (2026-07 depth stress-test fixes) ───────────────
#
# The stress-test found 211/579 focus_areas.title were RAW finding IDs
# ("F-002"), and representative_quote was often the finding's whole
# pipe-delimited table row ("F-002 | 🎯🎯 15,531 issues … [E-286] | …")
# whose inline [E-###] citations were never parsed into evidence_e_ids.

_BARE_FINDING_ID_RE = re.compile(r"^F-\d+$")
# E-IDs as they appear inline: E-093 · E-018:F1 · E-INT-002.
_INLINE_EID_RE = re.compile(r"\bE-(?:[A-Z]+-)?\d+\b")
_EMOJI_RE = re.compile("[\U0001f000-\U0001faff☀-➿]+")
_MIN_TITLE_LEN = 8


def extract_inline_eids(text: str) -> list[str]:
    """Every inline E-ID citation, order-preserving, deduped. 'E-018:F1'
    contributes 'E-018' (the facet suffix isn't part of the evidence key)."""
    out: list[str] = []
    for m in _INLINE_EID_RE.finditer(text or ""):
        eid = m.group(0)
        if eid not in out:
            out.append(eid)
    return out


def _quote_cells(text: str) -> list[str]:
    """Split a finding table-row dump into its content cells: drop the
    bare finding-ID cell + emoji markers; keep the rest verbatim."""
    out: list[str] = []
    for cell in (text or "").split("|"):
        cell = _EMOJI_RE.sub("", cell).strip()
        if not cell or _BARE_FINDING_ID_RE.match(cell):
            continue
        out.append(cell)
    return out


# Bracketed E-citation MARKUP inside quotes ("[E-286]", "[E-018:F1]",
# and the malformed "[E-P4C4]" / "[E-{Juel}]" variants). Real E-IDs are
# extracted into evidence_e_ids BEFORE this strips the markers — a
# representative quote never carries raw citation brackets.
_EID_MARKUP_RE = re.compile(r"\s*\[E-[^\]]*\]")


def _finalize_quote(quote: str | None) -> str | None:
    if not quote:
        return None
    cleaned = _EID_MARKUP_RE.sub("", quote)
    # Upstream truncation can leave an UNCLOSED citation tail
    # ("…confirmed via [E-09") that the bracket-pair regex can't see.
    cleaned = re.sub(r"\s*\[E-[^\]]*$", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" :;—-")
    return cleaned[:400] or None


def clean_representative_quote(text: str) -> str | None:
    """A citable quote from a finding text that may be a raw table-row
    dump. Drop the ID cell + emojis, then mine the first verbatim
    salient sentence (nlp.quotes) from the remaining cells; fall back
    to the longest content cell. Citation markers are stripped (they
    live in evidence_e_ids). Never returns the raw dump."""
    from app.services.nlp.quotes import mine_quotes

    cells = _quote_cells(text)
    if not cells:
        return None
    for cell in cells:
        mined = mine_quotes(cell)
        if mined:
            return _finalize_quote(mined[0]["quote"])
    return _finalize_quote(max(cells, key=len))


async def clean_persisted_focus_areas(
    session: AsyncSession, *, entity_display_id: str,
) -> dict[str, int]:
    """Make the STORED focus areas correct — not just filtered at render.

    The read path drops scaffolding + cleans the display title, but the
    persisted ``title`` / ``verbatim_quote`` stay raw, so downstream consumers
    (the KPI enricher, the evidence drawer's quote) still see "2 Top Findings"
    and "F-003 | … | 3.5". This rewrites the persisted columns to the same clean
    forms the read path derives (``clean_focus_area`` display title +
    ``clean_representative_quote``), and DELETES rows that are pure document
    scaffolding (keep=False) — safe because the gap-fill has already populated a
    real focus set for any entity that had only scaffolding. Idempotent."""
    from app.services.focus_area_sanity import clean_focus_area

    ent = (await session.execute(text(
        "SELECT e.id::text eid, e.subvertical, r.id::text rid "
        "FROM entities e JOIN runs r ON r.entity_id = e.id AND r.status='ACTIVE' "
        "WHERE e.display_id = :d"), {"d": entity_display_id})).first()
    if ent is None:
        return {"cleaned": 0, "dropped": 0, "salvaged": 0}
    rows = (await session.execute(text(
        "SELECT id::text id, title, verbatim_quote, involved_subcap_ids "
        "FROM focus_areas WHERE run_id = CAST(:r AS uuid)"), {"r": ent.rid})).all()
    from app.services.nlp.titlecraft import make_title
    cleaned = dropped = salvaged = 0
    for r in rows:
        subs = list(r.involved_subcap_ids or [])
        keep, display_title = clean_focus_area(
            r.title or "", r.verbatim_quote or "", subs, subvertical=ent.subvertical)
        if not keep:
            # SALVAGE before dropping: a row titled with scaffolding ("2 Top
            # Findings") but carrying a REAL finding in its quote ("Acuity runs
            # IBM AIX on-premises …") is genuine content mis-labelled by the
            # section header — derive a headline from the quote and keep it. Only
            # a row whose QUOTE is also meta/instruction ("Each finding includes
            # …") is true scaffolding and is dropped.
            cq = clean_representative_quote(r.verbatim_quote or "") or ""
            quote_keep, _ = clean_focus_area(
                "Strategic priority", cq, subs, subvertical=ent.subvertical)
            salv = make_title(cq) if (quote_keep and len(cq) >= 30) else ""
            if salv and len(salv) >= _MIN_TITLE_LEN:
                await session.execute(text(
                    "UPDATE focus_areas SET title = :t, verbatim_quote = :q "
                    "WHERE id = CAST(:i AS uuid)"),
                    {"t": salv[:200], "q": cq, "i": r.id})
                salvaged += 1
                continue
            await session.execute(text(
                "DELETE FROM focus_areas WHERE id = CAST(:i AS uuid)"), {"i": r.id})
            dropped += 1
            continue
        # clean the persisted quote (raw finding-row dump → human sentence)
        new_quote = r.verbatim_quote
        if new_quote and (" | " in new_quote or _FINDING_ID_LEAD_RE.match(new_quote)
                          or new_quote.strip() == (r.title or "").strip()):
            new_quote = clean_representative_quote(new_quote) or new_quote
        if (display_title and display_title != r.title) or new_quote != r.verbatim_quote:
            await session.execute(text(
                "UPDATE focus_areas SET title = :t, verbatim_quote = :q "
                "WHERE id = CAST(:i AS uuid)"),
                {"t": (display_title or r.title)[:200], "q": new_quote, "i": r.id})
            cleaned += 1
    return {"cleaned": cleaned, "dropped": dropped, "salvaged": salvaged}


_FINDING_ID_LEAD_RE = re.compile(r"^\s*[FG]-?\d{1,4}\b", re.I)


def humanize_focus_title(title: str, body_text: str) -> str:
    """Replace bare finding-ID / degenerate / sentence-fragment titles with
    a human headline derived from the finding text (nlp.titlecraft SVO
    compression) — 'F-002' → 'No marketing automation despite active
    builds', and a raw prose fragment ("Applied is uniquely positioned to
    deliver practical, powerful…") → its SVO core. A strategic-priority
    title must be a concise headline, never a prose sentence (operator
    2026-07); the prose belongs in the quote/description. Healthy headline
    titles pass through unchanged; when no better headline is derivable a
    bare ID is at least labelled ('Client research finding F-002') and a
    fragment is left as-is rather than degraded."""
    from app.services.focus_area_sanity import (
        _FINDING_ID_PREFIX_RE,
        is_fragment_title,
        title_from_finding_row,
    )
    from app.services.nlp.titlecraft import make_title

    current = (title or "").strip()
    # A pipe-delimited finding-row TITLE ("F-003 | ROSIE-Salesforce NBA | ROSIE
    # = 22 ML models") must never ship as a raw dump: strip the leading F-0NN
    # token and take the first non-empty pipe segment (the "| Rosie" fix).
    if "|" in current and (_BARE_FINDING_ID_RE.match(current.split("|", 1)[0].strip())
                           or _FINDING_ID_PREFIX_RE.match(current)):
        head, _body = title_from_finding_row(current)
        if head and len(head) >= _MIN_TITLE_LEN and not is_fragment_title(head):
            return head[:128]
        if head:
            current = head  # fall through to make_title compression
    bare = bool(_BARE_FINDING_ID_RE.match(current))
    fragment = is_fragment_title(current)
    if not bare and not fragment and len(current) >= _MIN_TITLE_LEN:
        return current
    for cell in _quote_cells(body_text):
        candidate = make_title(cell)
        if not candidate or len(candidate) < _MIN_TITLE_LEN:
            continue
        # A bare finding-ID has no real title, so any derived headline
        # beats it. A sentence-fragment title already carries the full
        # statement, so replace it only with a genuine (non-fragment)
        # headline — never with a worse fragment.
        if bare or not is_fragment_title(candidate):
            return candidate[:128]
    return f"Client research finding {current}" if bare else current


def _grounding_is_unhygienic(grounding: Any) -> bool:
    """True when an existing grounding row needs repair: a raw table-row
    dump as the representative quote, any bracketed [E-…] citation
    markup left in it (post-fix quotes are prose; real E-IDs live in
    evidence_e_ids — incl. the malformed "[E-P4C4]" / "[E-{Juel}]"
    variants the stress-test surfaced), or an EMPTY grounding — a dict
    with neither quote nor E-IDs anchors nothing (the all-94 rendered
    sweep found 46 clients shipping heuristic rows in exactly that
    state), so it recomputes from the subcaps' rationales/evidence."""
    if not isinstance(grounding, dict):
        return True
    quote = grounding.get("representative_quote") or ""
    if not quote:
        return not (grounding.get("evidence_e_ids") or [])
    return " | " in quote or "[E-" in quote


# Catalogue tier → weight. pillars_weight is the share of the focus area's
# CATALOGUE weight sitting in each pillar — involved subcaps weighted by
# their ccg_subcaps.tier (T1 flagship > T2 > T3), replacing the FE's flat
# count-share proxy.
_TIER_WEIGHT = {"T1": 1.0, "T2": 0.75, "T3": 0.5}
_PILLAR_RE = re.compile(r"^(P\d+)C")


def compute_pillars_weight(
    subcap_ids: list[str], tier_by_subcap: dict[str, str],
) -> dict[str, int] | None:
    """Integer percentage share per pillar (sums to exactly 100)."""
    totals: dict[str, float] = {}
    for sid in subcap_ids:
        m = _PILLAR_RE.match(sid or "")
        if not m:
            continue
        weight = _TIER_WEIGHT.get(tier_by_subcap.get(sid, "T2"), 0.75)
        totals[m.group(1)] = totals.get(m.group(1), 0.0) + weight
    if not totals:
        return None
    grand = sum(totals.values())
    out = {p: int(round(v / grand * 100)) for p, v in sorted(totals.items())}
    drift = 100 - sum(out.values())
    if drift:
        top = max(out, key=lambda p: out[p])
        out[top] += drift
    return out


def build_grounding(
    *,
    subcap_ids: list[str],
    rationale_by_subcap: dict[str, str],
    evidence_by_subcap: dict[str, list[dict[str, Any]]],
    source_kind: str,
) -> dict[str, Any]:
    """Real anchors for a focus area: a VERBATIM representative quote
    mined (nlp.quotes — never paraphrased) from the clustered subcaps'
    score rationales / evidence excerpts, plus the E-IDs — inline
    [E-###] citations found IN the quoted texts first (they are the
    finding's own citations), then the tier-ordered linked evidence.
    ``source_kind`` ∈ docx | gemini | heuristic."""
    from app.services.nlp.quotes import mine_quotes

    linked_e_ids: list[str] = []
    candidate_texts: list[str] = []
    for sid in subcap_ids:
        rationale = (rationale_by_subcap.get(sid) or "").strip()
        if rationale:
            candidate_texts.append(rationale)
    for sid in subcap_ids:
        for ev in evidence_by_subcap.get(sid, []):
            eid = ev.get("e_id")
            if eid and eid not in linked_e_ids:
                linked_e_ids.append(eid)
            excerpt = (ev.get("excerpt") or "").strip()
            if excerpt:
                candidate_texts.append(excerpt)
    representative_quote: str | None = None
    for text_block in candidate_texts:
        # Table-row dumps ("F-002 | 🎯🎯 15,531 issues … [E-286] | …")
        # are cleaned per cell; plain prose passes through mine_quotes
        # unchanged.
        cleaned = (
            clean_representative_quote(text_block)
            if "|" in text_block else None
        )
        if cleaned:
            representative_quote = cleaned
            break
        mined = mine_quotes(text_block)
        if mined:
            representative_quote = mined[0]["quote"][:400]
            break
    # Inline citations carried by the quote itself + the candidate texts
    # are the most direct anchors — merge them ahead of the linked ids.
    # (Stress-test probe: a '[E-###]' inside the representative quote
    # with an empty evidence_e_ids array is a hygiene failure.)
    inline: list[str] = list(extract_inline_eids(representative_quote or ""))
    for text_block in candidate_texts[:8]:
        for eid in extract_inline_eids(text_block):
            if eid not in inline:
                inline.append(eid)
    evidence_e_ids = inline + [e for e in linked_e_ids if e not in inline]
    return {
        # Citation markers stripped AFTER extraction — the quote is
        # prose; the anchors live in evidence_e_ids.
        "representative_quote": _finalize_quote(representative_quote),
        "evidence_e_ids": evidence_e_ids[:6],
        "source_kind": source_kind,
    }


def _financial_lines(financial_highlights: Any) -> list[str]:
    """Flatten firmographics.financial_highlights JSONB to citable lines."""
    lines: list[str] = []
    if isinstance(financial_highlights, dict):
        for key, val in financial_highlights.items():
            if key == "series" or val is None:
                continue
            if isinstance(val, dict | list):
                continue
            lines.append(f"{key}: {val}")
    elif isinstance(financial_highlights, list):
        lines = [str(x) for x in financial_highlights if x]
    return lines


def find_financial_ref(fa_text: str, financial_lines: list[str]) -> str | None:
    """Quantities match (nlp.quantities) between the focus area's own text
    and the entity's financial highlights — the wireframe SOURCE block's
    "Financial reference" line. Returns the matching highlight (≤160
    chars) or None; never fabricates a reference."""
    from app.services.nlp.quantities import extract_metrics

    if not fa_text or not financial_lines:
        return None
    fa_metrics = extract_metrics(fa_text)
    if not fa_metrics:
        return None
    fa_values = {(m["unit"], round(float(m["value"]), 2)) for m in fa_metrics}
    fa_labels = {
        (m.get("metric") or "").lower()
        for m in fa_metrics
        if m.get("metric") and len(str(m["metric"])) >= 3
    }
    fa_label_tokens = {
        tok for label in fa_labels for tok in re.findall(r"[a-z]{4,}", label)
    }
    for line in financial_lines:
        for m in extract_metrics(line):
            if (m["unit"], round(float(m["value"]), 2)) in fa_values:
                return line.strip()[:160]
            label = (m.get("metric") or "").lower()
            if label and label in fa_labels:
                return line.strip()[:160]
        # Highlight lines are mostly "Key ($B): value (year)" — the value
        # carries no unit symbol so extract_metrics skips it. Match the
        # KEY's tokens against the FA's metric labels instead ("Total
        # Assets ($B)" ↔ "assets").
        key = line.split(":", 1)[0].lower()
        key_tokens = set(re.findall(r"[a-z]{4,}", key))
        if key_tokens & fa_label_tokens:
            return line.strip()[:160]
    return None


_ARROW_SPLIT_RE = re.compile(r"\s*(?:→|->)\s*|\s+to\s+")


_KPI_BAD_TAIL_RE = re.compile(
    r"(?:\b(?:beyond|to|at|of|by|above|below|over|under|from|toward|into|"
    r"scaled|grew|reached|hit|surpassed|climbed|rose|jumped|expanded)\s*)$",
    re.I)
_KPI_METRIC_NOUN_RE = re.compile(
    r"\b(?:ratio|rate|target|assets?|members?|customers?|employees?|"
    r"branch(?:es)?|loans?|deposits?|revenue|income|cost|synerg\w+|"
    r"dividends?|volume|hours?|cases?|scores?|growth|margin|efficiency|"
    r"headcount|aum|nps|attrition|retention|conversion|uptime|backlog|"
    r"transactions?|users?|accounts?|savings|processing|throughput|"
    r"turnaround|utili[sz]ation|adoption|coverage|penetration|"
    r"complaints?|claims?|premiums?|payouts?)\b", re.I)
_KPI_CANON: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\basset", re.I), "Total assets"),
    (re.compile(r"\baum\b", re.I), "Assets under management"),
    (re.compile(r"\bmember", re.I), "Members"),
    (re.compile(r"\bcustomer", re.I), "Customers"),
    (re.compile(r"\bemployee|\bstaff|\bheadcount", re.I), "Employees"),
    (re.compile(r"\bbranch", re.I), "Branches"),
    (re.compile(r"\bloan", re.I), "Loans"),
    (re.compile(r"\bdeposit", re.I), "Deposits"),
    (re.compile(r"\brevenue|\bincome", re.I), "Revenue"),
    (re.compile(r"\bdividend", re.I), "Dividends paid"),
    (re.compile(r"\bcases?\b", re.I), "Cases per year"),
]


def derive_focus_area_kpis(
    texts: list[str | tuple[str, str | None]], *, max_kpis: int = 3,
) -> list[dict[str, Any]]:
    """Derive KPI seed rows from a focus area's quotes + linked evidence
    excerpts + rec text via nlp.quantities. Priority: before→after
    transitions ("12 days → 4 days" ⇒ current+target+delta) then labelled
    single metrics (current only — the AE fills the target). Every row:
    ``{kpi_label, source_mode: "public", current_value, target_value,
    delta, evidence_e_id}``; no label ⇒ no row (never a fabricated name).

    Evidence traceability (2026-07-06): each item of ``texts`` may be a
    plain string or a ``(text, e_id)`` pair. A KPI mined from a block
    inherits the block's inline ``[E-###]`` citation when the text carries
    one, else the attached ``e_id`` — so the KPI strip can open the exact
    evidence row its number was read from. Honest None when neither the
    text nor the caller anchors the block."""
    from app.services.nlp.quantities import extract_metrics

    rows: list[dict[str, Any]] = []
    seen_labels: set[str] = set()

    def add(label: str | None, current: str | None, target: str | None,
            delta: str | None, e_id: str | None) -> None:
        clean = (label or "").strip(" -—·")
        # a KPI label never carries an internal register code
        # ("Indio ISS-003 SF-Epic" -> "Indio SF-Epic", 2026-07-13 corpus QA)
        clean = re.sub(r"\s*\b(?:ISS|URF|REQ|QA)-[\dA-Z-]+\b", "", clean).strip(" -—·")
        # A KPI label must NAME a metric. The quantity extractor hands back
        # the phrase preceding the number, which can be verb debris ('CCU
        # scaled beyond' -> $3.5B, the 2026-07-13 sample vetting). A label
        # ending on a verb/preposition is canonicalized from its own
        # vocabulary; if nothing canonical matches, the row is dropped --
        # never a fabricated KPI name.
        if _KPI_BAD_TAIL_RE.search(clean):
            # first try to RECOVER the metric phrase by stripping the
            # trailing verb/preposition debris ("… processing for lending
            # sits at" -> "… processing for lending"); only fall back to
            # canonicalization (or dropping) when nothing metric-shaped
            # survives (2026-07-13 corpus QA: legit disclosed KPIs were
            # dropped whole because their lead-in ended on 'sits at').
            stripped = _KPI_BAD_TAIL_RE.sub("", clean).strip(" -—·")
            if stripped and _KPI_METRIC_NOUN_RE.search(stripped):
                clean = stripped
            else:
                canon = next((name for rx, name in _KPI_CANON
                              if rx.search(clean)), None)
                if canon is None:
                    return
                clean = canon
        # ...and it must contain a metric NOUN (or canonicalize to one):
        # "Beacon Bank" / "M run-rate vs" / "framework b Beacon's" are
        # phrase debris around a number, not KPI names (2026-07-13
        # Beacon vetting). Dropping is honest; naming is not ours to invent.
        if not _KPI_METRIC_NOUN_RE.search(clean):
            canon = next((name for rx, name in _KPI_CANON
                          if rx.search(clean)), None)
            if canon is None:
                return
            clean = canon
        if len(clean) < 3:
            return
        key = clean.lower()
        if key in seen_labels:
            return
        seen_labels.add(key)
        rows.append({
            "kpi_label": clean[:80].strip().capitalize()
            if clean == clean.lower() else clean[:80].strip(),
            "source_mode": "public",
            "current_value": current,
            "target_value": target,
            "delta": delta,
            "evidence_e_id": e_id,
        })

    transitions: list[tuple[dict[str, Any], str | None]] = []
    singles: list[tuple[dict[str, Any], str | None]] = []
    for item in texts:
        text_block, attached = (item if isinstance(item, tuple) else (item, None))
        if not text_block:
            continue
        # The block's own inline citation is the most direct anchor;
        # the caller-attached E-ID is the fallback.
        inline = extract_inline_eids(text_block)
        block_eid = (inline[0] if inline else attached) or None
        for m in extract_metrics(text_block):
            if m.get("direction") in ("improvement", "degradation"):
                transitions.append((m, block_eid))
            elif m.get("metric"):
                singles.append((m, block_eid))

    for m, block_eid in transitions:
        raw = str(m.get("raw") or "")
        parts = [p.strip() for p in _ARROW_SPLIT_RE.split(raw) if p.strip()]
        current = parts[0] if len(parts) == 2 else None
        target = parts[1] if len(parts) == 2 else None
        delta = None
        if current and target:
            cur_num = re.match(r"[\d,.]+", current)
            tgt_num = re.match(r"[\d,.]+", target)
            if cur_num and tgt_num:
                try:
                    c = float(cur_num.group(0).replace(",", ""))
                    t = float(tgt_num.group(0).replace(",", ""))
                    if c > 0:
                        delta = f"{(t - c) / c * 100:+.0f}%"
                except ValueError:
                    delta = None
        add(m.get("metric"), current, target, delta, block_eid)
        if len(rows) >= max_kpis:
            return rows

    for m, block_eid in singles:
        unit = m.get("unit")
        value = m.get("value")
        if value is None:
            continue
        # Bare entity-count matches ("5 members" inside prose) make junk
        # KPIs — only surface count metrics at institutional scale.
        if unit == "count" and value < 20:
            continue
        # a bare 1900-2099 integer is a YEAR read as a value ("Member:
        # 2,024" shipped from "…in 2024", corpus stress-test 2026-07-12)
        # — units like $/% are real figures, bare counts in that band
        # are not worth the confusion
        if unit in (None, "count") and float(value).is_integer() \
                and 1900 <= value <= 2099:
            continue
        if unit == "pct":
            current = f"{value:g}%"
        elif unit == "usd":
            current = f"${value:,.0f}"
        elif unit == "stars":
            current = f"{value:g} stars"
        elif unit in ("days", "months"):
            current = f"{value:g} {unit}"
        elif unit == "ratio":
            current = f"{value:g}x"
        else:
            current = f"{value:,.0f}".replace(".0", "")
        add(m.get("metric"), current, None, None, block_eid)
        if len(rows) >= max_kpis:
            break
    return rows


# ═══════════════════════════════════════════════════════════════════════
# Focus-enrichment wave (migration 056): grounding-fill, KPI reasoning,
# linked insight cards. All PURE + deterministic so they run identically
# Vertex-hot or cold; the Gemini surfaces in ``enrichment_queries`` reuse
# these same validators, and the deterministic tiers below are the honest
# floor that always produces something without a model call.
# ═══════════════════════════════════════════════════════════════════════

# Significant-token unit for grounding validation + prose-similarity
# linking. ≥3 chars, English + FSI filler dropped — a shared-token count
# over these is the "genuinely about the same thing" signal.
_SIG_TOKEN_RE = re.compile(r"[a-z][a-z0-9]{2,}")
_SIG_STOPWORDS = frozenset({
    "the", "and", "for", "with", "that", "this", "from", "into", "our",
    "are", "was", "were", "has", "have", "had", "will", "would", "their",
    "its", "his", "her", "they", "them", "not", "but", "all", "any",
    "can", "may", "than", "then", "such", "who", "how", "why", "what",
    "which", "when", "where", "over", "under", "across", "within", "per",
    "via", "new", "use", "used", "using", "more", "most", "some", "each",
    "one", "two", "also", "very", "much", "many", "few", "out", "off",
    "now", "yet", "still", "however", "including", "based",
    # generic FSI/report filler that co-occurs everywhere and so carries
    # no topical signal
    "bank", "banks", "client", "clients", "member", "members", "customer",
    "customers", "digital", "capability", "capabilities", "focus", "area",
    "areas", "strategic", "priority", "priorities", "report", "score",
})


def significant_tokens(text: str) -> set[str]:
    """Lowercase content tokens (≥3 chars, stopwords/FSI-filler dropped).
    The unit of the grounding ≥3-shared-token validator and the linked-
    insight prose-similarity basis. Pure — no NLP model dependency, so it
    is identical in every environment."""
    return {
        t for t in _SIG_TOKEN_RE.findall((text or "").lower())
        if t not in _SIG_STOPWORDS
    }


def grounding_eid_supported(
    fa_text: str, excerpt: str, *, min_shared: int = 3,
) -> bool:
    """A candidate/returned E-ID grounds a focus area ONLY when its
    evidence excerpt shares ≥``min_shared`` significant tokens with the
    FA's quote/title. This is the anti-drift gate: an E-ID that exists in
    the bundle but is about an unrelated topic is rejected."""
    return len(
        significant_tokens(fa_text) & significant_tokens(excerpt)
    ) >= min_shared


def deterministic_grounding_eids(
    fa_text: str,
    evidence: list[tuple[str, str]],
    *,
    floor: int = 2,
    top: int = 3,
) -> list[str]:
    """Deterministic grounding fallback (source_kind='similarity'): rank
    the entity's evidence by significant-token overlap with the FA text,
    keep the top-``top`` whose overlap ≥ ``floor``. ``evidence`` is
    ``[(e_id, excerpt), ...]``. Honest by construction — no overlap ⇒ no
    id (an empty return is a legal, truthful answer). Ties break on the
    e_id so the output is stable across runs."""
    fa_toks = significant_tokens(fa_text)
    if not fa_toks:
        return []
    scored: list[tuple[int, str]] = []
    seen: set[str] = set()
    for e_id, excerpt in evidence:
        if not e_id or e_id in seen:
            continue
        n = len(fa_toks & significant_tokens(excerpt))
        if n >= floor:
            scored.append((n, e_id))
            seen.add(e_id)
    scored.sort(key=lambda p: (-p[0], p[1]))
    return [e_id for _n, e_id in scored[:top]]


# ── linked insight cards (layered, argue-through-facts) ──────────────────
_LINK_STRENGTH = {"subcap": 0, "co_citation": 1, "prose": 2, "gemini": 3}


def build_linked_insights(
    *,
    fa_subcap_ids: list[str],
    fa_evidence_e_ids: list[str],
    fa_text: str,
    insight_cards: list[dict[str, Any]],
    min_prose: int = 3,
) -> list[dict[str, Any]]:
    """Deterministic linked-insight union — the layered, fact-arguing
    alternative to the FE's single ``linked_subcap_id`` filter. A card
    links to a focus area on ANY of three bases, and every link CARRIES
    its basis so the UI can argue *why*:

      • ``subcap``      — the card's affects/linked_subcap_id overlaps the
        FA's involved subcaps (the structural link).
      • ``co_citation`` — the card's linked_e_ids overlap the FA's
        grounding evidence (they cite the same source).
      • ``prose``       — the card's title+what shares ≥``min_prose``
        significant tokens with the FA quote/title (semantic overlap).

    ``insight_cards`` items:
    ``{id, ic_id, title, severity, what_text, linked_subcap_id, affects,
    linked_e_ids}``. Returns link rows ordered strongest-basis-first,
    each ``{id, ic_id, title, severity, linked_subcap_id, bases, e_ids,
    source:'deterministic'}`` — persisted on ``focus_areas.linked_insights``
    and rendered as minicards with a link-basis chip."""
    fa_subs = set(fa_subcap_ids or [])
    fa_eids = set(fa_evidence_e_ids or [])
    fa_toks = significant_tokens(fa_text)
    out: list[dict[str, Any]] = []
    for card in insight_cards:
        card_subs = set(card.get("affects") or [])
        anchor = card.get("linked_subcap_id")
        if anchor:
            card_subs.add(anchor)
        card_eids = {e for e in (card.get("linked_e_ids") or []) if e}
        bases: list[dict[str, Any]] = []
        shared_subs = sorted(fa_subs & card_subs)
        if shared_subs:
            bases.append({"kind": "subcap", "detail": shared_subs})
        shared_eids = sorted(fa_eids & card_eids)
        if shared_eids:
            bases.append({"kind": "co_citation", "detail": shared_eids})
        prose = len(fa_toks & significant_tokens(
            f"{card.get('title') or ''} {card.get('what_text') or ''}"))
        if prose >= min_prose:
            bases.append({"kind": "prose", "detail": prose})
        if not bases:
            continue
        out.append({
            "id": str(card.get("id") or ""),
            "ic_id": card.get("ic_id"),
            "title": card.get("title"),
            "severity": card.get("severity"),
            "linked_subcap_id": anchor,
            "bases": bases,
            "e_ids": shared_eids or sorted(card_eids)[:4],
            "source": "deterministic",
        })
    out.sort(key=lambda li: (
        min(_LINK_STRENGTH.get(b["kind"], 9) for b in li["bases"]),
        li["id"],
    ))
    return out


# ── KPI reasoning validators (public-disclosure + roadmap-uplift bound) ──
_KPI_NUM_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
_KPI_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def _kpi_numbers(text: str) -> list[float]:
    out: list[float] = []
    for m in _KPI_NUM_RE.finditer(text or ""):
        try:
            out.append(float(m.group(0).replace(",", "")))
        except ValueError:
            continue
    return out


def kpi_current_disclosed(
    current: str, cited_excerpts: list[str], *, tol: float = 0.02,
) -> bool:
    """The KPI's CURRENT value must appear numerically (within ``tol``
    relative tolerance) in at least one CITED excerpt — this rejects a
    fabricated 'current' that no disclosed source states. A current with
    no parseable number cannot be a disclosed KPI value."""
    cur_nums = _kpi_numbers(current)
    if not cur_nums:
        return False
    c = cur_nums[0]
    hay = [n for ex in cited_excerpts for n in _kpi_numbers(ex)]
    return any(abs(c - h) <= tol * max(abs(c), 1e-9) for h in hay)


def kpi_target_consistent(
    current: str, target: str, rec_texts: list[str], *, tol: float = 0.15,
) -> bool:
    """The KPI's TARGET must be arithmetically consistent with a cited
    roadmap/rec uplift — either (a) the target value is stated in a rec's
    uplift text, or (b) the implied current→target delta matches an uplift
    percentage the rec states (within ``tol``). A target the roadmap does
    not support is a WRONG KPI and is rejected."""
    tgt_nums = _kpi_numbers(target)
    if not tgt_nums:
        return False
    t = tgt_nums[0]
    rec_nums = [n for rt in rec_texts for n in _kpi_numbers(rt)]
    # (a) target value stated verbatim in a rec uplift
    if any(abs(t - n) <= tol * max(abs(t), 1e-9) for n in rec_nums):
        return True
    # (b) current→target delta matches a stated uplift percentage
    cur_nums = _kpi_numbers(current)
    if cur_nums and cur_nums[0]:
        c = cur_nums[0]
        if c != 0:
            delta_pct = abs((t - c) / c) * 100.0
            rec_pcts = [float(m.group(1)) for rt in rec_texts
                        for m in _KPI_PCT_RE.finditer(rt)]
            if any(abs(delta_pct - p) <= tol * 100.0 for p in rec_pcts):
                return True
    return False


def kpi_delta_label(current: str, target: str) -> str | None:
    """Signed percentage delta from current→target when both parse to a
    number; else None (never a fabricated delta)."""
    cur = _kpi_numbers(current)
    tgt = _kpi_numbers(target)
    if not (cur and tgt) or cur[0] == 0:
        return None
    return f"{(tgt[0] - cur[0]) / cur[0] * 100:+.0f}%"


def refine_focus_subcaps(
    fa_text: str,
    existing_ids: list[str],
    catalogue_names: dict[str, str],
    evidence_rows: list[tuple[str, list[str]]],
    *, max_ids: int = 6,
) -> dict[str, list[str]]:
    """Accuracy pass for a focus area's subcap mapping (2026-07-12
    directive: 'map the focus area to a related subcap with utmost
    accuracy'). Deterministic, run-data-grounded:

    VERIFY — an existing id survives when its id appears verbatim in
    the FA text, or its catalogue name shares a significant token with
    it; anything else is a mis-mapping and is dropped (reported in
    ``flagged``).
    FILL — candidates come from (a) catalogue names sharing ≥2
    significant tokens with the FA text, and (b) the entity's OWN
    evidence: excerpts sharing ≥2 tokens with the FA vote for their
    linked subcaps, and a category needs ≥2 supporting excerpts
    (category consensus, the QA-ML-03 discipline) before its leaves
    are added. Never a fabricated id — every candidate exists in the
    catalogue or the run's links."""
    fa_toks = significant_tokens(fa_text)
    verified: list[str] = []
    flagged: list[str] = []
    for sid in existing_ids or []:
        name_toks = significant_tokens(catalogue_names.get(sid, ""))
        if sid in fa_text or (name_toks & fa_toks):
            verified.append(sid)
        else:
            flagged.append(sid)
    added: list[str] = []
    # (a) catalogue-name lexical match
    for sid, name in catalogue_names.items():
        if sid in verified or sid in added:
            continue
        if len(significant_tokens(name) & fa_toks) >= 2:
            added.append(sid)
    # (b) evidence category-consensus vote
    cat_votes: dict[str, list[str]] = {}
    for excerpt, linked in evidence_rows or []:
        if len(significant_tokens(excerpt or "") & fa_toks) < 2:
            continue
        for sid in linked or []:
            cat = sid[:4] if len(sid) >= 4 else sid
            cat_votes.setdefault(cat, []).append(sid)
    for _cat, sids in sorted(cat_votes.items(),
                             key=lambda t: -len(t[1])):
        if len(sids) < 2:
            continue
        best = max(set(sids), key=sids.count)
        if best not in verified and best not in added:
            added.append(best)
    final = (verified + added)[:max_ids]
    return {"final": final, "verified": verified,
            "flagged": flagged, "added": added[:max_ids]}


def mine_disclosed_kpis(
    fa_text: str, texts_with_eids: list[tuple[str, str]], *, max_kpis: int = 4,
) -> list[dict[str, Any]]:
    """Deterministic public-KPI candidate mining, TOPICALLY BOUND to the
    focus area: ``derive_focus_area_kpis`` over each ``(e_id, excerpt)``,
    keeping only rows whose source excerpt shares ≥2 significant tokens
    with the FA text (so a stray number from an off-topic excerpt never
    seeds a KPI). Each candidate carries the ``e_id`` it was mined from —
    the disclosed value + its evidence id the reasoning tier grounds on."""
    fa_toks = significant_tokens(fa_text)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for e_id, excerpt in texts_with_eids:
        if not excerpt:
            continue
        if len(fa_toks & significant_tokens(excerpt)) < 2:
            continue  # not topically bound to this focus area
        mined = derive_focus_area_kpis([excerpt])
        if not mined:
            # the excerpt is topically bound and carries a disclosed value,
            # but the quantity extractor's own label was debris (e.g. "for
            # lending sits" from "Straight-through processing for lending
            # sits at 18%"). Recover an HONEST label from the FA's metric-
            # noun phrase — the value stays the excerpt's, the label stays
            # grounded in the focus area's own words (2026-07-13 corpus QA:
            # legit STP/turnaround KPIs were silently dropped).
            fb = _fa_grounded_kpi(fa_text, excerpt)
            if fb:
                mined = [fb]
        for kpi in mined:
            key = kpi["kpi_label"].lower()
            if key in seen:
                continue
            seen.add(key)
            out.append({**kpi, "e_id": e_id, "excerpt": excerpt[:300]})
            if len(out) >= max_kpis:
                return out
    return out


def _fa_grounded_kpi(fa_text: str, excerpt: str) -> dict[str, Any] | None:
    """A KPI whose label is the focus area's own metric-noun phrase and whose
    current value is a disclosed number from the topically-bound excerpt.
    Both halves are grounded — nothing invented; returns None when the FA
    names no metric noun or the excerpt carries no usable number."""
    from app.services.nlp.quantities import extract_metrics
    mets = [m for m in extract_metrics(excerpt)
            if m.get("unit") in ("pct", "usd", "count", "ratio", "days", "hours")
            and m.get("raw")]
    if not mets:
        return None
    m = _KPI_METRIC_NOUN_RE.search(fa_text)
    if not m:
        return None
    # the noun-anchored phrase: from the FA start (minus a lead verb like
    # "Improve"/"Increase") through the metric noun
    head = fa_text[: m.end()].strip()
    head = re.sub(r"^(?:improve|increase|reduce|raise|grow|drive|lift|boost|"
                  r"strengthen|expand|accelerate|close|optimi[sz]e|enhance)\s+",
                  "", head, flags=re.I).strip(" -—·")
    label = head[:80].strip()
    if len(label) < 3:
        return None
    return {
        "kpi_label": label[0].upper() + label[1:],
        "source_mode": "public",
        "current_value": mets[0]["raw"],
        "target_value": None,
        "delta": None,
    }


def gemini_provenance(
    surface: str, model_id: str, evidence_e_ids: list[str] | None = None,
) -> dict[str, Any]:
    """The traceability envelope stamped onto every Gemini-derived focus
    field — {source:'vertex', surface, model_id, synthesized_at,
    evidence_e_ids}. Flows vertex_synthesis_cache → focus_areas rows →
    pack export → the FocusAreaView provenance badge."""
    from datetime import UTC, datetime
    return {
        "source": "vertex",
        "surface": surface,
        "model_id": model_id,
        "synthesized_at": datetime.now(UTC).isoformat(),
        "evidence_e_ids": list(evidence_e_ids or []),
    }


def kpi_fa_key(fa_id: str) -> str:
    """Canonical `focus_area_kpi_overrides.fa_id` key. The column is
    VARCHAR(32) but `focus_areas.id` serialises to a 36-char hyphenated
    UUID — writes with the raw UUID string exceed the column and 500.
    UUID-likes are stored as their 32-char hex; anything else is
    truncated to 32. Both the write-surfaces endpoints and the KPI
    seeding below MUST key through this function."""
    compact = fa_id.replace("-", "")
    if len(compact) == 32 and all(c in "0123456789abcdefABCDEF" for c in compact):
        return compact.lower()
    return fa_id[:32]


@dataclass
class _GroundingInputs:
    rationale_by_subcap: dict[str, str]
    evidence_by_subcap: dict[str, list[dict[str, Any]]]
    tier_by_subcap: dict[str, str]
    financial_lines: list[str]


async def _load_grounding_inputs(
    session: AsyncSession, *, run_id: str, entity_id: str,
    subcap_ids: set[str], catalog_version: str | None,
) -> _GroundingInputs:
    """Bulk-load everything the grounding/KPI derivation needs for the
    given involved-subcap set (one query per source, no N+1)."""
    ids = sorted(subcap_ids)
    rationale_by_subcap: dict[str, str] = {}
    evidence_by_subcap: dict[str, list[dict[str, Any]]] = {}
    tier_by_subcap: dict[str, str] = {}
    if ids:
        rat_rows = (await session.execute(
            text("""
                SELECT subcap_id, rationale
                  FROM subcap_scores
                 WHERE run_id = :rid AND subcap_id = ANY(:ids)
            """),
            {"rid": run_id, "ids": ids},
        )).all()
        rationale_by_subcap = {
            r.subcap_id: r.rationale for r in rat_rows if r.rationale
        }
        ev_rows = (await session.execute(
            text("""
                SELECT e_id, excerpt, tier,
                       UNNEST(linked_subcap_ids) AS sid
                  FROM evidence_index
                 WHERE run_id = :rid AND linked_subcap_ids && CAST(:ids AS varchar[])
                 ORDER BY tier ASC, e_id ASC
            """),
            {"rid": run_id, "ids": ids},
        )).all()
        for r in ev_rows:
            if r.sid in subcap_ids:
                evidence_by_subcap.setdefault(r.sid, []).append(
                    # Honest-NULL tier (unscored evidence) sorts last (T8, least
                    # authoritative) instead of crashing int(None) — parity with
                    # deepen_narrative._best_tier's NULL tolerance.
                    {"e_id": r.e_id, "excerpt": r.excerpt,
                     "tier": int(r.tier) if r.tier is not None else 8}
                )
        if catalog_version:
            tier_rows = (await session.execute(
                text("""
                    SELECT subcap_id, tier FROM ccg_subcaps
                     WHERE version = :ver AND subcap_id = ANY(:ids)
                """),
                {"ver": catalog_version, "ids": ids},
            )).all()
            tier_by_subcap = {r.subcap_id: r.tier for r in tier_rows if r.tier}
    fin_row = (await session.execute(
        text("SELECT financial_highlights FROM firmographics WHERE entity_id = :eid"),
        {"eid": entity_id},
    )).first()
    financial_lines = _financial_lines(fin_row.financial_highlights if fin_row else None)
    return _GroundingInputs(
        rationale_by_subcap=rationale_by_subcap,
        evidence_by_subcap=evidence_by_subcap,
        tier_by_subcap=tier_by_subcap,
        financial_lines=financial_lines,
    )


def _enrich_area(
    area: SynthesizedFocusArea,
    inputs: _GroundingInputs,
    *,
    source_kind: str,
    rec_texts: list[str] | None = None,
) -> None:
    """Fill grounding / pillars_weight / financial_ref / kpis in place."""
    area.grounding = build_grounding(
        subcap_ids=area.involved_subcap_ids,
        rationale_by_subcap=inputs.rationale_by_subcap,
        evidence_by_subcap=inputs.evidence_by_subcap,
        source_kind=source_kind,
    )
    area.pillars_weight = compute_pillars_weight(
        area.involved_subcap_ids, inputs.tier_by_subcap,
    )
    fa_text = " ".join(
        t for t in (
            area.title, area.description,
            (area.grounding or {}).get("representative_quote") or "",
        ) if t
    )
    area.financial_ref = find_financial_ref(fa_text, inputs.financial_lines)
    # KPI mining reads the linked EVIDENCE CONTENT itself (not just the
    # generated description) and attributes every block to its E-ID so
    # each derived KPI is drawer-traceable (2026-07-06). Attribution:
    # the quote/rationale inherit the grounding's lead E-ID (their inline
    # [E-###] citations win inside derive_focus_area_kpis); each evidence
    # excerpt carries its own E-ID.
    grounding_eids = list((area.grounding or {}).get("evidence_e_ids") or [])
    lead_eid = grounding_eids[0] if grounding_eids else None
    kpi_texts: list[str | tuple[str, str | None]] = [
        (area.description or "", None),
        ((area.grounding or {}).get("representative_quote") or "", lead_eid),
        *[(inputs.rationale_by_subcap.get(sid) or "", None)
          for sid in area.involved_subcap_ids],
    ]
    for sid in area.involved_subcap_ids:
        for ev in inputs.evidence_by_subcap.get(sid, [])[:2]:
            excerpt = (ev.get("excerpt") or "").strip()
            if excerpt:
                kpi_texts.append((excerpt, ev.get("e_id")))
    kpi_texts.extend((t, None) for t in (rec_texts or []))
    area.kpis = derive_focus_area_kpis(kpi_texts)


async def _seed_kpi_overrides(
    session: AsyncSession, *, entity_id: str, fa_id: str,
    kpis: list[dict[str, Any]],
) -> int:
    """Seed derived KPI rows into focus_area_kpi_overrides — ONLY when the
    (entity, fa) pair has none (the AE's manual edits are never clobbered;
    the per-FA PUT endpoint stays the write path)."""
    if not kpis:
        return 0
    fa_key = kpi_fa_key(fa_id)
    existing = (await session.execute(
        text("""
            SELECT 1 FROM focus_area_kpi_overrides
             WHERE entity_id = :eid AND fa_id = :fa LIMIT 1
        """),
        {"eid": entity_id, "fa": fa_key},
    )).first()
    if existing is not None:
        return 0
    inserted = 0
    for kpi in kpis:
        await session.execute(
            text("""
                INSERT INTO focus_area_kpi_overrides
                    (entity_id, fa_id, kpi_label, source_mode,
                     current_value, target_value, delta, evidence_e_id,
                     updated_at)
                VALUES (CAST(:eid AS uuid), :fa, :label, 'public',
                        :cur, :tgt, :delta, :ev_eid, NOW())
                ON CONFLICT (entity_id, fa_id, kpi_label) DO NOTHING
            """),
            {
                "eid": entity_id, "fa": fa_key,
                "label": kpi["kpi_label"][:255],
                "cur": kpi.get("current_value"),
                "tgt": kpi.get("target_value"),
                "delta": (kpi.get("delta") or None),
                # migration 060 — the E-ID the number was read from.
                "ev_eid": (kpi.get("evidence_e_id") or None),
            },
        )
        inserted += 1
    return inserted


# Gemini-rung observability (2026-07-05): the 01735cd build fell to the
# heuristic on ALL runs and the only trace was a swallowed log.warning —
# the HARD gate then misdiagnosed it as an IAM problem. Callers
# (derive_focus_areas) print these counters + the last error in their
# "# " summary so the build log names the ACTUAL failure.
GEMINI_STATS: dict[str, int] = {"schema_ok": 0, "plain_ok": 0, "failed": 0}
LAST_GEMINI_ERROR: str | None = None


def _note_gemini_failure(reason: str) -> None:
    global LAST_GEMINI_ERROR
    GEMINI_STATS["failed"] += 1
    LAST_GEMINI_ERROR = reason[:300]


async def _gemini_synthesize(ctx: _RunContext) -> list[SynthesizedFocusArea] | None:
    """Call Gemini Flash via the lazy VertexClient. Returns None on any
    failure (no creds, timeout, malformed response, validator reject)
    so the caller can fall back to the heuristic.

    CACHE-FIRST (2026-07-04): a re-run with the same prompt (same scores/
    rationales/catalogue) reads the persisted rows from
    vertex_synthesis_cache and costs 0 tokens — the module previously
    documented this behaviour without implementing it, so every
    derive_focus_areas re-run re-paid Gemini for all no-DOCX clients."""
    import hashlib

    from app.services import synthesis_cache_db as _cache_db

    _prompt = _build_prompt(ctx)
    _fp = hashlib.sha256(f"focus_v1|{_prompt}".encode()).hexdigest()
    cached = _cache_db.safe_fetch_active(
        "run", str(ctx.run_id), "focus_area_synthesis", _fp)
    if cached is not None and isinstance(cached.output_json, dict):
        cached_raw = cached.output_json.get("focus_areas")
        if isinstance(cached_raw, list):
            out = _validate_and_dedupe(cached_raw, ctx.all_subcap_ids)
            if out:
                return out
    try:
        from app.services.vertex_client import GeminiCall, get_vertex_client
    except ImportError:
        _note_gemini_failure("vertex_client not importable")
        return None
    try:
        client = get_vertex_client()
    except Exception as e:
        _note_gemini_failure(f"client init: {type(e).__name__}: {e}")
        return None

    _schema = {
        "type": "object",
        "properties": {
            "focus_areas": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "involved_subcap_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "rationale": {"type": "string"},
                    },
                    "required": ["title", "description", "involved_subcap_ids"],
                },
            },
        },
        "required": ["focus_areas"],
    }

    async def _attempt(schema: dict | None) -> tuple[str, dict]:
        """One Gemini attempt; returns (raw_text, parsed_dict) or raises."""
        buf: list[str] = []
        # max_output_tokens 1500→4096 (2026-07-05): gemini-2.5 models
        # spend "thinking" tokens from the SAME output budget — 1500 was
        # tight enough to truncate the JSON mid-array on real runs.
        async for chunk in client.stream(GeminiCall(
            surface="focus_area_synthesis", model="flash", prompt=_prompt,
            response_schema=schema, max_output_tokens=4096, temperature=0.3,
        )):
            buf.append(chunk)
        raw = "".join(buf).strip()
        # Strip Markdown code fences if Gemini wrapped the JSON.
        fenced = re.match(r"^```(?:json)?\s*([\s\S]+?)\s*```$", raw)
        if fenced:
            raw = fenced.group(1)
        return raw, json.loads(raw)

    # Two-rung Gemini ladder BEFORE the heuristic (2026-07-05, 01735cd
    # build post-mortem: the schema-constrained streaming call failed on
    # EVERY run while the same build's schema-less calls — why_now,
    # platform_story — succeeded, so ALL 65 rows fell to the heuristic
    # and the HARD focus_clustering gate failed the build; the reason
    # was invisible because it only ever reached log.warning). Rung 1:
    # schema-constrained (best quality). Rung 2: plain call, same
    # strict-JSON prompt, fence-strip + the SAME validator. The
    # heuristic remains the final rung; every failure is now counted
    # and surfaced by derive_focus_areas' summary line.
    payload: dict | None = None
    raw = ""
    try:
        raw, payload = await _attempt(_schema)
        GEMINI_STATS["schema_ok"] += 1
    except Exception as e:
        _note_gemini_failure(f"schema rung: {type(e).__name__}: {e}")
        log.warning("focus_area_synth.gemini_schema_rung_failed",
                    err=str(e)[:200], run_id=ctx.run_id)
        try:
            raw, payload = await _attempt(None)
            GEMINI_STATS["plain_ok"] += 1
        except Exception as e2:
            _note_gemini_failure(f"plain rung: {type(e2).__name__}: {e2}")
            log.warning("focus_area_synth.gemini_failed",
                        err=str(e2)[:200], run_id=ctx.run_id)
            return None
    areas_raw = payload.get("focus_areas") if isinstance(payload, dict) else None
    if not isinstance(areas_raw, list):
        _note_gemini_failure("payload missing focus_areas list")
        return None
    validated = _validate_and_dedupe(areas_raw, ctx.all_subcap_ids)
    if validated:
        # Persist so the next re-run (same prompt fingerprint) costs 0 tokens.
        _cache_db.safe_insert_or_supersede(
            target_kind="run", target_id=str(ctx.run_id),
            surface="focus_area_synthesis", model="flash",
            input_fingerprint=_fp,
            prompt_template_version="focus_v1",
            grounding_bundle_hash=_fp[:32],
            catalogue_version="v7.0",
            output_text=raw[:20000],
            output_json={"focus_areas": areas_raw},
            validators_passed=True,
        )
    return validated


async def _persist_synthesized(
    session: AsyncSession, *, ctx: _RunContext, areas: list[SynthesizedFocusArea],
) -> int:
    """Persist into focus_areas. DELETE any prior synthesized rows for
    this run before INSERT — re-running synthesis replaces the prior
    output (the original DOCX-parsed rows are kept because they have
    a different source_path)."""
    if not areas:
        return 0
    await session.execute(
        text("""
            DELETE FROM focus_areas
             WHERE run_id = :rid
               AND source_path LIKE 'synthesized:%'
        """),
        {"rid": ctx.run_id},
    )
    inserted = 0
    for area in areas:
        # verbatim_quote MUST be an actual SOURCED span (a representative_quote
        # mined verbatim by build_grounding from the clustered subcaps' score
        # rationales / evidence excerpts) — never the synthesized "bet"
        # paragraph presented AS a client quote. The bet narrative lives in
        # the title + the grounding; when no sourced span exists the honest
        # fallback is the description (NOT NULL), but grounding then carries no
        # representative_quote so the FE surfaces no fabricated quote.
        sourced_quote = (area.grounding or {}).get("representative_quote")
        vq = (sourced_quote or area.description or area.title)[:512]
        row = (await session.execute(
            text("""
                INSERT INTO focus_areas (
                    run_id, entity_id, title, verbatim_quote,
                    source_path, page_number, involved_subcap_ids,
                    grounding, financial_ref, pillars_weight
                ) VALUES (
                    :rid, :eid, :title, :vq, :sp, NULL, :isids,
                    CAST(:grounding AS jsonb), :fin_ref,
                    CAST(:pweight AS jsonb)
                )
                RETURNING id
            """),
            {
                "rid": ctx.run_id,
                "eid": ctx.entity_id,
                "title": area.title[:128],
                "vq": vq,
                # `source_path` marks the data-source — the FE can chip
                # "Synthesized via Gemini" or "Heuristic" off this.
                "sp": f"synthesized:{area.data_source}",
                "isids": area.involved_subcap_ids,
                "grounding": (
                    json.dumps(area.grounding) if area.grounding else None
                ),
                "fin_ref": area.financial_ref,
                "pweight": (
                    json.dumps(area.pillars_weight)
                    if area.pillars_weight else None
                ),
            },
        )).first()
        if row is not None and area.kpis:
            await _seed_kpi_overrides(
                session, entity_id=ctx.entity_id,
                fa_id=str(row.id), kpis=area.kpis,
            )
        inserted += 1
    return inserted


async def _load_existing_docx_focus_areas(
    session: AsyncSession, *, run_id: str, subvertical: str | None = None,
) -> list[SynthesizedFocusArea]:
    """Return focus_areas rows already extracted from the DOCX layer
    (Client Profile parser) for this run. Any row whose source_path
    does NOT start with `synthesized:` counts as DOCX-sourced — the
    Client Profile parser tags strategic-section rows
    `docx:strategic_section` and Top-Findings rows with their actual
    DOCX paths (e.g. `04_reports/Foo_Client_Profile.docx`).

    Per the 2026-06 operator mandate ("Recall strategic objectives are
    in some client research reports. Only use Gemini models if they
    are not available there."), these are returned to the caller
    AHEAD of any Gemini synthesis so the model never overwrites the
    bank's own stated priorities.
    """
    rows = (await session.execute(
        text(
            """
            SELECT title, verbatim_quote, involved_subcap_ids, source_path
              FROM focus_areas
             WHERE run_id = :rid
               AND (source_path IS NULL
                    OR source_path NOT LIKE 'synthesized:%')
             ORDER BY id
            """
        ),
        {"rid": run_id},
    )).all()
    from app.services.focus_area_sanity import clean_focus_area

    out: list[SynthesizedFocusArea] = []
    for row in rows:
        # Sanity-filter (2026-06-10): the parser also captures DOCX
        # scaffolding ("2 Top Findings…", bare "F-004" ids). Without
        # this, ONE scaffolding row makes the ladder report
        # docx_present and skip synthesis — the focus view then shows
        # junk instead of real priorities. Passing the subvertical also
        # drops a subvertical-NA capability ("AI Claims Estimation" on a
        # Farm-Credit entity) rather than shipping it as a priority.
        keep, display_title = clean_focus_area(
            row.title or "", row.verbatim_quote or "",
            list(row.involved_subcap_ids or []), subvertical=subvertical)
        if not keep:
            continue
        out.append(SynthesizedFocusArea(
            title=display_title[:128],
            description=(row.verbatim_quote or "")[:512],
            involved_subcap_ids=list(row.involved_subcap_ids or []),
            data_source=(
                "docx-strategic"
                if (row.source_path or "").startswith("docx:strategic")
                else "docx"
            ),
            rationale=f"Extracted verbatim from {row.source_path or 'client profile'}.",
        ))
    return out


async def synthesize_focus_areas(
    session: AsyncSession,
    *,
    entity_display_id: str,
    persist: bool = True,
    allow_heuristic: bool = False,
) -> dict[str, Any]:
    """Top-level entry. Returns the synthesized + matched focus areas
    plus diagnostic metadata. Persists to focus_areas table by default.

    Lookup order (operator mandate, 2026-07-08 — focus areas / strategic
    objectives are NEVER deterministic):
      1. VERBATIM report focus_areas already persisted for this run —
         the strategic objectives the client itself put in the research
         report. Returned as-is; recs matched; NO Gemini call.
      2. Gemini synthesis — thorough extraction of the client's strategic
         priorities when the report states none verbatim.
      3. When Vertex is unavailable, ship NOTHING (honest deferral) rather
         than the deterministic heuristic clustering — that was wrong for
         most clients and is DISABLED by mandate (``allow_heuristic`` stays
         False; the prod Vertex-enabled refresh fills + persists later).
    """
    ctx = await _load_run_context(session, entity_display_id=entity_display_id)
    if ctx is None:
        return {
            "ok": False,
            "reason": "no_run",
            "message": f"No active or pending run for {entity_display_id} — synthesize after ingest.",
            "focus_areas": [],
        }

    # Step 1: prefer DOCX-sourced focus areas when available. Match
    # recommendations against them so the FE still gets the "this
    # focus area unlocks recs X, Y, Z" callout.
    docx_areas = await _load_existing_docx_focus_areas(
        session, run_id=ctx.run_id, subvertical=ctx.subvertical,
    )
    if docx_areas:
        _match_recommendations(docx_areas, ctx.recommendations)
        return {
            "ok": True,
            "reason": "docx_present",
            "message": (
                f"Using {len(docx_areas)} focus area(s) extracted from "
                f"the client research report; Gemini synthesis skipped."
            ),
            "data_source": "docx",
            "focus_areas": [a.to_dict() for a in docx_areas],
            "persisted_count": 0,  # already persisted at ingest
        }

    if len(ctx.low_scoring_subcaps) < 2:
        return {
            "ok": False,
            "reason": "insufficient_data",
            "message": "Run has fewer than 2 scored subcaps; can't cluster a focus area.",
            "focus_areas": [],
        }
    areas = await _gemini_synthesize(ctx)
    used_fallback = False
    if not areas:
        if not allow_heuristic:
            # Mandate: no deterministic clustering. Defer to a Vertex-enabled
            # refresh; do NOT persist / ship wrong focus areas.
            return {
                "ok": False,
                "reason": "needs_gemini_refresh",
                "message": (
                    "No verbatim report focus areas and Vertex is unavailable to "
                    "extract strategic objectives — deferred to the next "
                    "Vertex-enabled refresh (deterministic clustering disabled by "
                    "mandate; nothing shipped rather than wrong data)."
                ),
                "data_source": "pending_gemini",
                "focus_areas": [],
                "persisted_count": 0,
            }
        areas = _heuristic_focus_areas(ctx)
        used_fallback = True
    # Defense-in-depth: drop any synthesized area that still maps to an
    # out-of-scope (subvertical-NA) capability — Gemini can cluster on a
    # capability NAME even after NA subcaps are excluded from its input.
    from app.services.focus_area_sanity import focus_area_out_of_scope
    areas = [
        a for a in areas
        if not focus_area_out_of_scope(
            a.title, a.description, a.involved_subcap_ids,
            subvertical=ctx.subvertical)
    ]
    if not areas:
        return {
            "ok": False,
            "reason": "no_clusters",
            "message": "Couldn't form 2+ clusters from the run's low-scoring subcaps.",
            "focus_areas": [],
        }
    _match_recommendations(areas, ctx.recommendations)
    # Grounding + pillars_weight + financial_ref + derived KPIs on every
    # synthesized area (Part 6.1) — one bulk load for all areas' subcaps.
    involved: set[str] = set()
    for area in areas:
        involved.update(area.involved_subcap_ids)
    inputs = await _load_grounding_inputs(
        session, run_id=ctx.run_id, entity_id=ctx.entity_id,
        subcap_ids=involved, catalog_version=ctx.catalog_version,
    )
    rec_text_by_id = {
        r["rec_id"]: f"{r.get('title') or ''}. {r.get('description') or ''}"
        for r in ctx.recommendations
    }
    for area in areas:
        _enrich_area(
            area, inputs,
            source_kind="heuristic" if used_fallback else "gemini",
            rec_texts=[
                rec_text_by_id[rid]
                for rid in area.matched_recommendation_ids
                if rid in rec_text_by_id
            ],
        )
    persisted = 0
    if persist:
        persisted = await _persist_synthesized(session, ctx=ctx, areas=areas)
        await session.commit()
    return {
        "ok": True,
        "reason": "synthesized" if not used_fallback else "heuristic_fallback",
        "message": (
            "Synthesized via Gemini Flash."
            if not used_fallback
            else "Vertex unavailable — used deterministic heuristic clustering."
        ),
        "data_source": "gemini-flash" if not used_fallback else "heuristic",
        "focus_areas": [a.to_dict() for a in areas],
        "persisted_count": persisted,
    }


async def backfill_focus_area_enrichment(
    session: AsyncSession, *, entity_display_id: str,
) -> dict[str, Any]:
    """Idempotent enrichment backfill for EXISTING focus_areas rows
    (Part 6.1e). For every renderable row of the entity's active run that
    lacks grounding / pillars_weight, compute + persist them; seed derived
    KPI rows when the (entity, fa) pair has none. DOCX-parsed rows keep
    their verbatim_quote / page_number / source_path untouched — only the
    NEW migration-052 columns are filled (their grounding carries
    source_kind="docx" with the verbatim quote as the representative
    quote when it is citable).

    Returns {"ok", "rows", "grounded", "kpi_rows"} — safe to re-run; rows
    already enriched are skipped.
    """
    ctx = await _load_run_context(session, entity_display_id=entity_display_id)
    if ctx is None:
        return {"ok": False, "reason": "no_run", "rows": 0, "grounded": 0, "kpi_rows": 0}
    rows = (await session.execute(
        text("""
            SELECT id, title, verbatim_quote, source_path, page_number,
                   involved_subcap_ids, grounding, financial_ref,
                   pillars_weight
              FROM focus_areas
             WHERE run_id = :rid
             ORDER BY id
        """),
        {"rid": ctx.run_id},
    )).all()
    from app.services.focus_area_sanity import clean_focus_area

    renderable = [
        r for r in rows
        if clean_focus_area(r.title or "", r.verbatim_quote or "",
                            list(r.involved_subcap_ids or []),
                            subvertical=ctx.subvertical)[0]
    ]
    involved: set[str] = set()
    for r in renderable:
        involved.update(r.involved_subcap_ids or [])
    inputs = await _load_grounding_inputs(
        session, run_id=ctx.run_id, entity_id=ctx.entity_id,
        subcap_ids=involved, catalog_version=ctx.catalog_version,
    )
    rec_text_by_id = {
        r["rec_id"]: f"{r.get('title') or ''}. {r.get('description') or ''}"
        for r in ctx.recommendations
    }
    grounded = 0
    kpi_rows = 0
    titles_fixed = 0
    subcaps_linked = 0
    # ── Deterministic FA→subcap classifier (2026-07-04 deep search: 83
    # rows carried NO involved_subcap_ids — the focus card rendered a
    # bare '-' score chip). Lexical similarity (nlp.similarity, TF-IDF
    # cosine) between the FA's title+quote and the run's scored subcap
    # names assigns the top matches; the Gemini rung
    # (focus_subcap_classification) remains the semantic uplift for rows
    # this floor can't place.
    unlinked = [r for r in rows if not (r.involved_subcap_ids or [])]
    if unlinked:
        sub_rows = (await session.execute(
            text("""
                SELECT s.subcap_id, COALESCE(cs.name, '') AS name
                FROM subcap_scores s
                LEFT JOIN ccg_subcaps cs
                  ON cs.version = :ver AND cs.subcap_id = s.subcap_id
                WHERE s.run_id = :rid
            """),
            {"rid": ctx.run_id, "ver": ctx.catalog_version or "v7.0"},
        )).all()
        docs = [(s.subcap_id, f"{s.subcap_id} {s.name}") for s in sub_rows if s.name]
        if docs:
            # MiniLM tier for focus-area → subcap linking (2026-07-14 audit:
            # was TF-IDF-only). Drop-in preferred_index() — semantic when the
            # model is baked, exact lexical fallback when cold.
            from app.services.nlp.semantic import preferred_index
            idx = preferred_index()
            idx.fit(docs)
            for r in unlinked:
                query = f"{r.title or ''} {r.verbatim_quote or ''}"[:600]
                hits = idx.top_k(query, k=8, min_score=0.12)
                ids = list(dict.fromkeys(sid for sid, _ in hits))[:6]
                if len(ids) >= 2:
                    await session.execute(
                        text("""
                            UPDATE focus_areas SET
                                involved_subcap_ids = CAST(:ids AS VARCHAR[])
                            WHERE id = :faid
                              AND (involved_subcap_ids IS NULL
                                   OR cardinality(involved_subcap_ids) = 0)
                        """),
                        {"faid": r.id, "ids": ids},
                    )
                    subcaps_linked += 1
        # re-read so the grounding/weights pass below sees the new links
        if subcaps_linked:
            rows = (await session.execute(
                text("""
                    SELECT id, title, verbatim_quote, source_path, page_number,
                           involved_subcap_ids, grounding, financial_ref,
                           pillars_weight
                      FROM focus_areas
                     WHERE run_id = :rid
                     ORDER BY id
                """),
                {"rid": ctx.run_id},
            )).all()
            renderable = [
                r for r in rows
                if clean_focus_area(r.title or "", r.verbatim_quote or "",
                                    list(r.involved_subcap_ids or []),
                                    subvertical=ctx.subvertical)[0]
            ]
            involved = set()
            for r in renderable:
                involved.update(r.involved_subcap_ids or [])
            inputs = await _load_grounding_inputs(
                session, run_id=ctx.run_id, entity_id=ctx.entity_id,
                subcap_ids=involved, catalog_version=ctx.catalog_version,
            )
    # ── Title hygiene runs over ALL rows (not just renderable) — the
    # stress-test probe is table-level: no `^F-\d+$` title may remain.
    for r in rows:
        new_title = humanize_focus_title(r.title or "", r.verbatim_quote or "")
        if new_title != (r.title or "").strip() and new_title:
            await session.execute(
                text("UPDATE focus_areas SET title = :t WHERE id = :faid"),
                {"t": new_title[:128], "faid": r.id},
            )
            titles_fixed += 1
    # ── Deterministic grounding-fallback pool + linked-insight cards
    # (wave 056). One entity-wide evidence pool feeds the token-overlap
    # grounding fallback for FAs the mined pass left ID-less; the run's
    # insight cards feed the layered linked_insights union. Both are
    # fill-if-empty writes below — the Gemini surfaces
    # (focus_grounding / focus_linked_insights) upgrade the residual
    # empties, never clobbering these honest deterministic rows.
    ev_pool = (await session.execute(
        text("""
            SELECT e_id, excerpt FROM evidence_index
             WHERE run_id = :rid AND excerpt IS NOT NULL
             ORDER BY tier ASC, e_id ASC LIMIT 240
        """),
        {"rid": ctx.run_id},
    )).all()
    evidence_pool = [(e.e_id, e.excerpt or "") for e in ev_pool]
    ic_rows = (await session.execute(
        text("""
            SELECT id, ic_id, title, severity, what_text,
                   linked_subcap_id, affects, linked_e_ids
              FROM insight_cards WHERE run_id = :rid ORDER BY ic_id
        """),
        {"rid": ctx.run_id},
    )).all()
    insight_cards = [{
        "id": str(c.id), "ic_id": c.ic_id, "title": c.title,
        "severity": c.severity, "what_text": c.what_text,
        "linked_subcap_id": c.linked_subcap_id,
        "affects": list(c.affects or []),
        "linked_e_ids": list(c.linked_e_ids or []),
    } for c in ic_rows]
    grounding_similarity = 0
    linked = 0
    for r in renderable:
        source_path = r.source_path or ""
        if source_path.startswith("synthesized:heuristic"):
            source_kind = "heuristic"
        elif source_path.startswith("synthesized:"):
            source_kind = "gemini"
        else:
            source_kind = "docx"
        subcap_ids = list(r.involved_subcap_ids or [])
        # Repair scope: missing grounding AND unhygienic grounding (raw
        # table-row quote / uncited inline [E-###]) both recompute.
        needs_grounding = _grounding_is_unhygienic(r.grounding)
        needs_weight = not isinstance(r.pillars_weight, dict)
        area = SynthesizedFocusArea(
            title=r.title or "",
            description=r.verbatim_quote or "",
            involved_subcap_ids=subcap_ids,
            data_source=source_kind,
        )
        matched_recs = [
            rec["rec_id"] for rec in ctx.recommendations
            if set(rec.get("target_subcap_ids") or []) & set(subcap_ids)
        ]
        _enrich_area(
            area, inputs, source_kind=source_kind,
            rec_texts=[rec_text_by_id[rid] for rid in matched_recs
                       if rid in rec_text_by_id],
        )
        if area.grounding is not None:
            # The row's own verbatim text is the primary anchor when the
            # mined-quote pass found nothing better — CLEANED (never the
            # raw table-row dump), with its inline [E-###] citations
            # merged into evidence_e_ids.
            if not area.grounding.get("representative_quote"):
                area.grounding["representative_quote"] = (
                    clean_representative_quote(r.verbatim_quote or "")
                )
            inline = extract_inline_eids(
                (area.grounding.get("representative_quote") or "")
                + " " + (r.verbatim_quote or "")
            )
            merged = inline + [
                e for e in (area.grounding.get("evidence_e_ids") or [])
                if e not in inline
            ]
            area.grounding["evidence_e_ids"] = merged[:6]
            # Deterministic grounding fallback (source_kind='similarity'):
            # a renderable FA that STILL carries no E-ID anchor after the
            # mined + inline pass gets the top token-overlap evidence from
            # the entity pool. This is the honest floor the operator asked
            # for — "some research reports have no linkable IDs" — that the
            # focus_grounding Gemini surface later upgrades.
            fa_text_for_ground = " ".join(
                t for t in (r.title, r.verbatim_quote,
                            area.grounding.get("representative_quote")) if t)
            if not area.grounding.get("evidence_e_ids") and evidence_pool:
                fb = deterministic_grounding_eids(
                    fa_text_for_ground, evidence_pool)
                if fb:
                    area.grounding["evidence_e_ids"] = fb
                    area.grounding["source_kind"] = "similarity"
                    grounding_similarity += 1
        if needs_grounding or needs_weight or r.financial_ref is None:
            await session.execute(
                text("""
                    UPDATE focus_areas SET
                        grounding = CASE WHEN CAST(:repair AS boolean)
                            THEN CAST(:grounding AS jsonb)
                            ELSE COALESCE(grounding, CAST(:grounding AS jsonb)) END,
                        financial_ref = COALESCE(financial_ref, :fin_ref),
                        pillars_weight = COALESCE(pillars_weight, CAST(:pweight AS jsonb))
                     WHERE id = :faid
                """),
                {
                    "faid": r.id,
                    "repair": needs_grounding,
                    "grounding": json.dumps(area.grounding) if area.grounding else None,
                    "fin_ref": area.financial_ref,
                    "pweight": (
                        json.dumps(area.pillars_weight)
                        if area.pillars_weight else None
                    ),
                },
            )
        if needs_grounding:
            grounded += 1
        kpi_rows += await _seed_kpi_overrides(
            session, entity_id=ctx.entity_id, fa_id=str(r.id), kpis=area.kpis,
        )
        # Layered linked insight cards — fill-if-empty on focus_areas.
        # linked_insights (added by migration 056; guarded so pre-056
        # envs no-op instead of erroring the whole backfill).
        li = build_linked_insights(
            fa_subcap_ids=subcap_ids,
            fa_evidence_e_ids=list(
                (area.grounding or {}).get("evidence_e_ids") or []),
            fa_text=" ".join(t for t in (r.title, r.verbatim_quote) if t),
            insight_cards=insight_cards,
        )
        if li:
            n = await session.execute(
                text("""
                    UPDATE focus_areas SET
                        linked_insights = CAST(:li AS jsonb),
                        enrichment_provenance = COALESCE(
                            enrichment_provenance, '{}'::jsonb)
                            || CAST(:prov AS jsonb)
                     WHERE id = :faid
                       AND COALESCE(
                           jsonb_array_length(linked_insights), 0) = 0
                """),
                {"faid": r.id, "li": json.dumps(li[:8]),
                 "prov": json.dumps({"linked_insights": {
                     "source": "deterministic", "count": len(li[:8])}})},
            )
            linked += n.rowcount or 0
    await session.commit()
    return {
        "ok": True,
        "rows": len(renderable),
        "grounded": grounded,
        "kpi_rows": kpi_rows,
        "titles_fixed": titles_fixed,
        "subcaps_linked": subcaps_linked,
        "grounding_similarity": grounding_similarity,
        "linked_insights": linked,
    }
