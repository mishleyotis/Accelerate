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

**CG-15's template rule cannot be seen one item at a time**, so there is a third
checker for it and you run it on your first twenty drafts, not on 708:

```
python scripts/check_repetition.py drafts.json --page heatmap --at-scale 708
```

What refuses a payload is never a single synthesis — it is the SHAPE all of them
share, and the shape is already visible in twenty. Two producers discovered this
at submit time on 2026-08-08, one of them after building all 708 cells. Read the
CG-15 section below **before** you write prose, and run that script before you
write the twenty-first.

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
| **Template prose** across items of one field with a name substituted | **Two terms, both required.** *Phrasing*: 8-word shingles, `shared / min(A, B) >= 0.40`. *Claim*: the same ratio over CONTENT WORDS — what is left after stopwords, numerals, catalogue ids and the score and evidence-inventory registers come out — `>= 0.40`. Connected group of **3 or more** |
| Prose that only **restates a score** ("P4C1 scores 2.1, below the peer median of 3.0") or only **inventories the evidence** ("Two items speak to this cell") | Content words left after removing stopwords, numerals, catalogue ids, band words, the score register and the evidence-inventory register: `residual ≤ 2` on a text of 5 tokens or more |

**Where the thresholds come from.** Every number is measured against real
payloads, not chosen: the promoted Baxter run's lowest words-to-floor ratio is
0.64 (a 16-word timeline body against a 25-word floor — real content that
undershoots its budget, and it passes); its lowest residual is 4 content words
(a seven-word `consequence`); and across all 249,374 item-prose pairs the
highest 8-gram overlap between two genuinely distinct arguments is **0.179**,
against a refusal line of 0.40.

**Why the claim term exists, which is the thing worth understanding.** The
registers it strips out are the frame this contract *mandates*: H2 requires
every synthesis to say where the score sits against the peer median and to cite
inline. Every honest synthesis on the page therefore shares that frame, and
scoring it would refuse prose for obeying its own contract. Strip the frame, and
what is left is what the sentence actually asserts. Measured over the four
heatmaps available on 2026-08-08, on pairs that already clear the phrasing line:

| Corpus | highest phrasing | content overlap |
|---|---|---|
| Baxter, 706 honest cell syntheses | 0.179 — **nothing refused** | up to 0.793 |
| Kitsap, 37 honest cell syntheses | 0.070 — **nothing refused** | up to 0.115 |
| Fisher, 708 refused | 1.000 | min 0.433 |
| Frost, 677 refused | 1.000 | min 0.615 |
| Baxter's 17 ceilings, refused | 1.000 | min 0.630 |

Read the first row twice. **Honest prose about one institution shares vocabulary
freely** — 0.793 between two Baxter cells that are both perfectly fine — and it
is the *phrasing* that separates them. A template is high on both. That is why
neither number alone is the rule, and why "my 708 were all textually distinct"
is not the defence it sounds like: distinctness of wording is what the first
term measures, and Fisher's 708 cleared none of it.

**Baxter's 706 are the existence proof.** A 700-cell per-cell synthesis over one
taxonomy, one institution and one mandated shape is writable and passes with a
2.2x margin. If a 700-cell page is being refused, the shape is the problem, not
the scale.

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
  checks — **on the keys that item's own contract shape declares, and no
  others.**

That last clause is not pedantry, and it is the thing this gate got wrong for a
day. Of the **nineteen** item shapes that carry a per-item prose budget, exactly
**one** declares `state` + `sources_searched`:

| Item shape | Per-item absence route |
|---|---|
| `heatmap.alerts.alerts` | `state` + `sources_searched` / `queries_run` — **the only one** |
| the other eighteen, including `heatmap.cell_evidence.cells`, `overview.ceilings.rows`, `overview.findings.findings` | **none** |

**Do not supply the keys anyway.** CG-04 sweeps section-level keys only, so an
undeclared item key passes validation; the writer has no `item:` binding for it,
so promotion drops it. On one payload measured 2026-08-08, 394 of 697 cells
bought this exemption — and the AG-03 exemption too — with `state` and
`sources_searched` on `cell_evidence.cells`, which declares neither. Both gates
now check the shape, so the keys buy nothing; before they did, they bought a
pass on a field the client would never have seen. (The serving table has since
gained a `sources_searched` column, reached through the section's own
`empty_state`; `state` still has none. Neither is a contract key on
`cells[*]`.) The verdict now names the route *your* shape has, so read it rather
than assuming the alerts route.

**Where an item shape has no absence route, there are two that always work:**

