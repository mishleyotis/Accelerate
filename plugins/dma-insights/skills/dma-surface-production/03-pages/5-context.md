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

### C6 · five points is the floor, and it is a research floor

The card is a bar chart with a CAGR under it. Three bars is not a trajectory — it is a
line through two gaps, and it reads as thin research to the one audience that opens this
page. Ship **at least five dated points on one metric definition**, and take the deceleration
with them: a series that grows 13% · 13% · 2.5% · 2.1% · 5.3% tells a story a single CAGR
flattens away, and that story is usually the point.

Three failures produced the three-point cards already shipped, all of them repairable
before submission:

- **Points sourced from whatever press release mentioned a number.** The figures then carry
  the release date rather than a reporting period, round to the nearest billion, and lag the
  filing by two quarters. `01-start-here/2-evidence.md` has the regulator route per
  institution type — for a credit union, one NCUA quarterly file per December.
- **`source_e_id` pointing at a row that says something else.** Measured on a promoted run:
  the FY2023 asset point cited an annual-report row whose excerpt was about NPS, and the
  2025-Q3 point cited an Indeed employee rating. The id resolved, the chip opened, and it
  answered a different question. A financial point cites the source **of that figure, for
  that period**, or it does not ship.
- **Reading the newest number as the newest year-end.** Quarterly filers publish a cycle
  above the last December. Keep each figure on its own stated date: an institution can be
  $6.34B at 2025-12-31, $6.50B at 2026-03-31 and $6.40B at 2026-06-30 without any of them
  being wrong, and averaging them or picking the flattering one is the defect. Where a
  quarter falls, say so in `reading` rather than letting a rising chart imply it did not.

`trend` is COMPUTED from the emitted points and stays inside the contract's four words —
`GROWING │ STABLE │ DECLINING │ VOLATILE`. The prototype's "ACCELERATING" badge is not one
of them; render the contract's word.

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

### `signal` is a direction. It is not a sentence, and it is not a mood.

**CG-09 blocks the sentence-in-the-badge failure and it is the most-hit
vocabulary failure in the corpus.** `signal` takes `POSITIVE │ NEUTRAL │
NEGATIVE`, upper case, and nothing else. The column is plain TEXT, so a sentence
is accepted, promotion succeeds, and the defect surfaces on the page: a real run
wrote the consequence sentence into `signal` on all ten events, and D5's
Positive/Neutral/Negative filters then matched **zero of ten** on a page showing
ten.

The consequence sentence has its own home: `maturity_effect`
(`ADVANCED │ CONSTRAINED │ NEUTRAL`, plus one clause of reasoning) and the
event `body`. Case matters — `positive` misses the filter exactly as prose does.
Null passes: absent is not wrong, a sentence is.

**The second failure is worse, because it type-checks.** The three words read as
MOOD — good news, no news, bad news — and a producer who classifies the news
instead of the assessment ships a page that argues with itself. Measured on a
promoted run:

| event | shipped | why it was wrong |
|---|---|---|
| Merger with another credit union announced | `NEGATIVE` | the run's own why-now used the same announcement, citing the same id and the same date, as its **leading** reason to act |
| State community-reinvestment obligation takes effect | `NEGATIVE` | the workbook's caps log reads `None (forward obligation; informs P3C3)` — the assessment applied no cap |
| Email data breach, since remediated | `NEUTRAL` | correct, and for the right reason: the S2 ceiling lapsed at 24 months |

A remediated breach reading NEUTRAL beside a merger reading NEGATIVE is the
tell. Nothing about the *news* ranks those two that way. Something about the
*assessment* does, and the assessment is what the badge is for.

#### What each value means on this page

**`signal` is the direction this event moved the assessed position of the cells
in `capability_ids`.** Not how the event felt, not how much work it creates, not
whether a reader would call it good news.

