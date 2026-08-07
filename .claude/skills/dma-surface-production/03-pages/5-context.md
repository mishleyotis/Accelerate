# Page: context

Five sections. INTERNAL ONLY — the whole dashboard is withheld from the customer audience, but that does not relax the identity gate or citation.

**5 sections · 6 surfaces.** Submit with `submit_page_payload(run_id, page='context', payload={...})`.

Read `01-start-here/1-standing-clauses.md` before writing any section on this page. The standing clauses apply to every section and are not repeated below.

## Sections on this page

| Section | Required | Surfaces | Renders on |
|---|---|---|---|
| `timeline` | yes | C1 | D5 |
| `issue_register` | yes | C2 | D5 |
| `regulatory_standing` | yes | C3 | D5 |
| `context_sentiment` | yes | C4 | D5 |
| `acquisitions` | yes | C5 | D5 |
| — | — | C6 | D5 (renders `overview.financial_series`) |

**C6 is not a section of this page.** The financial trajectory card on D5 renders
`overview.financial_series` — the same section, the same row, the same
`reading`. You do not produce it twice and you cannot make the two cards
disagree, because there is only one. Write it on the overview page.

## Internal only, and what that does not excuse

Withheld from the customer audience does not mean unmarked. Audience redaction
is server-side and **default-deny**: a path you do not mark is a path that
reaches whoever can see the page. Two things still apply on every section here:

- Mark the internal rungs in `internal_only[]` — the redaction walker strips the
  paths you name, and only those.
- The identity gate, citation and the recency ladder are unchanged. An internal
  reader acts on this page; a wrong regulator or an unresolvable evidence chip
  costs the same credibility it would cost in front of the client.

---

## C1 · Digital evolution timeline

- **Section** `context.timeline` — **renders on** D5 (Context)
- **Contract** Chronological, year-range and signal filtered. Every event dated and cited; each expands inline to its detail.

### Must present

The client's technology history as dated events, each cited.

Every event dated; undated events are excluded, not rendered as 'ongoing'.

16 clients had two or fewer events — sparse timelines must declare themselves.

### `signal` is a direction. It is not a sentence.

**CG-09 blocks this and it is the most-hit vocabulary failure in the corpus.**
`signal` takes `POSITIVE │ NEUTRAL │ NEGATIVE`, upper case, and nothing else. The
column is plain TEXT, so a sentence is accepted, promotion succeeds, and the
defect surfaces on the page: a real run wrote the consequence sentence into
`signal` on all ten events, and D5's Positive/Neutral/Negative filters then
matched **zero of ten** on a page showing ten.

The consequence sentence has its own home: `maturity_effect`
(`ADVANCED │ CONSTRAINED │ NEUTRAL`, plus one clause of reasoning) and the
event `body`. Case matters — `positive` misses the filter exactly as prose does.
Null passes: absent is not wrong, a sentence is.

### What the event drawer shows, and what it shows when you leave it empty

Clicking an event opens a detail panel that renders `body`, `maturity_effect` and
the capability ids. All three were promoted and displayed by nothing until
recently, which is the whole of a timeline that "has no depth": the depth was
written and never shown. An event whose `body` is a restatement of its title
opens a panel that says nothing twice.

`storyline` and `arc_shape` render too — they are the page's argument, not
metadata. A storyline that names no inflection point is a list of dates in
sentence form.

### Sixteen clients had two events. A disclosing entity will offer two hundred.

The scarcity failure is the documented one and the enrichment step exists for it. The
abundance failure produces the same unreadable card from the opposite direction: forty true,
dated, cited events in chronological order, and no trajectory visible through them.

Select on **bearing and inflection** — an event earns its row because it changed the
capability position, not because it happened. A vendor renewal, a branch opening and a
rebrand are dated and belong nowhere near this card; a core conversion, a channel launch,
a leadership change that moved technology, a regulatory action and a completed integration
are the arc. State the selection basis alongside `arc_shape`, so a reader can see that the
ten events are a reading of the history rather than the ten you happened to find.

