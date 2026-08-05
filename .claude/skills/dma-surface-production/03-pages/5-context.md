# Page: context

Five sections. INTERNAL ONLY — the whole dashboard is withheld from the customer audience, but that does not relax the identity gate or citation.

**5 sections · 5 surfaces.** Submit with `submit_page_payload(run_id, page='context', payload={...})`.

Read `01-start-here/1-standing-clauses.md` before writing any section on this page. The standing clauses apply to every section and are not repeated below.

## Sections on this page

| Section | Required | Surfaces | Renders on |
|---|---|---|---|
| `timeline` | yes | C1 | D5 |
| `issue_register` | yes | C2 | D5 |
| `regulatory_standing` | yes | C3 | D5 |
| `context_sentiment` | yes | C4 | D5 |
| `acquisitions` | yes | C5 | D5 |

---

## C1 · Digital evolution timeline

- **Section** `context.timeline` — **renders on** D5 (Context)
- **Contract** Chronological, year-range and signal filtered. Every event dated and cited; each expands inline to its detail.

### Must present

The client's technology history as dated events, each cited.

Every event dated; undated events are excluded, not rendered as 'ongoing'.

16 clients had two or fewer events — sparse timelines must declare themselves.

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| events[] | Research workbook + enrichment | {event_date, title, body, kind, e_id} |
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

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| issues[] | issue_register.csv | {issue_id, title, severity, status, opened_on, rationale, linked_subcap_ids[]} |
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

### Prompt

```
Produce the regulatory standing card. Treat it as the document's identity anchor. {primary_regulator, additional_regulators[], license_type, jurisdictions[],  charter_date, enforcement_actions[], absence_of_enforcement, e_ids[]}   primary_regulator                 the prudential regulator, from the regulator's OWN registry, not                 from the entity's self-description. By sub-vertical: SV1                 OCC/FDIC/Fed/State DOB · SV2 NCUA/State CU · SV4 SEC/FINRA/Fed/                 CFTC · SV5 SEC/FINRA/State securities · SV6 SEC/CFTC · SV7-SV8                 State DOIs/NAIC · SV9 FCA/FCSIC.                 An FDIC or OCC chip on a Farm Credit entity, or an FCA chip on a                 national bank, is an IDENTITY ERROR: quarantine the whole card                 and escalate, because it means the profile is contaminated.   license_type  as the registry states it ("National bank holding co.",                 "federally chartered credit union", "Agricultural Credit                 Association"). This constrains which products the entity may                 offer and therefore which capabilities can legitimately be                 assessed.   jurisdictions from the registry or the entity's filings. THE FASTEST                 CONTAMINATION CHECK IN THE PRODUCT: cross-check against every                 footprint claim on every other surface and flag disagreement as a                 contradiction, not as variation. ENFORCEMENT - search always; absence is a finding Per action: {issue_id, regulator, kind, opened_on, status, summary, capped_subcap_ids[], remediation_status, e_id}   Search EVERY applicable regulator's enforcement or order pages by entity name:   NCUA, OCC, FDIC, Fed, CFPB, SEC, FINRA, state DOI/DOB, FCA. Dated actions only.   capped_subcap_ids  which cells this action CAPS and at what level. An action                      that caps nothing has not been analysed.   Emit once, hand to the issue register (C2) and the why-now (O3); all three must   carry the same date.   absence_of_enforcement                      searched all applicable regulators and found nothing ->                      RECORD THE SOURCES SEARCHED. Verified absence supports the                      compliance-posture cell; unverified silence supports                      nothing. CHALLENGE  D Probes: regulator taken from marketing rather than the registry; a same-named    institution's action attributed here (verify the charter number / CIK / RSSD,    never the name); a closed action rendered as open; jurisdictions inconsistent    with any other surface.  E Any identity mismatch -> quarantine and escalate. Never render a partial    identity. GATES: G1 Identity & Boundary; G2 Regulatory Anchor; every action dated and cited; jurisdictions reconcile across surfaces.
```

---

## C4 · Sentiment overview

- **Section** `context.context_sentiment` — **renders on** D5 (Context)
- **Contract** The sentiment grid at Context depth, each tile expanding inline to the items behind it. Prototype-only; produced under the O9 sentiment prompt at Context depth.

### Prompt

No prompt exists in the design specification for this surface. Produce it from the contract above, the standing clauses and the seven-step form in `04-craft/5-prompt-standard.md`.

---

## C5 · Acquisition history

- **Section** `context.acquisitions` — **renders on** D5 (Context)
- **Contract** Closed and announced transactions with integration status and maturity effect. A temporarily-constraining integration is not smoothed to neutral.

### Prompt

```
Produce the acquisition history: dated events with integration state and effect on assessed capabilities. Per row: {closed_on, target_name, kind, status, scale_metrics,           integration_target, affected_subcap_ids[], maturity_effect, effect_note,           e_ids[]}   closed_on         REQUIRED to the month. Announced-but-not-closed is a                     SEPARATE row with status=ANNOUNCED and its own date.   status            ANNOUNCED │ INTEGRATING │ COMPLETE │ ABANDONED   scale_metrics     quantified in the acquirer's own terms: branches, deposits or                     loan volume, members/customers, FTE.   integration_target the date integration is tracking to, where stated.   maturity_effect   ADVANCED │ CONSTRAINED │ NEUTRAL │ TEMPORARILY_CONSTRAINED                     with the named cells. TEMPORARILY_CONSTRAINED is honest and                     often correct during a cutover; do not smooth it to NEUTRAL.   effect_note       20-45 words: what the integration does to the named                     capability and over what window - specific cell, direction,                     window. ENRICHMENT (mandatory - M&A is public and dated, so silence is not evidence)   - the acquirer's press releases and newsroom, by year   - regulator approval notices, which are dated and public: OCC/FDIC/Fed     applications, NCUA merger approvals, FCA territory and merger approvals   - trade press for the sub-vertical   - the target's final filings   - "[Entity] acquires OR merger OR acquisition OR purchases branches 2019..2026" Mint E-CC ids with url + verbatim excerpt + retrieval date. CROSS-SURFACE (emit once, hand to three) Every acquisition is also a TIMELINE event with kind=M&A; an integration in flight is a COST OF ACTING NOW input for the why-now and a timing constraint for the roadmap. All three must carry the same date and the same direction of effect. CHALLENGE  D Probes: an announced deal rendered as closed; a branch purchase described as a    whole-institution acquisition; an acquisition by a same-named entity; an    integration called complete while the timeline still shows cutover activity.  E REJECT -> drop the row rather than assert a status you cannot date. GATES: every row dated and cited; status never NULL; affected cells resolve; consistent with C1 and O3.
```
