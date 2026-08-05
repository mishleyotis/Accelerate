# Gates and verdicts

Four families with four different jobs and four different failure behaviours. The prefix is
part of the id — three unprefixed families once collided and one of them rendered to
clients.

| Prefix | Family | When it runs | On failure |
|---|---|---|---|
| `AG-nn` | Analytical | Inside synthesis, per claim, before anything is emitted | The claim changes or is dropped — the agent's own discipline |
| `SG-nn` | Safeguard | At submit — and the results render to the client | Recorded and disclosed. Does not block promotion. |
| `ET-nn` | Enrichment trigger | During synthesis, to send the agent looking | Not a failure — a prompt to enrich |
| `CG-nn` | Corpus | At build time, over the exported pack, corpus-wide | Fails the build |

Two more run at submit and are not G-numbered because they are structural rather than
analytical:

- **Contract pass** — required fields, types, word budgets, forbidden registers, terminal
  punctuation, id resolution by pattern.
- **Evidence pass** — every id resolves and belongs to this entity and run; every excerpt is
  verbatim; every source domain is identity-checked.

**Any evidence reason at all fails the submission.** An excerpt is either a copy of
something a document says or it is not evidence.

## The gates that block most often

These are the ones a submission actually dies on, so they are named here rather than left
to be discovered from a verdict.

### AG-03 · every claim-bearing item cites evidence

Fires per ITEM, not per section. If a why-now card, a top finding, a recommendation, an
insight, a timeline event, an issue, a tech row, an alert, a cap, a gate result, a phase or
a conversation starter asserts something, its own evidence list must be non-empty. The keys
it looks for are read from each field's contract `doc` text — `e_ids`,
`supporting_e_ids`, `evidence_ids`, `new_evidence_ids`, `source_e_id`, `e_id` — so it
polices whatever the contract declared rather than a hardcoded list.

Three things it deliberately does NOT fire on:

- a row whose value is null (asserting nothing)
- a recorded absence carrying its ladder (`UNWORKED`, `WORKED_ABSENT`, `NOT_RUN`,
  `verified_absent`, `verified_sparse`, `cannot_estimate`, `insufficient_cohort`,
  `empty_state`, `quarantined`)
- a section-level envelope — the citation belongs at the item

**An inference cites too.** It cites the source the inference was drawn FROM. "No evidence
yet" on a card that makes a claim is not an empty state, it is an uncited claim, and the
gate names it as one. If you cannot cite it, do not assert it — run the ladder and emit the
absence instead.

The contradiction it also catches: an item whose state says `WORKED_FOUND` while its
evidence list is empty. One of the two is wrong.

### CG-09 · a closed vocabulary takes one of its values

Two registries feed this. The first is generated from the live schema: any field promoted
into a Postgres enum column. The second is hand-maintained for fields whose column is plain
TEXT but whose CONTRACT states a closed set — because a TEXT column accepts anything and
the defect surfaces on the page instead of at submit.

The case that produced it: `context.timeline.events[*].signal` takes
`POSITIVE │ NEUTRAL │ NEGATIVE`, and a producer wrote the consequence SENTENCE into it. The
column accepted it, promotion succeeded, and the D5 timeline's Positive/Neutral/Negative
filters then matched zero of ten events on a page with ten. The consequence sentence belongs
in `maturity_effect`; `signal` is the direction, in capitals, and nothing else.

Currently policed as contract vocabularies:

| Field | Values |
|---|---|
| `context.timeline.events[*].signal` | `POSITIVE │ NEUTRAL │ NEGATIVE` |
| `techstack.techstack.items[*].status` | `CONFIRMED │ INFERRED │ CLAIMED │ ABSENT` |

Case matters — the renderer compares against the declared spelling, so `positive` misses the
filter exactly as prose does. Null passes: absent is not wrong, a sentence is.

### AG-04 · a named peer's technographics carry their source

Blocks. Fires on any list item anywhere in a payload that carries `peer_coverage` or
`peer_deployments` — it is not scoped to the tech register, so the same discipline applies
wherever you compare a named institution's estate.

The card renders a verdict *beside a named credit union*. The version this replaces decided
that verdict from `hashCode(ts_id + peerName) % 100`, so "✓ deployed" against a real
institution was a function of the characters in a row id.

Three refusals:

