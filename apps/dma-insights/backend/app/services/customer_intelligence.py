"""Customer Intelligence Profile — persistent per-entity memory.

Per the user mandate: "persistent memory within the app such that
the layer of intelligence and deep customization at the customer
level is usually achieved."

For every entity we maintain one row in
``customer_intelligence_profiles`` that aggregates ACROSS RUNS:

  - Maturity history & velocity (score-delta per year).
  - Archetype history (with per-run silhouette).
  - Recurring vs emerging themes (recurring = appears in ≥ 2 runs;
    emerging = appears only in the latest run).
  - Persistent gaps (subcap_ids consistently below the median across
    runs) vs closed gaps (subcap_ids whose latest band > earliest).
  - Tech-stack additions / removals between latest two runs.
  - A Gemini-generated `intelligence_summary_md` (3-5 paragraph
    executive view) with grounding evidence IDs.
  - The summary embedding for cross-entity RAG queries.

State-transition contract (5 branches), driven by the recompute_profile
entrypoint:

  1. ``first_run``                 — no prior profile rows; velocity is
                                     NULL; maturity_history has one entry.
  2. ``incremental_update``        — profile exists; append latest run
                                     to history; recompute velocity =
                                     (latest_score - earliest_score) /
                                     years-spanned.
  3. ``re_ingest_same_request_id`` — incoming run.request_id matches a
                                     run already in maturity_history;
                                     update that entry in-place,
                                     do NOT duplicate; bump
                                     computed_at; leave computed_for_run_id.
  4. ``gemini_unavailable``        — vertex_client raises; the profile
                                     row still persists with
                                     intelligence_summary_md=NULL and
                                     summary_embedding=NULL; UI shows
                                     "Summary pending".
  5. ``validator_rejected``        — Gemini output fails grounding
                                     validator; same end-state as
                                     gemini_unavailable but with a
                                     warning audit row.

All compute functions in this module are pure — they take iterables of
plain dicts so they can be unit-tested without a database.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

ProfileState = Literal[
    "first_run",
    "incremental_update",
    "re_ingest_same_request_id",
    "gemini_unavailable",
    "validator_rejected",
]


@dataclass(slots=True)
class RunSnapshot:
    """One run's projection into the intelligence-rollup pipeline."""
    run_id: str
    request_id: str | None
    completed_at: datetime
    overall_score: float
    pillar_scores: dict[str, float]            # {"P1": 3.4, ...}
    archetype: str | None                       # e.g. "compliance-first"
    archetype_silhouette: float | None
    theme_tags: list[str]                       # post-classifier surface
    below_median_subcap_ids: list[str]          # gap signal
    tech_stack: list[str]                       # tech IDs detected


@dataclass(slots=True)
class ComputedProfile:
    first_dma_at: datetime
    latest_dma_at: datetime
    total_runs: int
    maturity_history: list[dict[str, Any]] = field(default_factory=list)
    maturity_velocity: float | None = None
    archetype_history: list[dict[str, Any]] = field(default_factory=list)
    recurring_themes: list[str] = field(default_factory=list)
    emerging_themes: list[str] = field(default_factory=list)
    persistent_gap_subcap_ids: list[str] = field(default_factory=list)
    closed_gap_subcap_ids: list[str] = field(default_factory=list)
    tech_stack_additions: list[str] = field(default_factory=list)
    tech_stack_removals: list[str] = field(default_factory=list)


def compute_maturity_history(snapshots: list[RunSnapshot]) -> list[dict[str, Any]]:
    """Chronological list — one entry per run.

    Each entry: {run_id, completed_at, overall_score, pillar_scores}.
    Sorted ascending by completed_at; the most recent run is last so
    the velocity calculation can subscript [-1] vs [0].
    """
    ordered = sorted(snapshots, key=lambda s: s.completed_at)
    return [
        {
            "run_id": s.run_id,
            "completed_at": s.completed_at.isoformat(),
            "overall_score": round(s.overall_score, 3),
            "pillar_scores": {k: round(v, 3) for k, v in s.pillar_scores.items()},
        }
        for s in ordered
    ]


def compute_velocity(snapshots: list[RunSnapshot]) -> float | None:
    """Score delta per year between earliest and latest snapshot.

    Returns None when there's only 1 snapshot or when the time span
    is less than 30 days (avoids exploding the denominator).
    """
    if len(snapshots) < 2:
        return None
    ordered = sorted(snapshots, key=lambda s: s.completed_at)
    first, last = ordered[0], ordered[-1]
    days = (last.completed_at - first.completed_at).total_seconds() / 86400.0
    if days < 30:
        return None
    years = days / 365.25
    return round((last.overall_score - first.overall_score) / years, 3)


def compute_archetype_history(snapshots: list[RunSnapshot]) -> list[dict[str, Any]]:
    """One entry per run, with the assigned archetype + silhouette."""
    ordered = sorted(snapshots, key=lambda s: s.completed_at)
    return [
        {
            "run_id": s.run_id,
            "completed_at": s.completed_at.isoformat(),
            "archetype": s.archetype,
            "silhouette": round(s.archetype_silhouette, 3)
            if s.archetype_silhouette is not None else None,
        }
        for s in ordered
    ]


