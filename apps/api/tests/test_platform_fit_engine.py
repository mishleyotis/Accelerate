"""Stress-testing the fit engine: does the top platform match the client?

The arithmetic being right is the easy half. These cases attack the RANKING,
because a score nobody can argue with can still put the wrong platform first —
which is how a client ends up reading a recommendation that does not serve any
objective they hold.

Every guarantee below was a measured defect in the engine this one descends
from (2026-06 platform audit, 470 cards across 94 clients):

  95/470  "red but hot" — fit >= 80 with every readiness prerequisite failing
  42/470  clamped identically — four clients rendered five identical cards
 570/685  breakdown disagreed with the headline it was supposed to explain
 470/470  READY — INSUFFICIENT_EVIDENCE was unreachable

Owner decision 2026-08-19: readiness multiplies, it does not add. Owner
instruction the same day: "Ensure the top platform matches the need for the
client accordingly and aligns with their strategic objectives."
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "shared"))

import platform_fit as pf  # noqa: E402


def cell(sid, score=2.0, cat="P1C1", sev=("high",), es=0.8, incumbent=False):
    return pf.Cell(subcap_id=sid, current_score=score, category_id=cat,
                   severities=sev, evidence_strength=es,
                   incumbent_covers=incumbent)


def cand(name, cells=None, **kw):
    # THREE cells by default, because the contract discards below three and
    # the engine now says TOO_NARROW rather than ranking a one-cell card. A
    # helper that defaulted to one made every case about something else.
    return pf.Candidate(platform=name, l3_area=kw.pop("l3_area", "Area"),
                        cells=cells if cells is not None
                        else [cell(f"P1C1.1.{i}") for i in (1, 2, 3)],
                        **kw)


# The run's other gap cells — interconnect measures the mass this platform
# would LIFT without addressing, so it is 0 without them. Production always
# supplies them; a test that omits them is testing a different engine.
RUN_GAPS = [cell(f"P1C1.9.{i}", 2.0, "P1C1") for i in range(1, 6)] + \
           [cell(f"P9C9.9.{i}", 2.0, "P9C9") for i in range(1, 4)]


# ── the guarantee the owner chose the multiplicative shape for ─────────

def test_a_red_platform_can_never_reach_the_hot_band():
    """95 of 470 cards scored hot while every prerequisite was failing. With
    readiness as a MULTIPLIER the highest reachable red fit is 62, so this is
    arithmetically impossible rather than merely discouraged."""
    best = cand("Everything", [cell(f"P1C1.1.{i}", 1.0, "P1C1", ("critical",), 1.0)
                               for i in range(1, 9)],
                family_absent=True, readiness="red", alignment=1.0)
    got = pf.score(best)["fit_score"]
    assert got < pf.HOT_THRESHOLD, \
        f"a red-readiness platform scored {got}, at or above the hot band"
    assert got <= 62.0 + 1e-9


def test_the_same_platform_green_does_reach_it():
    """The guard must bind on readiness, not on the score being small."""
    c = cand("Everything", [cell(f"P1C1.1.{i}", 1.0, "P1C1", ("critical",), 1.0)
                            for i in range(1, 9)],
             family_absent=True, readiness="green", alignment=1.0)
    assert pf.score(c, RUN_GAPS)["fit_score"] >= pf.HOT_THRESHOLD


def test_amber_sits_between_them():
    def fit(r):
        return pf.score(cand("P", [cell("P1C1.1.1", 1.0)], readiness=r,
                             alignment=0.8))["fit_score"]
    assert fit("red") < fit("amber") < fit("green")


# ── the owner's ask: the top platform serves the client's objective ────

def test_a_well_aligned_platform_outranks_a_broader_unaligned_one():
    """THE INSTRUCTION, as arithmetic. A platform touching four cells that
    serves no objective the client states must not outrank one touching two
    that serves the objective they lead with."""
    broad = cand("Broad but off-strategy",
                 [cell(f"P2C1.1.{i}", 2.5, "P2C1") for i in range(1, 5)],
                 alignment=0.05, alignment_quote="not named in the plan")
    aligned = cand("Serves the stated objective",
                   [cell("P1C1.1.1", 2.0, "P1C1"), cell("P1C1.1.2", 2.0, "P1C1")],
                   alignment=0.95,
                   alignment_quote="'model governance before supervision attaches'")
    order = [r["platform"] for r in pf.rank([broad, aligned])]
    assert order[0] == "Serves the stated objective", order


def test_alignment_cannot_rescue_a_platform_that_addresses_nothing():
    """The other direction, or alignment becomes a way to promote a card with
    no gap behind it. A platform addressing nothing is refused by state
    whatever the objective says."""
    empty = cand("Perfectly aligned, addresses nothing", [], alignment=1.0)
    row = pf.score(empty, RUN_GAPS)
    assert row["state"] == pf.STATE_TOO_NARROW
    assert row["fit_score"] < pf.HOT_THRESHOLD


def test_a_platform_under_the_minimum_cell_count_is_too_narrow():
    """The contract: "drop it when it addresses fewer than 3 of this run's
    cells". Said as a state rather than by silently ranking it low."""
    thin = cand("Two cells only", [cell("P1C1.1.1"), cell("P1C1.1.2")],
                alignment=0.9)
    assert pf.score(thin, RUN_GAPS)["state"] == pf.STATE_TOO_NARROW


