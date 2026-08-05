# Fields the app depends on

Every entry below is a field the rendering layer reads. Where it is absent or
off-contract, a real surface degrades in a specific, observed way. This is not a
second contract — the page packs remain authoritative for shape — it is the list
of places where "technically valid" and "renders correctly" came apart in
production, with the consequence named so the cost of skipping one is visible.

Read this once. Then, when a page pack asks for a field listed here, know that
something on the page has nowhere else to get it.

## Closed vocabularies — a sentence in an enum field breaks a filter

| Field | Values | What a wrong value did |
|---|---|---|
| `context.timeline.events[*].signal` | `POSITIVE │ NEUTRAL │ NEGATIVE` | A consequence SENTENCE was written here. The column is TEXT, so promotion succeeded, and the D5 timeline's Positive/Neutral/Negative filters matched **zero of ten** events on a page with ten. |
| `context.timeline.events[*].maturity_effect` | prose, 1–2 sentences | This is where the consequence sentence belongs. |
| `techstack.techstack.items[*].status` | `CONFIRMED │ INFERRED │ CLAIMED │ ABSENT` | Required per row. There is no `PARTIAL`. |
| `heatmap…band` | `Activating │ Building │ Competing │ Differentiating` | Four bands. **Never write M5 or "Transformational"** — the resolver has four branches and anything ≥4.0 is Differentiating. |

Gate **CG-09** now refuses an off-vocabulary value at submit. Case matters: the
renderer compares against the declared spelling, so `positive` misses the filter
exactly as prose does.

## Every claim-bearing item cites its own evidence

Gate **AG-03**. Per ITEM, not per section. A why-now card, finding,
recommendation, insight, timeline event, issue, tech row, alert, cap, gate
result, phase or conversation starter that asserts something must carry a
non-empty evidence list of its own.

**An inference cites too** — the source it was drawn from. "No evidence yet" on
a card that makes a claim is not an empty state; it is an uncited claim.

## Leadership contact routes

`overview.leadership.roster[*]` now carries, per person:

| Field | Note |
|---|---|
| `email` | a work address, from a cited source |
| `linkedin_url` | full URL |
| `phone` | a line that is actually this person's. **Never a switchboard number on an individual's row** — that misrepresents it. |
| `enriched_at` | the date the route was established |
| `enrichment_basis` | WHERE it came from |

`enrichment_basis` is not decoration. **"Clay reports it" is not a source** — the
filing or profile Clay surfaced is. Without it, a contact route is the one field
on the panel asserting something with no provenance, and the panel says so.

These are established in YOUR session (step 4, Clay) and written into the roster
item. The app makes no third-party call while serving, so a route that is not
promoted does not exist for the reader. Mark the paths `internal_only`.

Do not attach a contact to the wrong person. A name-similar match is an identity
failure: a search for a Chief Data Officer that returns an intern with the same
surname is not that person, and quarantining the field is correct.

## Firmographics, and where the footprint actually comes from

The strip's footprint renders from `context.regulatory_standing.jurisdictions` —
the app reads it from there, not from `firmographics.fields[]`, whose must-present
set names HQ and branches but no footprint. So an empty footprint on the overview is
an empty `jurisdictions` on the context page: fix it there.

The two must agree, and `jurisdictions` is the fastest contamination check in the
product — a five-state Northeast footprint on a Utah institution is a different
institution. A disagreement between surfaces is a contradiction to resolve or
quarantine, never variation to average.

**CAGR belongs in `firmographics.fields[]`**, where the must-present set names it,
with its own `as_of` and `source_e_id`. It is NOT a financial-series field (below).

Every firmographic field renders its own provenance, so a value with no
`source_e_id`/`as_of` renders as a bare number. `branches` is an integer count —
never a serialised list, never a dict repr.

## Values the app computes — do not send them

Counts are computed, never asserted (invariant 8). Specifically:

- **CAGR** is computed at read from the financial series' first and last dated
  points over the real number of years between them. Send ≥2 dated points and it
  appears; send one and it correctly does not. A **cited** CAGR goes on
  firmographics instead.
