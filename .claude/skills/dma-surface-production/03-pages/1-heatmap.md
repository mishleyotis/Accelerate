# Page: heatmap

FIRST. Nine sections. Cell evidence establishes the linkage every other page cites, and the coverage figures the Overview reports are computed over the cells you link here. Four of these sections render on the Health dashboard.

**9 sections · 9 surfaces.** Submit with `submit_page_payload(run_id, page='heatmap', payload={...})`.

Read `01-start-here/1-standing-clauses.md` before writing any section on this page. The standing clauses apply to every section and are not repeated below.

## Sections on this page

| Section | Required | Surfaces | Renders on |
|---|---|---|---|
| `workbook_scores` | yes | H4 | D3 |
| `focus_areas` | yes | H1 | D3 |
| `cell_evidence` | yes | H2 | D3 |
| `evidence` | yes | H6 | D3 |
| `value_chain` | optional | H9 | D3 |
| `alerts` | yes | H3 | D7 |
| `safeguard_gates` | yes | H5 | D7 |
| `evidence_age` | yes | H7 | D7 |
| `cohort_patterns` | optional | H8 | D7 |

---

## H4 · Workbook grain scores

- **Section** `heatmap.workbook_scores` — **renders on** D3 (Heatmap)
- **Contract** The maturity grid at four grain levels — pillar, category, capability, sub-capability. A cell drills in; it does not open a panel.

### Must present

The pillar and category zooms serve the workbook's OWN stated figure, with the subcap rollup shown alongside it, never instead of it.

Every aggregate cell ships both candidates and its source_cell, so a disagreement is measurable rather than invisible.

### Peer figures exist at two grains and nowhere else

The scoring workbook's `Peer_Benchmarks` tab gives per-CATEGORY scores for named
peers plus Median / P25 / P75. Measured: **0 of 765 cell rows carry a peer median.**

So `peer_median` belongs on `pillars` and `categories` — the grains the workbook
states — and **not on a cell.** At cell grain the app inherits the category median
and labels it a proxy, which is honest; a per-cell peer figure you supply is a number
no source states.

Two things this replaces, both worth knowing so you recognise them:

- The renderer used to draw peer ticks as `score + 0.3` — arithmetic in no source,
  on every card. It is deleted, so a missing peer figure is now **visibly** missing
  rather than plausibly present.
- Where no peer figure is available at all, `peer_basis = cannot_estimate` and the
  median stays null. Never estimate one to fill the axis.

Read the cohort from the workbook rather than assuming one; the peers differ by
sub-vertical. `01-start-here/2-evidence.md` owns the peer fallback ladder and its
proxy-disclosure rung.

### Cell NAMES come from the catalogue, never from prose

`get_capability_catalogue(run_id)` is the source. Measured on a real run: **0 of 765
served cells had a name**, because the run was not pinned to the catalogue version it
was scored against — a 17-category assessment joined against the current 16-category
catalogue matches nothing. If cells are coming back nameless, that is a catalogue pin
to fix in the run, not a name to copy out of report prose. Copying a name out of prose
is how raw taxonomy codes end up rendering as labels.

Check `is_thin_evidence` too: it was false on all 765 cells of a run that also carried
11 thin alerts. H3 and H2 must agree — every alerted cell is one the payload declared
under-evidenced.

### The workbook scores more cells than this run may serve

The `P*_Subcap_Scoring` tabs carry the whole catalogue, T2 variant cells included, so a
credit-union workbook holds insurance-carrier, RIA and insurance-broker variants. The
serve layer scopes them to the entity's own sub-vertical; measured, a credit union
served 765 cells of which **59 belonged to another sub-vertical** and rendered anyway.

A variant cell names its owner in its terminal segment — `P1C1.3.IC1` is a carrier cell,
`P2C4.6.RIA1` an adviser cell — and the codes that name exactly one sub-vertical are
`RB · CU · CL · CIB · FC · AM · RIA · IC · IB`. Base cells and family or product codes
(`BK`, `WM`, `PEN`) serve for everyone.

