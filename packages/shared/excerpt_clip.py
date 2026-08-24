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

#: The share of all clauses landing on ONE exact length that stops being
#: chance. The measured corpus was 90.9%; prose over a real sample does not
#: reach a quarter.
CLIP_SHARE = 0.25

#: …and that many clauses at least, so a tiny corpus cannot trip it on two.
MIN_CLIPPED = 8


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

      CLIPPED  — one exact clause length holds `CLIP_SHARE` of the corpus
      CLEAN    — enough clauses to judge, and no length spikes
      TOO_FEW  — under `MIN_CLAUSES`; this corpus cannot answer

    `width` is the clip found, not a width supplied — which is the point of
    having this alongside `clause_truncated`.
    """
    clauses: list[str] = []
    for e in excerpts or ():
        if e:
            clauses += [c for c in str(e).split(CLAUSE_SPLIT) if c]

    total = len(clauses)
    base = {"total_clauses": total, "excerpts_scanned":
            sum(1 for e in (excerpts or ()) if e)}

    if total < MIN_CLAUSES:
        return {**base, "verdict": "TOO_FEW", "width": None, "clipped": 0,
                "share": None,
                "reason": f"only {total} clause(s); a length spike needs at "
                          f"least {MIN_CLAUSES} to mean anything. This is NOT "
                          f"a finding of clean — the corpus is too small to "
                          f"carry the signature either way."}

    hist: dict[int, int] = {}
    for c in clauses:
        if len(c) >= MIN_CLIP_WIDTH and c[-1:].isalnum():
            hist[len(c)] = hist.get(len(c), 0) + 1

    if not hist:
        return {**base, "verdict": "CLEAN", "width": None, "clipped": 0,
                "share": 0.0,
                "reason": "no clause ends mid-word at a repeatable length"}

    width, count = max(hist.items(), key=lambda kv: (kv[1], -kv[0]))
    share = count / total
    runner = max((n for w, n in hist.items() if w != width), default=0)

    if count < MIN_CLIPPED or share < CLIP_SHARE:
        return {**base, "verdict": "CLEAN", "width": None, "clipped": 0,
                "share": round(share, 4),
                "reason": (f"the most repeated mid-word clause length is "
                           f"{width} at {count} of {total} clause(s) "
                           f"({share:.1%}) — under the {CLIP_SHARE:.0%} share "
                           f"and {MIN_CLIPPED}-clause floor a clip has to "
                           f"clear, so this reads as ordinary prose")}

    example = next(c for c in clauses
                   if len(c) == width and c[-1:].isalnum())
    return {**base, "verdict": "CLIPPED", "width": width, "clipped": count,
            "share": round(share, 4), "runner_up": runner,
            "reason": (f"{count} of {total} clause(s) ({share:.1%}) are "
                       f"exactly {width} characters and end mid-word, against "
                       f"{runner} at the next most repeated length. Prose "
                       f"spreads its clause lengths; a hard clip stacks them "
                       f"on one integer. Every excerpt in this corpus is a "
                       f"CUT, not a quotation — a producer reading one names "
                       f"what fell past the cut, measured on one register as "
                       f"9 product names present in zero of their own cited "
                       f"excerpts."),
            "example_ends": f"...{example[-40:]!r}"}