| Value | The claim | The shape it usually has |
|---|---|---|
| `POSITIVE` | the named cells score higher, or carry a higher ceiling, **because** this happened | a platform delivered, a function stood up, a role created and still filled, a programme with results in production |
| `NEUTRAL` | the named cells score exactly what they would score without it — the event **explains** the position without setting it | a constraint whose window has expired; an obligation or transaction that adds demand, exposure or scale and takes no capability away; an announcement that has not yet completed anything |
| `NEGATIVE` | the assessment holds the named cells to a maximum, or scores them lower, **because** of this event, and that constraint is live at the run's reference date | a cap in the caps log, with its cells and its level, inside its window |

#### The test that decides a borderline case

In order. Stop at the first rung that answers.

1. **Ask the caps log.** `get_report_bundle` hands you the Severity-to-Maturity
   Cap Matrix result: an **Issue Time Map** row with a `Cap Applied` column, and
   the **Severity Cap Impact** prose behind it. A live cap on the named cells →
   `NEGATIVE`. `Cap Applied: None (…)`, or a cap the arithmetic has retired →
   **not NEGATIVE**, whatever the event is about. The log is the assessment's own
   arithmetic and it outranks your reading of the news.
2. **Run the counterfactual.** Delete the event from the history and re-read the
   cells it names. Higher without it → `NEGATIVE`. Lower without it →
   `POSITIVE`. The same → `NEUTRAL`.
3. **Tie-break: capability, not consequence.** If the event changes what the
   institution must **do** rather than what it **can** do, it is `NEUTRAL`.
   Demand is not maturity. Urgency belongs to the why-now (O3), pressure belongs
   in this event's `body`, and neither of them is a signal.

Two consistency rules fall straight out of the definition, and **AG-05 blocks
both**:

- **The badge and the sentence are one claim.** `POSITIVE ↔ ADVANCED`,
  `NEGATIVE ↔ CONSTRAINED`, `NEUTRAL ↔ NEUTRAL`. Wanting `NEGATIVE` with an
  `ADVANCED` clause means you are holding two readings of one event. Pick one
  and write both halves of it.
- **An event that anchors a why-now trigger is not NEGATIVE.** O3 says this
  event opens a window worth acting in; the timeline saying it capped the same
  cells is one run contradicting itself in front of one reader. AG-05 matches
  the two on a shared `e_id`, or on the same date and subject, and it reads the
  sibling page's live submission to do it — so whichever of context and overview
  you submit **second** is where the verdict lands.

Same rule downstream: C5's `maturity_effect` on the same transaction must carry
the same direction. An acquisitions row reading `negative` beside a timeline row
reading `NEUTRAL` is the same contradiction one card further down the page —
and `negative` is not in C5's vocabulary anyway
(`ADVANCED │ CONSTRAINED │ NEUTRAL │ TEMPORARILY_CONSTRAINED`).

#### The five events, worked

| Event | Signal | Why, in the definition's terms |
|---|---|---|
| Core banking relationship extended to the vendor's cloud | `POSITIVE` | delivered, not announced: the platform the CTO is quoted about is the one the run assesses. Remove it and the architecture cells score lower |
| Email data breach, since remediated | `NEUTRAL` | rung 1 answers: `Cap Applied: None (>24mo; P4C4 cap retired)`. The ceiling was real and lapsed at 24 months with 54 elapsed; the six linked cells now score on post-incident investment. A retired cap constrains nothing today |
| State community-reinvestment obligation takes effect | `NEUTRAL` | rung 1 answers again: `None (forward obligation; informs P3C3)`. The statute adds a reporting duty and removes no capability; what holds the compliance cells is a missing lending-analytics layer that predates it and would exist without it |
| Merger with another credit union announced | `NEUTRAL` | rung 1 is silent, rung 2 answers: nothing has converted, so the integration cells score exactly what they scored before the announcement. Rung 3 confirms it — a second member book is demand, not capability. The pressure is real and it is WN-1's claim |
| Leadership evolution announced | `NEUTRAL` | the same reading, applied where it is less comfortable. An incoming president whose mandate matches the assessment's sequence is why the window is open; it is not yet a change in what the institution can do. `POSITIVE` here would be the merger error with the sign flipped |

