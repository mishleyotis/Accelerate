"""Rich-context Gemini KPI enrichment for the focus-area drilldown.

When an AE drills into a focus area on the D3 heatmap, the KPI strip must show
the RIGHT metrics for THAT entity with a credible BASELINE and a TARGET to aim
for — grounded in the client's own DMA narrative. The deterministic miner
(``focus_area_synthesizer.derive_focus_area_kpis``) only scrapes disclosed
numbers, so it yields fragment labels and almost never a target. This module is
the Gemini upgrade: it hands the model a RICH per-client context and formulates a
deep, safeguarded prompt for reasoned KPIs.

The context given to Gemini (the whole system stays client-aware):
  * WHO — name, subvertical, HQ/region, size (assets), regulator;
  * WHERE THEY STAND — overall maturity + per-pillar scores, the analyst's SCQA
    narrative (the DMA thesis), and the deepest gaps;
  * THE FOCUS AREA — its title, the verbatim source quote, the capabilities it
    spans, and its pillar;
  * FINANCIALS — the trajectory line, so a target can be sized to the business.

The ask: 3-5 KPIs for THIS focus area, each with ``baseline`` (today, grounded
in a disclosed figure or an honest estimate flagged as such), ``target`` (what
they should aim for, justified by the DMA narrative + peer band), a ``rationale``
tying it to the narrative, a source, and a confidence. Safeguards are shared with
:mod:`app.services.enrichment_prompter` (recency / no-hallucination / honesty /
calibration). Baselines that are estimates rather than disclosed are marked so
the strip can badge them.

Offline-safe + DI-testable: a cold/absent Vertex client resolves to ``None`` and
the caller keeps the deterministic strip.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.enrichment_prompter import _ROLE, parse_response

_PILLAR_NAME = {
    "P1": "Strategy & Governance", "P2": "Customer Experience",
    "P3": "Operations & Process", "P4": "Data & Technology",
}


@dataclass
class KpiContext:
    """The rich, per-client context a KPI prompt is grounded in."""
    entity_name: str
    subvertical: str
    fa_id: str
    focus_title: str
    focus_quote: str = ""
    focus_pillar: str = ""
    focus_subcaps: list[str] = field(default_factory=list)
    overall_score: float | None = None
    pillar_scores: dict[str, float] = field(default_factory=dict)
    dma_narrative: str = ""          # the analyst SCQA / thesis
    deepest_gaps: list[str] = field(default_factory=list)
    financials_line: str = ""
    region: str = ""
    assets: str = ""
    regulator: str = ""
    min_kpis: int = 3
    max_kpis: int = 5


KPI_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "kpis": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "baseline": {"type": "string"},
                    "baseline_is_estimate": {"type": "boolean"},
                    "target": {"type": "string"},
                    "unit": {"type": "string"},
                    "rationale": {"type": "string"},
                    "source_url": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["label", "baseline", "target"],
            },
        },
    },
    "required": ["kpis"],
}


def _context_block(ctx: KpiContext) -> str:
    lines = [f"CLIENT: {ctx.entity_name} ({ctx.subvertical})"]
    if ctx.assets:
        lines.append(f"  size: {ctx.assets}")
    if ctx.region:
        lines.append(f"  region: {ctx.region}")
    if ctx.regulator:
        lines.append(f"  regulator: {ctx.regulator}")
    if ctx.overall_score is not None:
        lines.append(f"  overall digital maturity: {ctx.overall_score:.2f}/5")
    if ctx.pillar_scores:
        ps = ", ".join(f"{_PILLAR_NAME.get(p, p)} {s:.1f}"
                       for p, s in sorted(ctx.pillar_scores.items()))
        lines.append(f"  pillar maturity: {ps}")
    if ctx.deepest_gaps:
        lines.append(f"  deepest gaps: {'; '.join(ctx.deepest_gaps[:4])}")
    if ctx.financials_line:
        lines.append(f"  financials: {ctx.financials_line}")
    if ctx.dma_narrative:
        lines.append(f"\nDMA NARRATIVE (the analyst's thesis for this client):\n"
                     f"  {ctx.dma_narrative[:900]}")
    pillar = _PILLAR_NAME.get(ctx.focus_pillar, ctx.focus_pillar or "")
    lines.append(f"\nFOCUS AREA: {ctx.focus_title}"
                 + (f"  (pillar: {pillar})" if pillar else ""))
    if ctx.focus_quote:
        lines.append(f"  source quote: \"{ctx.focus_quote[:300]}\"")
    if ctx.focus_subcaps:
        lines.append(f"  capabilities in scope: {', '.join(ctx.focus_subcaps[:8])}")
    return "\n".join(lines)


def build_kpi_context(state: Any, focus_area: dict) -> KpiContext:
    """Assemble the rich per-client KPI context from the shared L1 ``EntityState``
    + one focus_areas row — so every KPI prompt carries the SAME client-wide
    understanding the rest of the system uses (scores, the DMA narrative, gaps,
    financials), not just the focus area in isolation."""
    caps = [c for c in state.capabilities if c.in_scope and c.score is not None]
    overall = round(sum(c.score for c in caps) / len(caps), 2) if caps else None
    pillars: dict[str, list[float]] = {}
    for c in caps:
        pillars.setdefault(c.pillar, []).append(c.score)
    pillar_scores = {p: sum(v) / len(v) for p, v in pillars.items()}
    sc = state.scqa if isinstance(state.scqa, dict) else {}
    narrative = (sc.get("answer") or sc.get("narrative")
                 or sc.get("situation") or "").strip()
    gaps, _seen_gap = [], set()
    for c in state.ranked_gaps:
        if not c.name or c.peer_median is None or c.name.lower() in _seen_gap:
            continue
        _seen_gap.add(c.name.lower())
        gaps.append(f"{c.name} {c.score:.1f} vs {c.peer_median:.1f} peer")
        if len(gaps) >= 4:
            break
    fm = state.firmographics or {}
    pf = fm.get("parsed_facts") if isinstance(fm.get("parsed_facts"), dict) else {}
    fin_lines = (fm.get("financial_highlights") or {}).get("lines") \
        if isinstance(fm.get("financial_highlights"), dict) else None
    financials = (fin_lines[0][:180] if fin_lines else "")
    aum = fm.get("aum_usd")
    assets = f"${aum / 1e9:.1f}B assets" if isinstance(aum, int | float) and aum else ""
    subs = focus_area.get("involved_subcap_ids") or []
    return KpiContext(
        entity_name=state.name, subvertical=state.subvertical or "",
        fa_id=str(focus_area.get("id") or focus_area.get("fa_id") or ""),
        focus_title=str(focus_area.get("title") or "").strip(),
        focus_quote=str(focus_area.get("verbatim_quote") or "").strip(),
        focus_pillar=(subs[0][:2] if subs else ""),
        focus_subcaps=list(subs)[:8],
        overall_score=overall, pillar_scores=pillar_scores,
        dma_narrative=narrative, deepest_gaps=gaps, financials_line=financials,
        region=str(pf.get("geography") or pf.get("footprint") or ""),
        assets=assets, regulator=str(fm.get("primary_regulator") or ""))


def build_kpi_prompt(ctx: KpiContext, prior: dict | None = None) -> str:
    """Formulate the deep, rich-context KPI prompt. A follow-up (``prior`` set)
    names why the last answer was rejected and re-asks."""
    schema = ('{"kpis": [{"label": "...", "baseline": "<today, a figure or an '
              'honest estimate>", "baseline_is_estimate": true|false, '
              '"target": "<what to aim for>", "unit": "%|days|$|ratio|score", '
              '"rationale": "<why, tied to the DMA narrative + peer band>", '
              '"source_url": "<url if the baseline is disclosed>", '
              '"confidence": <0.0-1.0>}]}')
    safeguards = (
        "SAFEGUARDS:\n"
        f"- Return {ctx.min_kpis}-{ctx.max_kpis} KPIs that DIRECTLY measure "
        "progress on THIS focus area for THIS client — not generic industry "
        "metrics.\n"
        "- BASELINE: prefer a real, recent disclosed figure for this client "
        "(cite its source_url); if none is public, give a defensible estimate "
        "from the client's size/maturity and set baseline_is_estimate=true. "
        "NEVER invent a precise disclosed number.\n"
        "- TARGET: a concrete, time-implied target justified by the DMA narrative "
        "and the relevant peer band — ambitious but credible for this client's "
        "maturity, not a generic best-in-class number.\n"
        "- RATIONALE: one sentence tying the KPI to the client's narrative/gap.\n"
        "- RECENCY: use the most recent figures; a stale/generic baseline lowers "
        "confidence.\n"
        "- NO HALLUCINATION: never fabricate a source_url or a disclosed figure.\n"
        f"Return ONLY JSON in this shape:\n{schema}")
    if prior:
        return (
            f"{_ROLE}\n\nYour previous KPI set for the focus area "
            f"'{ctx.focus_title}' ({ctx.entity_name}) was rejected: "
            f"{prior.get('_reason', 'insufficient')}. Provide a corrected set that "
            f"fixes that — every KPI needs a concrete baseline AND target.\n\n"
            f"{_context_block(ctx)}\n\n{safeguards}")
    return (
        f"{_ROLE}\n\n"
        f"TASK: define the KPIs an account team should track to move this client "
        f"forward on ONE focus area, with a baseline and a target for each.\n\n"
        f"{_context_block(ctx)}\n\n{safeguards}")


def _num(s: str) -> float | None:
    m = re.search(r"-?[\d,]+\.?\d*", str(s or ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _delta(baseline: str, target: str) -> str | None:
    """A signed %-delta baseline→target when both are comparable numbers."""
    c, t = _num(baseline), _num(target)
    if c is None or t is None or c == 0:
        return None
    pct = (t - c) / abs(c) * 100
    return f"{pct:+.0f}%"


def parse_kpis(raw: str | None, ctx: KpiContext) -> list[dict] | None:
    """Parse + validate the KPI list. Returns the accepted rows, or None when
    nothing parses (so the loop can re-ask). Each accepted row carries a clean
    label + baseline + target (+ delta/rationale/source/estimate flag)."""
    obj = parse_response(raw) if raw and '"found"' in (raw or "") else None
    if obj is None:
        try:
            s = re.sub(r"^```(?:json)?|```$", "", (raw or "").strip(),
                       flags=re.I | re.M).strip()
            start = s.find("{")
            obj = json.loads(s[start:]) if start >= 0 else None
        except (ValueError, TypeError):
            obj = None
    if not isinstance(obj, dict) or not isinstance(obj.get("kpis"), list):
        return None
    out: list[dict] = []
    seen: set[str] = set()
    for k in obj["kpis"][: ctx.max_kpis]:
        if not isinstance(k, dict):
            continue
        label = str(k.get("label", "")).strip()[:80]
        baseline = str(k.get("baseline", "")).strip()[:60]
        target = str(k.get("target", "")).strip()[:60]
        if len(label) < 3 or not baseline or not target:
            continue                       # a KPI without both anchors is dropped
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "kpi_label": label,
            "current_value": baseline,
            "target_value": target,
            "delta": _delta(baseline, target),
            "baseline_is_estimate": bool(k.get("baseline_is_estimate", True)),
            "rationale": str(k.get("rationale", "")).strip()[:300] or None,
            "source_url": str(k.get("source_url", "")).strip() or None,
            "confidence": float(k.get("confidence", 0) or 0),
        })
    return out or None


async def enrich_focus_kpis(
    ctx: KpiContext, *, client: Any, model: str = "flash", max_rounds: int = 2,
) -> list[dict] | None:
    """Acquire reasoned KPIs for one focus area. Iterates a follow-up when the
    model returns too few / malformed KPIs. Offline/cold/erroring → None."""
    if client is None:
        return None
    prior: dict | None = None
    for _ in range(max_rounds):
        try:
            from app.services.vertex_client import GeminiCall
            chunks: list[str] = []
            async for part in client.stream(GeminiCall(
                    surface="focus_kpi_enrichment", model=model,
                    prompt=build_kpi_prompt(ctx, prior),
                    response_schema=KPI_SCHEMA, max_output_tokens=1536)):
                chunks.append(part)
            raw = "".join(chunks)
        except Exception:
            return None
        kpis = parse_kpis(raw, ctx)
        if kpis and len(kpis) >= ctx.min_kpis:
            return kpis
        prior = {"_reason": (f"only {len(kpis or [])} valid KPIs "
                             f"(need >= {ctx.min_kpis}); each needs baseline AND target")}
    return kpis if (kpis := parse_kpis(raw, ctx)) else None


_KPI_056: bool | None = None


async def _kpi_has_056_columns(session: AsyncSession) -> bool:
    """Schema probe, cached per process: migration 056 adds
    evidence_e_ids/rationale to focus_area_kpi_overrides. A probe beats
    try/except here — a failed INSERT aborts the surrounding
    transaction."""
    global _KPI_056
    if _KPI_056 is None:
        _KPI_056 = bool((await session.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='focus_area_kpi_overrides' "
            "AND column_name='evidence_e_ids'"))).first())
    return _KPI_056


async def persist_focus_kpis(
    session: AsyncSession, *, entity_id: str, run_id: str, fa_id: str,
    kpis: list[dict], catalogue_version: str = "v7.0",
) -> int:
    """Write reasoned KPIs to focus_area_kpi_overrides (source_mode='public'),
    replacing the low-quality deterministic 'public' rows for this FA, plus a
    citable evidence_index row per sourced KPI. Returns the count written."""
    if not kpis:
        return 0
    # focus_area_kpi_overrides keys on the 32-char dashless-hex form of the
    # focus_areas UUID (the endpoint groups kpis_by_fa on it). source_mode is
    # constrained to public|client|hidden — Gemini KPIs are public-sourced, so
    # they REPLACE the low-quality deterministic 'public' rows for this FA (the
    # intended upgrade) while AE-entered 'client'/'hidden' rows are preserved.
    fa_key = fa_id.replace("-", "")[:32]
    await session.execute(text(
        "DELETE FROM focus_area_kpi_overrides "
        "WHERE fa_id = :fa AND source_mode = 'public'"), {"fa": fa_key})
    written = 0
    for i, k in enumerate(kpis):
        # a deterministically-mined KPI cites the run's OWN evidence row
        # it was extracted from (no synthetic E-GK row needed)
        e_id = k.get("evidence_e_id") or None
        if not e_id and k.get("source_url") and not k.get("baseline_is_estimate"):
            # evidence_index.e_id is varchar(16): "E-GK-" + 8-hex of (fa_id, i).
            e_id = "E-GK-" + hashlib.sha1(
                f"{fa_id}-{i}".encode()).hexdigest()[:8]
            from app.services.enrichment_quality import vet_text
            quote = vet_text(
                f"{k['kpi_label']}: baseline {k['current_value']} → "
                f"target {k['target_value']}. {k.get('rationale') or ''}")[0][:1000]
            chash = hashlib.sha256(f"{e_id}|{quote[:500]}".encode()).hexdigest()
            await session.execute(text("""
                INSERT INTO evidence_index (run_id, entity_id, e_id, tier, excerpt,
                    source_name, source_url, claim_type, linked_subcap_ids,
                    content_hash, created_at)
                VALUES (CAST(:rid AS uuid), CAST(:eid AS uuid), :e, 4, :exc,
                    'Gemini KPI enrichment', :su, 'ai_enrichment', '{}',
                    :ch, NOW())
                ON CONFLICT (run_id, e_id) DO UPDATE SET excerpt = EXCLUDED.excerpt,
                    source_url = EXCLUDED.source_url
            """), {"rid": run_id, "eid": entity_id, "e": e_id, "exc": quote,
                   "su": k["source_url"], "ch": chash})
        _params = {"eid": entity_id, "fa": fa_key, "label": k["kpi_label"],
                   "cur": k["current_value"], "tgt": k["target_value"],
                   "delta": k.get("delta"), "e": [e_id] if e_id else [],
                   "rat": (k.get("rationale") or None)}
        if await _kpi_has_056_columns(session):
            await session.execute(text("""
                INSERT INTO focus_area_kpi_overrides (entity_id, fa_id,
                    kpi_label, source_mode, current_value, target_value,
                    delta, evidence_e_ids, rationale, updated_at)
                VALUES (CAST(:eid AS uuid), :fa, :label, 'public', :cur,
                    :tgt, :delta, CAST(:e AS text[]), :rat, NOW())
            """), _params)
        else:
            await session.execute(text("""
                INSERT INTO focus_area_kpi_overrides (entity_id, fa_id,
                    kpi_label, source_mode, current_value, target_value,
                    delta, updated_at)
                VALUES (CAST(:eid AS uuid), :fa, :label, 'public', :cur,
                    :tgt, :delta, NOW())
            """), {k2: v for k2, v in _params.items()
                   if k2 not in ("e", "rat")})
        written += 1
    _ = catalogue_version
    return written