1. **Leave the item out of the array.** A per-item argument is owed per-item
   evidence. A cell no evidence reached does not belong in `cells[]` carrying a
   sentence four hundred siblings also carry — omit it, and `linking_stats`
   reports the reach honestly, which is one finding instead of four hundred
   copies of one. Kitsap's promoted heatmap emits 37 of 706 cells this way and
   passes cleanly.
2. **Say it once, in the section's own prose or its `empty_state`** with the
   `sources_searched` ladder — for arrays whose membership is fixed.

`thin: true` is **not** an exemption. It says the evidence is short of a cell, not
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

#### Writing seven hundred of these

The question that gets asked at cell 400 is "how can 700 arguments over one
taxonomy possibly be distinct?" They are distinct because **the facts are
distinct**, and the honest sentence for a cell with nothing in it is distinct
too, as long as it names what would have been there.

Four of the promoted Baxter run's eight zero-evidence cells, near-verbatim.
Same outcome, same mandated frame, and they pass with room to spare:

> **Academic partnership** leaves visible traces — *named research
> collaborations, sponsored programmes, university recruiting pipelines* — and
> none appears anywhere in BCU's own materials, its news page, or the trade
> coverage of it.
>
> **User acceptance testing** leaves artefacts — *test plans, sign-off records,
> defect logs* — and none is visible in BCU's public record, nor in the
> assessment corpus, nor in any vendor case study covering its core conversion.
>
> No *emissions baseline, reduction target or transition commitment* appears in
> BCU's annual report, its about pages, its news releases or the trade coverage
> of it.
>
> A **roadmap** in this domain would *sequence commitments against dates*, and
> BCU has no published commitments to sequence.

And the shape that was refused, from a payload built the same day:

> Strategy Refresh Cadence **was searched across the six mandatory public tiers
> for this entity and no entity-specific artefact naming the capability was
> returned**, so the score is carried by the category position.

Both report "nothing found". The first four name **the artefact that capability
would have left**, and it differs every time because capabilities differ. The
fifth names **only the outcome**, and the outcome is identical for all 400 cells
it was pasted under, so once the frame is stripped there is nothing left to tell
them apart. The rule in one line:

> **Name what you looked for, not that you looked.** The search protocol is the
> same on every cell; what it was hunting is not.

If a cell has nothing of its own to say even under that test, it is not a cell
with a thin argument — it is a cell with no argument, and route 1 above applies:
leave it out.

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

### CG-44 · a peer figure the assessment holds reaches the overview strip

Two halves, and the second is arithmetic.

**The cascade.** A heatmap that carries peer figures and an overview strip that
carries none is a page hiding what the assessment knows. Either the strip
carries them too, or the strip says WHY not — a named, readable reason, not a
null. Owner, 2026-08-23: the overview had no peer scores while the heatmap
underneath it did.

**The identity.** `delta` is not free text: it must equal `score − peer_median`
within **0.05**, and `direction` must agree with its sign. A delta that
disagrees with the two numbers beside it is worse than an absent one, because
a reader checks the subtraction and stops trusting the page.

Refused, not repaired: recompute the delta from the two figures you served
rather than adjusting either figure to fit a delta you already wrote.

### CG-45 · a card proposing a platform says how far the client already reaches into it

Every `platform_story.platforms[]` card and every `overview.opportunity.tiles[]`
tile carries a reach statement of at least **120 characters** under one of
`estate_reach` · `their_stack_context` · `current_estate`.

Owner, 2026-08-23: a platform recommendation ignored that the client *already
owns much of the platform being proposed*. A card that does not say what they
hold today reads as a greenfield pitch to someone who has already bought it.

**This gate must never push you into inventing utilization.** "They own the
licence; nothing observed says how much of it is switched on" is a complete,
passing reach statement. What is refused is silence about the estate, never an
honest statement that the estate's depth is unknown. Deployment counts,
seat counts and adoption percentages that no evidence carries are a separate
defect and AG-03 will take them.

### CG-46 · the issue register holds the institution's own matters

An issue is something that happened to the entity and bears on its scores —
an enforcement action, a breach, an arbitration award, a regulatory censure,
a news event. It is **not** an observation about the assessment: "the workbook
scores this cell thinly" is a note about our own working, and Gulf's register
was made of those.

The gate reads the SUBJECT keys (`title` · `summary` · `description` ·
`matter` · `name`) for assessment-shaped language, and refuses only when the
REASONING keys (`rationale` · `detail` · `impact` · `provenance` ·
`opened_on_basis`) carry no entity matter either.

That split is the whole gate, and it was learned by getting it wrong: the
first version read every key together and refused three genuine FINRA
arbitration awards on T. Rowe Price, because the word "workbook" appeared in
a `rationale` explaining how the row had been SCORED. Describing your own
method in the reasoning field is correct and stays passing. Putting your
method in the title is the defect.