The last row is the check on the rule. If the definition only ever moved
`NEGATIVE` badges to `NEUTRAL` it would be a way of making the page read better,
not a definition.

#### Is the enum itself the wrong vocabulary?

The three **values** are right; the **name** and the **rendering** are what
mislead. `POSITIVE/NEUTRAL/NEGATIVE` under a field called `signal`, rendered as
Positive/Neutral/Negative filter chips, invites a reader — and a producer — to
read sentiment. The payload already carries the unambiguous words one field
along: `maturity_effect` is `ADVANCED │ CONSTRAINED │ NEUTRAL`, which names the
axis out loud.

Replacing the enum would be a **contract change**, and it is not a small one.
`signal` promotes into `context_timeline`, so the change would need an
expand-migrate-contract on that column plus a backfill of every promoted run;
CG-09 reads its values from the enum registry; D5's three filter chips key on
them; and the Surface Specification states the vocabulary. That is a schema
change, an API change and a frontend change to fix a labelling problem — so it
is not made here.

What is worth doing, and is a **frontend** change rather than a contract one, is
relabelling the axis where it renders: the chips read *Advanced / Neutral /
Constrained*, or the group is titled "effect on assessed maturity". The stored
values do not move; the reader stops being told a merger is bad news.

### What the event drawer shows, and what it shows when you leave it empty

Clicking an event opens a detail panel that renders `body`, `maturity_effect` and
the capability ids. All three were promoted and displayed by nothing until
recently, which is the whole of a timeline that "has no depth": the depth was
written and never shown. An event whose `body` is a restatement of its title
opens a panel that says nothing twice.

`storyline` and `arc_shape` render too — they are the page's argument, not
metadata. A storyline that names no inflection point is a list of dates in
sentence form.

**`arc_shape` is one of five words, and it is not a place to be descriptive.**

```
STEADY_INVESTMENT · STOP_START · POST_EVENT_CATCHUP · LEGACY_ANCHORED · RECENT_ACCELERATION
```

A promoted run served `"strategy-first, substrate-later"` here. It is a better
sentence than any of the five and it is the wrong answer: the column is TEXT, so
it stored cleanly, the card printed it verbatim, and the arc it describes —
strategy landing before the substrate that carries it — is `LEGACY_ANCHORED`
with the evidence sentence in `storyline`, where prose belongs. An enum field
that accepts a sentence is a field nothing downstream can group, filter or
compare across runs, which is the entire point of having five words.

`scripts/check_payload.py` refuses a value outside the five. The connector's own
CG-09 covers `events[].signal` and `techstack.items[].status`; **it does not
cover `arc_shape`**, so the local check is the only one that fires.

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
| events[].kind | contract vocabulary | `PLATFORM │ LEADERSHIP │ M&A │ REGULATORY │ CHANNEL │ DATA │ SECURITY │ STRATEGY` — exact, and there are only eight. A run served `TECHNOLOGY` and `CAPABILITY`, which are reasonable words and match no filter on D5 |
| events[].signal | contract vocabulary | `POSITIVE │ NEUTRAL │ NEGATIVE` — CG-09, exact case. The direction the event moved the ASSESSED position of the cells it names; the caps log decides, then the counterfactual |
| events[].maturity_effect | producer | `ADVANCED │ CONSTRAINED │ NEUTRAL` + one clause; this is where the consequence sentence goes. One claim with `signal`, and AG-05 blocks a disagreement |
| events[].capability_ids | catalogue | an event bearing on no capability is not a digital-evolution event |
| storyline | producer | 60–110 words; renders as the page's argument |
| arc_shape | contract vocabulary | **exactly one of five words** — `STEADY_INVESTMENT │ STOP_START │ POST_EVENT_CATCHUP │ LEGACY_ANCHORED │ RECENT_ACCELERATION`. Needs ≥3 dated points; never asserted from two. The evidence sentence goes in `storyline`, not here |
| verified_sparse | producer | set when the sources hold fewer than 3 dated events |

