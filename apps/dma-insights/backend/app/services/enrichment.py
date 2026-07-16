"""AI enrichment service — narrative LLM output threaded with evidence IDs.

This service runs when:
  - a subcap_score is persisted with evidence_count < 2 (thin evidence),
    auto-fired by the package_persist layer
  - an admin manually triggers a re-enrichment for an entity
  - the catalogue bumps version and prior enrichments are superseded

State transitions:
  evidence_count < 2 (thin evidence) on a subcap_score
    → enrichment job fires; result references every supplied E-ID
  prior enrichment exists for (target_kind, target_id) and
  catalogue_version differs
    → prior row's superseded_by is set to the new row's id
  validator rejects the generated text (fabricated E-ID in the
  enrichment_text that wasn't in grounding_evidence_ids)
    → enrichment_text is replaced with the deterministic template;
      validators_passed=False is persisted
  no grounding evidence supplied
    → service short-circuits and writes a minimal template referencing
      only the V7 capability text + peer median

Pure-logic surface. Live DB writes are owned by the caller (package_persist
or an enrichment worker). Tests exercise prompt construction + validator
short-circuit + supersede logic directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

EnrichmentTargetKind = Literal[
    "subcap_score", "insight_card", "recommendation", "entity",
]


@dataclass(frozen=True)
class EnrichmentInput:
    """Inputs to a single enrichment job."""
    target_kind: EnrichmentTargetKind
    target_id: str
    surface: str
    catalogue_version: str
    grounding_evidence: list[dict] = field(default_factory=list)
    # dict shape: {e_id, source_name, excerpt, tier, claim_type}
    capability_text: str = ""          # V7 capability prose (subcap_id)
    peer_median: float | None = None
    peer_n: int = 0


@dataclass
class EnrichmentResult:
    """Output of a single enrichment job, ready to persist."""
    enrichment_text: str
    grounding_evidence_ids: list[str]
    grounding_subcap_ids: list[str] = field(default_factory=list)
    validators_passed: bool = True
    confidence: float = 0.7
    fallback_used: bool = False
    model: str = "flash"


def build_enrichment_prompt(input_: EnrichmentInput) -> str:
    """Render the deterministic prompt for Gemini Flash.

    The prompt is intentionally narrow: rephrase the supplied evidence
    into a 2-3 sentence narrative that AEs can drop into a slide. The
    LLM MUST cite every supplied E-ID at least once.
    """
    evidence_lines = []
    for ev in input_.grounding_evidence:
        eid = ev.get("e_id", "")
        src = ev.get("source_name", "")
        excerpt = (ev.get("excerpt") or "").strip()
        evidence_lines.append(f"  [{eid}] ({src}) — {excerpt}")
    evidence_blob = "\n".join(evidence_lines) or "  (no evidence supplied)"

    peer_blob = ""
    if input_.peer_median is not None and input_.peer_n >= 3:
        peer_blob = (
            f"\nPeer median (subvertical, n={input_.peer_n}): "
            f"{input_.peer_median:.2f}"
        )

    return (
        f"You are DMA Insights' enrichment writer.\n"
        f"Produce 2-3 short sentences (max 80 words total) narrating the "
        f"capability state for the supplied evidence. You MUST cite every "
        f"E-ID listed below at least once, in square brackets.\n"
        f"Never invent E-IDs. Never reference subcap codes that aren't in "
        f"the capability text.\n\n"
        f"Capability:\n  {input_.capability_text.strip() or '(unspecified)'}\n\n"
        f"Evidence:\n{evidence_blob}{peer_blob}\n\n"
        f"NARRATIVE:"
    )


def template_enrichment_text(input_: EnrichmentInput) -> str:
    """Deterministic fallback used when:
      - the LLM call fails / validator rejects
      - the supplied bundle is empty
      - we're running offline (no Vertex creds)

    Cites every supplied E-ID by reference; never invents anything.
    """
    eids = [
        ev.get("e_id", "") for ev in input_.grounding_evidence if ev.get("e_id")
    ]
    if not eids:
        return (
            f"Evidence is sparse for this capability ({input_.capability_text or 'subcap'}). "
            f"An Analyst should refresh the DMA before relying on the score."
        )
    eid_ref = ", ".join(f"[{e}]" for e in eids)
    cap = input_.capability_text or "this capability"
    peer = (
        f" Peer median: {input_.peer_median:.2f} (n={input_.peer_n})."
        if input_.peer_median is not None and input_.peer_n >= 3
        else ""
    )
    return (
        f"{cap.strip().rstrip('.')} — grounded on {eid_ref}.{peer} "
        f"Validator-approved narrative pending an Analyst review."
    )


def validate_enrichment(
    *,
    response_text: str,
    grounding_evidence_ids: list[str],
) -> tuple[bool, list[str]]:
    """V1+V2-lite for the enrichment surface: every E-ID in the response
    must be in the supplied grounding set. Returns (clean, fabricated[]).

    This is a thin pre-check used by tests and the persistence layer.
    The full validator (which also checks against DB existence) runs in
    grounding_validator.validate_response.
    """
    import re
    mentioned = set(re.findall(r"E-\d+", response_text))
    allowed = set(grounding_evidence_ids)
    fabricated = sorted(mentioned - allowed)
    return (len(fabricated) == 0, fabricated)


def enrich_with_fallback(
    input_: EnrichmentInput,
    *,
    generate_fn=None,
) -> EnrichmentResult:
    """Pure pipeline: try to generate via generate_fn (if provided),
    validate, fall back to template on rejection or absence of generator.

    `generate_fn` is a callable `EnrichmentInput -> str` (synchronous for
    test simplicity). In production the caller wraps Vertex.
    """
    if not input_.grounding_evidence:
        return EnrichmentResult(
            enrichment_text=template_enrichment_text(input_),
            grounding_evidence_ids=[],
            validators_passed=True,
            fallback_used=True,
            confidence=0.4,
            model="template",
        )

    eids = [
        ev.get("e_id", "") for ev in input_.grounding_evidence if ev.get("e_id")
    ]
    if generate_fn is None:
        return EnrichmentResult(
            enrichment_text=template_enrichment_text(input_),
            grounding_evidence_ids=eids,
            validators_passed=True,
            fallback_used=True,
            confidence=0.5,
            model="template",
        )

    try:
        text = generate_fn(input_)
    except Exception:
        return EnrichmentResult(
            enrichment_text=template_enrichment_text(input_),
            grounding_evidence_ids=eids,
            validators_passed=False,
            fallback_used=True,
            confidence=0.3,
            model="template",
        )

    clean, _fabricated = validate_enrichment(
        response_text=text, grounding_evidence_ids=eids,
    )
    if not clean:
        return EnrichmentResult(
            enrichment_text=template_enrichment_text(input_),
            grounding_evidence_ids=eids,
            validators_passed=False,
            fallback_used=True,
            confidence=0.3,
            model="template",
        )

    return EnrichmentResult(
        enrichment_text=text,
        grounding_evidence_ids=eids,
        validators_passed=True,
        fallback_used=False,
        confidence=0.75,
        model="flash",
    )


def should_supersede(
    *,
    prior_catalogue_version: str | None,
    new_catalogue_version: str,
) -> bool:
    """Decision: should the new enrichment supersede the prior one?

    Yes when:
      - a prior row exists at all (we always replace; supersede chain
        keeps the audit trail)
      - the catalogue version changed (definitely supersede; the prior
        narrative might reference subcap codes that no longer resolve)

    No when:
      - no prior row exists (this is a fresh insert)
    """
    return prior_catalogue_version is not None
