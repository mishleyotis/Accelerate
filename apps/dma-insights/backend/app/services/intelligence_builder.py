"""Intelligence builder — assembles grounding bundle + prompt and streams
Gemini tokens to the SSE Redis channel for each surface.

Called as a FastAPI background task when a client opens
  GET /api/v1/sse/intelligence/{surface}/{ref}

The ref format is surface-specific:
  subcap_narrative   → "{display_id}:{subcap_id}"  e.g. "fce-001:P2C3.2.4"
  why_now            → "{display_id}"
  insight_explanation→ "{display_id}:{insight_card_id}"
  platform_story     → "{display_id}:{platform_id}"
  meeting_prep       → "{display_id}"

Design:
  1. Parse ref → context (entity, subcap, etc.)
  2. Fetch grounding data from DB (scores, evidence, rationale)
  3. Render a prompt from a simple template (falls back to inline if table empty)
  4. Call vertex_client.stream() token-by-token, publish each to Redis
  5. Run V1-V3 validators on the full assembled text
  6. Publish "done" (with cited E-IDs) or "fallback" (with flag detail)

The caller (sse router) must NOT await this — it spawns it as a background
task so the SSE connection starts receiving tokens immediately.
"""
from __future__ import annotations

import json
import logging
import re as _re
from typing import Any

import redis.asyncio as redis_async
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.grounding_validator import ValidationFlags, validate_response
from app.services.vertex_client import GeminiCall, get_vertex_client

logger = logging.getLogger(__name__)

# Minimum MiniLM cosine an emitted evidence-bundle line must clear against
# the brief's topic — the SAME floor qa_surface_attribution scores the
# meeting_prep bundle at (2026-07-14). Sub-floor lines are pads, not
# grounding.
_EVIDENCE_LINE_RELEVANCE_FLOOR = 0.30

# ── Surface registry ──────────────────────────────────────────────────────────
# For each surface: the model to use + the inline prompt template (fallback
# when the prompt_templates table has no active row for this surface).

_TEMPLATES: dict[str, dict[str, Any]] = {
    "subcap_narrative": {
        "model": "flash",
        "template": (
            "You are a digital maturity expert for Zennify. "
            "Explain this sub-capability concisely to a financial-services executive.\n\n"
            "Sub-capability: {subcap_id} — {subcap_name}\n"
            "Client score: {score} / 5 (band {band})\n"
            "Peer median: {peer_median}\n"
            "Assessment rationale: {rationale}\n\n"
            "Linked evidence ({ev_count} items): {ev_summary}\n\n"
            "Write 3 short paragraphs:\n"
            "1. What this score means for this client\n"
            "2. Why it matters (regulatory/competitive/operational context)\n"
            "3. What closing the gap would look like\n\n"
            "Cite at least one evidence ID in the format E-NNN."
        ),
    },
    "why_now": {
        "model": "flash",
        "template": (
            "You are a digital maturity expert for Zennify. "
            "Write a 3-sentence 'Why Now' narrative for this client assessment.\n\n"
            "Entity: {entity_name}\n"
            "Overall score: {overall_score}\n"
            "SCQA situation: {scqa_situation}\n"
            "Why-now signals: {why_now_signals}\n"
            "Recent indexed evidence (cite ONLY these IDs):\n{recent_evidence}\n\n"
            "Format: 3 sentences. Start with a market/regulatory trigger, "
            "then the client's current position, then the opportunity window. "
            "Be specific; cite only the evidence IDs listed above — never invent IDs."
        ),
    },
    "insight_explanation": {
        "model": "flash",
        "template": (
            "You are a digital maturity expert for Zennify. "
            "Explain this insight card to a financial-services executive.\n\n"
            "Title: {title}\n"
            "What: {what_text}\n"
            "Why: {why_text}\n"
            "So what: {so_what_text}\n"
            "Linked evidence: {ev_summary}\n\n"
            "Write 2 concise paragraphs explaining the finding and its implications. "
            "Reference evidence IDs (E-NNN format) where they support your points."
        ),
    },
    "platform_story": {
        "model": "pro",
        "template": (
            "You are a Zennify solutions consultant writing a data-heavy "
            "platform DOSSIER (not conversation starters) for an AE.\n\n"
            "Platform: {platform_id}\n"
            "Entity: {entity_name}\n"
            "Fit score: {fit_score}\n"
            "Readiness: {readiness_line}\n"
            "Current systems detected in the stack: {current_stack}\n"
            "Top opportunity gaps (opportunity-ranked, score vs peer median): {top_gaps}\n"
            "Open prerequisites (score vs threshold): {prereq_lines}\n"
            "SCQA situation: {scqa_situation}\n"
            "Evidence behind those gaps (cite ONLY these E-IDs, in [E-NNN] "
            "brackets):\n{gap_evidence}\n\n"
            "Write THREE short titled sections, 1-2 sentences each:\n"
            "1. **Current state** — name the confirmed current systems above and "
            "where the entity stands; greenfield vs expansion.\n"
            "2. **Why {platform_id}** — the top opportunity gap by NAME with its "
            "score vs peer median.\n"
            "3. **Path to ready** — the open prerequisites (score vs threshold) "
            "and the sequencing.\n\n"
            "Every factual claim must cite an evidence ID in [E-NNN] bracket form "
            "from the list above. NEVER invent an ID, a number, a system name, or "
            "a figure not present in this grounding. Reference capabilities by "
            "NAME, not by PnCn.n.n code."
        ),
    },
    "firmographics_extraction": {
        # Clay is NOT in prod for this version (operator, 2026-06-10):
        # firmographics come from the client research/profile reports
        # first; this surface fills ONLY the gaps, grounded on the
        # entity's own report excerpts. STRICT JSON out; every field
        # must carry a verbatim supporting quote from the excerpts —
        # the caller drops any field whose quote is not present in the
        # grounding text (anti-fabrication, mirrors the E-ID check).
        "model": "flash",
        # DYNAMIC: {missing_fields}/{field_schema} are computed per entity by
        # _ctx_firmographics_extraction — only the still-unknown fields are
        # requested, never the report-owned ones.
        "template": (
            "You are a precise data extractor for Zennify. From ONLY the "
            "report excerpts below about {entity_name}, extract the "
            "institution's OWN firmographics. NEVER use figures that "
            "belong to an acquired company, a peer, or a parent.\n\n"
            "Report excerpts:\n{report_excerpts}\n\n"
            "The ONLY fields still unknown for this institution are: "
            "{missing_fields}. Output STRICT JSON (no prose, no markdown "
            "fences) with any subset of EXACTLY these keys — OMIT a key "
            "entirely when the excerpts do not state it explicitly, and "
            "NEVER return a key outside this list:\n"
            "{{{field_schema}}}"
        ),
    },
    "thought_leadership_extraction": {
        # Un-deads the D1 ThoughtLeadershipPanel (94/94 empty, 2026-06
        # audit): extract the roster's OWN public output (posts,
        # articles, podcasts, conference talks) STRICTLY from the
        # entity's indexed evidence excerpts. STRICT JSON out; every
        # item must carry a verbatim `excerpt` copied from the provided
        # lines — the caller (enrich_corpus._accept_tl_items) drops any
        # item whose excerpt is not a substring of the grounding text,
        # mirroring the firmographics_extraction anti-fabrication gate.
        "model": "flash",
        "template": (
            "You are a precise data extractor for Zennify. From ONLY the "
            "evidence excerpts below about {entity_name}, extract thought-"
            "leadership items PUBLISHED OR DELIVERED BY the institution or "
            "its own leaders (LinkedIn posts, articles, podcasts, "
            "conference talks, blog posts, interviews). NEVER include "
            "third-party coverage ABOUT the institution, peer content, or "
            "anything the excerpts do not explicitly describe.\n\n"
            "Evidence excerpts:\n{report_excerpts}\n\n"
            "Output a STRICT JSON array (no prose, no markdown fences). "
            "Each element:\n"
            "[{{\"type\": \"linkedin_post|article|podcast|conference|blog|interview\",\n"
            "  \"date\": \"YYYY-MM-DD or null\",\n"
            "  \"title\": \"<short title>\",\n"
            "  \"excerpt\": \"<verbatim substring copied from the excerpts above>\",\n"
            "  \"author\": \"<person name or null>\",\n"
            "  \"url\": \"<url from the excerpts or null>\"}}]\n"
            "Return [] when the excerpts contain no such items. The "
            "`excerpt` value MUST be copied verbatim from the lines above."
        ),
    },
    "meeting_prep": {
        "model": "pro",
        "template": (
            "You are a Zennify AE preparing for a client meeting. "
            "Produce a concise pre-meeting brief.\n\n"
            "Entity: {entity_name}\n"
            "Overall score: {overall_score}\n"
            "Top 3 findings: {top_findings}\n"
            "Platform fit: {platform_summary}\n"
            "SCQA: {scqa_situation}\n\n"
            "Recent evidence about this client (the ONLY citable sources):\n"
            "{recent_evidence}\n\n"
            "Write:\n"
            "• Executive summary (2 sentences)\n"
            "• Top 3 talking points — each anchored on a SPECIFIC client "
            "fact from the evidence above, citing its E-ID in [brackets]\n"
            "• 2 anticipated objections + responses (cite evidence where it "
            "rebuts the objection)\n"
            "• 3 metric questions to ask the client\n"
            "• Recommended next-step CTA\n\n"
            "Cite ONLY E-IDs that appear in the evidence above — never "
            "invent one. Keep the total under 400 words."
        ),
    },
}