### Prompt

```
Extract the digital evolution timeline, then make it a STORYLINE that explains how this client reached its current maturity. STEP 1 - COLLECT DATED EVENTS FROM THE PACKAGE The research workbook's dated rows, the assessment report's history sections, regulator enforcement dates, vendor tenure evidence. STEP 2 - ENRICH (mandatory - the package is almost never sufficient here) 16 clients shipped two or fewer events. Search deliberately for the client's own history, with explicit year markers:   - the entity's newsroom and press releases, year by year   - annual reports for the last 5 years - each states that year's initiatives   - core-platform and digital-channel announcements: "[Entity] core conversion";     "[Entity] selects OR implements OR migrates [vendor] 2019..2026"   - leadership changes that moved technology: "[Entity] names CIO OR CTO OR CDO"   - M&A and charter events   - regulator actions WITH DATES (NCUA / OCC / FDIC / CFPB / SEC / FINRA /     state DOI)   - conference talks and case studies with dates   - app-store release history: first release, major redesigns   - vendor tenure: "[Entity] [vendor] since OR relationship history" Mint E-CC ids for everything new with url + verbatim excerpt + retrieval date. STEP 3 - EMIT EVENTS {event_date, title, body, kind, signal, capability_ids[], maturity_effect,  e_ids[], claim_label}   event_date      REQUIRED, precise to at least the month. An undated item is                   EXCLUDED - never rendered as "ongoing".   kind            PLATFORM │ LEADERSHIP │ M&A │ REGULATORY │ CHANNEL │ DATA │                   SECURITY │ STRATEGY   body            25-45 words: what changed, and what it replaced or enabled.   capability_ids  which assessed capabilities this bears on. An event bearing on                   none does not belong here - a rebrand is not a digital                   evolution event.   signal          POSITIVE │ NEUTRAL │ NEGATIVE - the direction this event moved                   the ASSESSED position of the cells in capability_ids, never a                   reading of the news. POSITIVE: those cells score higher because                   it happened. NEGATIVE: the assessment holds them to a maximum                   because of it and the cap is LIVE. NEUTRAL: they score what they                   would score anyway - a retired cap, an announcement that has                   converted nothing, an obligation that adds demand and takes no                   capability away. DECIDE IT IN THIS ORDER: (1) the caps log -                   'Cap Applied: None (...)' or a retired cap is NOT NEGATIVE,                   whatever the event is about; (2) the counterfactual - delete the                   event and re-read the cells; (3) capability, not consequence.                   A badge without its consequence sentence is incomplete, and an                   event that anchors a why-now trigger is never NEGATIVE (AG-05).   maturity_effect ADVANCED │ CONSTRAINED │ NEUTRAL with one clause of reasoning.                   ONE CLAIM WITH signal: POSITIVE-ADVANCED, NEGATIVE-CONSTRAINED,                   NEUTRAL-NEUTRAL. A ten-year-old core conversion never revisited                   CONSTRAINS current maturity; say so. STEP 4 - WRITE THE STORYLINE (this is the tie back to the DMA) storyline: 60-110 words tracing how the SEQUENCE produced today's assessed position. Name the inflection points and the consequence. It must be consistent with the executive summary's Complication and with the Platform page's effort profile: if the storyline says integration debt accumulated from a 2014 core conversion, integration had better rank first in the effort profile. Then arc_shape = STEADY_INVESTMENT │ STOP_START │ POST_EVENT_CATCHUP │ LEGACY_ANCHORED │ RECENT_ACCELERATION, with one sentence of evidence. STEP 5 - CHALLENGE (R-Layer)  B  Is there a competing arc? An event you attributed to strategy that actually     follows a regulator action is a different story entirely.  D  Probes: undated; an event about a same-named different entity; a vendor     press release describing an INTENTION rather than a completion (Evidence     Level 2, not 1); an event with no capability bearing; an arc asserted from     too few points.  E  REJECT -> drop the event. FEWER THAN 3 DATED EVENTS -> emit them, set     verified_sparse=true, and do NOT write an arc from two points. GATES: S34_timeline_provenance (every event cited); G6 (arc claims need >=3 dated points); G9 (milestones dated); AG-05 (signal agrees with maturity_effect, and no NEGATIVE event anchors a why-now trigger); ET-07 (every cited id resolves to the cells it supports, or the section states why it supports none).
```

