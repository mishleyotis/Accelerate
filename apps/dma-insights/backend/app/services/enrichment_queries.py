"""Gap-driven Gemini enrichment queries for every rendered EMPTY class.

The all-94 empties census (2026-07-04; 836 empty instances across 29
classes) found the surfaces below rendering an empty/thin state for real
clients. Each entry here FORMULATES the exact Gemini query that clears
that empty for one client — dynamically, from the client's OWN gaps and
its OWN citable material — plus the acceptor that validates the model's
output and the fill-if-empty persistence that lands it where the pack
exporters and routers already read.

Census class → query (count at census time):
  D1.sentiment_card (19)          → sentiment_extraction
  D5.acquisitions_zero (62)       → acquisition_extraction
  D5.fin_no_multiyear (77)        → financial_series_extraction
  D5.timeline_lt3 (10)            → timeline_event_extraction
  D2.cards_lt5 (30)               → insight_card_generation
  D3.kpis_all_empty (33)          → focus_kpi_extraction
  D3.fa_no_subcaps (52)           → focus_subcap_classification
  D6.rows_no_evidence (94)        → techstack_evidence_linking
  D1.firmographics_empty (≤90)    → firmographics_extraction (website,
                                    founded, cagr, branches, hq, employees,
                                    ticker-where-public, geography, trend —
                                    registered HERE so the deploy-time
                                    SOFT_STEP enrich_empty_surfaces fills
                                    every empty firmographic; the prior
                                    intelligence_builder path did NOT run in
                                    that sweep, which left the majority of
                                    clients shipping empty firmographics)
  D4.story_md (94, Gemini-cold)   → platform_story (existing surface,
                                    fills on the hot deploy regen)

Honesty contract (every query):
  - grounding is the entity's own evidence/report text, E-ID labelled;
  - output is STRICT JSON; every filled value carries a verbatim
    ``quote`` that the acceptor requires to be a substring of the
    grounding (whitespace-normalised) — fabrications are dropped;
  - "absent" is a legal, useful answer: the model is told to omit
    fields / return [] when the sources do not establish a value, and
    (for acquisitions) an explicit verified-absent marker is persisted
    so the card can say "none found" with provenance instead of
    rendering an unknown-empty;
  - persistence is fill-if-empty only — report-derived ingest values
    always win, and re-runs never clobber analyst edits.

Execution: ``app.scripts.enrich_empty_surfaces`` walks entities x
queries, skips entities whose gap probe returns None (nothing missing),
routes each call through the synthesis-cache decision gates (0-token
re-reads), and applies ``accept`` + ``persist``. ``--dry-run`` emits
the fully-rendered per-client query manifest with zero Vertex calls.
"""
from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_E_ID_RE = re.compile(r"\bE-\d{1,4}\b")
_WS_RE = re.compile(r"\s+")


def _norm(t: str) -> str:
    return _WS_RE.sub(" ", t or "").strip().lower()


def _quote_in(quote: str, hay_norm: str, min_len: int = 8) -> bool:
    q = _norm(quote)
    return bool(q) and len(q) >= min_len and q in hay_norm


def _strip_fences(raw: str) -> str:
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip())


def parse_strict_json(out_text: str) -> Any:
    try:
        return json.loads(_strip_fences(out_text))
    except (ValueError, TypeError):
        return None


@dataclass(frozen=True)
class EnrichmentQuery:
    """One empty-class → Gemini-query mapping."""
    surface: str
    model: str                      # "flash" | "pro"
    empty_class: str                # census class this clears
    description: str
    template: str                   # .format_map(ctx) → prompt
    build_ctx: Callable[[AsyncSession, str], Awaitable[dict[str, Any] | None]]
    accept: Callable[[str, dict[str, Any]], Any]          # → payload | None
    persist: Callable[[AsyncSession, str, Any, dict[str, Any]], Awaitable[int]]


# ── shared context helpers ─────────────────────────────────────────────────

async def _entity_row(session: AsyncSession, did: str):
    row = (await session.execute(text(
        """
        SELECT e.id AS entity_id, e.name, e.subvertical,
               r.id AS run_id, r.ccg_catalog_version
        FROM entities e
        LEFT JOIN runs r ON r.entity_id = e.id AND r.status = 'ACTIVE'
        WHERE e.display_id = :did
        ORDER BY r.completed_at DESC NULLS LAST LIMIT 1
        """), {"did": did})).first()
    if row is None:
        raise ValueError(f"entity not found: {did}")
    return row


async def _evidence_lines(
    session: AsyncSession, entity_id: str, *, like: str | None = None,
    limit: int = 24,
) -> list[str]:
    """Tier-ordered ``[E-###] excerpt`` lines, optionally filtered by an
    ILIKE pattern over the excerpt (keeps the bundle on-topic)."""
    where = "AND ev.excerpt ILIKE :pat" if like else ""
    rows = (await session.execute(text(
        f"""
        SELECT ev.e_id, ev.excerpt FROM evidence_index ev
        WHERE ev.entity_id = :eid AND ev.excerpt IS NOT NULL {where}
        ORDER BY ev.tier ASC, ev.created_at DESC LIMIT :lim
        """), {"eid": str(entity_id), "lim": limit,
               **({"pat": like} if like else {})})).all()
    return [f"[{r.e_id}] {str(r.excerpt)[:500]}" for r in rows]


def _grounding_blob(lines: list[str], cap: int = 12000) -> str:
    return "\n".join(lines)[:cap] or "No source material available."


# ── 1. sentiment_extraction (D1.sentiment_card, 19 clients) ───────────────

_SENTIMENT_TEMPLATE = """You extract STRUCTURED review-sentiment data for {entity_name} (a {subvertical} financial institution).

SOURCES — the ONLY material you may use; every entry must quote one of these lines verbatim:
{grounding}

Return STRICT JSON (no markdown fences, no commentary):
{{"employee": [{{"source": "Glassdoor|Indeed|Comparably", "metric": "<what is rated>", "score": <number>, "scale": <5|10|100>, "n": <review count or null>, "quote": "<verbatim source line fragment>"}}],
  "customer": [{{"source": "BBB|CFPB|App Store|Google Play|Trustpilot|DepositAccounts|NPS", "metric": "...", "score": <number>, "scale": <number>, "n": <int|null>, "quote": "..."}}]}}

Rules:
- ONLY ratings the sources state explicitly. If the sources carry no employee ratings, return "employee": []. Same for customer. NEVER estimate.
- score must be the number in the quote; scale inferred from its format (4.2/5 → scale 5).
- Include at most 6 entries per cohort."""


async def _ctx_sentiment(session: AsyncSession, did: str) -> dict[str, Any] | None:
    ent = await _entity_row(session, did)
    cur = (await session.execute(text(
        "SELECT sentiment FROM firmographics WHERE entity_id = :eid"),
        {"eid": str(ent.entity_id)})).first()
    sent = (cur.sentiment if cur else None) or {}
    if isinstance(sent, dict) and (sent.get("employee") or sent.get("customer")):
        return None                                   # not empty — skip
    lines = await _evidence_lines(
        session, ent.entity_id,
        like="%glassdoor%", limit=8,
    )
    for pat in ("%indeed%", "%bbb%", "%cfpb%", "%app store%", "%review%",
                "%rating%", "%trustpilot%", "%nps%"):
        lines += await _evidence_lines(session, ent.entity_id, like=pat, limit=6)
    seen: set[str] = set()
    lines = [ln for ln in lines if not (ln in seen or seen.add(ln))][:24]
    if not lines:
        return None                                   # nothing citable — stay honest-null
    return {
        "entity_name": ent.name, "subvertical": ent.subvertical or "FSI",
        "grounding": _grounding_blob(lines),
        "recent_evidence": _grounding_blob(lines),    # fingerprint carrier
    }


def _accept_sentiment(out_text: str, ctx: dict[str, Any]) -> Any:
    data = parse_strict_json(out_text)
    if not isinstance(data, dict):
        return None
    hay = _norm(str(ctx.get("grounding") or ""))
    out: dict[str, list[dict]] = {"employee": [], "customer": []}
    for cohort in ("employee", "customer"):
        for item in (data.get(cohort) or [])[:6]:
            if not isinstance(item, dict):
                continue
            try:
                score = float(item.get("score"))
                scale = float(item.get("scale"))
            except (TypeError, ValueError):
                continue
            if not (0 < score <= scale <= 100):
                continue
            if not _quote_in(str(item.get("quote") or ""), hay):
                continue
            out[cohort].append({
                "source": str(item.get("source") or "")[:40],
                "metric": str(item.get("metric") or "")[:80],
                "score": score, "scale": scale,
                "n": int(item["n"]) if isinstance(item.get("n"), int | float) else None,
            })
    return out if (out["employee"] or out["customer"]) else None


async def _persist_sentiment(
    session: AsyncSession, did: str, payload: Any, provenance: dict[str, Any],
) -> int:
    n = await session.execute(text(
        """
        UPDATE firmographics f SET
            sentiment = CAST(:s AS JSONB), sentiment_synced_at = NOW()
        FROM entities e
        WHERE e.id = f.entity_id AND e.display_id = :did
          AND (f.sentiment IS NULL
               OR (COALESCE(f.sentiment->'employee','[]'::jsonb) = '[]'::jsonb
                   AND COALESCE(f.sentiment->'customer','[]'::jsonb) = '[]'::jsonb))
        """),
        {"did": did, "s": json.dumps({
            **payload, "derived_from": "gemini", "_fx_provenance": provenance,
        })})
    return n.rowcount or 0