So the grid you emit is the entity's cell set, and **every count computed off it — the
coverage denominator, the linking stats, the pillar cell totals — is computed off the
same set.** A figure computed over the workbook's rows and rendered beside a grid that
serves fewer is a contradiction a reader can find by counting.
`01-start-here/6-entity-shape.md` carries the derivation and its limits.

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| pillars / categories | Scoring workbook + assessment report | the stated figure, with source_cell |
| pillars/categories `peer_median` | `Peer_Benchmarks` tab | stated at these two grains only |
| a CELL's peer figure | **inherited at read** | the category median, labelled a proxy — never sent per cell |
| cell names | `get_capability_catalogue(run_id)` | never from report prose |
| rollup_score | subcap_scores | the arithmetic mean, carried alongside |
| score_source | workbook_scores.resolve_cell | 'payload' or 'rollup' — the flag that makes 'both took the same source' checkable |

### Prompt

```
Emit the workbook's own pillar and category scores.   pillars    : {P1..P4: {score, peer_median, source_cell}}   categories : {PxCy:   {score, peer_median, source_cell}}   - These grains are STATED in the workbook and the assessment report.     They are not projections and must not be recomputed by averaging     subcapabilities -- cap logic, category weighting and analyst override     are applied when they are struck.   - source_cell is mandatory. A figure that names no workbook location     cannot be checked against one and is rejected.   - Where the workbook states nothing at a grain, omit it. The app falls     back to the rollup and labels the fallback.
```

---

## H1 · Focus areas

- **Section** `heatmap.focus_areas` — **renders on** D3 (Heatmap)
- **Contract** Three to five client priorities, each with a verbatim quote from the client's own report and its page number, plus a configurable KPI strip.

### Must present

Three to five client priorities, each with a VERBATIM quote from the client's own report and its page number.

The quote must be the client speaking — not the scoring ledger's annotation, not a cut-off diagnostic question, not machine scoring text.

57 of 138 clients had none; a client with a full assessment and no focus areas is a synthesiser failure to diagnose, not an empty state to render.

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| focus_areas[].verbatim_quote | Client Profile DOCX | exact text + page number |
| focus_areas[].involved_subcap_ids | producer | extracted from the quote's subject |
| focus_areas[].title | producer | the priority in the client's own words |

### Prompt

```
Produce the focus areas: the client's own stated priorities, validated against what they have said most recently. STEP 1 - EXTRACT FROM THE CLIENT PROFILE RESEARCH REPORT Per area: {fa_id, name, verbatim_quote, source_document, source_page, source_filename, involved_subcap_ids[], entity_score, peer_score, delta}   verbatim_quote   THE CLIENT'S OWN WORDS, copied exactly from their document.                    50-400 chars. It must read like a person wrote it about their                    own institution.                    REJECT as a quote candidate anything that: contains a                    capability code (PxCy.z), contains "Score M1..M5", contains                    the word "category" followed by a code, is a scoring                    rationale, or is a [Section] tag. 53 clients shipped machine                    scoring text as the client's quote.   source_page      REQUIRED. The provenance triple is document + page +                    filename; without the page an AE cannot show the client                    where it came from.   involved_subcap_ids                    cells THIS run serves. Compute entity_score as the mean over                    them and peer_score the same way, at the same grain - a                    focus-area score built from a different cell set than the                    peer figure is a grain violation. STEP 2 - VALIDATE AGAINST THE CLIENT'S MOST RECENT VOICE (mandatory) The report tells you what they said THEN. Establish what they are saying NOW:   - the two most recent quarterly filings and the latest annual report:     strategy, outlook and MD&A sections   - the entity's newsletter and blog, last 12 months   - press releases and the newsroom, last 12 months   - executive INTERVIEWS and podcasts: "[Entity] CEO OR CIO interview 2025 2026"   - conference talks and panels by their executives   - earnings-call commentary where public   - trade-press articles naming the entity For each area emit:   currency_status  CONFIRMED_CURRENT (restated in the last 12 months) │                    AGING (last stated 12-24 months ago) │                    SUPERSEDED (they now say something different - state what) │                    UNCONFIRMED (no recent statement found; say what you searched)   currency_note    20-45 words with the newest supporting statement and its date. A SUPERSEDED focus area is one of the most valuable findings the product can produce, because the AE would otherwise walk in with last year's priority. STEP 3 - RECORD NEW EVIDENCE AS EVIDENCE (not just as reading) Every source used in step 2 is minted as E-CC-nnn with url + verbatim excerpt + retrieval date + tier + claim label, registered in the evidence store, and linked to the focus area AND to the cells it bears on. Enrichment that is not recorded cannot be shown in a drilldown, and evidence that cannot be shown might as well not exist. Emit new_evidence_ids[] per area. STEP 4 - EXTRACTION DISCIPLINE FOR EXCERPTS Read the document, do not skim it. An excerpt must be the span that ACTUALLY supports the claim, 50-500 characters, verbatim, never a URL, never a summary of the page. Where a rich document (an annual report, a strategic plan) supports many areas, mine it once for all facts, assign fact-level ids E-xxx:Fy, and map each fact to its targets - then still run the per-area searches. The single most common enrichment failure is one document-level search mapped identically onto five areas. STEP 5 - CHALLENGE (R-Layer, per area)  A State: "this is a current priority for this client", with confidence.  B Search for counter-evidence: has this initiative been paused, completed or    replaced? "[Entity] [initiative] paused OR completed OR replaced OR delayed".  C Is this priority plausible for this sub-vertical, size and regulator?  D Probes: the quote is machine text; the source document belongs to a    DIFFERENT ENTITY (check the filename and the header - one measured case cites    FCE_DMA_Client_Profile_FINAL.docx on a page for a different bank); the area    maps to no served cell; the priority is a vendor's framing rather than the    client's; the quote is from a document older than 24 months with nothing    recent to support it.  E REJECT -> drop the area. UNCERTAIN -> ship with currency_status and    confidence LOW. GATES: S29_focus_grounding; S9_focus_invalid; S18_focus_title_duplication; provenance triple present; quote is client prose.
```

