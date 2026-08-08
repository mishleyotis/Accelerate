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

Run the two local checkers before you spend a round trip — they state the same
rules in the same words, and name the gate that will refuse you:

```
python scripts/check_payload.py payload.json --page heatmap \
    --subvertical SV2 --cells bundle.json
python scripts/check_language.py payload.json
```

`--subvertical` turns on ET-05 and `--cells` turns on CG-14; without them those
two print "not run" rather than passing silently.

**CG-15 is not in the local checkers.** It runs at submit only, so a clean local
run says nothing about it. Read its section below before you write prose, not
after the verdict.

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

### CG-15 · a payload that says nothing

**The only gate that reads the prose for content.** Every other gate here checks
structure, identity or arithmetic, and a payload can satisfy all of them while
asserting nothing: all 34 sections present, every required field set to `"N/A"`
or `[]`, every id resolving, every figure agreeing with the workbook — zero
blocking reasons, eligible to promote. That is what this closes.

Five refusals, each naming its arithmetic in the verdict:

| Refused | The arithmetic |
|---|---|
| A **placeholder** where the contract requires prose — `N/A` `TBD` `-` `—` `none` `unknown` `not applicable` `pending` `todo` `nil`, the empty string, whitespace | Case- and punctuation-insensitive: `"N/A."`, `"n.a"`, `"  "` all normalise to the same key |
| A prose field **under a credible floor for its own contract** | `words < ceil(stated_floor × 0.5)`, minimum 3. The floor is read from the field's own `doc` text, so `consequence` (6-14) and `answer` (90-150) get different lines. A field whose stated floor is under 6 is a label, not prose, and only the placeholder rule applies to it |
| A **section every one of whose present content fields is vacuous** — the headline case | `vacuous / present == 1`, present ≥ 1, and no valid `empty_state` |
| **Template prose** across items of one field with a name substituted | 8-word shingles, `overlap = shared / min(count A, count B) >= 0.40`, connected group of **3 or more** |
| Prose that only **restates a score** ("P4C1 scores 2.1, below the peer median of 3.0") or only **inventories the evidence** ("Two items speak to this cell") | Content words left after removing stopwords, numerals, catalogue ids, band words, the score register and the evidence-inventory register: `residual ≤ 2` on a text of 5 tokens or more |

**Where the thresholds come from.** All four numbers are tuned against the
promoted Baxter run, not chosen: its lowest words-to-floor ratio is 0.64 (a
16-word timeline body against a 25-word floor — real content that undershoots
its budget, and it passes); its lowest residual is 4 content words (a seven-word
`consequence`); and across all 249,374 item-prose pairs the highest 8-gram
overlap between two genuinely distinct arguments is 0.179, against a refusal
line of 0.40.

#### What it deliberately allows

**An honest absence is a finding, and it passes.** Refusing it would be worse
than the hole this closes — it would push you toward inventing content to clear
a gate. Two exemptions, each narrow:

- a section carrying a valid `empty_state` (reason **and** `sources_searched`)
  is not a shell, so the **section** check stands down for it. That, and only
  that: an `empty_state` on a section that is otherwise populated does **not**
  exempt the prose beside it — overview.sentiment in the promoted run has bars,
  themes and a gap analysis as well as an `empty_state` naming the review text
  it could not cite, and one declared absence must not switch the gate off for
  everything else in the section;
- an **item** recording an absence on the protocol's own ladder —
  `WORKED_ABSENT`, `UNWORKED`, `NOT_RUN`, `verified_absent`, `verified_sparse`,
  `cannot_estimate`, `insufficient_cohort`, `quarantined` — **with the search
  that established it** (`sources_searched`, `queries_run`, or a
  `not_run_reason`) is exempt from the floor, the residual and the template
  checks.

`thin: true` is **not** one of them. It says the evidence is short of a cell, not
that the argument is, and the contract still asks for the argument. Neither is
`recency_band: UNVERIFIED` — an undated source is CG-10's business, and no
licence for the sentence beside it to say nothing.

