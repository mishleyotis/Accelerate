"""EPIC (2026-10-18): Executive_Summary's "Peer Median (est.)" attached the
cohort average of three unnamed assessed brokers to the five named, unscored
peers ("1.4 — locked peer set: Alera …"), and the peer overall was an
unweighted mean of pillar figures set beside a pillar-WEIGHTED overall."""
from __future__ import annotations

from engine import assessment, prelim
from fixtures import scored_run


def _cohort(cats):
    # a different figure per pillar, so weighted and unweighted means differ
    by_pillar = {"P1": 1.5, "P2": 3.0, "P3": 2.0, "P4": 4.0}
    return {"entities": 3, "floor": 3, "basis": "recomputed", "sub_vertical": "CU",
            "categories": {c: {"n": 3, "mean": by_pillar[c[:2]], "median": by_pillar[c[:2]],
                               "p25": by_pillar[c[:2]] - 0.1, "p75": by_pillar[c[:2]] + 0.1}
                           for c in cats}}


def _exec(wb):
    return {str(r.get("Field")): str(r.get("Value")) for r in wb.rows("Executive_Summary")}


def test_a_cohort_peer_figure_is_labelled_as_the_cohort_not_the_locked_set(tmp_path):
    run, wb, cells, ev = scored_run(tmp_path)
    cats = [r["Category_ID"] for r in wb.rows("Peer_Benchmarks") if r.get("Category_ID")]
    prelim.fill_cohort_peers(wb, _cohort(cats), overwrite=True)
    assessment.rollup(wb)
    v = _exec(run.open())["Peer Median (est.)"]
    assert "cohort average of 3 other assessed" in v
    assert "identified, not scored" in v


def test_the_peer_overall_is_weighted_like_the_overall():
    # EPIC's own figures: IB_v1 weights 20/35/20/25
    pillars = [{"pillar_id": "P1", "score": 1.44, "weight": 0.20, "peer_median": 1.38},
               {"pillar_id": "P2", "score": 1.30, "weight": 0.35, "peer_median": 1.40},
               {"pillar_id": "P3", "score": 1.06, "weight": 0.20, "peer_median": 1.39},
               {"pillar_id": "P4", "score": 1.36, "weight": 0.25, "peer_median": 1.41}]
    assert assessment.peer_overall_of(pillars) == 1.40          # 1.3965
    # unequal weights and spread figures: weighted 2.7, unweighted 2.25
    skew = [{"score": 1.0, "weight": 0.1, "peer_median": 1.0},
            {"score": 1.0, "weight": 0.1, "peer_median": 2.0},
            {"score": 1.0, "weight": 0.1, "peer_median": 3.0},
            {"score": 1.0, "weight": 0.7, "peer_median": 3.0}]
    assert assessment.peer_overall_of(skew) == 2.7
    # a pillar with no score does not weigh in
    skew[3]["score"] = None
    assert assessment.peer_overall_of(skew) == 2.0
