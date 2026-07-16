"""Deploy-time Gemini enrichment for the data-UNAVAILABILITY gaps.

The 95-client stress-test split every empty surface into *extraction* bugs (the
fact is in the client's own package — fixed in the derive scripts) and *genuine
unavailability* (the package carries no signal at all: headcount for 9 clients, a
non-US HQ, the thin ``atb-a8f3`` ingest). The mandate: an unavailable datum must
be Gemini-enriched, never left blank and never fabricated.

This module is the dedicated PROMPT FORMULATOR + ITERATIVE acquisition loop:

  * :func:`formulate_prompt` crafts a grounded, anti-hallucination prompt — it
    states what we already KNOW (to disambiguate the entity), asks for ONE
    specific datum, and REQUIRES a verbatim source sentence + source URL +
    as-of date + a 0-1 confidence, with an explicit ``found:false`` escape so the
    model returns nothing rather than guessing.
  * :func:`assess` grades a response for sufficiency (value present, sourced,
    confidence over the bar) and names exactly what is missing.
  * :func:`enrich_gap` runs the loop: on a weak/un-sourced answer it formulates a
    TARGETED follow-up question naming the deficiency and re-asks, up to
    ``max_rounds``. A sufficient answer returns ``found=True``; a model that
    reliably reports the datum does not exist returns ``found=False`` (a durable
    honest-null); an offline/cold/erroring client or an exhausted-unclear loop
    returns ``None`` (the caller keeps the field null and may retry next deploy).
  * :func:`persist_enrichment` writes a sufficient outcome back three ways so it
    joins the same evidence contract every other fact obeys: the column value, a
    CITABLE ``evidence_index`` row (the verbatim quote + source → it appears in
    the AE's evidence drawer), and an ``ai_enrichments`` provenance row.

Offline-safe + DI-testable: pass a stub ``client`` with an async ``stream`` that
yields JSON chunks. A cold Vertex client (``DMA_DISABLE_VERTEX`` / no project)
raises inside ``stream`` and the loop resolves to ``None`` — so a creds-less
deploy degrades to honest-null instead of hanging.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_SUBVERTICAL_LABEL = {
    "RB": "retail bank", "CB": "commercial bank", "CU": "credit union",
    "PB": "private bank", "IC": "insurance carrier", "IB": "insurance broker",
    "WM": "wealth manager", "RIA": "registered investment adviser",
    "AM": "asset manager", "FINTECH_SAAS": "fintech / SaaS provider",
    "CL": "commercial lender",
}


@dataclass
class EnrichmentGap:
    """One unavailable datum to acquire for a known entity."""
    entity_name: str
    subvertical: str
    field: str                      # firmographics column / logical key
    surface: str                    # ai_enrichments.surface tag
    want: str                       # human description of the datum sought
    unit_hint: str = ""             # e.g. "an integer employee count"
    quality_hints: tuple[str, ...] = ()   # field-specific disambiguation/quality
    known_context: dict[str, Any] = field(default_factory=dict)
    min_confidence: float = 0.7


@dataclass(frozen=True)
class FieldSpec:
    """A registry entry describing how to enrich one single-datum field: the
    tailored ask, the coercion kind, the firmographics column (or None ⇒ write
    into parsed_facts), and field-specific quality hints. New entries extend
    coverage automatically — the gap builder is data-driven, not a hard-coded
    pair."""
    field: str
    surface: str
    want: str
    unit_hint: str
    quality_hints: tuple[str, ...]
    value_kind: str                 # int | str | usd | year
    column: str | None              # firmographics column, or None ⇒ parsed_facts
    parsed_facts_key: str | None = None   # read/write key when column is None


@dataclass
class EnrichmentOutcome:
    """The result of an acquisition loop. ``found`` distinguishes a sufficient
    hit (True) from a model-confirmed absence (False)."""
    found: bool
    field: str
    value: Any = None
    unit: str | None = None
    quote: str | None = None
    source_url: str | None = None
    source_name: str | None = None
    published_date: str | None = None
    confidence: float = 0.0
    rounds: int = 0
    model: str = "flash"


# The structured-output contract (Vertex response_schema + our validator).
RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "value": {"type": "string"},
        "unit": {"type": "string"},
        "quote": {"type": "string"},
        "source_url": {"type": "string"},
        "source_name": {"type": "string"},
        "published_date": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["found"],
}


def _known_lines(gap: EnrichmentGap) -> str:
    keep = ("aum_usd", "revenue_usd", "headcount", "hq_address", "region",
            "footprint", "primary_regulator", "founded", "website", "branches",
            "subvertical")
    ctx = {**gap.known_context}
    ctx.setdefault("subvertical", _SUBVERTICAL_LABEL.get(gap.subvertical, gap.subvertical))
    lines = [f"  - {k}: {v}" for k in keep if (v := ctx.get(k)) not in (None, "", [], {})]
    return "\n".join(lines) or "  - (only the legal name is known)"


# The model conditioning + safeguards shared by every gap-kind. Kept in one
# place so a tightened safeguard applies to ALL surfaces at once.
_ROLE = (
    "You are a meticulous financial-services research analyst enriching a "
    "Digital Maturity Assessment for a Salesforce account team. You value being "
    "CORRECT over being complete: a wrong figure misleads a live sales pitch, so "
    "you would rather return nothing than a guess.")
_SCHEMA = (
    '{"found": true|false, "value": "<the datum>", "unit": "<unit or empty>", '
    '"quote": "<verbatim source sentence>", "source_url": "<url>", '
    '"source_name": "<publisher/site>", "published_date": "<YYYY or YYYY-MM-DD>", '
    '"confidence": <0.0-1.0>}')


def _rules(gap: EnrichmentGap) -> str:
    base = [
        "SAFEGUARDS:",
        "- SOURCE: use ONLY authoritative primary sources — the company's own "
        "website/newsroom, a regulator filing (NCUA/FDIC/OCC/SEC/state DOI), a "
        "10-K / annual report, or the official LinkedIn company page. No blogs, "
        "aggregators, or unnamed sources.",
        "- RECENCY: prefer the MOST RECENT figure available; report its "
        "publication / as-of date. If the only source is older than ~3 years, "
        "still return it but LOWER the confidence and note the age in the quote.",
        "- NO HALLUCINATION: return the VERBATIM sentence you took the value from "
        "and a source_url you are confident RESOLVES — never invent or approximate "
        "a URL, a figure, or a quote. If sources conflict, take the most "
        "authoritative and lower confidence.",
        "- HONESTY: if you cannot find it in a reliable source, return "
        '{"found": false}. NEVER guess, estimate, extrapolate, or infer.',
        "- CALIBRATION: confidence 0.0-1.0 must reflect source authority AND "
        "recency (a dated secondary source is < 0.6).",
    ]
    for h in gap.quality_hints:
        base.append(f"- {h}")
    base.append(f"Return ONLY JSON in this exact shape:\n{_SCHEMA}")
    return "\n".join(base)


def formulate_prompt(gap: EnrichmentGap, prior: list[dict] | None = None) -> str:
    """Craft the acquisition prompt — dynamic per gap. It CONDITIONS the model
    (role + correctness-over-completeness stance), states the grounded context,
    poses the tailored query, and appends the shared safeguards (source /
    recency / no-hallucination / honesty / calibration) plus any field-specific
    quality hints. A follow-up (``prior`` non-empty) names the exact deficiency
    of the last answer and demands a corrected, sourced reply."""
    label = _SUBVERTICAL_LABEL.get(gap.subvertical, gap.subvertical)
    rules = _rules(gap)
    if prior:
        last = prior[-1]
        missing = ", ".join(last.get("_missing", [])) or "insufficient sourcing/confidence"
        return (
            f"{_ROLE}\n\n"
            f"Your previous answer for '{gap.want}' about {gap.entity_name} "
            f"({label}) was INSUFFICIENT — it lacked: {missing}.\n"
            f"Previous answer: {json.dumps({k: v for k, v in last.items() if not k.startswith('_')})}\n\n"
            "Provide a corrected answer that fixes EXACTLY those gaps. A primary "
            "source URL and the verbatim source sentence are REQUIRED, and "
            "confidence must reflect the source's authority and recency. If no "
            f"reliable source exists, return {{\"found\": false}}.\n\n{rules}")
    return (
        f"{_ROLE}\n\n"
        f"TASK: find ONE specific, verifiable, CURRENT fact.\n"
        f"COMPANY: {gap.entity_name} ({label})\n"
        f"WHAT WE ALREADY KNOW (use to disambiguate the right entity — do not "
        f"repeat it back):\n{_known_lines(gap)}\n\n"
        f"FIND: {gap.want}"
        + (f" ({gap.unit_hint})" if gap.unit_hint else "")
        + f"\n\n{rules}")


def parse_response(raw: str | None) -> dict | None:
    """Tolerant JSON extraction (fenced/`prose {json} prose`). None when no
    object or no ``found`` key is present."""
    s = (raw or "").strip()
    if not s or "OFFLINE" in s[:40].upper():
        return None
    s = re.sub(r"^```(?:json)?|```$", "", s.strip(), flags=re.I | re.M).strip()
    start, depth, out = s.find("{"), 0, None
    if start >= 0:
        for i in range(start, len(s)):
            if s[i] == "{":
                depth += 1
            elif s[i] == "}":
                depth -= 1
                if depth == 0:
                    out = s[start:i + 1]
                    break
    if not out:
        return None
    try:
        obj = json.loads(out)
    except (ValueError, TypeError):
        return None
    return obj if isinstance(obj, dict) and "found" in obj else None


def assess(gap: EnrichmentGap, parsed: dict) -> list[str]:
    """Return the list of deficiencies (empty ⇒ sufficient). Only applies when
    the model claims ``found: true``."""
    missing: list[str] = []
    if str(parsed.get("value", "")).strip() == "":
        missing.append("a concrete value")
    if not str(parsed.get("source_url", "")).strip() and not str(parsed.get("quote", "")).strip():
        missing.append("a source URL or a verbatim quote")
    try:
        conf = float(parsed.get("confidence", 0) or 0)
    except (ValueError, TypeError):
        conf = 0.0
    if conf < gap.min_confidence:
        missing.append(f"confidence >= {gap.min_confidence:g} (was {conf:g})")
    return missing


async def _collect(client: Any, prompt: str, model: str) -> str | None:
    """Stream one Gemini turn to a string. Any cold/offline/erroring client → None."""
    try:
        from app.services.vertex_client import GeminiCall
        chunks: list[str] = []
        async for part in client.stream(GeminiCall(
                surface="enrichment", model=model, prompt=prompt,
                response_schema=RESPONSE_SCHEMA, max_output_tokens=1024)):
            chunks.append(part)
        return "".join(chunks)
    except Exception:
        return None


async def enrich_gap(
    gap: EnrichmentGap, *, client: Any, model: str = "flash", max_rounds: int = 3,
) -> EnrichmentOutcome | None:
    """Iteratively acquire ``gap`` from Gemini. Returns a ``found=True`` outcome
    when an answer is sufficient, a ``found=False`` outcome when the model
    reliably reports the datum does not exist, or ``None`` when the client is
    offline/erroring or the loop exhausts without a clear result."""
    if client is None:
        return None
    prior: list[dict] = []
    for r in range(1, max_rounds + 1):
        prompt = formulate_prompt(gap, prior)
        raw = await _collect(client, prompt, model)
        if raw is None:
            return None
        parsed = parse_response(raw)
        if parsed is None:
            prior.append({"_missing": ["valid JSON in the required shape"]})
            continue
        if parsed.get("found") is False:
            return EnrichmentOutcome(found=False, field=gap.field, rounds=r, model=model)
        missing = assess(gap, parsed)
        if not missing:
            try:
                conf = float(parsed.get("confidence", 0) or 0)
            except (ValueError, TypeError):
                conf = 0.0
            return EnrichmentOutcome(
                found=True, field=gap.field, value=str(parsed.get("value", "")).strip(),
                unit=(str(parsed.get("unit", "")).strip() or None),
                quote=(str(parsed.get("quote", "")).strip() or None),
                source_url=(str(parsed.get("source_url", "")).strip() or None),
                source_name=(str(parsed.get("source_name", "")).strip() or None),
                published_date=(str(parsed.get("published_date", "")).strip() or None),
                confidence=conf, rounds=r, model=model)
        parsed["_missing"] = missing
        prior.append(parsed)
    return None


# ── the enrichable-field registry (data-driven coverage) ────────────────────
# Each single-datum surface the stress-test classed as UNAVAILABILITY. Adding a
# spec here automatically extends prompt-formulation, gap discovery, coercion,
# and persistence — no other code changes. Deliberately EXCLUDES revenue for
# deposit-taking LOBs (assets is their scale metric; enriching revenue would be
# semantically wrong — see the 2026-07-09 classification).
FIELD_SPECS: dict[str, FieldSpec] = {
    "headcount": FieldSpec(
        field="headcount", surface="firmographics_enrichment",
        want="the total number of employees (approximate full-time headcount)",
        unit_hint="an integer employee count",
        quality_hints=(
            "COUNT the whole institution's staff, not one branch or a parent's "
            "total; prefer a full-time-equivalent figure and exclude independent "
            "contractors when the source distinguishes them.",),
        value_kind="int", column="headcount"),
    "hq_address": FieldSpec(
        field="hq_address", surface="firmographics_enrichment",
        want="the headquarters city and state/province (the primary corporate HQ)",
        unit_hint="a 'City, ST' location",
        quality_hints=(
            "Return the CORPORATE headquarters city — not a branch, a mailing PO "
            "box, or a parent/subsidiary's HQ. 'City, ST' (or 'City, Province, "
            "Country' outside the US).",),
        value_kind="str", column="hq_address"),
    "aum_usd": FieldSpec(
        field="aum_usd", surface="firmographics_enrichment",
        want="total assets (or assets under management) from the latest balance sheet",
        unit_hint="a USD amount with unit, e.g. $4.3B",
        quality_hints=(
            "Use the MOST RECENT reported total assets / AUM; state the fiscal "
            "period. Do not use a peer-cohort band or a market-cap figure.",),
        value_kind="usd", column="aum_usd"),
    "primary_regulator": FieldSpec(
        field="primary_regulator", surface="firmographics_enrichment",
        want="the primary prudential regulator",
        unit_hint="e.g. NCUA / FDIC / OCC / a state DOI / SEC",
        quality_hints=(
            "Name the PRIMARY federal or state prudential regulator for this "
            "charter type (NCUA for federal CUs, FDIC/OCC/Fed for banks, a state "
            "DOI for insurers, SEC/FINRA for broker-dealers).",),
        value_kind="str", column="primary_regulator"),
    "founded_year": FieldSpec(
        field="founded_year", surface="firmographics_enrichment",
        want="the year the institution was founded or chartered",
        unit_hint="a 4-digit year",
        quality_hints=(
            "The founding/charter year of THIS institution — not a parent, a "
            "rebrand, or a merger date.",),
        value_kind="year", column=None, parsed_facts_key="founded"),
}
_USD_MULT = {"B": 1e9, "M": 1e6, "K": 1e3, "T": 1e12}
# Short evidence-id codes (evidence_index.e_id is varchar(16); "E-GEM-" + code).
_FIELD_EID = {"headcount": "HC", "hq_address": "HQ", "aum_usd": "AUM",
              "primary_regulator": "REG", "founded_year": "FND"}


def coerce_value(value: str, unit: str | None, kind: str) -> Any:
    """Coerce Gemini's string value to the column type; None when implausible."""
    v = (value or "").strip()
    if kind == "str":
        return v[:120] or None
    if kind == "year":
        m = re.search(r"\b(1[6-9]\d\d|20[0-2]\d)\b", v)
        return int(m.group(1)) if m else None
    if kind == "int":
        m = re.search(r"[\d,]{2,}", v)
        n = int(m.group(0).replace(",", "")) if m else None
        return n if n and 1 <= n <= 5_000_000 else None
    if kind == "usd":
        m = re.search(r"([\d.,]+)\s*([BMKT])?", v + " " + (unit or ""))
        if not m:
            return None
        try:
            num = float(m.group(1).replace(",", ""))
        except ValueError:
            return None
        mult = _USD_MULT.get((m.group(2) or "").upper(), 1.0 if num > 1e5 else 1e9)
        out = num * mult
        return out if out > 1e4 else None
    return v or None


