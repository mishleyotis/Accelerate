# Page: overview

SECOND. Twelve sections. Needs the coverage and tier figures that fall out of the heatmap work. The hero is the only card guaranteed to be read.

**12 sections · 14 surfaces.** Submit with `submit_page_payload(run_id, page='overview', payload={...})`.

Read `01-start-here/1-standing-clauses.md` before writing any section on this page. The standing clauses apply to every section and are not repeated below.

## Sections on this page

| Section | Required | Surfaces | Renders on |
|---|---|---|---|
| `scores` | yes | O1 | D1 |
| `firmographics` | yes | O2 | D1 |
| `why_now` | yes | O3 | D1 |
| `exec_summary` | yes | O4 | D1 |
| `opportunity` | yes | O5 | D1 |
| `findings` | yes | O6 | D1 |
| `leadership` | yes | O7 | D1 |
| `financial_series` | yes | O8, C6 | D1, D5 |
| `sentiment` | yes | O9 | D1 |
| `ceilings` | yes | O1b | D1 |
| `evidence_coverage` | yes | O10, O11 | D1 |
| `thought_leadership` | yes | O12 | D1 |

---

## O1 · Scores &amp; peer benchmarks

- **Section** `overview.scores` — **renders on** D1 (Overview)
- **Contract** Composite to 1dp with its band word, four pillar scores with peer deltas, posture chip, evidence basis, and an 18–32 word framing sentence that states the gap, quantifies it and localises it.

### Must present

Overall maturity to 1dp in the hero ring, with its band word (Building, Competitive…).

Four pillar scores P1–P4 as a bar strip, each to 1dp with peer delta arrow.

Peer median per pillar and the cohort the median is drawn from.

Every number must equal the served cell to within one 2dp rounding step. The hero ring and the run row must render the SAME number — they are two views of one value.

### Read the cohort before you serve its median

The peer discipline this prompt states — same sub-vertical, ±50% asset size, same regulator
jurisdiction, no M&A distortion inside 24 months — describes how a cohort *should* have been
built. It does not certify the one in the workbook. The sub-vertical bands are wide enough
to hold a hundredfold size range, so a median drawn from the bottom of a band and rendered
against an entity at the top puts a confident delta arrow on all four pillars that no source
supports.

Check the cohort's own sizes against the entity's, and let the answer choose the basis:
inside ±50%, serve it and name the cohort; at an edge, recompute at lower N with the
ladder's floor-of-three arithmetic and emit `peer_n` so the reader sees the basis shrank;
a different size class entirely, `peer_basis = cannot_estimate` with the median null and the
reason stated. A missing tick is honest. `01-start-here/6-entity-shape.md` carries the
decision table.

**Some sub-verticals have no peer median to find, and that is structural rather than
missing.** Where the comparable institutions are private and none of them discloses, the
peer table cannot be repaired by searching harder — no rung of the ladder yields a figure
because no figure exists. What often does exist is a published *ranking* of those firms,
which is rung 4: a proxy that must disclose itself with the literal phrase *peer proxy* and
must never be presented as a median. Say which of the two you have. A hero that admits it
has no peer basis and states the entity's position on its own evidence is more use than one
whose arrows were manufactured to fill the strip.

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| overall_score | Scoring workbook | mean of the four pillar means, 2dp; never a flat mean of subcaps (those weight pillars by catalogue size) |
| pillar_scores[] | Scoring workbook | runs.workbook_scores.pillars, else the rollup of subcap_scores by LEFT(subcap_id,2) |
| peer_median | peer_comparison_table.csv | per-pillar cohort median |
| band | lib/maturity.ts | single source of truth for score→band→hex (ADR 0008) |

### Prompt

```
Produce the hero: composite, four pillar scores with peer deltas, posture, the framing sentence, and the firmographics strip. STEP 1 - READ, DO NOT DERIVE Scores come from the workbook. You never assign M1-M5. Read the composite as the mean of the four pillar means (NOT a flat mean of all sub-capabilities - those differ, and shipping both produced a hero ring and a run row that disagreed at 1dp on 26 clients). Round once, at 2dp, then present at 1dp: rounding to 2dp and then to 1dp is not the same function as rounding once, and .x5 ties diverge. STEP 2 - PEER FIGURES, WHERE THE TABLE HAS THEM Per pillar: {pillar_id, score, peer_median, delta, direction}. delta is signed and is computed, never restated from the source. STEP 3 - PEER FIGURES, WHERE IT DOES NOT  (in this order, stop at the first that yields a defensible number)   a RECOMPUTE AT LOWER N. Drop the peer lacking the figure; take the median of     the rest. Floor N=3. N=5 -> sorted[2]; N=4 -> mean(sorted[1..2]);     N=3 -> sorted[1]. Emit peer_n so the reader knows the basis shrank.   b ADJACENCY INFERENCE. A neighbouring sub-capability's evidence implies     something about this one. Label INFERENCE, state the reasoning in one     clause, widen the band.   c PROXY CEILING. LinkedIn specialist ratio <5% caps P1C4 at L2.5;     negative-dominant Glassdoor caps at L3.0. Lowest cap wins.   d STOP. Accumulated uncertainty over +/-0.8 -> "Cannot reliably estimate".     A point estimate past the cap is false precision, which is worse than a     declared unknown.   Disclose proxying with the literal phrase "peer proxy". NEVER write   "identical methodology". NEVER impute a value into the peer cell. The peer set   is immutable once selected: same sub-vertical, +/-50% asset size, same   regulator jurisdiction, no M&A distortion inside 24 months. STEP 4 - THE FRAMING SENTENCE  (18-32 words) State the gap, quantify it, and localise it to a pillar or a named capability. Model: "Trails regional bank peer median by -0.3 points. Gap concentrated in P4 Data foundation." Do NOT open with the composite - it is rendered beside you. STEP 5 - POSTURE LEADING │ COMPETING │ LAGGING │ MIXED, justified against the peer set, with the evidence basis chip (EVIDENCE / HYBRID / INFERRED) set from what actually backs the scores. STEP 6 - GRAIN ASSERTION (blocking) For every "<label> at N/5" you emit, resolve the label to a served cell and assert the score matches within +/-0.05. A mismatch is a grain_violation and the card does not ship. This is the most common defect in this product. STEP 7 - ENRICHMENT AND CHALLENGE (R-Layer)  A State the posture claim and its confidence.  B Search for what would refute it. At least one contradictory query:    "[Entity] digital transformation criticism OR delay OR failure".  C Is the posture reasonable for this sub-vertical, size tier and regulator?  D Probes: grain mismatch; identity contamination (every figure must be THIS    entity - check the domain on every source); Peer Outlier (a capability wildly    unlike peers needs its evidence re-verified); staleness.  E ACCEPT / REJECT / UNCERTAIN. UNCERTAIN ships with the band stated.
```

---

## O2 · Firmographics strip

- **Section** `overview.firmographics` — **renders on** D1 (Overview)
- **Contract** Assets, employees and branches rendered inside the hero rather than as a separate panel. Every figure identity-checked against the entity.

### Must present

Employees, revenue, AUM or assets, CAGR, HQ, branches, founded year, primary regulator, charter — each as value + provenance.

Every populated field shows where it came from; an unknown field renders an em dash, never a guess and never a dict repr.

Figures must be about THIS legal entity. A parent, subsidiary or same-name institution is a contamination, and the panel is quarantined rather than shown.

Magnitude sanity: an AUM or asset figure implying a market-scale absurdity is rejected (a $2.70T AUM on a mid-market manager was a real defect).

**The must-present set is a set, not a suggestion, and two of its members are the ones that go missing.**

- **CAGR belongs here.** The financial-series section's `cagr` column is unbound and
  computed at read; a producer-stated, cited CAGR is a firmographics field with its
  own `as_of` and `source_e_id`. If you want a sourced growth rate on the page, this
  is where it goes. If you want the computed one, send O8 ≥2 dated points.
- **Footprint is NOT a firmographics field.** The strip's footprint renders from
  `context.regulatory_standing.jurisdictions`, which is also the fastest
  contamination check in the product. An empty footprint on the overview is an
  empty `jurisdictions` on the context page — fix it there, and make the two agree,
  because a disagreement is a contradiction rather than variation.