| Refused | Because |
|---|---|
| A `peer_coverage` share with no `peer_deployments` breakdown | A share with no basis is unfalsifiable |
| A `deployed: true` row missing `source_url` or `as_of` | A technographic claim about a named institution is a research finding; undated and unsourced it is an assertion about someone else's estate on a client's dashboard |
| A share disagreeing with its own breakdown by more than **one peer** (`1 / len(rows)`) | The figure and its basis are two numbers that must be the same number |

**A peer you could not establish belongs in the list as `deployed: null`.** That is what lets
the card read "2 of 5, 3 not established" rather than implying five were checked. Two of five
with three unknown is not 40%; it is two of two established, or a share you do not state.
Rows with `deployed: null` count in the denominator, so scope the share to what the breakdown
supports.

### SG-S8 · sentiment rests on more than one line

**Discloses — it does not block.** A failing SG-S8 still promotes and renders to the client
with its plain label: *"Sentiment rests on a single source, so treat it as indicative only"*.
That is the point. The common misreading of this surface runs the other way — a thin reading
taken as a finding about the institution — so the thinness is stated on the card rather than
hidden by a block.

The count is computed at submit from the rating rows and is **never read from a declared
`displayed_lines`**. A producer stating its own line count is the one input this gate cannot
trust; `displayed_lines` exists for the renderer, not for the gate.

What counts, and what does not:

- Counted: `overview.sentiment.bars[]` and `context.context_sentiment.context_tiles[].rows[]`
  — the same dataset at two depths, counted identically whichever page is submitted.
- **A row with no `rating` is not a line of sentiment.** It is a source you searched, and it
  belongs in the ladder (`sources_searched`), not in the count.
- Three results: `PASS` at two or more rated rows · `FAIL` at one · `NOT_RUN` with the reason
  `no rated rows` when nothing rated was emitted at all.
- **A self-published NPS standing alone is thin whatever the count.** Where every rated row's
  source names NPS, the gate fails regardless of how many there are — one voice about itself,
  repeated, is still one voice.

## The citation stack

| | Check | Catches |
|---|---|---|
| V1 | Cited ids are a subset of the bundle you were given | Reasoning that reached outside its grounding |
| V2 | No fabricated ids — by pattern **and** by database existence | Invented ids, including in the mint namespace |
| V3 | No fabricated entity-specific tokens unless in the run's own rows | Invented platforms, agents and vendors |
| V4 | Re-embed the output; require semantic agreement with the bundle | A fluent paraphrase that invents a claim while citing only real ids |

V4 is the one that matters most: text can satisfy V1–V3 and still say something the sources
do not support.

## Reading a verdict

```json
{ "gate_id": "CG-01", "section": "findings", "path": "findings[2].body",
  "message": "quoted 2.34/5 resolves to P3C2.1.1 = 2.10 (Δ 0.24 > 0.05)",
  "severity": "block" }
```

**Repair the cause, not the symptom.** This verdict is not asking you to write 2.10. It is
telling you that you read the score from one row and the name from another. Fix the pairing.

A verdict often names the checks that *passed* alongside the one that failed — that is
deliberate, so you can see which assertion actually broke rather than re-deriving all of
them.

## Cross-surface reconciliation

The same metric on two surfaces must agree or one is quarantined. Seven pairs are enforced:

| Pair | Assertion |
|---|---|
| O1 hero composite ↔ H4 workbook rollup | Agree to two decimals before either promotes |
| O8 financial trajectory ↔ C6 Context trajectory | Identical — C6 renders O8's section |
| T2 landscape counts ↔ T1 register | Recomputed from the register, never stored |
| O10 coverage denominator ↔ H4 cell set | Computed over the same cell set the heatmap serves |
| H3 alert cells ↔ H2 cell evidence | Every alerted cell is one the payload declared under-evidenced |
| P3 roadmap rec ids ↔ P2 recommendations | Every phase cites a recommendation the payload describes |
| Run history score ↔ O1 hero | Both average the four pillar means at the same precision |

## Safeguard gates render to the client

Three consequences:

- **Plain language.** A human sentence beside every gate, 8–18 words. A client reading a
  bare code learns nothing and distrusts everything.
- **A third state.** `NOT_RUN`, with a reason. A gate reporting PASS because it did not run
  is worse than one reporting FAIL.
- **A failing gate is not a blocked run.** Disclosure is the point. The assessment ships
  with its weakness stated.