# ── 2. acquisition_extraction (D5.acquisitions_zero, 62 clients) ───────────

_ACQ_TEMPLATE = """You extract M&A FRAMES for {entity_name}. An acquisition frame requires a named acquirer AND a named target where {entity_name} is one of the two parties, plus an event verb (acquired, merged, purchased, announced acquisition of).

SOURCES — the ONLY citable material (each line starts with its evidence id):
{grounding}

Return STRICT JSON:
{{"acquisitions": [{{"acquirer": "...", "target": "...", "amount": "<$X or null>", "status": "announced|closed|integrating", "announced_on": "YYYY-MM|YYYY|null", "e_id": "E-###", "quote": "<verbatim fragment>"}}],
  "verified_absent": <true|false>}}

Rules:
- Strategy intent ("actively seeking acquisitions"), peer/third-party deals, and negated statements are NOT frames — exclude them.
- If the sources contain no qualifying frame, return "acquisitions": [] and "verified_absent": true.
- e_id must be one of the ids shown in SOURCES; quote must be verbatim from that line."""


async def _ctx_acquisitions(session: AsyncSession, did: str) -> dict[str, Any] | None:
    ent = await _entity_row(session, did)
    n_acq = (await session.execute(text(
        """
        SELECT COUNT(*) FROM timeline_events
        WHERE entity_id = :eid AND kind = 'acquisition'
        """), {"eid": str(ent.entity_id)})).scalar_one()
    if int(n_acq) > 0:
        return None
    lines: list[str] = []
    for pat in ("%acqui%", "%merger%", "%merged%", "%purchase%", "% M&A %"):
        lines += await _evidence_lines(session, ent.entity_id, like=pat, limit=8)
    seen: set[str] = set()
    lines = [ln for ln in lines if not (ln in seen or seen.add(ln))][:20]
    if not lines:
        return None                                   # nothing to mine OR verify
    return {
        "entity_name": ent.name,
        "grounding": _grounding_blob(lines),
        "recent_evidence": _grounding_blob(lines),
        "_entity_id": str(ent.entity_id),
    }


def _accept_acquisitions(out_text: str, ctx: dict[str, Any]) -> Any:
    data = parse_strict_json(out_text)
    if not isinstance(data, dict):
        return None
    hay = _norm(str(ctx.get("grounding") or ""))
    allowed = set(_E_ID_RE.findall(str(ctx.get("grounding") or "")))
    ent_l = _norm(str(ctx.get("entity_name") or ""))
    frames = []
    for item in (data.get("acquisitions") or [])[:8]:
        if not isinstance(item, dict):
            continue
        acquirer = str(item.get("acquirer") or "").strip()
        target = str(item.get("target") or "").strip()
        status = str(item.get("status") or "").strip().lower()
        e_id = str(item.get("e_id") or "").strip()
        if not (acquirer and target and status in
                {"announced", "closed", "integrating"} and e_id in allowed):
            continue
        if not _quote_in(str(item.get("quote") or ""), hay, min_len=12):
            continue
        # the entity must be a party — otherwise it is peer/third-party M&A
        if ent_l.split(" ")[0] not in _norm(acquirer) \
                and ent_l.split(" ")[0] not in _norm(target):
            continue
        frames.append({
            "acquirer": acquirer[:120], "target": target[:120],
            "amount": (str(item.get("amount")) or None),
            "status": status,
            "announced_on": str(item.get("announced_on") or "") or None,
            "e_id": e_id,
            "quote": str(item.get("quote") or "")[:400],
        })
    if frames:
        return {"acquisitions": frames, "verified_absent": False}
    if data.get("verified_absent") is True:
        return {"acquisitions": [], "verified_absent": True}
    return None


async def _persist_acquisitions(
    session: AsyncSession, did: str, payload: Any, provenance: dict[str, Any],
) -> int:
    ent = await _entity_row(session, did)
    written = 0
    if payload.get("verified_absent"):
        # Persist the VERIFIED absence so the card can say "no acquisition
        # activity found (verified against N source items)" instead of an
        # unknown-empty.
        n = await session.execute(text(
            """
            UPDATE firmographics f SET
                parsed_facts = COALESCE(f.parsed_facts, '{}'::jsonb)
                               || CAST(:pf AS JSONB)
            FROM entities e
            WHERE e.id = f.entity_id AND e.display_id = :did
              AND COALESCE(f.parsed_facts->>'acquisitions_verified_absent','')
                  <> 'true'
            """),
            {"did": did, "pf": json.dumps({
                "acquisitions_verified_absent": True,
                "_acq_provenance": provenance,
            })})
        return n.rowcount or 0
    for fr in payload["acquisitions"]:
        raw_date = fr.get("announced_on") or ""
        m = re.match(r"^(\d{4})(?:-(\d{2}))?", raw_date)
        event_date = (
            date(int(m.group(1)), int(m.group(2) or 1), 1) if m else None)
        precision = ("month" if (m and m.group(2)) else
                     "year" if m else "publish_fallback")
        dup = (await session.execute(text(
            """
            SELECT 1 FROM timeline_events
            WHERE entity_id = :eid AND kind = 'acquisition'
              AND LOWER(title) LIKE :t LIMIT 1
            """), {"eid": str(ent.entity_id),
                   "t": f"%{_norm(fr['target'])[:40]}%"})).first()
        if dup:
            continue
        await session.execute(text(
            """
            INSERT INTO timeline_events
                (id, entity_id, event_date, kind, title, body, e_id,
                 signal, date_precision, evidence_e_ids, created_at)
            VALUES (gen_random_uuid(), :eid, :d, 'acquisition',
                    :title, :body, :e, 'positive', :prec,
                    CAST(:evs AS VARCHAR[]), NOW())
            """),
            {"eid": str(ent.entity_id), "d": event_date,
             "title": f"{fr['acquirer']} acquires {fr['target']}"[:120],
             "body": fr["quote"], "e": fr["e_id"], "prec": precision,
             "evs": [fr["e_id"]]})
        written += 1
    return written


# ── 3. financial_series_extraction (D5.fin_no_multiyear, 77 clients) ───────

_FIN_SERIES_TEMPLATE = """You extract a MULTI-YEAR financial series for {entity_name} from its own report material.

SOURCES — the ONLY citable material:
{grounding}

Return STRICT JSON:
{{"metric": "total_assets|revenue|aum|deposits|net_income|premium|loans", "unit": "usd_b|usd_m|pct", "series": {{"<YYYY>": <number>, ...}}, "quote": "<the verbatim source fragment carrying the years and values>"}}

Rules:
- ONLY year→value pairs the sources state explicitly ("grew from $2.3B in 2021 to $3.2B in 2025" → {{"2021": 2.3, "2025": 3.2}}).
- The series must describe {entity_name} ITSELF — peer/benchmark institutions named in the sources are NOT this series.
- At least 2 distinct years or return {{}}. NEVER interpolate or estimate intermediate years.
- Values in the unit you declare (e.g. $3.2B with unit usd_b → 3.2)."""


async def _ctx_fin_series(session: AsyncSession, did: str) -> dict[str, Any] | None:
    ent = await _entity_row(session, did)
    cur = (await session.execute(text(
        "SELECT financial_highlights FROM firmographics WHERE entity_id = :eid"),
        {"eid": str(ent.entity_id)})).first()
    fh = (cur.financial_highlights if cur else None) or {}
    from app.services.context_extras import financials_view
    view = financials_view(fh if isinstance(fh, dict) else None) or {}
    if any(len(s.get("fy") or []) >= 2 for s in view.get("series_labeled") or []):
        return None                                   # already charts — skip
    lines = [str(x) for x in (fh.get("lines") or [])[:20]] \
        if isinstance(fh, dict) else []
    for pat in ("%assets%", "%revenue%", "%deposit%", "% AUM %", "%net income%"):
        lines += await _evidence_lines(session, ent.entity_id, like=pat, limit=6)
    secs = (await session.execute(text(
        """
        SELECT ds.body FROM document_sections ds
        JOIN runs r ON r.id = ds.run_id AND r.status = 'ACTIVE'
        WHERE ds.entity_id = :eid
          AND ds.section_kind IN ('trend_analysis', 'benchmark_comparison')
        ORDER BY ds.ordinal LIMIT 4
        """), {"eid": str(ent.entity_id)})).all()
    lines += [str(s.body or "")[:1500] for s in secs]
    seen: set[str] = set()
    lines = [ln for ln in lines if ln and not (ln in seen or seen.add(ln))][:30]
    if not lines:
        return None
    return {
        "entity_name": ent.name,
        "grounding": _grounding_blob(lines),
        "recent_evidence": _grounding_blob(lines),
    }


def _accept_fin_series(out_text: str, ctx: dict[str, Any]) -> Any:
    data = parse_strict_json(out_text)
    if not isinstance(data, dict) or not isinstance(data.get("series"), dict):
        return None
    hay = _norm(str(ctx.get("grounding") or ""))
    quote = str(data.get("quote") or "")
    if not _quote_in(quote, hay, min_len=16):
        return None
    unit = str(data.get("unit") or "")
    metric = str(data.get("metric") or "")
    if unit not in {"usd_b", "usd_m", "pct"} or not metric:
        return None
    series: dict[str, float] = {}
    for y, v in data["series"].items():
        if not re.fullmatch(r"(?:19|20)\d{2}", str(y)):
            continue
        try:
            val = float(v)
        except (TypeError, ValueError):
            continue
        # every year must literally appear in the verbatim quote — the
        # anti-interpolation gate
        if str(y) not in quote:
            continue
        series[str(y)] = val
    if len(series) < 2:
        return None
    return {"metric": metric[:40], "unit": unit, "series": series,
            "quote": quote[:400]}