`branches` is an integer count. Never a serialised list, never a dict repr — an
unknown field renders an em dash, and a dict printed into a strip is the one failure
mode a reader instantly distrusts.

### The registry that has the figure depends on who files, not on the sub-vertical alone

STEP 3's registry list assumes a filer. For an entity that files nothing, every route on it
misses and the panel comes back empty from a search that was run correctly — which is the
worst outcome available, because it looks like a verified absence.

Choose the route from the ownership shape as well as the sub-vertical:

| Shape | Where the firmographic actually lives |
|---|---|
| SEC registrant | 10-K/10-Q cover page and MD&A; the XBRL facts carry the period explicitly |
| Insured depository, unlisted | The regulator's call report — NCUA 5300, FFIEC/UBPR — quarterly, dated, T1 |
| Private, employee-owned | The trade press's annual ranking tables (dated third-party revenue for private firms); an ESOP's **Form 5500**, which is public, dated, and carries participant counts and plan assets; state licence and agency registries; the entity's own acquisition announcements, which usually disclose the *target's* revenue and headcount |
| Any insurance intermediary | The state departments of insurance the entity is licensed in, plus the NAIC producer database — these give licence type and jurisdictions, which is what C3 needs |
| Any affiliated adviser or broker-dealer | SEC Form ADV via IAPD, and FINRA BrokerCheck. A private group with a registered affiliate has dated public filings about part of itself |

**When the sub-vertical's must-present metric is genuinely undisclosed, the field is absent
with its route recorded — never modelled.** A private brokerage does not publish commission
revenue or producer count; an aggregator's estimate of either has no traceable source, so it
is an inference at best and it must be labelled one, not rendered as a figure with a
provenance chip. Absent beats wrong is not a fallback here, it is the answer: the strip
shows what the entity discloses, and the reader can tell the difference between a firm that
does not publish and a producer who did not look.

**Ownership is a firmographic and a contradiction site.** Where the entity's own site states
one ownership structure and a dated transaction states another — a recapitalisation that
brought minority investors in while employees kept the majority, say — the dated
announcement outranks the undated boilerplate, both are recorded, and the change of control
is a why-now signal and a C5 row as well as a field on this strip.

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| legal_name, founded, charter | Client Profile DOCX + run_manifest | firmographics narrative_md and the manifest's institution_name |
| employees, revenue, AUM, CAGR | Client Profile DOCX financial highlights; Clay | Clay inbound is HMAC-signed and fail-closed when the secret is unset (ADR 0010) |
| hq_address, branches | Client Profile DOCX; Clay | branches must be an integer count, never a serialised list or dict |
| primary_regulator | Assessment report / profile | stated, not inferred from charter |
| identity_mismatch | producer validator | set when a field's source names a different entity; quarantines the panel |

### Prompt

```
Produce the firmographics strip. Sub-vertical decides WHICH fields, not just what values. STEP 0 - CLASSIFY, THEN CHOOSE THE FIELDS Classification is regulator first, operating model second, revenue mix as tiebreak. Never by size, never by product names. First match wins; unmatched escalates rather than force-fitting.   SV1 Regional Banks $1B-$100B  total assets, deposits, loans, NIM, efficiency                                 ratio, NPL ratio   SV2 Credit Unions             total assets, SHARES, loans, net worth ratio,                                 ROA, MEMBER COUNT   SV3 Commercial Lending        loan portfolio, CRE concentration, C&I volume,                                 NPA ratio   SV4 CIB / Capital Markets     revenue by segment, trading revenue, IB fees,                                 AUM   SV5 RIAs & Broker-Dealers     AUM, client count, revenue, ADVISOR COUNT   SV6 Asset Management          AUM BY STRATEGY, fund performance, NET FLOWS,                                 expense ratios   SV7 Insurance Brokers         premium placed, commission revenue, PRODUCER                                 COUNT, acquisitions   SV8 Insurance Carriers        DWP, COMBINED RATIO, LOSS RATIO, investment                                 income, surplus   Farm Credit                   UNDEFINED in research. Do NOT borrow SV1's                                 metrics. Emit sub_vertical_undefined=true and                                 say so on the surface. Rendering "shares" for a bank or "deposits" for an RIA is a category error even when the number is right. STEP 1 - IDENTITY GATE (blocking, runs before any figure is accepted) For EVERY field: assert the source document is about THIS legal entity.   - match the legal name, not the trading name; resolve suffixes   - check the REGULATOR against the entity's own: an FCA figure on an     OCC-regulated bank is a different institution   - check the FOOTPRINT: a five-state Northeast footprint on a Utah bank is a     different institution   - check the ORDER OF MAGNITUDE against any other figure for the same metric     already on the pack. Two figures for one metric that differ by more than     25% are a contradiction to resolve, not two data points to render.   Any failure -> QUARANTINE the field. Emit it as absent with   quarantine_reason, never as a value. A measured case: one client shipped   $12.2B assets / FCA / NY-NJ-CT-MA-NH on the Overview while the hero and the   Context page both said $87.9B / OCC. Both cards rendered. That must fail. STEP 2 - RECENCY GATE (blocking) Every figure carries {value, as_of, source_e_id, recency_band}. No as_of, no render. Bands: CURRENT <18mo · RECENT 18-36mo · LEGACY >36mo · UNVERIFIED undated. A LEGACY figure may render ONLY with its date visible. An UNVERIFIED figure never renders as current. Report undated_pct for the panel. STEP 3 - ENRICHMENT (mandatory, not a fallback) Always search for a NEWER figure than the package holds, because the package is as old as the assessment:   - the authoritative registry for the sub-vertical: FDIC BankFind (banks),     NCUA Research (credit unions), OCC Bank Search, FFIEC NPW, SEC EDGAR     (10-K/10-Q), SEC IAPD + FINRA BrokerCheck (advisers/BDs), NAIC and AM Best     (insurers)   - the entity's own site: MANDATORY fetch - about page, newsroom, investor     relations, latest quarterly release   - LinkedIn for headcount; the careers page for footprint   - the newest quarterly filing, not the annual, when the metric is quarterly Mint E-CC ids with url + verbatim excerpt + retrieval date + tier + claim label. If enrichment finds a newer figure that disagrees with the package, the NEWER specific source wins (recent>older, specific>general) and you emit the contradiction row rather than silently replacing. STEP 4 - MAGNITUDE SANITY Compare against the sub-vertical's plausible range and against the entity's own prior-year figure. A regional bank at $2.70T is not a large regional bank, it is a parse error - one client shipped exactly that. Implausible -> quarantine, do not clamp. STEP 5 - EMIT Per field: {field, value, unit, as_of, recency_band, source_e_id, confidence, quarantined, quarantine_reason}. Absent beats wrong: a dash with a provenance note is honest; a plausible-looking wrong number is not.
```

---

## O3 · Why-now signals

- **Section** `overview.why_now` — **renders on** D1 (Overview)
- **Contract** Dated, cited events. Each carries trigger, window, consequence of waiting, cost of acting now and why this sequence.

### Must present

Three to six trigger cards, each a DATED external event with a kind pill, a one-line body and its E-ID.

Each signal answers 'why call them now' — a leadership change, an earnings move, a regulatory action, a technology announcement, an M&A event.

A signal is an EVENT, not a score read-out. 'P2 scores 2.4' is not a why-now.

No signal may be the assessment itself ('Zennify completed a Digital Maturity Assessment' shipped on 11 clients and is circular).

**`synthesis` is a REQUIRED field, not a closing flourish.** 60–110 words, one
paragraph across the signals: what the signals TOGETHER say about timing that no
single one says. The signals are the raw material; the synthesis is the product,
and it is why the card exists rather than being a list of recent news. It must be
consistent with `exec_summary.complication` and with the platform page's roadmap
phase 1 — three surfaces stating one timing argument.

Required **even on a thin card**: two signals still make a timing argument, and no
source states a thin exemption. A card that genuinely cannot carry one declares
`empty_state`.

**`cost_of_acting_now` is required per signal** and it is the field that gets
dropped. It is the honest other side — the concurrent commitment this collides
with, from the timeline, the issue register and the tech stack. A signal with only
upside is a pitch, and it is rejected. If the cost is genuinely low, state WHY it
is low; that is an argument, and "no cost" is not.

`linked_subcap_ids` renders: it is what ties the timing claim to the assessment
beneath it. A signal linked to no cell is news.