---

## H2 · Cell evidence

- **Section** `heatmap.cell_evidence` — **renders on** D3 (Heatmap)
- **Contract** Per-cell evidence linkage and synthesis prose, with the count of items reasoned over computed from the citation array.

### Must present

Each scored cell's drilldown: the evidence rows behind its score, with excerpt, source, tier and freshness band.

Evidence must reach the cells — 67 clients rendered 100% thin-evidence while holding hundreds of linked rows.

Attribution must be right: a Forbes ranking under an Open-Banking subcapability is a misattribution, not a citation.

### The per-cell `synthesis` is what the drawer renders

Clicking a cell opens a drawer, and `synthesis` is its body — the sentence or two
saying what this cell's evidence, taken together, establishes about this capability.
It was promoted and displayed by nothing until recently, so a drawer that had a
synthesis showed the ids instead.

Measured on a real run: `cell_evidence` rows existed for **69 of 765 served
cells** — 9%. A cell with no synthesis opens a drawer that says nothing, and that
drawer is the whole reason the grid is clickable.

### Every served cell carries a synthesis. The grades differ; the coverage does not.

This is the default, not a stretch goal, and the earlier framing — raise coverage where
you can and declare where it stops — licensed 9% as an honest outcome. It is not: a grid
where nine cells in ten open onto silence is the single largest gap between what this
product costs to produce and what a client experiences.

What makes it achievable is that a synthesis is not one research task per cell. It is a
statement of **what is established about this capability and how firmly**, and there are
three honest grades of that statement:

| Grade | When | What the drawer carries |
|---|---|---|
| **Cited** | The cell has its own linked items | 40–90 words on what they establish, where the score sits against the peer median, one clause of consequence. `grounded_on` = the citation count |
| **Inherited** | No cell-specific item, but the parent capability or category carries evidence that bears on it | 25–50 words reasoning explicitly from that evidence to this cell, citing the parent's ids, `claim_label: INFERENCE`, cell marked thin. An inference cites what it was inferred *from* — that is what makes it one |
| **Declared** | Nothing at capability level either, and the ladder has run | The ladder itself: what was searched, what would close it, and the ceiling the absence sets. This is H3's alert content, rendered where the reader clicks |

An inherited synthesis is not a hedge and it is not padding. "The category's two sources
speak to the platform this capability runs on but not to this capability's own coverage,
so the score rests on the platform's presence rather than on observed use" is a true
statement about the evidence position, it is falsifiable, and it is exactly what a reader needs
before they argue about the number. A declared one is the absence protocol doing its job at
the grain the reader clicked on.

What is never acceptable is grade zero — a scored cell with no row at all, which asserts a
number and answers nothing about it.

### The order the work is done in, because the order cannot be recovered late

