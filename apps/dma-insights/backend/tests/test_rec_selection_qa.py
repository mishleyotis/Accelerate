"""rec_selection_qa — the deterministic selection-quality gate (2026-07-06).

Pins the mis-selection classes from the production review: recs not aimed
at the entity's own observed gaps, evidence-free recs, net-new "deploy X"
recs for already-confirmed platforms, duplicate rows under two id
spellings (R1 ≡ REC-01), and phases scheduled before their prerequisites.
Pure-logic, no DB.
"""
from __future__ import annotations

from app.services.rec_selection_qa import (
    RecQaInput,
    norm_rec_id,
    qa_rec_selection,
    rec_richness,
    resolve_duplicate_ids,
)

_SCORES = {"P2C1": 1.79, "P2C4": 2.18, "P4C2": 2.65, "P1C1": 4.3}


def _rec(rec_id="REC-01", **kw) -> RecQaInput:
    return RecQaInput(rec_id=rec_id, **kw)


class TestGapGrounding:
    def test_rec_targeting_a_real_gap_is_clean(self) -> None:
        flags = qa_rec_selection(
            [_rec(title="Financial Services Cloud — P2C1 (1.79→2.8)",
                  root_cause_e_ids=("E-075",))],
            cat_scores=_SCORES,
        )
        assert flags["REC-01"] == []

    def test_rec_targeting_only_strong_categories_flags(self) -> None:
        # P1C1 is already at 4.3 — no observed gap for this entity.
        flags = qa_rec_selection(
            [_rec(title="Strengthen governance",
                  target_subcap_ids=("P1C1.1.1",),
                  root_cause_e_ids=("E-002",))],
            cat_scores=_SCORES,
        )
        assert "targets_no_observed_gap" in flags["REC-01"]

    def test_rec_with_no_category_link_flags_ungrounded(self) -> None:
        flags = qa_rec_selection(
            [_rec(title="Adopt industry best practices",
                  description="Generic guidance with no capability link.")],
            cat_scores=_SCORES,
        )
        assert "ungrounded_gap" in flags["REC-01"]

    def test_no_evidence_link_flags_and_inline_citation_clears(self) -> None:
        flags = qa_rec_selection(
            [_rec("REC-01", title="Fix P2C1 onboarding"),
             _rec("REC-02", title="Fix P2C4 automation",
                  description="Grounded in E-075 and E-081.")],
            cat_scores=_SCORES,
        )
        assert "no_evidence_link" in flags["REC-01"]
        assert "no_evidence_link" not in flags["REC-02"]


class TestPlatformApplicability:
    def test_net_new_deploy_of_confirmed_platform_flags(self) -> None:
        flags = qa_rec_selection(
            [_rec(title="Deploy Salesforce Financial Services Cloud P2C1",
                  platform_id="salesforce", root_cause_e_ids=("E-01",))],
            cat_scores=_SCORES,
            confirmed_platform_ids={"salesforce"},
        )
        assert "already_deployed_platform" in flags["REC-01"]

    def test_optimize_frame_on_confirmed_platform_is_clean(self) -> None:
        flags = qa_rec_selection(
            [_rec(title="Optimize Salesforce journeys for P2C1 gaps",
                  platform_id="salesforce", root_cause_e_ids=("E-01",))],
            cat_scores=_SCORES,
            confirmed_platform_ids={"salesforce"},
        )
        assert flags["REC-01"] == []

    def test_net_new_deploy_of_absent_platform_is_clean(self) -> None:
        flags = qa_rec_selection(
            [_rec(title="Deploy nCino for P2C1 commercial onboarding",
                  platform_id="ncino", root_cause_e_ids=("E-01",))],
            cat_scores=_SCORES,
            confirmed_platform_ids={"salesforce"},
        )
        assert flags["REC-01"] == []


