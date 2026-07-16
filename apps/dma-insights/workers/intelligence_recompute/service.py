"""Pure-logic helpers for the intelligence_recompute worker.

State Transitions (6 branches — match the worker_state_label() output):

  1. ``first_time_compute``       — no prior customer_intelligence_profiles
                                    row; Vertex call runs; summary persisted.
  2. ``incremental_with_new_run`` — profile exists; the entity has at least
                                    one new ACTIVE run not yet rolled into
                                    maturity_history; recompute everything.
  3. ``idempotent_skip``          — profile.computed_for_run_id matches the
                                    entity's latest ACTIVE run AND
                                    profile.catalogue_version matches the
                                    run's catalogue. No Vertex call; no
                                    UPSERT. Worker returns early.
  4. ``vertex_unavailable``       — Vertex client raises (timeout / 5xx /
                                    no creds). Row is still UPSERTed with
                                    ``intelligence_summary_md = NULL``,
                                    ``summary_status = 'vertex_unavailable'``
                                    so the UI can show "Summary pending".
  5. ``validator_rejected``       — Vertex returned text but cited E-IDs
                                    not in the bundled evidence. The
                                    deterministic template fallback is used;
                                    a gemini_hallucination_alerts row is
                                    written; summary_status set to
                                    ``'validator_rejected'``.
  6. ``embedding_failed``         — Vertex embed() raises after the summary
                                    text is in hand. We keep the markdown
                                    but ``summary_embedding = NULL``;
                                    summary_status set to ``'embedding_failed'``.

All entry points are pure functions taking iterables of dicts or
RunSnapshot objects so they can be unit-tested without a database.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from app.services.customer_intelligence import (
    ComputedProfile,
    RunSnapshot,
    build_summary_prompt,
)

WorkerState = Literal[
    "first_time_compute",
    "incremental_with_new_run",
    "idempotent_skip",
    "vertex_unavailable",
    "validator_rejected",
    "embedding_failed",
]


@dataclass(frozen=True)
class EvidenceRow:
    """Projection of one evidence_index row for the recompute prompt."""
    e_id: str
    tier: int
    excerpt: str


@dataclass(frozen=True)
class ExistingProfile:
    """The rollup's idempotency anchor — matches the columns we care about."""
    computed_for_run_id: str | None
    catalogue_version: str | None
    summary_present: bool


@dataclass
class SummaryDecision:
    """Result of the LLM-call sub-routine. Lets the worker emit one of the
    five summary outcomes without coupling pure logic to async I/O.
    """
    summary_md: str | None
    cited_evidence_ids: list[str] = field(default_factory=list)
    cited_subcap_ids: list[str] = field(default_factory=list)
    confidence: float | None = None
    summary_status: str = "ok"   # ok | vertex_unavailable | validator_rejected
    embedding: list[float] | None = None


def should_skip(
    *,
    existing: ExistingProfile | None,
    latest_run_id: str,
    latest_catalogue_version: str,
) -> bool:
    """Idempotent-skip decision.

    Skip only when:
      - a prior profile exists AND
      - it was computed against the same latest run AND
      - it was computed against the same catalogue AND
      - the summary text is already present (so we don't repeatedly skip
        a vertex_unavailable row that's still waiting for a retry).
    """
    if existing is None:
        return False
    if not existing.summary_present:
        return False
    if existing.computed_for_run_id != latest_run_id:
        return False
    return existing.catalogue_version == latest_catalogue_version


def classify_worker_state(
    *,
    existing: ExistingProfile | None,
    latest_run_id: str,
    latest_catalogue_version: str,
    vertex_available: bool,
    validator_passed: bool,
    embedding_succeeded: bool,
) -> WorkerState:
    """Decide which of the 6 worker-state branches we end up in.

    Pure decision so the dispatch is testable without I/O.
    Ordering: idempotent_skip > vertex_unavailable > validator_rejected
    > embedding_failed > (first_time | incremental).
    """
    if should_skip(
        existing=existing,
        latest_run_id=latest_run_id,
        latest_catalogue_version=latest_catalogue_version,
    ):
        return "idempotent_skip"
    if not vertex_available:
        return "vertex_unavailable"
    if not validator_passed:
        return "validator_rejected"
    if not embedding_succeeded:
        return "embedding_failed"
    if existing is None:
        return "first_time_compute"
    return "incremental_with_new_run"