Coverage is decided when you plan the run, not when you reach H2. Work outward:

1. **Every cell any other surface cites.** Findings, insight cards, gap rows,
   recommendations, focus areas, ceilings, roadmap phases, stair-step steps, why-now
   links, issue caps, sentiment caps, tech-stack linkage. These are the cells a reader
   *will* click, because something on another page sent them there, and every one of them
   must be **cited** grade. A cell good enough to carry an argument elsewhere and blank
   here is the worst single defect on this page.
2. **Every cell below the assessment's threshold**, and every cell carrying a thin alert.
   The low scores are what the client came to look at.
3. **The rest**, worked by document rather than by cell: mine each rich source once, assign
   fact-level ids `E-xxx:Fy`, and map each fact to every cell it bears on. One annual
   report or 10-K populates twenty to fifty cells; a call report populates the financial
   and risk capabilities across a pillar. That is how the long tail gets covered at cost,
   and it is the same technique H3's ladder already requires — the difference is that here
   you are spending it on reach rather than on a single alert.

Precision still binds: a fact mapped onto five cells because it was found while reading
about the category is over-linking, and over-linking is worse than a declared gap because
it renders as support. If a fact does not speak to the capability, the cell gets an
inherited or declared synthesis instead — those grades exist so that the reach is honest.

### `linking_stats` reports the grades, not just the reach

A single reach percentage lets a run with 9% cited coverage and 91% silence report a number
that sounds like progress. Report the shape instead: cells served, cells cited, cells
inherited, cells declared, rows unlinkable, and the count of **cells cited by another
surface that are not at cited grade** — which should be zero and is the number worth
looking at first.

`scripts/check_consistency.py` recomputes all of these against the payloads and fails the
cross-surface one, because no per-page gate can see it.

The drawer resolves the ids **you cited for this cell**, not a reverse-derived list,
so a cited id that no longer resolves renders as UNRESOLVED rather than quietly
vanishing. `grounded_on` is the LENGTH of the citation list — computed, never
asserted (invariant 8, checked by AG-02).

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| cells[].e_ids | research workbook P1C1..P4C4 sheets | one row per E-ID, mapped to the subcap the sheet is about |
| cells[].excerpt | research workbook | the quoted span, verbatim |
| cells[].synthesis | producer | the drawer's body, at cited / inherited / declared grade — one for every served cell |
| cells[].grounded_on | **computed** | the length of `e_ids`; never asserted |
| freshness_band | evidence_staleness.py | current / aging / dated / stale / undated, keyed to the run date |
| linking_stats | producer | the grade counts, plus cells cited elsewhere and not cited here |

### Prompt

```
**REISSUED** — the original 642-char prompt covered linking only. The synthesis
contract below was previously stranded in the DD-1 drilldown prompt, which is not a
submission unit, so a section produced from the original prompt had linkage and no prose.

STEP 1 — GRAIN CHECK, BEFORE ANYTHING ELSE
Assert the score, the peer median and the cell id all come from the SAME row of
subcap_scores. If the score belongs to the category and the id to the sub-capability,
STOP and emit grain_violation. Do not write prose over a mismatch. One line pairing a
sub-capability score with a category id produced 125 violations across the corpus.

STEP 2 — LINK ON SUBSTANCE, NOT PROXIMITY
Map each research-workbook row to the sub-capability its SHEET is about, then verify the
excerpt speaks to that capability. A plausible-but-unrelated citation is worse than none.
The commonest cause of over-linking is one category-level search mapped onto five
sub-capabilities.

STEP 3 — EMIT THE EVIDENCE LIST FIRST
Per cell: {subcap_id, e_ids[], items[], reach_note, synthesis, grounded_on, provenance}
Per item: {e_id, tier, claim_label, recency, source_title, publisher, excerpt}
  excerpt verbatim, 50–500 chars, never a bare URL.
Count the items. That count is grounded_on and it is printed beside the synthesis.

STEP 4 — WRITE A SYNTHESIS FOR EVERY SERVED CELL, AT ONE OF THREE GRADES
CITED (the cell has its own items), 40–90 words: what the evidence establishes about THIS
capability, where the score sits against the peer median, and one clause of consequence —
at or above median, what to protect; below, what it constrains downstream. Cite inline. Do
NOT open by restating the score, it is rendered above you. Below three linked items, mark
the cell thin and say so in the panel.
INHERITED (no cell-specific item, but the parent capability or category carries evidence
bearing on it), 25–50 words reasoning from that evidence to this cell, citing the parent's
ids, claim_label INFERENCE, cell marked thin.
DECLARED (nothing at capability level either): the ladder — searched, closure condition,
and the ceiling the absence sets.
A scored cell with NO row is the one unacceptable outcome: it asserts a number and answers
nothing about it. Order the work by consequence — first every cell another surface cites,
which must be CITED grade; then every below-threshold and alerted cell; then the rest,
worked document-by-document with fact-level ids mapped to every cell a fact truly bears on.

STEP 5 — PEER FIGURE
Where the peer table lacks one, apply the peer fallback ladder (01-start-here/2-evidence.md).
Label an inferred figure INFERENCE with one clause of reasoning. NEVER impute.

STEP 6 — REACH, HONESTLY
linking_stats: cells served, cells cited, cells inherited, cells declared, rows unlinkable,
and cells_cited_elsewhere_not_cited_here — which should be zero and is the number to read
first. A single reach percentage lets 9% coverage sound like progress; the shape does not.
If every row is unlinkable, say so — that is a source-data finding, not a silent zero.

GATES: grain lock (blocking) · citation V1–V4 · excerpt verbatim · identity on every
source domain
```