class TestDuplicates:
    def test_id_spelling_collision_flags_and_resolves_to_richest(self) -> None:
        thin = _rec("R1", title="Financial Services Cloud P2C1",
                    root_cause_e_ids=("E-01",), richness=1)
        rich = _rec("REC-01", title="Financial Services Cloud P2C1",
                    description="Full root-cause narrative …",
                    root_cause_e_ids=("E-01",), richness=4)
        flags = qa_rec_selection([thin, rich], cat_scores=_SCORES)
        assert any(f.startswith("duplicate_rec_id:") for f in flags["REC-01"])
        assert resolve_duplicate_ids([thin, rich]) == [("R1", "REC-01")]

    def test_near_identical_titles_flag(self) -> None:
        flags = qa_rec_selection(
            [_rec("REC-01", title="Marketing Cloud Account Engagement journeys P2C1",
                  root_cause_e_ids=("E-01",)),
             _rec("REC-02", title="Marketing Cloud Account Engagement journeys P2C4",
                  root_cause_e_ids=("E-02",))],
            cat_scores=_SCORES,
        )
        assert any(f.startswith("near_duplicate:") for f in flags["REC-02"])

    def test_distinct_titles_do_not_flag(self) -> None:
        flags = qa_rec_selection(
            [_rec("REC-01", title="Data Cloud unified profile P2C1",
                  root_cause_e_ids=("E-01",)),
             _rec("REC-02", title="Service Cloud compliance workflows P2C4",
                  root_cause_e_ids=("E-02",))],
            cat_scores=_SCORES,
        )
        assert not any(f.startswith("near_duplicate:") for f in flags["REC-02"])


class TestSequencing:
    def test_phase_before_prerequisite_flags(self) -> None:
        flags = qa_rec_selection(
            [_rec("REC-01", title="Data Cloud foundation P2C1", phase=3,
                  root_cause_e_ids=("E-01",)),
             _rec("REC-02", title="Einstein NBA activation P2C4", phase=1,
                  prerequisite_rec_ids=("R1",),
                  root_cause_e_ids=("E-02",))],
            cat_scores=_SCORES,
        )
        assert "phase_before_prerequisite:REC-01" in flags["REC-02"]

    def test_missing_prerequisite_flags(self) -> None:
        flags = qa_rec_selection(
            [_rec("REC-02", title="Einstein NBA P2C4", phase=2,
                  prerequisite_rec_ids=("REC-09",),
                  root_cause_e_ids=("E-02",))],
            cat_scores=_SCORES,
        )
        assert "missing_prerequisite:REC-09" in flags["REC-02"]

    def test_prerequisite_cycle_flags_members(self) -> None:
        flags = qa_rec_selection(
            [_rec("REC-01", title="A P2C1", phase=1,
                  prerequisite_rec_ids=("REC-02",), root_cause_e_ids=("E-01",)),
             _rec("REC-02", title="B P2C4", phase=1,
                  prerequisite_rec_ids=("REC-01",), root_cause_e_ids=("E-02",))],
            cat_scores=_SCORES,
        )
        assert "prerequisite_cycle" in flags["REC-01"]
        assert "prerequisite_cycle" in flags["REC-02"]

    def test_consistent_sequencing_is_clean(self) -> None:
        flags = qa_rec_selection(
            [_rec("REC-01", title="Data Cloud foundation P2C1", phase=1,
                  root_cause_e_ids=("E-01",)),
             _rec("REC-02", title="Einstein NBA activation P2C4", phase=2,
                  prerequisite_rec_ids=("REC-01",),
                  root_cause_e_ids=("E-02",))],
            cat_scores=_SCORES,
        )
        assert flags["REC-01"] == [] and flags["REC-02"] == []


def test_norm_rec_id_shapes() -> None:
    assert norm_rec_id("R1") == "REC-01"
    assert norm_rec_id("REC-01") == "REC-01"
    assert norm_rec_id("Recommendation 7") == "REC-07"
    assert norm_rec_id("") == ""


def test_rec_richness_counts_real_fields() -> None:
    from types import SimpleNamespace

    row = SimpleNamespace(
        description="d",
        root_cause_e_ids=["E-01"],
        outcomes={"metric": "P2C1 score 1.79 → 2.8"},
        feature=None,
        target_subcap_ids=[],
    )
    assert rec_richness(row) == 3