async def _persist_fin_series(
    session: AsyncSession, did: str, payload: Any, provenance: dict[str, Any],
) -> int:
    # financials_view treats a pre-structured `series` key as the primary
    # year axis — both the D1 card and the D5 chart light up from this.
    n = await session.execute(text(
        """
        UPDATE firmographics f SET
            financial_highlights =
                COALESCE(f.financial_highlights, '{}'::jsonb)
                || CAST(:fh AS JSONB)
        FROM entities e
        WHERE e.id = f.entity_id AND e.display_id = :did
          AND (f.financial_highlights IS NULL
               OR NOT f.financial_highlights ? 'series')
        """),
        {"did": did, "fh": json.dumps({
            "series": payload["series"],
            "series_metric": payload["metric"],
            "series_unit": payload["unit"],
            "series_basis": "gemini:verbatim",
            "_series_provenance": provenance,
        })})
    return n.rowcount or 0


# ── 4. timeline_event_extraction (D5.timeline_lt3, 10 clients) ─────────────

_TIMELINE_TEMPLATE = """You extract DATED events for {entity_name}'s digital-evolution timeline.

SOURCES — the ONLY citable material (each line starts with its evidence id):
{grounding}

Return STRICT JSON:
{{"events": [{{"date": "YYYY-MM-DD|YYYY-MM|YYYY", "kind": "leadership|regulatory|milestone|product|partnership|acquisition", "title": "<≤60 chars, subject-verb-object>", "body": "<1-2 sentences>", "signal": "positive|negative|neutral", "e_id": "E-###", "quote": "<verbatim fragment carrying the date>"}}]}}

Rules:
- ONLY dated occurrences (launched/hired/announced/fined/migrated/completed). Baselines, obligations and inferences are NOT events.
- Negated statements ("no enforcement actions") are NOT events.
- The date must come from the quote; never use a publication date as the event date.
- Maximum 6 events; return {{"events": []}} if the sources carry none."""


async def _ctx_timeline(session: AsyncSession, did: str) -> dict[str, Any] | None:
    ent = await _entity_row(session, did)
    n_ev = (await session.execute(text(
        "SELECT COUNT(*) FROM timeline_events WHERE entity_id = :eid"),
        {"eid": str(ent.entity_id)})).scalar_one()
    if int(n_ev) >= 3:
        return None
    existing = (await session.execute(text(
        "SELECT title FROM timeline_events WHERE entity_id = :eid"),
        {"eid": str(ent.entity_id)})).all()
    lines = await _evidence_lines(session, ent.entity_id, limit=30)
    dated = [ln for ln in lines if re.search(r"(?:19|20)\d{2}", ln)]
    if not dated:
        return None
    return {
        "entity_name": ent.name,
        "grounding": _grounding_blob(dated[:24]),
        "recent_evidence": _grounding_blob(dated[:24]),
        "_existing_titles": [r.title for r in existing],
        "_entity_id": str(ent.entity_id),
    }


_KINDS = {"leadership", "regulatory", "milestone", "product",
          "partnership", "acquisition"}


def _accept_timeline(out_text: str, ctx: dict[str, Any]) -> Any:
    data = parse_strict_json(out_text)
    if not isinstance(data, dict):
        return None
    hay = _norm(str(ctx.get("grounding") or ""))
    allowed = set(_E_ID_RE.findall(str(ctx.get("grounding") or "")))
    existing = {_norm(t)[:40] for t in ctx.get("_existing_titles") or []}
    events = []
    for item in (data.get("events") or [])[:6]:
        if not isinstance(item, dict):
            continue
        date = str(item.get("date") or "")
        m = re.fullmatch(r"(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", date)
        kind = str(item.get("kind") or "").lower()
        signal = str(item.get("signal") or "").lower()
        e_id = str(item.get("e_id") or "")
        title = str(item.get("title") or "").strip()[:60]
        quote = str(item.get("quote") or "")
        if not (m and kind in _KINDS and e_id in allowed and title
                and signal in {"positive", "negative", "neutral"}):
            continue
        if not _quote_in(quote, hay, min_len=12):
            continue
        if m.group(1) not in quote:
            continue                              # date must be in the quote
        if _norm(title)[:40] in existing:
            continue
        precision = "day" if m.group(3) else ("month" if m.group(2) else "year")
        event_date = f"{m.group(1)}-{m.group(2) or '01'}-{m.group(3) or '01'}"
        events.append({"date": event_date, "precision": precision,
                       "kind": kind, "title": title,
                       "body": str(item.get("body") or "")[:500],
                       "signal": signal, "e_id": e_id})
        existing.add(_norm(title)[:40])
    return {"events": events} if events else None


async def _persist_timeline(
    session: AsyncSession, did: str, payload: Any, provenance: dict[str, Any],
) -> int:
    ent = await _entity_row(session, did)
    written = 0
    for ev in payload["events"]:
        await session.execute(text(
            """
            INSERT INTO timeline_events
                (id, entity_id, event_date, kind, title, body, e_id,
                 signal, date_precision, evidence_e_ids, created_at)
            VALUES (gen_random_uuid(), :eid, :d, :kind,
                    :title, :body, :e, :sig, :prec,
                    CAST(:evs AS VARCHAR[]), NOW())
            """),
            {"eid": str(ent.entity_id),
             "d": date.fromisoformat(ev["date"]), "kind": ev["kind"],
             "title": ev["title"], "body": ev["body"], "e": ev["e_id"],
             "sig": ev["signal"], "prec": ev["precision"],
             "evs": [ev["e_id"]]})
        written += 1
    return written


# ── 5. insight_card_generation (D2.cards_lt5, 30 clients) ──────────────────

_INSIGHT_TEMPLATE = """You are a senior FSI analyst writing insight cards for {entity_name} (a {subvertical} institution). The client currently has {existing_count} card(s): {existing_titles}.

CAPABILITY GAPS (the run's lowest-scoring sub-capabilities):
{gaps}

SOURCES — the ONLY citable evidence (each line starts with its evidence id):
{grounding}

Write up to {want} NEW cards as STRICT JSON:
{{"cards": [{{"title": "<names the actual capability/system, ≤80 chars>", "what_text": "<observed client-specific facts with numbers>", "why_text": "<the causal driver — not a score restatement>", "so_what_text": "<the action an account executive should take>", "severity": "HIGH|MEDIUM|LOW", "linked_subcap_id": "<one id from CAPABILITY GAPS>", "linked_e_ids": ["E-###"], "affects": ["<other subcap ids from CAPABILITY GAPS this touches>"], "theme": "<2-4 word theme>"}}]}}

Rules:
- Every card MUST cite ≥1 e_id from SOURCES and ground its what_text in those excerpts.
- Do not duplicate the existing titles. Do not invent systems, numbers, or subcap ids.
- Fewer good cards beat filler — return [] if the evidence cannot support a new card."""


async def _ctx_insight_gen(session: AsyncSession, did: str) -> dict[str, Any] | None:
    ent = await _entity_row(session, did)
    if ent.run_id is None:
        return None
    cards = (await session.execute(text(
        "SELECT title FROM insight_cards WHERE run_id = :rid"),
        {"rid": str(ent.run_id)})).all()
    if len(cards) >= 5:
        return None
    gaps = (await session.execute(text(
        """
        SELECT s.subcap_id, s.score, COALESCE(cs.name, '') AS name,
               COALESCE(s.rationale, '') AS rationale
        FROM subcap_scores s
        LEFT JOIN ccg_subcaps cs
          ON cs.version = :ver AND cs.subcap_id = s.subcap_id
        WHERE s.run_id = :rid AND s.score IS NOT NULL
        ORDER BY s.score ASC LIMIT 12
        """), {"rid": str(ent.run_id),
               "ver": ent.ccg_catalog_version or "v7.0"})).all()
    if not gaps:
        return None
    lines = await _evidence_lines(session, ent.entity_id, limit=20)
    if not lines:
        return None
    return {
        "entity_name": ent.name, "subvertical": ent.subvertical or "FSI",
        "existing_count": len(cards),
        "existing_titles": "; ".join(r.title for r in cards) or "(none)",
        "want": 5 - len(cards),
        "gaps": "\n".join(
            f"  - {g.subcap_id}  {g.name}  score={g.score}  "
            f"why={g.rationale[:140]}" for g in gaps),
        "grounding": _grounding_blob(lines),
        "recent_evidence": _grounding_blob(lines),
        "_gap_ids": [g.subcap_id for g in gaps],
        "_existing_titles": [r.title for r in cards],
        "_run_id": str(ent.run_id), "_entity_id": str(ent.entity_id),
    }


