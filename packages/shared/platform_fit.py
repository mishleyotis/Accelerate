"""Platform fit, computed once, in one place, for every client.

REPORTED 2026-08-19: "Platform fit scores calculation is very different from
Baxter's." It was. There were FOUR definitions of one number:

  · the Surface Spec:  fit = 100 x (0.66*opportunity + 0.34*readiness)
  · `platform_fit.py` engine v2, the engine the Spec names by filename:
      fit = 100 x (w_opp*opportunity + w_int*interconnect + w_abs*absent)
                x readiness_multiplier
  · Baxter, promoted: 76.5, and its own `fit_basis` says it was read from the
    OPPORTUNITY tile's composite -- a different number wearing this name
  · Logix, promoted: null on all five, with no rank and no basis

The engine the Spec names exists only in `apps/dma-insights/`, the legacy
snapshot the charter marks reference-only. So the new build had no fit engine
at all, and each producer answered the gap its own way. That is the defect;
the payloads are downstream of it.

## The Spec's formula is a mis-transcription, not a competing design

Engine v2's other two weights are 0.26 + 0.08 = **0.34**, and its opportunity
weight is **0.66**. The Spec kept the split and put the wrong name on the
second term. So there is no conflict to adjudicate between two designs: there
is one design, and one copy of it that lost the middle terms.

## What this computes

    opportunity   per addressable cell: gap x severity x evidence strength
    interconnect  catalogue adjacency -- closing a cell lifts sibling gap
                  cells in the same category
    absent        confirmed-ABSENT platform family: greenfield ground
    alignment     the entity's OWN stated objectives, 0..1

    fit = 100 x (w_opp*opp + w_int*int + w_abs*abs + w_align*align)
              x readiness_multiplier                       , capped at 99.0

READINESS IS A MULTIPLIER, NOT AN ADDEND, and that is the whole point of v2.
A 2026-06 audit measured 95 of 470 cards scoring "red but hot" -- fit at or
above 80 while every readiness prerequisite was failing. Red multiplies by
0.62, so the highest reachable fit with red readiness is 62: hot-and-red is
arithmetically impossible rather than merely discouraged. Owner decision,
2026-08-19, choosing this shape over the Spec's additive one.

## Alignment, and why the audited weights were not re-tuned

The owner asked that the top platform match the client's need and align with
their strategic objectives. The contract already carries that idea: a
finding's `strategic_alignment` is "15-30 words PLUS a 0-1 score, quoting the
entity's OWN stated objective -- the RANKING KEY". Platforms now use the same
key and the same 0..1 scale.

The three v2 weights were calibrated against a measured skew (a flat 0.15
absence bonus was top-ranking whatever family a client happened to lack, on 20
of 28 sampled clients). Re-tuning them by hand here would discard that. So
alignment takes a share and the audited three are scaled UNIFORMLY into what
is left -- their proportions to each other are exactly preserved.

Where the producer could not establish the objectives, the contract is
explicit: "SAY SO, rank by downstream impact, and set
ranking_basis=impact_fallback -- do not pretend to an alignment you did not
establish." So an unknown alignment RENORMALISES back to the three-term
blend. It is not scored as zero: zero would leave the ranking unchanged and
drag every score down by a fifth, making a client look worse for a producer's
omission.

No model is called here and none could be: every function is pure and depends
only on its inputs.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ── calibration, mirrored from engine v2 ──────────────────────────────
#
# Anything named `_V2_` is the audited value and is not re-tuned here. The
# 2026-07-14 skew audit set the absent term low on purpose: a flat 0.15
# absence bonus had been top-ranking whatever platform family a client
# happened to lack, on 20 of 28 sampled clients.
_V2_W_OPPORTUNITY = 0.66
_V2_W_INTERCONNECT = 0.26
_V2_W_ABSENT = 0.08

# The share given to strategic alignment. The only weight this build chose,
# and it is stated rather than folded into the others.
W_ALIGNMENT = 0.20

_V2_SUM = _V2_W_OPPORTUNITY + _V2_W_INTERCONNECT + _V2_W_ABSENT
_SCALE = (1.0 - W_ALIGNMENT) / _V2_SUM

W_OPPORTUNITY = _V2_W_OPPORTUNITY * _SCALE
W_INTERCONNECT = _V2_W_INTERCONNECT * _SCALE
W_ABSENT = _V2_W_ABSENT * _SCALE

# A platform addressing this many cells earns the full breadth bonus, and the
# opportunity mean is taken over its best this-many cells rather than over all
# of them. Both halves are one measured fix: the catalogue makes set sizes
# differ fivefold between platforms, and an all-set mean punishes the broadest
# one with hundreds of small-gap dilutors — measured on the corpus as
# Salesforce ranking LAST for 93 of 94 clients purely by set size.
BREADTH_FULL = 40
BREADTH_BONUS = 0.20

# Below this many addressable cells the contract says discard rather than
# rank: "drop it when it addresses fewer than 3 of this run's cells".
MIN_CELLS = 3

# Vertical relevance CAPS the fit. 0.35 gives a ceiling near 35, so a
# lending-origination platform cannot render hot for an entity with no lending
# operation however large its gap surface. "Out-of-vertical rank-1 is a
# defect" — the contract, and a stated defect class this engine had no term
# for until 2026-08-19.
RELEVANCE_DISCARD = 0.5

# Readiness: red caps the reachable fit at 100 x 1.0 x 0.62 = 62, below the
# hot threshold. Amber is a soft penalty.
READINESS_MULTIPLIER = {"green": 1.00, "amber": 0.85, "red": 0.62}
# Unknown readiness is AMBER, the honest middle. Green would reward a card
# that established nothing; red would punish silence into a lie.
READINESS_DEFAULT = "amber"
HOT_THRESHOLD = 80.0

# Severity -> priority MULTIPLIER, centred on 1.0 so an unlinked cell scores
# its raw opportunity rather than being penalised for having no issue.
SEVERITY_WEIGHTS = {"critical": 1.6, "high": 1.3, "medium": 1.0,
                    "low": 0.85, "opportunity": 1.0}

# Target band M4 (4.0); the runway from the M1 floor is 3.0.
TARGET_BAND_SCORE = 4.0
GAP_DENOM = 3.0

# A gapped cell an installed third-party incumbent already covers is halved,
# not zeroed: the capability can still be improved or integrated, but it is
# not net-new ground.
INCUMBENT_COVERAGE_DISCOUNT = 0.5

# Evidence: a score with no linked evidence came from SOME corpus signal, so
# it is discounted rather than zeroed; strength scales within a band rather
# than multiplying the gap away.
NEUTRAL_EVIDENCE_STRENGTH = 0.55
ES_DAMP_FLOOR = 0.6
EVIDENCE_FLOOR = 0.10

FIT_CAP = 99.0

STATE_READY = "READY"
STATE_INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
STATE_TOO_NARROW = "TOO_NARROW"
STATE_OUT_OF_VERTICAL = "OUT_OF_VERTICAL"

# How many driving cells the evidence state is judged on, and how many are
# returned for traceability.
TOP_N = 5

ALIGNMENT_STATED = "stated_objective"
ALIGNMENT_FALLBACK = "impact_fallback"

# ── reciprocal rank fusion ────────────────────────────────────────────
#
# REQUESTED 2026-08-23: "reciprocal rank fusion for platform selection,
# tested against client corpus", against a promoted platform card the owner
# read as "basic ... no deep reasoning".
#
# WHAT RRF FIXES HERE, and what it does not. The four factors above are
# incommensurate in SPREAD even though they share a 0..1 scale: greenfield is
# effectively binary, alignment is a producer's 0..1 judgement usually quoted
# in coarse steps, opportunity is a continuous mean that on a real corpus
# occupies a narrow band. A weighted sum is dominated by whichever term
# happens to vary widest on THIS client, whatever its weight says — so the
# ordering is stable in the arithmetic and unstable in the data. Rank fusion
# is invariant to any monotone rescaling of any single signal, which is
# precisely that failure mode.
#
# WHAT RRF MUST NOT DO here is replace the blend. The three v2 weights are a
# calibration against a measured skew (a flat absence bonus top-ranking
# whatever family a client lacked, on 20 of 28 sampled clients); pure RRF
# discards it, because rank fusion cannot express "this term matters a
# twelfth as much as that one" — it only knows who came first. Swapping a
# calibrated blend for an uncalibrated vote would be the same mistake as
# re-tuning the weights by hand, in the other direction.
#
# So fusion is a NEAR-TIE RESOLVER, and its scope is stated arithmetically
# rather than asserted:
#
#   · every candidate is ranked on each signal, INCLUDING the v2 blend, which
#     votes as a list of its own and carries the largest weight;
#   · the fused order may reorder two cards only when their fits differ by at
#     most FUSION_BAND. Beyond the band, fit wins outright and fusion is
#     recorded as consulted-and-overruled;
#   · every card carries `signal_ranks`, `rrf_score` and a `fusion_note`,
#     whether fusion moved it or not — a reader who cannot see why one card
#     beat another is the "no deep reasoning" complaint, and agreement is as
#     much of an answer as disagreement.
#
# GUARANTEE, and it is tested: if A is ordered above B, then either A's fit is
# at least B's, or their fits differ by no more than FUSION_BAND. A card can
# never overtake one that beats it decisively.
#
# K=60 is Cormack, Clarke & Buettcher's constant (SIGIR 2009), unchanged. It
# damps the top of each list so that rank 1 versus rank 2 is worth more than
# rank 9 versus rank 10 without letting any single first place decide the
# fusion alone.
RRF_K = 60

# In fit points, on the 0..99 scale the cards render. 8.0 is a little under a
# tenth of the usable range: wide enough to cover the cluster a client's
# middle cards actually land in, narrow enough that the top card cannot be
# displaced by a card the arithmetic separates clearly.
FUSION_BAND = 8.0

#: The lists fused, and the vote each carries. The four factor weights are the
#: engine's own — reusing them keeps the calibration inside the fusion instead
#: of inventing a second set of numbers nobody audited. The blend votes at
#: W_FIT because it already contains all four; without it, fusion would treat
#: a card that came second on everything as equal to one that came first on
#: the term that matters most.
W_FIT = 1.0
FIT_LIST = "Fit (engine v2 blend)"


@dataclass
class Cell:
    """One addressable capability cell, as this run serves it."""
    subcap_id: str
    current_score: float | None
    category_id: str | None = None
    severities: tuple = ()
    evidence_strength: float | None = None      # 0..1, None -> neutral prior
    incumbent_covers: bool = False
    peer_median: float | None = None
    # Value-chain stages this cell sits in. Adjacency is "same category OR
    # same stage"; the stage half was in the legacy engine and missing here,
    # so a platform whose lift runs along a journey rather than a category
    # scored no interconnect at all.
    vc_stages: tuple = ()


@dataclass
class Candidate:
    """One platform under consideration for this entity."""
    platform: str
    l3_area: str | None = None
    cells: list = field(default_factory=list)   # list[Cell]
    family_absent: bool = False                 # confirmed ABSENT in the register
    readiness: str = "green"                    # green | amber | red
    alignment: float | None = None              # 0..1, the entity's own objective
    alignment_quote: str | None = None
    # Platforms this one needs FIRST. Engine v2 computed a prerequisite DAG
    # beside the fit and this build dropped it; the omission was caught by
    # scoring a real client, where a workload the institution places ON the
    # new foundation outranked the foundation itself because the foundation
    # was not ready yet. Ranking the visible next step above the thing it
    # depends on is the exact move that client's own answer warns against.
    depends_on: tuple = ()
    # 0..1, how relevant this platform is to THIS sub-vertical. It CAPS the
    # fit rather than being blended, so an out-of-vertical family cannot rank
    # first however large its gap surface.
    relevance: float = 1.0


def _clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def gap_of(cell: Cell) -> float:
    """0..1 distance to the target band. A cell with no score contributes
    nothing rather than a default: invariant 9, derived values are computed
    or null, never a sentinel that looks like data."""
    if cell.current_score is None:
        return 0.0
    return _clamp((TARGET_BAND_SCORE - float(cell.current_score)) / GAP_DENOM)


def severity_weight(cell: Cell) -> float:
    """The heaviest severity linked to this cell. A cell an issue calls
    critical is worth more to close than one nothing is linked to."""
    if not cell.severities:
        return SEVERITY_WEIGHTS["medium"]
    return max(SEVERITY_WEIGHTS.get(str(s).lower(), 1.0) for s in cell.severities)


def evidence_strength_of(cell: Cell) -> float:
    es = NEUTRAL_EVIDENCE_STRENGTH if cell.evidence_strength is None \
        else _clamp(float(cell.evidence_strength))
    # Dampened into [floor, 1]: a real gap with thin public evidence is still
    # a gap, just less bankable.
    return ES_DAMP_FLOOR + (1.0 - ES_DAMP_FLOOR) * es


def cell_opportunity(cell: Cell) -> float:
    """One cell's opportunity, 0..1.

    `gap x severity x evidence strength`, with severity CENTRED ON 1.0 so an
    unlinked cell scores its raw opportunity — the legacy engine's own stated
    intent, which an earlier version of this file broke by dividing through by
    the heaviest severity. That capped every all-medium platform at 0.625 of
    the term, and most cells carry no linked issue, so it was a systematic
    depression driven by missing linkage rather than by real severity.
    """
    gap = gap_of(cell)
    if gap <= 0.0:
        return 0.0
    # THE ORDER MATTERS. Severity may lift a cell to full opportunity, and the
    # clamp lands THERE — then evidence dampens what survives. Clamping after
    # the damping instead lets a thinly-evidenced critical gap ride its
    # saturated severity: gap x severity 1.6 with a 0.6 evidence damp scores
    # 0.96 that way and 0.60 this way, so the thin one would have out-scored a
    # fully-evidenced medium gap. Evidence discounts a claim; it never gets to
    # be the reason a claim is large.
    base = min(1.0, gap * severity_weight(cell))
    v = base * evidence_strength_of(cell)
    if cell.incumbent_covers:
        v *= INCUMBENT_COVERAGE_DISCOUNT
    return _clamp(v)


def _ranked_cells(cand: Candidate) -> list:
    return sorted(cand.cells, key=lambda c: (-cell_opportunity(c), c.subcap_id))


def core_of(cand: Candidate) -> list:
    """The cells actually driving the score: the best BREADTH_FULL of them."""
    return _ranked_cells(cand)[:BREADTH_FULL]


def opportunity_of(cand: Candidate) -> float:
    """Mean over the platform's BEST cells, lifted by a breadth bonus.

    Not the mean over all of them. The catalogue makes set sizes differ
    fivefold between platforms, and an all-set mean punishes the broadest with
    hundreds of small-gap dilutors — measured as Salesforce ranking last for
    93 of 94 clients purely by set size. Sets at or under the cap keep their
    exact mean, so this changes nothing for a narrow platform.
    """
    core = core_of(cand)
    if not core:
        return 0.0
    mean_opp = sum(cell_opportunity(c) for c in core) / len(core)
    breadth = min(1.0, len(cand.cells) / BREADTH_FULL)
    return _clamp(mean_opp * (1.0 + BREADTH_BONUS * breadth))


def interconnect_of(cand: Candidate, all_gap_cells=None) -> float:
    """The gap mass this platform's core would LIFT without addressing.

    For every category or value-chain stage the core touches, count the run's
    other gap cells in that category or stage which the platform does not
    itself address — the dependents that closing the core lifts. Normalised
    per involved category so a platform tagged against two hundred cells
    cannot saturate on volume alone.

    An earlier version measured how tightly the platform's OWN cells
    clustered, which is a different quantity entirely: it rewarded a narrow
    platform for being narrow and told a reader nothing about compounding.

    With no run context the term is 0.0 rather than a guess — an uplift
    nobody measured is not an uplift.
    """
    core = core_of(cand)
    if not core or not all_gap_cells:
        return 0.0
    addr = {c.subcap_id for c in cand.cells}
    cats = {c.category_id for c in core if c.category_id}
    stages = {st for c in core for st in (c.vc_stages or ())}
    if not cats and not stages:
        return 0.0
    pool = dependents = 0
    for g in all_gap_cells:
        if g.subcap_id in addr or gap_of(g) <= 0:
            continue
        pool += 1
        if (g.category_id in cats) or (set(g.vc_stages or ()) & stages):
            dependents += 1
    if not pool:
        return 0.0
    # A SHARE of the run's remaining gap mass, which is normalised by
    # construction: a platform tagged against two hundred cells cannot buy
    # the term by volume, because volume shrinks the pool it is measured
    # against as fast as it grows the dependents.
    return _clamp(dependents / pool)


def absent_of(cand: Candidate) -> float:
    """Greenfield ground: the register confirms this family absent."""
    return 1.0 if cand.family_absent else 0.0


def readiness_multiplier(cand: Candidate) -> float:
    return READINESS_MULTIPLIER.get(str(cand.readiness).lower(),
                                    READINESS_MULTIPLIER[READINESS_DEFAULT])


def mean_evidence_strength(cand: Candidate) -> float:
    """Judged on the cells DRIVING the score, not on every tagged cell.

    A platform whose top contributors carry no linked evidence is honestly
    INSUFFICIENT_EVIDENCE however many cells it nominally addresses — and an
    unevidenced cell counts as 0.0 here, not as the neutral prior. The prior
    exists so a scored-but-unevidenced cell still contributes opportunity; it
    must not also buy the card a clean bill of grounding.
    """
    top = core_of(cand)[:TOP_N]
    if not top:
        return 0.0
    return sum(0.0 if c.evidence_strength is None else _clamp(float(c.evidence_strength))
               for c in top) / len(top)


def state_for(cand: Candidate) -> str:
    """Why a card cannot be ranked as it stands, or READY.

    The v1 engine made INSUFFICIENT_EVIDENCE unreachable — 470 of 470 cards
    READY — so each branch here is one the corpus can actually reach.
    """
    if float(cand.relevance) < RELEVANCE_DISCARD:
        return STATE_OUT_OF_VERTICAL
    if len(cand.cells) < MIN_CELLS:
        return STATE_TOO_NARROW
    if mean_evidence_strength(cand) < EVIDENCE_FLOOR:
        return STATE_INSUFFICIENT
    return STATE_READY


def top_contributors(cand: Candidate) -> list:
    """The cells the score rests on, with their own numbers. The traceability
    mandate: a breakdown a reader cannot walk back to named cells explains
    nothing."""
    return [{"subcap_id": c.subcap_id,
             "pillar": c.subcap_id[:2],
             "category_id": c.category_id,
             "score": None if c.current_score is None else round(float(c.current_score), 2),
             "peer_median": None if c.peer_median is None else round(float(c.peer_median), 2),
             "gap": round(gap_of(c), 3),
             "severity_weight": severity_weight(c),
             "evidence_strength": (None if c.evidence_strength is None
                                   else round(float(c.evidence_strength), 3)),
             "contribution": round(cell_opportunity(c), 4)}
            for c in core_of(cand)[:TOP_N]]


def score(cand: Candidate, all_gap_cells=None) -> dict:
    """The fit, its factors, its state and the cells it rests on.

    `factors` sum to the pre-multiplier subtotal and everything needed to
    reproduce the headline is on the row — the contract's
    breakdown-equals-headline rule, which 570 of 685 cards broke by rendering
    two numbers from two code paths.
    """
    opp = opportunity_of(cand)
    inter = interconnect_of(cand, all_gap_cells)
    absent = absent_of(cand)
    known_alignment = cand.alignment is not None
    align = _clamp(float(cand.alignment)) if known_alignment else 0.0

    if known_alignment:
        w_opp, w_int, w_abs, w_align = (W_OPPORTUNITY, W_INTERCONNECT,
                                        W_ABSENT, W_ALIGNMENT)
        basis = ALIGNMENT_STATED
    else:
        # RENORMALISE, never score the unknown as zero: zero leaves the order
        # unchanged and drags every score down by a fifth, which makes a
        # client look worse for a producer's omission.
        w_opp, w_int, w_abs, w_align = (_V2_W_OPPORTUNITY, _V2_W_INTERCONNECT,
                                        _V2_W_ABSENT, 0.0)
        basis = ALIGNMENT_FALLBACK

    factors = [
        {"name": "Addressable opportunity", "value": round(opp, 4),
         "weight": round(w_opp, 4), "contribution": round(w_opp * opp, 4)},
        {"name": "Catalogue interconnect", "value": round(inter, 4),
         "weight": round(w_int, 4), "contribution": round(w_int * inter, 4)},
        {"name": "Greenfield family", "value": round(absent, 4),
         "weight": round(w_abs, 4), "contribution": round(w_abs * absent, 4)},
        {"name": "Strategic alignment", "value": round(align, 4),
         "weight": round(w_align, 4), "contribution": round(w_align * align, 4)},
    ]
    subtotal = sum(f["contribution"] for f in factors)
    mult = readiness_multiplier(cand)
    relevance = _clamp(float(cand.relevance))
    # Relevance CAPS rather than blends: an out-of-vertical family must not be
    # able to buy its way back with gap surface.
    fit = min(FIT_CAP, 100.0 * subtotal * mult * relevance)
    return {
        "platform": cand.platform,
        "l3_area": cand.l3_area,
        "fit_score": round(fit, 1),
        "state": state_for(cand),
        "factors": factors,
        "subtotal": round(subtotal, 4),
        "readiness": str(cand.readiness).lower(),
        "readiness_multiplier": mult,
        "relevance": round(relevance, 3),
        "alignment_basis": basis,
        "alignment_quote": cand.alignment_quote,
        "cells_addressed": len(cand.cells),
        "cells_driving": len(core_of(cand)),
        "evidence_strength_mean": round(mean_evidence_strength(cand), 4),
        "top_contributors": top_contributors(cand),
    }


def _factor(row: dict, name: str) -> float:
    return next((f["value"] for f in row["factors"] if f["name"] == name), 0.0)


def fusion_lists(rows) -> list:
    """The (name, weight, value-getter) triples fused, in a fixed order.

    Derived from `factors` rather than restated, so a factor added to `score`
    joins the fusion instead of silently sitting outside it — the shape of
    every "we added a term and half the system never saw it" defect in this
    build.
    """
    weights = {f["name"]: f["weight"] for f in (rows[0]["factors"] if rows else ())}
    out = [(name, weights.get(name, 0.0),
            (lambda n: (lambda r: _factor(r, n)))(name))
           for name in [f["name"] for f in (rows[0]["factors"] if rows else ())]]
    out.append((FIT_LIST, W_FIT, lambda r: r["fit_score"]))
    return out


def _competition_ranks(rows, getter) -> dict:
    """1-based ranks, highest value first, TIES SHARING THE BEST RANK.

    Standard competition ranking (1,2,2,4) rather than ordinal (1,2,3,4). Two
    candidates that are genuinely equal on a signal must contribute equally to
    the fusion; ordinal ranking would break the tie by list position, which is
    itself derived from fit, and quietly give the fit order a second vote.
    """
    vals = sorted({round(float(getter(r)), 6) for r in rows}, reverse=True)
    at = {v: i + 1 for i, v in enumerate(vals)}
    return {r["platform"]: at[round(float(getter(r)), 6)] for r in rows}


def fuse(rows, k: int = RRF_K) -> list:
    """Attach `signal_ranks` and `rrf_score` to every row. Pure; returns rows.

    rrf(P) = sum over lists of  weight / (k + rank of P on that list)
    """
    if not rows:
        return rows
    lists = fusion_lists(rows)
    ranks = {name: _competition_ranks(rows, get) for name, _, get in lists}
    for r in rows:
        r["signal_ranks"] = {name: ranks[name][r["platform"]]
                             for name, _, _ in lists}
        r["rrf_score"] = round(
            sum(w / (k + ranks[name][r["platform"]]) for name, w, _ in lists), 6)
    order = sorted(rows, key=lambda r: (-r["rrf_score"], r["platform"]))
    for i, r in enumerate(order, start=1):
        r["rrf_rank"] = i
    return rows


def _fusion_runs(rows) -> list:
    """Split a FIT-ORDERED list into runs that fusion may reorder within.

    A run continues while the next card is within FUSION_BAND of the run's
    LEADER — not of its predecessor. Chaining off the predecessor would let
    80, 74, 68 form one run and put the 68 above the 80, eight points at a
    time; measuring from the leader is what makes the guarantee in the block
    comment above provable rather than approximate.
    """
    runs, cur = [], []
    for r in rows:
        if cur and (cur[0]["fit_score"] - r["fit_score"]) > FUSION_BAND:
            runs.append(cur)
            cur = []
        cur.append(r)
    if cur:
        runs.append(cur)
    return runs


def _fused_order(rows) -> list:
    """Fit order, re-sorted by RRF inside each near-tie run."""
    out = []
    for run in _fusion_runs(rows):
        out.extend(sorted(run, key=lambda r: (-r["rrf_score"], _tie_key(r))))
    return out


def _tie_key(row: dict) -> tuple:
    """Deterministic separation for equal fits, so no client renders five
    identical cards (42 of 470 clamped identically under v1). Evidence
    density first, then greenfield, then the platform name — every term
    stable across processes."""
    greenfield = next((f["value"] for f in row["factors"]
                       if f["name"] == "Greenfield family"), 0.0)
    return (-row["fit_score"], -row["evidence_strength_mean"],
            -greenfield, row["platform"])


def _sequence(rows) -> list:
    """Reorder so a platform never precedes something it depends on.

    Fit decides the order; this repairs it. A stable pass over the fit order,
    emitting a card only once every prerequisite present in this set has been
    emitted — so among cards with no dependency between them the fit order is
    untouched, and the repair is visible on the row that moved.

    A cycle cannot deadlock the page: once nothing is emittable the remaining
    cards are appended in fit order and each says its prerequisite was not
    resolvable. A ranking that hangs is worse than one that discloses.
    """
    remaining = list(rows)
    names = {r["platform"] for r in remaining}
    out, placed = [], set()
    while remaining:
        # THE BEST AVAILABLE CARD, not the first one the scan reaches. A
        # first-found pass let a 30.9 card precede a 47.5 one that was merely
        # waiting on one more prerequisite — the sequencing repair silently
        # became the ranking. `remaining` is already in fit order, so the
        # first emittable entry IS the highest-fit emittable one.
        progressed = False
        for r in list(remaining):
            need = {d for d in (r.get("depends_on") or ()) if d in names}
            if need <= placed:
                out.append(r)
                placed.add(r["platform"])
                remaining.remove(r)
                progressed = True
                break                    # re-scan from the top: placing this
                                         # card may free a better one
        if not progressed:
            for r in remaining:
                r["sequence_note"] = (
                    "prerequisite chain could not be resolved (it names a "
                    "platform that in turn waits on this one); ranked on fit "
                    "alone")
            out.extend(remaining)
            break
    return out


def rank(candidates, all_gap_cells=None) -> list:
    """Scored, fused, then sequenced. `rank` is 1-based and assigned after all
    three, so two cards never share one and no card precedes its own
    prerequisite.

    The three passes are deliberately in this order and each may only undo the
    one before it within a stated bound: fusion reorders inside FUSION_BAND,
    sequencing reorders only to satisfy a declared prerequisite, and both say
    on the row when they moved it.
    """
    scored = sorted((score(c, all_gap_cells) for c in candidates), key=_tie_key)
    depends = {str(c.platform): tuple(getattr(c, "depends_on", ()) or ())
               for c in candidates}
    for r in scored:
        r["depends_on"] = list(depends.get(r["platform"], ()))
    fit_only_order = [r["platform"] for r in scored]

    fuse(scored)
    scored = _fused_order(scored)
    fit_order = [r["platform"] for r in scored]     # what sequencing sees
    rows = _sequence(scored)

    for i, row in enumerate(rows, start=1):
        row["rank"] = i
        moved = fit_order.index(row["platform"]) != (i - 1)
        fused_from = fit_only_order.index(row["platform"])
        fused_to = fit_order.index(row["platform"])
        terms = " + ".join(
            "{w} x {n}".format(w=f["weight"], n=f["name"].lower())
            for f in row["factors"])
        # THE FUSION, SAID OUT LOUD on every card. A reader who cannot see why
        # one card beat another is the complaint this was built for, and
        # "fusion agreed with the arithmetic" is as much of an answer as a
        # move — silence would leave the two indistinguishable.
        won = [n for n, r_ in row["signal_ranks"].items() if r_ == 1]
        placing = ", ".join(f"{n} #{r_}" for n, r_ in row["signal_ranks"].items())
        if fused_to == fused_from:
            row["fusion_note"] = (
                f"Rank fusion (RRF, k={RRF_K}) agreed with the fit order. "
                f"Placings: {placing}." +
                (f" First on {', '.join(won)}." if won else ""))
        else:
            direction = "up" if fused_to < fused_from else "down"
            row["fusion_note"] = (
                f"Rank fusion (RRF, k={RRF_K}) moved this card {direction} "
                f"{abs(fused_to - fused_from)} place(s) against the fit order, "
                f"within the {FUSION_BAND:g}-point near-tie band. Placings: "
                f"{placing}. Fusion only reorders cards the fit does not "
                f"separate by more than {FUSION_BAND:g} points.")
        row["rank_basis"] = (
            "fit" if not moved and fused_to == fused_from else
            "sequenced: it is held behind " + ", ".join(row["depends_on"])
            if moved and row["depends_on"] else
            "sequenced: another card on this page waits on it" if moved else
            f"rank fusion within the {FUSION_BAND:g}-point near-tie band")
        row["fit_basis"] = (
            "Computed by the shared platform-fit engine: 100 x ({terms})"
            " x {mult} readiness = {fit}. Readiness is a multiplier, not an"
            " addend: a platform whose prerequisites are red cannot reach the"
            " hot band ({hot}), and relevance {rel} caps it. Alignment basis:"
            " {basis}. Rank basis: {rank_basis}. State: {state}."
            " {fusion}".format(
                terms=terms, mult=row["readiness_multiplier"],
                fit=row["fit_score"], hot=HOT_THRESHOLD,
                basis=row["alignment_basis"], rank_basis=row["rank_basis"],
                rel=row["relevance"], state=row["state"],
                fusion=row["fusion_note"]))
    return rows
