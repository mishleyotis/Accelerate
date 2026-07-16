"""Platform readiness index — traffic-light aggregation over prerequisite checks.

Each platform documents its prerequisites (per PRD §08). For a given run,
each prereq is evaluated against actual `subcap_scores` and emits a status:

  - MET     : current_score >= threshold
  - PARTIAL : within 0.5 of threshold (but below)
  - UNMET   : > 0.5 below threshold

Aggregate readiness:
  - any UNMET → red
  - else any PARTIAL → amber
  - all MET → green
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ReadinessLight = Literal["green", "amber", "red"]
CheckStatus = Literal["MET", "PARTIAL", "UNMET", "MISSING"]


@dataclass
class PrereqCheck:
    name: str
    required_subcap_id: str
    threshold: float
    status: CheckStatus
    current_score: float | None
    note: str | None = None


def evaluate_prereq(
    *,
    name: str,
    required_subcap_id: str,
    threshold: float,
    scores_by_subcap: dict[str, float],
) -> PrereqCheck:
    current = scores_by_subcap.get(required_subcap_id)
    if current is None:
        return PrereqCheck(
            name=name,
            required_subcap_id=required_subcap_id,
            threshold=threshold,
            status="MISSING",
            current_score=None,
            note=f"no score recorded for {required_subcap_id}",
        )
    if current >= threshold:
        status: CheckStatus = "MET"
    elif current >= threshold - 0.5:
        status = "PARTIAL"
    else:
        status = "UNMET"
    return PrereqCheck(
        name=name,
        required_subcap_id=required_subcap_id,
        threshold=threshold,
        status=status,
        current_score=current,
    )


def aggregate_readiness(checks: list[PrereqCheck]) -> ReadinessLight:
    if not checks:
        return "amber"  # no checks ≈ insufficient info
    # MISSING is treated the same as UNMET for the traffic light: we don't
    # have evidence the prereq holds, so we cannot claim readiness.
    if any(c.status in ("UNMET", "MISSING") for c in checks):
        return "red"
    if any(c.status == "PARTIAL" for c in checks):
        return "amber"
    return "green"


def failing_prereq_subcaps(checks: list[PrereqCheck]) -> list[str]:
    """Subcap ids of every non-MET prerequisite — the fit engine v2's
    sequencing input (platform A precedes B when A addresses one of B's
    failing prereq subcaps). Deterministic order: UNMET/MISSING first
    (hard blockers), then PARTIAL."""
    hard = [c.required_subcap_id for c in checks if c.status in ("UNMET", "MISSING")]
    soft = [c.required_subcap_id for c in checks if c.status == "PARTIAL"]
    return hard + soft
