"""Warm + persist the Gemini synthesis cache for the whole corpus.

The deploy-phase half of the synthesis contract (master plan Part 8):
a freshly deployed build serves a COLD ``vertex_synthesis_cache`` —
every synthesis-eligible block lazily renders PENDING until an AE
first opens it. This script walks ``eligible entities x synthesis
surfaces`` and, for each cache miss, calls Vertex ONCE, validates the
output's citations against the supplied grounding bundle, and persists
the row — so the first AE click after a deploy is a 0-token cache hit.

Surfaces warmed (per-entity):
  - ``why_now``          (1 call)   — grounded on the run's evidence
  - ``platform_story``   (≤5 calls) — one per scored platform, grounded
                                      on the gap subcaps' evidence
  - ``firmographics_extraction``     (≤1 call, gap entities only) —
                                      STRICT-JSON gap fill, verbatim-
                                      quote validated per field
  - ``thought_leadership_extraction`` (≤1 call, empty-panel entities
                                      only) — STRICT-JSON item array,
                                      verbatim-excerpt validated per
                                      item; persists into
                                      ``firmographics.thought_leadership``

(The intelligence summary is owned by the intelligence_recompute
worker; subcap narratives are persisted at ingest; insight/RAG answers
are interactive-only by design.)

Honest-cold behaviour: when Vertex is unreachable (no creds — local
sandboxes, CI), NOTHING is persisted. The script reports the would-call
matrix and exits 0; pages keep their honest PENDING states. We never
cache the offline placeholder string as if it were synthesis.

Validator gate: any E-ID in the output that is NOT in the grounding
bundle marks the row ``validators_passed=False`` and the row is NOT
persisted (fail-closed; the lazy path will retry with the same
guardrails).

Cost controls: ``--max-calls`` hard ceiling (default 600 ~= 101 entities
x 6 surfaces), ``--dry-run`` reports the gate matrix with zero Vertex
calls, ``--surfaces`` / ``--limit`` scope the sweep.

RESILIENT EXECUTION (2026-07-05, services.enrichment_runner): the sweep
runs BOUNDED-PARALLEL (``--concurrency`` / $DMA_ENRICH_CONCURRENCY
workers, each with its own session; Vertex streams drained in
abandonable daemon threads) under a WALL-CLOCK BUDGET (``--budget-sec``
/ $DMA_ENRICH_BUDGET_SEC, default 1200s — sized under the derive
chain's 1500s step timeout). At budget it stops scheduling, drains
in-flight work and exits 0 with a ``remaining=N`` count: nothing is
lost, because every synthesized row persists immediately and the cache
fingerprint makes the NEXT invocation fast-skip done work — chain wave
→ explicit warm step → post-deploy refresh CONVERGE on full warmth.
Work runs in visibility tiers (why_now → gap fills → top-2
platform_story → ranks 3-5) so a budget cut lands on the least visible
surfaces. Self-healing: per-surface breakers (4 consecutive failures
stop that surface only) + a global cold-stop on auth-class errors.
The 2026-07-05 a52f723 build showed why: the sequential unbudgeted
sweep ate its 1500s step timeout twice and then ran the build into
Cloud Build's global deadline.

Usage:
  export DATABASE_URL=postgresql+asyncpg://...   (context queries)
  export DATABASE_URL_SYNC=postgresql://...      (cache writes)
  python -m app.scripts.enrich_corpus --dry-run
  python -m app.scripts.enrich_corpus --surfaces why_now --limit 5
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.services import intelligence_builder as ib
from app.services import synthesis_cache_db as cache_db
from app.services.enrichment_runner import (
    BudgetedEnrichmentRunner,
    EnrichItem,
    VertexGateway,
    env_int,
)
from app.services.enrichment_triggers import Trigger
from app.services.synthesis_orchestrator import (
    DecisionGate,
    SynthesisRequest,
    decide_synthesis_path,
)
from app.services.vertex_client import (
    GeminiCall,
    get_vertex_client,
    resolve_model_id,
)


def _tpl_version(surface: str) -> str:
    """Prompt version derived from the LIVE template text — editing a
    template in intelligence_builder auto-busts every cached fingerprint
    for that surface (the hardcoded "v1" never did; audit 2026-07-04)."""
    import hashlib
    tpl = str(ib._TEMPLATES.get(surface, {}).get("template", ""))
    return "v1-" + hashlib.sha256(tpl.encode()).hexdigest()[:10]

_E_ID_RE = re.compile(r"\bE-\d{1,4}\b")

# Mirrors the per-surface model choice in intelligence_builder._TEMPLATES.
_SURFACE_MODEL = {
    "why_now": "flash",
    "platform_story": "pro",
    # Clay is NOT in prod (2026-06-10): firmographics gaps the client
    # research/profile reports did not state explicitly are filled by
    # Gemini, grounded on the entity's own excerpts with a per-field
    # verbatim-quote check.
    "firmographics_extraction": "flash",
    # Un-deads the D1 ThoughtLeadershipPanel: structured item array,
    # verbatim-excerpt validated (same anti-fabrication contract).
    "thought_leadership_extraction": "flash",
    # Outlier-confirm rung for the financial trajectory (user mandate:
    # "unusual outliers should be flagged and even confirmed using
    # Gemini"): every anomaly build_trajectory dropped/flagged gets a
    # keep/drop/rescale verdict grounded on the entity's own evidence.
    # Validator-gated (quote-verbatim + arithmetic-bounded values); cold
    # Vertex leaves the deterministic honest gap untouched.
    "financial_series_confirm": "flash",
}

# Surface registration (2026-07-06 wave 2): the confirm rung's template
# registers into intelligence_builder._TEMPLATES from HERE — enrich_corpus
# owns the surface end-to-end (context builder, acceptor, persistence
# below), and _tpl_version/fingerprinting read the shared registry so the
# cache-bust contract is identical to every other surface.
ib._TEMPLATES.setdefault("financial_series_confirm", {
    "model": "flash",
    "template": (
        "You are a precise financial-data auditor for Zennify. The multi-"
        "year series below for {entity_name} carries FLAGGED outlier "
        "points the deterministic guard could not confirm. For EACH "
        "flagged point decide, using ONLY the evidence excerpts, whether "
        "the value is genuine (keep), a pure unit mistake (rescale x1000 "
        "or /1000), or unsupported (drop).\n\n"
        "Entity scale context: {scale_context}\n"
        "Charted series (post-guard): {series_json}\n"
        "Flagged points:\n{anomalies_json}\n\n"
        "Evidence excerpts (the ONLY admissible support):\n"
        "{report_excerpts}\n\n"
        "Output a STRICT JSON array (no prose, no markdown fences), one "
        "element per flagged point:\n"
        "[{{\"metric\": \"total_assets|net_income_m\", \"fy\": 2024,\n"
        "  \"verdict\": \"keep|drop|rescale\", \"value\": <number or null>,\n"
        "  \"quote\": \"<verbatim substring copied from the excerpts>\",\n"
        "  \"reason\": \"<one sentence>\"}}]\n"
        "Rules: `keep` and `rescale` REQUIRE a verbatim quote stating the "
        "figure; a `rescale` value MUST be the flagged value x1000 or "
        "/1000, a `keep` value MUST equal the flagged value; when the "
        "excerpts do not establish the figure, the verdict is `drop`."
    ),
})

# Every warmable surface — `--surfaces all` expands to this (the
# cloudbuild regen step + post-deploy refresh run the full set).
_ALL_SURFACES = ",".join(_SURFACE_MODEL)


def _provenance_json(surface: str) -> dict:
    """The provenance payload stamped into every cache row this script
    writes (`vertex_synthesis_cache.output_json`). The read path
    (routers/entities overview merge) and the deploy assertions
    (qa_gemini_surfaces) both key off `source == "vertex"` +
    `model_id` + `synthesized_at`."""
    from datetime import UTC, datetime

    return {
        "source": "vertex",
        "model_id": resolve_model_id(_SURFACE_MODEL[surface]),
        "synthesized_at": datetime.now(UTC).isoformat(),
        "generator": "app.scripts.enrich_corpus",
    }


def _bundle_from_ctx(ctx: dict) -> list[dict]:
    """Grounding bundle = the evidence lines the prompt was given.
    Order is part of the fingerprint (rerank visibility)."""
    blob = str(ctx.get("recent_evidence") or ctx.get("gap_evidence") or "")
    return [{"line": ln} for ln in blob.splitlines() if ln.strip()]


def _allowed_e_ids(ctx: dict) -> set[str]:
    """Every E-ID the rendered prompt context carries — ALL ctx fields, not
    just the evidence bundle. The why_now / platform_story prompts also embed
    the run's why-now signals and SCQA situation, whose inline citations are
    REAL, DB-derived E-IDs for this entity; treating those as fabricated
    blocked 219/273 sweep outputs as false positives (2026-07-06 audit). The
    anti-hallucination property is unchanged: an id the model was never shown
    anywhere in the prompt still blocks."""
    blob = " ".join(str(v) for v in ctx.values() if v is not None)
    return set(_E_ID_RE.findall(blob))


_STORY_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
_STORY_GROUND_KEYS = (
    "fit_score", "readiness_line", "top_gaps", "current_stack",
    "prereq_lines", "gap_evidence", "scqa_situation",
)


def _accept_platform_story(out_text: str, ctx: dict) -> bool:
    """platform_story anti-fabrication (platform v3): beyond the E-ID
    whitelist, EVERY number the model emits must appear in the grounding
    (the fit score, the score-vs-peer figures, the prereq thresholds, the
    evidence lines) — a Gemini-invented dollar figure, user count, or year
    that isn't in the dossier inputs blocks the row (deterministic floor
    stands). Section numbers 1-3 are structural, not claims."""
    grounding = " ".join(str(ctx.get(k) or "") for k in _STORY_GROUND_KEYS)
    ground_nums = set(_STORY_NUM_RE.findall(grounding))
    ground_ints = {n.split(".")[0] for n in ground_nums}
    for n in _STORY_NUM_RE.findall(out_text or ""):
        if n in ground_nums or n in ("1", "2", "3"):
            continue
        # tolerate integer/decimal mismatch ('3' grounding ↔ '3.0' output)
        if n.split(".")[0] in ground_ints:
            continue
        return False
    return True


# Widened 2026-07-04 from the all-94 empties census (ticker 62 null,
# hq 49, trend 33, founded 30, cagr 26, branches 25, geography 15,
# website 4, license_type). Every fill is verbatim-quote validated;
# absence in the sources stays honest-null.
_FIRMO_GAP_FIELDS = (
    "total_assets", "employees_approx", "branches", "hq",
    "primary_regulator", "cagr", "ticker", "founded", "trend",
    "geography", "website", "license_type",
)


async def _firmo_missing_fields(session, display_id: str) -> list[str]:
    """Fields the report-derived ingest left empty for this entity —
    the ONLY ones the Gemini extractor is allowed to fill."""
    row = (
        await session.execute(text(
            """
            SELECT f.hq_address, f.primary_regulator, f.aum_usd,
                   f.headcount, f.parsed_facts
            FROM entities e
            LEFT JOIN firmographics f ON f.entity_id = e.id
            WHERE e.display_id = :did
            """), {"did": display_id})
    ).first()
    pf = (row.parsed_facts if row else None) or {}
    # Real columns count as present too (frost has aum_usd/headcount as
    # columns with no parsed_facts twin — asking Gemini to re-derive a
    # known value is wasted tokens and a hallucination surface).
    _col_for = {
        "hq": "hq_address", "primary_regulator": "primary_regulator",
        "total_assets": "aum_usd", "employees_approx": "headcount",
    }
    missing = []
    for field in _FIRMO_GAP_FIELDS:
        col = _col_for.get(field)
        col_val = getattr(row, col) if (row is not None and col) else None
        pf_val = pf.get(field)
        has_pf = bool(str(pf_val).strip()) if pf_val is not None else False
        if not col_val and not has_pf:
            missing.append(field)
    return missing


def _accept_firmo_fields(out_text: str, excerpts: str) -> dict[str, str]:
    """Parse the extractor's STRICT JSON and keep only fields whose
    `quote` is a VERBATIM substring of the grounding excerpts (after
    whitespace normalization) — the anti-fabrication contract for
    structured fields, mirroring the E-ID validator for prose."""
    import json as _json

    def _norm(t: str) -> str:
        return re.sub(r"\s+", " ", t or "").strip().lower()

    raw = out_text.strip()
    # tolerate ```json fences despite the prompt forbidding them
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    try:
        data = _json.loads(raw)
    except (ValueError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    hay = _norm(excerpts)
    accepted: dict[str, str] = {}
    for field in _FIRMO_GAP_FIELDS:
        item = data.get(field)
        if not isinstance(item, dict):
            continue
        value = str(item.get("value") or "").strip()
        quote = _norm(str(item.get("quote") or ""))
        if value and quote and len(quote) >= 8 and quote in hay:
            accepted[field] = value[:120]
    return accepted


_TL_TYPES = {
    "linkedin_post", "article", "podcast", "conference", "blog",
    "interview",
}


def _accept_tl_items(out_text: str, excerpts: str) -> list[dict[str, str | None]]:
    """Parse the thought-leadership extractor's STRICT JSON array and
    keep only items whose `excerpt` is a VERBATIM substring of the
    grounding excerpts (after whitespace normalization) — the same
    anti-fabrication contract `_accept_firmo_fields` enforces per
    field. Malformed output → [] (fail-closed, nothing persisted)."""
    import json as _json

    def _norm(t: str) -> str:
        return re.sub(r"\s+", " ", t or "").strip().lower()

    raw = out_text.strip()
    # tolerate ```json fences despite the prompt forbidding them
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    try:
        data = _json.loads(raw)
    except (ValueError, TypeError):
        return []
    if isinstance(data, dict):  # tolerate {"items": [...]} wrappers
        data = data.get("items")
    if not isinstance(data, list):
        return []
    hay = _norm(excerpts)
    accepted: list[dict[str, str | None]] = []
    for item in data[:12]:
        if not isinstance(item, dict):
            continue
        excerpt = str(item.get("excerpt") or "").strip()
        title = str(item.get("title") or "").strip()
        if not title or len(_norm(excerpt)) < 8 or _norm(excerpt) not in hay:
            continue
        tl_type = str(item.get("type") or "").strip().lower()
        accepted.append({
            "type": tl_type if tl_type in _TL_TYPES else "article",
            "date": (str(item["date"])[:10]
                     if item.get("date") not in (None, "", "null") else None),
            "title": title[:160],
            "excerpt": excerpt[:400],
            "author": (str(item["author"]).strip()[:80]
                       if item.get("author") not in (None, "", "null") else None),
            "url": (str(item["url"]).strip()[:500]
                    if item.get("url") not in (None, "", "null") else None),
        })
    return accepted


async def _tl_panel_empty(session, display_id: str) -> bool:
    """True when the entity's thought_leadership panel has nothing to
    render — the ONLY case the Gemini extractor is allowed to fill
    (report/Clay-derived values always win, mirroring the
    firmographics gap-fill contract)."""
    row = (
        await session.execute(text(
            """
            SELECT f.thought_leadership AS tl
            FROM entities e
            LEFT JOIN firmographics f ON f.entity_id = e.id
            WHERE e.display_id = :did
            """), {"did": display_id})
    ).first()
    tl = row.tl if row is not None else None
    if tl is None:
        return True
    if isinstance(tl, list | dict):
        return len(tl) == 0
    return not str(tl).strip()


def _unconfirmed_anomalies(fh: object) -> list[dict]:
    """The trajectory anomaly_details entries still awaiting a Gemini
    verdict. Horizon drops (basis assessment_horizon) are POLICY, not data
    doubt — they are never sent for confirmation."""
    traj = fh.get("trajectory") if isinstance(fh, dict) else None
    details = traj.get("anomaly_details") if isinstance(traj, dict) else None
    if not isinstance(details, list):
        return []
    return [d for d in details
            if isinstance(d, dict) and not d.get("verdict")
            and d.get("basis") != "assessment_horizon"]


async def _fh_for_entity(session, display_id: str) -> dict:
    row = (
        await session.execute(text(
            """
            SELECT f.financial_highlights AS fh
            FROM entities e
            LEFT JOIN firmographics f ON f.entity_id = e.id
            WHERE e.display_id = :did
            """), {"did": display_id})
    ).first()
    fh = row.fh if row is not None else None
    return fh if isinstance(fh, dict) else {}


async def _ctx_financial_series_confirm(session, display_id: str) -> dict:
    """Grounding for the outlier-confirm rung: the flagged anomaly entries
    + the post-guard series + the entity's scale context + the evidence
    excerpts that mention financial figures. `report_excerpts` is the
    verbatim haystack the acceptor checks each returned quote against;
    `recent_evidence` mirrors the FULL grounding (anomalies included) so
    the cache fingerprint re-fires when either the series or the evidence
    changes."""
    import json as _json
    row = (
        await session.execute(text(
            """
            SELECT e.id AS entity_id, e.name AS entity_name,
                   f.financial_highlights AS fh, f.aum_usd, f.headcount,
                   f.parsed_facts ->> 'size_tier' AS size_tier
            FROM entities e
            LEFT JOIN firmographics f ON f.entity_id = e.id
            WHERE e.display_id = :did
            """), {"did": display_id})
    ).first()
    if row is None:
        raise ValueError(f"entity not found: {display_id}")
    fh = row.fh if isinstance(row.fh, dict) else {}
    traj = fh.get("trajectory") if isinstance(fh.get("trajectory"), dict) else {}
    anomalies = _unconfirmed_anomalies(fh)
    ev = (
        await session.execute(text(
            """
            SELECT ev.e_id, ev.excerpt
            FROM evidence_index ev
            WHERE ev.entity_id = :eid AND ev.excerpt IS NOT NULL
              AND ev.excerpt ~* '(total assets|net income|\\$|billion|million|NCUA|10-K|call report)'
            ORDER BY ev.tier ASC, ev.created_at DESC LIMIT 24
            """), {"eid": row.entity_id})
    ).all()
    parts = [f"[{e.e_id}] {e.excerpt}" for e in ev if e.excerpt]
    if isinstance(fh.get("lines"), list):
        parts.extend(str(x) for x in fh["lines"][:20])
    excerpts = "\n".join(parts)[:14000] or "No evidence excerpts available."
    scale_bits = []
    if row.aum_usd:
        scale_bits.append(f"total assets/AUM ${float(row.aum_usd) / 1e9:.2f}B")
    if row.size_tier:
        scale_bits.append(f"size tier {row.size_tier}")
    if row.headcount:
        scale_bits.append(f"{row.headcount} employees")
    series_json = _json.dumps(
        {"fy": traj.get("fy"), "series": traj.get("series"),
         "unit_convention": "total_assets in $B, net_income_m in $M"})
    anomalies_json = _json.dumps(anomalies, ensure_ascii=False)
    blob = f"{anomalies_json}\n{series_json}\n{excerpts}"
    return {
        "entity_name": row.entity_name,
        "scale_context": "; ".join(scale_bits) or "not on record",
        "series_json": series_json,
        "anomalies_json": anomalies_json,
        "report_excerpts": excerpts,
        # full grounding mirrored → fingerprint sensitivity + E-ID gating
        "recent_evidence": blob,
    }


def _accept_series_verdicts(
    out_text: str, excerpts: str, details: list[dict],
) -> list[dict]:
    """Parse the confirm rung's STRICT JSON and keep only verdicts that are
    (a) about a flagged anomaly, (b) arithmetically bounded — `keep` must
    restate the flagged value, `rescale` must be exactly x1000 or /1000 —
    and (c) for keep/rescale, backed by a verbatim quote from the grounding
    excerpts. Anything else is dropped (fail-closed: the deterministic
    honest gap stands). Mirrors _accept_firmo_fields' contract."""
    import json as _json

    def _norm(t: str) -> str:
        return re.sub(r"\s+", " ", t or "").strip().lower()

    raw = out_text.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    try:
        data = _json.loads(raw)
    except (ValueError, TypeError):
        return []
    if isinstance(data, dict):    # tolerate {"verdicts": [...]} wrappers
        data = data.get("verdicts")
    if not isinstance(data, list):
        return []
    by_key = {(str(d.get("metric")), d.get("fy")): d
              for d in details if isinstance(d, dict)}
    hay = _norm(excerpts)
    accepted: list[dict] = []
    seen: set[tuple[str, object]] = set()
    for item in data[:16]:
        if not isinstance(item, dict):
            continue
        try:
            key = (str(item.get("metric")), int(item.get("fy")))
        except (TypeError, ValueError):
            continue
        cand = by_key.get(key)
        verdict = str(item.get("verdict") or "").strip().lower()
        if cand is None or key in seen or verdict not in ("keep", "drop", "rescale"):
            continue
        reason = str(item.get("reason") or "").strip()
        if verdict == "drop":
            if not reason:
                continue
            accepted.append({"metric": key[0], "fy": key[1],
                             "verdict": "drop", "reason": reason[:240]})
            seen.add(key)
            continue
        try:
            value = float(item.get("value"))
            flagged = float(cand.get("value"))
        except (TypeError, ValueError):
            continue
        quote = _norm(str(item.get("quote") or ""))
        if len(quote) < 8 or quote not in hay:
            continue
        if verdict == "keep" and abs(value - flagged) > 0.01 * max(abs(flagged), 1e-9):
            continue
        if verdict == "rescale" and not any(
                abs(value - flagged * f) <= 0.01 * abs(flagged * f)
                for f in (1000.0, 0.001)):
            continue
        accepted.append({"metric": key[0], "fy": key[1], "verdict": verdict,
                         "value": value, "reason": reason[:240]})
        seen.add(key)
    return accepted