def assemble_snapshots(rows: list[dict[str, Any]]) -> list[RunSnapshot]:
    """Convert raw rows (from a SQL SELECT) into RunSnapshot objects.

    Each row is expected to carry at minimum:
      run_id, request_id, completed_at, overall_score, pillar_scores,
      archetype, archetype_silhouette, theme_tags,
      below_median_subcap_ids, tech_stack

    Missing optional fields default safely.
    """
    snaps: list[RunSnapshot] = []
    for r in rows:
        completed_at = r.get("completed_at")
        if isinstance(completed_at, str):
            completed_at = datetime.fromisoformat(completed_at)
        if completed_at is None:
            continue
        snaps.append(
            RunSnapshot(
                run_id=str(r["run_id"]),
                request_id=(str(r["request_id"]) if r.get("request_id") else None),
                completed_at=completed_at,
                overall_score=float(r.get("overall_score") or 0.0),
                pillar_scores={k: float(v) for k, v in (r.get("pillar_scores") or {}).items()},
                archetype=r.get("archetype"),
                archetype_silhouette=(
                    float(r["archetype_silhouette"])
                    if r.get("archetype_silhouette") is not None else None
                ),
                theme_tags=list(r.get("theme_tags") or []),
                below_median_subcap_ids=list(r.get("below_median_subcap_ids") or []),
                tech_stack=list(r.get("tech_stack") or []),
            )
        )
    return snaps


def deterministic_template_summary(
    *, entity_name: str, profile: ComputedProfile,
) -> str:
    """Validator-fallback summary, built from the deterministic rollup.

    Used when Vertex output fails the grounding validator OR when Vertex
    is unavailable. The text is honest about its provenance so the UI
    can render the "Summary pending — auto-generated rollup" badge.
    """
    lines = [
        f"# {entity_name} — Digital Maturity Trajectory",
        "",
        f"**{profile.total_runs} assessment{'s' if profile.total_runs > 1 else ''} on file** "
        f"(first {profile.first_dma_at.date().isoformat()}, "
        f"latest {profile.latest_dma_at.date().isoformat()}).",
        "",
    ]
    if profile.maturity_velocity is not None:
        direction = "improving" if profile.maturity_velocity > 0 else "declining"
        lines.append(
            f"Maturity score is **{direction} at {profile.maturity_velocity:+.2f}/yr** "
            f"based on the longitudinal rollup."
        )
    if profile.recurring_themes:
        lines.append(
            f"Recurring themes across runs: {', '.join(profile.recurring_themes)}."
        )
    if profile.emerging_themes:
        lines.append(
            f"New themes in the latest run: {', '.join(profile.emerging_themes)}."
        )
    if profile.persistent_gap_subcap_ids:
        lines.append(
            f"Persistent gaps: {', '.join(profile.persistent_gap_subcap_ids[:5])}."
        )
    if profile.closed_gap_subcap_ids:
        lines.append(
            f"Closed since first run: {', '.join(profile.closed_gap_subcap_ids[:5])}."
        )
    if profile.tech_stack_additions or profile.tech_stack_removals:
        lines.append(
            f"Tech-stack drift — added: {', '.join(profile.tech_stack_additions) or '(none)'}; "
            f"removed: {', '.join(profile.tech_stack_removals) or '(none)'}."
        )
    lines.append("")
    lines.append(
        "_This summary was auto-generated from the deterministic rollup "
        "because the LLM call did not pass validation. An analyst will "
        "regenerate it on the next nightly recompute._"
    )
    return "\n".join(lines)


def validate_summary_citations(
    *,
    cited_evidence_ids: list[str],
    bundled_evidence_ids: set[str],
    cited_subcap_ids: list[str] | None = None,
    bundled_subcap_ids: set[str] | None = None,
) -> tuple[bool, list[str]]:
    """Return (passed, fabricated_ids).

    Fabricated: any cited ID not present in the bundle. This is the same
    contract grounding_validator.py uses for RAG answers.
    """
    bundled = set(bundled_evidence_ids)
    fabricated_e = [e for e in cited_evidence_ids if e not in bundled]
    fabricated_s: list[str] = []
    if cited_subcap_ids and bundled_subcap_ids is not None:
        fabricated_s = [s for s in cited_subcap_ids if s not in bundled_subcap_ids]
    fabricated = fabricated_e + fabricated_s
    return (len(fabricated) == 0, fabricated)


def parse_structured_output(text: str) -> dict[str, Any] | None:
    """Extract JSON from a Vertex structured-output response.

    Returns None when the payload can't be parsed. Mirrors the
    intelligence_builder fallback heuristic so multiple wrappers are
    handled uniformly.
    """
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        # ```json\n{...}\n```
        try:
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        except Exception:
            return None
    try:
        return json.loads(text)
    except Exception:
        return None