async def persist_enrichment(
    session: AsyncSession, *, gap: EnrichmentGap, outcome: EnrichmentOutcome,
    run_id: str, entity_id: str, catalogue_version: str = "v7.0",
) -> str | None:
    """Write a ``found=True`` outcome three ways: the firmographics column (if
    mapped, never clobbering an existing value), a CITABLE ``evidence_index`` row
    (so the fact appears in the AE's evidence drawer), and an ``ai_enrichments``
    provenance row. Returns the synthesized E-ID, or None if nothing was written
    (not found / value did not coerce)."""
    if not outcome.found:
        return None
    # evidence_index.e_id is varchar(16): use a short, stable per-field code so
    # long field names (primary_regulator, founded_year) never overflow.
    e_id = f"E-GEM-{_FIELD_EID.get(gap.field, gap.field.upper()[:8])}"
    # quality gate: consultant-grade language + text cleanup on the stored quote.
    from app.services.enrichment_quality import contradiction as _contradiction
    from app.services.enrichment_quality import vet_text
    excerpt = vet_text(outcome.quote or f"{gap.want}: {outcome.value}")[0][:1000]
    source_name = (outcome.source_name or "Gemini enrichment")[:200]
    content_hash = hashlib.sha256(
        f"{outcome.source_url or ''}|enrichment|{excerpt[:500]}".encode()).hexdigest()

    await session.execute(text("""
        INSERT INTO evidence_index (run_id, entity_id, e_id, tier, excerpt,
            source_name, source_url, claim_type, published_date, linked_subcap_ids,
            content_hash, created_at)
        VALUES (CAST(:rid AS uuid), CAST(:eid AS uuid), :e, 4, :exc, :sn, :su,
            'ai_enrichment', :pd, '{}', :ch, NOW())
        ON CONFLICT (run_id, e_id) DO UPDATE SET
            excerpt = EXCLUDED.excerpt, source_name = EXCLUDED.source_name,
            source_url = EXCLUDED.source_url, published_date = EXCLUDED.published_date,
            content_hash = EXCLUDED.content_hash
    """), {"rid": run_id, "eid": entity_id, "e": e_id, "exc": excerpt,
           "sn": source_name, "su": outcome.source_url,
           "pd": _date_or_none(outcome.published_date), "ch": content_hash})

    spec = FIELD_SPECS.get(gap.field)
    # Contradiction fence: both writes below KEEP the existing corpus value
    # (COALESCE / empty-guard) so a differing enriched value would otherwise be
    # dropped SILENTLY. Read the current value first and, when the enrichment
    # conflicts with it, surface the conflict on the provenance row instead of
    # hiding it (the "never brush a contradiction under the rug" contract).
    contradiction_note: str | None = None
    if spec is not None:
        coerced = coerce_value(str(outcome.value), outcome.unit, spec.value_kind)
        if coerced is not None and spec.column:
            # a fixed allow-list of columns — never interpolated from input.
            cur = (await session.execute(text(
                f"SELECT {spec.column} AS v FROM firmographics "
                "WHERE entity_id = CAST(:eid AS uuid)"), {"eid": entity_id})).first()
            if cur is not None and cur.v is not None and str(cur.v).strip():
                contradiction_note = _contradiction(str(coerced), str(cur.v))
            await session.execute(text(
                f"UPDATE firmographics SET {spec.column} = COALESCE({spec.column}, :v), "
                "updated_at = NOW() WHERE entity_id = CAST(:eid AS uuid)"),
                {"v": coerced, "eid": entity_id})
        elif coerced is not None and spec.parsed_facts_key:
            # parsed_facts-only field: merge the key ONLY when currently empty
            # (never clobber an extracted value) + stamp provenance. The merge is a
            # JSON string param so asyncpg needn't infer a jsonb element type.
            cur = (await session.execute(text(
                "SELECT parsed_facts->>:k AS v FROM firmographics "
                "WHERE entity_id = CAST(:eid AS uuid)"),
                {"k": spec.parsed_facts_key, "eid": entity_id})).first()
            if cur is not None and cur.v is not None and str(cur.v).strip():
                contradiction_note = _contradiction(str(coerced), str(cur.v))
            merge = json.dumps({
                spec.parsed_facts_key: coerced,
                f"{spec.parsed_facts_key}_basis": "gemini_enrichment"})
            await session.execute(text(
                "UPDATE firmographics SET "
                "parsed_facts = COALESCE(parsed_facts, '{}'::jsonb) || CAST(:m AS jsonb), "
                "updated_at = NOW() "
                "WHERE entity_id = CAST(:eid AS uuid) "
                "  AND COALESCE(parsed_facts->>:k, '') = ''"),
                {"m": merge, "k": spec.parsed_facts_key, "eid": entity_id})

    # When the enrichment contradicts a kept corpus value, store the note ON the
    # provenance row and mark validators_passed=FALSE so the conflict is visible
    # for review — the corpus value was kept (COALESCE), never silently replaced.
    enr_text, validators_ok = excerpt, True
    if contradiction_note:
        enr_text = f"{contradiction_note}\n\n{excerpt}"[:2000]
        validators_ok = False
    await session.execute(text("""
        INSERT INTO ai_enrichments (target_kind, target_id, surface, model,
            enrichment_text, grounding_evidence_ids, grounding_subcap_ids,
            confidence, validators_passed, catalogue_version, created_at)
        VALUES ('entity', CAST(:eid AS uuid), :surface, :model, :txt,
            ARRAY[:e], '{}', :conf, :vp, :cv, NOW())
    """), {"eid": entity_id, "surface": gap.surface, "model": outcome.model,
           "txt": enr_text, "e": e_id, "conf": outcome.confidence,
           "vp": validators_ok, "cv": catalogue_version})
    return e_id


