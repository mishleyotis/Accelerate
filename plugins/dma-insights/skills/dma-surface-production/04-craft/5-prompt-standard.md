# The prompt standard

Read this when a surface has no prompt in its page pack, or when a prompt is clearly thin
and you are about to improvise. A prompt missing any of these is asking you to guess, and a
guess that type-checks promotes silently wrong content.

## Fourteen attributes

| # | Attribute | Requirement |
|---|---|---|
| 1 | **Numbered steps** | A long prompt without steps is a wall the agent skims. Retrieval first, derivation only on failure. |
| 2 | **Output shape** | Every field named, in one brace block. Intent without shape forces a guess that type-checks. |
| 3 | **Word budgets** | Per field. Unbudgeted prose overflows its card or reads as filler. |
| 4 | **Named gates** | What will be asserted at submit, before the agent writes. |
| 5 | **Empty state** | What to emit when the evidence is not there, and what to record about the search. |
| 6 | **Explicit prohibitions** | The commonest defects are things the agent should not have done. |
| 7 | **Identity gate** | Every figure is about THIS entity. One contaminated figure reaches five surfaces. |
| 8 | **Grain lock** | A quoted figure and its named cell are the same cell, within 0.05. |
| 9 | **Citation discipline** | Register before citing; verbatim excerpts; ids the server allocated. |
| 10 | **Register rules** | A client reads this prose. No consultant register, no codes, no score-predicate openers. |
| 11 | **Measured exemplar** | A prompt anchored to a real defect is followed; an abstract one is not. |
| 12 | **Provenance** | So deterministically composed content cannot present as analyst judgement. |
| 13 | **Audience marking** | Which paths go in internal_only. An unmarked internal rung reaches the client. |
| 14 | **Ordering** | Where order carries meaning — ranked, sequenced or chronological. |

Five of these — identity (7), grain (8), citation at the item (9), register (10) and
audience (13) — are the standing clauses. They apply to every section and live in
`01-start-here/1-standing-clauses.md` rather than being restated.

## The required form

```
STEP 1 — RETRIEVE    Where the answer already exists, and how to record that it was
                     retrieved rather than derived.
STEP 2 — DERIVE      Only on retrieval failure. State what derivation is legitimate and
                     what looks like derivation but is not.
STEP 3 — EMIT        Every field in one brace block. Per-field budget. A measured
                     exemplar per prose field.
STEP 4 — ORDER       The ranking or sequencing key, and its fallback.
STEP 5 — ABSENCE     What to emit when the evidence is not there, and what to record
                     about the search that established it.
STEP 6 — GATES       What will be asserted at submit.
STEP 7 — DRILLDOWN   What the expanded panel carries, if the surface has one.
```

Steps matter more than length. Every strong prompt in the source set is stepped and every
weak one is a flat bullet list — because steps force the author to say what happens when
retrieval fails, what the ranking key is, and what to do when the evidence is absent. A
bullet list lets all three go unwritten.

## Prefer retrieval to derivation, and say so

The strongest prompt in the set opens by telling the agent the analyst has already done the
work:

> Read the reports in full. The analyst's key-findings, executive-summary and per-pillar
> conclusion sections already contain the findings; extract them with their reasoning
> intact. Record `source_kind=retrieved` with the section and page. Only if retrieval
> yields fewer than five, derive — from the joins, not the scores. **NEVER derive by taking
> the five widest score gaps; that produces a sorted list, not findings.**

That last sentence is worth more than a paragraph of guidance, because it names the exact
wrong thing an agent would otherwise do.

## Measured exemplars beat instructions

"Quantify the consequence" produces hedged prose. These produce the thing itself:

> "Blocks 34 downstream subcaps" · "5–7 month cycle compression" ·
> "Trails peer sentiment by ~0.8 stars" · "Window closes at nCino go-live"

Give an exemplar for every prose field. It is the single strongest differentiator between
prompts that work and prompts that do not.

## Name a ranking key and its fallback

> Order by strategic alignment, tie-broken by breadth of downstream impact, then severity.
> The widest gap is frequently not the most important finding. **If you cannot establish
> the entity's strategic objectives, say so, rank by downstream impact, and set
> `ranking_basis=impact_fallback` — do not pretend to an alignment you did not establish.**

A ranking without a stated fallback becomes a fabricated ranking the moment the key is
unavailable.

## Require the set to cohere

For any surface emitting several items, state what makes them a set rather than a list:

> The five findings must read as ONE story in order: the root constraint, then what it
> blocks, then where the leverage is, then the timing. If the five do not form a thread,
> you have five observations.

## Self-check

Run `scripts/score_prompt.py` on anything you write. Under 10 of 14, or under 1,500
characters for a non-trivial surface, treat it as unfinished.
