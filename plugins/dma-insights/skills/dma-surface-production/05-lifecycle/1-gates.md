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
at submit time on 2026-08-08, one of them after building all 708 cells. Read
`gates/CG-15.md` **before** you write prose, and run that script before you
write the twenty-first.

## The gates that block most often

These are the ones a submission actually dies on, so they are named here rather than left
to be discovered from a verdict.

Each has its own file under `05-lifecycle/gates/` — read the ones your reading
order names before you write, and any other when a verdict names it. Nothing
here needs the whole book up front.

| Gate | What it asserts | Deep dive |
|---|---|---|
| `AG-03` | every claim-bearing item cites evidence | `gates/AG-03.md` |
| `CG-15` | a payload that says nothing | `gates/CG-15.md` |
| `CG-09` | a closed vocabulary takes one of its values | `gates/CG-09.md` |
| `AG-04` | a named peer's technographics carry their source | `gates/AG-04.md` |
| `ET-04` | a cited id resolves to a row that carries its excerpt | `gates/ET-04.md` |
| `ET-05` | a run cites only its own sub-vertical's variant cells | `gates/ET-05.md` |
| `CG-10` | a date that could not be established says so | `gates/CG-10.md` |
| `CG-11` | prose begins as a sentence | `gates/CG-11.md` |
| `CG-12` | a face field is a label, not a paragraph | `gates/CG-12.md` |
| `CG-14` | a linked cell exists on this run | `gates/CG-14.md` |
| `CG-13` | every required field has somewhere to live | `gates/CG-13.md` |
| `SG-S8` | sentiment rests on more than one line | `gates/SG-S8.md` |
| `CG-44` | a peer figure the assessment holds reaches the overview strip | `gates/CG-44.md` |
| `CG-45` | a card proposing a platform says how far the client already reaches into it | `gates/CG-45.md` |
| `CG-46` | the issue register holds the institution's own matters | `gates/CG-46.md` |
| `CG-47` | why_now's summary prose counts the signals it serves | `gates/CG-47.md` |
| `CG-48` | a value is refused at submit if its column cannot hold it | `gates/CG-48.md` |
| `CG-49` | a client-visible absence does not name this system's machinery | `gates/CG-49.md` |
| `ET-02` | no id is invented in a minted namespace | `gates/ET-02.md` |
| `ET-03` | you create five id classes and no others | `gates/ET-03.md` |
| `CG-02` | a required field is present, or the section declares an empty state | `gates/CG-02.md` |
| `CG-03` | a value is the type the contract declares | `gates/CG-03.md` |
| `CG-06` | an absence names its reason and what was searched | `gates/CG-06.md` |
| `CG-07` | a figure quoted in prose resolves to a cell this run serves | `gates/CG-07.md` |
| `CG-08` | there is no fifth band | `gates/CG-08.md` |
| `CG-24` | `layers[].detected` equals what `items[]` actually holds | `gates/CG-24.md` |
| `CG-25` | one card per argument | `gates/CG-25.md` |
| `CG-42` | a recommendation names an area the page can join on | `gates/CG-42.md` |
| `CG-43` | the Context grid and the Overview bars are one dataset | `gates/CG-43.md` |
| `ET-08` | a cell-link field carries a cell id, or names nothing | `gates/ET-08.md` |
| `CG-50` | the product a row names appears in the span it cites | `gates/CG-50.md` |

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

---

<!-- generated:gate-census BEGIN — edit gen_gates_md.py, not this -->

## Every gate, by id

The registry holds **83** gates. This census is generated from `apps/mcp/dma_mcp/gates.py` by `plugins/dma-insights/scripts/gen_gates_md.py`, so a gate cannot exist in the connector and be absent here. The sections above go deeper on the ones that block most often; this table is what you read when a verdict names an id you have not seen.

When the row below is not enough, the connector will explain itself: `explain_gate(gate_id)` returns the registry's own wording plus the threshold history. A verdict also carries the JSON path it fired on, so the repair routes from the path through `05-lifecycle/routing.md` to the owning per-surface producer without needing this file at all.