- **`grounded_on`** is the length of the citation array.
- **Landscape counts** are recomputed from the T1 register.
- **Pillar shares and thin-evidence flags** are the database's generated columns.
- **An insight card's pillar and theme** — see the insights section below.
- **A cell's peer figure** — inherited from the category median and labelled a
  proxy.

### Three columns exist and are deliberately unbound

The instinct to fill a column that exists is the failure mode here.

| Do not send | Why |
|---|---|
| `overview.financial_series.basis` at section level | Basis is stated PER POINT, because mixing metric definitions across periods produces a fake trend. A section-level copy is a second place the definition can disagree with itself |
| `overview.financial_series.cagr` | Computed at read (above). Send the dated points |
| `insights.landscape.summary` | Refused. The corpus's one summary line belongs to T1 on the techstack page; this column's DDL comment imported it across a page boundary |

### One section is server-derived: do not author it

`heatmap.value_chain` has `fields: {}`, and that is the ANSWER, not a gap. The
arrangement comes from joining `ccg_value_chains` to `ccg_vc_mapping` — a property
of the catalogue for this sub-vertical and version, not of this run. You emit the
envelope and nothing else; **CG-04 refuses fields outside the section contract**, so
an authored stage list is a contract fork. If the surface renders empty, that is a
server-side derivation to fix, not a payload to write.

(Known flaw, so you recognise it: `ccg_value_chains.chain_id` is minted per STAGE,
so one value names one stage and only `sub_vertical` + `version` identifies a chain.)

### What the app CANNOT compute, and therefore needs from you

- **Peer medians at pillar and category grain.** They exist in the workbook's
  `Peer_Benchmarks` tab and nowhere else — 0 of 765 cell rows carry one. Send them at
  those two grains. With none, the heatmap shows no tick and no delta, which is
  correct and says nothing.
- **Peer technographic deployment.** `techstack.items[*].peer_coverage`,
  `.peer_deployments[]` and `.dma_impact` are real fields now. A per-peer verdict is
  a research finding and cannot be derived — the version this replaced decided
  "✓ deployed" beside a named institution from `hashCode(row_id + peerName) % 100`.
  **AG-04 blocks**: a stated share needs one row per peer (unestablished peers carry
  `deployed: null`), `source_url` and `as_of` on every `deployed: true` row, and
  agreement with its own breakdown to within one peer. Two of five with three unknown
  is not 40%.

### Five fields that had no contract, so submissions were discarded

Each column existed with nothing bound to it, so whatever a producer sent went
nowhere and the surface rendered empty — which read as producer laziness and was not.

| Field | Requirement |
|---|---|
| `overview.why_now.synthesis` | **Required.** 60–110 words across the signals: what they TOGETHER say about timing. Consistent with `exec_summary.complication` and roadmap phase 1. Required even on a thin card |
| `overview.financial_series.reading` | **Required.** 35–60 words: does the growth outpace the digital capability that has to support it. Serves BOTH O8 and C6, so written once |
| `overview.sentiment.themes` | **Required.** 2–4 per audience from the review TEXT, each with `cap_statement` naming the cell it caps and at what level |
| `overview.sentiment.gap_analysis` | Conditional — omit when only one audience was established |
| `context.context_sentiment.context_tiles` | **Required.** Three tiles `customer │ employee │ market`; each row's `note` must END by naming the cell it caps |

## Reasoning that renders

These render in full and were previously written and never shown, which is the
whole of the "shallow" reading:

- insight cards: `severity_rationale`, `alternative_explanation`,
  `validation_question`, `claim_label`, and the whole `r_layer`
- recommendations: `root_cause`, `cost_of_inaction`, `sequencing_reason`,
  `kpi_triple`, `validation_gate`, `r_layer`
- why-now: `cost_of_acting_now` — REQUIRED, and the honest other side of the
  argument. A card with only the upside is the shallow one.
- timeline: `storyline` and `arc_shape`
- roadmap: each phase's `rationale`
- platform: `discarded[]` with reasons — the "why not X" a reader looks for

Write them as if they will be read, because they are.

## Linkage that makes a page traceable