def test_raising_alignment_never_lowers_the_fit():
    base = cand("P", [cell("P1C1.1.1")], alignment=0.2)
    more = cand("P", [cell("P1C1.1.1")], alignment=0.9)
    assert pf.score(more)["fit_score"] >= pf.score(base)["fit_score"]


def test_an_unestablished_alignment_renormalises_rather_than_scoring_zero():
    """The contract: "if you cannot establish the entity's strategic
    objectives, SAY SO, rank by downstream impact, and set
    ranking_basis=impact_fallback". Scoring the unknown as zero would leave
    the order unchanged and drag every score down by a fifth — a client
    looking worse for a producer's omission."""
    known_zero = pf.score(cand("P", [cell("P1C1.1.1")], alignment=0.0))
    unknown = pf.score(cand("P", [cell("P1C1.1.1")], alignment=None))
    assert unknown["alignment_basis"] == pf.ALIGNMENT_FALLBACK
    assert known_zero["alignment_basis"] == pf.ALIGNMENT_STATED
    assert unknown["fit_score"] > known_zero["fit_score"], \
        "an unknown alignment is being scored as a zero one"


def test_the_fallback_blend_is_the_audited_one():
    """When alignment is unknown the three remaining weights must be exactly
    engine v2's, not the scaled-down ones — otherwise the fallback silently
    re-tunes a calibration an audit produced."""
    row = pf.score(cand("P", [cell("P1C1.1.1")], alignment=None))
    w = {f["name"]: f["weight"] for f in row["factors"]}
    assert w["Addressable opportunity"] == 0.66
    assert w["Catalogue interconnect"] == 0.26
    assert w["Greenfield family"] == 0.08
    assert w["Strategic alignment"] == 0.0


# ── breakdown-equals-headline ──────────────────────────────────────────

def test_the_factors_reproduce_the_headline():
    """570 of 685 cards rendered two numbers from two code paths. Everything
    needed to reproduce the fit is on the row."""
    for c in (cand("A", [cell("P1C1.1.1"), cell("P1C1.1.2")], alignment=0.7),
              cand("B", [cell("P2C1.1.1", 3.5, "P2C1")], family_absent=True,
                   readiness="amber", alignment=None)):
        row = pf.score(c)
        rebuilt = 100.0 * sum(f["contribution"] for f in row["factors"]) \
            * row["readiness_multiplier"]
        assert abs(min(pf.FIT_CAP, rebuilt) - row["fit_score"]) <= 0.05, row