The Gantt's window is derived from the events' and issues' own dates, so an
undated item is **listed rather than drawn** — it is not lost, but it is not
placed either, and a reader cannot see where it sits. Date it or accept that.

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| events[] | Research workbook + enrichment | {event_date, title, body, kind, signal, capability_ids[], maturity_effect, e_ids[], claim_label} |
| events[].signal | contract vocabulary | `POSITIVE │ NEUTRAL │ NEGATIVE` — CG-09, exact case |
| events[].maturity_effect | producer | `ADVANCED │ CONSTRAINED │ NEUTRAL` + one clause; this is where the consequence sentence goes |
| events[].capability_ids | catalogue | an event bearing on no capability is not a digital-evolution event |
| storyline | producer | 60–110 words; renders as the page's argument |
| arc_shape | producer | needs ≥3 dated points; never asserted from two |
| verified_sparse | producer | set when the sources hold fewer than 3 dated events |

### Prompt

```
Extract the digital evolution timeline, then make it a STORYLINE that explains how this client reached its current maturity. STEP 1 - COLLECT DATED EVENTS FROM THE PACKAGE The research workbook's dated rows, the assessment report's history sections, regulator enforcement dates, vendor tenure evidence. STEP 2 - ENRICH (mandatory - the package is almost never sufficient here) 16 clients shipped two or fewer events. Search deliberately for the client's own history, with explicit year markers:   - the entity's newsroom and press releases, year by year   - annual reports for the last 5 years - each states that year's initiatives   - core-platform and digital-channel announcements: "[Entity] core conversion";     "[Entity] selects OR implements OR migrates [vendor] 2019..2026"   - leadership changes that moved technology: "[Entity] names CIO OR CTO OR CDO"   - M&A and charter events   - regulator actions WITH DATES (NCUA / OCC / FDIC / CFPB / SEC / FINRA /     state DOI)   - conference talks and case studies with dates   - app-store release history: first release, major redesigns   - vendor tenure: "[Entity] [vendor] since OR relationship history" Mint E-CC ids for everything new with url + verbatim excerpt + retrieval date. STEP 3 - EMIT EVENTS {event_date, title, body, kind, signal, capability_ids[], maturity_effect,  e_ids[], claim_label}   event_date      REQUIRED, precise to at least the month. An undated item is                   EXCLUDED - never rendered as "ongoing".   kind            PLATFORM │ LEADERSHIP │ M&A │ REGULATORY │ CHANNEL │ DATA │                   SECURITY │ STRATEGY   body            25-45 words: what changed, and what it replaced or enabled.   capability_ids  which assessed capabilities this bears on. An event bearing on                   none does not belong here - a rebrand is not a digital                   evolution event.   signal          POSITIVE │ NEUTRAL │ NEGATIVE, and state the SCORE EFFECT in                   the panel: positive raises the ceiling on the affected                   capability, negative caps it, neutral is context with no                   direct effect. A badge without its consequence sentence is                   incomplete.   maturity_effect ADVANCED │ CONSTRAINED │ NEUTRAL with one clause of reasoning.                   A ten-year-old core conversion never revisited CONSTRAINS                   current maturity; say so. STEP 4 - WRITE THE STORYLINE (this is the tie back to the DMA) storyline: 60-110 words tracing how the SEQUENCE produced today's assessed position. Name the inflection points and the consequence. It must be consistent with the executive summary's Complication and with the Platform page's effort profile: if the storyline says integration debt accumulated from a 2014 core conversion, integration had better rank first in the effort profile. Then arc_shape = STEADY_INVESTMENT │ STOP_START │ POST_EVENT_CATCHUP │ LEGACY_ANCHORED │ RECENT_ACCELERATION, with one sentence of evidence. STEP 5 - CHALLENGE (R-Layer)  B  Is there a competing arc? An event you attributed to strategy that actually     follows a regulator action is a different story entirely.  D  Probes: undated; an event about a same-named different entity; a vendor     press release describing an INTENTION rather than a completion (Evidence     Level 2, not 1); an event with no capability bearing; an arc asserted from     too few points.  E  REJECT -> drop the event. FEWER THAN 3 DATED EVENTS -> emit them, set     verified_sparse=true, and do NOT write an arc from two points. GATES: S34_timeline_provenance (every event cited); G6 (arc claims need >=3 dated points); G9 (milestones dated).
```

---

## C2 · Issue register &amp; Gantt

- **Section** `context.issue_register` — **renders on** D5 (Context)
- **Contract** One row per matter with identity fields, rendered as a Gantt. Each issue expands inline and names the cells it caps.