def _date_or_none(raw: str | None) -> _dt.date | None:
    """Accept a YYYY or YYYY-MM-DD → a ``date`` (YYYY → Jan 1). asyncpg binds a
    real date object; a bare string trips its date codec."""
    s = (raw or "").strip()
    try:
        if re.fullmatch(r"\d{4}", s):
            return _dt.date(int(s), 1, 1)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            return _dt.date.fromisoformat(s)
    except ValueError:
        return None
    return None


def _field_is_empty(spec: FieldSpec, fm: dict, pf: dict) -> bool:
    """A registry field is a gap when its current value is empty — a null column
    or a missing/blank parsed_facts key."""
    val = fm.get(spec.column) if spec.column else pf.get(spec.parsed_facts_key)
    if isinstance(val, str):
        return val.strip() == ""
    return val in (None, 0, [], {})


def build_unavailability_gaps(
    *, entity_name: str, subvertical: str, firmographics: dict[str, Any],
) -> list[EnrichmentGap]:
    """Registry-driven: one gap per FIELD_SPEC whose value is genuinely empty for
    this entity. Data-driven so a newly-registered field is picked up
    automatically and NO surface is silently skipped. The known-context anchor is
    assembled once and shared, so each prompt disambiguates the right entity."""
    fm = firmographics or {}
    pf = fm.get("parsed_facts") if isinstance(fm.get("parsed_facts"), dict) else {}
    known = {
        "aum_usd": fm.get("aum_usd"), "revenue_usd": fm.get("revenue_usd"),
        "headcount": fm.get("headcount"), "hq_address": fm.get("hq_address"),
        "primary_regulator": fm.get("primary_regulator"),
        "founded": pf.get("founded"), "website": pf.get("website"),
        "footprint": pf.get("footprint"), "region": pf.get("geography"),
        "branches": pf.get("branches"),
    }
    gaps: list[EnrichmentGap] = []
    for spec in FIELD_SPECS.values():
        if _field_is_empty(spec, fm, pf):
            gaps.append(EnrichmentGap(
                entity_name=entity_name, subvertical=subvertical,
                field=spec.field, surface=spec.surface, want=spec.want,
                unit_hint=spec.unit_hint, quality_hints=spec.quality_hints,
                known_context=known))
    return gaps


