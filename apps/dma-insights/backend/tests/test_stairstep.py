"""Tests for the stairstep-curve service."""
from __future__ import annotations

from app.services.stairstep import (
    DEFAULT_REC_UPLIFT,
    CurrentByPillar,
    RecForStair,
    compute_average_by_pillar,
    compute_stairstep,
)


def _rec(
    rec_id: str,
    *,
    title: str = "rec",
    target_subcap_ids: list[str] | None = None,
    uplift: dict[str, float] | None = None,
) -> RecForStair:
    return RecForStair(
        rec_id=rec_id,
        title=title,
        target_subcap_ids=target_subcap_ids or [],
        uplift_per_pillar=uplift,
    )


class TestComputeAverageByPillar:
    def test_groups_by_pillar_prefix(self) -> None:
        scores = [
            ("P1C1.1.1", 2.0),
            ("P1C2.1.1", 4.0),
            ("P2C1.1.1", 3.0),
        ]
        cur = compute_average_by_pillar(scores)
        assert cur.P1 == 3.0
        assert cur.P2 == 3.0
        assert cur.P3 == 0.0
        assert cur.P4 == 0.0

    def test_skips_malformed_ids(self) -> None:
        scores = [
            ("", 2.0),
            ("X", 3.0),
            ("P1C1.1.1", 4.0),
        ]
        cur = compute_average_by_pillar(scores)
        assert cur.P1 == 4.0

    def test_unknown_pillar_dropped(self) -> None:
        scores = [("P9C1.1.1", 4.0), ("P1C1.1.1", 3.0)]
        cur = compute_average_by_pillar(scores)
        assert cur.P1 == 3.0


