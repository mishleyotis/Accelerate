# Evidence, citation and the peer ladder

## Two legal origins, and only two

**Package evidence** is already in the store with an entity, a run, a tier and a URL. Cite
it; never create it.

**Enrichment** is anything found outside the package. Register it first, cite it second. The
server allocates the id and computes the rank score. Registration is idempotent by content,
so one annual report cited by six cards produces one row.

## The quality ladder

| Tier | Type | Weight | Ceiling |
|---|---|---|---|
| T1 | Regulatory and audited sources — and machine technographic scans | 1.0 | L5 |
| T2 | Official disclosures; structured internal notes | 0.85 | L5 |
| T3 | Third-party analysis — analyst, app ratings, trade press | 0.7 | L4 |
| T4 | Internal unvalidated narrative | 0.55 | L2.5 |
| T5 | Marketing and claims — requires corroboration | 0.3 | L2 |

Two rules that cost real score accuracy:

- **A machine technographic scan is T1, never T4.** Filing it at T4 caps the capability at
  L2.5 and silently suppresses the score. It was the commonest misclassification in the
  corpus.
- **There is no T6, T7 or T8.** A separate eight-row source-type table renders the weakest
  tier as something that reads stronger than it is, inverting trust exactly where the
  evidence is weakest.

## Recency — one vocabulary

| Age | Band | Recency score |
|---|---|---|
| ≤ 12 months | CURRENT | 5.0 |
| 12–24 months | RECENT | 4.0 |
| 24–36 months | DATED | 3.0 |
| 36–48 months | STALE | 2.0 |
| 48 months+ | ARCHIVAL | 1.0 |
| no date | UNVERIFIED | 1.0 |

An undated item is never rendered as current. Age is computed against the run's pinned
reference date, or it is null. Never a sentinel.

## The rank score

```
ERS = (0.35 × Tier) + (0.25 × Recency) + (0.20 × Specificity) + (0.20 × Corroboration)

Each factor is scored 1.0–5.0, so the result is bounded 1.0–5.0.
High ≥ 3.5    Medium 2.5–3.5    Low < 2.5

Corroboration  3+ independent / 2 independent / single T1–T2 / single T3 / single T4–T5
               "Independent" means different ORIGINS. An annual report and an investor
               deck from the same institution are ONE source.
```

The server computes this at registration. Never send it; it is ignored.

## The peer fallback ladder

Where the peer table lacks a figure, apply in strict order and stop at the first rung that
yields one.

| # | Rung | Procedure | Records |
|---|---|---|---|
| 1 | Peer table figure | peer_comparison_table.csv carries the cell | `basis = table` |
| 2 | Recompute at lower cohort size | Drop the peer lacking the figure and re-take the median. Floor of three: N=5 → sorted[2]; N=4 → mean of sorted[1..2]; N=3 → sorted[1]. | `basis = recomputed, peer_n records the size actually used` |
| 3 | Adjacency inference | Infer from a neighbouring sub-capability in the same category. | `basis = inferred, labelled INFERENCE with one clause of reasoning` |
| 4 | Proxy ceiling | A signal that caps rather than estimates — e.g. a specialist-headcount ratio below 5% caps its category, negative-dominant review sentiment caps at mid-scale. Lowest cap wins. | `basis = inferred, proxy_disclosure carries the literal phrase 'peer proxy'` |
| 5 | Stop | Print 'Cannot reliably estimate'. | `basis = cannot_estimate, peer_median stays NULL` |

**Never impute a value into the cell.** A proxied figure must disclose itself with the
literal phrase *peer proxy* — a governance check greps for it — and must never claim
identical methodology. A proxy that reads as a measurement is the peer-fabrication failure
this ladder exists to prevent.

## Linking

An item supports a cell when it **speaks to that capability**, not when it was found while
researching the category. The commonest cause of over-linking is one category-level search
mapped identically onto five sub-capabilities.

A cell whose every drawer is empty is a **linking** failure, not an evidence gap. Diagnose
before enriching — enriching a linker bug adds evidence that also will not render.

## Four failure modes, ordered by damage

| Failure | What the client sees | Caught by |
|---|---|---|
| **Fabricated** — no such row | A chip that opens nothing | Pattern and existence checks, fail-closed |
| **Foreign** — a real row, another entity | A competitor's data on their page | Cohort filter plus the identity gate. **Stop production.** |
| **Misattributed** — real row, wrong cell | Evidence that does not support the claim | Linker thresholds. The quietest failure: nothing breaks |
| **Unverifiable excerpt** | A quote not in the source | Verified against the fetched artefact at registration |

## When you cannot establish an id

In order, stopping at the first that applies:

1. **Enrich.** Find a real source, register it, cite the returned id. This is the answer
   most of the time and the highest-value work on any surface.
2. **Drop the claim, keep the surface.** A shorter honest card beats a complete unfounded one.
3. **Emit the empty state with what was searched.** Absence with a recorded search is a
   finding. Absence with no record is a research failure wearing a finding's clothes.

Never keep the claim and remove the citation. An uncited claim is excluded by the serve
layer anyway, so it is wasted work as well as wrong.