# ── the enrichment ledger — durable per-gap tracking + re-probe ─────────────
# One row per (entity, field) in ``enrichment_ledger``. The runner reads it to
# skip resolved gaps and (re)probe unresolved ones with backoff, so a deploy
# never leaves a surface un-attempted and a cold-Vertex deploy simply defers.
_ACTIVE_STATUSES = ("pending", "deferred", "failed")


async def ensure_pending(
    session: AsyncSession, entity_id: str, gaps: list[EnrichmentGap],
) -> None:
    """Register every current gap as ``pending`` (idempotent). Guarantees the
    ledger lists EVERY discovered gap even if a run is budget-capped before it
    reaches one — so nothing is silently dropped."""
    for g in gaps:
        await session.execute(text(
            "INSERT INTO enrichment_ledger (entity_id, field, surface, status) "
            "VALUES (CAST(:e AS uuid), :f, :s, 'pending') "
            "ON CONFLICT (entity_id, field) DO NOTHING"),
            {"e": entity_id, "f": g.field, "s": g.surface})


# A vetted, stored enrichment is trusted for 6 months before a refresh re-probe —
# so a re-deploy never re-spends tokens on an already-resolved datum, yet the
# corpus stays current as a client's business changes (the operator's "unless 6
# months have elapsed" rule).
REFRESH_AFTER = _dt.timedelta(days=182)