def test_the_stated_subtotal_matches_its_own_factors():
    row = pf.score(cand("A", [cell("P1C1.1.1")], alignment=0.5))
    assert abs(sum(f["contribution"] for f in row["factors"])
               - row["subtotal"]) <= 1e-9


# ── no client renders five identical cards ─────────────────────────────

def test_identical_platforms_are_still_separated_deterministically():
    """42 of 470 cards clamped to one value; four clients rendered five
    identical ones."""
    same = [cand(f"P{i}", [cell("P1C1.1.1", 1.0, "P1C1", ("critical",), 1.0)])
            for i in range(5)]
    ranks = [r["rank"] for r in pf.rank(same)]
    assert sorted(ranks) == [1, 2, 3, 4, 5], "two cards share a rank"


def test_the_order_is_stable_between_two_identical_runs():
    def order():
        return [r["platform"] for r in pf.rank([
            cand("B", [cell("P1C1.1.1")], alignment=0.5),
            cand("A", [cell("P1C1.1.1")], alignment=0.5),
            cand("C", [cell("P2C1.1.1", 3.0, "P2C1")], alignment=0.5)])]
    assert order() == order()


def test_a_tie_is_broken_by_evidence_before_alphabet():
    thin = cand("A thin", [cell("P1C1.1.1", 2.0, "P1C1", ("high",), 0.15)])
    solid = cand("Z solid", [cell("P1C1.1.1", 2.0, "P1C1", ("high",), 0.15)])
    solid.cells = [cell("P1C1.1.1", 2.0, "P1C1", ("high",), 0.15)]
    # same fit, different evidence density
    thin.cells[0].evidence_strength = 0.11
    order = [r["platform"] for r in pf.rank([thin, solid])]
    assert order[0] == "Z solid", \
        "the alphabet beat the evidence, so the tie-break is cosmetic"


# ── honesty about grounding ────────────────────────────────────────────

def test_insufficient_evidence_is_reachable():
    """470 of 470 cards were READY under v1 — the branch could not fire."""
    row = pf.score(cand("P", [cell(f"P1C1.1.{i}", 2.0, "P1C1", ("high",), 0.0)
                              for i in (1, 2, 3, 4)]), RUN_GAPS)
    assert row["state"] == pf.STATE_INSUFFICIENT


def test_the_evidence_state_is_judged_on_the_driving_cells():
    """A platform whose TOP contributors carry no evidence is unevidenced,
    however many well-evidenced small-gap cells it also touches — and an
    unevidenced cell counts as 0.0 here rather than as the neutral prior,
    which exists so it still contributes opportunity, not so it buys a clean
    bill of grounding."""
    driving_unevidenced = [cell(f"P1C1.1.{i}", 1.0, "P1C1", ("critical",), 0.0)
                           for i in range(1, 6)]
    padding = [cell(f"P1C1.2.{i}", 3.9, "P1C1", ("low",), 1.0)
               for i in range(1, 20)]
    row = pf.score(cand("P", driving_unevidenced + padding), RUN_GAPS)
    assert row["state"] == pf.STATE_INSUFFICIENT


def test_an_out_of_vertical_platform_cannot_render_hot():
    """"Out-of-vertical rank-1 is a defect: a carrier platform must not top a
    bank's list." Relevance CAPS the fit rather than blending into it, so gap
    surface cannot buy the way back."""
    c = cand("Carrier platform", [cell(f"P1C1.1.{i}", 1.0, "P1C1", ("critical",), 1.0)
                                  for i in range(1, 9)],
             family_absent=True, readiness="green", alignment=1.0, relevance=0.35)
    row = pf.score(c, RUN_GAPS)
    assert row["state"] == pf.STATE_OUT_OF_VERTICAL
    assert row["fit_score"] < 40.0