### Must present

The client's own open matters, one row per MATTER, with severity, status and a drilldown that has something in it.

One matter must not ship as many rows (SunStrong shipped 13 rows for one matter).

A row with neither rationale nor linked capabilities renders title-only; the frontend guards this, so do not fabricate a rationale to fill it.

### Every issue names the cells it bears on

Measured on a real run: **4 of 5 issues carried no capability linkage at all**, so
the drilldown opened onto nothing and the register read as a list of matters
unrelated to the assessment it sits inside. That is the "issues not linked to the
DMA" symptom, and it is a linkage failure, not a rendering one.

Treat linkage as part of the row, not a courtesy. An issue that bears on no
assessed capability is either mis-scoped for this register or the linkage has not
been done — say which.

**Two lists, two different claims. Do not conflate them.**

| List | Claim | Consequence on screen |
|---|---|---|
| `capped_subcap_ids` | This matter CAPS these cells, at a stated level | A padlock and a ceiling on the grid; the cell's score is explained |
| `linked_subcap_ids` | This matter BEARS ON these cells | The drilldown opens onto them; no ceiling asserted |

A cap with no level is not a cap. The grid distinguishes the two, so a cell
listed under `capped_subcap_ids` with `cap_level: null` reads as "linked", and if
you meant a ceiling you have not stated one.

**`status` is never null, and it is the register's own word.** A real run used
`ACTIVE`, `NEW OBLIGATION` and `REMEDIATED`; the banner had been filtering for
`OPEN`, a value the register never uses, and showed nothing while the grid beneath
it showed markers. Send the source's status verbatim; do not normalise it to a
vocabulary the source does not use.

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| issues[] | issue_register.csv | {issue_id, title, severity, status, opened_on, resolved_on, rationale, capped_subcap_ids[], linked_subcap_ids[], e_ids[], provenance} |
| issues[].status | the register | its own word, never null, never normalised |
| issues[].capped_subcap_ids | producer analysis | with a cap level, or it is a link and not a cap |
| issues[].e_ids | register + enrichment | AG-03: per item, not per section |
| dedup | issue_dedup.collapse_issue_rows | collapses by register key, exact title and prefix containment |

### Prompt

```
**REISSUED** — added cap linkage, budgets, ordering and an explicit empty state.

STEP 1 — ONE ROW PER MATTER
Collapse duplicates differing only by formatting or a trailing clause.

STEP 2 — EMIT
{issue_id, title, severity, status, opened_on, resolved_on, rationale,
 capped_subcap_ids[], linked_subcap_ids[], e_ids[], provenance}
title 8–16 words, the matter in the source's own terms.
severity and status are ALWAYS populated. Never emit a NULL status.
rationale 25–60 words where the source gives one. If it does not, LEAVE IT EMPTY — the
drilldown renders the title alone and that is honest. Do not compose a rationale to make
the card look full.

STEP 3 — NAME WHAT IT CAPS
Where a matter constrains an assessed capability, put the cell in capped_subcap_ids with
its cap level. A regulatory matter that caps a cell and does not say so leaves the score
looking unexplained.

STEP 4 — CHRONOLOGY
Ordered by opened_on. The Gantt renders in the order sent.

STEP 5 — ABSENCE
No matters found is a finding: emit verified_absent with the registries searched.

GATES: one row per matter · status non-null · identity on every regulator named
```

---

## C3 · Regulatory standing

- **Section** `context.regulatory_standing` — **renders on** D5 (Context)
- **Contract** Primary regulator from the regulator's own registry, licence type, jurisdictions, and enforcement actions with the cells they cap.

### Must present

The prudential regulator, the licence as the registry words it, the jurisdictions,
the charter date, and either dated enforcement actions or a recorded absence with
the registries searched.

**Every `e_id` on this card must resolve for this run.** The card's "view evidence"
control is a control: until recently it was hardcoded in the renderer and opened
an id belonging to no run at all, so the drawer answered "no evidence in this
tier" — which is the view-evidence defect this surface was reported for. An
unresolvable id here is a dead control, not a cosmetic issue.

`jurisdictions` is the fastest contamination check in the product. It is read by
the firmographics footprint on the overview page, so the two cannot disagree —
a disagreement is a contradiction to resolve or quarantine, never variation to
average.