def _accept_insight_gen(out_text: str, ctx: dict[str, Any]) -> Any:
    data = parse_strict_json(out_text)
    if not isinstance(data, dict):
        return None
    allowed_e = set(_E_ID_RE.findall(str(ctx.get("grounding") or "")))
    gap_ids = set(ctx.get("_gap_ids") or [])
    existing = {_norm(t)[:60] for t in ctx.get("_existing_titles") or []}
    want = int(ctx.get("want") or 0)
    cards = []
    for item in (data.get("cards") or [])[:want]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()[:120]
        sid = str(item.get("linked_subcap_id") or "")
        e_ids = [e for e in (item.get("linked_e_ids") or []) if e in allowed_e]
        what = str(item.get("what_text") or "").strip()
        why = str(item.get("why_text") or "").strip()
        so = str(item.get("so_what_text") or "").strip()
        sev = str(item.get("severity") or "").upper()
        if not (title and sid in gap_ids and e_ids and
                len(what) >= 60 and len(why) >= 40 and len(so) >= 30 and
                sev in {"HIGH", "MEDIUM", "LOW"}):
            continue
        if _norm(title)[:60] in existing:
            continue
        cards.append({
            "title": title, "what_text": what[:1200], "why_text": why[:800],
            # DB check constraint is lowercase ('critical|high|medium|low')
            "so_what_text": so[:800], "severity": sev.lower(),
            "linked_subcap_id": sid, "linked_e_ids": e_ids[:6],
            "affects": [a for a in (item.get("affects") or [])
                        if a in gap_ids and a != sid][:4],
            "theme": str(item.get("theme") or "")[:60] or None,
        })
        existing.add(_norm(title)[:60])
    return {"cards": cards} if cards else None


async def _persist_insight_gen(
    session: AsyncSession, did: str, payload: Any, provenance: dict[str, Any],
) -> int:
    ent = await _entity_row(session, did)
    if ent.run_id is None:
        return 0
    n0 = (await session.execute(text(
        "SELECT COUNT(*) FROM insight_cards WHERE run_id = :rid"),
        {"rid": str(ent.run_id)})).scalar_one()
    written = 0
    for i, c in enumerate(payload["cards"]):
        await session.execute(text(
            """
            INSERT INTO insight_cards
                (id, run_id, entity_id, ic_id, severity, title, what_text,
                 why_text, so_what_text, linked_subcap_id, linked_e_ids,
                 affects, theme, created_at)
            VALUES (gen_random_uuid(), :rid, :eid, :ic, :sev, :title, :what,
                    :why, :so, :sid, CAST(:evs AS VARCHAR[]),
                    CAST(:aff AS VARCHAR[]), :theme, NOW())
            """),
            {"rid": str(ent.run_id), "eid": str(ent.entity_id),
             "ic": f"IC-GX{int(n0) + i + 1:02d}", "sev": c["severity"],
             "title": c["title"], "what": c["what_text"], "why": c["why_text"],
             "so": c["so_what_text"], "sid": c["linked_subcap_id"],
             "evs": c["linked_e_ids"], "aff": c["affects"],
             "theme": c["theme"]})
        written += 1
    return written


# ── 6. focus_kpi_extraction (D3.kpis_all_empty, 33 clients) ────────────────

_FOCUS_KPI_TEMPLATE = """You synthesize measurable KPIs for {entity_name}'s strategic focus areas by reasoning over what the client has PUBLICLY DISCLOSED and the uplift Zennify's roadmap would deliver. Layer real intelligence — a wrong KPI is worse than none.

FOCUS AREAS — each carries its strategy quote, the KPIs already DISCLOSED in the client's own material (with the evidence id stating each), and the ROADMAP RECOMMENDATIONS targeting it (with their metric uplifts):
{focus_areas}

SOURCES — the ONLY citable material (each line starts with its evidence id):
{grounding}

Return STRICT JSON:
{{"kpis": [{{"fa_id": "<id from FOCUS AREAS>", "label": "<≤40 chars metric name>", "current": "<a value the SOURCES disclose>", "target": "<the value after the roadmap uplift>", "rationale": "<one sentence tying the disclosed current to the roadmap target>", "evidence_e_ids": ["E-### the current is disclosed in"]}}]}}

Rules:
- ``current`` MUST be a number the SOURCES state; cite its evidence id(s) in ``evidence_e_ids``. Never invent a current.
- ``target`` MUST follow from a ROADMAP RECOMMENDATION's stated uplift for that focus area — the recommendation's target value, or the current adjusted by its stated % uplift. A target the roadmap does not support is WRONG — omit that KPI entirely.
- Prefer completing the DISCLOSED candidates shown; at most 2 KPIs per focus area.
- Omit a focus area when the sources carry no disclosed number for it."""


async def _ctx_focus_kpis(session: AsyncSession, did: str) -> dict[str, Any] | None:
    """Context for the KPI reasoning tier. COMPLETES partial rows: a focus
    area is pending when it has NO complete (target-bearing) KPI yet — so
    an entity whose other FAs already carry KPIs is no longer skipped
    wholesale (the ``if have: return None`` entity-grain skip was the
    2026-07 defect: 31 clients with zero KPIs stayed empty). Each pending
    FA is seeded with its DISCLOSED KPI candidates (deterministic
    nlp.quantities, topically bound to the FA) + the roadmap recs
    targeting its subcaps with their metric uplifts, so the model reasons
    over facts instead of guessing."""
    from app.services.focus_area_synthesizer import (
        kpi_fa_key,
        mine_disclosed_kpis,
    )
    ent = await _entity_row(session, did)
    if ent.run_id is None:
        return None
    fas = (await session.execute(text(
        """
        SELECT fa.id, fa.title, fa.verbatim_quote,
               fa.grounding->>'representative_quote' AS rep_quote,
               fa.grounding->'evidence_e_ids' AS ground_eids,
               fa.involved_subcap_ids AS subcaps
        FROM focus_areas fa
        WHERE fa.run_id = :rid ORDER BY fa.id LIMIT 8
        """), {"rid": str(ent.run_id)})).all()
    if not fas:
        return None
    # FAs that already carry a COMPLETE (target-bearing) KPI — those are
    # done; everything else is pending (fill-if-empty at the FA grain).
    complete = {r.fa_id for r in (await session.execute(text(
        """
        SELECT DISTINCT fa_id FROM focus_area_kpi_overrides
        WHERE entity_id = :eid AND target_value IS NOT NULL
        """), {"eid": str(ent.entity_id)})).all()}
    pending = [r for r in fas if kpi_fa_key(str(r.id)) not in complete]
    if not pending:
        return None
    fh_row = (await session.execute(text(
        "SELECT financial_highlights FROM firmographics WHERE entity_id = :eid"),
        {"eid": str(ent.entity_id)})).first()
    fh = (fh_row.financial_highlights if fh_row else None) or {}
    fin_lines = [str(x) for x in (fh.get("lines") or [])[:12]] \
        if isinstance(fh, dict) else []
    # evidence for the run keyed by e_id + by subcap (topical binding of
    # the disclosed-candidate mine + the acceptor's current-in-cited check)
    ev_rows = (await session.execute(text(
        """
        SELECT e_id, excerpt, linked_subcap_ids FROM evidence_index
        WHERE run_id = :rid AND excerpt IS NOT NULL
        ORDER BY tier ASC, e_id ASC LIMIT 300
        """), {"rid": str(ent.run_id)})).all()
    excerpt_by_eid = {e.e_id: (e.excerpt or "")[:500] for e in ev_rows}
    eids_by_subcap: dict[str, list[str]] = {}
    for e in ev_rows:
        for sid in (e.linked_subcap_ids or []):
            eids_by_subcap.setdefault(sid, []).append(e.e_id)
    recs = (await session.execute(text(
        """
        SELECT rec_id, title, description, target_subcap_ids
        FROM recommendations WHERE run_id = :rid ORDER BY rec_id
        """), {"rid": str(ent.run_id)})).all()

    fa_block: list[str] = []
    rec_texts_by_fa: dict[str, list[str]] = {}
    grounding_lines: list[str] = list(fin_lines)
    for r in pending:
        fa_id = str(r.id)
        subs = set(r.subcaps or [])
        fa_text = " ".join(t for t in (r.title, r.rep_quote or r.verbatim_quote) if t)
        # candidate (e_id, excerpt) = evidence on this FA's subcaps + its
        # already-attached grounding E-IDs (JSONB → list; guard the string
        # form so a non-decoded array never explodes into characters)
        cand_eids: list[str] = [
            e for e in (r.ground_eids or []) if isinstance(e, str)]
        for sid in subs:
            cand_eids.extend(eids_by_subcap.get(sid, []))
        seen_e: set[str] = set()
        pairs = []
        for e in cand_eids:
            if e in seen_e or e not in excerpt_by_eid:
                continue
            seen_e.add(e)
            pairs.append((e, excerpt_by_eid[e]))
            grounding_lines.append(f"[{e}] {excerpt_by_eid[e]}")
        disclosed = mine_disclosed_kpis(fa_text, pairs)
        rec_matches = [rc for rc in recs
                       if set(rc.target_subcap_ids or []) & subs]
        rec_texts_by_fa[fa_id] = [
            f"{rc.title or ''}. {rc.description or ''}" for rc in rec_matches]
        disc_txt = "; ".join(
            f"{d['kpi_label']}={d.get('current_value') or '?'} [{d['e_id']}]"
            for d in disclosed) or "(none mined)"
        rec_txt = " | ".join(
            f"{rc.rec_id} {(rc.title or '')[:60]}: {(rc.description or '')[:140]}"
            for rc in rec_matches[:4]) or "(no roadmap recs target this area)"
        fa_block.append(
            f"  - id={fa_id}  {r.title}: \"{(r.rep_quote or r.verbatim_quote or '')[:220]}\"\n"
            f"      DISCLOSED: {disc_txt}\n"
            f"      ROADMAP: {rec_txt}")
    grounding = _grounding_blob(grounding_lines)
    return {
        "entity_name": ent.name,
        "focus_areas": "\n".join(fa_block),
        "grounding": grounding,
        "recent_evidence": grounding,
        "_fa_ids": [str(r.id) for r in pending],
        "_excerpt_by_eid": excerpt_by_eid,
        "_rec_texts_by_fa": rec_texts_by_fa,
        "_entity_id": str(ent.entity_id),
    }


