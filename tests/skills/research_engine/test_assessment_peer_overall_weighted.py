"""The overall peer median is struck on the same pillar weights as the
client's overall.

WHY THIS EXISTS (B1 Bank, 2026-10-08). `compute()` weighted the client's
overall by the pinned CL_v1 pillar weights (0.20/0.20/0.35/0.25 → 1.43) but
took the peer overall as the plain mean of the four pillar peer figures
(1.64). The report validator caught the gap the sections stated (-0.21)
disagreeing with the sum of their own weighted pillar gaps (-0.22).
"""
from __future__ import annotations

from engine import assessment as A


class _WB:
    def __init__(self, rows):
        self._rows = rows

    def scoring_rows(self):
        return self._rows


def test_peer_overall_uses_the_pinned_pillar_weights(monkeypatch):
    rows = [{"Category": f"P{p}C1", "Score": s, "Evidence_IDs": "E-001"}
            for p, s in ((1, 1.0), (2, 1.0), (3, 1.0), (4, 1.0))]
    monkeypatch.setattr(A, "_weights", lambda wb: {"P1": 0.20, "P2": 0.20, "P3": 0.35, "P4": 0.25})
    monkeypatch.setattr(A, "_peer_medians", lambda wb: {"P1C1": 1.53, "P2C1": 1.6975,
                                                         "P3C1": 1.7175, "P4C1": 1.62})
    monkeypatch.setattr(A, "_category_names", lambda: {})
    got = A.compute(_WB(rows))
    assert got["overall"] == 1.0
    assert got["peer_overall"] == 1.65          # unweighted would read 1.64
    assert got["gap_overall"] == -0.65


def test_a_pillar_with_no_peer_figure_leaves_the_peer_weights_renormalised(monkeypatch):
    rows = [{"Category": "P1C1", "Score": 2.0, "Evidence_IDs": "E-001"},
            {"Category": "P3C1", "Score": 2.0, "Evidence_IDs": "E-001"}]
    monkeypatch.setattr(A, "_weights", lambda wb: {"P1": 0.20, "P2": 0.20, "P3": 0.35, "P4": 0.25})
    monkeypatch.setattr(A, "_peer_medians", lambda wb: {"P1C1": 1.0, "P3C1": 2.1})
    monkeypatch.setattr(A, "_category_names", lambda: {})
    got = A.compute(_WB(rows))
    assert got["peer_overall"] == round((0.2 * 1.0 + 0.35 * 2.1) / 0.55, 2)
