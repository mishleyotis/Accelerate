# The platform story

The highest-defect surface in the corpus, and the one an AE is most likely to be challenged
on, because it is the one that names a purchase. Measured: **570 of 685 breakdown modals
disagreed with their own headline fit**, **six clients ranked an out-of-vertical platform
first**, and **501 story cards shipped clipped mid-sentence**.

## The fit score is not yours

```
fit = 100 × (0.66 · opportunity + 0.34 · readiness)
```

Computed deterministically by the fit engine. **You explain it. You never recompute it, never
re-sort it, and never round it differently.** If the breakdown you render does not sum to the
headline, the breakdown is wrong — the headline is the engine's.

Two consequences that are easy to get wrong:

- **A stale fit figure is worse than a missing one.** A fit computed against a superseded run
  looks current and is not. Assert the run id before you use the figure.
- **Opportunity is weighted twice readiness.** So a platform can rank first on gap surface
  while being unsellable this year. That is not a contradiction to hide — it is the finding,
  and it belongs in the readiness prerequisites and the roadmap horizon.

## The unit of recommendation is the L3 area, not the vendor

Every claim must render the path **L3 area → L4 feature → sub-capability**. That path is what
makes a recommendation auditable rather than a vendor preference. Emit `catalogue_path` on
every gap row.

> A claim that cannot name the L4 feature addressing the cell is not a fit claim.

## The stack register changes the answer

This is the step most often skipped, and skipping it produces the Tech Stack Mismatch defect —
recommending something the client already owns.

| Register says | Do |
|---|---|
| **CONFIRMED** at this layer | Greenfield becomes **EXTENSION**. Reframe as adoption and depth, and say so explicitly |
| **ABSENT** with a demand signal — hiring, RFP, board commitment | **Raise** priority, and cite the signal |
| **Mid-migration** | A **timing constraint** on everything downstream. Carry it into sequencing |
| **CLAIMED** but unconfirmed | Treat as absent for fit, and flag the Marketing-Reality Gap |

The demand signal is where Clay earns its place: `Open Jobs` is the cheapest capability signal
there is, and a posting naming a platform is a T2–T3 citation for exactly this.

## Discard, with reasons

> **A ranking that cannot discard is a sort.**

Drop a platform when any of these hold, and emit `discarded[] {platform, reason, relevance}`:

- Sub-vertical relevance below 0.5
- The anchor cells belong to a different entity type — a carrier sub-capability on a bank
- The client already runs it at that layer
- It addresses fewer than three cells

Six clients ranked an out-of-vertical platform first; one with a relevance of 0.35 was ignored
entirely. The discard list is not tidying-up — it is the evidence that the ranking was a
judgement.

## The effort profile must match the history

Rank the effort dimensions — integration, data quality, process redesign, change management,
licensing — for **this** client, from the evidence.

> If the timeline attributes integration debt to a core conversion never revisited,
> integration ranks first. An effort profile that contradicts the history means one of them is
> wrong.

## One story per area, or four tabs render an empty state

The page tabs by L3 area, and each area shows the story whose **own gap rows** name
that area. A run promoting recommendations across five areas and a story covering
one ships four tabs saying "the platform story promoted gap rows for 1 platform,
none of them in this area". Nothing is broken and nothing is there.

> Every area the run promotes a recommendation against carries a tile, and every
> tile carries its own `r_layer`. A shared reasoning trace across five tiles is one
> argument wearing five hats — and AG-01 is satisfied per claim, not per page.

Where the engine ranked no platform for an area, `fit_score` is **null with its
reason**, not a number you produced. The engine ranks a fixed set; the null is the
honest report of that, and the reason is often the finding — an area whose
utilisation nobody has measured is an area a fit score cannot be computed for.

## The estate reach is arithmetic

"Where the estate does not yet reach" was being written from impression, and it
reads as impression. The register already answers it:

```
reached      = cells with at least one register row in linked_subcap_ids
not reached  = every other cell this run scores in that category
```

Emit both numbers and the cells, per category, with the products holding that layer
and their status. Then state **why the non-reach is established**, because status is
what makes it evidence rather than silence: `ABSENT` on a recorded negative search
is proof the run looked; `INFERRED` is a signal and never a governed layer;
`CONFIRMED` turns the tile into extension; an unresolved research flag in the
assessment is a reason to hold and stronger than any inference.

The distribution is usually the finding. When every reached cell sits in one
capability group and the lowest-scoring cells have no register row at all, say so —
as available value, never as fault. The reader may have chosen the incumbent.

## Peers: what they deployed, and the pathway back

The question a reader brings to this page is *what did institutions like us do*.
`peer_deployments[]` answers it in the shape AG-04 enforces —
`{peer, deployed, basis, source_url, as_of}` — and the gate is **not scoped to the
tech register**, so it applies here unchanged.