---

## C2 · Issue register &amp; Gantt

- **Section** `context.issue_register` — **renders on** D5 (Context)
- **Contract** One row per matter with identity fields, rendered as a Gantt. Each issue expands inline and names the cells it caps.

### Must present

The client's own open matters, one row per MATTER, with severity, status and a drilldown that has something in it.

One matter must not ship as many rows. Collapse duplicates that differ only by
formatting or a trailing clause — `issue_dedup.collapse_issue_rows` is the rule.

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

### What a cap is, and where it comes from

**A cap is the assessment's own arithmetic, not a description of an issue.** It
says: *this matter holds these named cells to a maximum maturity, so a cell
sitting at 3.0 sits there for a reason a reader can open.* Without it a reader
meets a number and has to accept it. With it they meet a constraint, its cells,
its level and its date.

**It is established from the workbook, never composed.** The assessment applies
the Severity-to-Maturity Cap Matrix and records the result in its caps log —
which reaches you through `get_report_bundle` as the `issue_register` report
sections: **Issue Time Map** (a `Cap Applied` column, one row per matter) and
**Severity Cap Impact** (the prose that states the level, the cells and the
window). Read both. The column is the authority on *whether*; the prose is the
authority on *what and why*.

A caps log row states four things, and all four belong on the register row:

| From the log | Onto the row |
|---|---|
| the cells named | `capped_subcap_ids` (with a level) or `linked_subcap_ids` (without) |
| the level | the `cap_level` on those ids |
| the pre-cap and post-cap position | the first clause of `rationale` |
| the window or condition that ends it | the rest of `rationale`, with its date arithmetic |

**Cap Applied: None is a finding, and it is the commonest one.** On the Baxter
run all five workbook rows read `None`. That is not an absence of analysis — it
is the analysis, and each `None` carries its reason in the same cell:
`None (>24mo; P4C4 cap retired)`, `None (friction indicator; NPS 79.81 offsets)`,
`None (forward obligation; informs P3C3)`. Send `capped_subcap_ids: []`, keep the
cells under `linked_subcap_ids`, and put the reason in the rationale where it
renders.

**Persistence, so you do not lose the work.** `capped_subcap_ids` is validated at
submit and has **no column on `context_issue_register`** — it is dropped at
promote (the writer spec flags this for adjudication). What survives promotion is
`issue_id, title, severity, status, opened_on, resolved_on, rationale,
linked_subcap_ids, e_ids`. Two consequences you must design around:

- The cells must be in **`linked_subcap_ids`** or the reader never sees them.
  Sending them only under `capped_subcap_ids` ships a drilldown that opens onto
  nothing.
- Any per-item field the contract does not persist — `opened_on_basis`,
  `sources_searched` on an issue row — passes the gate and then vanishes. Send
  it *and* repeat the substance in the `rationale`, which is the only prose
  carrier that reaches the surface.

### An issue that caps nothing still says so

The drilldown has three states and each must be stated out loud. The one that
goes wrong is the middle one.

| State | The row | What the panel must say |
|---|---|---|
| **ceiling** | cells + a level | the level, and how many of the named cells sit at it |
| **linked** | cells, no level | the assessed spread, and that this matter sets no maximum |
| **unlinked** | no cells | that it names none — **and the narrative must say why it is still on the register** |

The reported defect was the middle state rendering as the third: the panel printed
*"This matter names no capability cell"* whenever no LEVEL was stated, which — with
every promoted row shipping an empty linkage list — was every row. A reader who
clicked an issue was told the assessment had not been done.