**On a disclosing entity the problem is the opposite of scarcity.** A public company
produces a dated, citable event most weeks, so the card fills with true, current,
irrelevant triggers and argues nothing. Select on the two things a why-now needs and
nothing else: a **dated window with something that closes it**, and a **consequence that
names a served cell**. An event with neither is news however recent it is. State the
selection basis on the surface — a reader who can see why these three of forty trusts the
three. `01-start-here/6-entity-shape.md` carries the selection keys per surface.

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| synthesis | producer | REQUIRED, 60–110 words; consistent with O4's Complication and P3's phase 1 |
| signals[].body | Research workbook + enrichment | dated timeline events within a 24-month lookback, most recent first |
| signals[].kind | producer classification | LEADERSHIP │ EARNINGS │ REGULATORY │ TECHNOLOGY │ M&A │ MARKET |
| signals[].event_date | the source | required; an undated signal is dropped |
| signals[].cost_of_acting_now | timeline, issue register, tech stack | REQUIRED, 30–55 words; a signal with only upside is rejected |
| signals[].linked_subcap_ids | catalogue | the tie to the assessment; renders on the card |
| signals[].e_ids | evidence store | at least one; uncited signals are dropped |

### Prompt

```
Synthesise why this entity should act now. This is the report's conclusion rendered as a card, not a changelog. Emit 2-4 signals. Per signal, ALL FIVE headers are required: {wn_id, trigger, window, consequence_of_waiting, cost_of_acting_now,  why_this_sequence, linked_subcap_ids[], e_ids[], dated_on, claim_label,  confidence}   trigger                25-45 words. WHAT CHANGED, dated to at least the                          month, cited. Ideal: a regulator action, a filing, a                          vendor milestone, a named executive hire, an M&A event.                          An undated trigger is not a trigger - drop it.   window                 20-40 words. How long the opening lasts AND THE EVENT                          THAT CLOSES IT, with its date. "Window closes at                          [named event], [quarter]". No closing condition means                          no window; say "no dated close established" rather                          than implying urgency you cannot support.   consequence_of_waiting 30-55 words. Which assessed capability degrades, in                          which direction, over what horizon. Name the cell.                          Ground it: a peer trajectory, a dated regulatory                          deadline, a contract expiry, a migration date.   cost_of_acting_now     30-55 words. REQUIRED. The concurrent commitment this                          collides with, drawn from the timeline, the issue                          register and the tech stack: a live core migration, an                          open consent order, an integration in cutover, a                          leadership vacancy. If the cost is genuinely low, state                          WHY it is low. A signal with only upside is a pitch and                          is rejected.   why_this_sequence      20-35 words. Why this is first rather than second, tied                          to the roadmap phase and any readiness gate. Then ONE synthesis paragraph across the signals, 60-110 words: what the signals TOGETHER say about timing that no single one says. This is the card's reason to exist. It must be consistent with the executive summary's Complication and with the roadmap's phase 1. SOURCES AND ENRICHMENT Start from the package: the assessment report's timing sections, the issue register, the timeline, leadership changes. Then ENRICH - the package is almost never current enough for a timing claim:   - every applicable regulator's enforcement and order pages (NCUA / OCC / FDIC     / CFPB / SEC / FINRA / state DOI), by date   - the entity's newsroom and investor relations, last 12 months   - "[Entity] core conversion OR migration OR go-live 2025 2026"   - "[Entity] names OR appoints CIO OR CTO OR CDO OR chief digital"   - M&A and charter events with dates   - the latest quarterly filing for forward-looking commitments Mint E-CC ids with url + verbatim excerpt + retrieval date. CHALLENGE (R-Layer)  B  Argue the opposite: why should they WAIT? If the wait case is strong, the     signal changes or goes. Run "[Entity] delay OR postpone OR paused     [initiative]".  D  Probes: Temporal Inconsistency (urgency asserted, metrics flat);     Marketing-Reality Gap (a vendor announcement read as a commitment);     Regulatory Divergence (the entity's framing vs the regulator's);     an event about a same-named different entity.  E  ACCEPT / REJECT / UNCERTAIN. Fewer than 2 defensible signals -> emit what     you have and set thin=true. Do NOT manufacture urgency to fill the card. GATES: S25_whynow_provenance (every trigger dated and cited); no undated trigger; cost_of_acting_now non-empty.
```

---

## O4 · Executive summary

- **Section** `overview.exec_summary` — **renders on** D1 (Overview)
- **Contract** Situation, complication, question, answer. At most one raw score, and client facts must outnumber score references.

### Must present

A Situation–Complication–Question–Answer narrative, 4 short paragraphs, that an AE can read aloud.

At most ONE raw score in the whole summary; the story carries the argument, not the arithmetic. 131/138 bodies once quoted two or more.

Every factual claim carries an E-ID. Client facts must outnumber score references.

Any score quoted must resolve to a served cell under the label used — quoting a category average under a subcapability's name is the O1/S23 grain defect.

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| scqa_md | Assessment report DOCX | executive_summary section, then the per-pillar deep dives for the Complication |
| cited_e_ids | research workbook | every claim's E-ID, validated against this run's evidence store |
| scores quoted | scoring workbook | must match the served cell ±0.05 at the grain named |

### Prompt

```
Write the executive summary as SCQA. It synthesises the corpus, not the scorecard. BEFORE WRITING, READ ALL OF: the four pillar deep-dives, the issue register, the peer table, the sentiment sources, the tech stack, the timeline, the recommendations and their phases. A summary written from the scores alone is the failure mode this card exists to avoid. {situation, complication, question, answer, sequencing_rationale,  cost_of_delay, e_ids[], claim_label}   situation     50-90 words. Where this client is, in terms they would use,                 anchored on ONE figure that is theirs (a firmographic, a                 trajectory, a footprint) - not a maturity score.   complication  70-120 words. THE CONSTRAINT, AS A MECHANISM. What is blocking                 what, and through what causal path. Must contain a causal                 connective (because / so that / which means / with the result                 that). If you cannot state a mechanism you have a measurement;                 go back to the deep-dives and find the mechanism.   question      25-45 words. The decision the client actually faces, in their                 voice. Not "how can we improve digital maturity".   answer        90-150 words. The sequenced recommendation. Name the                 recommendations by what they do, not by REC id. State what                 happens first and what it unblocks.   sequencing_rationale                 50-90 words. WHY THIS ORDER. The dependency, the readiness gate,                 or the window that fixes it. This is the judgement the client                 cannot make from the heatmap, and it is the highest-value                 sentence in the document.   cost_of_delay 40-70 words. What degrades if the sequence slips a year, tied to                 a named capability and a dated trigger where one exists. SAFEGUARDS (mechanical, checked before submit)   - NO sentence may consist of a score predicate ("X stands at N/5", "X scores     N", "X is rated N").   - AT MOST ONE numeric maturity score in the entire summary, and only where it     carries an argument.   - The complication MUST contain a causal connective.   - Every quantitative claim carries an E-ID.   - No internal codes (PxCy.z, E-nnn, REC-nn) in the client-visible prose - use     capability NAMES.   - Terminal punctuation on every field. 452 bodies across 136 clients shipped     without it. COHESION (blocking) The Complication must be the same constraint the Top findings rank first, the same one the Platform page's effort profile leads with, and consistent with the timeline's arc. If they disagree, one of them is wrong - resolve it before shipping, because the client reads all four. CHALLENGE (R-Layer)  B  What would make this summary wrong? If the complication rests on one     source, say so and lower confidence.  D  Probes: Input-Output Disconnect (investment claimed, outcomes flat);     CX Disconnect (internal metrics good, customer sentiment bad - that     contradiction is often the real complication); Peer Outlier.  E  ACCEPT / REJECT / UNCERTAIN. GATES: S26_exec_synthesis; S16_headline_score_quoting; S20_score_recap_register; S1_jargon.
```

---

## O5 · Opportunity surface tiles

- **Section** `overview.opportunity` — **renders on** D1 (Overview)
- **Contract** Where engagement value concentrates per platform, tied to the cells below M3 that the platform addresses.

### Must present

Five tiles naming where value is available, each with a headline, a one-line rationale and its anchor capability.

Prose must be whole sentences — tiles once shipped head-clipped mid-word.