The eleven alert justifications in the promoted run sit at an 8-gram overlap of
0.90–0.97 and pass, because every one of them records `WORKED_ABSENT` or
`UNWORKED` with the four sources it searched. They say the same sentence eleven
times because it is the same finding eleven times, and demanding variation there
would be demanding invention. **Strip the ladder and the same three sentences are
a template** — the exemption is the record, not the wording.

Two more things it does not fire on:

- **`narrative_thread` repeated across a page's sections.** It is one thread per
  page carried onto every section by contract; 10 of overview's 12 sections carry
  the identical string in the promoted run, correctly. Repetition is only a defect
  where the contract asked for one argument **per item**.
- **A number.** A score came off a workbook row, so a section carrying a real
  figure is not a shell — it gets field verdicts, not the section verdict.

The one thing no absence excuses is a **bare placeholder**. `"N/A"` is not the
absence protocol; the protocol is a stated reason plus the ladder, and it is
available on every section that needs it. `"N/A"` renders as itself.

#### What it caught on a run that had already promoted

All 17 `overview.ceilings.rows[*].rationale` values — one template with the cited
document swapped, two pairs of them byte-identical:

> Best evidence is T2-grade (**BCU 2024 Annual Report (PDF)**), which licenses
> observation up to the Differentiating band under the tier ceiling. The limiting
> absence is internal utilisation evidence — public sources establish deployment,
> not depth of use.

The contract asks that field for "TWO halves, both required: (a) what the
evidence DOES establish, cited; (b) the specific thing whose ABSENCE set the
ceiling". Seventeen categories got one sentence about tier grades. The repair is
to write (b) per category — the artefact whose absence caps *that* category —
not to reword the template seventeen ways.

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

### ET-04 · a cited id resolves to a row that carries its excerpt

Invariant 4 is fail-closed in three parts, and only two of them used to be
enforced: the id resolves, it belongs to this entity and run, and **it carries a
verbatim excerpt of 50–500 characters**. A citation that resolves to a row with
an empty excerpt renders as a chip a reader opens onto nothing — worse than an
uncited sentence, because it claims a source.

Both sides of the boundary. `register_evidence` refuses a short span at the
door; an INGESTED row can still arrive without one, and it is the citation, not
the registration, that puts it in front of a client. The payload's own copy —
`heatmap.evidence[*].excerpt`, which the chip renders — is held to the same
50–500 band, and an empty one is named as empty rather than as short.

### ET-05 · a run cites only its own sub-vertical's variant cells

A T2 variant cell's terminal segment names the sub-vertical that owns it:
`P1C1.3.CU1` is credit unions, `P1C1.3.IC1` is insurance carriers,
`P2C4.6.RIA1` is RIAs. A credit union's payload citing 59 insurance-carrier,
RIA and insurance-broker cells is what produced this gate.

**One-sided, deliberately.** A cell is foreign only when its code names exactly
ONE sub-vertical AND that sub-vertical is not the entity's. A base cell
(`P1C1.3.2`), a family code (`P1C2.7.BK1` — the depository family; NCUA is the
credit-union regulator) and a product line (`P3C4.2.PEN1`) all serve everyone.
An entity whose sub-vertical is not in the vocabulary keeps everything.

The serving tier already filters these on read. This gate exists because a read
filter cannot repair the SENTENCE written beside a cell that does not apply:
drop the cell from the citation list, and take the reasoning that rests on it
with it. Sweeps every `*subcap_ids` list and every `subcap_id` scalar.

### CG-10 · a date that could not be established says so

An item's own dating field — the timeline's `event_date`, the register's
`opened_on`, a signal's `dated_on`, a firmographic's `as_of` — is a date or an
explicit absence rung. A bare null does not render as "no date"; it renders as
an empty slot beside a populated one, and the surface cannot tell *nobody
looked* from *looked and found nothing*. Those are different facts, so the
payload states which.

