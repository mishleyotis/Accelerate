"""Per-subcap narrative extractor (Gemini Pro structured output).

The existing heuristic in ``section_routing.build_narrative_heatmap``
splits a pillar deep-dive body on ``\\n\\n`` and pairs each paragraph
with the subcap_id(s) it mentions. That's a coarse string match. This
module produces a purpose-built per-subcap narrative via Vertex Pro
with the schema:

  {
    "per_subcap_narrative": [
      {
        "subcap_id": "P1C1.1.1",
        "narrative_md": "…",
        "evidence_anchors": ["E-001", "E-007"],
        "confidence": 0.0..1.0
      },
      …
    ]
  }

State Transitions (4 branches — match ``ExtractorState``):

  full_match
    Vertex returned narratives for every subcap_id provided; the
    validator passed all of them; `data-source="llm"` on every cell.

  partial_match_with_warnings
    Vertex returned narratives for a subset of input subcap_ids;
    fabricated subcap_ids stripped by the validator; remaining
    subcaps fall back to the regex paragraph-extraction heuristic.

  validator_rejected_template_fallback
    Either Vertex was unavailable OR every returned subcap_id failed
    validation (fabricated). The router falls back entirely to the
    regex heuristic; `data-source="heuristic"`.

  empty_input
    No subcap_ids passed in. Returns an empty result; no LLM call.

Cached by SHA256(pillar_id + body_text + run_id) so re-running doesn't
re-pay LLM cost.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal

ExtractorState = Literal[
    "full_match",
    "partial_match_with_warnings",
    "validator_rejected_template_fallback",
    "empty_input",
]


@dataclass(frozen=True)
class PerSubcapNarrative:
    """One element of the LLM's per_subcap_narrative output."""
    subcap_id: str
    narrative_md: str
    evidence_anchors: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class ExtractionResult:
    """Output of extract_per_subcap_narrative.

    data_source: which provenance to render on each cell:
      ``llm``        — narrative came from the structured-output extractor
      ``heuristic``  — narrative came from the legacy paragraph-split
                       fallback
    """
    state: ExtractorState
    narratives: list[PerSubcapNarrative] = field(default_factory=list)
    rejected_subcap_ids: list[str] = field(default_factory=list)
    rejected_evidence_ids: list[str] = field(default_factory=list)
    data_source: Literal["llm", "heuristic", "mixed"] = "heuristic"


def cache_key(*, pillar_id: str, body_text: str, run_id: str) -> str:
    """Stable hash so re-running over the same body doesn't re-pay LLM cost.

    Caller key-prefixes (`subcap_narrative:`) and stuffs into Redis with
    the surface's TTL.
    """
    blob = "␟".join([pillar_id, run_id, body_text or ""]).encode("utf-8")
    return "subcap_narrative:" + hashlib.sha256(blob).hexdigest()[:48]


def build_prompt(
    *,
    pillar_id: str,
    body_text: str,
    valid_subcap_ids: list[str],
    valid_evidence_ids: list[str],
) -> str:
    """Build the deterministic Vertex Pro prompt.

    Pure; lets us snapshot-test the LLM contract.
    """
    subs = ", ".join(sorted(valid_subcap_ids))
    es = ", ".join(sorted(valid_evidence_ids)[:24])  # cap so prompt fits
    return (
        f"You are DMA Insights' per-subcap narrative classifier.\n"
        f"Given the pillar {pillar_id} deep-dive analyst prose and the\n"
        f"list of in-scope subcap IDs, produce one narrative_md per\n"
        f"subcap_id (omit any that aren't substantively covered).\n"
        f"Output ONLY valid JSON in this shape:\n"
        f'  {{"per_subcap_narrative": [\n'
        f'     {{"subcap_id": "P1C1.1.1", "narrative_md": "…",\n'
        f'       "evidence_anchors": ["E-001"], "confidence": 0.0..1.0}}\n'
        f"   ]}}\n"
        f"Never invent subcap_ids — every subcap_id you emit MUST be in\n"
        f"this list: {subs}.\n"
        f"Never invent evidence_anchors — every E-ID you emit MUST be in\n"
        f"this list: {es}.\n\n"
        f"PILLAR DEEP-DIVE BODY:\n{body_text}\n"
    )


