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

# Readiness: red caps the reachable fit at 100 x 1.0 x 0.62 = 62, below the
# hot threshold. Amber is a soft penalty.
READINESS_MULTIPLIER = {"green": 1.00, "amber": 0.85, "red": 0.62}
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

ALIGNMENT_STATED = "stated_objective"
ALIGNMENT_FALLBACK = "impact_fallback"


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


def opportunity_of(cand: Candidate) -> float:
    """Mean per-cell opportunity, 0..1. MEAN and not SUM: a sum rewards a
    platform for touching many cells shallowly, which is how a breadth term
    becomes the whole score."""
    if not cand.cells:
        return 0.0
    total = 0.0
    for c in cand.cells:
        v = gap_of(c) * severity_weight(c) * evidence_strength_of(c)
        if c.incumbent_covers:
            v *= INCUMBENT_COVERAGE_DISCOUNT
        total += v
    # severity can exceed 1.0, so normalise by the heaviest reachable weight
    return _clamp(total / (len(cand.cells) * SEVERITY_WEIGHTS["critical"]))


def interconnect_of(cand: Candidate) -> float:
    """Catalogue adjacency: closing a cell lifts its siblings in the same
    category. Measured as the share of the platform's cells that sit in a
    category where it reaches more than one — a platform whose cells are
    scattered one-per-category lifts nothing."""
    if not cand.cells:
        return 0.0
    by_cat: dict = {}
    for c in cand.cells:
        by_cat.setdefault(c.category_id or c.subcap_id, []).append(c)
    clustered = sum(len(v) for v in by_cat.values() if len(v) > 1)
    return _clamp(clustered / len(cand.cells))


def absent_of(cand: Candidate) -> float:
    return 1.0 if cand.family_absent else 0.0


def readiness_multiplier(cand: Candidate) -> float:
    return READINESS_MULTIPLIER.get(str(cand.readiness).lower(), 0.62)


def mean_evidence_strength(cand: Candidate) -> float:
    if not cand.cells:
        return 0.0
    raw = [NEUTRAL_EVIDENCE_STRENGTH if c.evidence_strength is None
           else _clamp(float(c.evidence_strength)) for c in cand.cells]
    return sum(raw) / len(raw)


def state_for(cand: Candidate) -> str:
    """INSUFFICIENT_EVIDENCE where the card cannot honestly claim grounding.
    The v1 engine made this branch unreachable — 470 of 470 cards READY."""
    if not cand.cells:
        return STATE_INSUFFICIENT
    if mean_evidence_strength(cand) < EVIDENCE_FLOOR:
        return STATE_INSUFFICIENT
    return STATE_READY


def score(cand: Candidate) -> dict:
    """The fit, its factors and its state. `factors` sum to the pre-multiplier
    subtotal and the whole arithmetic is reproducible from what is returned —
    the contract's breakdown-equals-headline rule, which 570 of 685 cards
    broke by rendering two numbers from two code paths."""
    opp, inter, absent = opportunity_of(cand), interconnect_of(cand), absent_of(cand)
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
    fit = min(FIT_CAP, 100.0 * subtotal * mult)
    return {
        "platform": cand.platform,
        "l3_area": cand.l3_area,
        "fit_score": round(fit, 1),
        "state": state_for(cand),
        "factors": factors,
        "subtotal": round(subtotal, 4),
        "readiness": str(cand.readiness).lower(),
        "readiness_multiplier": mult,
        "alignment_basis": basis,
        "alignment_quote": cand.alignment_quote,
        "cells_addressed": len(cand.cells),
        "evidence_strength_mean": round(mean_evidence_strength(cand), 4),
    }


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


def rank(candidates) -> list:
    """Scored, then sequenced. `rank` is 1-based and assigned after both, so
    two cards never share one and no card precedes its own prerequisite."""
    scored = sorted((score(c) for c in candidates), key=_tie_key)
    depends = {str(c.platform): tuple(getattr(c, "depends_on", ()) or ())
               for c in candidates}
    for r in scored:
        r["depends_on"] = list(depends.get(r["platform"], ()))
    fit_order = [r["platform"] for r in scored]
    rows = _sequence(scored)

    for i, row in enumerate(rows, start=1):
        row["rank"] = i
        moved = fit_order.index(row["platform"]) != (i - 1)
        terms = " + ".join(
            "{w} x {n}".format(w=f["weight"], n=f["name"].lower())
            for f in row["factors"])
        row["rank_basis"] = (
            "fit" if not moved else
            "sequenced: it is held behind " + ", ".join(row["depends_on"])
            if row["depends_on"] else
            "sequenced: another card on this page waits on it")
        row["fit_basis"] = (
            "Computed by the shared platform-fit engine: 100 x ({terms})"
            " x {mult} readiness = {fit}. Readiness is a multiplier, not an"
            " addend: a platform whose prerequisites are red cannot reach the"
            " hot band ({hot}). Alignment basis: {basis}. Rank basis:"
            " {rank_basis}.".format(
                terms=terms, mult=row["readiness_multiplier"],
                fit=row["fit_score"], hot=HOT_THRESHOLD,
                basis=row["alignment_basis"], rank_basis=row["rank_basis"]))
    return rows
