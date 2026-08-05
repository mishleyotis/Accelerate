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

| Step | On this page |
|---|---|
| A Hypothesis | The rank-1 fit claim, with its confidence |
| B Counter-evidence | Argue the runner-up explicitly. **Inside a 5-point margin, present both and say the call is close** |
| C Domain test | Plausible for this sub-vertical, size tier and regulator? |
| D Probes | Out-of-vertical rank 1 · anchor-cell entity mismatch · Tech Stack Mismatch · stale fit figure · breakdown ≠ headline · gap row disagreeing with the heatmap |
| E Verdict | ACCEPT · REJECT · UNCERTAIN. Reject means **discard and re-rank**, not soften |

## Gates

`S31_platform_distinctiveness` · `S13_platform_score_lead` · `S17_exec_fit_stale` ·
breakdown-equals-headline · `catalogue_path` present per row · every gap row's current score
within ±0.05 of what the heatmap serves.