def validate(
    raw: dict[str, Any],
    *,
    valid_subcap_ids: list[str],
    valid_evidence_ids: list[str] | None = None,
) -> tuple[list[PerSubcapNarrative], list[str], list[str]]:
    """Apply the anti-hallucination validator.

    Returns:
      (kept, rejected_subcap_ids, rejected_evidence_ids)

    Rejection rules:
      - every returned subcap_id MUST be in valid_subcap_ids (else drop).
      - every evidence_anchor MUST be in valid_evidence_ids (when that
        list is provided); fabricated anchors stripped from the survivor.
    """
    if not isinstance(raw, dict):
        return [], [], []
    items = raw.get("per_subcap_narrative") or []
    if not isinstance(items, list):
        return [], [], []

    valid_subs = set(valid_subcap_ids)
    valid_eids = set(valid_evidence_ids or [])

    kept: list[PerSubcapNarrative] = []
    rejected_subs: list[str] = []
    rejected_anchors: list[str] = []

    for it in items:
        if not isinstance(it, dict):
            continue
        sid = str(it.get("subcap_id") or "")
        if sid not in valid_subs:
            rejected_subs.append(sid)
            continue
        anchors_in = it.get("evidence_anchors") or []
        anchors_out: list[str] = []
        for e in anchors_in:
            es = str(e)
            if valid_eids and es not in valid_eids:
                rejected_anchors.append(es)
                continue
            anchors_out.append(es)
        narrative = (it.get("narrative_md") or "").strip()
        if not narrative:
            continue
        kept.append(
            PerSubcapNarrative(
                subcap_id=sid,
                narrative_md=narrative,
                evidence_anchors=anchors_out,
                confidence=float(it.get("confidence") or 0.0),
            )
        )
    return kept, rejected_subs, rejected_anchors


def heuristic_per_subcap(
    *, body_text: str, valid_subcap_ids: list[str],
) -> list[PerSubcapNarrative]:
    """Regex paragraph-split fallback — mirrors the legacy
    section_routing.build_narrative_heatmap behaviour.

    For each subcap_id, returns the paragraphs that mention it, joined
    with double-newlines. Empty when no paragraph references the ID.
    """
    out: list[PerSubcapNarrative] = []
    paragraphs = [p for p in (body_text or "").split("\n\n") if p.strip()]
    for sid in valid_subcap_ids:
        matched = [p for p in paragraphs if sid in p]
        if matched:
            out.append(
                PerSubcapNarrative(
                    subcap_id=sid,
                    narrative_md="\n\n".join(matched),
                    evidence_anchors=[],
                    confidence=0.4,
                )
            )
    return out


def merge_llm_and_heuristic(
    *,
    llm_narratives: list[PerSubcapNarrative],
    valid_subcap_ids: list[str],
    body_text: str,
) -> tuple[list[PerSubcapNarrative], str]:
    """Combine LLM output with heuristic fallback for subcaps the LLM
    didn't cover.

    Returns (final_list, data_source). data_source is:
      'llm'       — every subcap covered by the LLM
      'heuristic' — no LLM coverage at all
      'mixed'     — LLM covered some; heuristic filled the rest
    """
    covered = {n.subcap_id for n in llm_narratives}
    missing = [s for s in valid_subcap_ids if s not in covered]
    if not missing:
        return llm_narratives, "llm"
    fallback = heuristic_per_subcap(
        body_text=body_text, valid_subcap_ids=missing,
    )
    combined = list(llm_narratives) + fallback
    if not llm_narratives and fallback:
        return combined, "heuristic"
    if not llm_narratives and not fallback:
        return [], "heuristic"
    return combined, "mixed"


def parse_llm_text(text: str) -> dict[str, Any] | None:
    """Extract JSON from a Vertex response, handling ```json fences."""
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        try:
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        except Exception:
            return None
    try:
        return json.loads(text)
    except Exception:
        return None