Measured prose length on a real run: **21 words for the whole card.** A regulatory
standing that states a regulator and stops has not been analysed; the analysis is
what the actions cap and what a verified absence supports.

### The prudential regulator, and the four things that get mistaken for one

The prompt's sub-vertical map gives the family. Three distinctions inside it decide whether
the card is right:

- **Charter type sets the second regulator.** A federally chartered credit union answers to
  the NCUA; a state-chartered one answers to the NCUA for insurance and to its state
  supervisor for the charter, and both belong on the card. The same split runs through
  state-versus-national banks. Establish the charter from the registry before you name one
  regulator or two — `license_type` as the registry words it is what makes this checkable.
- **A disclosure regulator is not a prudential one.** The SEC receives a listed bank's
  filings and does not supervise its safety and soundness. `primary_regulator` on a bank is
  the chartering supervisor, and the SEC belongs in `additional_regulators[]` if anywhere.
  The same applies to a broker's affiliated adviser: SEC registration of the adviser is a
  fact about the adviser, not the prudential standing of the group.
- **An intermediary is licensed, not chartered.** For a brokerage or an agency, the analogue
  of a charter is a set of state department-of-insurance licences and appointments, one per
  jurisdiction, with a designated licensed producer named. `jurisdictions` for such an entity
  comes from those licence records, and it is a longer and more precise list than a
  self-described footprint — which is exactly what makes it the contamination check.

**A counterparty's regulator is not contamination.** A credit union acquiring a bank
generates an FDIC or state banking-department approval notice; those documents are about
this entity's transaction and are the best-dated evidence that it exists. Cite them, hand
them to C5, C1 and O3, and let the identity gate pass them on the ground that the document
is about this entity even though the regulator is not this entity's. What they may never do
is set `primary_regulator` — an FDIC chip on a credit union's standing card is still the
identity error this card quarantines for, and the distinction between "regulates this
entity" and "regulated the other side of this deal" is the one the reader is trusting you
to have made.

**On a multi-brand entity, the sweep runs under every name.** Enforcement pages and
complaint databases key on the legal entity in some places and on the trading name in
others, so a search run only under the legal name has skipped rungs. Record which names
were searched in `absence_of_enforcement` — a verified absence that names one of seven
brands is not a verified absence.

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| primary_regulator | the regulator's OWN registry | never the entity's self-description |
| license_type | the registry | worded as the registry words it; it constrains which capabilities can legitimately be assessed |
| jurisdictions | registry or filings | reconciles with the overview footprint |
| enforcement_actions[] | every applicable regulator's order pages | dated only; each with the cells it caps |
| absence_of_enforcement | producer | the registries searched — verified absence supports the compliance-posture cell, unverified silence supports nothing |
| e_ids | evidence store | each must resolve for THIS run; the chip is a control |

### Prompt

```
Produce the regulatory standing card. Treat it as the document's identity anchor. {primary_regulator, additional_regulators[], license_type, jurisdictions[],  charter_date, enforcement_actions[], absence_of_enforcement, e_ids[]}   primary_regulator                 the prudential regulator, from the regulator's OWN registry, not                 from the entity's self-description. By sub-vertical: SV1                 OCC/FDIC/Fed/State DOB · SV2 NCUA/State CU · SV4 SEC/FINRA/Fed/                 CFTC · SV5 SEC/FINRA/State securities · SV6 SEC/CFTC · SV7-SV8                 State DOIs/NAIC · SV9 FCA/FCSIC.                 An FDIC or OCC chip on a Farm Credit entity, or an FCA chip on a                 national bank, is an IDENTITY ERROR: quarantine the whole card                 and escalate, because it means the profile is contaminated.   license_type  as the registry states it ("National bank holding co.",                 "federally chartered credit union", "Agricultural Credit                 Association"). This constrains which products the entity may                 offer and therefore which capabilities can legitimately be                 assessed.   jurisdictions from the registry or the entity's filings. THE FASTEST                 CONTAMINATION CHECK IN THE PRODUCT: cross-check against every                 footprint claim on every other surface and flag disagreement as a                 contradiction, not as variation. ENFORCEMENT - search always; absence is a finding Per action: {issue_id, regulator, kind, opened_on, status, summary, capped_subcap_ids[], remediation_status, e_id}   Search EVERY applicable regulator's enforcement or order pages by entity name:   NCUA, OCC, FDIC, Fed, CFPB, SEC, FINRA, state DOI/DOB, FCA. Dated actions only.   capped_subcap_ids  which cells this action CAPS and at what level. An action                      that caps nothing has not been analysed.   Emit once, hand to the issue register (C2) and the why-now (O3); all three must   carry the same date.   absence_of_enforcement                      searched all applicable regulators and found nothing ->                      RECORD THE SOURCES SEARCHED. Verified absence supports the                      compliance-posture cell; unverified silence supports                      nothing. CHALLENGE  D Probes: regulator taken from marketing rather than the registry; a same-named    institution's action attributed here (verify the charter number / CIK / RSSD,    never the name); a closed action rendered as open; jurisdictions inconsistent    with any other surface.  E Any identity mismatch -> quarantine and escalate. Never render a partial    identity. GATES: G1 Identity & Boundary; G2 Regulatory Anchor; every action dated and cited; jurisdictions reconcile across surfaces.
```