async def _refs_for_entity(session, display_id: str) -> list[tuple[str, str, int]]:
    """(surface, ref, tier) triples to warm for one entity. Tiers order
    the budgeted sweep so a budget cut lands on the LEAST visible work:
      0  why_now                 (the D1 strip — most visible surface)
      1  firmographics / thought-leadership gap fills + financial-series
         outlier confirms (D1 panels + trajectory accuracy)
      2  platform_story for the entity's top-2 platforms (what
         qa_gemini_surfaces samples)
      3  platform_story ranks 3-5
    """
    out: list[tuple[str, str, int]] = [("why_now", display_id, 0)]
    if await _firmo_missing_fields(session, display_id):
        out.append(("firmographics_extraction", display_id, 1))
    # trajectory anomalies awaiting a keep/drop/rescale verdict — the
    # confirm rung fires once per entity and the verdict stamps make the
    # next sweep fast-skip it (fill-if-empty idempotence).
    if _unconfirmed_anomalies(await _fh_for_entity(session, display_id)):
        out.append(("financial_series_confirm", display_id, 1))
    # thought_leadership is STRICTLY a Clay-enrichment surface (operator
    # mandate 2026-07-06): the panel stays EMPTY until the Clay connector
    # webhook syncs it — NO Gemini gap-fill. The extraction surface handler
    # below is retained but never dispatched, so a Clay-less entity's panel
    # is honestly empty rather than filled with mis-typed evidence.
    rows = (
        await session.execute(text(
            """
            SELECT ps.platform_id
            FROM platform_scores ps
            JOIN runs r ON r.id = ps.run_id AND r.status = 'ACTIVE'
            JOIN entities e ON e.id = r.entity_id
            WHERE e.display_id = :did
            ORDER BY ps.fit_score DESC NULLS LAST
            LIMIT 5
            """), {"did": display_id})
    ).all()
    out.extend(
        ("platform_story", f"{display_id}:{r.platform_id}", 2 if i < 2 else 3)
        for i, r in enumerate(rows)
    )
    return out