def test_a_well_evidenced_platform_is_ready():
    assert pf.score(cand("P"), RUN_GAPS)["state"] == pf.STATE_READY


# ── the arithmetic's own edges ─────────────────────────────────────────

def test_fit_never_exceeds_the_cap():
    row = pf.score(cand("P", [cell(f"P1C1.1.{i}", 1.0, "P1C1", ("critical",), 1.0)
                              for i in range(1, 20)],
                        family_absent=True, alignment=1.0))
    assert row["fit_score"] <= pf.FIT_CAP


def test_a_closed_cell_contributes_nothing():
    """A cell already at the target band is not an opportunity."""
    at_target = pf.score(cand("P", [cell("P1C1.1.1", pf.TARGET_BAND_SCORE)]))
    below = pf.score(cand("P", [cell("P1C1.1.1", 2.0)]))
    assert at_target["fit_score"] < below["fit_score"]


def test_a_cell_with_no_score_is_not_an_opportunity_either():
    """Invariant 9: derived values are computed or null, never a default that
    looks like data. A scoreless cell must not read as a maximal gap."""
    scoreless = pf.score(cand("P", [pf.Cell("P1C1.1.1", None, "P1C1")]))
    assert scoreless["fit_score"] == 0.0


def test_an_incumbent_covered_cell_is_halved_not_dropped():
    plain = pf.score(cand("P", [cell("P1C1.1.1")]))["fit_score"]
    covered = pf.score(cand("P", [cell("P1C1.1.1", incumbent=True)]))["fit_score"]
    assert 0 < covered < plain


def _inter(row):
    return next(f["value"] for f in row["factors"]
                if f["name"] == "Catalogue interconnect")


def test_interconnect_measures_the_gap_mass_the_core_would_lift():
    """NOT how tightly the platform's own cells cluster, which is what an
    earlier version measured: that rewarded a narrow platform for being narrow
    and told a reader nothing about compounding. It is the share of the run's
    OTHER gap cells sitting in a category or value-chain stage the core
    touches."""
    run = [cell(f"P1C1.9.{i}", 2.0, "P1C1") for i in range(1, 5)] + \
          [cell(f"P7C7.7.{i}", 2.0, "P7C7") for i in range(1, 5)]
    on_the_seam = pf.score(cand("P", [cell(f"P1C1.1.{i}", cat="P1C1")
                                      for i in (1, 2, 3)]), run)
    off_on_its_own = pf.score(cand("P", [cell(f"P5C5.1.{i}", cat="P5C5")
                                         for i in (1, 2, 3)]), run)
    assert _inter(on_the_seam) == 0.5, _inter(on_the_seam)
    assert _inter(off_on_its_own) == 0.0
    assert on_the_seam["fit_score"] > off_on_its_own["fit_score"]


def test_a_value_chain_stage_counts_as_adjacency_too():
    """The legacy engine's rule is "same category OR same value-chain stage",
    and the stage half was missing — so a platform whose lift runs along a
    member journey rather than a catalogue category scored no interconnect at
    all."""
    core = [pf.Cell(f"P1C1.1.{i}", 2.0, "P1C1", ("high",), 0.8,
                    vc_stages=("onboarding",)) for i in (1, 2, 3)]
    run = [pf.Cell(f"P8C8.8.{i}", 2.0, "P8C8", ("high",), 0.8,
                   vc_stages=("onboarding",)) for i in (1, 2)]
    assert _inter(pf.score(cand("P", core), run)) == 1.0


def test_interconnect_is_zero_without_run_context_rather_than_guessed():
    """An uplift nobody measured is not an uplift."""
    assert _inter(pf.score(cand("P"), None)) == 0.0


def test_a_deeper_gap_never_lowers_the_fit():
    shallow = pf.score(cand("P", [cell("P1C1.1.1", 3.5)]))["fit_score"]
    deep = pf.score(cand("P", [cell("P1C1.1.1", 1.2)]))["fit_score"]
    assert deep >= shallow


