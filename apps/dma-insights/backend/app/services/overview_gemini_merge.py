"""Read-path merge of persisted Gemini enrichment into the D1 overview.

RC1 (2026-07 audit): the deploy pipeline persisted Gemini output into
`vertex_synthesis_cache` / `firmographics.parsed_facts._gemini_extracted`
/ `ai_enrichments`, but the overview endpoint NEVER read any of it back
into responses — enrichment was invisible to AEs. This module is the
pure (no-DB, no-FastAPI) merge the router calls with rows it already
fetched, so the policy is unit-testable with faked cache rows.

Merge policy (locked to master plan Part 3.2):
  - Gemini output UPLIFTS the response only when the row is
    validator-passed (the router's SQL filters `validators_passed`;
    this module defends again).
  - Deterministic / package-derived values are NEVER overwritten —
    the why_now uplift is PREPENDED as its own provenance-stamped
    signal; firmographics gap-fill values were already persisted
    fill-if-empty at enrich time, so here we only stamp provenance.
  - Every merged field carries `source: "vertex"` + `model_id` +
    `synthesized_at` (the honesty contract + what
    `qa_gemini_surfaces --mode live` asserts).

State branches:
  no cache rows / no enrichments   → inputs returned unchanged
  why_now row present              → uplift signal prepended (never
                                     duplicated on re-entry)
  parsed_facts._gemini_extracted   → firmographics["provenance"][field]
                                     stamped per extracted field
  thought_leadership row + empty
  panel                            → firmographics.thought_leadership
                                     filled from the cached items
  entity-level ai_enrichments      → firmographics["ai_enrichments"]
                                     list attached (validator-passed
                                     rows only)
"""
from __future__ import annotations

from typing import Any

# Short display label for the synthesis tile (pure, spaCy-degrading).
from app.services.nlp.titlecraft import make_title

# Pure token helpers (no DB) — near-duplicate detection for the why_now
# uplift (2026-07-06 mandate: no duplicate why-now content on one page).
from app.services.startup_enrich import (
    significant_tokens,
    texts_near_identical,
    why_now_signal_text,
)

# Same symmetric token-containment contract the deterministic miner's dedup
# guard uses (deepen_narrative._push) — one duplicate policy per producer.
from app.services.wn_dedup import token_containment

# The provenance keys every merged field carries.
_PROV_KEYS = ("source", "model_id", "synthesized_at")


def _row_provenance(row: dict[str, Any]) -> dict[str, Any]:
    """Provenance stamp from a vertex_synthesis_cache row dict.
    Prefers the persisted output_json payload (written by
    enrich_corpus._provenance_json); falls back to the row columns."""
    oj = row.get("output_json") or {}
    if not isinstance(oj, dict):
        oj = {}
    created = row.get("created_at")
    synthesized_at = oj.get("synthesized_at") or (
        created.isoformat() if hasattr(created, "isoformat") else created
    )
    return {
        "source": "vertex",
        "derived_from": "vertex",
        "model_id": oj.get("model_id") or row.get("model"),
        "synthesized_at": synthesized_at,
    }


def _is_vertex_signal(sig: Any) -> bool:
    return isinstance(sig, dict) and (
        sig.get("source") == "vertex" or sig.get("derived_from") == "vertex"
    )


def _restates_existing(text: str, signals: list[dict[str, Any]]) -> bool:
    """True when the Vertex why_now synthesis merely RESTATES the signals
    already on the page — near-identical to one signal's text, or ≥85% of
    its content words already covered by the union of the persisted signal
    texts. A restatement adds a duplicate card, not intelligence, so it is
    suppressed (2026-07-06 mandate: every why-now element on the page must
    communicate something different). A genuinely synthesized narrative
    (new framing, new connections) passes."""
    toks = significant_tokens(text)
    if len(toks) < 6:
        return False
    union: set[str] = set()
    for s in signals:
        st = significant_tokens(why_now_signal_text(s))
        if st and texts_near_identical(text, why_now_signal_text(s)):
            return True
        union |= st
    return bool(union) and len(toks & union) / len(toks) >= 0.85