# ── Redis publish helpers ─────────────────────────────────────────────────────

async def _publish(
    redis: redis_async.Redis,
    surface: str,
    ref: str,
    payload: dict[str, Any],
) -> None:
    channel = f"dma:sse:gemini:{surface}:{ref}"
    try:
        await redis.publish(channel, json.dumps(payload, default=str))
    except Exception:
        logger.debug("publish failed (channel=%s) — subscriber likely gone", channel)


# ── Context builders per surface ──────────────────────────────────────────────

async def _ctx_subcap_narrative(
    session: AsyncSession, display_id: str, subcap_id: str
) -> dict[str, Any]:
    row = (
        await session.execute(
            text("""
                SELECT
                    e.name AS entity_name,
                    ss.score,
                    ss.band,
                    ss.peer_median,
                    ss.rationale,
                    cs.name AS subcap_name
                FROM entities e
                JOIN runs r ON r.entity_id = e.id AND r.status = 'ACTIVE'
                JOIN subcap_scores ss ON ss.run_id = r.id AND ss.subcap_id = :sid
                LEFT JOIN ccg_subcaps cs
                    ON cs.subcap_id = ss.subcap_id
                    AND cs.version = r.ccg_catalog_version
                WHERE e.display_id = :did
                ORDER BY r.completed_at DESC NULLS LAST
                LIMIT 1
            """),
            {"did": display_id, "sid": subcap_id},
        )
    ).first()

    ev_rows = (
        await session.execute(
            text("""
                SELECT ei.e_id, ei.source_name, COALESCE(ei.excerpt, '') AS excerpt
                FROM evidence_index ei
                JOIN runs r ON r.id = ei.run_id
                JOIN entities e ON e.id = r.entity_id
                WHERE e.display_id = :did
                  AND :sid = ANY(ei.linked_subcap_ids)
                  AND r.status = 'ACTIVE'
                ORDER BY ei.tier ASC
                LIMIT 5
            """),
            {"did": display_id, "sid": subcap_id},
        )
    ).fetchall()

    ev_summary = "; ".join(
        f"{r.e_id} ({r.source_name}: {r.excerpt[:60]}…)" for r in ev_rows
    ) if ev_rows else "No linked evidence"
    # Structured one-line-per-item variant of ev_summary; consumed by the
    # deterministic cold fallback so it can render a real "Grounded
    # evidence" list (title + E-ID + excerpt) when Vertex is unreachable.
    ev_lines = [
        f"{r.e_id} ({r.source_name}): {r.excerpt[:140]}" for r in ev_rows
    ]

    if row is None:
        return {
            "subcap_id": subcap_id,
            "subcap_name": subcap_id,
            "score": "N/A",
            "band": "N/A",
            "peer_median": "N/A",
            "rationale": "No assessment data available.",
            "ev_count": 0,
            "ev_summary": ev_summary,
            "_ev_lines": ev_lines,
            # V1 grounding validator needs the IDs we actually retrieved
            # so it can reject citations to E-IDs that weren't supplied
            # to the model.
            "_retrieved_e_ids": [r.e_id for r in ev_rows],
        }
    return {
        "subcap_id": subcap_id,
        "subcap_name": row.subcap_name or subcap_id,
        "score": f"{row.score:.1f}" if row.score is not None else "N/A",
        "band": row.band or "N/A",
        "peer_median": f"{row.peer_median:.1f}" if row.peer_median is not None else "N/A",
        "rationale": row.rationale or "No rationale recorded.",
        "ev_count": len(ev_rows),
        "ev_summary": ev_summary,
        "_ev_lines": ev_lines,
        "_retrieved_e_ids": [r.e_id for r in ev_rows],
    }