---

## H6 · Evidence store

- **Section** `heatmap.evidence` — **renders on** D3 (Heatmap)
- **Contract** The run's full evidence index: tier, claim class, recency, publisher, verbatim excerpt, and the cells each item supports.

### Must present

The full evidence index for the run: E-ID, source, URL, excerpt, tier, date, freshness band, and which surfaces cite it.

Excerpts are verbatim and grounded — the fail-closed floor is 50 characters for a grounded excerpt, above the 40-character linkable minimum.

New enrichment mints E-CC ids with provenance recorded.

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| evidence[] | research workbook + 01_evidence index | the evidence of record |
| content_hash | evidence_dedup.py | SHA256(url + claim_type + excerpt[:500]) |
| discovered_by | producer | 'claude-code' for minted rows |
| freshness_band | generated column | maintained by Postgres, not the producer |

### Prompt

```
**REISSUED** — added the register-before-cite rule, the T1-scan tier correction,
bidirectional linkage and recency handling.

STEP 1 — REGISTER BEFORE YOU CITE
Package evidence keeps its original id. Anything found outside the package is registered
through the connector, which allocates the id and computes the rank score. NEVER choose an
id yourself — an invented id is fabrication by construction even when the source is real.

STEP 2 — EMIT
{e_id, source_name, url, excerpt, claim_type, tier, published_date, discovered_by,
 supports_subcap_ids[], surfaces[]}
excerpt VERBATIM, 50–500 chars. A paraphrase is not evidence.
claim_type FACT | INFERENCE | HYPOTHESIS | CEILING_ESTIMATE.
tier T1–T5. A machine technographic scan is T1, never T4 — filing it at T4 caps the
capability and silently suppresses the score.

STEP 3 — TWO THINGS YOU MUST NOT DO
Do not register a row you did not read. Do not register a URL you could not retrieve.

STEP 4 — BIDIRECTIONAL LINKAGE
supports_subcap_ids lets the drawer render chips that jump to the other cells an item
backs, so a wrong link is visible from two directions.

STEP 5 — RECENCY
Undated is UNVERIFIED, never CURRENT. Age is computed against the run's pinned reference
date or it is null — never a sentinel.

GATES: excerpt verbatim · id resolves and belongs to this entity · source domain
identity-checked · rank score bounded
```

---

## H9 · Value-chain view

- **Section** `heatmap.value_chain` — **renders on** D3 (Heatmap)
- **Contract** The same scores arranged along the institution's value chain rather than the catalogue's taxonomy. Prototype-only; no prompt in the design specification.

### You author the envelope and nothing else

`fields: {}` on this section is the **answer**, not a gap waiting to be filled. The
Surface Specification declines a payload contract deliberately:

> No prompt block exists for this surface in the design specification. It renders
> from server-derived data and its contract is the one stated above.