def build_recompute_payload(
    *,
    entity_id: str,
    entity_name: str,
    catalogue_version: str,
    latest_run_id: str,
    profile: ComputedProfile,
    summary: SummaryDecision,
) -> dict[str, Any]:
    """Project a ComputedProfile + SummaryDecision into the UPSERT params.

    Pure — used by both the live SQLAlchemy persister and unit tests.
    The resulting dict carries every column the
    customer_intelligence_profiles table expects.
    """
    return {
        "entity_id": entity_id,
        "entity_name": entity_name,
        "first_dma_at": profile.first_dma_at.isoformat(),
        "latest_dma_at": profile.latest_dma_at.isoformat(),
        "total_runs": profile.total_runs,
        "maturity_history": profile.maturity_history,
        "maturity_velocity": profile.maturity_velocity,
        "archetype_history": profile.archetype_history,
        "recurring_themes": profile.recurring_themes,
        "emerging_themes": profile.emerging_themes,
        "persistent_gap_subcap_ids": profile.persistent_gap_subcap_ids,
        "closed_gap_subcap_ids": profile.closed_gap_subcap_ids,
        "tech_stack_additions": profile.tech_stack_additions,
        "tech_stack_removals": profile.tech_stack_removals,
        "intelligence_summary_md": summary.summary_md,
        "summary_status": summary.summary_status,
        "summary_grounding_evidence_ids": summary.cited_evidence_ids,
        "summary_embedding": summary.embedding,
        "catalogue_version": catalogue_version,
        "computed_for_run_id": latest_run_id,
    }


async def call_vertex_summary(
    *,
    entity_name: str,
    profile: ComputedProfile,
    evidence: list[EvidenceRow],
    vertex_client: Any,
    embed_client: Any | None = None,
) -> SummaryDecision:
    """Wraps the Vertex Pro structured-output call.

    Returns a SummaryDecision carrying the parsed output. Failures collapse
    to a SummaryDecision with `summary_md=None` and a non-`ok` status —
    the caller decides whether to UPSERT with the template fallback.
    """
    prompt = build_summary_prompt(
        entity_name=entity_name,
        profile=profile,
        evidence_excerpts=[
            {"e_id": e.e_id, "tier": e.tier, "excerpt": e.excerpt}
            for e in evidence
        ],
    )

    # --- Vertex Pro generation -----------------------------------------
    try:
        # Try the structured-output path first; falls back to free-text.
        from app.services.vertex_client import GeminiCall
        call = GeminiCall(
            surface="intelligence_summary",
            model="pro",
            prompt=prompt,
            max_output_tokens=1024,
            temperature=0.2,
        )
        chunks: list[str] = []
        async for chunk in vertex_client.stream(call):
            chunks.append(chunk)
        raw_text = "".join(chunks).strip()
    except Exception:
        return SummaryDecision(
            summary_md=None,
            summary_status="vertex_unavailable",
        )

    parsed = parse_structured_output(raw_text)
    if parsed is None:
        # Treat unparseable output as text-only.
        summary_md = raw_text or None
        cited_e: list[str] = []
        cited_s: list[str] = []
        confidence: float | None = None
    else:
        summary_md = parsed.get("intelligence_summary_md") or raw_text or None
        cited_e = list(parsed.get("cited_evidence_ids") or [])
        cited_s = list(parsed.get("cited_subcap_ids") or [])
        confidence = parsed.get("confidence")

    if not summary_md:
        return SummaryDecision(
            summary_md=None,
            summary_status="vertex_unavailable",
        )

    # --- Embedding (best-effort) ---------------------------------------
    embedding: list[float] | None = None
    if embed_client is None:
        embed_client = vertex_client
    try:
        embs = await embed_client.embed([summary_md])
        if embs and embs[0]:
            embedding = [float(x) for x in embs[0]]
    except Exception:
        embedding = None

    return SummaryDecision(
        summary_md=summary_md,
        cited_evidence_ids=cited_e,
        cited_subcap_ids=cited_s,
        confidence=confidence,
        summary_status="ok" if embedding is not None else "embedding_failed",
        embedding=embedding,
    )


def state_after_decision(
    *,
    existing: ExistingProfile | None,
    decision: SummaryDecision,
    validator_passed: bool,
    latest_run_id: str,
    latest_catalogue_version: str,
) -> WorkerState:
    """Convenience wrapper combining the should_skip check with the
    summary outcome to produce a single state label.
    """
    return classify_worker_state(
        existing=existing,
        latest_run_id=latest_run_id,
        latest_catalogue_version=latest_catalogue_version,
        vertex_available=decision.summary_status != "vertex_unavailable",
        validator_passed=validator_passed,
        embedding_succeeded=decision.embedding is not None,
    )