async def _recent_evidence_lines(
    session: AsyncSession,
    display_id: str,
    *,
    subcap_ids: list[str] | None = None,
    limit: int = 8,
    topic: str | None = None,
) -> str:
    """Top evidence rows for the entity's ACTIVE run as prompt-bundle
    lines ("E-001 (T6, 3mo, SourceName): excerpt…"). Grounds the
    why_now / platform_story prompts on the entity's OWN indexed
    evidence so "cite evidence IDs" is satisfiable rather than an
    invitation to fabricate (2026-06-10 audit, CRITICAL #4/#8).
    `subcap_ids` scopes to evidence linked at-or-under those ids.

    ``topic`` (2026-07-09 NLP hardening): when given and the MiniLM tier is
    hot, a WIDE candidate set is recalled and re-ranked by retrieve-then-
    rerank RELEVANCE to the topic, so the bundle grounds the brief's actual
    subject — the pure tier/recency ordering put semantically unrelated
    excerpts in 51.5% of meeting-prep bundles (corpus audit), which the
    membership-only citation validator then blessed. Cold tier or no topic
    → the original tier/recency ordering, unchanged."""
    scope = ""
    wide = bool(topic)
    params: dict[str, Any] = {
        "did": display_id, "lim": max(limit * 8, 48) if wide else limit,
    }
    if subcap_ids:
        scope = "AND ei.linked_subcap_ids && CAST(:sids AS varchar[])"
        params["sids"] = [s[:32] for s in subcap_ids][:16]
    rows = (
        await session.execute(
            text(f"""
                SELECT ei.e_id, ei.tier, ei.recency_months,
                       ei.source_name, COALESCE(ei.excerpt, '') AS excerpt
                FROM evidence_index ei
                JOIN runs r ON r.id = ei.run_id AND r.status = 'ACTIVE'
                JOIN entities e ON e.id = r.entity_id
                WHERE e.display_id = :did {scope}
                  AND length(COALESCE(ei.excerpt, '')) > 40
                ORDER BY ei.tier DESC NULLS LAST,
                         ei.recency_months ASC NULLS LAST
                LIMIT :lim
            """),
            params,
        )
    ).fetchall()
    if not rows:
        return "No indexed evidence for this run."

    def _fmt(r) -> str:
        return (
            f"- {r.e_id} ({f'T{r.tier}' if r.tier is not None else 'tier unstated'}, "
            f"{str(r.recency_months) + 'mo' if r.recency_months is not None else 'undated'}, "
            f"{r.source_name}): {r.excerpt[:140]}"
        )

    if wide and len(rows) > limit:
        try:
            from app.services.nlp import rerank as _rr
            from app.services.nlp.semantic import SemanticIndex, model_available
            if model_available():
                idx = SemanticIndex()
                idx.fit([(i, r.excerpt) for i, r in enumerate(rows)])
                recalled = idx.top_k(topic, len(rows), min_score=0.0)
                fused = _rr.rerank(
                    topic, [(i, rows[i].excerpt, cos) for i, cos in recalled])
                order = [i for i, _s in (fused or recalled)]
                # Relevance floor (2026-07-14 attribution audit): the old
                # unconditional top-`limit` cut shipped sub-floor pads for
                # thin/off-topic entities — qa_surface_attribution scores
                # every emitted line vs the SAME topic at the 0.30 MiniLM
                # floor (meeting_prep fidelity 0.943 < 0.95). Keep only
                # lines clearing the floor, measured on the exact emitted
                # line text; a bundle where nothing clears keeps its single
                # best line (a marginal grounding beats none).
                kept = [i for i in order
                        if idx.relevance(topic, _fmt(rows[i])[:400])
                        >= _EVIDENCE_LINE_RELEVANCE_FLOOR]
                order = (kept or order[:1])[:limit]
                rows = [rows[i] for i in order]
        except Exception:
            rows = rows[:limit]     # never let ranking break the surface
    rows = rows[:limit]
    return "\n".join(_fmt(r) for r in rows)


async def _ctx_why_now(
    session: AsyncSession, display_id: str
) -> dict[str, Any]:
    row = (
        await session.execute(
            text("""
                SELECT e.name AS entity_name, r.scqa, r.why_now_signals
                FROM entities e
                JOIN runs r ON r.entity_id = e.id AND r.status = 'ACTIVE'
                WHERE e.display_id = :did
                ORDER BY r.completed_at DESC NULLS LAST LIMIT 1
            """),
            {"did": display_id},
        )
    ).first()

    scores = (
        await session.execute(
            text("""
                SELECT ROUND(AVG(ss.score)::numeric, 1) AS overall
                FROM subcap_scores ss
                JOIN runs r ON r.id = ss.run_id
                JOIN entities e ON e.id = r.entity_id
                WHERE e.display_id = :did AND r.status = 'ACTIVE'
            """),
            {"did": display_id},
        )
    ).scalar()

    if row is None:
        return {
            "entity_name": display_id,
            "overall_score": "N/A",
            "scqa_situation": "No SCQA recorded.",
            "why_now_signals": "None",
            "recent_evidence": "No indexed evidence for this run.",
            "_retrieved_e_ids": [],
        }
    scqa = row.scqa or {}
    signals = row.why_now_signals
    if isinstance(signals, list):
        # Readable per-signal lines (kind + the prose an AE reads), never raw
        # dict reprs — the model mirrors what it is shown, and dict dumps were
        # restated verbatim into outputs (2026-07-06 duplication audit).
        signals = "; ".join(
            (f"{s.get('kind') or 'SIGNAL'}: {s.get('text') or s.get('detail') or ''}".strip(" :")
             if isinstance(s, dict) else str(s))
            for s in signals if s)
    ctx = {
        "entity_name": row.entity_name,
        "overall_score": str(scores) if scores else "N/A",
        "scqa_situation": scqa.get("situation", "No situation recorded.") if isinstance(scqa, dict) else str(scqa),
        "why_now_signals": signals or "None",
        "recent_evidence": await _recent_evidence_lines(session, display_id),
    }
    # V1 grounding scope = every E-ID actually shown to the model (evidence
    # lines + inline citations the signals/SCQA carry — all DB-derived). An
    # empty list here made the validator flag EVERY citation as out-of-bundle
    # (the enrich-sweep validator_blocked=219/273 false-positive class).
    ctx["_retrieved_e_ids"] = _extract_e_ids(
        " ".join(str(v) for v in ctx.values()))
    return ctx


