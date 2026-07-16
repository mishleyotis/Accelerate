"""Pattern-drift detection service — computes how an entity's score
profile diverges from its cohort norm per pillar + per sub-cap.

Pure module. Caller fetches subcap_scores + peer_benchmarks and feeds
them in; this module returns a structured drift signal that powers a
"This entity is drifting from cohort norm by X" affordance on D1/D3.

State-branch contract (visible in the returned DriftReport):
  - Cohort has fewer than `min_n` peers for a subcap → that subcap is
    reported as `cohort_insufficient` and skipped from drift maths.
  - Entity has no score for a subcap that the cohort medians cover →
    subcap reported as `entity_missing` and skipped.
  - Otherwise drift_score = current - peer_median. We bucket into:
        critical_low   : drift <= -1.0
        below          : -1.0 < drift < -0.4
        nominal        : -0.4 <= drift <= 0.4
        above          : 0.4 < drift < 1.0
        critical_high  : drift >= 1.0
  - The aggregate pillar drift averages drift_score across the subcaps
    in that pillar; if all subcaps are skipped, the pillar drift is None.

The result is intentionally deterministic — same inputs → same drifts —
so the test suite can lock the numbers down.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

DriftBucket = Literal[
    "critical_low", "below", "nominal", "above", "critical_high",
    "cohort_insufficient", "entity_missing",
]

PILLARS: tuple[str, ...] = ("P1", "P2", "P3", "P4")

CRITICAL_LOW_THRESHOLD = -1.0
BELOW_THRESHOLD = -0.4
ABOVE_THRESHOLD = 0.4
CRITICAL_HIGH_THRESHOLD = 1.0


@dataclass(frozen=True)
class SubcapDrift:
    subcap_id: str
    pillar: str
    bucket: DriftBucket
    drift_score: float | None      # entity_score - peer_median; None if skipped
    entity_score: float | None
    peer_median: float | None
    peer_n: int


@dataclass
class PillarDrift:
    pillar: str
    drift_score: float | None
    subcap_count: int
    by_bucket: dict[str, int] = field(default_factory=dict)


@dataclass
class DriftReport:
    subcap_drifts: list[SubcapDrift] = field(default_factory=list)
    pillar_drifts: list[PillarDrift] = field(default_factory=list)
    cohort_insufficient_count: int = 0
    entity_missing_count: int = 0
    overall_drift: float | None = None   # mean across pillar_drifts


def _bucket_for(drift: float) -> DriftBucket:
    if drift <= CRITICAL_LOW_THRESHOLD:
        return "critical_low"
    if drift < BELOW_THRESHOLD:
        return "below"
    if drift >= CRITICAL_HIGH_THRESHOLD:
        return "critical_high"
    if drift > ABOVE_THRESHOLD:
        return "above"
    return "nominal"


def compute_drift(
    *,
    entity_scores: Iterable[tuple[str, float]],
    peer_benchmarks: Iterable[tuple[str, float, int]],  # (subcap_id, median, n)
    min_n: int = 3,
) -> DriftReport:
    """Returns DriftReport scored against the cohort.

    `entity_scores` and `peer_benchmarks` are iterables (so callers can
    stream rows from SQLAlchemy without materializing). Both are
    converted to dicts here for O(1) per-subcap lookup.
    """
    by_subcap_score = {sid: float(score) for sid, score in entity_scores}
    by_subcap_peer = {
        sid: (float(median), int(n))
        for sid, median, n in peer_benchmarks
    }

    report = DriftReport()
    pillar_acc: dict[str, list[float]] = {p: [] for p in PILLARS}
    pillar_bucket_counts: dict[str, dict[str, int]] = {p: {} for p in PILLARS}

    # Walk every subcap that appears in either map so we surface both
    # cohort_insufficient AND entity_missing cases.
    all_subcap_ids = sorted(set(by_subcap_score) | set(by_subcap_peer))
    for sid in all_subcap_ids:
        pillar = sid[:2] if sid[:2] in PILLARS else None
        entity_score = by_subcap_score.get(sid)
        peer = by_subcap_peer.get(sid)

        if peer is None or peer[1] < min_n:
            bucket: DriftBucket = "cohort_insufficient"
            report.cohort_insufficient_count += 1
            report.subcap_drifts.append(SubcapDrift(
                subcap_id=sid,
                pillar=pillar or "?",
                bucket=bucket,
                drift_score=None,
                entity_score=entity_score,
                peer_median=peer[0] if peer else None,
                peer_n=peer[1] if peer else 0,
            ))
            continue

        if entity_score is None:
            report.entity_missing_count += 1
            report.subcap_drifts.append(SubcapDrift(
                subcap_id=sid,
                pillar=pillar or "?",
                bucket="entity_missing",
                drift_score=None,
                entity_score=None,
                peer_median=peer[0],
                peer_n=peer[1],
            ))
            continue

        drift = round(entity_score - peer[0], 2)
        bucket = _bucket_for(drift)
        report.subcap_drifts.append(SubcapDrift(
            subcap_id=sid,
            pillar=pillar or "?",
            bucket=bucket,
            drift_score=drift,
            entity_score=entity_score,
            peer_median=peer[0],
            peer_n=peer[1],
        ))
        if pillar is not None:
            pillar_acc[pillar].append(drift)
            pillar_bucket_counts[pillar][bucket] = (
                pillar_bucket_counts[pillar].get(bucket, 0) + 1
            )

    # Roll up pillar drifts
    pillar_means: list[float] = []
    for p in PILLARS:
        drifts = pillar_acc[p]
        if drifts:
            mean = round(sum(drifts) / len(drifts), 2)
            report.pillar_drifts.append(PillarDrift(
                pillar=p,
                drift_score=mean,
                subcap_count=len(drifts),
                by_bucket=dict(pillar_bucket_counts[p]),
            ))
            pillar_means.append(mean)
        else:
            report.pillar_drifts.append(PillarDrift(
                pillar=p,
                drift_score=None,
                subcap_count=0,
                by_bucket={},
            ))

    if pillar_means:
        report.overall_drift = round(sum(pillar_means) / len(pillar_means), 2)
    return report
