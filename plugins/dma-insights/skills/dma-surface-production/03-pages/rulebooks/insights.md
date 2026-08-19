# Rulebook: insights · v2 (2026-08-19)

The insights page's anti-pattern rulebook: what a promoted insights page looks
like when it is right (Baxter, run `c1351d25`) and the named, measured failures
that reached a rendered page (Logix, run `d7ed1d90`, and the memory findings
behind each entry). The **insights producer reads it before authoring, as
Method step 2**, alongside `get_memory_digest` + `search_findings`; the
**rectifier is its only writer** — an edit with no finding behind it is an
opinion. Entries flagged by a USER or REVIEWER are **PERMANENT and never
retired**. Baxter is **v5.0-shaped — 17 categories including P1C5, 706 cells —
so every shape-specific count quoted from it (8 cards, tiles 16/30/2/3) is a
v5.0 fact of that run, not a contract**; a v7.0 run (16 categories) has its own.

---

## I1 · Insight cards

### Baxter positive pattern

The promoted Baxter page carries 8 cards, and the shape to copy is the JOIN —
each card sets two sources that sit apart against each other and argues the
gap between them:

> "Member advocacy is exceptional — a net promoter score near 80 against a
> sector average in the thirties — while the public review record concentrates
> on one theme: holds on mobile deposits and freezes triggered by fraud
> controls. Both readings are about the same members in the same period."
> (IC-1 `what_text` — an advocacy measure joined against a review record; this
> is the card the reviewer ACCEPTED: "Verified end to end: the reasoning trace
> holds", dma@zennify.com, 2026-08-08)

> "Active engineering recruitment names senior Salesforce and cloud-DevOps
> roles, while the technology profile confirms no integration platform across
> an estate of more than two hundred systems, with a single general-purpose
> automation tool carrying point-to-point connections."
> (IC-3 `what_text` — a job posting joined against a technographic profile;
> its title, "The hiring plan is buying integration by hand", is the argument
> in a phrase, not a capability name)

> "It converts a genuine strength into member friction at money-movement
> moments, the highest-stakes interactions the institution has."
> (IC-1 `severity_rationale` — severity argued by CONSEQUENCE; nothing in it
> is a score or a distance from a median)

> "The most likely benign reading is that these detections are crawl residue
> or isolated test estate rather than production surface — which is precisely
> why the scope question is worth asking rather than assuming either way."
> (IC-4 `alternative_explanation` — the r_layer verdict on this card is
> UNCERTAIN, and it ships anyway: alternative stated, confidence MEDIUM,
> the card reframed as a scope question rather than an exposure claim)

Shape notes, measured on the promoted body: every title is ≤10 words and
falsifiable; no `what_text` opens with a score read-out; severity is 3
critical / 5 high, each with a consequence argument; `supporting_e_ids` is
non-empty on 8 of 8 cards (1–4 ids each); `confidence` tracks the r_layer
verdict (UNCERTAIN → MEDIUM, never hidden); every `validation_question` names
an internal artefact (fraud-hold volumes with false-positive rate, the
point-to-point integration inventory, the CaseHUB-equivalent data dictionary).
Five of eight cards anchor in P4 — no one-card-per-pillar symmetry, because
"eight cards about two pillars is itself a finding about the client".
`pillar_id` is null on 8 of 8 and no `theme` key exists anywhere. The one
blemish is the pattern's own caveat: IC-2 was reviewer-REJECTED (MEM-0017,
below) — copy the page minus that card's counter-case shape.

### Anti-patterns

- **MEM-0017 / REVIEWER reject on D1 insights** — a counter-case asserted
  rather than tested — measured: reviewer dma@zennify.com rejected Baxter
  IC-2 (run `c1351d25`, annotation 2) with "the counter-case is asserted
  rather than tested"; the card's r_layer dismissed its strongest objection
  ("the measured Agentforce outcomes are strong") as "scope-limited" without
  a probe that could have falsified the dismissal — the rule: every r_layer
  `counter` names the test it survived — a probe run, a query issued, a source
  checked; "rejected because X" with nothing run behind X goes back to the
  desk, and an untestable counter caps the card at MEDIUM with the ambiguity
  stated. **PERMANENT — never retire.** Test: the reject-to-finding loop is
  pinned by `apps/mcp/tests/test_reviewer_feedback.py::test_a_reject_raises_a_finding_carrying_the_card_and_its_r_layer`;
  the claim-shape rule itself (a counter must be tested, not asserted) —
  test: MISSING — corpus entry open.