def _accept_focus_kpis(out_text: str, ctx: dict[str, Any]) -> Any:
    """Reject WRONG KPIs: current must appear numerically (within
    tolerance) in a CITED excerpt, and any target must be arithmetically
    consistent with a roadmap rec's stated uplift. A fabricated current or
    an unsupported target drops the whole row."""
    from app.services.focus_area_synthesizer import (
        kpi_current_disclosed,
        kpi_delta_label,
        kpi_target_consistent,
    )
    data = parse_strict_json(out_text)
    if not isinstance(data, dict):
        return None
    fa_ids = set(ctx.get("_fa_ids") or [])
    excerpt_by_eid: dict[str, str] = ctx.get("_excerpt_by_eid") or {}
    rec_texts_by_fa: dict[str, list[str]] = ctx.get("_rec_texts_by_fa") or {}
    per_fa: dict[str, int] = {}
    kpis = []
    for item in (data.get("kpis") or [])[:24]:
        if not isinstance(item, dict):
            continue
        fa_id = str(item.get("fa_id") or "")
        label = str(item.get("label") or "").strip()[:40]
        cur = (str(item.get("current")) if item.get("current") not in (None, "") else None)
        tgt = (str(item.get("target")) if item.get("target") not in (None, "") else None)
        rationale = str(item.get("rationale") or "").strip()[:280]
        e_ids = [e for e in (item.get("evidence_e_ids") or [])
                 if isinstance(e, str) and e in excerpt_by_eid]
        if not (fa_id in fa_ids and label and cur and e_ids):
            continue
        cited = [excerpt_by_eid[e] for e in e_ids]
        # current must be a DISCLOSED number in one of the cited excerpts
        if not kpi_current_disclosed(cur, cited):
            continue
        # a target must be consistent with a roadmap rec uplift, else WRONG
        rec_texts = rec_texts_by_fa.get(fa_id) or []
        if tgt and not kpi_target_consistent(cur, tgt, rec_texts):
            continue
        if per_fa.get(fa_id, 0) >= 2:
            continue
        per_fa[fa_id] = per_fa.get(fa_id, 0) + 1
        kpis.append({
            "fa_id": fa_id, "label": label, "current": cur, "target": tgt,
            "delta": kpi_delta_label(cur, tgt) if tgt else None,
            "rationale": rationale, "evidence_e_ids": e_ids[:6],
        })
    return {"kpis": kpis} if kpis else None


async def _persist_focus_kpis(
    session: AsyncSession, did: str, payload: Any, provenance: dict[str, Any],
) -> int:
    """Fill-if-empty per (entity, fa, label) with per-row provenance —
    never clobbers an AE edit or an existing labelled row (ON CONFLICT DO
    NOTHING). Persists evidence_e_ids + rationale + a provenance envelope
    {source_mode:'gemini_reasoned', model_id, evidence, surface,
    synthesized_at} (migration 056 columns)."""
    from app.services.focus_area_synthesizer import kpi_fa_key
    ent = await _entity_row(session, did)
    written = 0
    for k in payload["kpis"]:
        fa_key = kpi_fa_key(k["fa_id"])
        row_prov = {
            **provenance, "source_mode": "gemini_reasoned",
            "evidence": k.get("evidence_e_ids") or [],
        }
        n = await session.execute(text(
            """
            INSERT INTO focus_area_kpi_overrides
                (id, entity_id, fa_id, kpi_label, source_mode,
                 current_value, target_value, delta, evidence_e_ids,
                 rationale, provenance, updated_at)
            VALUES (gen_random_uuid(), :eid, :fa, :label, 'public',
                    :cur, :tgt, :delta, CAST(:evs AS VARCHAR[]),
                    :rat, CAST(:prov AS JSONB), NOW())
            ON CONFLICT (entity_id, fa_id, kpi_label) DO NOTHING
            """),
            {"eid": str(ent.entity_id), "fa": fa_key, "label": k["label"],
             "cur": k["current"], "tgt": k["target"],
             "delta": k.get("delta"), "evs": k.get("evidence_e_ids") or [],
             "rat": k.get("rationale") or None,
             "prov": json.dumps(row_prov)})
        written += n.rowcount or 0
    return written


# ── 7. focus_subcap_classification (D3.fa_no_subcaps, 52 clients) ──────────

_FA_SUBCAP_TEMPLATE = """You map {entity_name}'s strategic focus areas to the capability catalogue.

FOCUS AREAS (no capability links yet):
{focus_areas}

SCORED SUB-CAPABILITIES for this client (the ONLY legal ids):
{subcaps}

Return STRICT JSON:
{{"assignments": [{{"fa_id": "<id from FOCUS AREAS>", "subcap_ids": ["<2-6 ids from SCORED SUB-CAPABILITIES>"]}}]}}

Rules:
- Choose subcaps whose NAME semantically matches what the focus area is about. 2-6 per area.
- Omit an area entirely if no subcap plausibly relates — never force a mapping."""


async def _ctx_fa_subcaps(session: AsyncSession, did: str) -> dict[str, Any] | None:
    ent = await _entity_row(session, did)
    if ent.run_id is None:
        return None
    fas = (await session.execute(text(
        """
        SELECT fa.id, fa.title, fa.verbatim_quote
        FROM focus_areas fa
        WHERE fa.run_id = :rid
          AND (fa.involved_subcap_ids IS NULL
               OR cardinality(fa.involved_subcap_ids) = 0)
        ORDER BY fa.id LIMIT 8
        """), {"rid": str(ent.run_id)})).all()
    if not fas:
        return None
    subs = (await session.execute(text(
        """
        SELECT s.subcap_id, COALESCE(cs.name, '') AS name
        FROM subcap_scores s
        LEFT JOIN ccg_subcaps cs
          ON cs.version = :ver AND cs.subcap_id = s.subcap_id
        WHERE s.run_id = :rid ORDER BY s.subcap_id LIMIT 200
        """), {"rid": str(ent.run_id),
               "ver": ent.ccg_catalog_version or "v7.0"})).all()
    if not subs:
        return None
    return {
        "entity_name": ent.name,
        "focus_areas": "\n".join(
            f"  - id={r.id}  {r.title}: \"{(r.verbatim_quote or '')[:220]}\""
            for r in fas),
        "subcaps": "\n".join(
            f"  - {s.subcap_id}  {s.name}" for s in subs),
        "recent_evidence": "\n".join(
            f"{r.title} {(r.verbatim_quote or '')[:120]}" for r in fas),
        "_fa_ids": [str(r.id) for r in fas],
        "_subcap_ids": [s.subcap_id for s in subs],
    }


def _accept_fa_subcaps(out_text: str, ctx: dict[str, Any]) -> Any:
    data = parse_strict_json(out_text)
    if not isinstance(data, dict):
        return None
    fa_ids = set(ctx.get("_fa_ids") or [])
    legal = set(ctx.get("_subcap_ids") or [])
    out = []
    for item in (data.get("assignments") or [])[:8]:
        if not isinstance(item, dict):
            continue
        fa_id = str(item.get("fa_id") or "")
        ids = [s for s in (item.get("subcap_ids") or []) if s in legal]
        if fa_id in fa_ids and 2 <= len(ids) <= 6:
            out.append({"fa_id": fa_id, "subcap_ids": ids})
    return {"assignments": out} if out else None


async def _persist_fa_subcaps(
    session: AsyncSession, did: str, payload: Any, provenance: dict[str, Any],
) -> int:
    written = 0
    for a in payload["assignments"]:
        n = await session.execute(text(
            """
            UPDATE focus_areas SET
                involved_subcap_ids = CAST(:ids AS VARCHAR[])
            WHERE id = CAST(:faid AS UUID)
              AND (involved_subcap_ids IS NULL
                   OR cardinality(involved_subcap_ids) = 0)
            """), {"faid": a["fa_id"], "ids": a["subcap_ids"]})
        written += n.rowcount or 0
    return written


# ── 8. techstack_evidence_linking (D6.rows_no_evidence, 94 clients) ────────

_TECH_EVIDENCE_TEMPLATE = """You link {entity_name}'s detected technology platforms to the evidence that names them.

PLATFORM ROWS (no evidence links yet):
{rows}

SOURCES — the ONLY citable material (each line starts with its evidence id):
{grounding}

Return STRICT JSON:
{{"links": [{{"tech_id": "<id from PLATFORM ROWS>", "e_ids": ["E-###"]}}]}}

Rules:
- Link a row ONLY when the cited source line literally names that product or vendor.
- Omit rows no source names — silence is honest."""


async def _ctx_tech_evidence(session: AsyncSession, did: str) -> dict[str, Any] | None:
    ent = await _entity_row(session, did)
    rows = (await session.execute(text(
        """
        SELECT id, vendor, product FROM tech_stack_entries
        WHERE entity_id = :eid
          AND (evidence_e_ids IS NULL OR cardinality(evidence_e_ids) = 0)
          AND status <> 'ABSENT'
        ORDER BY product LIMIT 24
        """), {"eid": str(ent.entity_id)})).all()
    if not rows:
        return None
    lines = await _evidence_lines(session, ent.entity_id, limit=30)
    if not lines:
        return None
    return {
        "entity_name": ent.name,
        "rows": "\n".join(
            f"  - id={r.id}  {r.vendor or ''} {r.product}" for r in rows),
        "grounding": _grounding_blob(lines),
        "recent_evidence": _grounding_blob(lines),
        "_rows": {str(r.id): f"{r.vendor or ''} {r.product}".strip()
                  for r in rows},
    }