The Backend Schema says the same from the other side: joining `ccg_value_chains` to
`ccg_vc_mapping` "is what lets the heatmap arrange the same scores along the
institution's value chain rather than the catalogue's taxonomy." The arrangement is
a property of the CATALOGUE for this sub-vertical and version, not of this run.

So:

- **You do not author stages.** Not their names, not their order, not their cell
  membership.
- **You do not author cell membership.** The mapping table already states which
  cells sit in which stage.
- You emit the section envelope — `produced_at`, `producer_version`, `e_ids[]`,
  `internal_only[]` — and, where the section cannot stand up for this run, its
  `empty_state` with the reason.
- **CG-04 refuses fields outside the section contract.** An invented stage list is
  not a helpful addition; it is a contract fork, and the section contract here has
  no fields for it to fork into.

If the surface renders empty for a run, that is a server-side derivation to fix — not
a payload to write. Say so in the empty state rather than filling the hole by hand.

### An empty chain has two different causes, and they are not both bugs

Before reporting a derivation fault, ask which one you have. The arrangement is keyed on
`sub_vertical` + `version`, so:

- **The catalogue carries no chain for this sub-vertical at this version.** A brokerage,
  an adviser or any sub-vertical whose chain was never authored has nothing to arrange, and
  the honest empty state says exactly that — naming the sub-vertical and the version — so
  the next reader does not re-diagnose it as a mapping failure. It is a catalogue gap to
  route, not a run defect.
- **A chain exists and the run does not render it.** Now it is a derivation fault: the run
  is pinned to a version whose mapping is absent, or the entity's sub-vertical did not
  resolve. Say which you established and how.

What you must not do in either case is borrow a neighbouring sub-vertical's chain. The
stages of a depository's value chain are not a brokerage's, and an arrangement that looks
plausible is worse than an absent one — it renders the client's own operating model back to
them incorrectly, which is the fastest way to lose the page.

### A known flaw, so you can recognise it

`ccg_value_chains.chain_id` is minted **per stage** by the loader (`VC-RB-01`,
`VC-RB-02`, …), so one `chain_id` names one STAGE, not an arrangement. Only
`sub_vertical` + `version` together identify a value chain. If you see a `chain_id`
treated as the name of a whole chain anywhere, that is the flaw, not your mapping.

### Prompt

**There is no prompt, and that is not an omission.** The surface is server-derived:
there is nothing to synthesise, so there is nothing to prompt for. Emit the
envelope. Do not produce this section from `04-craft/5-prompt-standard.md` — that
form is for surfaces whose contract has fields and no prompt, and this one has
neither.

---

## H3 · Thin-evidence alerts

- **Section** `heatmap.alerts` — **renders on** D7 (Health)
- **Contract** The run's under-evidenced cells with severity, current count, proxy attempted and closure condition.

### Must present

One alert per cell scored on insufficient evidence, with severity and the cell it concerns, feeding the Alerts queue.

The register is payload-produced; the legacy deriver is switched off.

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| alerts[] | scoring workbook is_thin_evidence + link reconcile | cleared only by real linked support, never set by the producer |
| severity | producer | mapped from the evidence deficit |

### Prompt