Each tile names a capability in words and ties to a platform the client could use.

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| tiles[].headline | Assessment report + recommendations_detail.json | the gap framed as available value |
| tiles[].anchor_subcap_id | scoring workbook | the subcapability the tile is about |
| tiles[].platform | platform fit engine v2 | deterministic; the agent explains, never recomputes |

### Prompt

```
Produce the opportunity tiles: composite fit per platform, decomposable and validated. STEP 1 - COMPUTE, SHOWING THE PARTS composite = Σ(priority × gap) over the addressable cells, normalised 0-100. Emit {platform, composite, factors[], addressable_cells[], relevance, their_stack_context, rank, rank_rationale}   factors[]          {name, weight, value, contribution} and they MUST sum to                      the composite. The drilldown reproduces this arithmetic.   addressable_cells[] {subcap_id, name, current, peer, gap, feature_that                       _addresses_it}. Every cell must be one THIS run serves.   relevance          0-1, how relevant this platform is to THIS sub-vertical. STEP 2 - DISCARD (a ranking that cannot reject is a sort) Drop a platform when: relevance < 0.5 for the sub-vertical; the anchor cells belong to a different entity type (a carrier sub-capability on a bank); the client already runs it at the layer in question (that is an adoption conversation, not a fit conversation); or it addresses fewer than 3 cells. Emit discarded[] with {platform, reason} - a visible discard is evidence of judgement, and it is what an AE needs when the client asks "why not X". STEP 3 - FACTOR IN THEIR OWN STACK  (this changes the answer, not the framing) Read the tech stack register. A CONFIRMED platform at a layer removes that layer's greenfield opportunity and creates an extension one. An ABSENT platform with a demand signal (hiring, an RFP, a board commitment) RAISES priority. A platform mid-migration is a timing constraint on everything downstream. STEP 4 - VALIDATE AGAINST THE ASSESSMENT REPORT (blocking) Read the report's platform and recommendation sections. If the arithmetic's rank-1 is a platform the report does not discuss, you have a disagreement: resolve it, state which won and why, and lower confidence. Do NOT ship an arithmetic rank that contradicts the analyst without saying so. STEP 5 - CHALLENGE (R-Layer)  A State the rank-1 claim and its confidence.  B Argue for the runner-up. What would make IT first? If the margin is inside    5 points, present both and say the ranking is close.  C Is this platform plausible for this sub-vertical, size tier and regulator?  D Probes: out-of-vertical rank-1; anchor-cell entity-type mismatch; stale    fit figure (an exec_fit computed against a superseded run);    Tech Stack Mismatch (recommending what they already own).  E REJECT -> discard the tile and re-rank. Never keep a rank you cannot defend. STEP 6 - RANK RATIONALE  (25-45 words per tile) Why this platform sits at this rank, naming the cells it addresses and the constraint it lifts. Not a restatement of the composite. GATES: S13_platform_score_lead; S17_exec_fit_stale; S31_platform _distinctiveness; breakdown-equals-headline.
```

---

## O6 · Top findings

- **Section** `overview.findings` — **renders on** D1 (Overview)
- **Contract** Ranked findings, each with what, why and so what, a named consequence, a rejected alternative, and an inline expansion.

### Must present

Four to six findings, each a capability-named headline with a What/Why/So-what body and evidence chips.

The score chip and the anchor id must name the SAME cell. A subcap-grain score under a category id read '3.5/5' against a cell serving 2.77 on 59 clients.

The title must be a capability, not an evidence sentence, not a person's name, not a raw code, and not the body restated.

Bodies end in terminal punctuation and never repeat a sentence.

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| findings[].name | Client Profile focus areas; assessment report | a capability label, humanised — never 'P4C1' and never '[P2C3.2.IC1] Evidence' |
| findings[].subcap_id | scoring workbook | MUST be the cell whose score is quoted |
| findings[].score / peer_median | scoring workbook | that cell's own score, 2dp |
| findings[].e_ids | research workbook | at least one; uncited findings are dropped |

### Prompt

```
Produce the top findings. RETRIEVE them; derive only if retrieval fails. STEP 1 - RETRIEVE FROM THE RESEARCH AND ASSESSMENT REPORTS (first choice) Read 04_reports/Assessment_Report*.docx and the Client Profile research report in full. The analyst's key-findings, executive-summary and per-pillar conclusion sections already contain the findings; extract them with their reasoning intact. Record source_kind=retrieved with the section and page. STEP 2 - ONLY IF RETRIEVAL YIELDS FEWER THAN 5 Derive from the corpus - the joins, not the scores: a complaint theme against a process score, a job posting against a platform tenure, a regulator finding against a self-description, a timeline event against a capability. Record source_kind=derived. NEVER derive by taking the five widest score gaps; that produces a sorted list, not findings. STEP 3 - EMIT  (5 findings, each with EVERY field) {f_id, title, theme, consequence, body, rejected_alternative,  strategic_alignment, linked_subcap_ids[], platform_chips[], e_ids[],  source_kind, claim_label, confidence}   title         <=12 words. A CLAIM, and where possible one that rejects the                 obvious alternative in the same breath - the measured exemplar                 is "Data fragmentation is the root constraint, not                 under-investment". NEVER a capability name alone, never a                 score, never a person's name, never an evidence sentence, never                 a raw code.   theme         ONE of the client's own domains, upper-case, 1-3 words:                 DATA FOUNDATION │ WORKFLOW │ DECISIONING │ CHANNELS │ TIMING │                 RISK & COMPLIANCE │ OPERATING MODEL. This is the reader's                 orientation cue.   consequence   6-14 words, QUANTIFIED where the evidence allows. Measured                 exemplars: "Blocks 34 downstream subcaps"; "5-7 month cycle                 compression"; "Trails peer sentiment by ~0.8 stars"; "Window                 closes at nCino go-live". A consequence with no magnitude and no                 named event is not finished.   body          55-95 words. The argument: what is true, the mechanism by which                 it produces the consequence, and what it implies. Cited. Must                 NOT open with a score predicate.   rejected_alternative                 20-35 words. The competing explanation you considered and why                 the evidence favours yours.   strategic_alignment                 15-30 words PLUS a 0-1 score. Which of the ENTITY'S OWN stated                 strategic objectives this bears on, quoting the objective from                 their annual report, investor deck, strategic plan or CEO                 letter. This is the RANKING KEY. STEP 4 - RANK BY STRATEGIC ALIGNMENT, NOT BY GAP WIDTH Order by strategic_alignment score, tie-broken by breadth of downstream impact (how many cells it blocks), then by severity. The widest gap is frequently not the most important finding. State the ranking basis on the surface. If you cannot establish the entity's strategic objectives, SAY SO, rank by downstream impact, and set ranking_basis=impact_fallback - do not pretend to an alignment you did not establish. STEP 5 - NARRATIVE COHESION The five findings must read as ONE story in order: the root constraint, then what it blocks, then where the leverage is, then the timing. Emit narrative_thread, 45-75 words, tracing that line. If the five do not form a thread, you have five observations. STEP 6 - THE DRILLDOWN: FOUR HEADINGS, EACH WITH ITS OWN JOB The card face shows id, title, theme and consequence. The expansion carries the argument under exactly four headings. Every one is required; a heading present but empty is worse than the row not expanding.   WHAT     25-45 words. The STRUCTURAL FACT, then one concrete illustration the            client will recognise about themselves. Do not restate the title and            do not open with a score. The measured exemplar states three parallel            cores, then makes it real: "a customer with a mortgage, a deposit            account, and a card appears as three unrelated records." Cite.            Sub-parts, in order: (a) the fact; (b) the illustration; (c) the scope            where the evidence supports one (how many systems, how many records,            which lines of business).   WHY      25-45 words. THE MECHANISM, in three moves: (a) the CAUSE - usually            historical, and usually the most interesting sentence on the card            ("each core was retained through prior acquisitions rather than            consolidated"); (b) what has been done ANYWAY, which is where the            waste lives ("invested heavily in analytics on top"); (c) HOW it            propagates ("every downstream initiative inherits the fragmentation            underneath"). If you cannot name the cause, say so - an unexplained            fact is still a finding, but do not invent a history.            Where the mechanism is entitlement-without-adoption, say it in client            language ("the capability is bought but unused") and fire URF-04            internally; never print the URF code on a client surface.   SO WHAT  25-45 words. THE DECISION, in two moves: (a) the consequence of            sequence - what compounds if this is not done FIRST ("every CX            investment made before the substrate is fixed compounds the            problem"); (b) this finding's ROLE in the narrative - is it the            constraint, the fastest win, the proof point, or the timing gate? The            measured F-02 does this explicitly: "the fastest credible win ... it            builds the proof point for the larger data conversation." Name a            quantified benefit only where the evidence carries one ("a 5-7 month            cycle compression"), and name the procurement reality where it helps            ("a tool they already own, with no new procurement").            Never "consider investing in". Never a benefit with no source.   EVIDENCE one row per supporting item: {e_id, source_title, recency, tier,            claim_label}, each id resolving to the evidence store so the chip            opens the evidence drawer. The heading is a control ("EVIDENCE ·            CLICK TO VIEW"), so an unresolvable id is a dead control, not a            cosmetic issue. A finding with zero evidence rows does not ship. CROSS-HEADING CHECKS (run before emitting)   - WHAT states a fact; WHY explains it; SO WHAT decides. If two headings say     the same thing in different words, the card has one idea, not three.   - The consequence on the card FACE must be the same consequence SO WHAT argues.   - Every number in any heading resolves to a served cell or a cited source.   - No internal codes (PxCy.z, URF-nn, REC-nn) in any of the four headings. STEP 7 - CHALLENGE (R-Layer, per finding)  B  One contradictory query per finding: "[Entity] [area] failure complaint     outage criticism".  D  Probes: title-is-not-a-claim; grain mismatch between the quoted figure and     the named cell; Input-Output Disconnect; Marketing-Reality Gap; a finding     that restates another; a WHY that asserts a history with no source.  E  REJECT -> drop it and retrieve or derive a replacement. Fewer than 3     defensible findings on a completed run is a failure state, not an empty one. GATES: W1_workbook_fidelity (quoted score resolves to the named cell); S14_capability_gap_title; S14_jargon_title; S1_jargon; S20_score_recap_register; terminal punctuation.
```

