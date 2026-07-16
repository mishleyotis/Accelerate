"""Stairstep-curve service — D4 milestone computation.

For each platform card on D4, we compute a per-pillar stair-step that
shows how the entity moves from M-band-current → M-band-target across the
roadmap. Each step is an applicable recommendation grouped by pillar; the
y-axis is the projected score after that recommendation lands.

Pure module — no DB IO. The router fetches subcap_scores + recommendations
and feeds them in.

State-branch contract:
  - Entity has no addressable subcaps   → empty stairstep_steps + an empty
                                          empty_state reason "no-gaps".
  - Recommendation lacks uplift_per_pillar → falls back to
                                          DEFAULT_REC_UPLIFT (0.4 per
                                          pillar it targets).
  - Multiple recs in the same pillar    → ordered by uplift desc, ties
                                          broken by rec_id.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

DEFAULT_REC_UPLIFT = 0.4
PILLARS: tuple[str, ...] = ("P1", "P2", "P3", "P4")


@dataclass(frozen=True)
class RecForStair:
    rec_id: str
    title: str
    target_subcap_ids: list[str]
    uplift_per_pillar: dict[str, float] | None  # may be None
    # Part 7.3 — per-step platform reasoning notes so the staircase bands
    # aren't bare: the platform that enables the step + the concrete
    # feature it ships (both from the rec's platform mapping; optional).
    platform_name: str | None = None
    feature: str | None = None


@dataclass(frozen=True)
class CurrentByPillar:
    """Average current score per pillar."""
    P1: float
    P2: float
    P3: float
    P4: float

    def get(self, pillar: str) -> float:
        return getattr(self, pillar)


@dataclass(frozen=True)
class StairStep:
    """One step on the stairstep curve."""
    rec_id: str
    title: str
    pillar: str
    score_before: float
    score_after: float
    uplift: float
    # "via Salesforce · Data Cloud" — composed from the rec's platform
    # mapping (None when the rec carries neither platform nor feature).
    platform_note: str | None = None


def compose_platform_note(rec: RecForStair) -> str | None:
    """Per-step platform reasoning note (Part 7.3): the platform that
    enables the step-up, plus the concrete feature when known."""
    if rec.platform_name and rec.feature and rec.feature != rec.platform_name:
        return f"via {rec.platform_name} · {rec.feature}"
    if rec.platform_name:
        return f"via {rec.platform_name}"
    if rec.feature:
        return f"via {rec.feature}"
    return None


@dataclass
class StairstepResult:
    steps_by_pillar: dict[str, list[StairStep]] = field(default_factory=dict)
    end_score_by_pillar: dict[str, float] = field(default_factory=dict)
    empty_state: str | None = None  # "no-gaps" | "no-recs" | None
    # When the run carried no scored SUBCAPS to average, the client is still
    # placed on the curve from a coarser signal. This names it:
    # "pillar_scores" | "overall_maturity" | None (subcaps drove the position).
    position_source: str | None = None
    # The EFFECTIVE current-by-pillar the stair was built from — equals the
    # subcap average, or the resolved fallback when that was all-zero. The
    # router surfaces THIS so the response's current position matches the
    # steps (and the frontend's has-any-score gate sees the fallback).
    current_by_pillar: CurrentByPillar | None = None


def _all_zero(current_by_pillar: CurrentByPillar) -> bool:
    return all(current_by_pillar.get(p) == 0.0 for p in PILLARS)


def compute_average_by_pillar(
    subcap_scores: Iterable[tuple[str, float]],
) -> CurrentByPillar:
    """`subcap_scores` is `[(subcap_id, score), ...]`. Pillar is the first
    two chars (P1, P2, P3, P4)."""
    sums: dict[str, float] = dict.fromkeys(PILLARS, 0.0)
    counts: dict[str, int] = dict.fromkeys(PILLARS, 0)
    for subcap_id, score in subcap_scores:
        if not subcap_id or len(subcap_id) < 2:
            continue
        pillar = subcap_id[:2]
        if pillar not in sums:
            continue
        sums[pillar] += score
        counts[pillar] += 1
    return CurrentByPillar(
        P1=round(sums["P1"] / counts["P1"], 2) if counts["P1"] else 0.0,
        P2=round(sums["P2"] / counts["P2"], 2) if counts["P2"] else 0.0,
        P3=round(sums["P3"] / counts["P3"], 2) if counts["P3"] else 0.0,
        P4=round(sums["P4"] / counts["P4"], 2) if counts["P4"] else 0.0,
    )


def compute_stairstep(
    *,
    current_by_pillar: CurrentByPillar,
    recommendations: Iterable[RecForStair],
    target_band_score: float = 4.0,
    score_ceiling: float = 5.0,
    pillar_scores_fallback: CurrentByPillar | None = None,
    overall_maturity_fallback: float | None = None,
) -> StairstepResult:
    """Build the per-pillar stair from current → target.

    Each rec contributes its uplift to every pillar it targets (per
    `uplift_per_pillar`, or `DEFAULT_REC_UPLIFT` as a fallback). Steps are
    cumulative — `score_after` is `score_before + uplift`, clamped to
    `score_ceiling`. The function never goes backwards (if a rec produces
    a negative uplift we drop it).

    Position fallback (2026-07 operator report — Zions): a run with no scored
    SUBCAPS to average by pillar (``current_by_pillar`` all-zero) must still
    place the client on the curve when a coarser maturity signal exists —
    the entity's overall PILLAR scores (``pillar_scores_fallback``), or failing
    those its overall maturity (``overall_maturity_fallback``, seeded across
    all four pillars). ``empty_state='no-gaps'`` ("No scored subcaps yet") is
    honest ONLY when NONE of the three signals exists.
    """
    recs = list(recommendations)
    result = StairstepResult()

    if _all_zero(current_by_pillar):
        if pillar_scores_fallback is not None and not _all_zero(pillar_scores_fallback):
            current_by_pillar = pillar_scores_fallback
            result.position_source = "pillar_scores"
        elif overall_maturity_fallback and overall_maturity_fallback > 0:
            v = round(float(overall_maturity_fallback), 2)
            current_by_pillar = CurrentByPillar(P1=v, P2=v, P3=v, P4=v)
            result.position_source = "overall_maturity"
        else:
            result.current_by_pillar = current_by_pillar
            result.empty_state = "no-gaps"
            return result
    result.current_by_pillar = current_by_pillar
    if not recs:
        result.empty_state = "no-recs"
        return result

    # Bucket recs by which pillar(s) they uplift.
    by_pillar: dict[str, list[tuple[float, RecForStair]]] = {p: [] for p in PILLARS}
    for rec in recs:
        per_pillar = rec.uplift_per_pillar or {}
        # If the rec has no map, assume it targets the pillars implied by
        # its `target_subcap_ids` and use the default uplift.
        if not per_pillar:
            implied = {sid[:2] for sid in rec.target_subcap_ids if sid[:2] in PILLARS}
            per_pillar = dict.fromkeys(implied, DEFAULT_REC_UPLIFT)

        for pillar, uplift in per_pillar.items():
            if pillar not in PILLARS:
                continue
            if uplift <= 0:
                continue
            by_pillar[pillar].append((float(uplift), rec))

    # Order each pillar's recs by uplift desc (rec_id breaks ties).
    for pillar, bucket in by_pillar.items():
        bucket.sort(key=lambda t: (-t[0], t[1].rec_id))
        steps: list[StairStep] = []
        running = current_by_pillar.get(pillar)
        # Skip the pillar entirely if it's already at/above target.
        if running >= target_band_score:
            result.steps_by_pillar[pillar] = []
            result.end_score_by_pillar[pillar] = running
            continue
        for uplift, rec in bucket:
            before = running
            after = min(score_ceiling, round(running + uplift, 2))
            if after <= before:
                continue
            steps.append(StairStep(
                rec_id=rec.rec_id, title=rec.title, pillar=pillar,
                score_before=before, score_after=after, uplift=round(after - before, 2),
                platform_note=compose_platform_note(rec),
            ))
            running = after
            if running >= score_ceiling:
                break
        result.steps_by_pillar[pillar] = steps
        result.end_score_by_pillar[pillar] = running

    if all(not v for v in result.steps_by_pillar.values()):
        result.empty_state = "no-applicable-uplift"
    return result
