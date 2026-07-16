"""Evidence→subcap mapping threshold ladder (Training Spec Tab 01 §2.1).

Candidate link when cosine >= 0.62; auto-accept >= 0.72 with tier and recency
checks passing; review band 0.45-0.62 routes to adjudication; reject < 0.45
(a link asserted below this threshold anywhere in the app is a QA-ML-03
failure). Hard-negative discipline: a top-1 whose margin over the runner-up
is < 0.05 cosine routes to review regardless of absolute score. The
misattribution budget is < 2% wrong links on the labelled evaluation set,
measured on auto-accepted links — the budget is the contract, these
thresholds are the instrument.

``calibrate`` maps a raw cosine distribution onto the spec scale by
percentile anchoring (the repo's MiniLM cosines run denser/lower than the
spec's nominal scale — recall floor 0.28, attach floor 0.30), so ``classify``
stays meaningful across embedding backends. Pure module: no model imports.
"""
from __future__ import annotations

from bisect import bisect_left

CANDIDATE = 0.62
AUTO_ACCEPT = 0.72
REVIEW_LOW = 0.45
RUNNERUP_MARGIN = 0.05

_DEFAULT_ANCHOR_PCTS: dict[float, float] = {
    25.0: REVIEW_LOW,
    60.0: CANDIDATE,
    80.0: AUTO_ACCEPT,
}


def classify(cos: float, runner_up: float | None = None, *,
             tier_ok: bool = True, recent_ok: bool = True) -> str:
    """Route one candidate link: auto_accept | candidate | review | reject."""
    if cos < REVIEW_LOW:
        return "reject"
    if cos < CANDIDATE:
        return "review"
    if runner_up is not None and (cos - runner_up) < RUNNERUP_MARGIN:
        return "review"
    if cos >= AUTO_ACCEPT:
        return "auto_accept" if (tier_ok and recent_ok) else "candidate"
    return "candidate"


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    rank = (pct / 100.0) * (len(sorted_vals) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = rank - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


class CalibratedMap:
    """Monotonic piecewise-linear map raw cosine -> spec scale, fitted so the
    raw distribution's anchor percentiles land on the spec thresholds."""

    def __init__(self, anchors: list[tuple[float, float]]):
        # anchors: (raw_value, spec_value), strictly increasing in raw
        cleaned: list[tuple[float, float]] = []
        for raw, spec in sorted(anchors):
            if cleaned and raw <= cleaned[-1][0]:
                raw = cleaned[-1][0] + 1e-6
            cleaned.append((raw, spec))
        self.anchors = cleaned

    def __call__(self, raw: float) -> float:
        pts = self.anchors
        if not pts:
            return max(0.0, min(1.0, raw))
        xs = [p[0] for p in pts]
        i = bisect_left(xs, raw)
        if i == 0:
            x0, y0 = pts[0]
            x1, y1 = pts[1] if len(pts) > 1 else (x0 + 1.0, y0 + 1.0)
        elif i >= len(pts):
            x0, y0 = pts[-2] if len(pts) > 1 else (pts[-1][0] - 1.0, pts[-1][1] - 1.0)
            x1, y1 = pts[-1]
        else:
            x0, y0 = pts[i - 1]
            x1, y1 = pts[i]
        if x1 == x0:
            return max(0.0, min(1.0, y1))
        y = y0 + (raw - x0) * (y1 - y0) / (x1 - x0)
        return max(0.0, min(1.0, y))


def calibrate(raw_scores: list[float],
              anchor_pcts: dict[float, float] | None = None) -> CalibratedMap:
    vals = sorted(v for v in raw_scores if isinstance(v, int | float))
    pcts = anchor_pcts or _DEFAULT_ANCHOR_PCTS
    if not vals:
        return CalibratedMap([(0.0, 0.0), (1.0, 1.0)])
    anchors = [(_percentile(vals, p), spec) for p, spec in sorted(pcts.items())]
    return CalibratedMap(anchors)