async def _ctx_insight_explanation(
    session: AsyncSession, display_id: str, card_id: str
) -> dict[str, Any]:
    row = (
        await session.execute(
            text("""
                SELECT ic.title, ic.what_text, ic.why_text, ic.so_what_text,
                       ic.affected_subcap_ids
                FROM insight_cards ic
                JOIN runs r ON r.id = ic.run_id
                JOIN entities e ON e.id = r.entity_id
                WHERE e.display_id = :did
                  AND (ic.id::text = :cid OR ic.ic_id = :cid)
                LIMIT 1
            """),
            {"did": display_id, "cid": card_id},
        )
    ).first()

    if row is None:
        return {
            "title": card_id,
            "what_text": "No detail available.",
            "why_text": "",
            "so_what_text": "",
            "ev_summary": "No evidence linked.",
            "_retrieved_e_ids": [],
        }

    subcap_ids = row.affected_subcap_ids or []
    ev_rows = (
        await session.execute(
            text("""
                SELECT ei.e_id, ei.source_name, COALESCE(ei.excerpt, '') AS excerpt
                FROM evidence_index ei
                JOIN runs r ON r.id = ei.run_id
                JOIN entities e ON e.id = r.entity_id
                WHERE e.display_id = :did
                  AND ei.subcap_ids && :sids
                ORDER BY ei.tier ASC LIMIT 5
            """),
            {"did": display_id, "sids": subcap_ids},
        )
    ).fetchall() if subcap_ids else []

    ev_summary = "; ".join(
        f"{r.e_id} ({r.source_name}: {r.excerpt[:60]}…)" for r in ev_rows
    ) if ev_rows else "No linked evidence"

    return {
        "title": row.title,
        "what_text": row.what_text or "",
        "why_text": row.why_text or "",
        "so_what_text": row.so_what_text or "",
        "ev_summary": ev_summary,
        "_ev_lines": [
            f"{r.e_id} ({r.source_name}): {r.excerpt[:140]}" for r in ev_rows
        ],
        "_retrieved_e_ids": [r.e_id for r in ev_rows],
    }


async def _ctx_platform_story(
    session: AsyncSession, display_id: str, platform_id: str
) -> dict[str, Any]:
    """Grounding for the platform_story Gemini uplift — REGROUNDED (platform
    v3) on the deterministic dossier's inputs, not the sorted-first
    addressable id anchor the audit found (which duplicated the starters).

    Feeds the fit engine's TOP-OPPORTUNITY subcaps (from
    ``fit_breakdown.top_subcaps`` — opportunity-ranked, NOT
    ``addressable_subcap_ids[:5]``) with score-vs-peer-median, the readiness
    light + OPEN prerequisites (scores vs thresholds), the confirmed-ABSENT
    families, and the entity's confirmed current systems — so the prompt asks
    for a where-the-entity-is dossier, never a starters duplicate."""
    row = (
        await session.execute(
            text("""
                SELECT e.name AS entity_name, r.scqa,
                       ps.fit_score, ps.addressable_subcap_ids AS top_addressable_gaps,
                       ps.fit_breakdown, ps.readiness_index
                FROM entities e
                JOIN runs r ON r.entity_id = e.id AND r.status = 'ACTIVE'
                LEFT JOIN platform_scores ps
                    ON ps.run_id = r.id AND ps.platform_id = :pid
                WHERE e.display_id = :did
                ORDER BY r.completed_at DESC NULLS LAST LIMIT 1
            """),
            {"did": display_id, "pid": platform_id},
        )
    ).first()

    if row is None:
        return {
            "entity_name": display_id,
            "platform_id": platform_id,
            "fit_score": "N/A",
            "readiness_line": "No readiness recorded.",
            "top_gaps": "No gap data",
            "current_stack": "No detected current systems.",
            "prereq_lines": "No prerequisites recorded.",
            "scqa_situation": "",
            "gap_evidence": "No indexed evidence for this run.",
            "_retrieved_e_ids": [],
        }

    scqa = row.scqa or {}
    bd = row.fit_breakdown if isinstance(row.fit_breakdown, dict) else {}
    top_subcaps = [t for t in (bd.get("top_subcaps") or []) if isinstance(t, dict)]
    # Opportunity-ranked named facts (never the sorted-first id anchor).
    gap_facts: list[str] = []
    gap_subcap_ids: list[str] = []
    for t in top_subcaps[:5]:
        gap_subcap_ids.append(str(t.get("subcap_id")))
        nm = t.get("name") or t.get("subcap_id")
        sc, pm = t.get("score"), t.get("peer_median")
        if isinstance(sc, int | float) and isinstance(pm, int | float):
            gap_facts.append(f"{nm}: {sc:.1f}/5 vs {pm:.1f} peer median")
        elif isinstance(sc, int | float):
            gap_facts.append(f"{nm}: {sc:.1f}/5")
        else:
            gap_facts.append(str(nm))
    if not gap_facts:
        gaps = row.top_addressable_gaps or []
        gap_subcap_ids = [str(g) for g in gaps[:5]]
        gap_facts = gap_subcap_ids

    # OPEN prerequisites with scores vs thresholds (from the persisted spec).
    prereqs = (bd.get("prereqs") or {})
    prereq_lines: list[str] = []
    for sid, p in prereqs.items():
        if not isinstance(p, dict):
            continue
        status = str(p.get("status", "")).upper()
        cur, thr = p.get("current_score"), p.get("threshold")
        if status != "MET" and isinstance(cur, int | float) and isinstance(thr, int | float):
            prereq_lines.append(
                f"{p.get('name', sid)}: {cur:.1f} vs {thr:.1f} threshold ({status})")
    absent = [str(f) for f in (bd.get("absent_families") or []) if f]

    # Confirmed current systems (named organizational capabilities) — one
    # cheap query, guarded so a minimal test DB degrades gracefully.
    current_stack = "No detected current systems."
    try:
        tech_rows = (
            await session.execute(
                text("""
                    SELECT t.vendor, t.product, t.status
                    FROM tech_stack_entries t
                    JOIN entities e ON e.id = t.entity_id
                    WHERE e.display_id = :did
                      AND t.status IN ('CONFIRMED', 'INFERRED')
                    ORDER BY t.status ASC
                    LIMIT 6
                """),
                {"did": display_id},
            )
        ).all()
        systems = [str(r.product or r.vendor) for r in tech_rows if (r.product or r.vendor)]
        if systems:
            current_stack = ", ".join(dict.fromkeys(systems))
    except Exception:
        pass

    readiness = row.readiness_index or "unrated"
    readiness_line = (
        f"{readiness} — {len(prereq_lines)} prerequisite(s) open"
        if prereq_lines else f"{readiness} — prerequisites clear"
    )
    ctx = {
        "entity_name": row.entity_name,
        "platform_id": platform_id,
        "fit_score": f"{row.fit_score:.0f}/100" if row.fit_score is not None else "N/A",
        "readiness_line": readiness_line
        + (f"; confirmed-absent families: {', '.join(absent[:2])}" if absent else ""),
        "top_gaps": "; ".join(gap_facts),
        "current_stack": current_stack,
        "prereq_lines": "; ".join(prereq_lines) or "All mapped prerequisites are met.",
        "scqa_situation": scqa.get("situation", "") if isinstance(scqa, dict) else str(scqa),
        "gap_evidence": await _recent_evidence_lines(
            session, display_id,
            subcap_ids=gap_subcap_ids or None,
        ),
    }
    # Same V1 grounding-scope contract as _ctx_why_now: every E-ID the prompt
    # shows (gap evidence + any SCQA inline citations) is a legal citation.
    ctx["_retrieved_e_ids"] = _extract_e_ids(
        " ".join(str(v) for v in ctx.values()))
    return ctx