def _accept_tech_evidence(out_text: str, ctx: dict[str, Any]) -> Any:
    data = parse_strict_json(out_text)
    if not isinstance(data, dict):
        return None
    grounding = str(ctx.get("grounding") or "")
    rows: dict[str, str] = ctx.get("_rows") or {}
    # e_id → its own source line, so name-presence is checked per-line
    line_by_eid = {}
    for ln in grounding.split("\n"):
        m = _E_ID_RE.search(ln)
        if m:
            line_by_eid[m.group(0)] = _norm(ln)
    out = []
    for item in (data.get("links") or [])[:24]:
        if not isinstance(item, dict):
            continue
        tid = str(item.get("tech_id") or "")
        name = rows.get(tid)
        if not name:
            continue
        # the cited line must name the product (or its vendor token)
        tokens = [t for t in _norm(name).split(" ") if len(t) >= 3]
        good = []
        for e in (item.get("e_ids") or [])[:4]:
            ln = line_by_eid.get(str(e), "")
            if ln and tokens and any(t in ln for t in tokens):
                good.append(str(e))
        if good:
            out.append({"tech_id": tid, "e_ids": good})
    return {"links": out} if out else None


async def _persist_tech_evidence(
    session: AsyncSession, did: str, payload: Any, provenance: dict[str, Any],
) -> int:
    written = 0
    for link in payload["links"]:
        n = await session.execute(text(
            """
            UPDATE tech_stack_entries SET
                evidence_e_ids = CAST(:evs AS VARCHAR[])
            WHERE id = CAST(:tid AS UUID)
              AND (evidence_e_ids IS NULL OR cardinality(evidence_e_ids) = 0)
            """), {"tid": link["tech_id"], "evs": link["e_ids"]})
        written += n.rowcount or 0
    return written


# ── 9. focus_grounding (D3.fa_no_grounding — 30 clients zero E-ID) ─────────
# Research reports without linkable evidence ids leave the focus heatmap
# ungrounded. Attach the entity's OWN evidence ids, validator-gated: a
# returned E-ID must exist in the bundle AND its excerpt must share ≥3
# significant tokens with the focus area's quote/title (topical relevance,
# not just id membership). The deterministic token-overlap fallback in
# focus_area_synthesizer.backfill fills the honest floor; this upgrades it.

_FOCUS_GROUNDING_TEMPLATE = """You attach EVIDENCE IDS to {entity_name}'s strategic focus areas — grounding each in the client's own research material.

FOCUS AREAS (no evidence links yet):
{focus_areas}

SOURCES — the ONLY citable evidence (each line starts with its evidence id):
{grounding}

Return STRICT JSON:
{{"grounding": [{{"fa_id": "<id from FOCUS AREAS>", "evidence_e_ids": ["E-###", ...]}}]}}

Rules:
- Attach an E-ID ONLY when its SOURCE line is genuinely ABOUT that focus area (shares its subject matter — not merely the same document). 1-4 ids per area.
- Every e_id MUST be one shown in SOURCES.
- Omit an area entirely when no source line relates — silence is honest."""


async def _ctx_focus_grounding(session: AsyncSession, did: str) -> dict[str, Any] | None:
    ent = await _entity_row(session, did)
    if ent.run_id is None:
        return None
    fas = (await session.execute(text(
        """
        SELECT fa.id, fa.title, fa.verbatim_quote,
               fa.grounding->>'representative_quote' AS rep_quote
        FROM focus_areas fa
        WHERE fa.run_id = :rid
          AND COALESCE(jsonb_array_length(fa.grounding->'evidence_e_ids'), 0) = 0
        ORDER BY fa.id LIMIT 8
        """), {"rid": str(ent.run_id)})).all()
    if not fas:
        return None                                   # every FA grounded — skip
    lines = await _evidence_lines(session, ent.entity_id, limit=30)
    if not lines:
        return None                                   # nothing citable
    fa_text = {str(r.id): " ".join(
        t for t in (r.title, r.rep_quote or r.verbatim_quote) if t) for r in fas}
    return {
        "entity_name": ent.name,
        "focus_areas": "\n".join(
            f"  - id={r.id}  {r.title}: \"{(r.rep_quote or r.verbatim_quote or '')[:220]}\""
            for r in fas),
        "grounding": _grounding_blob(lines),
        "recent_evidence": _grounding_blob(lines),
        "_fa_ids": [str(r.id) for r in fas],
        "_fa_text": fa_text,
    }


def _accept_focus_grounding(out_text: str, ctx: dict[str, Any]) -> Any:
    from app.services.focus_area_synthesizer import grounding_eid_supported
    data = parse_strict_json(out_text)
    if not isinstance(data, dict):
        return None
    grounding = str(ctx.get("grounding") or "")
    fa_ids = set(ctx.get("_fa_ids") or [])
    fa_text: dict[str, str] = ctx.get("_fa_text") or {}
    # e_id → its own source line, so relevance is checked per-excerpt
    line_by_eid: dict[str, str] = {}
    for ln in grounding.split("\n"):
        m = _E_ID_RE.search(ln)
        if m:
            line_by_eid[m.group(0)] = ln
    out = []
    for item in (data.get("grounding") or [])[:8]:
        if not isinstance(item, dict):
            continue
        fa_id = str(item.get("fa_id") or "")
        if fa_id not in fa_ids:
            continue
        good: list[str] = []
        for e in (item.get("evidence_e_ids") or [])[:4]:
            excerpt = line_by_eid.get(str(e))
            # validator: id must exist in the bundle AND its excerpt must
            # share ≥3 significant tokens with the FA quote/title
            if excerpt and grounding_eid_supported(fa_text.get(fa_id, ""), excerpt):
                good.append(str(e))
        if good:
            out.append({"fa_id": fa_id, "evidence_e_ids": good})
    return {"grounding": out} if out else None


async def _persist_focus_grounding(
    session: AsyncSession, did: str, payload: Any, provenance: dict[str, Any],
) -> int:
    """Fill-if-empty: merge evidence_e_ids + source_kind='gemini' +
    provenance into focus_areas.grounding, preserving representative_quote,
    only when the row still carries no evidence ids."""
    from app.services.focus_area_synthesizer import gemini_provenance
    written = 0
    model_id = provenance.get("model_id", "")
    for g in payload["grounding"]:
        patch = {
            "evidence_e_ids": g["evidence_e_ids"],
            "source_kind": "gemini",
            "provenance": gemini_provenance(
                "focus_grounding", model_id, g["evidence_e_ids"]),
        }
        n = await session.execute(text(
            """
            UPDATE focus_areas SET
                grounding = COALESCE(grounding, '{}'::jsonb) || CAST(:patch AS jsonb)
            WHERE id = CAST(:faid AS UUID)
              AND COALESCE(jsonb_array_length(grounding->'evidence_e_ids'), 0) = 0
            """), {"faid": g["fa_id"], "patch": json.dumps(patch)})
        written += n.rowcount or 0
    return written


# ── 10. focus_linked_insights (D3.fa_no_linked_insights) ───────────────────
# The deterministic linked_insights union (affects∩subcaps + co-citation +
# prose) covers most FAs; Gemini adjudicates the residual empty/ambiguous
# ones — cited card ids + E-IDs must be real.

_FOCUS_LINKED_TEMPLATE = """You decide which insight cards belong to {entity_name}'s strategic focus areas that have NO linked cards yet. Argue through the facts — link a card only when it genuinely advances the area's strategy.

FOCUS AREAS (no linked insight cards):
{focus_areas}

INSIGHT CARDS (the ONLY cards you may link; each starts with its id):
{cards}

Return STRICT JSON:
{{"links": [{{"fa_id": "<id from FOCUS AREAS>", "card_ids": ["<id from INSIGHT CARDS>", ...]}}]}}

Rules:
- Link a card ONLY when it advances that focus area's strategy. 1-4 cards per area.
- card_ids MUST come from INSIGHT CARDS.
- Omit an area when no card fits — never force a link."""


async def _ctx_focus_linked(session: AsyncSession, did: str) -> dict[str, Any] | None:
    ent = await _entity_row(session, did)
    if ent.run_id is None:
        return None
    fas = (await session.execute(text(
        """
        SELECT fa.id, fa.title, fa.verbatim_quote, fa.involved_subcap_ids
        FROM focus_areas fa
        WHERE fa.run_id = :rid
          AND COALESCE(jsonb_array_length(fa.linked_insights), 0) = 0
        ORDER BY fa.id LIMIT 8
        """), {"rid": str(ent.run_id)})).all()
    if not fas:
        return None
    cards = (await session.execute(text(
        """
        SELECT id, ic_id, title, severity, what_text,
               linked_subcap_id, linked_e_ids
        FROM insight_cards WHERE run_id = :rid ORDER BY ic_id LIMIT 40
        """), {"rid": str(ent.run_id)})).all()
    if not cards:
        return None
    card_meta = {str(c.id): {
        "id": str(c.id), "ic_id": c.ic_id, "title": c.title,
        "severity": c.severity, "linked_subcap_id": c.linked_subcap_id,
        "e_ids": list(c.linked_e_ids or []),
    } for c in cards}
    return {
        "entity_name": ent.name,
        "focus_areas": "\n".join(
            f"  - id={r.id}  {r.title}: \"{(r.verbatim_quote or '')[:200]}\""
            for r in fas),
        "cards": "\n".join(
            f"  - id={c.id}  [{c.ic_id}] {c.title}: {(c.what_text or '')[:120]}"
            for c in cards),
        "recent_evidence": "\n".join(
            f"{r.title} {(r.verbatim_quote or '')[:120]}" for r in fas),
        "_fa_ids": [str(r.id) for r in fas],
        "_card_meta": card_meta,
    }