def compute_themes(snapshots: list[RunSnapshot]) -> tuple[list[str], list[str]]:
    """Returns (recurring_themes, emerging_themes).

    - Recurring: theme appears in ≥ 2 runs.
    - Emerging: theme appears ONLY in the latest run, never before.
    """
    if not snapshots:
        return [], []
    ordered = sorted(snapshots, key=lambda s: s.completed_at)
    counts: Counter[str] = Counter()
    for s in ordered:
        for t in set(s.theme_tags):
            counts[t] += 1
    recurring = sorted([t for t, c in counts.items() if c >= 2])
    latest_themes = set(ordered[-1].theme_tags)
    prior_themes: set[str] = set()
    for s in ordered[:-1]:
        prior_themes.update(s.theme_tags)
    emerging = sorted(latest_themes - prior_themes) if len(ordered) > 1 else []
    return recurring, emerging


def compute_gaps(snapshots: list[RunSnapshot]) -> tuple[list[str], list[str]]:
    """Returns (persistent_gap_subcap_ids, closed_gap_subcap_ids).

    - Persistent: subcap appears as below-median in ALL runs.
    - Closed:    subcap was below-median in the earliest run but NOT
                  in the latest. (We use first vs last; mid-run
                  oscillation is intentionally ignored — the user
                  wants "trajectory" not noise.)
    """
    if not snapshots:
        return [], []
    ordered = sorted(snapshots, key=lambda s: s.completed_at)
    in_all = set(ordered[0].below_median_subcap_ids)
    for s in ordered[1:]:
        in_all &= set(s.below_median_subcap_ids)
    persistent = sorted(in_all)
    closed: list[str] = []
    if len(ordered) >= 2:
        first_gaps = set(ordered[0].below_median_subcap_ids)
        latest_gaps = set(ordered[-1].below_median_subcap_ids)
        closed = sorted(first_gaps - latest_gaps)
    return persistent, closed


def compute_tech_drift(snapshots: list[RunSnapshot]) -> tuple[list[str], list[str]]:
    """Returns (additions, removals) — what changed between the most
    recent two runs."""
    if len(snapshots) < 2:
        return [], []
    ordered = sorted(snapshots, key=lambda s: s.completed_at)
    prev = set(ordered[-2].tech_stack)
    curr = set(ordered[-1].tech_stack)
    return sorted(curr - prev), sorted(prev - curr)


def compute_profile(snapshots: list[RunSnapshot]) -> ComputedProfile:
    """Aggregate everything we can derive deterministically from snapshots."""
    if not snapshots:
        raise ValueError("compute_profile requires ≥ 1 snapshot")
    ordered = sorted(snapshots, key=lambda s: s.completed_at)
    recurring, emerging = compute_themes(snapshots)
    persistent, closed = compute_gaps(snapshots)
    additions, removals = compute_tech_drift(snapshots)
    return ComputedProfile(
        first_dma_at=ordered[0].completed_at,
        latest_dma_at=ordered[-1].completed_at,
        total_runs=len(ordered),
        maturity_history=compute_maturity_history(snapshots),
        maturity_velocity=compute_velocity(snapshots),
        archetype_history=compute_archetype_history(snapshots),
        recurring_themes=recurring,
        emerging_themes=emerging,
        persistent_gap_subcap_ids=persistent,
        closed_gap_subcap_ids=closed,
        tech_stack_additions=additions,
        tech_stack_removals=removals,
    )


def classify_state(
    *,
    existing_profile: dict | None,
    incoming_request_id: str | None,
    gemini_available: bool,
    validator_passed: bool,
) -> ProfileState:
    """Decide which of the 5 state branches the recompute is on."""
    if not gemini_available:
        return "gemini_unavailable"
    if not validator_passed:
        return "validator_rejected"
    if existing_profile is None:
        return "first_run"
    # Re-ingest if the new run's request_id is already in the history.
    if incoming_request_id:
        history = existing_profile.get("maturity_history") or []
        if any(h.get("request_id") == incoming_request_id for h in history):
            return "re_ingest_same_request_id"
    return "incremental_update"


def build_summary_prompt(
    *,
    entity_name: str,
    profile: ComputedProfile,
    evidence_excerpts: list[dict[str, Any]],
) -> str:
    """Constructs the Gemini Pro prompt for intelligence_summary_md.

    Kept pure so we can snapshot-test the prompt. The persistence
    layer calls vertex_client.generate() with this; the validator
    checks every cited E-ID against `evidence_excerpts` E-IDs.
    """
    lines = [
        f"Compose a 3-5 paragraph executive view of {entity_name}'s "
        "longitudinal digital-maturity trajectory.",
        "Synthesize an evidence-backed argument — never a score recap and "
        "never a list of quoted excerpts. Open with the situation the "
        "evidence documents (name the systems and practices the researchers "
        "observed), develop the complication from the observed gaps with "
        "their E-ID citations, and close by referencing the recommended "
        "focus that follows from that observed state.",
        "",
        f"Total runs observed: {profile.total_runs}",
        f"Maturity velocity (score/year): {profile.maturity_velocity}",
        f"Recurring themes: {', '.join(profile.recurring_themes) or '(none)'}",
        f"Emerging themes: {', '.join(profile.emerging_themes) or '(none)'}",
        f"Persistent gaps: {', '.join(profile.persistent_gap_subcap_ids) or '(none)'}",
        f"Closed gaps: {', '.join(profile.closed_gap_subcap_ids) or '(none)'}",
        "",
        "Cite specific evidence by E-ID. Do not invent E-IDs not in the "
        "provided list.",
        "",
        "Available evidence:",
    ]
    for e in evidence_excerpts[:24]:
        lines.append(
            f"  [{e.get('e_id')}] T{e.get('tier')}: {e.get('excerpt', '')[:200]}"
        )
    return "\n".join(lines)
