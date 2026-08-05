# Evidence, citation and the peer ladder

## Two legal origins, and only two

**Package evidence** is already in the store with an entity, a run, a tier and a URL. Cite
it; never create it.

**Enrichment** is anything found outside the package. Register it first, cite it second. The
server allocates the id and computes the rank score. Registration is idempotent by content,
so one annual report cited by six cards produces one row.

## Registering an excerpt: re-extract, never retype

The excerpt is verified against the **fetched artefact**, fail-closed, at registration. What
the checker actually does, so you neither over- nor under-correct:

- Whitespace runs — including newlines and paragraph breaks — collapse to one space on BOTH
  sides, and the comparison is case-insensitive. **So re-flowing whitespace is safe.** You do
  not need to reproduce the source's line breaks.
- After that normalisation, your span must appear **contiguously** in the artefact. That is
  the whole test, and it is where hand-repair fails.
- The span must be **50–500 characters**.
- No reachable URL → `url_unreachable`, and nothing is registered.
- A `FACT` with no `source_url` is **automatically downgraded to `INFERENCE`** and told to you
  in `adjustments`. That is not an error; it is the system refusing to let an untraceable
  claim keep a fact's label.

Measured against production, registering one real source: four attempts refused before one
was accepted.

| Attempt | Verdict |
|---|---|
| Two passages joined together | `excerpt_not_verbatim` — the artefact has words between them, so the joined span is contiguous nowhere |
| A hand-written summary of the source | `excerpt_not_verbatim` — the words are not there |
| A Glassdoor URL | `url_unreachable` — the site returns 403 to automated fetch |
| A 123-character literal substring of the fetched page | **accepted**; ERS computed server-side |

The rule that follows: **take the span exactly as the fetched artefact holds it, in one
piece.** Reformatting is fine; joining, trimming a clause, or supplying a missing subject is
not. If the passage you want spans an intervening caption or heading, take the half that
carries the claim rather than stitching.

## A source that blocks retrieval cannot be cited at all

Glassdoor, Indeed, ZipRecruiter and the Glassdoor mirrors all return 403 to automated
fetches. A figure whose only source is one of those is **unciteable** — there is no id to
carry it.

That leaves exactly three honest moves, and inventing an id is not among them:

1. Find the same figure somewhere retrievable (an aggregator that republishes it with
   attribution, a filing, a press release) and cite THAT.
2. Carry it as an explicit inference with its route named — what you saw, where, and that the
   source could not be fetched.
3. Omit the figure, and record the attempt in `sources_searched` as a rung that did not
   resolve.

A blocked source belongs in the ladder, never in an `e_ids` list, and never behind a number
presented as cited. `01-start-here/4-absence-protocol.md` owns the ladder's shape.

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

### The whole ladder hangs from `reference_date`

`runs.completed_at` becomes every evidence row's `reference_date`. Without it the generated
`age_months` is null and **every** item bands `UNVERIFIED` — regardless of how many of them
carry a publication date.

Measured on a real run: **120 served items, 45 of them carrying a published date, and all 120
banded UNVERIFIED.** A `FACT` chip then rendered beside an "unverified" label, which a reader
correctly reads as a contradiction.

The date is usually there twice. Check both before concluding a run has none:

- the manifest — `assessment.completed_at`, `assessment_date`, `completed_at`,
  `generated_at`, `execution_timestamp`, `last_updated`
- **the run's own request id.** The corpus names every run
  `DMA-ASM-<ENTITY>-<YYYYMMDD>-<seq>`, so `DMA-ASM-BCU-20260330-0001` states 2026-03-30 as
  plainly as a manifest field would. The worker reads it as a last resort — it is read, not
  guessed.

If a run genuinely has no date, say so on the surface. Never present an item as current when
its band is `UNVERIFIED`.

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

**First, the grain.** The scoring workbook's `Peer_Benchmarks` tab states per-CATEGORY scores
for named peers plus Median / P25 / P75. Measured: **0 of 765 cell rows carry a peer median**,
and that is faithful — the workbook does not state one at cell grain.

So at pillar and category grain you serve the workbook's figure. **At cell grain the app
inherits the category median and labels it a proxy** — you do not restate a per-cell peer
figure, because no source holds one. Read the cohort from the workbook rather than assuming
it; the peers differ by sub-vertical (one credit-union run's tab named CEFCU, Alliant,
Consumers, GreenState and Lake Michigan).

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