### CG · Corpus / contract (60)

| Gate | What it asserts | On failure | Deep dive |
|---|---|---|---|
| `CG-01` | **Required section present.** Every required section of the page carries a payload object. | block | — |
| `CG-02` | **Required field present.** Every required field of a section is present and non-null; an explicit empty state passes where the contract allows one. | block | `gates/CG-02.md` |
| `CG-03` | **Field type agreement.** Every field matches its contract type (list/object/scalar), list items included. | block | `gates/CG-03.md` |
| `CG-04` | **No invented fields.** No field outside the section contract, envelope included. | block | — |
| `CG-05` | **Envelope complete.** produced_at, producer_version, e_ids[], internal_only[] on every section. | block | — |
| `CG-06` | **Absence carries its ladder.** empty_state names its reason and sources_searched. | block | `gates/CG-06.md` |
| `CG-07` | **Quoted figure resolves to its cell.** Every quoted score resolves to the named served cell within 0.05, label and figure read from one row, rounded once. | block | `gates/CG-07.md` |
| `CG-08` | **Band word from the raw score.** Band words resolve from the RAW score at the four strict boundaries (<2, <3, <4, >=4); no fifth band exists. | block | `gates/CG-08.md` |
| `CG-09` | **Enum-column value.** A field promoted into an enum column carries one of that enum's values; a value the enum rejects type-checks as a string and then aborts the promote transaction. | block | `gates/CG-09.md` |
| `CG-10` | **A date that could not be established says so.** An item's own dating field (the timeline's event_date, the register's opened_on, a signal's dated_on, a firmographic as_of) is either a date or an explicit absence rung — UNVERIFIED / WORKED_ABSENT / undated on a recency or basis key, a… | block | `gates/CG-10.md` |
| `CG-11` | **Prose begins as a sentence.** A prose field on a client surface — a prose-keyed field, or any string that ends in terminal punctuation — begins with a capital. A first word carrying an uppercase letter after its first character (nCino, iOS, eBay) is the vendor's own… | block | `gates/CG-11.md` |
| `CG-12` | **A face field is a label, not a paragraph.** A field that renders in a chip, badge or single-line slot stays inside its contract's stated budget (window 20-40 words, trigger 25-45, detection_basis one clause of 160 characters, a landscape tile detail 90, a client-visible… | block | `gates/CG-12.md` |
| `CG-13` | **Every required field has somewhere to live.** Build-time census: each required contract field is bound by its section's writer, or is named in the computed-at-read register with the source it is recomputed from. | block | `gates/CG-13.md` |
| `CG-14` | **A linked cell exists on this run.** Every `*subcap_ids` link and every `subcap_id` scalar resolves against the run's own scored cell set — existence, not score. | block | `gates/CG-14.md` |
| `CG-15` | **A payload that says nothing.** Prose that a client would read as content actually carries some: no placeholder scalar ('N/A', 'TBD', '-', 'none', 'pending', blank) where the contract requires prose; no prose field under half the word floor its own contract doc… | block | `gates/CG-15.md` |
| `CG-16` | **The assembled payload is the whole payload.** A chunked upload assembles only when the received part set is exactly {1..parts_total}: parts_total agrees across every part, the upload is bound to the run and page it was opened for, and every part places at its stated path. A gap… | block | — |
| `CG-17` | **A declared length is the assembled length.** Where the producer declares the assembled length of a path (`expect={'heatmap.cell_evidence.cells': 706}`), the assembled payload carries exactly that many. | block | — |
| `CG-18` | **Must-present members are stated or held.** A list field declaring `must_present` carries every named member — each either stated with provenance, or explicitly quarantined with a reason. Absent, or blank with no reason, is refused. | block | — |
| `CG-19` | **A required list is not silently empty.** A required list field carries items, or the section declares an empty state, or the contract marks the field `may_be_empty`. An empty list is a claim and is made deliberately. | block | — |
| `CG-20` | **A vendor is a company, not a category.** Every technology-register row names the COMPANY that supplies it: not a category ('Integration platform'), not a placeholder ('unnamed'), and not the same string as its own product. | block | — |
| `CG-21` | **A leaf is a value, not a serialisation of one.** No payload leaf is a string that parses as a JSON object or array. Send the value; the encoding is never the value. | block | — |
| `CG-22` | **A safeguard gate_id in the payload is a real gate.** Every item in heatmap.safeguard_gates.gates[] names a gate_id present in this registry (retired counts as present — its history stays explicable). An item shaped like a disclosure but naming no real gate belongs in caps[], not gates[]. | block | — |
| `CG-23` | **Every page's own thread is written.** A section whose writer stores `narrative_thread` carries a non-empty one. The contract's words: a page is not a container for surfaces, and if the thread cannot be written the surfaces are not yet a page. | block | — |
| `CG-24` | **A rollup agrees with the rows it rolls up.** A layer rollup's `detected` equals the number of that layer's own register rows carrying a detected status. Computed from items[], never taken from the payload. | block | `gates/CG-24.md` |
| `CG-25` | **One card per argument.** No two insight cards share an ic_id, a title, or a what_text — compared on words, so reformatting one copy does not make it a second argument. | block | `gates/CG-25.md` |
| `CG-26` | **One thought-leadership entry per document.** No two entries carry the same source url, compared without trailing-slash or case differences. | block | — |
| `CG-27` | **Spelled out on first use.** No abbreviation from the registry's list reaches AUTHORED prose without its own expansion in the same field. Quotes, excerpts, source titles and a person's stated role are verbatim and are never read. | block | — |
| `CG-28` | **No executive dropped for want of a contact route.** The roster serves every seat the section says it identified, and no seat is marked dropped for missing contact details. | block | — |
| `CG-29` | **A narrative thread says what THIS section adds.** No two sections on a page carry the same narrative_thread, word for word. | block | — |
| `CG-30` | **The fit on the card is the fit the engine computed.** Every platform card carries a fit score, and it matches what the shared engine computes from that card's own inputs within the 0.05 grain tolerance — rank included. | block | — |
| `CG-31` | **The tile is the same number as the card, from the same engine.** Every opportunity tile's factor names are the engine's four, and where the platform page is staged the tile's composite and rank equal its card's fit and rank at the 0.05 grain. | block | — |
| `CG-32` | **An enrichment that resolved is an enrichment that serves.** A section whose own disclosure states that an enrichment task completed and RESOLVED a positive count of values must serve at least one of them. Resolved-but-not-served is a dropped result, not an absence. | block | — |
| `CG-33` | **Three executives speaking, or the reason none were found.** overview.thought_leadership serves at least three entries. thin=true records a shortfall; it does not excuse one. | block | — |
| `CG-34` | **A trajectory reaches back five years, or the search did.** overview.financial_series serves five distinct years, or its search account names a period at least four years older than its newest point. | block | — |
| `CG-35` | **A manuscript mark is not a sentence.** No served string carries a pilcrow, a dagger, a zero-width character, a soft hyphen, a byte-order mark or a replacement character. The section sign is NOT covered: a regulatory citation is real work. | block | — |
| `CG-36` | **A source label names a document, it does not locate a quote.** Every source_document is a citation LABEL — publisher, subject and period — under 120 characters, with no parenthetical saying where inside the document the quote sits. verbatim_quote already carries the span that was used. | block | — |
| `CG-37` | **A contact route for a named person is marked internal_only.** Every email, linkedin_url or phone sitting beside a person's name appears in that section's internal_only list, by exact path. Company contact details not attached to a named individual are out of scope. | block | — |
| `CG-38` | **A financial figure is quoted from a filing, never computed.** Every value in a financial series carries significant digits that occur in the excerpt of the evidence row it cites. Rescaling a stated figure between units passes; arithmetic on two stated figures does not. | block | — |
| `CG-39` | **The run's recommendations reach the platform page.** When the run's bundle carries recommendations and the platform payload serves platform tiles, at least one recommendation must reach the page. A run whose analyst wrote recommendations and whose platform cards all read zero has dropped… | block | — |
| `CG-40` | **An enriched surface reaches its depth floor, or says why not.** Sections whose value is their DEPTH carry a floor: sentiment serves more than one rating line, why_now spans at least three years, techstack serves at least fifteen products. Below a floor the section must carry an empty_state or a thin… | block | — |
| `CG-41` | **Every roster seat records a contact-search OUTCOME.** For each person on overview.leadership, the payload says one of two things: a contact route was resolved (email, linkedin_url or phone) and its enrichment_basis names the profile or filing it came from; or the search RAN and matched… | block | — |
| `CG-42` | **Every recommendation names an L3 area the page can join on.** Each item in platform.recommendations states a non-empty l3_area, and an area that NEARLY matches a promoted card's area must match it exactly. The platform page joins cards to recommendations on that label alone, so a missing or… | block | `gates/CG-42.md` |
| `CG-43` | **The Context sentiment grid and the Overview bars are one dataset.** Every reading the Overview draws as a bar appears as a row in the Context grid and vice versa, keyed on e_id, and where both carry a reading the rating matches. Both surfaces empty is congruent and passes. | block | `gates/CG-43.md` |
| `CG-44` | **A peer figure the assessment holds reaches the overview strip.** If the heatmap's focus areas carry peer scores, the overview pillar strip carries peer figures too or says why they do not roll up. And where a pillar row states both its own score and a peer median, the delta is the subtraction of… | block | `gates/CG-44.md` |
| `CG-45` | **A card proposing a platform states the client's reach into it.** Every platform_story card and every overview opportunity tile carries a reach statement — what the client already holds in that area, how that was established, and separately what could not be seen about how much of it is used. A stated… | block | `gates/CG-45.md` |
| `CG-46` | **The issue register holds the institution's own matters.** An issue row whose subject is the assessment's own construction — evidence coverage, uncited items, source concentration, the scoring workbook — is refused unless it also names a matter of the institution's. An empty register must name… | block | `gates/CG-46.md` |
| `CG-47` | **why_now's summary prose counts the signals it serves.** Where why_now's narrative_thread, synthesis or storyline states a number of its own signals - 'the three signals', 'Three dated signals' - that number equals the length of the signals list. Years, partition numerators, and any count… | block | `gates/CG-47.md` |
| `CG-48` | **A value is refused if its column cannot hold it.** Every non-jsonb field a page writes is checked against the SQL type of the column it lands in, joining writer_spec.json to column_types.json (generated from the migrations). Numeric, boolean and date-like columns are read; TEXT, arrays… | block | `gates/CG-48.md` |
| `CG-49` | **A client-visible absence does not name this system's machinery.** The four empty_state keys the serve allowlist keeps for a customer - reason, closure_condition, closure, kind - carry no MEM/REF finding id, gate id, CUSTOMER_WITHHELD, or connector tool call. Ordinary words like 'gate', 'connector' and… | block | `gates/CG-49.md` |
| `CG-50` | **The product a techstack row names appears in the span it cites.** Every non-ABSENT techstack.items[] row is substring-tested against the excerpts of its own cited e_ids. Matching is by DISTINCTIVE TOKEN or MULTI-WORD PHRASE, never by a generic word alone: an excerpt saying 'Financial Services Cloud'… | block | `gates/CG-50.md` |
| `CG-51` | **A run that holds a peer set argues the techstack against it.** When this run holds a peer set — a peer with a score recorded for it, or a techstack row already carrying peer_deployments — the techstack page owes two things: at least one register row carries a non-empty peer_deployments[], and the… | block | — |
| `CG-03b` | **A shape the contract states in prose is whole.** Shapes that lived only in the page prose are machine contract (item_shape) and read: platform tiles carry peer_synthesis and an estate_reach with an integer cells_not_yet_reached, peer rows are whole; the C4 grid is three audience tiles… | block | — |
| `CG-18b` | **A held member is a last resort: capped, routed, never an answer.** At most 2 must-present members are held, or 25% of the set, whichever is smaller; every held reason names the registry route searched; a structural answer (not chartered, regulated by line, no retail branches) is stated as a value. | block | — |
| `CG-18c` | **The sub-vertical's firmographic set is present.** overview.firmographics carries every member of the run's primary sub-vertical set (must_present_by_subvertical), stated or held within the ceiling; Farm Credit declares sub_vertical_undefined. | block | — |
| `CG-18d` | **A scoped figure names the entity it describes.** On O2 (unit) and O8 (basis) alike, a figure scoped to a subsidiary, segment or division names that part of the group. | block | — |
| `CG-18e` | **The strip and the regulatory card agree.** When context.regulatory_standing states license_type or primary_regulator, overview.firmographics states charter and primary_regulator too, naming the same regulators. | block | — |
| `CG-18f` | **A CAGR is ranked, and served only corroborated.** A served CAGR's unit names what grew, the window, the scope and the independent source that corroborates it. A held CAGR beside a financial series of two or more dated points states each computed candidate's rate and why none was… | block | — |
| `CG-40b` | **A WORKED_ABSENT alert shows the ladder that worked it.** An H3 alert in state WORKED_ABSENT logs its queries_run and carries no rung left open (NOT_RUN, not fetched, blocked) without the failover that ran in its place. | block | — |
| `CG-PAR` | **No page lacks the structure every gold run serves.** At promote, each staged page is compared with the committed shape-only gold (surface_gold.json: keys, list lengths and per-row null patterns of the promoted gold runs, no values). The run's own gold record is left out, and gold of its… *(registry-only: no module emits this id today)* | block | — |
| `CG-STALE` | **A promoted page does not say its own run is withdrawn.** At promote, no section's empty_state or narrative_thread asserts that the run being promoted is withdrawn or withheld pending repair. *(registry-only: no module emits this id today)* | block | — |