So: **never leave a field null where the absence is the answer.** A matter that
genuinely caps nothing gets a rationale opening on the cap state (`Cap: none`,
`Cap retired`, `Cap: none today`) and then arguing it. A matter that genuinely
bears on no cell is either mis-scoped for this register or the linkage has not
been done — say which, in the rationale, in the row itself.

### Issue depth — the standard

A drilldown that only restates its title has not been produced. Every row owes a
reader all seven:

1. **identity** — id, severity and status in the register's own words
2. **the cells** — every cell the matter bears on, each one carried by this run
3. **the cap** — its level, or `none` with the reason it is none
4. **the arithmetic** — pre-cap and post-cap position, from the caps log
5. **the argument** — 2–4 sentences that argue the constraint, never restate the
   title
6. **the dates** — opened, resolved, and where undated, the search that
   established the absence
7. **the citations** — per item, each resolving with a verbatim excerpt

**Worked example — ISS-001, Baxter Credit Union.**

The workbook's Issue Time Map row:

```
ISS-001  Email Data Breach  Oct 2021  Remediated  S2 EXPIRED  54  E-008
         Cap Applied: None (>24mo; P4C4 cap retired)
```

and its Severity Cap Impact prose: *"The P4C4 Cybersecurity cap of 3.0 has been
retired. Current P4C4 scores reflect BCU's post-breach investments: NIST CSF 2.0,
13 security platforms, and CISO Southard's leadership."*

Read: the cells are P4C4, the level **was** 3.0, the window is 24 months and 54
have elapsed. Then check the position — the six linked P4C4 cells all score
**exactly 3.0** on this run, which is the sharpest thing on the row and is
invisible until you look:

```json
{
  "issue_id": "ISS-001",
  "title": "Employee email account breach in October 2021, remediated with no evidence of misuse",
  "severity": "S2 EXPIRED", "status": "REMEDIATED",
  "opened_on": "2021-10-01", "resolved_on": null,
  "capped_subcap_ids": [],
  "linked_subcap_ids": ["P4C4.2.1","P4C4.2.2","P4C4.5.1",
                        "P4C4.6.2","P4C4.7.2","P4C4.7.3"],
  "rationale": "Cap retired. The severity matrix held Information Security at a 3.0 ceiling while the incident sat inside its 24-month S2 window; at 54 months elapsed the ceiling lapsed and the six linked cells score on their own evidence. All six still read 3.0, so lifting the cap moved nothing — what holds them there is the NIST CSF 2.0 programme and a standing monitoring function, not a five-year-old email compromise. It stays on the register as the dated origin of a ceiling a reader would otherwise find unexplained.",
  "e_ids": ["E-BCU-008", "E-BCU-055", "E-CC-066"]
}
```