class TestComputeStairstep:
    def test_empty_recs_returns_no_recs_empty_state(self) -> None:
        current = CurrentByPillar(P1=2.0, P2=2.0, P3=2.0, P4=2.0)
        res = compute_stairstep(current_by_pillar=current, recommendations=[])
        assert res.empty_state == "no-recs"

    def test_zero_current_returns_no_gaps(self) -> None:
        current = CurrentByPillar(P1=0.0, P2=0.0, P3=0.0, P4=0.0)
        res = compute_stairstep(
            current_by_pillar=current,
            recommendations=[_rec("REC-1", uplift={"P1": 0.5})],
        )
        assert res.empty_state == "no-gaps"

    def test_zero_current_falls_back_to_overall_maturity(self) -> None:
        # 2026-07 operator report (Zions): a run with no scored SUBCAPS must
        # still place the client on the curve from its overall maturity rather
        # than claiming "no scored subcaps".
        current = CurrentByPillar(P1=0.0, P2=0.0, P3=0.0, P4=0.0)
        res = compute_stairstep(
            current_by_pillar=current,
            recommendations=[_rec("REC-1", uplift={"P1": 0.5})],
            overall_maturity_fallback=1.76,
        )
        assert res.empty_state is None  # NOT "no scored subcaps"
        assert res.position_source == "overall_maturity"
        assert res.current_by_pillar is not None
        assert res.current_by_pillar.P1 == 1.76  # every pillar seeded
        assert res.steps_by_pillar["P1"][0].score_before == 1.76

    def test_zero_current_prefers_pillar_scores_fallback(self) -> None:
        # Overall PILLAR scores win over the single overall-maturity number.
        current = CurrentByPillar(P1=0.0, P2=0.0, P3=0.0, P4=0.0)
        pillars = CurrentByPillar(P1=2.5, P2=1.4, P3=2.6, P4=1.8)
        res = compute_stairstep(
            current_by_pillar=current,
            recommendations=[_rec("REC-1", uplift={"P2": 0.5})],
            pillar_scores_fallback=pillars,
            overall_maturity_fallback=1.76,
        )
        assert res.position_source == "pillar_scores"
        assert res.current_by_pillar.P2 == 1.4

    def test_zero_current_no_signal_still_no_gaps(self) -> None:
        # No subcaps AND no coarser signal → the honest empty state remains.
        current = CurrentByPillar(P1=0.0, P2=0.0, P3=0.0, P4=0.0)
        res = compute_stairstep(
            current_by_pillar=current,
            recommendations=[_rec("REC-1", uplift={"P1": 0.5})],
            overall_maturity_fallback=0.0,
        )
        assert res.empty_state == "no-gaps"
        assert res.position_source is None

    def test_default_uplift_when_rec_lacks_per_pillar(self) -> None:
        current = CurrentByPillar(P1=2.0, P2=2.0, P3=2.0, P4=2.0)
        res = compute_stairstep(
            current_by_pillar=current,
            recommendations=[
                _rec("REC-1", target_subcap_ids=["P1C1.1.1"]),
            ],
        )
        steps = res.steps_by_pillar["P1"]
        assert len(steps) == 1
        assert steps[0].uplift == DEFAULT_REC_UPLIFT
        assert steps[0].score_after == round(2.0 + DEFAULT_REC_UPLIFT, 2)

    def test_recs_ordered_by_uplift_desc(self) -> None:
        current = CurrentByPillar(P1=2.0, P2=2.0, P3=2.0, P4=2.0)
        res = compute_stairstep(
            current_by_pillar=current,
            recommendations=[
                _rec("REC-A", uplift={"P1": 0.3}),
                _rec("REC-B", uplift={"P1": 0.9}),
                _rec("REC-C", uplift={"P1": 0.5}),
            ],
        )
        rec_ids = [s.rec_id for s in res.steps_by_pillar["P1"]]
        assert rec_ids == ["REC-B", "REC-C", "REC-A"]

    def test_caps_at_score_ceiling(self) -> None:
        # P1 below the default target (4.0) so the pillar runs; uplift big
        # enough that the cumulative score would exceed the ceiling.
        current = CurrentByPillar(P1=3.6, P2=0.0, P3=0.0, P4=0.0)
        res = compute_stairstep(
            current_by_pillar=current,
            recommendations=[_rec("REC-1", uplift={"P1": 1.8})],
            score_ceiling=5.0,
        )
        assert res.steps_by_pillar["P1"][0].score_after == 5.0
        # Cumulative running stops at the ceiling
        assert res.end_score_by_pillar["P1"] == 5.0

    def test_drops_non_positive_uplift(self) -> None:
        current = CurrentByPillar(P1=2.0, P2=2.0, P3=2.0, P4=2.0)
        res = compute_stairstep(
            current_by_pillar=current,
            recommendations=[
                _rec("REC-1", uplift={"P1": -0.5}),  # ignored
                _rec("REC-2", uplift={"P1": 0.4}),
            ],
        )
        assert [s.rec_id for s in res.steps_by_pillar["P1"]] == ["REC-2"]

    def test_pillar_at_target_skipped(self) -> None:
        current = CurrentByPillar(P1=4.5, P2=2.0, P3=2.0, P4=2.0)
        res = compute_stairstep(
            current_by_pillar=current,
            recommendations=[
                _rec("REC-1", uplift={"P1": 0.3, "P2": 0.3}),
            ],
        )
        # P1 already at/above target_band_score (4.0 default) → no steps
        assert res.steps_by_pillar["P1"] == []
        assert res.end_score_by_pillar["P1"] == 4.5
        # P2 gets the recommendation
        assert len(res.steps_by_pillar["P2"]) == 1


# ── Part 7.3: per-step platform reasoning notes ─────────────────────────

from app.services.stairstep import compose_platform_note  # noqa: E402


class TestPlatformNotes:
    def test_note_composes_platform_and_feature(self) -> None:
        rec = RecForStair(
            rec_id="REC-04", title="t", target_subcap_ids=["P4C1.1.1"],
            uplift_per_pillar={"P4": 0.5},
            platform_name="Salesforce", feature="Data Cloud",
        )
        assert compose_platform_note(rec) == "via Salesforce · Data Cloud"

    def test_note_platform_only_and_none(self) -> None:
        plat_only = RecForStair(
            rec_id="R1", title="t", target_subcap_ids=[],
            uplift_per_pillar=None, platform_name="nCino",
        )
        assert compose_platform_note(plat_only) == "via nCino"
        bare = RecForStair(
            rec_id="R2", title="t", target_subcap_ids=[], uplift_per_pillar=None,
        )
        assert compose_platform_note(bare) is None

    def test_steps_carry_platform_note(self) -> None:
        current = CurrentByPillar(P1=0.0, P2=0.0, P3=2.0, P4=0.0)
        result = compute_stairstep(
            current_by_pillar=current,
            recommendations=[RecForStair(
                rec_id="REC-09", title="Workflow Engine",
                target_subcap_ids=["P3C2.1.1"],
                uplift_per_pillar={"P3": 0.5},
                platform_name="nCino", feature="Workflow Engine",
            )],
        )
        step = result.steps_by_pillar["P3"][0]
        assert step.platform_note == "via nCino · Workflow Engine"