async def _ctx_meeting_prep(
    session: AsyncSession, display_id: str
) -> dict[str, Any]:
    row = (
        await session.execute(
            text("""
                SELECT e.name AS entity_name, r.scqa
                FROM entities e
                JOIN runs r ON r.entity_id = e.id AND r.status = 'ACTIVE'
                WHERE e.display_id = :did
                ORDER BY r.completed_at DESC NULLS LAST LIMIT 1
            """),
            {"did": display_id},
        )
    ).first()

    scores_row = (
        await session.execute(
            text("""
                SELECT ROUND(AVG(ss.score)::numeric, 1) AS overall
                FROM subcap_scores ss
                JOIN runs r ON r.id = ss.run_id
                JOIN entities e ON e.id = r.entity_id
                WHERE e.display_id = :did AND r.status = 'ACTIVE'
            """),
            {"did": display_id},
        )
    ).scalar()

    findings = (
        await session.execute(
            text("""
                SELECT ic.title, ic.severity
                FROM insight_cards ic
                JOIN runs r ON r.id = ic.run_id
                JOIN entities e ON e.id = r.entity_id
                WHERE e.display_id = :did AND r.status = 'ACTIVE'
                ORDER BY CASE ic.severity
                    WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2
                    WHEN 'MEDIUM' THEN 3 ELSE 4 END
                LIMIT 3
            """),
            {"did": display_id},
        )
    ).fetchall()

    platforms = (
        await session.execute(
            text("""
                SELECT ps.platform_id, ps.fit_score
                FROM platform_scores ps
                JOIN runs r ON r.id = ps.run_id
                JOIN entities e ON e.id = r.entity_id
                WHERE e.display_id = :did AND r.status = 'ACTIVE'
                ORDER BY ps.fit_score DESC NULLS LAST LIMIT 3
            """),
            {"did": display_id},
        )
    ).fetchall()

    if row is None:
        return {
            "entity_name": display_id,
            "overall_score": "N/A",
            "top_findings": "No findings available.",
            "platform_summary": "No platform data.",
            "scqa_situation": "",
        }

    scqa = row.scqa or {}
    findings_str = "; ".join(
        f"{r.title} ({r.severity})" for r in findings
    ) if findings else "No findings"
    platforms_str = ", ".join(
        f"{r.platform_id} (fit {r.fit_score:.2f})" for r in platforms
    ) if platforms else "No platform scores"

    # Ground the brief in the entity's own evidence so every talking point
    # can cite an E-ID and the V1/V2 validator has a REAL bundle to check —
    # previously _retrieved_e_ids was empty here, making the pro-model output
    # an ungrounded synthesis of finding titles (audit 2026-07-04). The bundle
    # is retrieved SEMANTICALLY against the meeting's own subject (entity +
    # top findings + SCQA situation) — pure tier/recency retrieval put
    # off-topic excerpts in 51.5% of bundles (2026-07-09 corpus audit).
    scqa_situation = (
        scqa.get("situation", "") if isinstance(scqa, dict) else str(scqa))
    topic = " ".join(filter(None, [
        row.entity_name, findings_str if findings else "",
        scqa_situation[:280],
    ])).strip() or None
    evidence_lines = await _recent_evidence_lines(
        session, display_id, topic=topic)
    return {
        "entity_name": row.entity_name,
        "overall_score": str(scores_row) if scores_row else "N/A",
        "top_findings": findings_str,
        "platform_summary": platforms_str,
        "scqa_situation": scqa_situation,
        "recent_evidence": evidence_lines,
        "_retrieved_e_ids": _extract_e_ids(evidence_lines),
    }


# ── Deterministic cold fallback ───────────────────────────────────────────────
# When the Vertex stream fails, we do NOT discard the already-assembled
# grounding context. Instead each surface renders a deterministic body
# template-filled from the real ctx values (score, band, peer_median,
# rationale, top evidence excerpts w/ E-IDs) — ported from the prototype's
# per-surface body tone (374f91c6:572-601) but never fabricating a fact
# the grounding did not supply.

# ctx builders emit these exact placeholder strings when a field is
# absent — the fallback renderer treats them as "not present" so the
# deterministic body never echoes a placeholder as if it were a fact.
_CTX_PLACEHOLDERS = {
    "", "N/A", "None",
    "No rationale recorded.", "No assessment data available.",
    "No situation recorded.", "No SCQA recorded.",
    "No indexed evidence for this run.", "No linked evidence",
    "No detail available.", "No gap data",
    "No findings available.", "No platform data.",
    "No findings", "No platform scores",
    "No detected current systems.", "No readiness recorded.",
    "No prerequisites recorded.",
}


def _ctx_has(ctx: dict[str, Any], key: str) -> bool:
    val = ctx.get(key)
    if val is None:
        return False
    s = str(val).strip()
    return bool(s) and s not in _CTX_PLACEHOLDERS


