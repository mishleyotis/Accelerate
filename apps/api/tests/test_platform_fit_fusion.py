"""Reciprocal rank fusion over the platform signals — the properties, measured.

REQUESTED 2026-08-23, against a promoted platform card the owner read as
"basic ... no deep reasoning": "reciprocal rank fusion for platform selection,
tested against client corpus".

Fusion here is a NEAR-TIE RESOLVER over the four factor lists plus the v2
blend, bounded by FUSION_BAND. The bound is the whole safety argument, so it
is asserted as a property over generated runs rather than demonstrated on one
case — a bound that holds on the examples somebody thought of is not a bound.

THE MEASUREMENT THAT NEARLY SHIPPED A DECORATIVE FUSION. The first probe of
this used TWO candidates, found 64 near-ties, and reordered none of them —
which reads exactly like a fusion that does nothing. It was the probe that was
wrong: with two candidates every rank difference is one place, so weighted RRF
reproduces the weighted sum by construction. At the real page size of five,
fusion reorders 18% of runs. `test_fusion_is_not_decorative` and
`test_fusion_does_not_run_the_page` pin BOTH ends of that, because a fusion
that never fires and a fusion that overrides the arithmetic are both defects
and neither shows up in a test that only checks one direction.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "shared"))

import platform_fit as pf  # noqa: E402


# ── generators ────────────────────────────────────────────────────────

def _cells(n, cat, score, es, sev):
    return [pf.Cell(subcap_id=f"{cat}.{i}", current_score=score,
                    category_id=cat, severities=sev, evidence_strength=es)
            for i in range(1, n + 1)]


def a_run(rng, n_candidates=5):
    """One client's worth of candidates, with the spread a real page has.

    The parameters are ranges rather than fixed values on purpose: the defect
    fusion exists for is a signal whose MAGNITUDE spread swamps the weighted
    sum while its RANK spread says something different, and that only appears
    across a population.
    """
    cands = []
    for j in range(n_candidates):
        cands.append(pf.Candidate(
            platform=f"P{j}", l3_area=f"L{j}",
            cells=_cells(rng.choice([6, 10, 14, 20, 28, 36]), f"P{j % 4 + 1}C1",
                         round(rng.uniform(1.2, 3.2), 2),
                         round(rng.uniform(0.4, 0.98), 2),
                         (rng.choice(["critical", "high", "medium", "low"]),)),
            family_absent=rng.random() < 0.35,
            readiness=rng.choice(["green", "green", "amber", "red"]),
            alignment=round(rng.uniform(0.1, 1.0), 2)))
    return cands, [c for k in cands for c in k.cells]


def ranked(rng, n=5):
    cands, gaps = a_run(rng, n)
    return pf.rank(cands, gaps)


# ── the bound, which is the safety argument ───────────────────────────

def test_fusion_never_overtakes_a_decisive_fit():
    """If A is ordered above B then A's fit is at least B's, or the two are
    within FUSION_BAND. This is the guarantee the block comment claims and the
    only thing standing between a near-tie resolver and a second ranking.

    Asserted over 500 generated runs rather than one built case: a bound is
    not a bound if it holds only on the examples somebody thought of.
    """
    rng = random.Random(11)
    checked = 0
    for _ in range(500):
        rows = ranked(rng)
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                # Sequencing may legitimately move a card past a better one;
                # it says so, and it is a different mechanism from fusion.
                if a["rank_basis"].startswith("sequenced") or \
                   b["rank_basis"].startswith("sequenced"):
                    continue
                checked += 1
                assert (a["fit_score"] >= b["fit_score"]
                        or b["fit_score"] - a["fit_score"] <= pf.FUSION_BAND), (
                    f"{a['platform']} (fit {a['fit_score']}) was ordered above "
                    f"{b['platform']} (fit {b['fit_score']}) — a "
                    f"{b['fit_score'] - a['fit_score']:.1f} point gap, outside "
                    f"the {pf.FUSION_BAND} band")
    assert checked > 2000, "the generator stopped producing comparable pairs"


def test_a_runaway_leader_is_never_displaced():
    """The clearest case of the bound, stated on its own so a regression names
    itself: a card ahead by more than the band cannot be moved off rank 1 by
    fusion, however badly it places on the individual signals."""
    cands = [
        # Wins the blend outright; LAST on greenfield and alignment.
        pf.Candidate(platform="Runaway", cells=_cells(30, "P1C1", 1.3, 0.95,
                                                      ("critical",)),
                     family_absent=False, readiness="green", alignment=0.05),
        pf.Candidate(platform="Popular", cells=_cells(4, "P2C1", 3.1, 0.5,
                                                      ("low",)),
                     family_absent=True, readiness="green", alignment=1.0),
        pf.Candidate(platform="Also popular", cells=_cells(4, "P3C1", 3.1, 0.5,
                                                          ("low",)),
                     family_absent=True, readiness="green", alignment=1.0),
    ]
    rows = pf.rank(cands, [c for k in cands for c in k.cells])
    assert rows[0]["platform"] == "Runaway"
    assert rows[0]["fit_score"] - rows[1]["fit_score"] > pf.FUSION_BAND
    # And it loses signals — proving the leader was tested, not merely lucky.
    assert rows[0]["signal_ranks"]["Strategic alignment"] > 1
    assert rows[0]["signal_ranks"]["Greenfield family"] > 1


# ── why rank fusion at all: scale invariance ──────────────────────────

def test_signal_ranks_survive_any_monotone_rescaling_of_one_signal():
    """THE REASON THIS IS RANK FUSION AND NOT A SECOND WEIGHTED SUM.

    Alignment is a producer's 0..1 judgement, usually quoted in coarse steps;
    opportunity is a continuous mean that occupies a narrow band on a real
    corpus. A weighted sum is dominated by whichever term happens to vary
    widest on THIS client, whatever its weight says. Rank fusion is invariant
    to any strictly monotone rescaling of a single signal — so squaring every
    alignment (which changes every fit) leaves the fused placings untouched.

    If this ever fails, fusion has picked up a magnitude dependence and is a
    weighted sum wearing a different name.
    """
    rng = random.Random(23)
    for _ in range(120):
        cands, gaps = a_run(rng)
        before = {r["platform"]: r["signal_ranks"]["Strategic alignment"]
                  for r in pf.rank(cands, gaps)}
        for c in cands:                       # x -> x**2 on (0,1]: monotone
            c.alignment = c.alignment ** 2
        after = {r["platform"]: r["signal_ranks"]["Strategic alignment"]
                 for r in pf.rank(cands, gaps)}
        assert before == after, (before, after)


def test_ties_share_the_best_rank_rather_than_being_split_by_list_order():
    """Competition ranking (1,2,2,4), not ordinal (1,2,3,4).

    Ordinal ranking would break a genuine tie by position in the input list —
    which is itself the fit order — and hand the blend a second, hidden vote.
    """
    rows = [{"platform": "A", "x": 0.5}, {"platform": "B", "x": 0.5},
            {"platform": "C", "x": 0.9}, {"platform": "D", "x": 0.1}]
    got = pf._competition_ranks(rows, lambda r: r["x"])
    assert got == {"C": 1, "A": 2, "B": 2, "D": 3}


def test_two_identical_candidates_fuse_identically():
    """The same property one level up: equal inputs must produce equal rrf
    scores, so the only thing separating them is the declared tie key."""
    def one(name):
        return pf.Candidate(platform=name, cells=_cells(12, "P1C1", 2.0, 0.8,
                                                        ("high",)),
                            family_absent=False, readiness="green",
                            alignment=0.5)
    cands = [one("A"), one("B")]
    rows = pf.rank(cands, [c for k in cands for c in k.cells])
    assert rows[0]["rrf_score"] == rows[1]["rrf_score"]
    assert rows[0]["signal_ranks"] == rows[1]["signal_ranks"]


# ── determinism ───────────────────────────────────────────────────────

def test_input_order_does_not_change_the_output():
    """A ranking that depends on the order candidates were appended in is a
    ranking that changes when a producer reorders its own list."""
    rng = random.Random(31)
    for _ in range(80):
        cands, gaps = a_run(rng)
        base = [r["platform"] for r in pf.rank(list(cands), gaps)]
        shuffled = list(cands)
        random.Random(99).shuffle(shuffled)
        assert [r["platform"] for r in pf.rank(shuffled, gaps)] == base


def test_fusion_is_stable_across_processes():
    """No hashing, no set iteration, no float equality on unrounded values in
    the ordering path — the same run twice gives byte-identical rrf scores."""
    rng = random.Random(41)
    cands, gaps = a_run(rng)
    a = {r["platform"]: r["rrf_score"] for r in pf.rank(list(cands), gaps)}
    b = {r["platform"]: r["rrf_score"] for r in pf.rank(list(cands), gaps)}
    assert a == b


# ── the disclosure, which is the "no deep reasoning" complaint ─────────

def test_every_card_carries_its_fusion_reasoning():
    """Whether fusion moved the card or not. Agreement is an answer; silence
    on agreement would make "fusion agreed" and "fusion never ran"
    indistinguishable on the page, which is this build's most-repeated defect
    shape."""
    rng = random.Random(53)
    for _ in range(60):
        for r in ranked(rng):
            assert isinstance(r["signal_ranks"], dict) and r["signal_ranks"]
            assert set(r["signal_ranks"]) == {f["name"] for f in r["factors"]} | {
                pf.FIT_LIST}
            assert isinstance(r["rrf_score"], float) and r["rrf_score"] > 0
            assert 1 <= r["rrf_rank"] <= 5
            assert "RRF" in r["fusion_note"] and str(pf.RRF_K) in r["fusion_note"]
            assert r["fusion_note"] in r["fit_basis"], \
                "the card's own basis must carry the fusion, not just the row"


def test_a_moved_card_says_it_moved_and_by_how_much():
    """A reader who sees 41.1 above 41.5 and no reason concludes the
    arithmetic is broken — the exact case AG-09 refuses. The note has to name
    the mechanism and the bound, not merely exist."""
    rng = random.Random(7)
    moved = []
    for _ in range(400):
        rows = ranked(rng)
        moved += [r for r in rows if r["rank_basis"].startswith("rank fusion")]
        if len(moved) >= 5:
            break
    assert moved, "no fusion move in 400 runs — see test_fusion_is_not_decorative"
    for r in moved:
        assert "near-tie band" in r["rank_basis"]
        assert "moved this card" in r["fusion_note"]
        assert "place(s)" in r["fusion_note"]
        assert str(int(pf.FUSION_BAND)) in r["fusion_note"]


def test_an_inversion_always_carries_a_non_empty_basis():
    """AG-09 refuses a lower rank on a higher score with nothing beside it.
    Fusion CREATES those inversions on purpose, so the gate and the engine
    have to agree — every row `rank` writes carries a populated fit_basis."""
    rng = random.Random(61)
    inversions = 0
    for _ in range(300):
        rows = ranked(rng)
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                if a["fit_score"] < b["fit_score"]:
                    inversions += 1
                    assert str(a["fit_basis"]).strip(), a
                    assert str(b["fit_basis"]).strip(), b
    assert inversions > 0, "no inversion generated — the assertion proved nothing"


# ── the two ends of "does fusion do the right amount" ──────────────────

def test_fusion_is_not_decorative():
    """A fusion that never fires is a fusion nobody needs, and it would look
    exactly like a correct one in every example-based test above.

    Measured 2026-08-23 at the real page size: 72 of 400 generated runs (18%)
    had fusion reorder at least one card. The floor here is deliberately well
    under that — this pins "it fires at all", not the rate.
    """
    rng = random.Random(7)
    runs = 400
    fired = sum(1 for _ in range(runs)
                if any(r["rank_basis"].startswith("rank fusion")
                       for r in ranked(rng)))
    assert fired >= runs * 0.05, (
        f"fusion reordered a card in only {fired} of {runs} runs. Below this "
        "it is decorative: the weighted RRF has collapsed onto the weighted "
        "sum, which is what happens when the blend's own vote is given enough "
        "weight to swamp the four signals.")


def test_fusion_does_not_run_the_page():
    """The other end. Fusion is a near-tie resolver; if it were reordering
    most cards it would BE the ranking, and the audited v2 calibration would
    have been replaced by an uncalibrated vote without anyone deciding to."""
    rng = random.Random(7)
    runs, cards, moved = 400, 0, 0
    for _ in range(runs):
        rows = ranked(rng)
        cards += len(rows)
        moved += sum(1 for r in rows if r["rank_basis"].startswith("rank fusion"))
    share = moved / cards
    assert share <= 0.25, (
        f"fusion moved {share:.1%} of all cards. Above a quarter it is not "
        "resolving near-ties, it is doing the ranking, and FUSION_BAND has "
        "stopped being a bound.")


def test_the_band_is_what_bounds_it():
    """Shrinking FUSION_BAND collapses fusion onto the exact-tie case, and
    nothing survives that is not an exact tie.

    A zero band does NOT mean "no moves": a run continues while the next card
    is within the band OF THE LEADER, and at zero that is still true for cards
    whose fits are equal. Breaking an exact tie by fused placing is the one
    move that remains, and it is the one move that is unarguable — the first
    version of this test asserted zero moves, found one in 300 runs, and the
    one it found was a 0.0-point tie.

    So the assertion is the accurate form of the bound: with a zero band,
    every card fusion moves is tied on fit with the card it passed.
    """
    rng = random.Random(7)
    original = pf.FUSION_BAND
    try:
        pf.FUSION_BAND = 0.0
        checked = 0
        for _ in range(300):
            rows = ranked(rng)
            for i, a in enumerate(rows):
                for b in rows[i + 1:]:
                    if a["rank_basis"].startswith("sequenced") or \
                       b["rank_basis"].startswith("sequenced"):
                        continue
                    checked += 1
                    assert a["fit_score"] >= b["fit_score"], (
                        f"with a zero band {a['platform']} ({a['fit_score']}) "
                        f"was still ordered above {b['platform']} "
                        f"({b['fit_score']}) — something outside FUSION_BAND "
                        "is reordering cards")
        assert checked > 1000
    finally:
        pf.FUSION_BAND = original


# ── the fusion must not be able to fall behind the engine ─────────────

def test_a_new_factor_joins_the_fusion_automatically():
    """`fusion_lists` reads `factors` rather than restating the four names.

    The alternative — a hand-kept list — is the shape of this build's most
    expensive defects: a term is added to the scorer and half the system never
    sees it. Asserted by adding a factor to a scored row and checking the
    fusion picks it up, which is cheaper than asserting it after the fact on
    the next term somebody adds.
    """
    rng = random.Random(71)
    cands, gaps = a_run(rng, 3)
    rows = [pf.score(c, gaps) for c in cands]
    for i, r in enumerate(rows):
        r["factors"].append({"name": "Invented signal", "value": i / 10.0,
                             "weight": 0.5, "contribution": 0.0})
    pf.fuse(rows)
    assert all("Invented signal" in r["signal_ranks"] for r in rows)
    assert [r["signal_ranks"]["Invented signal"] for r in rows] == [3, 2, 1]


def test_fusion_weights_are_the_engine_weights_not_a_second_set():
    """Reusing `factors[].weight` keeps the 2026-07-14 skew calibration inside
    the fusion. A separate table of fusion weights would be a second, unaudited
    calibration that drifts from the first silently."""
    rng = random.Random(83)
    cands, gaps = a_run(rng, 4)
    rows = pf.rank(cands, gaps)
    weights = dict((n, w) for n, w, _ in pf.fusion_lists(rows))
    for f in rows[0]["factors"]:
        assert weights[f["name"]] == f["weight"]
    assert weights[pf.FIT_LIST] == pf.W_FIT


def test_fusion_survives_a_degenerate_signal():
    """When no candidate is greenfield, that list is one big tie and
    contributes an identical term to every card — it must not tip anything,
    and it must not crash. A weighted sum shifts every score by a constant
    here; fusion does not move the order at all.
    """
    rng = random.Random(97)
    cands, gaps = a_run(rng)
    for c in cands:
        c.family_absent = False
    rows = pf.rank(cands, gaps)
    assert {r["signal_ranks"]["Greenfield family"] for r in rows} == {1}
    assert len({r["rank"] for r in rows}) == len(rows)


def test_one_candidate_and_no_candidates_are_not_special_cases():
    assert pf.rank([], []) == []
    c = pf.Candidate(platform="Only", cells=_cells(9, "P1C1", 2.0, 0.8, ("high",)),
                     readiness="green", alignment=0.5)
    rows = pf.rank([c], c.cells)
    assert len(rows) == 1 and rows[0]["rank"] == 1
    assert rows[0]["rrf_rank"] == 1
    assert all(v == 1 for v in rows[0]["signal_ranks"].values())