Research the **area**, not the vendor: the area is the question, the vendor is one
answer, and searching only the brand misses the peer who solved it with another.
Best routes, in order: the delivery partner's case study, the vendor's customer
story, the peer's own newsroom, trade press, careers postings — and **the run's own
benchmark section**, which frequently names peer platforms outright and costs
nothing to read.

`deployed: true` needs a URL and an `as_of`. Everything else is `null` **with the
searches recorded**, because a peer omitted from the list implies it was checked.
A vendor release naming a different institution establishes nothing. An announcement
four years stale with no later confirmation is `null` with the finding written out —
the reader gets the vendor and the date without a false present tense. Two
institutions publishing under one name is `null` on identity, stated.

> **Then name the pathway, in three sentences.** What the peer put in and what it
> produced, dated. Which capability of THIS client's that connects to, by cell and
> score. What sits on that pathway from us, tied to the assessment's own
> gap-to-solution mapping where the report states one.

The third sentence is commercial framing, so mark its path `internal_only` and leave
the first two on the client's page. The finding survives redaction; the pitch does
not need to.

## Readiness reasons, or it is a checklist

The readiness panel reads `recommendations[].prerequisites[]`. Reasoning written
into the story does not reach it. Cell thresholds render as badges and need no
prose; **condition rows are the only place readiness can argue**, so the `note` is
40–80 words and runs: what is already true and how it was established · what must be
true first and why it is a real prerequisite · the dependency or date that fixes the
phase. Opening on what is missing reads as a blocker list; opening on what is in
place reads as a plan.

Where a statutory date moves a phase ahead of its fit rank, say a date ordered it.
Where the engine's rank and the sequence disagree, state the disagreement and name
the gate that decided it.

## Capitals

Every prose field begins with a capital and ends in terminal punctuation. This was
measured on a live page: readiness conditions, notes and basis badges all rendering
lower-case mid-card, because they were written as dictionary fragments and never
read as sentences. They are sentences on the screen.

Contract vocabularies are the exception and inverting it breaks the page:
`opens_on`, `horizon`, `peer_basis`, `provenance`, `signal`, stack `status`,
`producer_version`, `internal_only` paths, ids and URLs are matched literally, and
capitalising them drops the row out of its filter. Scan the payload before
submitting: every string, skip the vocabulary keys, flag any first alphabetic
character that is lower-case.

## The story: 90–150 words

Not a dossier and not a vendor pitch. Four things, in this order:

1. What this platform would change for **this** client
2. Which constraint it lifts
3. What it depends on
4. What it does **not** solve

Name the cells. Cite. **Whole sentences** — 501 cards shipped clipped mid-sentence, which is a
budget failure, not a rendering one.

And: the story must reconcile to the arithmetic. If it argues for a platform the engine ranks
third, say why in the story rather than leaving the reader to notice.

## Reconcile the arithmetic with the analyst

Read the report's platform sections before you finalise the ranking.

> If the engine's rank 1 is a platform the report does not discuss, that disagreement **is a
> finding**. State it, say which won, and lower the confidence. Never ship an arithmetic rank
> that silently contradicts the analyst.

This is the single most valuable check on this page. The engine sees gap surface; the analyst
saw the client. When they disagree, the reader deserves to know.

## The R-Layer, applied here

Run it **per tile**, not once for the page.

| Step | On this page |
|---|---|
| A Hypothesis | This tile's fit claim, with its confidence |
| B Counter-evidence | Argue the runner-up explicitly. **Inside a 5-point margin, present both and say the call is close** |
| C Domain test | Plausible for this sub-vertical, size tier and regulator? |
| D Probes | Out-of-vertical rank 1 · anchor-cell entity mismatch · Tech Stack Mismatch · stale fit figure · breakdown ≠ headline · gap row disagreeing with the heatmap · **peer fabrication** (a `true` row with no source or date) · **vendor-claim substitution** (a release naming a different institution) · **missing fit figure** (an area the engine did not rank) |
| E Verdict | ACCEPT · REJECT · UNCERTAIN. Reject means **discard and re-rank**, not soften. UNCERTAIN means discovery first, and it is the right verdict where the assessment's own uncertainty band is the binding constraint |

Record `confidence` and, beside it, **why that level** — "medium because the peer
evidence is one established case in five" is a reader's basis for weighing the tile;
"MEDIUM" alone is a label.

## Gates

`S31_platform_distinctiveness` · `S13_platform_score_lead` · `S17_exec_fit_stale` ·
breakdown-equals-headline · `catalogue_path` present per row · every gap row's current score
within ±0.05 of what the heatmap serves · **AG-04** on every tile carrying
`peer_coverage` or `peer_deployments` · **AG-01** per tile, not per page.

And one that no gate can catch: **cell names resolve against the run's pinned
catalogue.** A gap row carrying a working title instead of the catalogue name reads
as a different capability from the one the heatmap serves for that id, and the
scores agreeing does not save it.
