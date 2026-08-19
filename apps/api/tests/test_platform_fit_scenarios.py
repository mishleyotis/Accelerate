"""Two real clients, their own stated objectives, and what the engine ranks.

"Ensure the top platform matches the need for the client accordingly and
aligns with their strategic objectives" — owner, 2026-08-19.

That is not a property of the arithmetic; it is a property of the arithmetic
MEETING a particular client. So these cases are the two promoted clients'
actual shapes: the platforms they carry, the readiness verdicts they state,
and alignments read from each institution's own answer in its executive
summary. If the engine puts the wrong card first for either of them, it is
wrong however clean its unit tests are.

Baxter is the case worth reading twice. Three of its five cards state "NOT
READY YET", and two of those promoted at rank 2 and rank 3 with fits of 70.0
and 73.0 — a platform nothing is ready for, sitting near the top of a page a
client reads as a recommendation. That is the "red but hot" defect a 2026-06
audit measured at 95 of 470 cards, live on the client every other client is
compared against.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "shared"))

import platform_fit as pf  # noqa: E402


def cells(n, cat, score=2.4, es=0.8, sev=("high",)):
    return [pf.Cell(subcap_id=f"{cat}.{i}", current_score=score,
                    category_id=cat, severities=sev, evidence_strength=es)
            for i in range(1, n + 1)]


def run_gaps(cands):
    """The run's whole gap surface — every candidate's cells plus a tail the
    platforms do not address. Interconnect is measured against this, so a
    scenario without it is scoring a different engine from production."""
    out = [c for cand in cands for c in cand.cells]
    out += [pf.Cell(f"P6C6.6.{i}", 2.2, "P6C6", ("medium",), 0.7)
            for i in range(1, 9)]
    return out


# ── Logix: governance first, because it is cheap now and dear later ────

LOGIX = [
    pf.Candidate("MLflow (Databricks-managed) with a catalogue", "L3-DB-MLFLOW",
                 cells(6, "P4C1"), readiness="amber", alignment=0.95),
    pf.Candidate("Salesforce Data Cloud", "L3-SF-DC-CORE",
                 cells(6, "P4C2"), readiness="amber", alignment=0.72),
    pf.Candidate("Salesforce Agentforce Service Agent", "L3-SF-AF-SVC",
                 cells(5, "P2C1"), readiness="amber", alignment=0.55),
    pf.Candidate("Fusion Framework System", "L3-PARTNER-FUSION",
                 cells(6, "P3C3"), readiness="amber", alignment=0.45),
    pf.Candidate("Marketing Cloud Engagement", "L3-SF-MC-ENG",
                 cells(4, "P2C2"), readiness="amber", alignment=0.25),
]


def test_logix_leads_with_the_platform_its_own_answer_names_first():
    """The institution's answer: "Stand up model governance first — an
    inventory, a validation standard and a promotion path — so that anything
    built above it is auditable on the day supervision starts."""
    ranked = pf.rank(LOGIX, run_gaps(LOGIX))
    assert ranked[0]["platform"].startswith("MLflow"), \
        [r["platform"] for r in ranked]


def test_logix_ranks_marketing_last_without_discarding_it():
    """No objective the institution states names growth tooling. Last is the
    honest place for it; absent would be a different claim."""
    ranked = pf.rank(LOGIX, run_gaps(LOGIX))
    assert ranked[-1]["platform"] == "Marketing Cloud Engagement"
    assert ranked[-1]["fit_score"] > 0


def test_logix_order_follows_its_stated_sequence():
    ranked = [r["platform"] for r in pf.rank(LOGIX, run_gaps(LOGIX))]
    assert ranked.index("Salesforce Data Cloud") < ranked.index("Fusion Framework System")


# ── Baxter: the foundation before the visible next step ────────────────

BAXTER = [
    pf.Candidate("MuleSoft Anypoint Platform", "L3-MS-ANYPOINT",
                 cells(7, "P3C1"), readiness="amber", alignment=0.95),
    pf.Candidate("Salesforce Data Cloud", "L3-SF-DC-CORE",
                 cells(8, "P4C2"), readiness="red", alignment=0.90),
    pf.Candidate("Service Cloud consolidation", "L3-SF-SC-CORE",
                 cells(9, "P2C1"), readiness="red", alignment=0.80),
    # The institution places these ON the new foundation, in its own words,
    # so they carry that dependency. Without it the workload outranked the
    # foundation it sits on — caught by running this very scenario.
    pf.Candidate("CRM Analytics", "L3-SF-CRMA",
                 cells(5, "P4C1"), readiness="amber", alignment=0.70,
                 depends_on=("MuleSoft Anypoint Platform",
                             "Salesforce Data Cloud")),
    pf.Candidate("Cross-system workflow orchestration", None,
                 cells(6, "P3C2"), readiness="red", alignment=0.40,
                 depends_on=("MuleSoft Anypoint Platform",)),
]


def test_baxter_leads_with_the_integration_backbone_its_answer_names_first():
    """"Lay the foundation first, in two moves … an integration backbone to
    replace point-to-point connections across the Jack Henry core, lending and
    channel platforms." """
    ranked = pf.rank(BAXTER, run_gaps(BAXTER))
    assert ranked[0]["platform"] == "MuleSoft Anypoint Platform", \
        [(r["platform"], r["fit_score"]) for r in ranked]