### AG · Analytical (8)

| Gate | What it asserts | On failure | Deep dive |
|---|---|---|---|
| `AG-01` | **Ranked or causal claims carry r_layer.** Any ranked/causal claim records hypothesis, counter, domain test, probes run and a verdict. | block | — |
| `AG-02` | **Counts are computed.** Where a surface declares its grounding, the number equals the length of the citation list. | block | — |
| `AG-03` | **Every claim-bearing item cites evidence.** Per ITEM, not per section: a why-now card, finding, recommendation, insight, timeline event, issue, tech row, alert, cap, gate result, phase or starter that asserts something carries a non-empty evidence list of its own, read from the… | block | `gates/AG-03.md` |
| `AG-04` | **A named peer's technographics carry their source.** Where peer_coverage is stated, a per-peer breakdown exists with one row per peer including the peers that could not be established (deployed: null); every deployed row carries a source_url and an as_of; and the share agrees with its own… | block | `gates/AG-04.md` |
| `AG-05` | **One event, one direction, across both pages.** An event the timeline classifies as constraining (signal NEGATIVE / maturity_effect CONSTRAINED) must not be the same event a why-now signal names as the reason to act — matched on a shared evidence id, or on the same date and subject.… | block | — |
| `AG-09` | **A rank that contradicts its own score says why.** For every platform P: if some platform Q ranks above P and scores below it, P carries a non-empty fit_basis or story_md. Rows missing either number are skipped, not failed. | block | — |
| `AG-11` | **A why-now signal is an event, not a recap.** No signal's prose states this assessment's own pillar, category or composite figures where a dated external event belongs. | block | — |
| `AG-12` | **A starter opens on an opportunity.** No conversation starter makes the client the subject of a failure — no contradiction claimed, no incapacity as the opening, no second-person absence, no ranking down. | block | — |