def test_a_critical_gap_outweighs_a_low_one_of_the_same_depth():
    low = pf.score(cand("P", [cell("P1C1.1.1", 2.0, sev=("low",))]))["fit_score"]
    crit = pf.score(cand("P", [cell("P1C1.1.1", 2.0, sev=("critical",))]))["fit_score"]
    assert crit > low


def test_the_weights_sum_to_one_so_the_fit_is_a_percentage():
    total = (pf.W_OPPORTUNITY + pf.W_INTERCONNECT + pf.W_ABSENT + pf.W_ALIGNMENT)
    assert abs(total - 1.0) < 1e-9


def test_the_audited_weights_keep_their_proportions_to_each_other():
    """Alignment took a share; the three v2 weights were NOT re-tuned by hand.
    Their ratios are the audit's, exactly."""
    assert abs(pf.W_OPPORTUNITY / pf.W_INTERCONNECT - 0.66 / 0.26) < 1e-9
    assert abs(pf.W_INTERCONNECT / pf.W_ABSENT - 0.26 / 0.08) < 1e-9


def test_every_row_carries_the_basis_that_explains_it():
    row = pf.rank([cand("P", [cell("P1C1.1.1")], alignment=0.5)])[0]
    assert "multiplier" in row["fit_basis"]
    assert str(row["fit_score"]) in row["fit_basis"]


# ── the prerequisite sequence, which engine v2 had and this dropped ────

def test_a_dependent_never_precedes_its_prerequisite():
    foundation = cand("Foundation", [cell("P1C1.1.1")], readiness="red",
                      alignment=0.9)
    workload = pf.Candidate("Workload", "B", [cell("P1C1.1.2")],
                            readiness="green", alignment=0.7,
                            depends_on=("Foundation",))
    order = [r["platform"] for r in pf.rank([foundation, workload])]
    assert order == ["Foundation", "Workload"], order


def test_the_card_that_moved_says_why():
    foundation = cand("Foundation", [cell("P1C1.1.1")], readiness="red",
                      alignment=0.9)
    workload = pf.Candidate("Workload", "B", [cell("P1C1.1.2")],
                            readiness="green", alignment=0.7,
                            depends_on=("Foundation",))
    held = next(r for r in pf.rank([foundation, workload])
                if r["platform"] == "Workload")
    assert "Foundation" in held["rank_basis"]
    assert "sequenced" in held["rank_basis"]


def test_a_prerequisite_naming_a_platform_not_on_this_page_is_ignored():
    """A dependency on something the page does not carry cannot be satisfied
    and must not hold a card back forever."""
    solo = pf.Candidate("Solo", "A", [cell("P1C1.1.1")], alignment=0.5,
                        depends_on=("Something else entirely",))
    assert pf.rank([solo])[0]["rank"] == 1


def test_a_dependency_cycle_discloses_instead_of_hanging():
    """A ranking that hangs is worse than one that says its chain is broken."""
    a = pf.Candidate("A", "a", [cell("P1C1.1.1")], alignment=0.5,
                     depends_on=("B",))
    b = pf.Candidate("B", "b", [cell("P1C1.1.2")], alignment=0.5,
                     depends_on=("A",))
    rows = pf.rank([a, b])
    assert len(rows) == 2 and [r["rank"] for r in rows] == [1, 2]
    assert any("could not be resolved" in (r.get("sequence_note") or "")
               for r in rows)


def test_sequencing_never_loses_or_duplicates_a_card():
    cards = [pf.Candidate(f"P{i}", "a", [cell(f"P1C1.1.{i}")], alignment=0.5,
                          depends_on=("P0",) if i else ())
             for i in range(5)]
    rows = pf.rank(cards)
    assert sorted(r["platform"] for r in rows) == [f"P{i}" for i in range(5)]