---

## O7 · Leadership panel

- **Section** `overview.leadership` — **renders on** D1 (Overview)
- **Contract** Roster with role and tenure, or an explicit verified-absent state naming every source searched.

### Must present

The executives who matter to this conversation: name, title, tenure signal, and what they own that the assessment touches.

An empty roster must be an explicit verified_absent, not a silent blank.

Measured on a real run: **25 words per person**. A roster entry whose
`relevance_note` restates the title is an org chart row.

### The contact route is established HERE, or it does not exist

`roster[*].email`, `.linkedin_url`, `.phone`, `.enriched_at`, `.enrichment_basis`
are real columns and the panel renders them beside the name.

**The app makes no third-party call while serving** (invariant 1). There is no
"fetch it when the AE clicks" — the click reads a stored row in milliseconds
because you established it during synthesis. A contact route you do not establish
now is a route that does not exist for the AE, and the panel says so honestly
rather than offering a button that cannot work.

**`enrichment_basis` is not decoration.** "Clay reports it" is not a source; the
filing or profile Clay surfaced is. Without a basis, the contact route is the one
field on this panel asserting something with no provenance. Where a tool returns
a value whose origin it does not name, the value is an inference — label it as one
or leave it out.

**A name-similar match is an identity FAILURE, not a near-miss.** Measured: a
search for six named executives returned five correct matches and, for a named SVP
Chief Data Officer, an INTERN with the same surname at the same employer.
Attaching it would have put an intern's email on a Chief Data Officer's row. The
check is that the returned TITLE matches the person you searched for — surname and
employer are not identity. On failure, quarantine the field with its reason.

### Who the panel is about changes with the entity's shape

STEP 2's ladder leans on proxy statements, Section 16 and press releases. Two shapes break
it in opposite directions.