- **MEM-0013 / WRITE_PATH_WITH_NO_READ_PATH** — the Accept/Reject pair on
  every card wrote nothing and could be read by nobody — measured 2026-08-08:
  0 readers · 0 rows · 8 Baxter cards rendering the control (closed by
  REF-0007: a read half plus a connector consumer that turns every verdict
  into memory carrying the card's own text and its r_layer) — the rule for
  the producer: the card is the unit a reviewer adjudicates, and a verdict
  comes back as memory verbatim; write each card — including its r_layer — as
  the thing that will be read back to you, because since REF-0007 it is.
  **PERMANENT — never retire.** Test:
  `apps/api/tests/test_annotation_feedback.py::test_the_read_returns_verdicts_with_their_actor`
  and `::test_latest_verdicts_is_the_shape_the_card_adapter_needs`.
- **S28_insight_integrity / AG-03 / AG-01** — a card with a dead anchor, an
  empty citation list, or no recorded reasoning — measured: dead
  `linked_subcap_id` links were 15 of 119 in the corpus (the count is carried
  in the I1 contract itself), and the serve layer excludes uncited cards —
  the rule: `linked_subcap_id` resolves to a cell THIS run serves, preferring
  a cell an O6 finding also links (that overlap is the theme lens);
  `supporting_e_ids` is non-empty per card because AG-03 fires per ITEM and
  the section envelope does not stand in; `r_layer` is recorded per card
  `{hypothesis, counter, domain_test, probes_run[], verdict, confidence}`
  because a card ranks by severity and asserts a mechanism, so AG-01 blocks
  it bare. Zero cards on a completed run is a failure state, not an empty
  state.
- **(no MEM) / contract fork: `theme` or `pillar_id` sent** — two answers to
  one question — measured: Logix (`d7ed1d90`) sent `pillar_id` on 8 of 8
  cards ("P3", "P4", "P2") where Baxter sends null on 8 of 8; `theme` has no
  I1 field at all — the rule: send neither; the app derives the theme from
  the O6 finding sharing the card's cell and reads the pillar from the cell
  id's leading token (`P4C1.3.1` → `P4`). CG-04 refuses `theme` as an unknown
  key; `pillar_id` is a legal column nothing refuses, so this rulebook is the
  only guard on it.
- **(no MEM) / 9-antipatterns §9 — an absence explained instead of removed** —
  an empty_state riding a full section as bookkeeping — measured: Logix
  `insights.empty_state` sat beside 8 served cards with reason "All eight
  cards are served… This state exists to carry the section's citation
  disclosure", closure_condition "Not applicable", and a disclosure paragraph
  packed into `sources_searched` — the rule: `empty_state` exists for absence
  and a populated section sends none; a citation disclosure is not a search
  ladder; and because `empty_state.reason` / `closure_condition` serve to the
  CUSTOMER (the probe keys around them do not), bookkeeping prose written
  there renders on the client's own dashboard.
- **MEM-0093 / CG-27 + CG-29 (9-antipatterns §4, §4b)** — abbreviation and
  duplicate-thread debt, paid at the worst moment — measured: a two-field
  re-promote of Baxter was blocked by 37 CG-27 refusals plus 14 word-for-word
  duplicated narrative_threads accumulated in pre-gate content — the rule:
  spell out every abbreviation on first use in each field (never inside a
  verbatim quote or excerpt span — expanding inside a span misquotes the
  source); and this page's two `narrative_thread`s each say what their own
  section adds — the insights thread argues the cards, the landscape thread
  argues the recount, and neither repeats the other or any other page's.
- **(no MEM) / AG-12-family: S2_accusatory (9-antipatterns §2)** — client
  prose that opens on an accusation — measured in the corpus: "What it cannot
  do is answer a question." / "You do not measure contact-centre deflection."
  — the rule: the client reads `what_text`, `so_what_text` and
  `validation_question`; state every gap from the opportunity end, and
  remember the follow-up is part of the opener — a consultative claim whose
  validation_question is "why do you not track that?" is still an accusation.
- **(no MEM) / 9-antipatterns §7 — a field written as metadata** — reasoning
  written, stored, served — and displayed by nothing — measured on a promoted
  run before the renderer caught up: `severity_rationale`,
  `alternative_explanation`, `validation_question` and `claim_label` were all
  present and nothing displayed them, which is the entire substance of a page
  being read as shallow — the rule: all four now render (beside the severity
  chip, under the claim, as the modal's closing line, on the card face), so
  write every card field as prose a client is reading, because one is.

### Exclusion set

The customer body of `insights.insights` is exactly the generated allowlist's
enumeration — section keys `cards`, `e_ids`, `empty_state`, `internal_only`,
`narrative_thread`, `produced_at`, `producer_version`, and the 17 enumerated
card keys; anything else drops at the serve boundary, and an unknown key never
gets that far because CG-04 refuses it at submit. Within that:

- **`r_layer` reaches no audience** — it is in `NEVER_SERVED_KEYS`, stripped
  at any depth for EVERY audience. It is still mandatory at submit (AG-01)
  and it is what the reviewer loop reads back (MEM-0013/MEM-0017), so write
  it fully — for the audit and the reviewer, never for the reader. Mark every
  `cards[*].r_layer` path in `internal_only` as Logix did (8 paths); marking
  is mandatory (invariant 5) and the server strip is the backstop, not the
  licence.
- **Probe ladders never serve**: `sources_searched`, `queries_run`,
  `searched_on` are customer-stripped by class (measured serving before the
  boundary existed: `searched_on` in 20 empty_states run-wide).
  `empty_state.reason` and `closure_condition` DO serve — a producer's real
  reason renders, a probe never does (owner adjudication 2026-08-14) — so a
  reason must read as information about the institution, never as our
  workflow.
- **Method vocabulary never rides a card**: `tier`, `ers`, `recency_band`,
  `discovered_by`, `provenance`, `link_basis` are customer-stripped keys, and
  their words do not belong in card prose either — where a card states how
  much it rests on, the number is the length of its citation list (AG-02),
  never a tier code or a rank score.
- **Cap vocabulary must not exist here**: `cap_level`, `ceiling`,
  `uncertainty_band`, `urf_modifiers` are excluded by class, and M-codes must
  not appear in any card's prose (charter invariant 6 — the four bands are
  the only maturity words).
- **Contact routes are stripped by key at any depth** (`email`,
  `linkedin_url`, `phone`, `contact_email`, `direct_line`, `mobile` —
  MEM-0045 measured them serving on a named executive): `so_what_text` names
  an owner by seat and title, never a route to an inbox; and
  `storyline_challenge`, `enrichment_basis`, `enriched_at` are
  customer-stripped — never describe a person in an enrichment tool's words.

### Enrichment pathways

Connector pathways: no ledger facet is registered for I1 (the surface map's
dash) — a card's enrichment travels the evidence ladder and exists only as
registered evidence, entered through `register_evidence` citing the SOURCE a
tool surfaced, never the tool. What the connectors feed is the JOINS: the
`sentiment` facet (`first_party` published ratings carrying n, scale and
date, T1-T2; `clay` news sentiment T3 — Glassdoor, Indeed and ZipRecruiter
all 403, so that value is an inference with its route named, or omitted) is
one half of IC-1's advocacy-against-review-record join; the `techstack`
facet (`explorium` ingest scan and the `clay` Tech Stack data point, both
T1, never T4 — the misfile caps the capability at L2.5) plus `clay` Open
Jobs (T2-T3 — the posting is first-party, the aggregator is not) are the
two halves of IC-3's hiring-against-technographic join; `clay` Recent News
(T3) and Latest Funding (T1-T2 only when a filing is behind it) feed the
timing joins, per `02-inputs/clay_taxonomy.json`. Per the pack's Information
sources table, the argument itself comes from the assessment report deep
dives and the research workbook; `supporting_e_ids` from the workbook plus
enrichment.

Web-search pathways (the dma-research discipline — five signal facets per
claim, proxy escalation before any absence — applied to this page's known
gaps):

- `"[Entity] [area] failure complaint outage criticism"` — the mandatory
  per-card contradictory query (R-Layer step B). A hit registers at its
  source's tier (a regulator record T1, trade press T3) with a verbatim
  50–500 char span; a miss is a rung in the card's `r_layer`, never an
  evidence row (W6: an absence enters as INFERENCE with its ladder where it
  enters at all).
- `"[Entity] [platform] administrator OR engineer job posting 2025 2026"` —
  the demand-signal half of a join: the posting is first-party T2, the
  aggregator T3, and it licenses "signals suggest", never "uses".
- `"[Entity] CFPB OR BBB complaint [product or channel]"` — the complaint
  TEXT is the analysable half of a CX join, T3; the excerpt is the verbatim
  narrative span, checked against THIS entity (the same-named-institution
  probe fires here).
- `"[Entity] [regulator] enforcement OR consent order 2024 2025"` — the
  Regulatory Divergence probe's search; T1 when it lands on the regulator's
  own record.
- `"[Entity] [claimed initiative] paused OR completed OR replaced OR
  delayed"` — the Temporal Inconsistency probe; whatever it finds registers
  at its source's tier, and nothing found is a ladder rung in the r_layer.

Query rules held from dma-research: entity name in every query, 4–8 words,
year markers in two-plus; a vendor case study naming the entity is T5 with
corroboration required (W6) and cannot carry a card alone. A card upgraded
from thin to cited is the highest-value work on this page.

Gap-to-pathway: `cards` is this section's only contract field, so the
worklist can raise exactly one row here — `empty_required` on `cards` — and
it names a failure, not a search: zero cards on a completed run closes by
authoring from the joins above, never by declaring an empty state. Per-card
holes (an empty `supporting_e_ids`, a bare causal claim) never reach
`list_enrichment_gaps` — AG-03 and AG-01 refuse them at submit, which is the
guard the worklist does not need to be.

## DD-3 · Insight modal (drilldown from I1)

The four-tab modal an I1 card opens (Drilldown atlas: DD-3, component
InsightModal, centred shell). It renders `insights.insights.cards[*]` and has
no payload of its own — the card face already showed title, flag, pillar and
a truncated WHAT, and the modal completes it rather than repeating it. The
spec's DD-3 shape adds `affects[]` and `linked_rec_id` to the I1 prompt
shape; both are legal card columns and both serve. An evidence chip inside
the modal opens DD-2 above it — that drawer's rules are
`rulebooks/heatmap.md § H6`.

### Baxter positive pattern

> "Those same controls decide on the member context available to them today,
> so legitimate activity trips them, and the cost lands precisely at the
> moments a member is trying to move money."
> (IC-1 `why_text` — the mechanism tab: the causal path from the claimed
> state to its consequence, not a restatement of the WHAT above it)

> "Can we see the last two quarters of fraud-hold volumes with their
> false-positive rate, and the servicing contacts they generated?"
> (IC-1 `validation_question` — the modal's closing line: a discovery
> question naming the internal artefact that would confirm or kill the card)

The modal-only columns have their exemplar on Logix, not Baxter:

> `"affects": ["P2C3.2.6", "P2C3.2.1", "P2C3.2.2", "P2C3.2.3", "P2C3.2.CU1",
> "P2C3.7.3", "P2C3.5.5", "P2C3.6.5"]`
> (IC-005 — the tab's cell chips: eight cells THIS run serves, the
> sub-vertical variant included; every chip resolves or the card carries a
> dead link)

Shape notes, measured: Baxter serves `affects: null` and `linked_rec_id:
null` on 8 of 8 cards — on that run the modal renders its cell chips from
`linked_subcap_id` alone. Logix populates `affects[]` on 8 of 8 and sets
`linked_rec_id` on 3 of 8 (REC-2 once, REC-4 twice) — the cross-page pointer
into P2's recommendations is set where a recommendation actually descends
from the card, never for symmetry, and null is its ordinary value.

### Anti-patterns

- **MEM-0017 — pointer to I1** — the counter-case tab is where the reject
  landed: `alternative_explanation` is the tab's reason to exist, and IC-2's
  r_layer dismissing its strongest objection untested is what came back as
  memory. Every counter names the test it survived; the modal is where the
  reviewer reads it, and since REF-0007 where the verdict returns from.
- **(no MEM) / 9-antipatterns §7 — pointer to I1** — the four fields this
  modal renders (`alternative_explanation` under the claim,
  `validation_question` as the closing line, `severity_rationale` beside the
  chip, `claim_label` on the face) are the same four that were once written,
  stored, served and displayed by nothing. The modal is the read path that
  made them prose; write them as prose.
- **(no MEM) / contract fork at the modal boundary** — the spec's DD-3 block
  names `flag` and `pillar` among what the face "already showed"; both are
  render derivations (`severity` → triage flag, pillar from the cell id's
  leading token), not submit keys. `flag` falls to CG-04 as unknown;
  `pillar_id` is the legal column nothing refuses — Logix sent it on 8 of 8
  where Baxter sends null on 8 of 8, and the I1 entry above is the only
  guard. `affects[]` ids must each resolve to a served cell — the dead-link
  class was 15 of 119.
- **(no MEM) / S2 in the closing line** — the `validation_question` is the
  modal's last word to the client; a claim whose follow-up reads "why do you
  not track that?" is an accusation wearing a question mark. State the
  question from the opportunity end and name the document, not the omission.

### Exclusion set

I1's boundary, rendered: the customer body of each card is the allowlist's
17 enumerated card keys — `affects` and `linked_rec_id` are among them and
serve — minus `r_layer`, which is in `NEVER_SERVED_KEYS` and reaches no
audience even though this modal is where its verdict comes back as memory
(MEM-0013). Method vocabulary, cap vocabulary and contact-route keys drop at
any depth, so the owner `so_what_text` names is a seat and a title, never an
inbox. The modal adds no key of its own; the evidence drawer it opens is
DD-2, whose exclusions are H6's.

### Enrichment pathways

Connector pathways: the parent's — no facet of its own; every chip and tab
renders content I1 already cites, and nothing is fetched at click time
(invariant 1). The modal is only ever as good as the joins and citations
established at synthesis.

Web-search pathways: the tab-shaped gaps, all of them I1 searches run before
the card ships — the counter-case tab needs the mandatory contradictory
query (`"[Entity] [area] failure complaint outage criticism"`), because an
`alternative_explanation` written without one is an assertion, which is
MEM-0017's shape; each probe the card's r_layer names (Input-Output
Disconnect, Marketing-Reality Gap, Temporal Inconsistency, Regulatory
Divergence, CX Disconnect, Peer Outlier, Tech Stack Mismatch) fires a
required extra search before the modal may open on the result. A negative
return is an r_layer rung, never an evidence row (W6).

Gap-to-pathway: none of its own — the worklist sees I1's `cards`
(`empty_required`) whole, and a hole inside a card is invisible to it. The
submit gates (AG-01, AG-03, S28_insight_integrity) and the post-promote
readback are the only checks that see this modal's content.

## T2 · Technology landscape strip

### Baxter positive pattern

> `{"kind": "GAPS", "basis": "3 · T2-T3 evidence", "count": 3, "detail":
> "Searched and not found at this layer.", "named_items": ["MuleSoft Anypoint
> Platform", "Salesforce CRM Analytics", "Salesforce Data Cloud"]}`
> (the GAPS tile names its platforms — a gap count with no names is
> unactionable, and the reader's next question is always "which")

> `{"kind": "CLAIMED", "basis": "2 · T3-T5 evidence", "count": 2, "detail":
> "Stated but not corroborated; treated as absent for fit.", "named_items":
> ["Apple Pay", "Google Pay"]}`
> (a short list is named even off the GAPS tile; the `detail` says what the
> status costs, not what the producer did)

> "The counts are recomputed from the register rows on every read, never
> stored, so this strip and the register cannot drift apart."
> (from the landscape `narrative_thread` — the section stating its own
> invariant-8 discipline instead of restating the tiles)

Shape notes, measured: four tiles, 16 + 30 + 2 + 3, summing to that v5.0
run's register (the numbers are Baxter facts, not targets); every one of the
four tiles prints a `basis` in the "N · tier mix" form; `named_items` is
empty on CONFIRMED (16) and INFERRED (30), where the lists are too long to be
useful, and populated where they are short; `reconciles_to_register` is true
and no `summary` key was sent. An honest extreme of the same pattern is on
the Logix run: a CONFIRMED tile of 0 with basis "0 · no T1 or T2 source on
this run names a technology" — a zero with its basis printed is a statement
about the run's evidence, and raising a row instead would let confidence
stand in for evidence.

### Anti-patterns

- **MEM-0046 / COMPOSED_VALUE_ASSUMES_ITS_INPUTS_ARE_DISJOINT** — the vendor
  name printed twice on a client-facing tile — measured 2026-08-09 on the
  Baxter customer body: the GAPS tile's `named_items` served "Salesforce
  Salesforce Data Cloud", "Salesforce Salesforce CRM Analytics", "MuleSoft
  MuleSoft Anypoint Platform" (3 of 3 duplicated), and the same expression
  gave "Snowflake None" for a vendor-only row; fixed at read by REF-0020's
  `_product_label` — the rule: a named item carries its vendor exactly once;
  keep vendor and product name disjoint in the register rows the strip
  recounts, and never let a None reach a label. Test:
  `apps/api/tests/test_computed_at_read.py::test_the_gaps_tile_does_not_say_the_vendor_name_twice`.
- **(no MEM) / AG-02, invariant 8 — a count asserted, not counted** — the API
  recomputes the four tiles from the register at read
  (`apps/api/tests/test_computed_at_read.py::test_landscape_recomputes_from_the_register_and_says_whether_it_reconciles`),
  so a stored count that disagrees with the register is exposed on the page,
  not hidden by it — the rule: produce T2 only after T1 is settled, and if
  the register changed, recount — never adjust; the four counts must sum to
  the register's row count, and `reconciles_to_register` is the record that
  you recounted ("the assertion, not the counts" —
  `apps/mcp/tests/test_field_census.py:64`).
- **(no MEM) / the pack's named characteristic defect** — a tile with a count
  and no basis — a bare count invites a certainty the evidence does not
  carry; measured positive on both reference runs: 8 of 8 tiles print a
  basis in the "N · tier mix" form — the rule: `basis` states what kind of
  count this is ("5 · T1-T3 evidence"), `detail` gives the reader one line to
  act on (what the rows share, or what would move them to a firmer status),
  and the GAPS tile always fills `named_items`.
- **MEM-0010 / CG-09 (RECURRED)** — an enum-shaped field written with prose —
  measured: a contract pipe-vocabulary field served a sentence
  ("strategy-first, substrate-later" against a five-value vocabulary) because
  TEXT columns store sentences happily and the filter, legend and colour rule
  reading the field then match nothing — the rule here: `tiles[].kind` is
  exactly one of `CONFIRMED │ INFERRED │ CLAIMED │ GAPS`, and every register
  row's status is exactly one of `CONFIRMED │ INFERRED │ CLAIMED │ ABSENT`
  (CG-09, plain TEXT, exact case) — a strip over a register with one
  off-vocabulary status cannot be recomputed at all.
- **(no MEM) / CONTRACT_FIELD_DISCARDED_AT_PROMOTION shape:
  `landscape.summary`** — a summary written into a deliberately unbound
  column — the column exists because its DDL comment imported T1's summary
  across a page boundary; the corpus's one summary line belongs to the
  TECHSTACK page, a summary written here is discarded at promotion, and
  neither reference run sent one (the serve allowlist for
  `insights.landscape` carries no `summary` key) — the rule: never emit it;
  the strip's one line of prose is its `narrative_thread`, and it argues the
  recount.

### Exclusion set

The customer body of `insights.landscape` is exactly the allowlist's
enumeration — `tiles` (items: `kind`, `count`, `basis`, `detail`,
`named_items` only), `reconciles_to_register`, `e_ids`, `empty_state`,
`internal_only`, `narrative_thread`, `produced_at`, `producer_version` — plus
`r_layer`, which the allowlist carries and the serve layer then strips for
every audience. Within that:

- **`r_layer` reaches no audience** but is worth writing at section level
  here: the Logix strip's r_layer defends its zero-CONFIRMED tile and records
  the recount probes, and that is exactly what an auditor needs. Mark it in
  `internal_only` (`["r_layer"]`, as Logix did); the strip is the backstop.
- **Probe ladders never serve** (`sources_searched`, `queries_run`,
  `searched_on`): the searches that established a GAP belong in the register's
  evidence rows and the run's ladders, never in tile `detail` or `basis`
  prose. The `basis` line's tier mix ("3 · T2-T3 evidence") is the contract's
  sanctioned client-facing statement of evidence kind — that is the ONLY
  method vocabulary this surface carries; `tier`, `ers`, `recency_band`,
  `discovered_by`, `provenance` and `link_basis` as keys are
  customer-stripped by class and must not be added to tiles or named items.
- **No cap vocabulary, no contact keys, no `summary`**: `cap_level`,
  `ceiling`, `uncertainty_band`, `urf_modifiers` and the contact-route keys
  have no business on a recount strip and are stripped by class anyway;
  `summary` is unbound and discarded (above) — never emit any of them.

### Enrichment pathways

Connector pathways: none of this section's own — the strip is a recount, and
the split is deliberate: T2 renders on the insights page while every input it
counts lives in the techstack register, so its data needs are T1's (the
surface map records the facet as "— (techstack, via T1)"). That facet, per
`02-inputs/enrichment_sources.json`: the `explorium` ingest scan (T1, wired
but not live — the routine records NOT_RUN until the credential exists), the
`clay` Tech Stack data point (T1 — a machine technographic scan is T1, never
T4; the misfile caps the capability at L2.5), then `first_party` platform
statements (T1-T2). Close a tile by closing register rows on the techstack
page, then RECOUNT here; no pathway writes a tile directly. The `basis` tier
mix is read off the counted rows' own evidence, which is the only method
vocabulary this surface carries (Exclusion set, above).

Web-search pathways (run against T1's rows; named here because these are the
searches that move a tile):

- `"[Entity] [gap platform] deployment OR selection announcement"` — a GAPS
  `named_item` is a searched absence: a hit converts the register row, the
  GAPS count falls and the strip is recounted, never adjusted. The negative
  return lives in the row's basis and the run's ladder — a negative search
  is a ladder rung, never an evidence row (W6).
- `"[Entity] [claimed product] integration OR go-live 2024 2025"` — the
  CLAIMED tile's move to a firmer status needs a second registrable domain
  or a T1-T2 single source (D4 rule 2); the institution's own page is
  T1-T2, the wallet vendor's is vendor collateral at T5 with corroboration
  required (W6).
- `site:[entity domain] [product]` plus a live technical read of the domain
  — first-party detection, T1-T2, the cheapest CONFIRMED there is; register
  the page with a verbatim 50–500 char span before the row changes status,
  because the tile's basis will count it.

Gap-to-pathway: this section emits `empty_required` on `tiles` only;
`reconciles_to_register` is a boolean, and a boolean's absence is its value —
never a worklist row. A strip that disagrees with the register is not a gap
either: the API recomputes the four counts at read and exposes the
disagreement, and the closure is a recount, not a search.