### SG · Safeguard (2)

| Gate | What it asserts | On failure | Deep dive |
|---|---|---|---|
| `SG-S8` | **Sentiment rests on more than one line.** The count of rating rows across all audiences, computed at submit and never read from a declared displayed_lines, is greater than one; a self-published NPS (T4/T5) standing alone is thin whatever the count. *(registry-only: no module emits this id today)* | disclose | `gates/SG-S8.md` |
| `SG-V4` | **Grounding against the run corpus.** Prose similarity against the narrowest applicable centroid (cell .62 / category .58 / pillar .55 / run .50); abstains to a recorded NOT_RUN below five members or without an embedding tier. *(registry-only: no module emits this id today)* | disclose | — |

### ET · Enrichment trigger (13)

| Gate | What it asserts | On failure | Deep dive |
|---|---|---|---|
| `ET-01` | **Cited ids resolve to this entity and run.** Every cited e_id resolves in the run's scope; a foreign id (another institution's row) halts production. | block | — |
| `ET-02` | **No minted-namespace fabrication.** Ids in the mint namespace must exist server-side; the agent never chooses the number. | block | `gates/ET-02.md` |
| `ET-03` | **Agent-created ids in their five classes.** ic/f/fa/ts/wn (+ authored rec) ids match their patterns; everything else is read or requested, never created. | block | `gates/ET-03.md` |
| `ET-04` | **Cited evidence carries its excerpt.** Every cited id resolves to a row carrying a verbatim excerpt of 50-500 characters; an empty excerpt is a refusal, and so is a payload-carried excerpt outside the band. | block | `gates/ET-04.md` |
| `ET-05` | **A run cites only its own sub-vertical's cells.** No section cites a variant cell whose terminal segment names a sub-vertical other than the entity's. Base cells and family or product-line variants serve every entity; the derivation is the catalogue's own id convention. | block | `gates/ET-05.md` |
| `ET-06` | **The candidate set is bounded by the entity's vertical.** No discard list carries a platform ruled out by the entity's own vertical — neither one whose stated reason argues from vertical or entity type, nor one whose anchor cells are another sub-vertical's variant cells. | block | — |
| `ET-07` | **A cited source resolves to the cells it supports.** Every id a cell-grain section cites resolves to a row carrying at least one evidence_subcap_links entry, OR the citation is stated as supporting no cell — either because the citing section reasons at IDENTITY grain (firmographics, the… | block | — |
| `ET-08` | **A cell-link field carries a cell id.** Every field this connector treats as a cell link — anything ending subcap_id / subcap_ids, plus capability_ids and subcaps — holds a catalogue cell id or nothing. A non-empty value that is not an id is refused. | block | `gates/ET-08.md` |
| `ET-09` | **No other client named in this client's prose.** No payload string names another client in the corpus, unless that name is a peer recorded server-side for this run. | block | — |
| `ET-10` | **A FACT rests on a T1 or T2 source.** Every cited evidence row labelled FACT carries tier T1 or T2. A T3-T5 row may be INFERENCE, HYPOTHESIS or CEILING_ESTIMATE; the label is derived from provenance, never typed. | block | — |
| `ET-11` | **A machine technographic scan is a T1 source.** Every cited evidence row whose source names a technographic scan provider (Hubbl, BuiltWith, Wappalyzer, Explorium and their kind) carries tier T1. Machine-generated, timestamped deployment data is the strongest tier the ladder has;… | block | — |
| `ET-12` | **The tech register is built on a machine scan.** The techstack page cites at least one connector-origin technographic reading (Clay Tech Stack or Vibe Prospecting technographics, registered with kind 'technographic', T1), or its r_layer records the scan as NOT_RUN naming both tools… | block | — |
| `ET-05b` | **The regulatory card works its sub-vertical's regulators.** C3's ladder carries a rung naming a regulator of the run's primary sub-vertical family (regulator_family_by_subvertical) whose outcome is not open. | block | — |

> **Emitted but not in the registry:** `SG-01`, `SG-06`. A verdict can name these and `explain_gate` cannot answer for them.

<!-- generated:gate-census END -->