def _ev_block(ctx: dict[str, Any]) -> str | None:
    """'Grounded evidence' list from the structured `_ev_lines` the ctx
    builders stash (one line per retrieved evidence row, E-ID first)."""
    lines = [str(ln).strip() for ln in ctx.get("_ev_lines", []) if str(ln).strip()]
    if not lines:
        return None
    return "Grounded evidence:\n" + "\n".join(f"- {ln}" for ln in lines)


def _grounded_fallback(surface: str, ctx: dict[str, Any]) -> tuple[str, list[str]]:
    """Render the per-surface deterministic body from the already-fetched
    grounding ctx. Returns (body, cited_evidence_ids) where the cited IDs
    are exactly the E-IDs that appear in the body (never invented)."""
    parts: list[str] = []

    if surface == "subcap_narrative":
        name = str(ctx.get("subcap_name") or ctx.get("subcap_id") or "This sub-capability")
        sid = str(ctx.get("subcap_id") or "")
        head = name if not sid or sid == name else f"{name} ({sid})"
        if _ctx_has(ctx, "score"):
            head += f" scores {ctx['score']} / 5"
            if _ctx_has(ctx, "band"):
                head += f" (band {ctx['band']})"
            head += "."
        else:
            head += " has no score recorded for the active run."
        if _ctx_has(ctx, "peer_median"):
            head += f" Peer median is {ctx['peer_median']}."
        parts.append(head)
        if _ctx_has(ctx, "rationale"):
            parts.append(f"Assessment rationale: {ctx['rationale']}")
        ev = _ev_block(ctx)
        if ev:
            parts.append(ev)
        else:
            parts.append(
                "No evidence is linked to this sub-capability in the "
                "current run — confirm in discovery."
            )
        if _ctx_has(ctx, "peer_median"):
            parts.append(
                "Closing the gap to peer requires investment in the "
                "platform candidates mapped to this sub-capability; the "
                "exact path differs by subvertical pillar weight."
            )

    elif surface == "why_now":
        ent = str(ctx.get("entity_name") or "This entity")
        if _ctx_has(ctx, "overall_score"):
            parts.append(
                f"{ent} currently averages {ctx['overall_score']} / 5 "
                "across scored sub-capabilities."
            )
        else:
            parts.append(f"{ent} has no aggregate score recorded for the active run.")
        if _ctx_has(ctx, "scqa_situation"):
            parts.append(f"Situation: {ctx['scqa_situation']}")
        if _ctx_has(ctx, "why_now_signals"):
            parts.append(f"Timing signals on file: {ctx['why_now_signals']}")
        recent = str(ctx.get("recent_evidence") or "")
        if _extract_e_ids(recent):
            parts.append(f"Recent grounded evidence:\n{recent}")

    elif surface == "platform_story":
        ent = str(ctx.get("entity_name") or "this entity")
        pid = str(ctx.get("platform_id") or "This platform")
        if _ctx_has(ctx, "fit_score"):
            head = f"{pid} fit score for {ent}: {ctx['fit_score']}."
        else:
            head = f"No fit score is recorded for {pid} on {ent}'s active run."
        if _ctx_has(ctx, "readiness_line"):
            head += f" Readiness: {ctx['readiness_line']}."
        parts.append(head)
        if _ctx_has(ctx, "current_stack"):
            parts.append(f"Current systems: {ctx['current_stack']}.")
        if _ctx_has(ctx, "top_gaps"):
            parts.append(f"Top opportunity gaps: {ctx['top_gaps']}.")
        if _ctx_has(ctx, "prereq_lines"):
            parts.append(f"Path to ready: {ctx['prereq_lines']}.")
        if _ctx_has(ctx, "scqa_situation"):
            parts.append(f"Situation: {ctx['scqa_situation']}")
        gap_ev = str(ctx.get("gap_evidence") or "")
        if _extract_e_ids(gap_ev):
            parts.append(f"Evidence behind those gaps:\n{gap_ev}")

    elif surface == "insight_explanation":
        if _ctx_has(ctx, "title"):
            parts.append(str(ctx["title"]))
        if _ctx_has(ctx, "what_text"):
            parts.append(f"What: {ctx['what_text']}")
        if _ctx_has(ctx, "why_text"):
            parts.append(f"Why: {ctx['why_text']}")
        if _ctx_has(ctx, "so_what_text"):
            parts.append(f"So what: {ctx['so_what_text']}")
        ev = _ev_block(ctx)
        if ev:
            parts.append(ev)

    elif surface == "meeting_prep":
        ent = str(ctx.get("entity_name") or "this entity")
        head = f"Pre-meeting brief for {ent}."
        if _ctx_has(ctx, "overall_score"):
            head += f" Overall score: {ctx['overall_score']} / 5."
        parts.append(head)
        if _ctx_has(ctx, "top_findings"):
            parts.append(f"Top findings: {ctx['top_findings']}")
        if _ctx_has(ctx, "platform_summary"):
            parts.append(f"Platform fit: {ctx['platform_summary']}")
        if _ctx_has(ctx, "scqa_situation"):
            parts.append(f"Situation: {ctx['scqa_situation']}")

    if not parts:
        # Surfaces with no meaningful deterministic template (e.g.
        # firmographics_extraction, whose consumer expects strict JSON)
        # stay honest rather than fabricating.
        return (
            "Insight temporarily unavailable — generation failed and no "
            "deterministic summary exists for this surface.",
            [],
        )

    parts.append(
        "— Deterministic summary rendered from the run's grounding data "
        "(Gemini unavailable)."
    )
    body = "\n\n".join(parts)
    return body, _extract_e_ids(body)


# ── Main entry ────────────────────────────────────────────────────────────────