### CG-47 · why_now's summary prose counts the signals it serves

Invariant 8: counts are computed, never stored where a source of truth exists.
A count written into a sentence IS a stored count, and it stops agreeing with
its own list the moment a signal is added or dropped.

Scoped deliberately to `overview.why_now`'s prose keys (`narrative_thread` ·
`synthesis` · `storyline`) against its `signals` array — nothing wider. A
whole-set adjective ("every", "all", "both", "each") is allowed, because those
stay true as the list changes; a numeral does not.

Write *"the signals below"*, not *"these four signals"*. The first version of
this gate was broader and produced four false positives on good prose across
thirteen sections; all four now ship as passing fixtures, which is why the
scope is one section rather than a principle applied everywhere.

### CG-48 · a value is refused at submit if its column cannot hold it

The writer registry maps every section field to a column with a type, and
`column_types.json` carries all 1,156 of them across 82 tables. A value whose
column cannot hold it validates at submit today and is discarded at promotion
tomorrow — the card renders empty under a real client's name and nothing
failed. MEM-0136 and MEM-0194, both BLOCKER, both this shape: a prose locator
went into `heatmap_focus_areas.source_page`, an INTEGER column.

Three families are checked — `numeric`, `boolean`, `dateish`. **A numeric
STRING is refused**: `"3.4"` is not 3.4, and the quote marks are how a value
that looks right on screen becomes null in the database.

### CG-49 · a client-visible absence does not name this system's machinery

Invariant 5 is default-deny redaction, and the serve layer honours it at KEY
grain: `reason`, `closure_condition`, `closure` and `kind` from an
`empty_state` reach the customer body intact. So an absence explained in terms
of OUR plumbing is a leak with a valid passport — it was allowed through by
name, not by accident.

Refused inside those keys: `MEM-`/`REF-` ids, gate ids, `CUSTOMER_WITHHELD`,
connector tool calls. All five promoted clients carried at least one.

Deliberately NOT refused: the plain words "gate", "connector", "staged". A
client-facing sentence may legitimately need one of them, and a gate that
refuses ordinary English teaches producers to fight it rather than read it.
Say what is missing and what would close it, in the client's terms.

### ET-02 · no id is invented in a minted namespace

The server allocates identifiers. An id shaped like one the catalogue or
`register_evidence` mints, that neither of them actually minted, is refused —
it would resolve to nothing while looking exactly like something that
resolves. This is the fabrication case, and it is why an id you cannot
account for is never worth guessing at: mint it, or cite the one you have.

### ET-03 · you create five id classes and no others

`ic_id` · `f_id` · `fa_id` · `ts_id` · `wn_id`, plus an authored `rec_id`.
Everything else comes from the catalogue or from `register_evidence`, which
dedups by content hash and computes the ERS server-side (a sent ERS is
ignored, not honoured). Reaching outside those five is how a payload cites an
evidence id that never existed — and fail-closed evidence means the citation,
not the run, is what breaks.

### CG-02 · a required field is present, or the section declares an empty state

There is no third option and there was never meant to be. A required field
that is simply absent is refused; a required field the run genuinely cannot
fill is satisfied by the section's `empty_state`. Leaving it out silently is
how a card renders blank under a real client's name with nothing having
failed.

### CG-03 · a value is the type the contract declares

Objects where the contract says object, strings where it says string, and the
same one level down for a list's items. It is the plainest gate in the set and
it fires more than any other, usually on a list whose items are the wrong
grain.

**What CG-03 cannot see, and never will:** a JSON-encoded object IS a valid
string. `'{"f_id": "F-1", "e_ids": ["E-CC-139"]}'` in a field the contract
declares as ids passes every type check in the module and reaches the client
as literal JSON inside a chip. That is why encoding has its own gate rather
than a widened CG-03. If the contract asks for ids, send ids; if it asks for
objects, send objects and let CG-03 check their type.

### CG-06 · an absence names its reason and what was searched

`empty_state` is not a flag. It carries a `reason` and a non-empty
`sources_searched` list, and an absence with no ladder is rejected. This is
the gate that separates *"I looked here, here and here, and there is nothing"*
from *"nothing came out"* — the distinction the whole build turns on. Compose
the reason for a client's eyes; CG-49 governs what may not appear in it.

### CG-07 · a figure quoted in prose resolves to a cell this run serves

Prose that names a pillar or category figure the run does not carry cannot be
checked by anyone, including the reader. The gate refuses the quotation rather
than the sentence: quote a grain the run serves, or drop the number and make
the qualitative claim.

