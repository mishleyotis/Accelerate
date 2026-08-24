"""A hard-clipped excerpt, detected two ways, from one rule.

MEM-0129 and MEM-0143, both BLOCKER. Package-origin evidence arrived with
every clause cut at exactly 140 characters and joined with " | ". Three such
clauses total 426 and sail through the 50-500 verbatim window without a
murmur — so no gate fired, and 1,960 of 2,063 served evidence items across
583 of 595 cells showed a client a quotation cut mid-word.

The consequence is not cosmetic. A producer reads a vendor name out of an
excerpt THE CITABLE SPAN DOES NOT CONTAIN, because the name fell past the
cut. Substring-testing every product on one technology register against its
own cited excerpt found nine distinct product names present in ZERO of them.
Repairing that register took it from 41 rows to 27 and CONFIRMED from 9 to 3.

TWO CHECKS, BECAUSE THEY SEE DIFFERENT THINGS.

`clause_truncated` judges ONE excerpt and must therefore be told the width.
It is the door check — `register_evidence` refuses a clipped span there.

`clip_signature` judges a WHOLE CORPUS and works the width out for itself.
That is the half the door check cannot do, and the hole in the first pass at
this fix: a package that clips at 150 or 200 walks past a rule that only
knows 140. `_RATIONALE_KEYS` in the workbook parser already carries a
`rationale_150_chars` spelling, so a second clip width is not hypothetical —
it is a column name in the shipped corpus.

What the corpus check keys on is a SPIKE, not a width. Prose clause lengths
spread; a clip stacks them on one integer. Measured on the T. Rowe corpus:
4,461 clauses of exactly 140 out of 4,906, with the next most common length
(114) appearing 23 times. Nothing that writes sentences does that.
"""
from __future__ import annotations

#: The clip the shipped corpus applied, measured on 4,906 clauses.
CLAUSE_CLIP_WIDTH = 140

#: Clauses are joined with this in package-origin rows.
CLAUSE_SPLIT = " | "

#: Below this a repeated exact length is ordinary — short clauses ("Q3 2024",
#: a ticker, a role) legitimately collide, and calling that a clip would put
#: a false BLOCKER on honest packages.
MIN_CLIP_WIDTH = 60

#: A spike needs a population. Under this the corpus cannot answer, and the
#: result says TOO_FEW rather than CLEAN — the two are not the same claim.
MIN_CLAUSES = 12

#: DISTINCT clauses landing on one exact length before it stops being chance.
#: Five separate sentences ending on the same integer is not a coincidence
#: anyone should explain away; one sentence repeated fifty times is.
MIN_CLIPPED = 5

#: …and that many times the DENSITY of the surrounding lengths — distinct
#: clauses per length, not a raw count, so the rule reads the same on a
#: corpus of 87 clauses and one of 1,384. A raw count is not scale-invariant:
#: a dense neighbourhood swallows a small spike and a sparse one invents one.
#: Measured on production 2026-08-24, against a 5-either-side window:
#:   t-rowe  1,119 distinct at 140 · 94 across the other ten lengths
#:           (9.4 per length) · 119x
#:   baxter     14 distinct at  80 ·  3 across the other ten lengths
#:           (0.3 per length) ·  47x
#:   logix / gulf / axos — one distinct clause per length, no spike at all.
NEIGHBOUR_RATIO = 3.0

#: The window either side of a candidate length that "neighbouring" means.
NEIGHBOURHOOD = 5


def clause_truncated(excerpt: str, width: int = CLAUSE_CLIP_WIDTH) -> str | None:
    """One excerpt: is any clause a hard cut at `width`?

    The signature is a clause of exactly `width` characters whose last
    character is a word character, so the cut landed INSIDE a word rather
    than at a boundary. A clause that happens to run to the width and ends
    cleanly is ordinary prose and passes — this is a check for a CUT, not
    for a WIDTH.

    Returns the verdict text, or None when the excerpt is clean, absent, or
    too short to carry a clipped clause at all.
    """
    if not excerpt:
        return None
    clipped = [c for c in str(excerpt).split(CLAUSE_SPLIT)
               if len(c) == width and c[-1:].isalnum()]
    if not clipped:
        return None
    return (f"excerpt_clause_truncated: {len(clipped)} clause(s) are exactly "
            f"{width} characters and end mid-word — the hard clip "
            f"the package ingest used to apply. The 50-500 length rule cannot "
            f"see this: three clipped clauses joined by ' | ' total 426 and "
            f"look healthy. Register the WHOLE span. A truncated excerpt is "
            f"worse than a short one, because a producer reads a vendor name "
            f"out of it that the citable span does not contain — measured on "
            f"one register as 9 product names present in zero of their own "
            f"cited excerpts. First clipped clause ends: "
            f"...{clipped[0][-40:]!r}")