async def run_intelligence(
    *,
    surface: str,
    ref: str,
    session: AsyncSession,
    redis: redis_async.Redis,
) -> None:
    """Assemble grounding, stream Gemini tokens to the SSE channel, validate.

    Called as a FastAPI BackgroundTask from the SSE intelligence endpoint.
    On any unhandled exception the fallback text is served and the error
    is logged — the SSE subscriber is never left hanging.
    """
    # NOTE on payload keys: fallback events carry the body under BOTH
    # `served_text` (historical key) and `text` (matches the token-event
    # key; forward-compat contract with lib/sse.ts + IntelligencePanel,
    # which reads either).
    cfg = _TEMPLATES.get(surface)
    if cfg is None:
        unsupported = f"Surface '{surface}' is not yet supported."
        await _publish(redis, surface, ref, {
            "kind": "fallback",
            "flags": {"unsupported_surface": surface},
            "served_text": unsupported,
            "text": unsupported,
        })
        return

    try:
        # Parse ref → context variables
        ctx = await _build_context(session, surface, ref)
    except Exception as exc:
        logger.warning("intelligence_builder: context build failed surface=%s ref=%s: %s", surface, ref, exc)
        ctx_err_text = (
            "Insight not available — the grounding data for this surface "
            "could not be loaded. Retry, or open the evidence drawer to "
            "review the underlying rows directly."
        )
        await _publish(redis, surface, ref, {
            "kind": "fallback",
            "flags": {"context_error": str(exc)},
            "served_text": ctx_err_text,
            "text": ctx_err_text,
        })
        return

    prompt = cfg["template"].format_map(_SafeFormatMap(ctx))

    vertex = get_vertex_client()
    call = GeminiCall(
        surface=surface,
        model=cfg["model"],
        prompt=prompt,
        temperature=0.2,
        max_output_tokens=1024,
    )

    chunks: list[str] = []
    try:
        async for chunk in vertex.stream(call):
            if not chunk:
                continue
            chunks.append(chunk)
            await _publish(redis, surface, ref, {"kind": "token", "text": chunk})
    except Exception as exc:
        logger.warning(
            "intelligence_builder: vertex stream failed surface=%s ref=%s: %s",
            surface, ref, exc,
        )
        # Cold/failed Vertex: do NOT discard the grounded ctx. Serve the
        # per-surface deterministic body filled from the already-fetched
        # grounding, with real citation chips.
        body, cited = _grounded_fallback(surface, ctx)
        await _publish(redis, surface, ref, {
            "kind": "fallback",
            "flags": {"vertex_error": str(exc), "deterministic": True},
            "served_text": body,
            "text": body,
            "cited_evidence_ids": cited,
        })
        return

    full_text = "".join(chunks)

    # Run V1-V3 validators
    cited_e_ids = _extract_e_ids(full_text)
    flags = ValidationFlags()
    try:
        flags = await validate_response(
            session=session,
            response_text=full_text,
            cited_evidence_ids=cited_e_ids,
            retrieved_bundle_e_ids=list(ctx.get("_retrieved_e_ids", [])),
            entity_id=None,
            run_catalog_version="v7.0",
        )
    except Exception as exc:
        logger.warning("intelligence_builder: validator failed: %s", exc)

    if flags.is_clean:
        await _publish(redis, surface, ref, {
            "kind": "done",
            "cited_evidence_ids": cited_e_ids,
        })
    else:
        # Validator rejected the generated answer (fabricated/out-of-scope id
        # etc.). Do NOT serve an apology — degrade to the SAME grounded
        # deterministic floor the cold-Vertex path uses (score/band/peer/
        # rationale + only real retrieved E-IDs), so the AE still gets the
        # substantive summary. This is the "fall back to template-fill on any
        # flag" contract (CLAUDE.md hard rule), not a withheld stub.
        body, cited = _grounded_fallback(surface, ctx)
        await _publish(redis, surface, ref, {
            "kind": "fallback",
            "flags": flags.to_dict(),
            "served_text": body,
            "text": body,
            "cited_evidence_ids": cited,
        })


async def _ctx_firmographics_extraction(
    session: AsyncSession, display_id: str
) -> dict[str, Any]:
    """Grounding for the firmographics gap-fill: the entity's OWN
    narrative + financial-highlight lines + entity-profile/exec report
    sections + top evidence excerpts. Everything in `report_excerpts`
    is candidate quote material — the caller verifies each returned
    quote is a substring of this text before accepting a field."""
    row = (
        await session.execute(
            text("""
                SELECT e.id AS entity_id, e.name AS entity_name,
                       f.narrative_md, f.financial_highlights
                FROM entities e
                LEFT JOIN firmographics f ON f.entity_id = e.id
                WHERE e.display_id = :did
            """),
            {"did": display_id},
        )
    ).first()
    if row is None:
        raise ValueError(f"entity not found: {display_id}")
    parts: list[str] = []
    if row.narrative_md:
        parts.append(str(row.narrative_md)[:4000])
    fh = row.financial_highlights or {}
    if isinstance(fh, dict):
        parts.extend(str(v) for v in fh.get("lines", [])[:30])
    secs = (
        await session.execute(
            text("""
                SELECT ds.body
                FROM document_sections ds
                JOIN runs r ON r.id = ds.run_id AND r.status = 'ACTIVE'
                WHERE r.entity_id = :eid
                  AND ds.entity_id = :eid
                  AND ds.section_kind IN
                      ('executive_summary_scqa', 'trend_analysis',
                       'benchmark_comparison')
                ORDER BY ds.ordinal LIMIT 6
            """),
            {"eid": row.entity_id},
        )
    ).all()
    parts.extend((s.body or "")[:3000] for s in secs)
    ev = (
        await session.execute(
            text("""
                SELECT ev.e_id, ev.excerpt
                FROM evidence_index ev
                WHERE ev.entity_id = :eid
                ORDER BY ev.tier ASC, ev.created_at DESC LIMIT 10
            """),
            {"eid": row.entity_id},
        )
    ).all()
    parts.extend(f"[{e.e_id}] {e.excerpt}" for e in ev if e.excerpt)
    excerpts = "\n".join(p for p in parts if p)[:14000] or "No report excerpts available."
    # DYNAMIC gap-driven prompt (2026-07-04): enumerate ONLY the fields this
    # entity is actually missing, so the model never re-states report-owned
    # values, tokens aren't spent on known fields, and the fill-if-empty merge
    # can't be raced by hallucinated "corrections" of present data.
    firmo = (
        await session.execute(
            text("""
                SELECT f.aum_usd, f.headcount, f.hq_address,
                       f.primary_regulator,
                       f.parsed_facts ->> 'branches'     AS branches,
                       f.parsed_facts ->> 'cagr'         AS cagr,
                       f.parsed_facts ->> 'ticker'       AS ticker,
                       f.parsed_facts ->> 'founded'      AS founded,
                       f.parsed_facts ->> 'trend'        AS trend,
                       f.parsed_facts ->> 'geography'    AS geography,
                       f.parsed_facts ->> 'website'      AS website,
                       f.parsed_facts ->> 'license_type' AS license_type
                FROM entities e
                LEFT JOIN firmographics f ON f.entity_id = e.id
                WHERE e.display_id = :did
            """),
            {"did": display_id},
        )
    ).first()
    # Field set widened 2026-07-04 from the all-94 empties census: ticker
    # (62 null), hq (49), trend (33), founded (30), cagr (26), branches
    # (25), geography (15), website (4), license_type. Every value must
    # carry its verbatim source quote; the acceptor rejects any quote
    # that is not a substring of the grounding excerpts, and the model
    # is told to OMIT fields the sources do not establish (private/CU
    # entities honestly have no ticker — absence is the right answer).
    _example = {
        "total_assets": '{"value": "$X.XB", "quote": "<verbatim excerpt line>"}',
        "employees_approx": '{"value": "N", "quote": "..."}',
        "branches": '{"value": "N", "quote": "..."}',
        "hq": '{"value": "City, ST", "quote": "..."}',
        "primary_regulator": '{"value": "OCC", "quote": "..."}',
        "cagr": '{"value": "X%", "quote": "..."}',
        "ticker": '{"value": "NYSE: XYZ", "quote": "..."}',
        "founded": '{"value": "YYYY", "quote": "..."}',
        "trend": '{"value": "ACCELERATING|STABLE|DECLINING", "quote": "..."}',
        "geography": '{"value": "<footprint, e.g. Texas (7 metros)>", "quote": "..."}',
        "website": '{"value": "https://…", "quote": "..."}',
        "license_type": '{"value": "<charter/license>", "quote": "..."}',
    }
    _present = {
        "total_assets": bool(firmo and firmo.aum_usd),
        "employees_approx": bool(firmo and firmo.headcount),
        "branches": bool(firmo and firmo.branches),
        "hq": bool(firmo and firmo.hq_address),
        "primary_regulator": bool(firmo and firmo.primary_regulator),
        "cagr": bool(firmo and firmo.cagr),
        "ticker": bool(firmo and firmo.ticker),
        "founded": bool(firmo and firmo.founded),
        "trend": bool(firmo and firmo.trend),
        "geography": bool(firmo and firmo.geography),
        "website": bool(firmo and firmo.website),
        "license_type": bool(firmo and firmo.license_type),
    }
    missing = [k for k, have in _present.items() if not have] or list(_example)
    field_schema = ",\n ".join(f'"{k}": {_example[k]}' for k in missing)
    return {
        "entity_name": row.entity_name,
        "report_excerpts": excerpts,
        # mirrored so enrich_corpus._bundle_from_ctx fingerprints the REAL
        # grounding (a report change must bust the cache for this surface).
        "recent_evidence": excerpts,
        "missing_fields": ", ".join(missing),
        "field_schema": field_schema,
    }