def test_every_not_ready_baxter_platform_falls_out_of_the_hot_band():
    """THE LIVE DEFECT. Two of these promoted at rank 2 and 3 with 70.0 and
    73.0 while stating "NOT READY YET"."""
    ranked = {r["platform"]: r for r in pf.rank(BAXTER, run_gaps(BAXTER))}
    for name in ("Salesforce Data Cloud", "Service Cloud consolidation",
                 "Cross-system workflow orchestration"):
        assert ranked[name]["fit_score"] < pf.HOT_THRESHOLD, \
            f"{name} states NOT READY YET and scores {ranked[name]['fit_score']}"


def test_a_workload_never_outranks_the_foundation_it_sits_on():
    """THE DEFECT THIS SCENARIO FOUND. Readiness as a multiplier pushed the
    unready foundation below a workload that depends on it — and "fund the
    visible next step or fix the foundation those steps depend on first" is
    the question this client's own summary asks. Engine v2 kept a prerequisite
    DAG beside the fit for exactly this; the first version of this engine
    dropped it."""
    ranked = [r["platform"] for r in pf.rank(BAXTER, run_gaps(BAXTER))]
    assert ranked.index("Salesforce Data Cloud") < ranked.index("CRM Analytics"), ranked
    assert ranked.index("MuleSoft Anypoint Platform") < \
        ranked.index("Cross-system workflow orchestration")


def test_a_card_held_back_by_a_prerequisite_says_so():
    held = next(r for r in pf.rank(BAXTER, run_gaps(BAXTER)) if r["platform"] == "CRM Analytics")
    assert "sequenced" in held["rank_basis"]
    assert "Salesforce Data Cloud" in held["rank_basis"]


def test_a_ready_platform_outranks_a_better_aligned_unready_one():
    """The sequencing the client itself argues for: the foundation move that
    can actually start goes first. Data Cloud is only 0.05 less aligned than
    MuleSoft and addresses MORE cells — readiness is what separates them, and
    that is the point of folding it in as a multiplier."""
    ranked = [r["platform"] for r in pf.rank(BAXTER, run_gaps(BAXTER))]
    assert ranked.index("MuleSoft Anypoint Platform") < \
        ranked.index("Salesforce Data Cloud")
    fits = {r["platform"]: r["fit_score"] for r in pf.rank(BAXTER, run_gaps(BAXTER))}
    assert fits["MuleSoft Anypoint Platform"] > fits["Salesforce Data Cloud"]


def test_the_unnamed_orchestration_card_ranks_last():
    """It names no product, the institution states no objective for
    orchestration as such, and it is not ready. It also carries the lowest
    fit on the page, so nothing has to be done to put it last."""
    ranked = pf.rank(BAXTER, run_gaps(BAXTER))
    assert ranked[-1]["platform"] == "Cross-system workflow orchestration"
    assert ranked[-1]["fit_score"] == min(r["fit_score"] for r in ranked)


def test_within_one_dependency_level_the_better_fit_still_leads():
    """The sequencing repairs the order; it must not BECOME the order. A
    first-found pass let a 30.9 card precede a 47.5 one that was waiting on
    one more prerequisite, which is the sequencing quietly outranking the
    fit."""
    ranked = [r["platform"] for r in pf.rank(BAXTER, run_gaps(BAXTER))]
    assert ranked.index("CRM Analytics") < \
        ranked.index("Cross-system workflow orchestration")


def test_a_page_with_no_declared_prerequisites_is_pure_fit_order():
    """Logix declares none, so nothing may move — and every card says `fit`
    as its basis rather than claiming a sequence that was not applied."""
    ranked = pf.rank(LOGIX, run_gaps(LOGIX))
    assert [r["rank_basis"] for r in ranked] == ["fit"] * 5
    fits = [r["fit_score"] for r in ranked]
    assert fits == sorted(fits, reverse=True)


# ── the two clients are comparable now, which was the complaint ────────

def test_both_clients_are_scored_by_one_engine_on_one_scale():
    for ranked in (pf.rank(LOGIX, run_gaps(LOGIX)), pf.rank(BAXTER, run_gaps(BAXTER))):
        assert [r["rank"] for r in ranked] == [1, 2, 3, 4, 5]
        for r in ranked:
            assert 0.0 <= r["fit_score"] <= pf.FIT_CAP
            assert r["alignment_basis"] == pf.ALIGNMENT_STATED
            assert abs(sum(f["contribution"] for f in r["factors"])
                       - r["subtotal"]) < 1e-9


def test_neither_client_renders_two_cards_with_one_rank():
    for ranked in (pf.rank(LOGIX, run_gaps(LOGIX)), pf.rank(BAXTER, run_gaps(BAXTER))):
        ranks = [r["rank"] for r in ranked]
        assert len(set(ranks)) == len(ranks)