def clip_signature(excerpts) -> dict:
    """A whole corpus: is there a clip, and at what width?

    Returns a verdict that is always one of three words, because "I looked
    and found nothing" and "I could not look" are different claims and a
    caller that cannot tell them apart will report the wrong one:

      CLIPPED  — one exact clause length spikes above its neighbours
      CLEAN    — enough clauses to judge, and no length spikes
      TOO_FEW  — under `MIN_CLAUSES`; this corpus cannot answer

    `width` is the clip found, not a width supplied — which is the point of
    having this alongside `clause_truncated`.

    TWO THINGS HERE WERE WRONG IN THE FIRST PASS, AND PRODUCTION SAID SO.

    (1) It counted OCCURRENCES. Baxter serves 1,517 excerpt renderings drawn
    from 87 distinct strings, so one repeated sentence stacked 158 clauses on
    a length and a genuinely varied corpus could be called clipped for
    repeating itself. Distinct clauses are what carry the evidence: five
    separate sentences ending on the same integer is not chance; the same
    sentence fifty times is not five coincidences, it is one.

    (2) It measured a SHARE of the whole corpus, and that hid a real clip on
    a live client. Baxter's clip at 80 covers 12 of 87 distinct clauses —
    14% — so a 25% share rule called it clean while it served a client
    quotations ending "Sr Clo", "branch-ce" and "become an agen". A clip does
    not have to be most of a corpus. It has to be a SPIKE: real prose spreads
    across adjacent lengths, a hard cut puts everything on one integer and
    nothing on its neighbours. Baxter's full distinct histogram is 67 lengths
    holding one or two clauses each, and 80 holding fourteen.
    """
    clauses: list[str] = []
    for e in excerpts or ():
        if e:
            clauses += [c for c in str(e).split(CLAUSE_SPLIT) if c]

    distinct = set(clauses)
    total = len(clauses)
    base = {"total_clauses": total, "distinct_clauses": len(distinct),
            "excerpts_scanned": sum(1 for e in (excerpts or ()) if e)}

    if total < MIN_CLAUSES:
        return {**base, "verdict": "TOO_FEW", "width": None, "clipped": 0,
                "reason": f"only {total} clause(s); a length spike needs at "
                          f"least {MIN_CLAUSES} to mean anything. This is NOT "
                          f"a finding of clean — the corpus is too small to "
                          f"carry the signature either way."}

    lengths: dict[int, int] = {}
    for c in distinct:
        lengths[len(c)] = lengths.get(len(c), 0) + 1

    cuts: dict[int, int] = {}
    for c in distinct:
        if len(c) >= MIN_CLIP_WIDTH and c[-1:].isalnum():
            cuts[len(c)] = cuts.get(len(c), 0) + 1

    def neighbours(width: int) -> int:
        return sum(n for w, n in lengths.items()
                   if w != width and abs(w - width) <= NEIGHBOURHOOD)

    best = None
    for width, count in sorted(cuts.items()):
        near = neighbours(width)
        density = near / (2 * NEIGHBOURHOOD)
        ratio = count / density if density else float("inf")
        if count >= MIN_CLIPPED and ratio >= NEIGHBOUR_RATIO:
            if best is None or count > best[1]:
                best = (width, count, near, ratio)

    if best is None:
        top = max(cuts.items(), key=lambda kv: kv[1], default=(None, 0))
        return {**base, "verdict": "CLEAN", "width": None, "clipped": 0,
                "reason": (f"no length spikes. The most repeated mid-word "
                           f"clause length is {top[0]} at {top[1]} distinct "
                           f"clause(s) across {len(distinct)} distinct — "
                           f"under the {MIN_CLIPPED}-clause floor or inside "
                           f"{NEIGHBOUR_RATIO:g}x the density of its "
                           f"neighbouring lengths, which is what ordinary "
                           f"prose looks like."
                           if top[0] else
                           "no distinct clause ends mid-word at a repeatable "
                           "length")}

    width, count, near, ratio = best
    served = sum(1 for c in clauses if len(c) == width and c[-1:].isalnum())
    example = next(c for c in distinct
                   if len(c) == width and c[-1:].isalnum())
    return {**base, "verdict": "CLIPPED", "width": width, "clipped": count,
            "clipped_served": served, "neighbours": near,
            "ratio": round(ratio, 2) if near else None,
            "reason": (f"{count} DISTINCT clause(s) are exactly {width} "
                       f"characters and end mid-word, against {near} distinct "
                       f"clause(s) across the {NEIGHBOURHOOD} lengths either "
                       f"side ({near / (2 * NEIGHBOURHOOD):.2f} per length) "
                       f"— a {ratio:.0f}x spike where prose spreads. "
                       f"Those {count} render {served} time(s) in this "
                       f"corpus. Every one of them is a CUT, not a "
                       f"quotation: a producer reading one names what fell "
                       f"past the cut, measured on one register as 9 product "
                       f"names present in zero of their own cited excerpts."),
            "example_ends": f"...{example[-40:]!r}"}