async def ledger_for_entity(session: AsyncSession, entity_id: str) -> dict[str, dict]:
    """Current ledger rows for an entity, keyed by field."""
    rows = (await session.execute(text(
        "SELECT field, status, attempts, next_probe_after, last_attempt_at, "
        "evidence_e_id FROM enrichment_ledger WHERE entity_id = CAST(:e AS uuid)"),
        {"e": entity_id})).all()
    return {r.field: {"status": r.status, "attempts": r.attempts,
                      "next_probe_after": r.next_probe_after,
                      "last_attempt_at": r.last_attempt_at,
                      "evidence_e_id": r.evidence_e_id} for r in rows}


def is_due(row: dict | None, now: _dt.datetime) -> bool:
    """Whether a gap should be (re)probed this run:
      * never-seen → probe;
      * active (pending/deferred/failed) past its backoff → re-probe;
      * resolved (enriched/absent) → SKIP until ``REFRESH_AFTER`` (6 months) has
        elapsed since the last attempt, then refresh (the datum may have moved).
    A stored, vetted enrichment inside the window costs zero tokens."""
    if row is None:
        return True
    if row["status"] in _ACTIVE_STATUSES:
        npa = row["next_probe_after"]
        return npa is None or npa <= now
    # resolved (enriched/absent): refresh only after the 6-month window
    last = row.get("last_attempt_at")
    return last is not None and (now - last) >= REFRESH_AFTER