def merge_gemini_overview(
    *,
    why_now_signals: list[dict[str, Any]],
    firmographics: dict[str, Any] | None,
    parsed_facts: dict[str, Any] | None,
    cache_rows: list[dict[str, Any]],
    enrichment_rows: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Merge validator-passed Gemini rows into the overview payload.

    `cache_rows` — dicts with at least {surface, output_text,
    output_json, model, created_at, cited_evidence_ids,
    validators_passed}, newest-first per surface (the router's SQL
    orders DESC; the FIRST row per surface wins here).
    `enrichment_rows` — entity-level ai_enrichments dicts
    {surface, enrichment_text, model, created_at, grounding_evidence_ids,
    validators_passed}.

    Returns (why_now_signals, firmographics) — new list, same-or-updated
    dict; inputs are not mutated.
    """
    by_surface: dict[str, dict[str, Any]] = {}
    for row in cache_rows or []:
        if not isinstance(row, dict) or not row.get("validators_passed"):
            continue
        by_surface.setdefault(str(row.get("surface") or ""), row)

    signals = list(why_now_signals or [])

    # ── why_now uplift — prepend a provenance-stamped synthesis signal ──
    # Suppressed when it merely restates the deterministic signals already
    # on the page (near-duplicate content adds nothing an AE can use).
    wn = by_surface.get("why_now")
    syn_text = str((wn or {}).get("output_text") or "").strip()
    if wn and syn_text and not any(_is_vertex_signal(s) for s in signals):
        # Content-level dedup (2026-07-06): the synthesis is grounded on the
        # SAME run evidence as the deterministic signals, so it often
        # restates one — previously a duplicate tile that evicted a real
        # signal from the 4-tile strip. Two complementary guards, either
        # suppresses the prepend: symmetric token containment against any
        # single signal (catches a long restatement of a short signal — the
        # miner's own dedup contract), and _restates_existing (near-identical
        # wording OR ≥85% of the synthesis' content words already covered by
        # the UNION of the persisted signal texts — catches a synthesis
        # stitched together from several signals).
        restated = any(
            token_containment(
                syn_text, s.get("detail") or s.get("text") or "") > 0.5
            for s in signals if isinstance(s, dict)
        ) or _restates_existing(syn_text, signals)
        if not restated:
            cited = list(wn.get("cited_evidence_ids") or [])
            signals.insert(0, {
                # Full 14-field template shape (proto 3d9fd6c1 WHY_NOW) —
                # this merge used to emit the legacy 5-key shape. 'WN-0'
                # marks the read-time prepend; persisted signals keep their
                # own WN-1..n sequence. Strength/claim/confidence follow the
                # deterministic vocabulary: a validator-passed synthesis over
                # already-cited evidence is SUPPORTING / INFERENCE.
                "id": "WN-0",
                "kind": "SYNTHESIS",
                "label": make_title(syn_text, 60) or "Why-now synthesis",
                "category": "market",
                "strength": "SUPPORTING",
                "window": None,
                "confidence": "MEDIUM" if len(cited) >= 2 else "LOW",
                "claim": "INFERENCE",
                "detail": syn_text,
                "metric": None,
                "peer_context": None,
                "play": None,
                "risk": None,
                "evidence": cited,
                "timeline": None,
                "impact": None,
                # legacy pair kept for older readers of the 5-key shape
                "text": syn_text,
                "date": None,
                **_row_provenance(wn),
            })

    if firmographics is None:
        # Nothing else to merge into — thought_leadership / provenance
        # all live under firmographics.
        return signals, None

    firm = dict(firmographics)
    pf = parsed_facts if isinstance(parsed_facts, dict) else {}

    # ── firmographics gap-fill provenance (values already flattened) ──
    gem_fields = [
        f for f in (pf.get("_gemini_extracted") or []) if isinstance(f, str)
    ]
    if gem_fields:
        fx_row = by_surface.get("firmographics_extraction")
        fx_prov = (
            _row_provenance(fx_row) if fx_row
            else _pf_provenance(pf.get("_fx_provenance"))
        )
        tl_row = by_surface.get("thought_leadership_extraction")
        tl_prov = (
            _row_provenance(tl_row) if tl_row
            else _pf_provenance(pf.get("_tl_provenance"))
        )
        prov = dict(firm.get("provenance") or {})
        for field in gem_fields:
            prov[field] = tl_prov if field == "thought_leadership" else fx_prov
        firm["provenance"] = prov
        firm["gemini_extracted_fields"] = sorted(set(gem_fields))

    # ── thought_leadership fill (cache row → empty panel only) ──
    tl_row = by_surface.get("thought_leadership_extraction")
    if tl_row and not firm.get("thought_leadership"):
        oj = tl_row.get("output_json") or {}
        items = oj.get("items") if isinstance(oj, dict) else None
        if isinstance(items, list) and items:
            firm["thought_leadership"] = items
            prov = dict(firm.get("provenance") or {})
            prov["thought_leadership"] = _row_provenance(tl_row)
            firm["provenance"] = prov

    # ── entity-level ai_enrichments (validator-passed only) ──
    merged_enrichments: list[dict[str, Any]] = []
    for row in enrichment_rows or []:
        if not isinstance(row, dict) or not row.get("validators_passed"):
            continue
        created = row.get("created_at")
        # Provenance honesty: a deterministic template-fallback row (model
        # 'template') must NOT be badged as Vertex output (audit 2026-07-04).
        _src = "template" if str(row.get("model") or "") == "template" else "vertex"
        merged_enrichments.append({
            "surface": row.get("surface"),
            "text": row.get("enrichment_text"),
            "evidence": list(row.get("grounding_evidence_ids") or []),
            "source": _src,
            "derived_from": _src,
            "model_id": row.get("model"),
            "synthesized_at": (
                created.isoformat() if hasattr(created, "isoformat")
                else created
            ),
        })
    if merged_enrichments:
        firm["ai_enrichments"] = merged_enrichments

    return signals, firm


def _pf_provenance(blob: Any) -> dict[str, Any]:
    """Normalize a parsed_facts-persisted provenance dict (written by
    enrich_corpus) to the response contract; tolerates absence."""
    if not isinstance(blob, dict):
        return {"source": "vertex", "derived_from": "vertex",
                "model_id": None, "synthesized_at": None}
    return {
        "source": "vertex",
        "derived_from": "vertex",
        "model_id": blob.get("model_id"),
        "synthesized_at": blob.get("synthesized_at"),
    }