def _accept_focus_linked(out_text: str, ctx: dict[str, Any]) -> Any:
    data = parse_strict_json(out_text)
    if not isinstance(data, dict):
        return None
    fa_ids = set(ctx.get("_fa_ids") or [])
    card_meta: dict[str, dict] = ctx.get("_card_meta") or {}
    out = []
    for item in (data.get("links") or [])[:8]:
        if not isinstance(item, dict):
            continue
        fa_id = str(item.get("fa_id") or "")
        if fa_id not in fa_ids:
            continue
        entries = []
        for cid in (item.get("card_ids") or [])[:4]:
            meta = card_meta.get(str(cid))
            if not meta:
                continue                              # fabricated card id
            entries.append({
                "id": meta["id"], "ic_id": meta["ic_id"],
                "title": meta["title"], "severity": meta["severity"],
                "linked_subcap_id": meta["linked_subcap_id"],
                "bases": [{"kind": "gemini", "detail": "adjudicated"}],
                "e_ids": meta["e_ids"][:4], "source": "gemini",
            })
        if entries:
            out.append({"fa_id": fa_id, "linked_insights": entries})
    return {"links": out} if out else None


async def _persist_focus_linked(
    session: AsyncSession, did: str, payload: Any, provenance: dict[str, Any],
) -> int:
    """Fill-if-empty: write the adjudicated linked_insights + a provenance
    envelope, only when the row still has none."""
    from app.services.focus_area_synthesizer import gemini_provenance
    written = 0
    model_id = provenance.get("model_id", "")
    for link in payload["links"]:
        prov = {"linked_insights": gemini_provenance(
            "focus_linked_insights", model_id,
            [e for li in link["linked_insights"] for e in li["e_ids"]])}
        n = await session.execute(text(
            """
            UPDATE focus_areas SET
                linked_insights = CAST(:li AS jsonb),
                enrichment_provenance = COALESCE(enrichment_provenance, '{}'::jsonb)
                    || CAST(:prov AS jsonb)
            WHERE id = CAST(:faid AS UUID)
              AND COALESCE(jsonb_array_length(linked_insights), 0) = 0
            """), {"faid": link["fa_id"],
                   "li": json.dumps(link["linked_insights"]),
                   "prov": json.dumps(prov)})
        written += n.rowcount or 0
    return written


# ── 11. firmographics_extraction (D1.firmographics_empty, ≤90 clients) ─────
# The operator report (2026-07-06): "majority clients have empty firmographics
# state not enriched during deployment ... queries to Gemini must cater for ALL
# empty states." Root cause: firmographics enrichment lived ONLY in the
# intelligence_builder / enrich_corpus path, which the deploy-time
# enrich_empty_surfaces SOFT_STEP never runs — so with the deterministic ladder
# (entity_healing) short of a field and Gemini WARM at deploy, nothing filled
# the residual empties. This query registers firmographics in THIS registry so
# the deploy sweep probes EVERY entity's empty enrichable firmographics fields
# and fills them, verbatim-quote gated, honest-null when the sources lack it,
# fill-if-empty per field (report/heal values always win).
#
# Every field carries its own verbatim-source quote; the acceptor drops any
# field whose quote is not a substring of the grounding excerpts (anti-
# fabrication, mirroring the E-ID check on prose surfaces) AND whose value fails
# a per-field format guard (year / percent / integer / ticker / host).
# Fields OWNED by app.scripts.enrich_unavailable (iterative + ledgered + 6-month
# refresh). This static firmographics query defers them to avoid token
# duplication — see _ctx_firmographics. (enrich_unavailable field → firmo key:
# headcount→employees_approx, hq_address→hq, founded_year→founded; aum_usd /
# primary_regulator are enrich_unavailable-only, not in this dict.)
_ENRICH_UNAVAILABLE_OWNED: frozenset[str] = frozenset(
    {"founded", "hq", "employees_approx"})
_FIRMO_ENRICH_FIELDS: dict[str, str] = {
    # field → the STRICT-JSON value example shown in the dynamic schema
    "website":          '{"value": "acme.com", "quote": "<verbatim excerpt fragment>"}',
    "founded":          '{"value": "YYYY", "quote": "..."}',
    "hq":               '{"value": "City, ST", "quote": "..."}',
    "cagr":             '{"value": "X%", "quote": "..."}',
    "branches":         '{"value": "N", "quote": "..."}',
    "employees_approx": '{"value": "N", "quote": "..."}',
    "ticker":           '{"value": "NYSE: XYZ", "quote": "..."}',
    "geography":        '{"value": "Texas (7 metros)", "quote": "..."}',
    "trend":            '{"value": "ACCELERATING|STABLE|DECLINING", "quote": "..."}',
}
_TREND_VALUES = {"ACCELERATING", "DECELERATING", "DECLINING", "STABLE", "VARIABLE"}

_FIRMO_TEMPLATE = """You are a precise data extractor for Zennify. From ONLY the report excerpts below about {entity_name}, extract the institution's OWN firmographics. NEVER use a figure that belongs to an acquired company, a peer, or a parent.

Report excerpts — the ONLY citable material; every value must quote one of these lines verbatim:
{report_excerpts}

The ONLY fields still unknown for this institution are: {missing_fields}. Output STRICT JSON (no prose, no markdown fences) with any SUBSET of EXACTLY these keys — OMIT a key entirely when the excerpts do not state it explicitly (absence is the correct, honest answer for a value the sources never disclose; a private or mutual institution has NO ticker, a branch-less manager has NO branches), and NEVER return a key outside this list:
{{{field_schema}}}

Every value MUST carry a `quote` copied verbatim from an excerpt line above; a value whose quote is absent from the excerpts is dropped."""


async def _ctx_firmographics(session: AsyncSession, did: str) -> dict[str, Any] | None:
    """Gap-driven grounding for the firmographics fill. Probes EVERY empty
    enrichable firmographics field (column-or-parsed_facts), returns None when
    none is empty (skip — no tokens) or nothing citable exists (honest-null).
    The prompt requests ONLY the still-missing fields, so the model never
    re-states report-owned values and the fill-if-empty merge can't be raced by
    a hallucinated "correction" of present data."""
    ent = await _entity_row(session, did)
    row = (await session.execute(text(
        """
        SELECT f.headcount, f.narrative_md, f.financial_highlights, f.parsed_facts
        FROM firmographics f WHERE f.entity_id = :eid
        """), {"eid": str(ent.entity_id)})).first()
    pf = (row.parsed_facts if row and row.parsed_facts else {}) or {}

    def _have(field: str) -> bool:
        if field == "employees_approx":
            return bool(row and row.headcount) or bool(
                str(pf.get("employees_approx") or "").strip())
        return bool(str(pf.get(field) or "").strip())

    # De-dup with app.scripts.enrich_unavailable (the iterative, ledgered,
    # safeguarded enricher): it OWNS founded / hq / headcount, so this static
    # query must never spend tokens on them (no double Gemini call for the same
    # datum). The fields stay in _FIRMO_ENRICH_FIELDS (acceptor/format guards
    # intact); they are only dropped from what this path REQUESTS.
    missing = [f for f in _FIRMO_ENRICH_FIELDS
               if not _have(f) and f not in _ENRICH_UNAVAILABLE_OWNED]
    if not missing:
        return None                                   # every field present — skip
    parts: list[str] = []
    if row and row.narrative_md:
        parts.append(str(row.narrative_md)[:4000])
    fh = (row.financial_highlights if row else None) or {}
    if isinstance(fh, dict):
        parts.extend(str(x) for x in (fh.get("lines") or [])[:30])
    secs = (await session.execute(text(
        """
        SELECT ds.body FROM document_sections ds
        JOIN runs r ON r.id = ds.run_id AND r.status = 'ACTIVE'
        WHERE ds.entity_id = :eid
          AND ds.section_kind IN ('executive_summary_scqa', 'trend_analysis',
                                  'benchmark_comparison')
        ORDER BY ds.ordinal LIMIT 6
        """), {"eid": str(ent.entity_id)})).all()
    parts.extend(str(s.body or "")[:3000] for s in secs)
    parts += await _evidence_lines(session, ent.entity_id, limit=14)
    excerpts = "\n".join(p for p in parts if p)[:14000]
    if not excerpts.strip():
        return None                                   # nothing citable — honest-null
    field_schema = ",\n ".join(f'"{k}": {_FIRMO_ENRICH_FIELDS[k]}' for k in missing)
    return {
        "entity_name": ent.name,
        "report_excerpts": excerpts,
        "grounding": excerpts,                        # acceptor haystack
        "recent_evidence": excerpts,                  # fingerprint carrier
        "missing_fields": ", ".join(missing),
        "field_schema": field_schema,
        "_missing": missing,
    }