---

## C4 · Sentiment overview

- **Section** `context.context_sentiment` — **renders on** D5 (Context)
- **Contract** The sentiment grid at Context depth, each tile expanding inline to the items behind it. Prototype-only; produced under the O9 sentiment prompt at Context depth.

### It is a re-projection of O9. It is not a second measurement.

This is the one thing to get right here. C4 and O9 render **the same dataset at two
depths** — O9 as bars on the overview, C4 as three expandable tiles on Context. The
ratings themselves live on `overview.sentiment.bars`, where O9 stores them. C4
re-projects them with a drilldown.

Consequences:

- **The two cards can never disagree.** Every `rows[].e_id` and `rows[].rating` here
  must appear in `overview.sentiment.bars`. That is a reconciliation, checked.
- You do not search twice and you do not find a different picture at Context depth.
  A figure that appears here and not on O9 is either a bar you forgot to emit or a
  second, unreconciled measurement — both are defects.
- Produce O9 first, then project.

### Must present

`context_tiles[]` — three tiles, `audience` one of `customer │ employee │ market`.
(`market` here is the family O9's bars call `industry`; the two names are the same
audience and the reconciliation is by `e_id`, not by label.)

Per tile: `{audience, rows[], e_ids[]}`.
Per row: `{source, rating, scale, n, as_of, url, e_id, note}`.

The first seven row fields are the O9 bar's interpretability fields and carry its
rules exactly:

| Missing | Consequence |
|---|---|
| no `n` | not a signal — do not render a number |
| no `scale` | the rating is meaningless (4.1 out of what?) and no bar is drawn |
| no `as_of` | UNVERIFIED recency; never presented as current |
| `n` below 30 | renders with a low-sample warning, not as a finding |

Sentiment older than 18 months is RECENT, not CURRENT; older than 36 is LEGACY and
must not be presented as the current picture.

**`note` is the expansion body, and it must END BY NAMING THE CELL IT CAPS.** That
sentence is the surface's reason to exist — sentiment that does not connect to an
assessed capability is decoration; sentiment that caps a cell is evidence. The
measured exemplar:

> Below industry median (43). Most complaints relate to ACH processing delays, not
> service quality. Caps P2C2.1.1 at M3.

`e_ids[]` are the tile's evidence chips. **Each must resolve, or the chip is a dead
control.** This is not hypothetical here: before this section had a column, whatever
a producer submitted for C4 was discarded at promotion and the card rendered a
hardcoded PROTOTYPE FIXTURE under a real client's name — Glassdoor 3.8 (n=412), App
Store 3.4 (n=8,200), a CFPB index of 24 — with chips that opened a drawer saying the
id does not resolve. None of those figures were the client's. An unbound field is
not a soft failure; it is a fixture rendered as a finding.

### SG-S8 discloses, and thinness is not a defect to hide

Sentiment resting on a single rated line trips **SG-S8**, which **discloses and
still promotes** — the client reads *"Sentiment rests on a single source, so treat it
as indicative only"*. That is deliberate: the common misreading of this surface is
the other way round, a thin reading taken as a finding about the institution.

Two rules follow:

- **Do not synthesise a second audience to fill the grid.** Search all seven source
  families (App Store, Google Play, Glassdoor, Indeed, CFPB complaint narratives,
  BBB, Trustpilot/Google reviews) plus J.D. Power and Forrester where the entity
  appears; if only one source survives, emit it and let the thin state show.