### CG-08 · there is no fifth band

Invariant 6, enforced at submit. Four bands, strict less-than, on the raw
score: `<2 Activating · <3 Building · <4 Competing · ≥4 Differentiating`.
Anything at or above 4.0 is Differentiating — the resolver has four branches
and a fifth band word does not render, so a payload carrying one is refused
rather than silently dropped. M5 and "Transformational" must not exist in
code, enum or prose.

### CG-24 · `layers[].detected` equals what `items[]` actually holds

Invariant 8 again: `items` is the source of truth for `detected`, so the count
is computed and never asserted. Measured 2026-08-18 on a promoted register —
operations served **0 detected against 7 expected while carrying 6 named
products**, because `detected` counted only CONFIRMED and INFERRED rows. That
is the figure that reads to a client as "no tech stack". Count what you
served, and let the status field carry the confidence.

### CG-25 · one card per argument

Nothing deduplicates insight cards anywhere downstream — the adapter is a
straight `.map`, so a card written twice renders twice and counts twice
toward a headline the reader takes on trust. Two cards making one argument
with different wording are one card; write it once, with the stronger
evidence.

### CG-42 · a recommendation names an area the page can join on

The platform page has no id joining a card to a recommendation. It joins on
ONE string — the L3 area label with the `[L3-…]` code stripped and
normalised — so a recommendation naming an area no card carries renders
detached from the story it belongs to. Use the label the card uses.

### CG-43 · the Context grid and the Overview bars are one dataset

The contract says it outright: the grid is *a re-projection of the same
dataset the overview renders as bars*, so the two cannot disagree. A client
reading both sees the contradiction immediately, and it is the cheapest
possible loss of trust. Re-project; do not re-derive.

### ET-08 · a cell-link field carries a cell id, or names nothing

Deliberately narrow: it fires only on a key this connector already treats as
a cell link, and only on a non-empty string that is not a cell id. An empty
value is CG-02's business, not this gate's — the two do not both report one
absence.

### CG-50 · the product a row names appears in the span it cites

MEM-0129, BLOCKER. A producer read a truncated excerpt, reached past the cut
into the scan summary it remembered, and named **nine products the citable
spans do not contain**. Substring-testing all fourteen rows against their own
cited excerpts: nine present in zero of them. Repairing the register against
that test took it from 41 rows to 27, CONFIRMED from 9 to 3, and removed the
run's entire security-tooling incumbency story — a story that had never been
there.

The finding made this a producer HABIT: *"substring-test every product name
against its own stored excerpt before citing it."* A habit is not a control.
It was written on 2026-08-21 and a run promoted the next day with 95% of its
client-facing evidence clipped, because nothing checked.

**What it checks:** does the span you cited contain the name you asserted?
Not whether the client really runs the product — no gate can know that.

**Matching is by distinctive token OR multi-word phrase**, so correct work
passes. An excerpt saying *"Financial Services Cloud"* corroborates a row
named *"Salesforce Financial Services Cloud"*, and the vendor counts too:
"Fiserv" in the excerpt corroborates a Fiserv product whose own name is
entirely generic. Generic words alone never corroborate — a match on "Cloud"
proves nothing.

**ABSENT rows are exempt.** Evidence of absence rarely names the absent
product, and refusing those rows would push you to delete honest ABSENT rows
rather than record them — trading a documented gap for a silent one.

**Three outcomes, kept apart:**

| What happened | What the verdict says |
|---|---|
| the name or its vendor appears | pass |
| no cited excerpt contains it, and one is a HARD CLIP | fix the STORE — re-ingest with whole spans. Rewriting the row against a truncated excerpt loses a product they may really run |
| no cited excerpt contains it, none truncated | fix the ROW — cite the source that does, or move it to `dropped[]`. *An item you cannot cite is a rumour*, in the contract's own words |

A row whose ids resolve but carry **no excerpt** is refused with its own
reason. That is deliberate: MEM-0129's nine looked exactly like rows that had
passed, so "could not check" is never reported as "checked and fine". An id
that does not resolve at all is ET-04's business and this gate stays quiet.

**Measured on the live corpus, 2026-08-24, 80 promoted rows across three
clients.** T. Rowe's repaired register passes 27 of 27 — the gate agrees with
the hand repair exactly. Gulf refuses 15 and Logix 2, and every one is real:
Gulf cites `E-CC-224`, a 258-character WCAG accessibility statement from its
privacy policy, on **twenty** rows including Salesforce CRM, Pardot, HubSpot,
Cloudflare and GitHub; Logix's Marketo Engage row cites a technographic list
that does not contain Marketo. Zero false positives.

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