async def record_attempt(
    session: AsyncSession, *, entity_id: str, run_id: str | None, field: str,
    surface: str, status: str, rounds: int = 0, confidence: float | None = None,
    evidence_e_id: str | None = None, value_preview: str | None = None,
    error: str | None = None, backoff_hours: int = 0,
) -> None:
    """UPSERT the ledger row for one attempt: set status, bump attempts, stamp
    the outcome + a backoff gate (``next_probe_after``) for re-probeable states."""
    await session.execute(text("""
        INSERT INTO enrichment_ledger (entity_id, run_id, field, surface, status,
            attempts, rounds, confidence, evidence_e_id, value_preview, last_error,
            next_probe_after, last_attempt_at, updated_at)
        VALUES (CAST(:e AS uuid), CAST(:rid AS uuid), :f, :s, :st, 1, :r, :c, :eid,
            :vp, :err,
            CASE WHEN :bh > 0 THEN NOW() + make_interval(hours => :bh) ELSE NULL END,
            NOW(), NOW())
        ON CONFLICT (entity_id, field) DO UPDATE SET
            run_id = EXCLUDED.run_id, surface = EXCLUDED.surface,
            status = EXCLUDED.status,
            attempts = enrichment_ledger.attempts + 1,
            rounds = EXCLUDED.rounds, confidence = EXCLUDED.confidence,
            evidence_e_id = COALESCE(EXCLUDED.evidence_e_id, enrichment_ledger.evidence_e_id),
            value_preview = EXCLUDED.value_preview, last_error = EXCLUDED.last_error,
            next_probe_after = EXCLUDED.next_probe_after,
            last_attempt_at = NOW(), updated_at = NOW()
    """), {"e": entity_id, "rid": run_id, "f": field, "s": surface, "st": status,
           "r": rounds, "c": confidence, "eid": evidence_e_id,
           "vp": (value_preview or "")[:200] or None,
           "err": (error or "")[:500] or None, "bh": backoff_hours})