- **A row with no rating is not a line of sentiment.** It is a source you searched,
  and it belongs in the ladder — `sources_searched` on the empty state — not in the
  tile. The gate counts rated rows and never reads a declared count.

A source that blocks automated retrieval cannot be cited at all — Glassdoor,
Indeed and ZipRecruiter all 403 — so it is a rung in the ladder, not an `e_id`.
See `01-start-here/2-evidence.md`.

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| context_tiles[].audience | contract | `customer │ employee │ market` |
| context_tiles[].rows[] | the same sources as O9 | reconciled by `e_id` and `rating`, never re-searched |
| rows[].note | producer | the expansion body; ends by naming the cell it caps |
| rows[].n / scale / as_of | the source | absent → the row does not render a number, a bar, or as current |
| context_tiles[].e_ids | evidence store | each resolves, or the chip is dead |
| the ratings themselves | `overview.sentiment.bars` | O9 owns them; C4 projects them |

### Prompt

```
Produce the Context-depth sentiment grid. This is a RE-PROJECTION of the O9 sentiment dataset, not a second measurement: produce O9 first, then project it here with a drilldown. If you find a figure here that is not on O9, you have either forgotten a bar or measured twice - reconcile, do not add. STEP 1 - RECONCILE BEFORE YOU WRITE Pull your own overview.sentiment.bars. Every row you are about to emit must correspond to one of those bars by e_id and by rating. The two cards render the same numbers in two shapes and a client sees both. STEP 2 - EMIT THREE TILES context_tiles[]: {audience, rows[], e_ids[]}   audience  customer | employee | market. "market" is the family O9's bars call             "industry" - same audience, and the reconciliation is by e_id, not             by label. Emit the tile even where its rows are empty, together             with the section empty_state naming what you searched: an absent             audience is a finding, a missing tile is a hole. STEP 3 - EMIT THE ROWS Per row: {source, rating, scale, n, as_of, url, e_id, note}   rating/scale/n  all three or the row does not render a number. No scale means                   "4.1 out of what?"; no n means it is not a signal; n below 30                   renders with a low-sample warning rather than as a finding.   as_of           REQUIRED. No as_of is UNVERIFIED recency and must never be                   presented as current. Older than 18 months is RECENT; older                   than 36 is LEGACY and is not the current picture.   url + e_id      registered through register_evidence, with the id the server                   gave back. A source that BLOCKS automated retrieval cannot be                   cited at all - it is a rung in the ladder, not an e_id.   note            THE EXPANSION BODY, and the reason this surface exists. 25-55                   words, and it MUST END BY NAMING THE CELL IT CAPS and at what                   rubric level. Distinguish the cause: "complaints relate to ACH                   processing delays, not service quality" is the analysis; a                   restatement of the star rating is not. Sentiment that connects                   to no assessed capability is decoration. STEP 4 - THINNESS DECLARES ITSELF Search all seven source families (App Store, Google Play, Glassdoor, Indeed, CFPB complaint narratives, BBB, Trustpilot/Google reviews) plus J.D. Power and Forrester where the entity appears, and any self-published NPS (T4/T5, needs corroboration). If only ONE rated line survives, emit it. SG-S8 will disclose that the reading is indicative and the run still promotes. Do NOT synthesise a second audience to fill the grid, and do not promote an unrated row into the tile to raise the count - a row with no rating belongs in sources_searched. STEP 5 - CHALLENGE (R-Layer)  B  A low rating with a high n and a high rating with a low n are different     claims. Which one is the institution, and which one is a sample?  D  Probes: a same-named different institution's reviews; a rating whose scale     you assumed; an app-store rating for a decommissioned app; a complaint index     that names a different entity; a note whose cap is asserted with no rubric     level.  E  REJECT -> drop the row rather than emit a number you cannot scale or date. GATES: SG-S8 (discloses at one rated line, and at self-published-only); reconciliation with overview.sentiment.bars; every e_id resolves; AG-03 per row.
```

---

## C5 · Acquisition history

- **Section** `context.acquisitions` — **renders on** D5 (Context)
- **Contract** Closed and announced transactions with integration status and maturity effect. A temporarily-constraining integration is not smoothed to neutral.