```
Produce the thin-evidence queue: work items that enrich and justify, not labels. STEP 1 - CLASSIFY EVERY THIN CELL INTO ONE OF THREE STATES   UNWORKED       the enrichment ladder has not been run on this cell   WORKED_FOUND   the ladder ran and found evidence -> the cell is no longer thin;                  emit the new E-CC ids and close the alert   WORKED_ABSENT  the ladder ran across all mandatory sources and found nothing A count that merges these is useless. UNWORKED is a backlog item; WORKED_ABSENT is a FINDING about the client and belongs in the narrative and, where it bears on posture, in the report. STEP 2 - FOR EVERY UNWORKED CELL, RUN THE LADDER BEFORE ALERTING Tiers 1-6 are mandatory; 7-10 fire when 1-6 yield fewer than 3 items:   1 direct capability   2 official document   3 keyword variant   4 regulatory (per applicable regulator)     5 technology / platform   6 sentiment           7 proxy signal        8 peer association   9 vendor reverse     10 CONTRADICTORY - mandatory, at least one per cell Rules: the entity name in every query; 4-8 words; no duplicate framings; never repeat a diagnostic question verbatim; add "2024 2025 2026" to at least two queries; web-fetch every rich document; LOG EVERY QUERY. Rich-document first: one annual-report fetch can populate 20-50 cells. Mine it once, assign fact-level ids E-xxx:Fy, map each fact to its targets - then still run the per-cell searches. The single most common failure is one category-level search mapped identically onto five cells. STEP 3 - GROUNDING (so nothing is hallucinated) Every item minted carries: e_id, url THAT RESOLVES, verbatim excerpt 50-500 chars taken from the fetched document, retrieval date, tier, claim label. An excerpt that is not present in the fetched text is a fabrication - assert it byte-for-byte against what you fetched, and drop the item if it does not match. Never paste a URL as an excerpt. Never summarise a page and call it an excerpt. STEP 4 - JUSTIFY THE SCORE, WHICH IS THE POINT Per cell emit: {subcap_id, score, confidence, evidence_count, state, sources_searched[], queries_run[], new_evidence_ids[], justification, closure_condition}   justification      40-80 words: on the evidence that DOES exist, why is this                      score defensible, and what is the ceiling that evidence                      licenses (Evidence Level 1-4 -> the language allowed)? A                      thin cell with a stated ceiling is honest; a thin cell with                      a confident score is not.   closure_condition  what specific artefact would close this alert - "the FY2025                      annual report's technology section", "a CFPB complaint                      narrative for this product". An alert with no closure                      condition cannot be worked by the next person. STEP 5 - AGEING Emit runs_open for each alert. An alert open across 3+ runs with no queries_run is escalated as a PROCESS defect, separately from the client's evidence position. Do not let it hide in a total. GATES: S3_thin; S3_no_cite; S30_evidence_reach; every excerpt verified against the fetched source; every alert carries sources_searched.
```

---

## H5 · Safeguard gates

- **Section** `heatmap.safeguard_gates` — **renders on** D7 (Health)
- **Contract** Client-visible gate results in plain language, including an explicit not-run state with its reason.

### Must present

The controls the assessment applied — caps enforced, uncertainty bands, QA verdicts — shown so a reader can see what constrained the scores.

This section had zero rows and no producer before it was contracted.

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| gates[] | Scoring workbook cap log; qa_verdict.json | {gate_id, kind, ceiling, affected_categories[], rationale} |
| cap_ceiling | workbook cap log | a served score above its cap is a hard defect |

### Prompt

```
**REISSUED** — two different things share this section and the original prompt emitted
neither a result nor a plain label, so the card could not render what it is contracted to.

STEP 1 — TWO ARRAYS, NOT ONE
This section carries both what the ASSESSMENT capped and what the SUBMISSION gates found.

STEP 2 — EMIT caps[] — what the assessment applied
{cap_id, kind, ceiling, affected_categories[], rationale, e_ids[]}
kind: cap | uncertainty_band | qa_hold | analyst_override
Read the workbook's own cap log and the QA verdict. rationale is the stated reason, quoted
or closely paraphrased. Do not invent a cap to explain a low score.

STEP 3 — EMIT gates[] — the SG family results
{gate_id, plain_label, result, detail, not_run_reason}
gate_id is SG-nn. result: PASS | FAIL | NOT_RUN.
plain_label is a human sentence, 8–18 words, REQUIRED — this card renders to the client and
a bare code teaches them to distrust the page.
not_run_reason is REQUIRED when result is NOT_RUN. A gate reporting PASS because it did not
run is worse than one reporting FAIL.

STEP 4 — DISCLOSE, DO NOT SUPPRESS
A failing gate is shown with its measurement. It does not block promotion.

GATES: plain_label on every client-visible gate · not_run_reason wherever NOT_RUN
```

---

## H7 · Evidence age tracker

- **Section** `heatmap.evidence_age` — **renders on** D7 (Health)
- **Contract** Age against a pinned reference date. Status follows band, band follows age, age follows a real date — or all three are null.

### Prompt

