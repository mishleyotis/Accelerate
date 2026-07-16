"""PASS-4 per-rec outcome grounding helpers (derive_recommendations).

Locks the 2026-07-06 de-collapse contract: each rec's metric derives
from ITS OWN stated capability targets (or a category no sibling rec
already claimed), and time/effort vary with the rec's own severity and
scope — the pack audit measured 58/94 clients whose recs all shared one
identical (time, effort, metric) triple.
"""
from __future__ import annotations

from typing import ClassVar

from app.scripts.derive_recommendations import (
    _pass2_title,
    own_target_pairs,
    pick_unused_category,
    severity_scope_effort,
)
from app.services.parsers.rec_files import compose_gap_outcomes


class TestOwnTargetPairs:
    def test_tab_grid_rows(self) -> None:
        # The DOCX score-impact grid shape the banner extractor persists
        # into gap_description.
        desc = (
            "Capability\tCurrent Score\tTarget Score\tImprovement\n"
            "P2C1\t1.79\t2.80\t+1.01\n"
            "P2C4\t2.18\t2.90\t+0.72"
        )
        assert own_target_pairs(desc) == [
            ("P2C1", 1.79, 2.8), ("P2C4", 2.18, 2.9),
        ]

    def test_arrow_clause(self) -> None:
        assert own_target_pairs(
            "P4C1 (Data Management & Governance): 2.10 → 3.0 — first "
            "governed client 360 platform"
        ) == [("P4C1", 2.1, 3.0)]

    def test_first_statement_per_category_wins(self) -> None:
        desc = "P2C1\t1.79\t2.80\t+1.01\nP2C1 (Digital Marketing): 1.79 → 3.0"
        assert own_target_pairs(desc) == [("P2C1", 1.79, 2.8)]

    def test_non_improvements_discarded(self) -> None:
        assert own_target_pairs("P2C1\t3.00\t2.00") == []
        assert own_target_pairs("no capability clause here") == []


class TestPickUnusedCategory:
    SCORES: ClassVar[dict[str, float]] = {"P2C1": 1.8, "P2C4": 2.2, "P4C1": 2.1}

    def test_prefers_worst_unused(self) -> None:
        used: set[str] = set()
        assert pick_unused_category(["P2C1", "P2C4"], self.SCORES, used) == "P2C1"
        used.add("P2C1")
        # Sibling rec sharing the same worst category must NOT collapse
        # onto it — it takes its own next-worst unused category.
        assert pick_unused_category(["P2C1", "P2C4"], self.SCORES, used) == "P2C4"

    def test_falls_back_to_worst_when_all_used(self) -> None:
        used = {"P2C1", "P2C4"}
        assert pick_unused_category(["P2C1", "P2C4"], self.SCORES, used) == "P2C1"

    def test_none_when_no_candidate_scored(self) -> None:
        assert pick_unused_category(["P3C3"], self.SCORES, set()) is None
        assert pick_unused_category([], self.SCORES, set()) is None


class TestSeverityScopeEffort:
    def test_severity_bands(self) -> None:
        assert severity_scope_effort("Severity: [CRITICAL] …", 2) == "LARGE"
        assert severity_scope_effort("Severity: [HIGH] …", 2) == "MEDIUM"
        assert severity_scope_effort("Severity: [LOW] …", 1) == "SMALL"

    def test_scope_bumps_one_level(self) -> None:
        assert severity_scope_effort("Severity: [HIGH] …", 4) == "LARGE"
        assert severity_scope_effort("Severity: [LOW] …", 4) == "MEDIUM"

    def test_none_without_severity_tag(self) -> None:
        # Bare severity words in prose must NOT trigger the band — only
        # the bracketed tag the banner extractor persists.
        assert severity_scope_effort("the HIGH cost of inaction", 3) is None
        assert severity_scope_effort("", 0) is None


class TestPass2TitleChain:
    def test_explicit_title_wins(self) -> None:
        assert _pass2_title({"title": "Deploy FSC", "solution": "x"}) == "Deploy FSC"

    def test_phase6_solution_string_shape(self) -> None:
        # The export shape that shipped 22 '(untitled)' recs pre-fix.
        raw = {"priority": "P1",
               "solution": "Financial Services Cloud + Service Cloud",
               "gap_categories": ["Member Experience"]}
        assert _pass2_title(raw) == "Financial Services Cloud + Service Cloud"

    def test_gap_category_label_fallback(self) -> None:
        assert _pass2_title({"gap_categories": [{"label": "Data Foundation"}]}) \
            == "Data Foundation"

    def test_untitleable_rec_returns_none_never_untitled(self) -> None:
        assert _pass2_title({"priority": "P2"}) is None


class TestMetricsDifferentiate:
    def test_recs_with_own_targets_get_distinct_metrics(self) -> None:
        # Two recs sharing P2C1 as their worst category (the IBKR R1/R2
        # shape that used to collapse to one identical triple).
        rec_a = "Severity: [CRITICAL]\nP2C1\t1.79\t2.80\nP2C4\t2.18\t2.90"
        rec_b = "Severity: [CRITICAL]\nP2C1\t1.79\t3.00\nP2C4\t2.18\t3.10"
        used: set[str] = set()
        outs = []
        for text in (rec_a, rec_b):
            pairs = own_target_pairs(text)
            cat, cur, tgt = next(
                (p for p in pairs if p[0] not in used), pairs[0])
            used.add(cat)
            eb = severity_scope_effort(text, len(pairs))
            outs.append(compose_gap_outcomes(
                label=cat, current=cur, target=tgt,
                peer_median=None, effort_band=eb, peer_name="Peer Bank",
            ))
        assert outs[0]["metric"] == "P2C1 score 1.79 → 2.8"
        assert outs[1]["metric"] == "P2C4 score 2.18 → 3.1"
        assert outs[0]["metric"] != outs[1]["metric"]

    def test_metric_uses_own_target_not_shared_band(self) -> None:
        pairs = own_target_pairs("P3C3\t2.15\t2.70")
        cat, cur, tgt = pairs[0]
        out = compose_gap_outcomes(
            label=cat, current=cur, target=tgt,
            peer_median=2.9, effort_band="MEDIUM", peer_name=None,
        )
        assert out["metric"] == "P3C3 score 2.15 → 2.7 (peer median 2.90)"
        assert "4.0" not in out["metric"]


class TestScopeAlignedWeld:
    """2026-07-14 attribution audit: welded root_cause_e_ids must
    grain-prefix-align with the rec's declared target_subcap_ids — the
    exact qa_surface_attribution predicate (recs fidelity 0.899 < 0.95
    came from category-grain welds diverging from the rec's targets)."""

    def test_predicate_matches_harness_semantics(self) -> None:
        from app.scripts.derive_recommendations import _scope_aligned
        # exact / at-or-under / above grain all align
        assert _scope_aligned(["P2C2.1.1"], ["P2C2.1.1"])
        assert _scope_aligned(["P2C2.1.1.3"], ["P2C2.1.1"])
        assert _scope_aligned(["P2C2"], ["P2C2.1.1"])
        # sibling leaves in the SAME category do NOT align (leaf grain)
        assert not _scope_aligned(["P2C2.3.1"], ["P2C2.1.1"])
        # unlinked evidence never aligns on a target-declaring rec
        assert not _scope_aligned([], ["P2C2.1.1"])
        # prefix must respect the dotted boundary, not raw string prefix
        assert not _scope_aligned(["P2C2.11"], ["P2C2.1"])