What makes it deep rather than long: the cap state is named in the first two
words; the arithmetic is checkable (24 vs 54 months, six cells, one level); the
argument says something the title does not (the cap's removal changed nothing);
and the last sentence answers the only question a `None` invites — *then why is
this here?*

**Enrich where the run is silent.** The register hands you a matter and rarely
hands you the record behind it. Search the regulator's own pages for a statutory
obligation, the state Attorney General breach registers for an incident, the
entity's own site for the control that bounds the friction — then `register_evidence`
each one, which mints the id and verifies the excerpt verbatim against a live
fetch. On this run four rows carrying one citation each became four rows carrying
two to five, and the added ids were what let the rationales argue rather than
assert.

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

### An unmeasured audience still fills its tile

The employee tile is the one that comes back empty, because the three sites everybody
thinks of first are the three that refuse automated fetches. What renders then is
*"EMPLOYEE · Not established for this run"*, and a client reads that as nobody having
looked. The absence is real; the blankness is a production failure on top of it.

So the blocked sites are where the search **starts**, not where it stops. Reachable
employer-side sources exist and have been registered on a live run:

- **Great Place To Work** certified-company profiles (`greatplacetowork.com/certified-company/<id>`)
  publish a Trust Index percentage, the comparison against a typical company in the same
  country, the five highest-scoring survey statements, a tenure distribution and an
  "Updated <month year>" stamp — all in fetchable prose and JSON-LD.
- **Comparably, Built In, and regional "best places to work" lists** carry employer scores
  that republish with attribution.
- **The institution's own careers and culture pages**, at T4/T5 and needing corroboration,
  but dated and quotable.

Where such a source publishes a percentage and no response count, emit the row with `n`
null and say in the `note` that the publisher states the percentage and not the sample.
That is a rated line with a disclosed limit — which is what the reader needs — and it is
not the same as no line at all.

Where nothing survives, the tile still ships: `rows: []`, a `state` rung, and a
`sources_searched` ladder in which **every rung names its own refusal**, with the status
code where there is one. "Glassdoor — HTTP 403 to automated retrieval; a source that cannot
be fetched cannot be cited" is a finding. An empty tile is not.

One trap on this surface specifically: a **bureau grade is not a rating**. A BBB letter (C+)
and a regulator's supervisory status have no scale and no sample, so under the `n`/`scale`
rules they draw no bar. They belong in the ladder or in a `note`, never in a tile as a
number, however tempting a letter grade looks beside four stars.

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

**In flight is not the same as announced, and the row's own `status` says which.**
A deal at `ANNOUNCED` with no close date has moved no system, so it has taken no
capability away from the cells it names: the honest value is `NEUTRAL` with the
forward cost argued in `effect_note`. Asserting `TEMPORARILY_CONSTRAINED` before a
cutover is scheduled dates a constraint that has not started. Measured on a
promoted run, the row went the other way and shipped `maturity_effect: "negative"`
— a word from the timeline's `signal` vocabulary, not from this field's four, on
the same transaction the why-now was naming as the reason to act. Both halves are
AG-05 failures: the vocabulary and the direction.

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
Produce the acquisition history: dated events with integration state and effect on assessed capabilities. Per row: {closed_on, target_name, kind, status, scale_metrics,           integration_target, affected_subcap_ids[], maturity_effect, effect_note,           e_ids[]}   closed_on         REQUIRED to the month. Announced-but-not-closed is a                     SEPARATE row with status=ANNOUNCED and its own date.   status            ANNOUNCED │ INTEGRATING │ COMPLETE │ ABANDONED   scale_metrics     quantified in the acquirer's own terms: branches, deposits or                     loan volume, members/customers, FTE.   integration_target the date integration is tracking to, where stated.   maturity_effect   ADVANCED │ CONSTRAINED │ NEUTRAL │ TEMPORARILY_CONSTRAINED                     with the named cells. TEMPORARILY_CONSTRAINED is honest and                     often correct during a cutover; do not smooth it to NEUTRAL.   effect_note       20-45 words: what the integration does to the named                     capability and over what window - specific cell, direction,                     window. ENRICHMENT (mandatory - M&A is public and dated, so silence is not evidence)   - the acquirer's press releases and newsroom, by year   - regulator approval notices, which are dated and public: OCC/FDIC/Fed     applications, NCUA merger approvals, FCA territory and merger approvals   - trade press for the sub-vertical   - the target's final filings   - "[Entity] acquires OR merger OR acquisition OR purchases branches 2019..2026" Mint E-CC ids with url + verbatim excerpt + retrieval date. CROSS-SURFACE (emit once, hand to three) Every acquisition is also a TIMELINE event with kind=M&A; an integration in flight is a COST OF ACTING NOW input for the why-now and a timing constraint for the roadmap. All three must carry the same date and the same direction of effect. CHALLENGE  D Probes: an announced deal rendered as closed; a branch purchase described as a    whole-institution acquisition; an acquisition by a same-named entity; an    integration called complete while the timeline still shows cutover activity.  E REJECT -> drop the row rather than assert a status you cannot date. GATES: every row dated and cited; status never NULL; affected cells resolve; consistent with C1 and O3 (AG-05 - the same transaction carries the same direction on the timeline and is never a constraint on a card the why-now names as the reason to act).
```