```
Produce the evidence age tracker: one row per evidence item, with a computed age and a status that FOLLOWS from it. Per row: {e_id, title, source_domain, published_or_asof, age_months, band,           status, identity_ok, reference_date}   reference_date  the run's as-of date, PINNED and RENDERED. Age is meaningless                   without the date it was computed against, and pinning makes the                   table reproducible.   age_months      (reference_date - published_or_asof) in months. If                   published_or_asof is absent or unparseable, age_months=null and                   band=undated. NEVER emit NaN, and never let a null age produce                   a positive status - the measured render shows "NaN mo ... FRESH"                   on every row, a status asserted over an uncomputable age.   band            current <=12 · aging 12-24 · dated 24-36 · stale >36 ·                   undated. These are the app's freshness_band values over the                   same 12/24/36 boundaries as the ERS Recency factor                   (CURRENT / RECENT / DATED / STALE / ARCHIVAL). Do not invent a                   third vocabulary.   status          derived from band ONLY: current->FRESH · aging->AGING ·                   dated->DATED · stale->STALE (with the >3y marker) ·                   undated->UNDATED. A status that does not follow from a computed                   band is a defect.   identity_ok     resolve source_domain against the entity's own domains and the                   known registries. A domain belonging to a DIFFERENT institution                   is an identity failure: identity_ok=false, quarantine the item,                   escalate, and do not let it count toward coverage (O10) or the                   tier distribution (O11). QUARTER-PRECISION DATES "2025-Q4" IS a date. Resolve to the quarter end for age and render the quarter as given. A quarter is not an absent date. ROLL-UP Emit undated_pct and stale_pct for the run. Where undated_pct is material, every surface quoting a time-sensitive figure must carry an age marker - 24 clients shipped 100% undated evidence while quoting current figures, and 46 were over 50% undated. GATES: no NaN in any age cell; status derived from band; every source domain identity-checked; undated_pct reported.
```

---

## H8 · Cross-entity patterns

- **Section** `heatmap.cohort_patterns` — **renders on** D7 (Health)
- **Contract** Sub-vertical concentration at or above the declared threshold. Counts and shares only; entity ids never leave the audit trail.

### Prompt

```
Produce cross-entity patterns: capability weaknesses recurring across a sub-vertical cohort. Per pattern: {sub_vertical, category_id, category_name, pattern_statement,               affected_count, cohort_size, share_pct, threshold_pct, confidence,               entity_ids[], action}   cohort_size     entities of the SAME sub-vertical with a completed run and a                   served score for this category. NEVER pool across                   sub-verticals: a Farm Credit association and a regional bank do                   not share a loan-origination cohort, because their funding                   models and product sets differ structurally.   share_pct       affected_count / cohort_size, rendered with BOTH numerator and                   denominator visible. "67%" alone hides that it is 4 of 6.   threshold_pct   the publication threshold (measured: 60). ENFORCE IT. A pattern                   below threshold is not published; if one is shown deliberately,                   label it BELOW_THRESHOLD. The measured render shows a 50% row                   under a ">=60%" header - an unenforced threshold or a                   mislabelled header, and both are defects.   MINIMUM COHORT  cohort_size < 5 -> do NOT publish; emit                   insufficient_cohort=true. Confidence from cohort size: >=20                   HIGH, >=12 MEDIUM, below 12 LOW - and RENDER it.   pattern_statement                   15-30 words naming the category, the threshold crossed and the                   share.   action          the campaign this justifies, actionable at portfolio level. CONFIDENTIALITY (blocking) Emit COUNTS and SHARES only. Never render another entity's name, score or evidence on a client-scoped page. entity_ids[] is for internal audit and must be stripped from any client-visible or AE-visible rendering. Verify on the rendered output, not in the payload. METHOD HONESTY State the score threshold used (<2.5) and the run recency window. A pattern mixing runs from three years apart is a statement about our backlog, not about the market; where the cohort's runs span more than 18 months, say so. CHALLENGE  B  Is there a structural explanation that makes the pattern trivial? If every     entity in the cohort runs the same shared core, a shared weakness is a fact     about the VENDOR, not the cohort - and that is a more useful finding. Say     which it is. For SV9 specifically, check the shared-technology providers     (FPI, AgVantis, the district bank) before calling anything a cohort pattern.  D  Probes: cohort pooled across sub-verticals; cohort below 5; threshold not     enforced; runs spanning a long window; a pattern driven by one outlier;     another client's identifying detail visible.  E  REJECT -> withhold. A withheld pattern costs nothing; a wrong one gets     repeated to clients. GATES: cohort >= 5 and same sub-vertical; threshold enforced or the exception labelled; numerator and denominator both rendered; no cross-client identifiers in any rendered output.
```