async def _process_ref(session, gateway: VertexGateway, surface: str,
                       ref: str, args: argparse.Namespace) -> str:
    """One enrichment unit: context → cache decision → Vertex → validate
    → persist. Returns the outcome label the runner counts. Raises
    gateway errors (cold/breaker/ceiling/timeout) for runner counting."""
    try:
        # financial_series_confirm is registered from THIS module (its
        # template lives in ib._TEMPLATES like every surface, but the
        # context builder is local) — everything else dispatches through
        # the shared intelligence_builder registry.
        if surface == "financial_series_confirm":
            ctx = await _ctx_financial_series_confirm(session, ref)
        else:
            ctx = await ib._build_context(session, surface, ref)
    except Exception as exc:  # context is best-effort per ref
        await session.rollback()  # clear aborted txn state
        if args.verbose:
            print(f"  ctx-err {surface}:{ref}: {exc}")
        return "context_error"

    bundle = _bundle_from_ctx(ctx)
    req = SynthesisRequest(
        target_kind="entity",
        target_id=ref,
        surface=surface,
        prompt_template_version=_tpl_version(surface),
        grounding_bundle=bundle,
        catalogue_version="v7.0",
        page_context={"route": f"enrich:{surface}"},
    )
    # decide_synthesis_path does one SYNC cache lookup — off the loop so
    # concurrent workers aren't serialized behind each other's I/O.
    decision = await asyncio.to_thread(
        decide_synthesis_path, req,
        lookup_existing=lambda tk, tid, sf, fp:
            cache_db.safe_fetch_active(tk, tid, sf, fp),
    )
    if decision.gate == DecisionGate.CACHE_HIT_FRESH:
        return "hit"
    if args.dry_run:
        return "miss"

    prompt = ib._TEMPLATES[surface]["template"].format_map(
        ib._SafeFormatMap(ctx))
    t0 = time.monotonic()
    out_text = (await gateway.generate(surface, GeminiCall(
        surface=surface, model=_SURFACE_MODEL[surface],
        prompt=prompt, temperature=0.2, max_output_tokens=1024,
    ))).strip()

    cited = sorted(set(_E_ID_RE.findall(out_text)))
    fabricated = [e for e in cited if e not in _allowed_e_ids(ctx)]
    if not out_text or fabricated:
        if args.verbose:
            print(f"  blocked {surface}:{ref} fabricated={fabricated}")
        return "validator_blocked"

    # platform_story: also gate every number against the grounding (a
    # fabricated figure that cites a real E-ID would slip the whitelist).
    if surface == "platform_story" and not _accept_platform_story(out_text, ctx):
        if args.verbose:
            print(f"  blocked platform_story:{ref} ungrounded number")
        return "validator_blocked"

    # firmographics_extraction: parse the STRICT JSON, accept ONLY fields
    # whose verbatim quote appears in the grounding excerpts, and merge
    # into firmographics.parsed_facts (missing keys only — the report-
    # derived ingest values always win). Clay is NOT in prod; this is the
    # Gemini-first gap fill.
    if surface == "firmographics_extraction":
        accepted = _accept_firmo_fields(
            out_text, str(ctx.get("report_excerpts") or ""),
        )
        missing = await _firmo_missing_fields(session, ref)
        accepted = {k: v for k, v in accepted.items() if k in missing}
        if not accepted:
            if args.verbose:
                print(f"  blocked firmo {ref}: no grounded fields")
            return "validator_blocked"
        import json as _json
        # Merge (not overwrite) the _gemini_extracted marker —
        # thought_leadership_extraction shares it.
        pf_row = (
            await session.execute(text(
                """
                SELECT f.parsed_facts FROM firmographics f
                JOIN entities e ON e.id = f.entity_id
                WHERE e.display_id = :did
                """), {"did": ref})
        ).first()
        prior = ((pf_row.parsed_facts if pf_row else None) or {})
        marker = sorted({
            *(prior.get("_gemini_extracted") or []), *accepted,
        })
        await session.execute(text(
            """
            UPDATE firmographics f SET
                parsed_facts = COALESCE(f.parsed_facts, '{}'::jsonb)
                               || CAST(:pf AS JSONB),
                updated_at = NOW()
            FROM entities e
            WHERE e.id = f.entity_id AND e.display_id = :did
            """),
            {"did": ref, "pf": _json.dumps({
                **accepted,
                "_gemini_extracted": marker,
                "_fx_provenance": _provenance_json(surface),
            })},
        )
        await session.commit()

    # financial_series_confirm: parse the STRICT JSON verdicts, accept only
    # anomaly-matched + arithmetic-bounded + quote-verbatim ones, and fold
    # them into fh.trajectory via derive_financials.apply_series_verdicts
    # (keep/rescale reinstate the confirmed point; drop keeps the honest
    # gap, now with a cited reason). Idempotent: stamped verdicts make the
    # entity ineligible on the next sweep.
    output_json = _provenance_json(surface)
    if surface == "financial_series_confirm":
        import json as _json

        from app.scripts.derive_financials import apply_series_verdicts
        fh = await _fh_for_entity(session, ref)
        details = _unconfirmed_anomalies(fh)
        accepted = _accept_series_verdicts(
            out_text, str(ctx.get("report_excerpts") or ""), details)
        if not accepted or not apply_series_verdicts(fh, accepted):
            if args.verbose:
                print(f"  blocked series-confirm {ref}: no grounded verdicts")
            return "validator_blocked"
        await session.execute(text(
            """
            UPDATE firmographics f SET
                financial_highlights =
                    COALESCE(f.financial_highlights, '{}'::jsonb)
                    || CAST(:patch AS JSONB),
                updated_at = NOW()
            FROM entities e
            WHERE e.id = f.entity_id AND e.display_id = :did
            """),
            {"did": ref, "patch": _json.dumps({
                "trajectory": fh.get("trajectory"),
                "_series_confirm_provenance": output_json,
            })},
        )
        await session.commit()
        output_json = {**output_json, "verdicts": accepted}

    # thought_leadership_extraction: parse the STRICT JSON array, accept
    # ONLY items whose verbatim excerpt appears in the grounding blob,
    # and fill firmographics.thought_leadership IF EMPTY (report/Clay
    # values always win). parsed_facts._gemini_extracted is re-read +
    # merged (not blind-overwritten) so the firmographics_extraction
    # marker written above survives.
    if surface == "thought_leadership_extraction":
        items = _accept_tl_items(
            out_text, str(ctx.get("report_excerpts") or ""),
        )
        if not items or not await _tl_panel_empty(session, ref):
            if args.verbose:
                print(f"  blocked tl {ref}: no grounded items")
            return "validator_blocked"
        import json as _json
        pf_row = (
            await session.execute(text(
                """
                SELECT f.parsed_facts FROM firmographics f
                JOIN entities e ON e.id = f.entity_id
                WHERE e.display_id = :did
                """), {"did": ref})
        ).first()
        prior = ((pf_row.parsed_facts if pf_row else None) or {})
        marker = sorted({
            *(prior.get("_gemini_extracted") or []),
            "thought_leadership",
        })
        await session.execute(text(
            """
            UPDATE firmographics f SET
                thought_leadership = CAST(:tl AS JSONB),
                parsed_facts = COALESCE(f.parsed_facts, '{}'::jsonb)
                               || CAST(:pf AS JSONB),
                updated_at = NOW()
            FROM entities e
            WHERE e.id = f.entity_id AND e.display_id = :did
            """),
            {"did": ref, "tl": _json.dumps(items),
             "pf": _json.dumps({
                 "_gemini_extracted": marker,
                 "_tl_provenance": output_json,
             })},
        )
        await session.commit()
        output_json = {**output_json, "items": items}

    await asyncio.to_thread(
        cache_db.safe_insert_or_supersede,
        target_kind="entity", target_id=ref, surface=surface,
        model=_SURFACE_MODEL[surface],
        input_fingerprint=decision.fingerprint,
        prompt_template_version=_tpl_version(surface),
        grounding_bundle_hash=decision.fingerprint[:32],
        catalogue_version="v7.0",
        output_text=out_text,
        output_json=output_json,
        cited_evidence_ids=cited,
        validators_passed=True,
        confidence=0.8,
        latency_ms=int((time.monotonic() - t0) * 1000),
    )
    return "synthesized"