**A private entity files none of them.** The routes that do exist are the entity's own
leadership and governance pages, every acquisition announcement (which names the acquired
firm's leaders and usually the executive who sponsored the deal), state licence registries —
which name an agency's designated licensed producer, a real accountable individual —
conference programmes, and an ESOP's Form 5500, whose plan administrator and trustees are
named officers. None of them is a proxy statement and together they establish the panel. An
empty roster on a 3,000-person firm is a search that stopped at rung two.

**A multi-brand entity has too many candidates, not too few.** Seven branded segments have
seven presidents, and none of them is the answer to "who owns this decision" at enterprise
grain. Scope the roster to the accountability the assessment touches: the enterprise
technology, operations, data and risk owners, plus the affiliate leader only where the
assessment itself is scoped to that affiliate — and say which scoping you applied, because
a reader who sees three of seven brand presidents will assume the other four were missed.

Both shapes make STEP 3's recency rule load-bearing rather than procedural. A technology
leadership change is announced, dated and public; the roster verifies every name against the
current leadership page and marks the departure, because a stale executive name is worse
than a gap — the AE will use it, and the client will know within one sentence that the work
is old.

Full playbook, call budget and tier map: `02-inputs/2-clay-enrichment.md`.
Ownership and brand shape: `01-start-here/6-entity-shape.md`.

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| roster[] | Client Profile DOCX | paragraph form OR a 5-column table — both shapes occur in real packages |
| roster scope | producer | stated: enterprise accountability, or an affiliate the assessment is scoped to |
| roster[].relevance_note | producer | 10–25 words: which capability this person owns and what they have said about it |
| roster[].email / .linkedin_url / .phone | enrichment, at synthesis time | stored; the app makes no call at serve time |
| roster[].enrichment_basis | the filing or profile the tool surfaced | never the tool itself |
| roster[].enriched_at | producer | when the route was established |
| verified_absent | producer | true only after the profile was read and held none |

### Prompt

```
Produce the leadership roster. An empty panel on an assessed entity is a failure state. STEP 1 - PACKAGE FIRST The Client Profile research report renders leaders in paragraphs OR in a table (one real fixture uses a 5-column table). Parse both shapes. STEP 2 - ENRICH UNTIL THE PANEL IS NOT EMPTY (mandatory)   - the entity's own leadership / about / governance page: MANDATORY fetch   - the latest proxy statement or annual report governance section   - "[Entity] names OR appoints OR promotes CIO OR CTO OR CDO OR chief digital     OR chief information", with year markers 2024 2025 2026   - LinkedIn: current holders of the relevant titles   - press releases for the last 24 months   - conference speaker listings and panel bios   - regulator filings that name officers Mint E-CC ids with url + verbatim excerpt + retrieval date. STEP 3 - RECENCY VALIDATION (blocking per person) Every entry carries as_of and a verification source. A name with no verification date does not render. Cross-check against the CURRENT leadership page: if the person is absent there, mark departed and remove them from the roster - a stale executive name is worse than a gap, because the AE will use it. Emit tenure where the source gives a start date. STEP 4 - THE DIGITAL-OWNERSHIP QUESTION The panel exists to answer "who owns this decision". For each relevant domain (data, digital channels, technology, risk) name the accountable executive, or state that no owner was established. If there is no CDO/CIO equivalent, run ALL FIVE proxy searches (board bios, C-suite digital hires, LinkedIn digital titles, conference talks, strategic-plan filings) BEFORE recording the absence - and then record the absence WITH the sources searched, because a genuine vacancy at that level is itself a finding that bears on P1C4 and belongs in the why-now. STEP 5 - EMIT {name, title, domain, appointed_on, tenure_months, as_of, source_e_id,  relevance_note, confidence}   relevance_note  10-25 words: why this person matters to THIS assessment -                   which capability they own, what they have said publicly about                   it. A roster without relevance is an org chart. STEP 6 - CHALLENGE  D Probes: a same-named person at a different institution (check the domain on    every source); a title that exists on the site but is vacant; an    announcement of an intention to hire read as a hire; a bio cached from a    prior employer.  E Never ship a name you could not verify against a current source. GATES: no empty roster on a completed run; every entry dated; identity checks.
```

---

## O8 · Financial trajectory

- **Section** `overview.financial_series` — **renders on** D1 (Overview)
- **Contract** A dated series. Below three points it renders as a labelled snapshot with no trend line.

### Must present

A multi-year dated series (assets, revenue or AUM) rendered as a trend, with the metric named and each point dated.

A trend word (improving, stable, declining) only when the series supports it.

Two points is not a trajectory — thin series must declare themselves.

**`reading` is a REQUIRED field.** 35–60 words: what the trajectory means for THE
ASSESSMENT — whether the growth outpaces the digital capability that has to support
it. That question is the card's reason to exist. It is not a restatement of the
series and not a restatement of the trend word; both are already on the card.

Measured on a real run: **22 words for the whole card.** A financial series with no
reading is a chart, and the AE has to supply the argument in the room.

**This section serves BOTH O8 and C6.** The Context page's financial card renders
this same section — the same row, the same `reading`. So it is written once and
cannot disagree with itself, and there is nothing to produce on the context page.

### Three columns exist and you must NOT send them

The instinct to fill a column that exists is the failure mode here. Each of these
is unbound deliberately:

| Do not send | Why |
|---|---|
| `basis` at section level | Basis is stated PER POINT, because mixing metric definitions across periods produces a fake trend. A section-level copy is a second place the definition can disagree with itself |
| `cagr` | **Computed at read** from the series' first and last dated points over the real number of years between them (invariants 8 and 9). Send ≥2 dated points and it appears; send one and it correctly does not. A producer-stated, cited CAGR belongs on `firmographics.fields[]`, whose must-present set names CAGR |
| a rounded or pre-formatted value | The card formats; you send the figure and its unit |

So: **CAGR is a firmographics field, not a series field.** If you want a cited CAGR
on the page, put it there with its `as_of` and `source_e_id`. If you want the
computed one, send the dated points and the app does the arithmetic.

Where the identity gate quarantines the series, declare `empty_state` and emit
`quarantine_reason` instead — a quarantined series never renders, so it has no
reading.

### A filing states the same metric several ways. `basis` is what stops that becoming a trend.

STEP 1 says the basis is the metric definition and that mixing definitions across periods
produces a fake trend. On an annual report that is a mild risk; on a 10-K it is the default
outcome, because one document states **period-end** total assets, **average** assets for the
period, assets by reportable **segment**, and often a restated prior-year figure — all
correct, all different, all labelled "total assets" in a table heading somewhere.

So fix the definition once and hold it across every point: period-end, consolidated, as
reported for that period. Name it in `basis` on each point rather than assuming the reader
infers it, and never mix a segment or affiliate figure into an enterprise series — a
branded segment's assets are a fact about that segment. Where a filing restates a prior
year, the restated figure and the originally reported one are a disagreement resolved by
recency, recorded, not averaged.

### When nothing is filed, the series comes from somewhere else or it is honestly sparse

The ladder in STEP 4 terminates at rung one for an entity that files nothing, and stopping
there produces `verified_sparse` on a firm whose figures are actually public. Before you
declare a snapshot, take the ladder to the shapes that carry private figures: the trade
press's annual ranking tables, which publish dated revenue for private firms year on year
and give a genuine multi-point third-party series; an ESOP's Form 5500; the entity's own
acquisition announcements, which disclose scale in the acquirer's terms; and rating-agency
commentary where the entity carries rated debt.

Two disciplines follow. A ranking table's figure is a **third-party estimate unless the
publisher says the firm reported it** — label the claim accordingly, and do not silently
promote an estimate to a fact because it appears in a table. And a series built from a
ranking table is a series about *revenue as that publisher defines it*: same definition
across points, same `basis` string, or it is two metrics in one line.

Where the entity genuinely discloses nothing across time, `verified_sparse` with the routes
recorded is the right answer and the `reading` still gets written — what a firm's scale and
trajectory imply for the capability that has to support it does not require three points to
say, only honesty about what it rests on.

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| series[] | Client Profile financial highlights; assessment report | {period, value, unit, as_of, source_e_id, basis} per point — basis per point, never section-level |
| reading | producer | REQUIRED, 35–60 words; serves O8 AND C6, so written once |
| trend | computed from the series | `GROWING │ STABLE │ DECLINING │ VOLATILE`; null below 3 dated points |
| CAGR | **computed at read**, or cited on firmographics | never sent on this section |
| verified_sparse | producer | set when the sources hold fewer than 3 points |

### Prompt

```
Produce the financial trajectory: a dated series, a trend label, and the validation that makes both trustworthy. STEP 1 - BUILD THE SERIES {period, value, unit, as_of, source_e_id, basis} per point, oldest first. basis is the metric definition (total assets / DWP / AUM / premium placed) taken from the sub-vertical - see O2. Mixing definitions across periods is a silent error that produces a fake trend. STEP 2 - IDENTITY GATE (blocking, per point) Assert every point is THIS legal entity: legal name, REGULATOR, and FOOTPRINT must all match the entity's own. A measured failure on this very card: an Overview series of $9.8B->$12.2B carrying regulator FCA and a NY-NJ-CT-MA-NH footprint, on an OCC-regulated Utah bank whose other two surfaces both said $87.9B. Any mismatch -> QUARANTINE the series, render the honest empty state, and emit quarantine_reason. Never render a quarantined series. STEP 3 - CROSS-SURFACE RECONCILIATION GATE (blocking) Before submitting, compare this metric against EVERY other surface in the pack that carries it: the hero firmographics strip, the Context trajectory, the peer table, the report narrative. Any two figures for the same metric and period differing by more than 25% is a contradiction. Resolve it by recent>older, specific>general, T1>T2>T3, and emit the resolution row. If you cannot resolve it, quarantine BOTH rather than shipping two numbers that disagree on one client. STEP 4 - RECENCY GATE AND MANDATORY ENRICHMENT The package is as old as the assessment, so ALWAYS search for a newer figure:   - the latest 10-Q/10-K on SEC EDGAR, or the sub-vertical's registry: FDIC     BankFind, NCUA Research, FFIEC NPW, NAIC, AM Best   - the entity's investor-relations page and most recent quarterly release   - "[Entity] total assets OR AUM OR direct written premium Q1 OR Q2 2026" If a newer figure exists, it becomes the headline and the older ones become the series. Mint E-CC ids with url + verbatim excerpt + retrieval date. Every point renders with its as_of; an undated point does not render. STEP 5 - MAGNITUDE SANITY Check each point against the sub-vertical's plausible range and against the adjacent periods. A single point 7x its neighbours is a parse or identity error, not growth. One client shipped $2.70T AUM from a parse error. Implausible -> quarantine, never clamp. STEP 6 - TREND LABEL GROWING │ STABLE │ DECLINING │ VOLATILE, computed from the series, with the CAGR where 3+ dated points exist. FEWER THAN 3 DATED POINTS -> no trend label at all; emit trend=null, verified_sparse=true, and label it a snapshot. A trend drawn from two points is a line, not a trajectory. STEP 7 - EMIT THE READING  (35-60 words) What the trajectory means for the assessment: does the growth outpace the digital capability that has to support it? That question is the card's reason to exist. Cite. GATES: S6_financials; S27_financial_series (>=3 dated points or verified_sparse); S24_firmo_integrity; cross-surface reconciliation.
```

---

## C6 · Financial trajectory

- **Section** `overview.financial_series` — **renders on** D5 (Context)
- **Contract** Renders the Overview's financial series section. One section, so the two cards cannot disagree.

### Prompt

**There is nothing to produce.** C6 is the same section rendered on a second page —
the same row, the same `series`, the same `reading`. Produce O8 above and C6
follows. Writing a second version is how the two cards come to disagree, and there
is no second row for it to land in.

---

## O9 · Sentiment

- **Section** `overview.sentiment` — **renders on** D1 (Overview)
- **Contract** Bars plus context tiles, each tile expanding inline to the items behind it.

### Must present

The prototype's design, which is the contract: source-level rating BARS grouped by audience on the Overview, and an interactive three-tile grid with drilldowns and evidence chips on Context.

Each bar names its source, its rating and its sample size.

A single displayed line is not a sentiment picture — thin sources declare themselves.

The invented card style that shipped on D1 is not in the design package and must not return.

### `themes` and `gap_analysis` are the analysis, and they are now writable

Until recently the contract had no fields for them, so whatever was submitted was
discarded at promotion and the card rendered with nine words on it. That was not
producer laziness — the column existed and nothing bound it. Both are bound now, so
STEP 3 and STEP 4 of the prompt below finally land somewhere.

`themes[]` — two to four per audience, extracted from the review and complaint
**TEXT**, not from the star rating. Per item `{audience, theme, mapped_subcap_ids,
cap_statement}`. `cap_statement` is PROSE and it names which cell this sentiment
caps and at what rubric level, with the cause distinguished. The measured exemplar
distinguishes process from service, and that distinction is what makes it usable:

> Below industry median (43). Most complaints relate to ACH processing delays, not
> service quality. Caps P2C2.1.1 at M3.

Sentiment that connects to no assessed capability is decoration. Sentiment that
caps a cell is evidence.

`gap_analysis` — `{b2b_b2c, internal_external, e_ids}`, conditional by
construction: omit it when only one audience was established. The Overview's
"B2B/B2C gap" chip is computed at render from `b2b_b2c` being non-empty; it is
never a stored boolean.

### SG-S8 discloses. Thinness is stated, not hidden.

A single rated line trips **SG-S8**, which **discloses and still promotes** — the
client reads *"Sentiment rests on a single source, so treat it as indicative
only"*. The gate computes the count from `bars[]` at submit and **never reads
`displayed_lines`**; that field exists for the renderer. A self-published NPS
standing alone is thin whatever the count.

Two consequences: a row with no `rating` is not a line of sentiment — it belongs in
`sources_searched` — and a source that blocks automated retrieval cannot be cited
at all. Glassdoor, Indeed and ZipRecruiter all 403, so they are rungs in the ladder
rather than evidence ids. See `01-start-here/2-evidence.md`.

### A multi-brand entity has several ratings and no average

Where the institution trades under more than one brand, each brand has its own app listing,
its own review pages and often its own complaint history. Four ratings are four sources.
Averaging them produces a figure that is in no source — the same fabrication the
never-average rule forbids between two disagreeing figures, and here it also destroys the
finding, because the *spread* between brands is usually what the sentiment is telling you.

Render them as separate rated lines with the brand named in `source`, and let the theme
carry the comparison: a channel rated a point apart across two brands of one institution is
a statement about how unevenly the channel was built, and it caps different cells for
different parts of the estate. Complaint records filed under the legal entity are
enterprise-level and belong in their own line, labelled as such.

**This dataset is also C4.** The Context page re-projects these same ratings as
three expandable tiles, reconciled by `e_id` and `rating`. Produce this section
first; C4 projects it and can never disagree with it.

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| bars[] | Research workbook sentiment rows; enrichment | {audience, source, rating, scale, n, as_of, url, e_id, trend_vs_prior} — customer, employee, industry |
| themes[] | the review and complaint TEXT | {audience, theme, mapped_subcap_ids, cap_statement}; 2–4 per audience |
| themes[].cap_statement | producer analysis | prose naming the cell and the rubric level, cause distinguished |
| gap_analysis | producer | {b2b_b2c, internal_external, e_ids}; omitted when only one audience exists |
| displayed_lines | producer | for the renderer only — SG-S8 recomputes and does not read it |
| `metric` | **no such key** | a prototype leftover named by no source; must not be emitted |
| context_tiles[] | **not this section** | C4 owns them — `03-pages/5-context.md` |

### Prompt

```
Produce the sentiment surface: per-audience ratings that each terminate in an assessed capability. STEP 1 - COLLECT ACROSS ALL SEVEN SOURCE FAMILIES (do not stop at one)   1 Apple App Store   rating, n, scale, latest release date   2 Google Play       rating, n, scale, latest release date   3 Glassdoor         overall + the sub-ratings that bear on execution   4 Indeed            where Glassdoor is thin   5 CFPB complaint narratives  by product, with counts - the complaint TEXT is                       the analysable part, not just the count   6 BBB               complaint themes and resolution behaviour   7 Trustpilot / Google reviews  where the entity has presence Plus: J.D. Power and Forrester rankings where the entity appears (T3), and any NPS the entity publishes itself (T4/T5, needs corroboration). STEP 2 - EVERY RATING CARRIES ITS INTERPRETABILITY FIELDS {audience, source, rating, scale, n, as_of, url, e_id, trend_vs_prior} No n -> not a signal, do not render a number. No scale -> the rating is meaningless (4.1 out of what?). No as_of -> UNVERIFIED recency, never rendered as current. n below 30 -> render with a low-sample warning, not as a finding. STEP 3 - THEMES, MAPPED TO CAPABILITIES (this is the analysis) Extract 2-4 recurring themes per audience from the review and complaint TEXT, not from the star rating. Map each theme to the pillar and cell it bears on:   onboarding / account opening friction        -> P2C3, P2C1   transfer, payment and processing delays      -> P3C2, P2C2   manual and spreadsheet-heavy internal work   -> P3C1, P3C3   data and personalisation complaints          -> P4C1, P4C2   app stability and release cadence            -> P2C1   advice and service quality                   -> P2C2 Then state the CAP: which cell this sentiment caps and at what level. Measured exemplar: "Below industry median (43). Most complaints relate to ACH processing delays, not service quality. Caps P2C2.1.1 at M3." Note that the exemplar also DISTINGUISHES the cause - process, not service - which is what makes it useful. Negative-dominant employee themes cap P1C4 and P4C3 at L3.0. Mixed themes add +0.2 uncertainty. Record which. STEP 4 - THE B2B/B2C AND INTERNAL/EXTERNAL GAPS Where both sides exist, state the GAP and what it implies. An employee rating well above the customer rating says the constraint is not capability but process; the reverse says delivery is outrunning the operating model. One measured exemplar reads "Engineering scores 4.2 - front-line ops scores 3.1", which localises the constraint inside the organisation. STEP 5 - RECENCY An app not updated in over 6 months is a flag in itself. Sentiment older than 18 months is RECENT not CURRENT; older than 36 is LEGACY and must not be presented as the current picture. STEP 6 - HONESTY If only one source exists after searching all seven, emit it and let the thin-source state show. Do NOT synthesise a second audience to fill the grid. One source should be rare. CHALLENGE (R-Layer)  D Probes: CX Disconnect (internal metrics good, customer sentiment bad - that    contradiction is a finding, surface it as one); a rating from the wrong app    (check the publisher); reviews for a same-named different entity; a sample    too small to mean anything; a rating average that hides a bimodal split.  E UNCERTAIN -> ship with n and scale visible and confidence LOW. GATES: SG-S8 (discloses, does not block: computed from the rating rows at submit, never from a declared displayed_lines; self-published-NPS-only is thin whatever the count); AG-03 per bar and per theme; every rating carries n + scale + as_of; every theme maps to a served cell; reconciles with context.context_sentiment.context_tiles by e_id and rating.
```

---

## O1b · Capability ceiling &amp; uncertainty

- **Section** `overview.ceilings` — **renders on** D1 (Overview)
- **Contract** Per category, the highest level the evidence would support under perfect execution, its uncertainty band, and the named absence that set it.

### Prompt

```
Produce the capability ceiling and uncertainty table: one row per category. A CEILING IS NOT A SCORE. It is the highest maturity level the available evidence would support even under perfect execution. You never assign scores; you state what the evidence can and cannot reach. Per row: {category_id, category_name, ceiling, uncertainty_band, rationale,           limiting_absence, urf_modifiers[], e_ids[], claim_label, confidence}   ceiling           M1-M5, set by the BEST evidence available and capped by its                     tier: T1/T2 -> up to L5 · T3 -> L4 · T4 -> L2.5 · T5 -> L2                     and only with corroboration. A ceiling can never exceed the                     cap of its best tier.   uncertainty_band  the +/- figure: base band plus URF modifiers. URF-01                     Capability Plateau +0.2 · URF-02 Adoption Gap +0.2 · URF-03                     Stagnation +0.1 · URF-04 Entitlement Underutilisation +0.2 ·                     URF-05 Shadow Systems +0.2 · URF-06 Peripheral Tool +0.1.                     Name every modifier applied. OVER +/-0.8 -> emit                     ceiling=null and "Cannot reliably estimate". A point estimate                     past the cap is false precision, which is worse than a                     declared unknown. A band under +/-0.3 on a single-source                     category is overconfident.   rationale         35-70 words with TWO halves, both required:                     (a) what the evidence DOES establish, cited;                     (b) the specific thing whose ABSENCE set the ceiling.   limiting_absence  the artefact that would raise the ceiling if found - a named                     document, metric or organisational unit. This is the research                     backlog for the next run, so make it searchable. ENRICH BEFORE SETTLING ON A LOW CEILING A ceiling set by absence obliges you to have looked. Before emitting a ceiling below M3 on an absence, run ladder tiers 1-6 for the limiting_absence specifically, plus the five mandatory organisational proxies where the absence is organisational (board bios, C-suite digital hires, LinkedIn digital titles, conference talks, strategic-plan filings). Mint E-CC ids for anything found and RAISE the ceiling if the evidence supports it. CHALLENGE (R-Layer)  B  What would raise this ceiling? Search for it explicitly. A ceiling you have     not tried to break is an assumption.  C  Is the ceiling plausible for this sub-vertical, size tier and regulator? A     Nano-tier entity is not expected to evidence a transformation office - the     context adjustment applies to the EXPECTATION, not to the evidence.  D  Probes: tier misclassification capping artificially (a machine scan filed as     T4 caps at L2.5 - the most common suppression in this corpus); the absence is     of something this sub-vertical does not have (never cap a Farm Credit     association for lacking a deposit channel it cannot legally operate);     an overconfident band.  E  ACCEPT / REJECT / UNCERTAIN. GATES: G14 Ceiling Estimate Framing; +/-0.8 cap enforced; every ceiling cited.
```

---

## O10 · Evidence coverage

- **Section** `overview.evidence_coverage` — **renders on** D1 (Overview)
- **Contract** Overall and per-pillar against the 80% hard gate, with the denominator definition rendered. Never rounded up across the gate.

### Prompt

```
Produce the evidence coverage instrumentation. {overall_pct, per_pillar[{pillar_id, pillar_name, pct, cells_total,  cells_covered, below_gate}], gate_pct, denominator_definition, note}   denominator_definition                 REQUIRED and RENDERED. State exactly what is counted: "share of                 scored sub-capabilities carrying at least one linked evidence                 item" is a different metric from "share meeting the three-item                 sufficiency threshold", and the two differ by tens of points.   gate_pct      80. A HARD GATE, not a target.   below_gate    true per pillar under the gate, rendered distinctly. An overall                 96% with one pillar at 62% is a failing assessment presented as a                 passing one.   note          15-30 words where any pillar is below gate: which cells drive it                 and what would close them. Otherwise omit. COMPUTE, DO NOT ESTIMATE Count from the served cells and their linked evidence, per pillar, over the SAME cell set the heatmap serves. A coverage figure computed over a different denominator than the heatmap renders is a contradiction the reader can find by counting. HONESTY Never round up across the gate: 79.6% renders as 79.6% with below_gate=true. Coverage counts LINKED evidence only - an item that resolves to no cell counts nowhere. A cell whose only evidence is undated DOES count toward coverage but is reported in the evidence age tracker; coverage and freshness are different questions and must not be merged. GATES: denominator stated; per-pillar breakdown present; no rounding across the gate; reconciles to the heatmap's cell set.
```

---

## O11 · Evidence tier distribution

- **Section** `overview.evidence_coverage` — **renders on** D1 (Overview)
- **Contract** Tier and claim-class histograms, plus what vocabulary this mix licenses across the whole document.

### Prompt

```
Produce the evidence tier and claim-class distribution. This is a census; it has no editorial layer. {item_count, fact_count, tiers[{tier, count, pct, max_evidence_level}],  claim_classes[{claim_label, count, pct}], self_sourced_pct, mix_implication}   item_count vs fact_count                 distinct and both reported. One annual report is ONE item                 carrying many facts with ids E-xxx:Fy.   max_evidence_level per tier                 T1/T2 -> L5 · T3 -> L4 · T4 -> L2.5 · T5 -> L2 (corroboration                 required). RENDER it, because it is what the mix means.   self_sourced_pct                 share of items from the entity's OWN publications (annual report,                 site, press releases). Above ~50%, corroboration is structurally                 weak regardless of the tier histogram, because same-institution                 documents are one source. Flag it.   mix_implication                 25-50 words. THE POINT OF THE CARD: what vocabulary this mix                 licenses across the whole document. A T3-dominant mix licenses                 "likely uses / signals suggest" and NOT "uses". A T5-heavy mix                 licenses almost nothing without corroboration. Say it plainly so                 the reader can hold the other surfaces to it. CHALLENGE  D Probes: machine scans (Hubbl / BuiltWith / Wappalyzer / Explorium) filed as T4    rather than T1 - this understates T1 AND suppresses ceilings, and it is the    most common misclassification in this corpus; a ceiling_estimate count of    zero, which usually means ceilings were asserted as facts rather than    labelled.  E Recount rather than adjust. GATES: item and fact counts both present; tier ceilings rendered; mix_implication non-empty; counts reconcile to the evidence store.
```

---

## O12 · Thought leadership signal

- **Section** `overview.thought_leadership` — **renders on** D1 (Overview)
- **Contract** Dated executive publications with verbatim quotes. A contradicting entry is the most valuable row on the card and is never filtered out.

### Where the entity holds earnings calls, the card's constraint is selection

Four transcripts a year, each with prepared remarks and an analyst Q&A, is a standing supply
of dated, attributed, verbatim executive statements — and the fastest way to fill this card
with quarters of guidance language that bears on no assessed capability. Admit an entry
because it **corroborates, contradicts or extends a finding**, not because it is the most
recent thing said. A transcript quote still needs `linked_subcap_ids`, and a call in which
nothing was said about the assessed capabilities is a call this card does not use.

For a private entity none of this exists, and the routes that do — conference programmes,
association speaking slots, trade-press bylines, an executive's own posts — are the ladder
in `01-start-here/4-absence-protocol.md`. Run all of it before `thin=true`: an entity with
no filings still has executives who speak in public, and this card is the one place their
words become evidence.

### Prompt

```
Produce the thought-leadership signal: the client's executives, in their own words, on the assessed capabilities. ENRICHMENT-FIRST. The package will not contain this. Search:   - LinkedIn posts and articles by named executives from the leadership roster   - conference agendas, panel listings and session abstracts, by year   - podcast and webinar appearances   - by-lined articles and trade-press contributions   - earnings-call transcripts for CIO/CTO/CDO commentary   - the entity's blog where posts are attributed to an executive   - association and user-group speaking slots Query with the executive's NAME plus the entity, with year markers. Mint E-CC ids with url + verbatim excerpt + retrieval date + tier + claim label. Per entry: {kind, published_on, headline, quote, author_name, author_role, url,             linked_subcap_ids[], alignment, e_id, claim_label}   kind            LINKEDIN POST │ CONFERENCE │ ARTICLE │ PODCAST │                   EARNINGS CALL │ BLOG │ PANEL   published_on    REQUIRED, to the day where the source gives one. Undated ->                   excluded: the card's own framing is a recency window, so a date                   is what makes an entry admissible.   headline        as published. Do NOT rewrite it.   quote           VERBATIM, 80-260 chars, the executive's own sentence. Never                   paraphrase an executive - the value is that these are their                   words. Never stitch two sentences into one quote.   author_role     the role AS STATED AT THE TIME. A quote from someone who has                   since left is still evidence but must be dated and the                   departure noted - cross-check against the leadership roster.   linked_subcap_ids                   which assessed capabilities the statement bears on. A post                   about community sponsorship bears on none and does not belong                   here. This link is what makes the card part of the DMA rather                   than a press clipping.   alignment       CORROBORATES │ CONTRADICTS │ EXTENDS our finding, with a 12-25                   word clause. A CONTRADICTS entry is the most valuable thing on                   the card and must NOT be filtered out. CHALLENGE (R-Layer)  B  For every CORROBORATES entry, ask whether it is marketing rather than a     capability claim. "We are committed to digital transformation" is T5 and     evidences nothing.  D  Probes: a same-named executive at a different institution (verify against the     entity's own leadership page); a repost of someone else's content read as the     executive's view; a quote lifted from a vendor case study (T5, needs     corroboration); a departed executive presented as current; a date outside the     rendered window.  E  REJECT -> drop the entry. Fewer than 2 entries after searching all seven     source families -> emit what you have, set thin=true, and name what was     searched. Do NOT pad with corporate press releases: this card is about NAMED     PEOPLE speaking. GATES: every entry dated, cited, attributed to a named person with a role, and linked to a served cell; verbatim quotes only; contradicting entries retained.
```