| Link | Why |
|---|---|
| `issue.linked_subcap_ids` | An issue with no cell cannot be tied to the DMA, and the drilldown says so. **Every matter that constrains a capability must name it.** |
| `event.capability_ids` | The route from a historical event back to the grid. |
| `techstack.linked_subcap_ids` | The tech detail's DMA impact is exactly these cells at their served scores. With none, it claims no impact. |
| `insight.linked_subcap_id` | How the card's pillar AND its theme are derived. A card with no cell gets neither. |
| `focus_area.subcaps` | Matched exactly. A cell the focus area does not name is not in its drilldown. |
| `cell_evidence.cells[*].synthesis` | The heatmap drawer's body. Present on 69 of 765 cells in a real run; a cell without one opens a drawer that says nothing. |
| `issue.capped_subcap_ids` **with a level** | A cap with no level reads as a link. The grid distinguishes a padlocked ceiling from a linked cell, so an unlevelled cap asserts nothing. |

## Insights: theme and pillar are DERIVED — do not send either

`theme` and `pillar_id` were null on all eight cards of a real run, so the D2
theme lens grouped everything by null and the pillar lens collapsed to one bucket.

Neither is a card field. **The I1 contract defines no `theme` and `insight_cards`
has no column for one**, and sending either creates a second answer to a question
the app can already answer:

| Lens | Derived from | Your lever |
|---|---|---|
| pillar | the leading token of the card's own cell id (`P4C1.3.1` → `P4`) | link the card to a cell |
| theme | the O6 **finding** that shares the card's cell — then a finding in the same category, recording which rung answered | make the cards and the findings talk about the same cells |

So the way to make the theme lens work is the OVERLAP: a card whose
`linked_subcap_id` an O6 finding also links inherits that finding's theme. A card
whose cell no finding touches groups by pillar, labelled *no theme derivable* — not
an error, but if half the cards land there, the findings and the cards are about
different assessments.

The vocabulary lives on `overview.findings[*].theme`:

```
DATA FOUNDATION │ WORKFLOW │ DECISIONING │ CHANNELS │ TIMING │
RISK & COMPLIANCE │ OPERATING MODEL
```

**"Other" is not a theme** and there is no residual bucket to send a finding to. If
a finding fits none of the seven, it is probably two claims — split it, or pick the
one the evidence supports. `OPERATING MODEL` is the widest and takes most orphans
honestly; reaching for it is a judgement, dumping into it is not.

`severity` drives the triage flag, and the app maps all four contract values
(`critical │ high │ opportunity │ info`) — nothing falls through to a default, so
send the severity the consequence supports rather than the one that looks urgent.

## Sentiment

**SG-S8** discloses at one rated line: the client reads *"Sentiment rests on a
single source, so treat it as indicative only"*, and the run still promotes. The
gate counts rated rows at submit and **never reads `displayed_lines`** — that field
is for the renderer.

Two consequences worth knowing before you write the section:

- **A row with no `rating` is not a line of sentiment.** It is a source you
  searched, and it belongs in `sources_searched`, not in the grid to raise a count.
- A self-published NPS standing alone is thin whatever the count — one voice about
  itself, repeated, is still one voice.

`themes[]` and `gap_analysis` are bound now and were not: the columns existed with
no contract fields, so whatever was submitted was discarded at promotion and the
card rendered nine words. STEP 3 and STEP 4 of the O9 prompt finally land.

`overview.sentiment.bars` and `context.context_sentiment.context_tiles` are **one
dataset at two depths**, reconciled by `e_id` and `rating`. Produce O9, then project
C4. There is no `metric` key — a prototype leftover, named by no source.

## Excerpts

The registration floor is 50 characters. A corpus whose excerpt median is 80 is
passing the gate and saying nothing — and 27 of 120 items in one run had **no
excerpt at all**. An excerpt is the sentence a reader would quote back. Take the
whole claim, not the fragment that clears the floor.

## Dates

`runs.completed_at` becomes every evidence item's `reference_date`. Without it,
the GENERATED `age_months` is null and `recency_band` is `UNVERIFIED` for EVERY
item — 120 items, 45 of them dated, all unverified, and a FACT then rendered
beside an "unverified" label. Check the manifest, and check the request id's own
`…-YYYYMMDD-NNNN` token before concluding there is no date.