The rungs it accepts: `UNVERIFIED` / `WORKED_ABSENT` / `NOT_RUN` / `undated` on
a `recency_band`, `recency_tag`, `band` or `*_basis` key · `quarantined: true`
with its reason · the item's own `sources_searched` ladder. Three financial
firmographics in a promoted run already do this correctly (`as_of: null`,
`recency_band: "UNVERIFIED"`) and pass untouched.

**A second date on the same item is not policed.** `resolved_on` on an ACTIVE
matter, `closed_on` on an ANNOUNCED merger, `appointed_on` where the source
gives no start date — the event has not happened, which is a fact about the
world, not a gap in the research.

Its evidence half: a cited row with no `published_date` carries `recency_band`
UNVERIFIED. A band of CURRENT with no date is a freshness reading computed from
nothing, and the drawer's freshness dot is drawn from it.

### CG-11 · prose begins as a sentence

Mechanical. A prose field on a client surface begins with a capital.

Scope: the value's KEY is a prose key, **or** the value ends in terminal
punctuation (the producer wrote a sentence, so it is one). A noun-phrase
fragment that renders inline after a label — `unit: "full and part-time
employees"` — is neither, and capitalising it mid-sentence is the same defect
pointing the other way.

Never touched: a **verbatim excerpt or quote** (editing a quotation's first
letter is the one thing evidence may never have done to it), an id, a hostname,
a URL, an enum, a `producer_version`, a single token.

**The exemption that matters**: a first word carrying an uppercase letter after
its first character — nCino, iOS, eBay, iPhone — is the vendor's own
orthography. `nCino originates the commercial book` passes; `the nCino
deployment covers commercial lending only.` does not, and the verdict names the
word and its repair.

### CG-12 · a face field is a label, not a paragraph

Two measured failures, one class: a 20–40-word `window` clause put in a chip on
the why-now card face destroyed the strip's layout, and a 150-character
`detection_basis` put in the register's right-hand badge overflowed every row.

Budgets, each naming its slot and where the long form lives:

| Field | Budget | The long form belongs in |
|---|---|---|
| `why_now.signals[*].window` | 20–40 words | `consequence_of_waiting` |
| `why_now.signals[*].trigger` | 25–45 words | `why_this_sequence` |
| `techstack.items[*].detection_basis` | ONE clause, ≤160 chars | `dma_impact` (40–90 words) |
| `landscape.tiles[*].detail` | ≤90 chars | — |
| `safeguard_gates.gates[*].plain_label` | 6–24 words | `what_it_checks` |
| `opportunity…feature_that_addresses_it` | ≤80 chars | — |

**The repair is to MOVE the prose, not to trim it.** A 634-character
three-sentence detection basis is not a long clause; it is an argument in the
wrong field.

### CG-14 · a linked cell exists on this run

`linked_subcap_ids` on a tech row and on a why-now, and every other
`*subcap_ids` list, render as chips that open the cell drawer. A cell the run
does not carry opens onto nothing and stays invisible until somebody clicks —
so it takes the same fail-closed posture as an evidence id rather than a
render-time guard. Eleven alerts in a promoted run cited placeholder ids of the
shape `P2C2.x.7`.

Existence, not score: a cell the run carries with a null score is still a cell,
and refusing a link to one would refuse the thin-evidence case the heatmap
exists to show.

### CG-13 · every required field has somewhere to live

Build time, not submit. A required contract field with no column is validated at
submit and then discarded at promotion — the card renders empty under a real
client's name and nothing failed. Every required field is either bound by its
section's writer or named in the computed-at-read register with the source it is
recomputed from. The same sweep also resolves every path the gate registries
name against the contract: a registry pointing at a field the contract does not
declare is a gate that is switched off and says nothing about it.

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