async def extract_per_subcap_narrative(
    *,
    pillar_id: str,
    body_text: str,
    valid_subcap_ids: list[str],
    valid_evidence_ids: list[str] | None = None,
    run_id: str = "",
    vertex_client: Any = None,
    cache: Any = None,
) -> ExtractionResult:
    """End-to-end extraction with the 4-branch state matrix.

    `vertex_client` is dependency-injected so unit tests can pass a
    fake. When `vertex_client` is None (offline), we go straight to the
    heuristic fallback.

    `cache` is optional Redis-like with `.get(key)` + `.set(key, value, ttl)`.
    On cache hit, the LLM call is skipped entirely.
    """
    # ── empty_input branch ─────────────────────────────────────────────
    if not valid_subcap_ids:
        return ExtractionResult(
            state="empty_input", narratives=[],
            data_source="heuristic",
        )

    # ── cache lookup ───────────────────────────────────────────────────
    key = cache_key(pillar_id=pillar_id, body_text=body_text, run_id=run_id)
    cached_raw: dict | None = None
    if cache is not None:
        try:
            raw = await cache.get(key) if hasattr(cache, "get") else None
            if raw:
                cached_raw = json.loads(raw)
        except Exception:
            cached_raw = None

    # ── LLM call (or cache) ────────────────────────────────────────────
    llm_payload: dict | None = cached_raw
    if llm_payload is None and vertex_client is not None:
        try:
            prompt = build_prompt(
                pillar_id=pillar_id, body_text=body_text,
                valid_subcap_ids=valid_subcap_ids,
                valid_evidence_ids=valid_evidence_ids or [],
            )
            from app.services.vertex_client import GeminiCall
            call = GeminiCall(
                surface="subcap_narrative", model="pro", prompt=prompt,
                max_output_tokens=2048, temperature=0.2,
            )
            chunks: list[str] = []
            async for chunk in vertex_client.stream(call):
                chunks.append(chunk)
            raw_text = "".join(chunks).strip()
            llm_payload = parse_llm_text(raw_text)
        except Exception:
            llm_payload = None

    # ── validator + dispatch ───────────────────────────────────────────
    if llm_payload is None:
        # validator_rejected_template_fallback (no LLM at all).
        fallback = heuristic_per_subcap(
            body_text=body_text, valid_subcap_ids=valid_subcap_ids,
        )
        return ExtractionResult(
            state="validator_rejected_template_fallback",
            narratives=fallback,
            data_source="heuristic",
        )

    kept, rejected_subs, rejected_anchors = validate(
        llm_payload,
        valid_subcap_ids=valid_subcap_ids,
        valid_evidence_ids=valid_evidence_ids,
    )

    if not kept:
        # All LLM narratives failed validation → full fallback.
        fallback = heuristic_per_subcap(
            body_text=body_text, valid_subcap_ids=valid_subcap_ids,
        )
        return ExtractionResult(
            state="validator_rejected_template_fallback",
            narratives=fallback,
            rejected_subcap_ids=rejected_subs,
            rejected_evidence_ids=rejected_anchors,
            data_source="heuristic",
        )

    # Cache write — only persist VALIDATED payload.
    if cache is not None and not cached_raw:
        try:
            payload_to_cache = json.dumps({
                "per_subcap_narrative": [
                    {
                        "subcap_id": n.subcap_id,
                        "narrative_md": n.narrative_md,
                        "evidence_anchors": n.evidence_anchors,
                        "confidence": n.confidence,
                    }
                    for n in kept
                ]
            })
            if hasattr(cache, "set"):
                await cache.set(key, payload_to_cache, ex=3600)
        except Exception:
            pass

    combined, data_source = merge_llm_and_heuristic(
        llm_narratives=kept,
        valid_subcap_ids=valid_subcap_ids,
        body_text=body_text,
    )

    state: ExtractorState
    if rejected_subs or len(combined) > len(kept):
        state = "partial_match_with_warnings"
    else:
        state = "full_match"

    return ExtractionResult(
        state=state,
        narratives=combined,
        rejected_subcap_ids=rejected_subs,
        rejected_evidence_ids=rejected_anchors,
        data_source=data_source,
    )