async def main_async(args: argparse.Namespace) -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL not set", file=sys.stderr)
        return 2
    engine = create_async_engine(
        dsn, pool_pre_ping=True,
        pool_size=max(2, args.concurrency), max_overflow=4)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    raw_surfaces = args.surfaces or "why_now,platform_story"
    if raw_surfaces.strip() == "all":
        raw_surfaces = _ALL_SURFACES
    surfaces = set(raw_surfaces.split(","))
    vertex = get_vertex_client()

    # ── scan phase: cheap DB probes build the tiered work list ─────────
    items: list[EnrichItem] = []
    async with maker() as session:
        ents = (
            await session.execute(text(
                "SELECT display_id FROM entities ORDER BY display_id"
                + ("" if args.limit is None else " LIMIT :lim")),
                {} if args.limit is None else {"lim": args.limit})
        ).all()
        for ent in ents:
            for surface, ref, tier in await _refs_for_entity(
                    session, ent.display_id):
                if surface not in surfaces:
                    continue

                def _make(surface: str = surface, ref: str = ref):
                    async def _proc(sess, gw) -> str:
                        return await _process_ref(sess, gw, surface, ref, args)
                    return _proc

                items.append(EnrichItem(
                    key=f"{surface}:{ref}", surface=surface,
                    tier=tier, process=_make(),
                    trigger=Trigger.G8_NEW_RUN))

    # ── execute phase: bounded-parallel workers under a wall budget ────
    gateway = VertexGateway(vertex, max_calls=args.max_calls)
    runner = BudgetedEnrichmentRunner(
        session_maker=maker, gateway=gateway,
        budget_sec=args.budget_sec, concurrency=args.concurrency)
    result = await runner.run(items, verbose=args.verbose)

    await engine.dispose()
    mode = ("DRY-RUN" if args.dry_run
            else "cold" if gateway.cold else "live")
    print(f"# enrich_corpus: {result.summary()} "
          f"(items={len(items)} vertex_calls={gateway.calls} "
          f"budget={runner.budget_sec:.0f}s x{runner.concurrency} {mode})")
    if gateway.cold:
        print(f"#   vertex cold: {gateway.cold_reason[:160]} — nothing "
              f"persisted for the skipped refs; pages keep honest PENDING")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--dry-run", action="store_true",
                   help="report the gate matrix; zero Vertex calls")
    p.add_argument("--surfaces",
                   help="comma list, or 'all' for every warmable surface "
                        "(default why_now,platform_story)")
    p.add_argument("--limit", type=int, help="only first N entities")
    p.add_argument("--max-calls", type=int, default=600)
    p.add_argument("--budget-sec", type=float, default=None,
                   help="wall-clock budget (default $DMA_ENRICH_BUDGET_SEC "
                        "or 1200) — exits 0 with remaining counts; re-runs "
                        "RESUME via cache fingerprints")
    p.add_argument("--concurrency", type=int,
                   default=env_int("DMA_ENRICH_CONCURRENCY", 6),
                   help="parallel Vertex workers "
                        "(default $DMA_ENRICH_CONCURRENCY or 6)")
    p.add_argument("--verbose", action="store_true")
    return asyncio.run(main_async(p.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