def _clean_firmo_value(field: str, value: str) -> str | None:
    """Per-field format guard: a grounded-but-malformed value (a CEO-tenure year
    parsed as `founded`, a peer ticker, a non-own host) is dropped, so only a
    clean, well-typed value ever lands. Reuses the deterministic ladder's
    validated cleaners for website/ticker."""
    from app.services.entity_healing import clean_ticker, clean_website
    v = (value or "").strip()
    if not v:
        return None
    if field == "website":
        return clean_website(v)
    if field == "ticker":
        return clean_ticker(v)
    if field == "founded":
        m = re.search(r"\b(1[789]\d\d|20[0-2]\d)\b", v)
        return m.group(1) if m else None
    if field == "cagr":
        m = re.search(r"(\d{1,2}(?:\.\d{1,2})?)\s*%", v)
        if not m:
            return None
        f = float(m.group(1))
        return f"{f:g}%" if 0 < f < 60 else None
    if field == "trend":
        u = v.upper()
        return u if u in _TREND_VALUES else None
    if field in ("branches", "employees_approx"):
        m = re.search(r"\d[\d,]{0,6}", v)
        if not m:
            return None
        n = int(m.group(0).replace(",", ""))
        cap = 10000 if field == "branches" else 1_000_000
        return str(n) if 1 <= n <= cap else None
    if field == "hq":
        if "{" in v or "\n" in v or not (3 <= len(v) <= 60):
            return None
        return v
    if field == "geography":
        return v[:80] if 2 <= len(v) <= 80 and "{" not in v else None
    return v[:120]


def _accept_firmographics(out_text: str, ctx: dict[str, Any]) -> Any:
    """Keep only fields whose ``quote`` is a VERBATIM substring of the grounding
    excerpts AND whose value passes its per-field format guard. A field never in
    the requested-missing set is ignored (can't overwrite present data). Absence
    is legal — an empty result returns None (nothing persisted)."""
    data = parse_strict_json(out_text)
    if not isinstance(data, dict):
        return None
    hay = _norm(str(ctx.get("grounding") or ""))
    allowed = set(ctx.get("_missing") or _FIRMO_ENRICH_FIELDS)
    out: dict[str, str] = {}
    for field in _FIRMO_ENRICH_FIELDS:
        if field not in allowed:
            continue
        item = data.get(field)
        if not isinstance(item, dict):
            continue
        value = str(item.get("value") or "").strip()
        if not value or not _quote_in(str(item.get("quote") or ""), hay):
            continue
        cleaned = _clean_firmo_value(field, value)
        if cleaned:
            out[field] = cleaned
    return out or None


async def _persist_firmographics(
    session: AsyncSession, did: str, payload: Any, provenance: dict[str, Any],
) -> int:
    """Fill-if-empty per field into ``firmographics.parsed_facts`` — a value the
    report/heal ladder already set is never clobbered (re-checked at persist to
    beat a race). Each filled field is stamped ``{field}_basis='gemini:verbatim'``
    so the firmographics-provenance contract stays at 100%, and the shared
    ``_gemini_extracted`` marker + ``_fx_provenance`` envelope are merged."""
    ent = await _entity_row(session, did)
    row = (await session.execute(text(
        "SELECT headcount, parsed_facts FROM firmographics WHERE entity_id = :eid"),
        {"eid": str(ent.entity_id)})).first()
    if row is None:
        return 0
    pf = (row.parsed_facts or {}) or {}
    patch: dict[str, Any] = {}
    for field, value in payload.items():
        if field == "employees_approx":
            if row.headcount or str(pf.get("employees_approx") or "").strip():
                continue
        elif str(pf.get(field) or "").strip():
            continue
        patch[field] = value
        patch[f"{field}_basis"] = "gemini:verbatim"
    if not patch:
        return 0
    filled = [k for k in patch if not k.endswith("_basis")]
    patch["_gemini_extracted"] = sorted({*(pf.get("_gemini_extracted") or []), *filled})
    patch["_fx_provenance"] = provenance
    await session.execute(text(
        """
        UPDATE firmographics f SET
            parsed_facts = COALESCE(f.parsed_facts, '{}'::jsonb) || CAST(:pf AS JSONB),
            updated_at = NOW()
        FROM entities e
        WHERE e.id = f.entity_id AND e.display_id = :did
        """), {"did": did, "pf": json.dumps(patch)})
    return len(filled)


# ── the registry ───────────────────────────────────────────────────────────

ENRICHMENT_QUERIES: dict[str, EnrichmentQuery] = {
    # HIGHEST PRIORITY (tier 0): the operator's firmographics safeguard. Placed
    # first so a wall-clock budget cut trims it LAST — every entity's empty
    # firmographics is probed before any lower-ranked empty class.
    "firmographics_extraction": EnrichmentQuery(
        surface="firmographics_extraction", model="flash",
        empty_class="D1.firmographics_empty",
        description="Fills EVERY empty enrichable firmographics field (website, "
                    "founded, cagr, branches, hq, employees, ticker-where-"
                    "public, geography, trend) from the entity's OWN report "
                    "excerpts — per-field verbatim-quote + format gated, honest-"
                    "null when the sources lack it, fill-if-empty per field.",
        template=_FIRMO_TEMPLATE,
        build_ctx=_ctx_firmographics, accept=_accept_firmographics,
        persist=_persist_firmographics,
    ),
    "sentiment_extraction": EnrichmentQuery(
        surface="sentiment_extraction", model="flash",
        empty_class="D1.sentiment_card",
        description="Structured employee/customer review ratings from the "
                    "entity's own review-bearing evidence.",
        template=_SENTIMENT_TEMPLATE,
        build_ctx=_ctx_sentiment, accept=_accept_sentiment,
        persist=_persist_sentiment,
    ),
    "acquisition_extraction": EnrichmentQuery(
        surface="acquisition_extraction", model="flash",
        empty_class="D5.acquisitions_zero",
        description="M&A frames (acquirer+target+status) or a VERIFIED-"
                    "absent marker so the empty card gains provenance.",
        template=_ACQ_TEMPLATE,
        build_ctx=_ctx_acquisitions, accept=_accept_acquisitions,
        persist=_persist_acquisitions,
    ),
    "financial_series_extraction": EnrichmentQuery(
        surface="financial_series_extraction", model="flash",
        empty_class="D5.fin_no_multiyear",
        description="Explicit year→value series from highlight prose / "
                    "trend sections; anti-interpolation gated.",
        template=_FIN_SERIES_TEMPLATE,
        build_ctx=_ctx_fin_series, accept=_accept_fin_series,
        persist=_persist_fin_series,
    ),
    "timeline_event_extraction": EnrichmentQuery(
        surface="timeline_event_extraction", model="flash",
        empty_class="D5.timeline_lt3",
        description="Dated, polarity-classified events for timeline-thin "
                    "clients; date-in-quote gated.",
        template=_TIMELINE_TEMPLATE,
        build_ctx=_ctx_timeline, accept=_accept_timeline,
        persist=_persist_timeline,
    ),
    "insight_card_generation": EnrichmentQuery(
        surface="insight_card_generation", model="pro",
        empty_class="D2.cards_lt5",
        description="Evidence-grounded W/W/SW insight cards up to 5 for "
                    "report-poor clients; subcap+E-ID validated.",
        template=_INSIGHT_TEMPLATE,
        build_ctx=_ctx_insight_gen, accept=_accept_insight_gen,
        persist=_persist_insight_gen,
    ),
    "focus_kpi_extraction": EnrichmentQuery(
        surface="focus_kpi_extraction", model="flash",
        empty_class="D3.kpis_all_empty",
        description="Per-FA reasoned KPI rows: current from a DISCLOSED "
                    "value+E-ID, target from a roadmap-uplift; wrong KPIs "
                    "rejected (current-in-cited + target-uplift gated). "
                    "Completes partial rows (no whole-entity skip).",
        template=_FOCUS_KPI_TEMPLATE,
        build_ctx=_ctx_focus_kpis, accept=_accept_focus_kpis,
        persist=_persist_focus_kpis,
    ),
    "focus_grounding": EnrichmentQuery(
        surface="focus_grounding", model="flash",
        empty_class="D3.fa_no_grounding",
        description="Attaches the entity's own evidence ids to focus areas "
                    "with zero grounding; id-in-bundle + ≥3-shared-token "
                    "relevance gated (source_kind='gemini').",
        template=_FOCUS_GROUNDING_TEMPLATE,
        build_ctx=_ctx_focus_grounding, accept=_accept_focus_grounding,
        persist=_persist_focus_grounding,
    ),
    "focus_linked_insights": EnrichmentQuery(
        surface="focus_linked_insights", model="flash",
        empty_class="D3.fa_no_linked_insights",
        description="Gemini-adjudicated insight-card links for focus areas "
                    "the deterministic union left empty; real card-id + "
                    "E-ID gated.",
        template=_FOCUS_LINKED_TEMPLATE,
        build_ctx=_ctx_focus_linked, accept=_accept_focus_linked,
        persist=_persist_focus_linked,
    ),
    "focus_subcap_classification": EnrichmentQuery(
        surface="focus_subcap_classification", model="flash",
        empty_class="D3.fa_no_subcaps",
        description="Semantic mapping of unlinked focus areas onto the "
                    "run's scored subcaps (fixes the '-' score chip).",
        template=_FA_SUBCAP_TEMPLATE,
        build_ctx=_ctx_fa_subcaps, accept=_accept_fa_subcaps,
        persist=_persist_fa_subcaps,
    ),
    "techstack_evidence_linking": EnrichmentQuery(
        surface="techstack_evidence_linking", model="flash",
        empty_class="D6.rows_no_evidence",
        description="Links detected tech rows to the evidence lines that "
                    "literally name the product/vendor.",
        template=_TECH_EVIDENCE_TEMPLATE,
        build_ctx=_ctx_tech_evidence, accept=_accept_tech_evidence,
        persist=_persist_tech_evidence,
    ),
}

__all__ = ["ENRICHMENT_QUERIES", "EnrichmentQuery", "parse_strict_json"]