async def _ctx_thought_leadership_extraction(
    session: AsyncSession, display_id: str
) -> dict[str, Any]:
    """Grounding for the thought-leadership extraction: the entity's own
    evidence excerpts (URL + source name inline so the model can copy
    them) plus the profile narrative. `report_excerpts` is the verbatim
    haystack the caller's substring validator checks each returned
    `excerpt` against. `recent_evidence` mirrors the same blob so the
    shared bundle/fingerprint + allowed-E-ID helpers in enrich_corpus
    see the grounding (fingerprint sensitivity + citation validation)."""
    row = (
        await session.execute(
            text("""
                SELECT e.id AS entity_id, e.name AS entity_name,
                       f.narrative_md, f.leadership
                FROM entities e
                LEFT JOIN firmographics f ON f.entity_id = e.id
                WHERE e.display_id = :did
            """),
            {"did": display_id},
        )
    ).first()
    if row is None:
        raise ValueError(f"entity not found: {display_id}")
    parts: list[str] = []
    # Roster names first — helps the model attribute authorship without
    # inventing people (authors must still appear in the excerpts).
    roster = row.leadership or []
    if isinstance(roster, list) and roster:
        names = ", ".join(
            str((p or {}).get("name") or "") for p in roster[:12]
            if isinstance(p, dict) and (p or {}).get("name")
        )
        if names:
            parts.append(f"Known leadership roster: {names}")
    if row.narrative_md:
        parts.append(str(row.narrative_md)[:3000])
    ev = (
        await session.execute(
            text("""
                SELECT ev.e_id, ev.source_name, ev.source_url,
                       ev.published_date, ev.excerpt
                FROM evidence_index ev
                WHERE ev.entity_id = :eid
                ORDER BY ev.tier ASC, ev.published_date DESC NULLS LAST
                LIMIT 24
            """),
            {"eid": row.entity_id},
        )
    ).all()
    for e in ev:
        if not e.excerpt:
            continue
        meta = " ".join(
            str(x) for x in (e.source_name, e.source_url, e.published_date) if x
        )
        parts.append(f"[{e.e_id}] ({meta}) {e.excerpt}")
    blob = "\n".join(p for p in parts if p)[:14000] \
        or "No evidence excerpts available."
    return {
        "entity_name": row.entity_name,
        "report_excerpts": blob,
        "recent_evidence": blob,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _build_context(
    session: AsyncSession, surface: str, ref: str
) -> dict[str, Any]:
    parts = ref.split(":", 1)
    if surface == "subcap_narrative":
        if len(parts) < 2:
            raise ValueError(f"subcap_narrative ref must be 'display_id:subcap_id', got {ref!r}")
        return await _ctx_subcap_narrative(session, parts[0], parts[1])
    if surface == "why_now":
        return await _ctx_why_now(session, parts[0])
    if surface == "insight_explanation":
        if len(parts) < 2:
            raise ValueError(f"insight_explanation ref must be 'display_id:card_id', got {ref!r}")
        return await _ctx_insight_explanation(session, parts[0], parts[1])
    if surface == "platform_story":
        if len(parts) < 2:
            raise ValueError(f"platform_story ref must be 'display_id:platform_id', got {ref!r}")
        return await _ctx_platform_story(session, parts[0], parts[1])
    if surface == "meeting_prep":
        return await _ctx_meeting_prep(session, parts[0])
    if surface == "firmographics_extraction":
        return await _ctx_firmographics_extraction(session, parts[0])
    if surface == "thought_leadership_extraction":
        return await _ctx_thought_leadership_extraction(session, parts[0])
    raise ValueError(f"Unknown surface: {surface!r}")


_RE_E_ID = _re.compile(r"\bE-\d+\b")


def _extract_e_ids(text: str) -> list[str]:
    return list(dict.fromkeys(_RE_E_ID.findall(text)))


class _SafeFormatMap(dict):  # type: ignore[type-arg]
    """dict subclass that returns the key wrapped in {…} for missing keys,
    so template.format_map() never raises KeyError."""
    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"