### Must present

One row per transaction, each dated and cited, with its integration state and its
effect on named cells. `rows` is the container.

This card also rendered an inline fixture until recently — two invented credit
unions, with an `evidence: []` that was never shown. It reads from the payload now,
so an empty `rows` is an honest empty state and a thin row is visibly thin. Both are
better than what it replaced, and neither is a reason to compose a transaction.

### A cross-charter transaction is the best-evidenced row on the card

Where the target sits under a different regulator from the acquirer — a co-operative
acquiring an insured bank, an intermediary acquiring a licensed agency in a state it does
not yet operate in — the approval trail is public, dated and authoritative, and it is
usually the only source that states the closing date precisely. Cite it, and take the
identity question the right way round: the notice is about this entity's transaction, so it
belongs here, and it says nothing about who regulates this entity. C3 owns that, and the two
cards must not end up naming different prudential regulators because one of them read an
approval notice as a charter fact.

A serial acquirer changes what this card is for. Ten transactions in five years is not ten
rows of equal weight: rank by integration consequence on a named cell, group the rest, and
say that is what you did. `scale_metrics` is where the volume goes — the aggregate the
transactions add up to — and `affected_subcap_ids` is what keeps each row part of the
assessment rather than a corporate history.

`TEMPORARILY_CONSTRAINED` is the value most often smoothed away and it is usually
the correct one during a cutover. An integration in flight constrains the
capabilities it touches for a stated window; saying so is the finding, and the
why-now's `cost_of_acting_now` and the roadmap's phase 1 both depend on it.

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| rows[] | newsroom, regulator approvals, trade press, target filings | {closed_on, target_name, kind, status, scale_metrics, integration_target, affected_subcap_ids[], maturity_effect, effect_note, e_ids[]} |
| rows[].closed_on | the announcement or approval notice | to the month; announced-but-not-closed is its own row |
| rows[].status | producer | `ANNOUNCED │ INTEGRATING │ COMPLETE │ ABANDONED`, never null |
| rows[].maturity_effect | producer analysis | including `TEMPORARILY_CONSTRAINED`, with the named cells |
| rows[].e_ids | evidence store | AG-03: per row |

### Prompt

```
Produce the acquisition history: dated events with integration state and effect on assessed capabilities. Per row: {closed_on, target_name, kind, status, scale_metrics,           integration_target, affected_subcap_ids[], maturity_effect, effect_note,           e_ids[]}   closed_on         REQUIRED to the month. Announced-but-not-closed is a                     SEPARATE row with status=ANNOUNCED and its own date.   status            ANNOUNCED │ INTEGRATING │ COMPLETE │ ABANDONED   scale_metrics     quantified in the acquirer's own terms: branches, deposits or                     loan volume, members/customers, FTE.   integration_target the date integration is tracking to, where stated.   maturity_effect   ADVANCED │ CONSTRAINED │ NEUTRAL │ TEMPORARILY_CONSTRAINED                     with the named cells. TEMPORARILY_CONSTRAINED is honest and                     often correct during a cutover; do not smooth it to NEUTRAL.   effect_note       20-45 words: what the integration does to the named                     capability and over what window - specific cell, direction,                     window. ENRICHMENT (mandatory - M&A is public and dated, so silence is not evidence)   - the acquirer's press releases and newsroom, by year   - regulator approval notices, which are dated and public: OCC/FDIC/Fed     applications, NCUA merger approvals, FCA territory and merger approvals   - trade press for the sub-vertical   - the target's final filings   - "[Entity] acquires OR merger OR acquisition OR purchases branches 2019..2026" Mint E-CC ids with url + verbatim excerpt + retrieval date. CROSS-SURFACE (emit once, hand to three) Every acquisition is also a TIMELINE event with kind=M&A; an integration in flight is a COST OF ACTING NOW input for the why-now and a timing constraint for the roadmap. All three must carry the same date and the same direction of effect. CHALLENGE  D Probes: an announced deal rendered as closed; a branch purchase described as a    whole-institution acquisition; an acquisition by a same-named entity; an    integration called complete while the timeline still shows cutover activity.  E REJECT -> drop the row rather than assert a status you cannot date. GATES: every row dated and cited; status never NULL; affected cells resolve; consistent with C1 and O3.
```
