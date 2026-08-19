# Rulebook: overview · v2 (2026-08-19)

This is the overview page's anti-pattern rulebook: the measured record of what a
promoted overview looks like when it is right (Baxter, run `c1351d25`) and the
named, gated failures that reached promotion before the gates existed (chiefly
Logix, run `d7ed1d90`). The **overview producer reads it before authoring, as
Method step 2**, alongside `get_memory_digest` + `search_findings`; the
**rectifier is its only writer** — a producer never edits it, and an edit with no
finding behind it is an opinion. Entries flagged by a USER or REVIEWER are
**PERMANENT and never retired**, whatever later rounds conclude. Baxter is
**v5.0-shaped — 17 categories including P1C5, 706 cells — so every shape-specific
count quoted from it is a v5.0 fact, not a contract**; a v7.0 run (Logix: 16
categories, 705 cells) has its own counts. The card-level firmographics rulebook
entry lives here, under O2, per D2 — the context rulebook points at it.

---

## O1 · Scores &amp; peer benchmarks

### Baxter positive pattern

> "Strategy governance runs ahead of the credit-union peer set while the data
> layer trails it; the gap concentrates in Data Management & Governance at 1.95
> against its 2.5 category median." (framing — 30 words measured, inside the
> 18–32 band: states the gap, quantifies it, localises it, and does not open
> with the composite that renders beside it)

> `{"pillar_id": "P4", "score": 2.53, "peer_median": 2.88, "delta": -0.35,
> "direction": "below", "peer_n": 5, "peer_basis": "table",
> "proxy_disclosure": null}`

> "One constraint runs through this page: a strategy layer that outruns its own
> data and integration foundation. The hero shows the divergence, the findings
> trace it to a self-described patchwork data estate and a missing integration
> backbone, the opportunity tiles sequence the fix, and the timing signals — a
> planned merger and a leadership succession — say why the window is now."
> (narrative_thread)

Shape notes, measured: composite 2.71 with posture MIXED and `posture_basis`
HYBRID; all four pillar rows carry a signed, computed `delta`, the cohort size
(`peer_n`) and the basis (`peer_basis`); all 12 section `narrative_thread`s on
the promoted page are distinct — the CG-29 discipline holding. Logix carries the
other honest peer shape: `peer_basis: same_subvertical_cohort_median` with a
`proxy_disclosure` on every pillar naming the five-peer corpus cohort, its 80%
cell floor and the floor-of-three ladder.

### Anti-patterns

- **MEM-0093 / CG-29** — one narrative thread pasted onto every section — measured
  on the 2026-08-19 Baxter re-promote: one `narrative_thread` word for word on 10
  of 12 overview sections (and 4 of 5 platform sections); every presence check
  passed — the rule: the thread says what THIS section adds to the argument; the
  page-level story belongs in the hero, once; two sections may connect to the
  story the same way but never in the same words (9-antipatterns §4b).
- **(no MEM) / 9-antipatterns §6** — a peer figure computed from a different
  cohort than the one beside it; no gate sees two bases on one surface — measured:
  14 of 16 categories carried a peer median and two carried none because the
  cohort was assembled once and never revisited — the rule: every peer figure on
  the page (pillar, category, cell, focus area) comes from ONE cohort in one
  pass, with `peer_n` emitted so the reader sees the basis; at an edge recompute
  at lower N (floor 3); a different size class is `peer_basis = cannot_estimate`
  with the median null.
- **MEM-0086 / CITATION_NAMES_THE_CONTAINER_NOT_THE_SPAN** — peer figures cited to
  a page carrying none of them — measured on Logix: three peer figures cited to
  the NCUA dataset download page; a regex for every named peer and every quoted
  figure over all 37 cited rows matched 0 — the rule: the cited span carries the
  figure; a derivation trail is a disclosure, not a citation, and a proxy
  discloses itself with the literal phrase "peer proxy", never as a median.
- **(no MEM) / the pack's STEP 1, measured** — two composite formulas shipped a
  hero ring and a run row that disagreed at 1dp on 26 clients — the rule: the
  composite is the mean of the four pillar means, never a flat mean of subcaps;
  round once at 2dp, present at 1dp; every "<label> at N/5" resolves to a served
  cell within ±0.05 or the card does not ship (grain_violation — the most common
  defect in this product).

### Exclusion set

`r_layer` reaches no audience and is stripped at any depth; mark it anyway
(invariant 5 — marking is mandatory, the strip is the backstop). The
customer-audience row is exactly the allowlist's: `composite`, `framing`,
`posture`, `posture_basis`, `confidence`, `claim_label`, `e_ids`,
`narrative_thread`, `empty_state{reason, closure_condition, closure, kind}` and
`pillars{pillar_id, score, peer_median, peer_n, peer_basis, delta, direction, n,
basis, proxy_disclosure}` — an invented key drops at serve with the drop counted
in the receipt (D1, fail-closed). No colour and no hex anywhere in the payload
(invariant 7); no M-code, cap or ceiling vocabulary in `framing` or
`posture_basis` — `cap_level`, `ceiling`, `uncertainty_band`, `urf_modifiers`
are excluded key classes.

### Enrichment pathways

- **Connector.** No connector serves a peer score. `enrichment_sources.json`
  `peer_scores` names one source — the corpus: the peer table of promoted
  assessments, then the fallback ladder, tier band "n/a — scores, not
  evidence". Clay's nearest data point serves peer platform deployments on the
  tech register (T1 per established deployment, under AG-04's shape), never a
  peer figure. The composite and pillar scores are the workbook's (Information
  sources: scoring workbook + `peer_comparison_table.csv`); nothing external
  moves a score.
- **Web search.** What search serves here is the framing and the R-Layer, not
  the numbers. "[Entity] digital transformation criticism OR delay OR failure"
  — the mandated contradictory query; a dated third-party report registers T3,
  and a negative return is a rung in the `r_layer`, never an evidence row.
  "[Entity] strategic plan digital priorities 2025 2026" — the entity's own
  statement registers T2 with a verbatim 50–500 char span and grounds the
  framing's localisation. Where the peer table is structurally empty (private
  comparables), a published ranking is rung 4: it registers T3 and discloses
  itself with the literal phrase "peer proxy", never as a median. Everything
  enters through `register_evidence`; W6 refuses vendor collateral above T5
  and a rephrased absence.
- **Gap-to-pathway.** Every field on `overview.scores` is required with no
  must-present set and no condition, so `list_enrichment_gaps` emits
  `empty_required` only. A missing `peer_median` inside `pillars` is not a
  worklist row — it is the fallback ladder's business, answered by the corpus
  pathway or by `peer_basis = cannot_estimate` with the median null.

---

## O2 · Firmographics strip

### Baxter positive pattern

> `{"field": "website", "value": "bcu.org", "as_of": "2026-08-15",
> "source_e_id": "E-CC-156", "confidence": "HIGH"}` — bare, lowercased, cited
> like any other field; this is the row that makes O11's `self_sourced_pct`
> computable (REF-0029).

> `{"field": "cagr", "value": "7.2", "unit": "percent a year, total assets
> FY2020-FY2025", "as_of": "2025-12-31", "source_e_id": "E-CC-045"}` — the
> producer-stated, cited CAGR is a firmographics field with its own date and
> source; it is never sent on the financial series.

> "Three dated records establish three different years, each measuring a
> different event, so this panel carries the charter record and holds the
> founding year open. […] the field stays open rather than adopting a registry
> arithmetic the institution has not confirmed." (`founded`, quarantined, with
> the three records each named and cited inside the reason)

Shape notes, measured: 15 fields in SV2 vocabulary — `shares`, `member_count`,
`net_worth_ratio`, never a bank's deposits; every populated field carries
`{value, unit, as_of, source_e_id, confidence}`; `undated_pct` 6.7 stated rather
than hidden; the one unresolvable field is quarantined with a producer-authored
reason, not guessed.

### Anti-patterns

- **MEM-0059 / CG-16** — every must-present set was prose in a doc string, so no
  gate ever asked for its members — measured: 0 validators read a must-present
  set; the live reference run served 12 firmographics fields with no `website`
  while its own empty-state ladder named the domain twice — the rule: the
  must-present set is machine-readable contract (`must_present`,
  `must_present_any`, `must_present_key`) and CG-16 reads it; present means
  stated-with-a-value OR quarantined-with-a-reason; a blank quarantine reason
  counts as blank. **PERMANENT — never retire** (raised_by_kind USER); test:
  `apps/mcp/tests/test_must_present_members.py`
  (`test_the_live_reference_payload_is_refused_by_this_gate`).
- **MEM-0069 + MEM-0073 / enrichment register** — the surface asserts "Scan did
  not run" on a fully researched panel — measured: `enrichment_status.ran`
  structurally false on O2/O9/O12 (no `basis_key` defined), `enriched_rows: 0`
  against 14 served fields, unchanged across a promote that added 7 cited rows —
  the rule: every field carries `source_e_id` (the basis a register can count),
  a recorded absence is also a basis, and a badge that contradicts the payload
  is reported with `report_recurrence`, never silently re-enriched around.
- **MEM-0051 / serve-order** — item arrays served in heap order — measured: the
  one reordered array of 97 compared was `overview.firmographics.fields`, 13 in
  and 13 out with indices 0–6 all differing, putting return-on-assets where
  branch count was on a ranked identity card — the rule: order is meaning
  (charter rule 10); the served order is now the submitted order, so submit the
  fields in the order the strip should read.
- **(no MEM) / 9-antipatterns §9** — an absence explained instead of removed —
  the sanctioned exception measured on Logix: `revenue` absent with the
  producer-authored reason "a credit union returns its surplus to members", which
  renders because it is real information about the institution — the rule: a
  status word ("queued for enrichment", "held", "pending") never renders; a field
  with nothing in it renders no row; only a real reason earns the exception.
- **(no MEM) / S24 + the pack's identity gate, measured** — one client shipped
  $12.2B assets / FCA / a NY-NJ-CT-MA-NH footprint on the Overview while the hero
  and the Context page both said $87.9B / OCC, and both cards rendered — the
  rule: every field asserts THIS legal entity by name, regulator and footprint;
  any failure quarantines the field with `quarantine_reason`, never renders it.

### Exclusion set

The customer field row is `{field, value, unit, as_of, confidence, quarantined,
quarantine_reason, source_e_id}` — `recency_band`, which Baxter emits per field,
is method vocabulary (an excluded key class) and drops at serve; so do `tier`,
`ers`, `discovered_by`, `provenance` anywhere they appear. Section keys
`undated_pct`, `identity_mismatch` and `sub_vertical_undefined` serve. Contact
keys (`email`, `linkedin_url`, `phone`, `contact_email`, `direct_line`,
`mobile`) strip for the customer at any depth in any section. Probe keys
(`sources_searched`, `queries_run`, `searched_on`) never serve; the customer
`empty_state` keeps only `{reason, closure_condition, closure, kind}`.

### Enrichment pathways

- **Connector** (facet `firmographics`): `first_party` — filings, call reports
  and annual reports, T1-T2, wired; every field cites the filing it was read
  from. `clay` — the Annual Revenue and Headcount Growth company data points,
  T1-T2 **when a filing is behind it** (`tier_condition` is part of the tier:
  a modelled value with no traceable source is an inference, not a T1 fact);
  session-bound. `moodys` (T2-T3), `harmonic` and `cb_insights` (T3) are
  declared, not wired — listing grants nothing.
- **Web search** (registry first, per STEP 3): FDIC BankFind / NCUA Research /
  OCC Bank Search / FFIEC NPW by entity name — the registry figure registers
  T1 with its period stated. SEC EDGAR "[Entity] 10-K OR 10-Q total assets
  2025 2026" — T1-T2. The entity's own about / newsroom / investor-relations
  pages — mandatory fetch, T2, and the page that states the domain is the
  citation for the `website` member (bare and lowercased). "[Entity] headcount
  OR employees" via LinkedIn — T3, profile-derived; an aggregator estimate is
  labelled an inference. Every value registers with a verbatim 50–500 char
  span; W6's one-document cap binds when one call report carries the panel;
  a registry search that returns nothing is recorded in the field's
  quarantine reason, never as a row.
- **Gap-to-pathway.** The one section on this page with a `must_present` set
  (eight members): a silent member emits `must_present_member`, closed by a
  stated value with provenance or a quarantine with a real reason — the
  registry pathway answers it. `undated_pct` emits `empty_required` and is
  computed from the fields. `sub_vertical_undefined` and `identity_mismatch`
  emit `empty_optional`, and no pathway fills them — they are producer
  verdicts.

---

## O3 · Why-now signals

### Baxter positive pattern

> "BCU announced a planned merger with HealthCare Associates Credit Union on
> 1 June 2026 — a second institution's members, accounts and systems will land
> on BCU's platform estate." (WN-1 trigger: dated, cited, external)

> "Expanding agents now, before the data layer unifies, is the cost: autonomous
> actions on inconsistent member records is a risk the assessment's own
> capability caps flag. Acting now therefore means funding the data foundation
> the expansion depends on, not the expansion itself." (WN-4
> `cost_of_acting_now` — the honest other side, drawn from the caps and the
> stack, not a pitch)

> "So the window is not an opportunity to add channels — it is the last quiet
> period before a conversion consumes the same integration capacity the
> foundation work needs." (from the synthesis — 106 words measured, inside the
> 60–110 band, and the same timing argument as O4's Complication and P3's
> phase 1)

Shape notes, measured: 4 signals, each carrying all five headers plus
`linked_subcap_ids` and `e_ids`; windows are honest — WN-1 and WN-3 both say "no
dated close is established" rather than implying urgency no source supports;
every trigger dated at least to the month.

### Anti-patterns

- **(no MEM) / AG-11** — a why-now signal that recaps the assessment's own
  scores — the refused span, measured on Logix: "A five-member same-sub-vertical
  cohort read on 19 August 2026 sits at 2.52, 2.70, 2.50 and 2.36 across the four
  pillars against this run's 1.60, 1.52, 1.75 and 1.43" — every figure is this
  assessment's own output — the rule: a signal names the date it happened and the
  source that reported it; if the answer is "our own scoring", it is not a signal
  (9-antipatterns §1).
- **measured · Logix why_now** — the synthesis counts signals the array no longer
  holds — measured: `signals[]` carries three rows while the synthesis opens
  "Four triggers and one line through them" and goes on to enumerate a fourth,
  the cohort reading AG-11 removed — the rule: after any signal drops, every
  count and enumeration in the synthesis is recomputed from the array; a count
  in prose is a computed value, never a leftover (invariant 8 in prose form).
- **(no MEM) / the pack's must-present, measured** — the circular signal:
  "Zennify completed a Digital Maturity Assessment" shipped as a why-now on 11
  clients — the rule: no signal may be the assessment itself, and the vendor's
  name in a customer-audience string is sell copy the VENDOR_NAME net records as
  a content defect; write the client's events, not ours.

### Exclusion set

Customer signal rows keep `{wn_id, kind, trigger, window,
consequence_of_waiting, cost_of_acting_now, why_this_sequence, dated_on,
linked_subcap_ids, e_ids, claim_label, confidence}`; section keys `synthesis`
and `thin` serve. `r_layer` reaches no audience. Probe ladders in any
`empty_state` (`sources_searched`, `searched_on`) drop; the producer's `reason`
and `closure_condition` stay — a real reason renders, a probe never does.

### Enrichment pathways

- **Connector** (facet `why_now`): `clay` — Recent News T3, Latest Funding
  T1-T2 when a filing is behind it, Open Jobs T2-T3 (the posting is
  first-party; the aggregator is not). `first_party` — the entity's own press
  releases and filings, T1: the dated event itself. `quartr` (T1-T2
  transcripts), `moodys` (T2-T3 rating actions), `mergr` and `cb_insights`
  (T3) are declared, not wired.
- **Web search** (per the prompt's enrichment block): every applicable
  regulator's enforcement and order pages, by date — T1. "[Entity] core
  conversion OR migration OR go-live 2025 2026" — the entity's newsroom T2,
  trade press T3; the vendor's own announcement is T5 (W6 vendor collateral)
  and needs corroboration before it dates a trigger. "[Entity] names OR
  appoints CIO OR CTO OR CDO OR chief digital" — press release T2. "[Entity]
  delay OR postpone OR paused [initiative]" — the mandated wait-case query;
  a negative return is a rung, never an evidence row. Each admitted event
  registers with its date and a verbatim 50–500 char span; an undated result
  cannot become a signal.
- **Gap-to-pathway.** `signals` and `synthesis` emit `empty_required`; `thin`
  emits `empty_optional`. An empty `signals` on a disclosing entity closes
  through the connector's dated data points and the regulator sweep;
  `synthesis` closes only by writing — no pathway supplies the argument.

---

## O3 drilldown · Why-now signal row (inline)

The spec names this drill without an atlas id: *"PROTOTYPE · drilldown from
O3 — why-now signal row (inline)."* The row expands in the document flow into
the signal's five headers; it renders `overview.why_now.signals[*]` and holds
no payload of its own, so it is produced by producing O3 and repaired by
repairing O3 — never patched in a second copy.

### Baxter positive pattern

> "The window runs to BCU's first Illinois CRA examination cycle; no exam date
> is published, so no dated close is established — the exposure grows with
> each quarter of undocumented activity." (WN-3 `window` — the honest
> expansion: a window with no closing condition says so instead of implying
> urgency)

> "An integration backbone laid before member-data conversion turns the merger
> from a bespoke-links project into a catalogue of reusable application
> programming interfaces." (WN-1 `why_this_sequence` — the header only the
> expansion shows in full, tying the trigger to the roadmap)

Shape notes, measured: WN-1 carries `linked_subcap_ids` P4C3.1.1 and P4C3.1.2
with `dated_on` 2026-06-01 and two e_ids, so the expansion's chips resolve.
The drill the spec measured returned "Closing P1C1.6.4 lifts the parent
category and unblocks downstream work" — the right shape, a trigger tied to a
cell tied to a consequence — and the five required headers are that shape held
per header.

### Anti-patterns

- **(no MEM) / the spec's segmented-header requirement** — the review found
  the card unsegmented and made all five headers required, each with an ideal
  — the rule: the row expands into ALL FIVE headers, each doing its own job; a
  header present but empty is worse than the row not expanding, and a window
  with no closing event says "no dated close established" rather than implying
  urgency.
- **pointer / O3's entries** — AG-11 (a signal that recaps our own scores) and
  the count-recompute rule are homed under O3; a defect visible in the
  expansion is the parent row's defect.
- **(no MEM) / the chips are controls** — every `e_ids` entry on the row opens
  the evidence drawer (DD-2, homed in the heatmap rulebook beside H6); an
  unresolvable id is a dead control, so register before citing.

### Exclusion set

The drill inherits O3's boundary whole: customer rows keep `{wn_id, kind,
trigger, window, consequence_of_waiting, cost_of_acting_now,
why_this_sequence, dated_on, linked_subcap_ids, e_ids, claim_label,
confidence}`; probe ladders drop; `r_layer` reaches no audience. There is no
drill-only key — an invented one drops at serve like any other.

### Enrichment pathways

- **Connector.** The parent's (facet `why_now`) — see O3. Nothing is fetched
  at click time (invariant 1): a route not established at synthesis does not
  exist for the reader.
- **Web search.** The drill's own gap is header depth: "[Entity] [trigger
  event] integration OR conversion timeline" dates the window's close, T1-T2
  by source; "[Entity] [concurrent commitment] status 2026" grounds
  `cost_of_acting_now` from the timeline and issue register, T2-T3. A
  negative return leaves the header honest ("no dated close established"),
  never a row.
- **Gap-to-pathway.** The drill emits no gaps of its own — the worklist sees
  `why_now.signals` whole (`empty_required` on the parent). A header absent
  inside an item is invisible to it; the readback after promote is the
  check.

---

## O4 · Executive summary

### Baxter positive pattern

> "The strategy layer has outrun the foundation beneath it. […] Because every AI
> deployment and personalisation programme reads member data through that
> fragmented layer, the assessment's only two active cross-pillar caps both
> trace to it, with the result that the capabilities BCU is most proud of are
> ceilinged by the infrastructure they stand on." (complication — a mechanism
> with causal connectives, not a measurement)

> "With a merger announced, a presidential transition underway and the AI
> programme ready to expand, does BCU fund the visible next step — more agents,
> more channels — or fix the foundation those steps depend on first?" (question
> — the decision the client actually faces, in their voice)

> "A year's slip lands the HACU merger conversion on point-to-point plumbing,
> lets the first Illinois CRA exam arrive against manual evidence, and scales
> autonomous agents on inconsistent member records — three dated pressures
> converging on the same unbuilt foundation." (cost_of_delay)

Shape notes, measured: zero raw maturity scores across all six fields — the
story carries the argument; client facts (370,000 members, $6.5B, nine
Salesforce products, five AI systems, two hundred platforms) outnumber score
references; every field ends in terminal punctuation; the complication is the
same constraint O6 ranks first and the roadmap's phase 1 implements (the
cohesion check, run before submit).

### Anti-patterns

- **MEM-0093 / CG-27** — abbreviations on a client surface — measured: 50
  occurrences of `FCU` and 48 of `NCUA` reached promoted prose, and the
  overview re-promote paid 22 CG-27 blocking refusals on a two-field change —
  the rule: spell it out on first use in each field; the exception is a SPAN —
  a quote or excerpt is byte-for-byte and is never edited (a tidy-up measurably
  rewrote a chief executive's congressional testimony), and labels take title
  case (9-antipatterns §4; the boundary lives in
  `packages/shared/abbreviations.py`).
- **(no MEM) / S16 + S20, measured** — the score-quoting summary: 131 of 138
  bodies quoted two or more raw scores — the rule: at most ONE numeric maturity
  score in the whole summary and only where it carries an argument; no sentence
  may be a score predicate ("X stands at N/5"); any score quoted resolves to a
  served cell under the label used (the O1/S23 grain defect otherwise).
- **(no MEM) / the pack's safeguards, measured** — 452 bodies across 136 clients
  shipped without terminal punctuation — the rule is mechanical and checked
  before submit; a missing full stop is a blocked field, not a style choice.

### Exclusion set

`storyline_challenge` — the red-team transcript (5 volleys measured on Logix,
`survived: true`) — is our preparation for the room: `CUSTOMER_STRIP_KEYS`
removes it for the customer audience and the renderer's card was deleted
2026-08-19; mark it `internal_only` as Logix does, and never let its language
leak into the six client-facing fields. `r_layer` reaches no audience. No
internal codes in the prose — PxCy.z, E-nnn, REC-nn, URF-nn — capability NAMES
only. Customer keys are otherwise the six SCQA fields plus `claim_label`,
`e_ids`, `narrative_thread` and the envelope.

### Enrichment pathways

- **Connector.** None dedicated — no facet in `enrichment_sources.json` serves
  `overview.exec_summary`. The card synthesises the corpus (Information
  sources: the report DOCX plus this run's evidence store); every quantitative
  claim cites a row registered by the surface that owns the fact.
- **Web search.** This card's searches are refutation, not collection.
  "[Entity] [complication area] failure complaint outage criticism" —
  counter-evidence, T3 where a third party reports it; a strong counter
  changes the complication. "[Entity] [claimed programme] outcomes 2024 2025
  2026" — the Input-Output Disconnect probe, registering at the tier of its
  source. One customer-experience query where internal metrics look good —
  the CX Disconnect probe; its sources land through O9's pathways and are
  cited here by id. A refutation search that returns nothing is recorded in
  the `r_layer`, never registered — an absence is not a FACT (W6).
- **Gap-to-pathway.** The six SCQA fields and `claim_label` emit
  `empty_required`; `storyline_challenge` emits `empty_optional`. None closes
  through a connector: a gap on this section is a writing gap over
  already-cited facts, not a research gap.

---

## O5 · Opportunity surface tiles

### Baxter positive pattern

> "Ranked first by two tenths — its gate is already met, so readiness holds
> nothing back — and still the proof point: smallest scope, a statutory deadline
> of its own, and it exercises the data foundation end-to-end for an audience
> that matters." (CRM Analytics `rank_rationale` — fit rank and build sequence
> distinguished, cells and constraint named, not a restatement of the composite)

> `{"platform": "Marketing Cloud", "reason": "Already deployed — adoption
> conversation, not a fit conversation"}` and `{"platform": "Experience Cloud",
> "reason": "The member digital-banking layer is served by Alkami; replacing it
> is not the constraint this assessment surfaces"}` (discarded[] — a ranking
> that can reject, and the answer for "why not X" in the room)

> factors on every tile are the engine's four, by name: "Addressable
> opportunity", "Catalogue interconnect", "Greenfield family", "Strategic
> alignment".

Shape notes, measured: 4 tiles + 4 discards with reasons; `their_stack_context`
reads the register ("Data Cloud is not deployed despite nine Salesforce products
in production; Tealium persists as a parallel member-data layer"); every tile
carries `addressable_cells[]` over cells this run serves.

### Anti-patterns

- **MEM-0095 / CG-31** — the opportunity tiles carried per-client factor systems
  and no gate read them — measured from the rendered pages 2026-08-19: a
  six-factor breakdown summing to 76.5 on one client and a three-factor breakdown
  summing to 67.0 on the other, hand-fixed during the re-score while zero gates
  referenced `tiles[].factors` or `tiles[].composite` — the rule: the factor
  names are the engine's four, every legacy factor name is refused BY NAME, and
  the tile's composite and rank equal the platform page's card fit and rank at
  the 0.05 grain — one number, every carrier gated. **PERMANENT — never retire**
  (raised_by_kind USER); test: `apps/mcp/tests/test_platform_fit_gate.py`
  (the CG-31 block, "the tile is the same number as the card").
- **MEM-0001 / CG-13** — a contract-legal item field validated at submit and
  dropped at promotion — measured: 18 declared item keys across 9 serving tables
  had no column, `overview_opportunity` twice among them; RECURRED — the rule:
  after promote, read the served body; a field you submitted that is absent from
  the served row is a CG-13 recurrence to report, never something to quietly
  resubmit around.
- **measured · both payloads** — the reference client is not exempt from the
  contract: Baxter's four tiles carry `headline: null` on 4 of 4 while Logix
  carries a headline on 5 of 5 ("An auditable model inventory, ready before
  supervision begins.") — the rule: the card face's must-present (headline, whole
  sentences, anchor capability) is calibrated by Logix here; audit the positive
  reference like any other client, because a gap that lives in the gold standard
  propagates as a pattern.

### Exclusion set

Customer tile rows keep `{platform, headline, composite, factors,
addressable_cells, anchor_subcap_id, relevance, rank, rank_rationale,
their_stack_context}`; `discarded{platform, reason}` serves — a visible discard
is evidence of judgement. `r_layer` reaches no audience. No colour and no band
hex in any tile (invariant 7); `tier`/`ers` on any nested evidence reference
drop by class.

### Enrichment pathways

- **Connector.** The tiles read two registers connectors feed. The tech-stack
  register (facet `techstack`: the `explorium` ingest scan, T1, wired-not-
  live; `clay` Tech Stack, T1 — a machine technographic scan is T1, never T4)
  decides greenfield against extension in `their_stack_context`. The demand
  signals of facet `platform_readiness` (`clay` Open Jobs T2-T3; `first_party`
  careers pages and announced programmes T1-T2) raise a priority. The
  composite itself is engine arithmetic — no pathway moves a rank.
- **Web search.** "[Entity] [platform] RFP OR selects OR implements 2024 2025
  2026" — a demand signal: entity announcement T2, trade press T3; the
  vendor's own customer story is T5 (W6) and cannot carry a tile alone.
  "[Entity] hiring [platform] administrator OR developer" — T2-T3, the
  cheapest capability signal there is. "[Entity] [layer] replacement OR
  migration" — a mid-migration hit is a timing constraint; register the dated
  span. A search that returns nothing about a candidate platform feeds
  `discarded[].reason` and registers nothing.
- **Gap-to-pathway.** `tiles` and `discarded` both emit `empty_required`. The
  tiles close from the engine plus the registers above; an empty `discarded`
  is a ranking that never rejected, and no search fixes that.

---

## O6 · Top findings

### Baxter positive pattern

> "Data fragmentation is the root constraint, not under-investment" (F-1 title —
> the pack's own measured exemplar: a claim that rejects the obvious alternative
> in the same breath)

> "Under-investment was considered and rejected: spend and staffing are visible;
> what is absent is consolidation — one member-data layer where the system of
> record already lives." (F-1 `rejected_alternative`)

> `strategic_alignment: {"score": 0.95, "statement": "The data chief's stated
> ambition — an agentic enterprise on unified member data — is this finding's
> own remedy in the client's words."}` with `ranking_basis:
> "strategic_alignment"` — the ranking key is the client's own objectives, and
> the basis is stated on the surface.

Shape notes, measured: five findings read as one story — root constraint (F-1),
what it blocks (F-2, F-3), the bounded proof (F-4), and a strength worth
protecting (F-5: "The measurement architecture is a strength worth protecting")
— a finding is not always a gap; consequences carry a magnitude or a named event
("Merger conversion lands on bespoke links"); `source_kind` recorded per finding.

### Anti-patterns

- **MEM-0002 / CONTRACT_FIELD_DISCARDED_AT_PROMOTION** — the anchors are null on
  the served run — measured on the reference client 2026-08-08: `subcap_id`
  present on 0 of 5 findings and `score` on 0 of 5, after the columns existed —
  the rule: every finding is anchored — emit `subcap_id` and THAT cell's own
  score (Logix carries the finished shape: F-01 → P3C3.1.1 at 3.0, every finding
  anchored); the quoted figure must resolve to the named cell ±0.05 (W1) — a
  subcap-grain score under a category id read "3.5/5" against a cell serving
  2.77 on 59 clients.
- **MEM-0001 / CG-13** — `overview_findings` was four of the 18 item keys with no
  promotion column (RECURRED), and the scar is visible in the reference body:
  `what`/`why`/`so_what` and the `evidence` rows are absent on 5 of 5 Baxter
  findings while Logix serves all four drilldown headings with 1–4 evidence rows
  per finding — the rule: the four headings are each required and each does its
  own job; a finding with zero evidence rows does not ship (the EVIDENCE heading
  is a control, and an unresolvable id is a dead control); verify the served
  body after promote.
- **(no MEM) / S14 + the pack, measured** — title defects: a capability name
  alone, a person's name, an evidence sentence, a raw code — "'[P2C3.2.IC1]
  Evidence'" shipped as a title — the rule: the title is a claim of at most 12
  words; the theme chip is one of the client's own domains; no internal code in
  any heading.

### Exclusion set

Customer finding rows keep the full drilldown (`title`, `theme`, `consequence`,
`body`, `what`, `why`, `so_what`, `evidence`, `rejected_alternative`,
`strategic_alignment`, `strategic_alignment_score`, `subcap_id`, `score`,
`peer_median`, `platform_chips`, `linked_subcap_ids`, `e_ids`, `source_kind`,
`claim_label`, `confidence`, `f_id`, `name`) — but `tier` inside `evidence` rows
is an excluded key class and drops for the customer, and `r_layer` (which Logix
marks per finding: `findings[0].r_layer` …) reaches no audience. `ranking_basis`
serves — state it. No URF codes in client-visible headings: entitlement-without-
adoption is said in client language and URF-04 fires internally.

### Enrichment pathways

- **Connector.** None dedicated — findings are RETRIEVED from the package
  first. What connectors feed is the joins STEP 2 derives from: the sentiment
  facet (O9's sources), the tech register (facet `techstack`, T1 scans), and
  the entity's own words for `strategic_alignment` — `first_party` filings
  and decks, T1-T2.
- **Web search.** "[Entity] annual report OR strategic plan objectives 2025"
  — the ranking key's source, T1-T2; the objective is quoted verbatim inside
  the 50–500 char span, never paraphrased. "[Entity] [finding area] failure
  complaint outage criticism" — one contradictory query per finding,
  mandatory; a hit registers at its source's tier, a miss is a rung in the
  finding's `r_layer`. "[Entity] [cause asserted in WHY] history" with year
  markers — a WHY that asserts a history needs a source; where none returns,
  the WHY says the cause is unestablished rather than inventing one. Every
  drilldown EVIDENCE row resolves — register before citing.
- **Gap-to-pathway.** `findings`, `narrative_thread` and `ranking_basis` emit
  `empty_required`. `ranking_basis` closes through the strategic-objectives
  search or falls back honestly (`impact_fallback`); `narrative_thread`
  closes only by writing.

---

## DD-9 · Finding expansion (drilldown from O6)

Inline expansion from a top-findings row (Drilldown atlas: DD-9, component
TopFindingsCard). No separate prompt and no payload of its own — it renders
the four headings and the evidence rows O6's `findings[*]` carry, which is why
the CG-13 scar recorded under O6 is a scar HERE: a heading discarded at
promotion is an expansion that opens onto nothing.

### Baxter positive pattern

The positive exemplar is Logix — Baxter's served drilldown fields are the
CG-13 scar O6 records (`what`/`why`/`so_what` absent on 5 of 5):

> "Compliance Program Framework is the strongest-scoring cell in its category,
> resting on a costed multi-year build. The same institution reported $9.688
> billion to its regulator in June 2026, below the threshold that build exists
> to meet." (F-01 `what` — the structural fact, then the figure that makes it
> real)

> "This is the constraint the rest of the assessment sits inside: capacity is
> already bought. The decision is what to ask of it during the interval, and
> that interval is the cheapest capacity this institution will have." (F-01
> `so_what` — a decision, not a restatement)

> `{"e_id": "E-CC-200", "tier": "T1", "recency": "CURRENT", "claim_label":
> "FACT", "source_title": "National Credit Union Administration Credit Union
> Online — LOGIX charter 1999 details"}` (one of F-01's four EVIDENCE rows —
> each id resolves, so each chip opens the drawer)

Shape notes, measured: all four headings on 5 of 5 Logix findings with 1–4
evidence rows each; F-01 anchors P3C3.1.1 at 3.0, so the face's score chip and
the expansion argue about the same cell.

### Anti-patterns

- **MEM-0001 / CG-13 — pointer to O6** — the drilldown headings are the fields
  that were discarded at promotion on the reference client; verify the served
  body after promote, because this panel is where the discard renders.
- **(no MEM) / the pack's cross-heading checks, measured** — WHAT states a
  fact, WHY explains it, SO WHAT decides; two headings saying the same thing
  in different words is one idea, not three; the consequence on the card FACE
  must be the same consequence SO WHAT argues; no internal code (PxCy.z,
  URF-nn, REC-nn) in any heading.
- **(no MEM) / the EVIDENCE heading is a control** — "EVIDENCE · CLICK TO
  VIEW": each row's id opens DD-2, so an unresolvable id is a dead control,
  and a finding with zero evidence rows does not ship.

### Exclusion set

O6's boundary, rendered: the customer finding row carries the full drilldown
(`what`, `why`, `so_what`, `evidence`, `rejected_alternative`, …) but `tier`
inside `evidence` rows drops for the customer, and `r_layer` — which Logix
marks on every finding — reaches no audience. The expansion adds no key of its
own.

### Enrichment pathways

- **Connector.** The parent's — none dedicated; the headings cite rows already
  in the store (see O6). The EVIDENCE rows' tiers follow their sources, per
  `clay_taxonomy.json`.
- **Web search.** The heading-shaped gaps: WHY's cause — "[Entity] [system]
  retained OR consolidated acquisition history", T2-T3, because a WHY that
  asserts a history with no source is the probe O6 names; SO WHAT's
  quantified benefit — cited or not named; and the per-finding contradictory
  query, whose negative return is an `r_layer` rung, never a row.
- **Gap-to-pathway.** None of its own — the worklist reports `findings`
  (`empty_required`) on the parent, and a heading absent inside an item is
  invisible to it. The post-promote readback O6 mandates is the only check
  that sees this panel's content.

---

## O7 · Leadership panel

### Baxter positive pattern

> "LinkedIn profile https://www.linkedin.com/in/bhavna-guglani/ — name AND title
> matched the roster entry exactly; work address resolved by Clay against the
> bcu.org domain […]" (`enrichment_basis` — the artefact, the match rule, and
> the domain, not the tool's say-so)

> "The enrichment search returned no profile whose TITLE matched this person (a
> name-similar match is an identity failure, not a near-miss) […]"
> (`enrichment_basis` on a seat with no route — the SEAT still serves; the
> absence sits on the contact field, not on the person)

> "Owns data strategy and the warehouse refactor; publicly named the patchwork
> problem this assessment anchors on." (Sahagian `relevance_note` — which
> capability this person owns and what they have said about it, ~25 words per
> person measured across the roster)

Shape notes, measured: six seats spanning data, digital channels, enterprise,
technology and risk, each with `appointed_on`/`tenure_months`/`as_of` and a
`source_e_id`; three seats carry no contact route and serve anyway — the roster
is the accountability set, contact enrichment is a convenience on top of it.

### Anti-patterns

- **MEM-0045 / DEFAULT_DENY_DELEGATED_TO_THE_PRODUCER** — the customer body
  served a named executive's contact route and the enrichment tool's notes about
  them — measured: 6 of 6 occurrences each of `linkedin_url`, `email`, `phone`,
  `enrichment_basis`, `enriched_at` in the customer body, identical to the
  internal body, while `internal_only` was an empty array on 34 of 34 sections
  of both clients — the rule: mark every contact route and every enrichment note
  `internal_only` on every row; the key-strip backstop exists, but an unmatched
  or missing marking is a producer defect the redaction receipt now names; never
  attach process vocabulary to a real person on their employer's dashboard
  (standing clause 12).
- **(no MEM) / CG-28** — an executive dropped because contact enrichment found
  nothing — measured: three seats served, six more returned by one search —
  chief information security officer, chief administrative officer, chief legal
  officer among them — and the Logix roster now carries seven seats including
  all three — the rule: run the contact search for EVERY officer the entity
  names; a seat that owns a finding serves with the fields you have
  (9-antipatterns §5).
- **MEM-0073 / enrichment register** — enrichment counted as established when the
  search failed — measured: `enriched_rows: 6` against 3 established routes,
  because the basis text beginning "The enrichment search returned no profile…"
  counts the same as a resolved profile — the rule: `enrichment_basis` names the
  filing or profile the tool surfaced, never the tool ("Clay reports it" is not
  a source), and a recorded absence must read as an absence.
- **measured · Logix leadership** — a route with no basis and no mark — measured:
  4 of 7 roster rows carry a `linkedin_url` with `enrichment_basis` null, and
  the `internal_only` marks cover `roster[0..2]` only — the rule: every contact
  field carries its basis, its `enriched_at` and its mark, or it is not emitted;
  the serve boundary strips it for the customer either way, but the internal
  reader is owed the provenance too.

### Exclusion set

`CUSTOMER_STRIP_CONTACT_KEYS` — `email`, `linkedin_url`, `phone`,
`contact_email`, `direct_line`, `mobile` — strip for the customer audience by
KEY at any depth, in any section, because the roster is not the only place a
person can appear; `enrichment_basis` and `enriched_at` are `CUSTOMER_STRIP_KEYS`.
The person's `name`, `title`, `domain`, tenure fields, `as_of`, `relevance_note`
and `source_e_id` stay — those are the finding; the route to their inbox is not.
`verified_absent` serves (true only after the profile was read and held none).
`r_layer` reaches no audience.

### Enrichment pathways

- **Connector** (facet `leadership`): `clay` — the contact routes (email,
  linkedin_url, phone, enrichment_basis) via find-and-enrich-contacts-at-
  company plus Summarize Work History (T3, profile-derived, per
  `clay_taxonomy.json`); the returned TITLE must match the person searched —
  surname plus employer is not identity, and on failure the field is
  quarantined with its reason. `first_party` — named seats and tenure from
  proxy statements, leadership pages and filings, T1-T2. The taxonomy's
  `job_title_keywords` scope the search and its excludes (Intern, Assistant,
  Coordinator) are the guard the measured intern-match defect made necessary;
  the taxonomy's named residual gap is board and executive committee
  membership (a Custom data point).
- **Web search.** The entity's leadership / about / governance page —
  mandatory fetch, T2. "[Entity] names OR appoints OR promotes CIO OR CTO OR
  CDO OR chief digital OR chief information 2024 2025 2026" — press release
  T2. Conference speaker listings and panel bios — T2 for a named conference.
  Regulator filings that name officers — T1. Before any recorded absence, all
  five proxy searches (board bios, C-suite digital hires, LinkedIn digital
  titles, conference talks, strategic-plan filings) — the negative routes are
  the ladder recorded with the vacancy, never rows.
- **Gap-to-pathway.** `roster` emits `empty_required` — closed by the package
  plus the ladder above, run for EVERY officer the entity names (CG-28).
  `verified_absent` emits `empty_optional` and is a producer verdict, true
  only after the profile was read and held none.

---

## O8 · Financial trajectory

### Baxter positive pattern

> `"basis": "Total assets (National Credit Union Administration 5300 Call
> Report, Account 010)"` — the same definition string on all six points:
> period-end, one registry, one account, so the trend is one metric and not a
> splice.

> "Six December cycles compound at 7.2% a year, but the annual step collapsed
> from 13.4% in 2022 to 2.1% in 2024 before recovering to 5.3%, and the book
> stands at $6.40B at 30 June 2026. The fastest growth landed on the integration
> and data layers this assessment scores lowest." (reading — 49 words measured,
> inside the 35–60 band, and it answers the card's question: does growth outpace
> the capability that has to support it)

Shape notes, measured: six dated points, oldest first, each `{period, value,
unit, as_of, source_e_id, basis}`; `trend: GROWING` computed from the series; no
`cagr` key sent — the computed CAGR appears at read from the dated points, and
the producer-stated, cited CAGR sits on O2 with its own `as_of`. **This section
serves O8 AND C6** — the Context page renders this same row, so it is written
once and there is nothing to produce for C6; a second version is how the two
cards come to disagree, and there is no second row for it to land in.

### Anti-patterns

- **(no MEM) / S24 + the pack's STEP 2, measured** — an identity-contaminated
  series rendered — measured: an Overview series of $9.8B→$12.2B carrying
  regulator FCA and a NY-NJ-CT-MA-NH footprint, on an OCC-regulated Utah bank
  whose other two surfaces both said $87.9B — the rule: every point asserts THIS
  legal entity by name, regulator and footprint; any mismatch quarantines the
  SERIES whole, with `quarantine_reason` and the honest empty state; a
  quarantined series never renders and has no reading.
- **(no MEM) / the pack's unbound-columns table** — three columns exist and must
  not be sent: section-level `basis` (basis is per point — a section-level copy
  is a second place the definition can disagree with itself), `cagr` (computed
  at read from the dated points; a sent value is how the computed one and the
  stated one disagree — invariants 8 and 9), and pre-formatted values (the card
  formats; send the figure and its unit).
- **measured · Logix financial_series** — the reading overruns its band —
  measured: 76 words against the 35–60 contract, on a card whose reading
  otherwise does the job ("capital is accumulating faster than the balance sheet
  is growing […] it makes the committed readiness capacity the asset to
  redeploy") — the rule: the band is contract, not advice; say the same thing
  inside it.

### Exclusion set

Customer series points keep `{period, value, unit, as_of, source_e_id, basis}`;
section keys `reading`, `trend`, `verified_sparse`, `quarantine_reason` serve.
`r_layer` reaches no audience. `recency_band`/`tier`/`ers` drop by class
anywhere they appear. C6 is this same section on the Context page — produce O8
and C6 follows; nothing here is context-page work.

### Enrichment pathways

- **Connector.** No facet of its own; two adjacent ones serve it.
  `first_party` filings (facet `firmographics`, T1-T2) are where the dated
  points live, and `clay`'s Latest Funding data point maps here per
  `clay_taxonomy.json` ("O8 financial context") — T1-T2 when a filing is
  behind it, otherwise an inference.
- **Web search** (STEP 4 is mandatory — the package is as old as the
  assessment): the latest 10-Q/10-K on SEC EDGAR, or the sub-vertical's
  registry — FDIC BankFind, NCUA Research, FFIEC NPW, NAIC, AM Best — T1,
  the period explicit. "[Entity] total assets OR AUM OR direct written
  premium Q1 OR Q2 2026" — registry or filing T1-T2; an investor-relations
  release T2. For a non-filer, the trade press's annual ranking tables — T3,
  a third-party estimate unless the publisher says the firm reported it.
  Every point registers with its `as_of` and a verbatim span; a search that
  finds nothing newer leaves the series as the package states it and
  registers no "no newer figure" row.
- **Gap-to-pathway.** `series` and `reading` emit `empty_required`. `trend`
  and `quarantine_reason` emit `conditional` — absence is CORRECT below three
  dated points and outside a quarantine respectively, so read the run state
  before the instruction. `verified_sparse` emits `empty_optional`; the
  registry pathway is what turns it from a default into a finding.

---

## O9 · Sentiment

### Baxter positive pattern

> `{"source": "Apple App Store — BCU Mobile Banking", "audience": "customer",
> "rating": 4.87, "scale": "1-5 stars", "n": 95033, "as_of": "2026-04-29",
> "url": "https://itunes.apple.com/lookup?id=1133974972&country=us",
> "e_id": "E-CC-011"}` — every interpretability field on every bar.

> "Consumer Financial Protection Bureau consumer complaint database […] —
> VERIFIED ABSENT: a full-text search for 'Baxter Credit Union' returns exactly
> one row, a 2016 debt-collection complaint naming the unrelated Law Offices of
> Timothy E. Baxter & Associates, excluded on identity (E-CC-053)"
> (sources_searched — an absence established, with the identity exclusion shown)

> "[…] it neither caps nor lifts Culture & Change Enablement: it establishes
> that the employee audience is measured and positive, and leaves the tooling
> question to the tech register." (a `cap_statement` honest about what the
> instrument measures — the analysis, not the star rating)

Shape notes, measured: seven bars across customer, employee and industry
audiences including four named peers; a rank or a grade (BBB C+, Computerworld
No. 2) draws no bar — no scale, no sample — and is carried as a theme instead;
the self-published NPS (79.81, no n) renders as corroboration, not measurement;
`gap_analysis` states both sides; the empty_state ladder records the 403s
(Glassdoor, Indeed, Trustpilot) as rungs, never as evidence ids.

### Anti-patterns

- **MEM-0071 / SG-S8's neighbour** — the register counted a key the section never
  had — measured: `enrichment_status` served `count: 0, thin: true` against 7
  rated bars, while the connector's own SG-S8 passed the same submission with
  `rated_rows: 7` — two components disagreeing about one section — the rule:
  `bars[]` is the section's countable field; `displayed_lines` exists for the
  renderer and SG-S8 recomputes from the rating rows at submit and never reads
  it; never tune either to move a badge — report the disagreement.
- **measured · Logix sentiment** — themes that terminate in no assessed
  capability — measured: 2 of 2 themes carry no `mapped_subcap_ids` and no
  `cap_statement` — sentiment that connects to no cell is decoration; both
  fields are bound now, so the cap statement names the cell and the rubric
  level with the cause distinguished (the measured exemplar: "Most complaints
  relate to ACH processing delays, not service quality. Caps P2C2.1.1 at M3").
- **(no MEM) / 9-antipatterns §7** — a field the renderer cannot read — measured:
  `"scale": 5` was written while only the string `"0..5"` parsed, and five grey
  rails rendered over five real ratings; the echo is measurable on Logix, where
  one bar's scale reads `"1-5"` while four read `"1-5 stars"` — the rule: write
  the shape the renderer already reads, one spelling per card; a second legal
  shape must be announced, because someone has to teach the reader about it.
- **(no MEM) / the pack's must-present** — the invented card style that shipped
  on D1 is not in the design package and must not return; the contract is the
  prototype's: rating bars grouped by audience here, the three-tile grid on
  Context (C4 projects this section and can never disagree with it — produce
  this first, reconciled by `e_id` and `rating`).

### Exclusion set

The whole section is **customer-withheld** (`CUSTOMER_WITHHELD` in
`redaction.py`): the customer projection shows `kind=withheld_for_audience`, so
an audit that reads it without `?audience=internal` will misreport redaction as
producer absence (MEM-0061 — two wrong diagnoses in one session; always read the
internal projection and say so). Produce the section fully for the internal and
AE readers regardless. `metric` is **no such key** — a prototype leftover named
by no source; never emit it. `displayed_lines` is renderer-only. Baxter
additionally marks `sentiment.bars` internal_only — the marking is mandatory
even where the section is withheld whole. Probe ladders in the empty_state drop
for any audience that ever sees it; M-code cap vocabulary inside
`cap_statement` prose stays internal with the section.

### Enrichment pathways

- **Connector** (facet `sentiment`): `first_party` — surveys the entity
  publishes and retrievable ratings carrying sample size, scale and date,
  T1-T2. `clay` — news sentiment, T3: one route of several, never review-site
  depth. Glassdoor, Indeed and ZipRecruiter all 403, so `register_evidence`
  gets `url_unreachable` — such a value is an inference with its route named,
  or it is omitted; a 403 is never an absence.
- **Web search** (the seven source families, each at its tier): the App Store
  and Google Play lookups — rating, n, scale, release date; T3, third-party
  platform data (the Baxter bars cite the lookup URL itself). The CFPB
  complaint database, full-text, by entity name — T1; the complaint TEXT is
  the analysable part, and an identity-excluded match is recorded as the
  exclusion. BBB and Trustpilot where presence exists — T3; a grade with no
  scale and no sample draws no bar. J.D. Power and Forrester rankings — T3;
  a self-published NPS is T4/T5 and needs corroboration. A rating registers
  only with n + scale + as_of; a blocked host is refused-robot — a rung,
  never a row.
- **Gap-to-pathway.** `bars` and `themes` emit `empty_required`.
  `gap_analysis` emits `conditional` — correctly absent when only one
  audience was established. `displayed_lines` emits `empty_optional` and is
  renderer-only; never send it to quiet the worklist.

---

## DD-12 · Sentiment source card (drilldown from O9)

Inline expansion from a sentiment tile (Drilldown atlas: DD-12, component
SentimentGridInteractive). No separate prompt: on Context the three tiles are
C4's projection of this section; on the Overview the row is the bar and its
expansion shows the source's own fields. Everything it renders is
`overview.sentiment` — produced once, under O9's prompt.

### Baxter positive pattern

> `{"source": "Apple App Store — Lake Michigan Credit Union", "audience":
> "industry", "rating": 2.99, "scale": "1-5 stars", "n": 688, "as_of":
> "2026-07-28", "url":
> "https://itunes.apple.com/lookup?id=481606178&country=us", "e_id":
> "E-CC-015"}` — a peer bar carrying every interpretability field the
> expansion renders, including the outlier rating that makes the peer set
> honest.

> theme: "Welcome, pride and autonomy — and nothing about the tooling" with
> `mapped_subcap_ids: []` — an empty mapping carried honestly, because its
> `cap_statement` says what the instrument measures and why it neither caps
> nor lifts the cell; the Logix defect (no mapping AND no statement) is the
> decoration this shape refuses.

Shape notes, measured: the expansion's whole content is the bar's fields plus
the theme's `cap_statement`; the Baxter empty_state records the known gap as a
reason, not as rows — "the App Store lookup application programming interface
returns ratings and counts but no review bodies, so no customer theme can be
mapped to a capability."

### Anti-patterns

- **pointer / O9's entries** — MEM-0071 (`bars[]` is the countable field) and
  the renderer-shape rule (one `scale` spelling per card) are homed under O9;
  the expansion is where a wrong spelling becomes a grey rail.
- **(no MEM) / the O9 shape note, rendered** — a rank or a grade (BBB C+, a
  Computerworld placing) draws no bar and expands as a THEME, not a rated
  row; a self-published NPS renders as corroboration, not measurement.
- **(no MEM) / C4 is the same data** — the Context tiles reconcile to these
  bars by `e_id` and `rating`; a drill authored separately for Context is how
  the two disagree. Produce O9; both projections follow.

### Exclusion set

The parent section is customer-withheld whole (`CUSTOMER_WITHHELD`), so this
expansion reaches the internal and AE readers only — read
`?audience=internal` before diagnosing an absence (MEM-0061). `metric` is no
such key; `displayed_lines` is renderer-only; probe ladders in the
empty_state drop.

### Enrichment pathways

- **Connector.** The parent's (facet `sentiment`) — `first_party` T1-T2,
  `clay` news sentiment T3, the 403 trio recorded as `url_unreachable` rungs.
  See O9.
- **Web search.** The expansion's known gap is citable review TEXT behind the
  ratings: the CFPB complaint narratives by product (T1) and BBB complaint
  themes (T3) are the two families that return quotable spans; Trustpilot and
  Google reviews where presence exists (T3). A span registers verbatim,
  50–500 chars; the lookup API's bare numbers stay bars, not text.
- **Gap-to-pathway.** None of its own — `bars` and `themes` report
  `empty_required` and `gap_analysis` reports `conditional` on the parent. An
  expansion that opens onto nothing is a theme without a `cap_statement`,
  which the worklist cannot see; the parent's must-present discipline is the
  check.

---

## O1b · Capability ceiling &amp; uncertainty

### Baxter positive pattern

> "Three strategy pillars are set out in BCU's own materials — member-first,
> application programming interface-driven technology standards and a data
> strategy for faster decisions — under a board technology committee carrying a
> former Fortune 50 chief information officer. The fullest public statement of
> that strategy is a 2020 conference deck, so its present form is inferred from
> later appointments rather than read." (P1C1 rationale — half (a): what the
> evidence establishes; half (b): the absence that set the ceiling)

> "The current digital strategy document with its refresh date and investment
> envelope; the fullest public statement of it is still the 2020 conference
> deck." (`limiting_absence` — a named, searchable artefact: the research
> backlog for the next run)

Shape notes, measured: 17 rows (the v5.0 category count; a v7.0 run has 16),
every row `claim_label: CEILING_ESTIMATE` with an uncertainty band and named URF
modifiers where applied; `internal_only: ['ceilings.rows']` marked by the
producer.

### Anti-patterns

- **MEM-0087 / the tier rule** — a machine technographic scan registered below T1
  caps ceilings artificially — measured: the same scan output re-registered at T1
  gained +0.85 mean ERS on identical content; a T4 filing caps at L2.5, and the
  pack calls tier misclassification the most common suppression in this corpus —
  the rule: a machine scan is T1, never T4; a ceiling set by a misfiled tier is
  recounted at the true tier, never adjusted in place.
- **measured · both payloads** — one field, two vocabularies: Logix rows state
  the ceiling as a rubric code (`"ceiling": "M3"`, band 0.4) where Baxter states
  a band word (`"ceiling": "Differentiating"`, band 0.3) — the prompt's ladder is
  M1–M5, and an internal table read across clients needs one vocabulary — the
  rule: follow the prompt's ladder here, record the divergence rather than
  papering it, and never let either vocabulary out of this section into
  client-facing prose (`cap_level` M-codes measured escaping into
  `context.issue_register` are the neighbouring leak, D1).
- **(no MEM) / G14 + the pack's enrichment obligation** — a ceiling set by
  absence obliges you to have looked: before emitting a ceiling below M3 on an
  absence, run the ladder for the `limiting_absence` specifically plus the five
  organisational proxies — a ceiling you have not tried to break is an
  assumption; over ±0.8 the row is `ceiling=null` "Cannot reliably estimate",
  because a point estimate past the cap is false precision.

### Exclusion set

This section is **NEVER_SERVED** — it reaches no audience at all (owner
instruction 2026-08-19: internal artifacts "are dropped at the payload boundary
and render nowhere"); it is still promoted, validated and auditable through the
connector, so produce it fully. Mark `rows` internal_only anyway, as both
payloads do. `ceiling`, `uncertainty_band`, `urf_modifiers` and `cap_level` are
excluded key classes everywhere — the generated allowlist's ceilings row keeps
only `{category_id, category_name, claim_label, confidence, e_ids,
limiting_absence, rationale}`, which is what would survive if the section ever
served. `r_layer` reaches no audience.

### Enrichment pathways

- **Connector.** No facet of its own. The pathway that most often moves a
  ceiling is the tech one: a machine technographic scan is T1, never T4
  (`clay` Tech Stack; the `explorium` ingest scan), because a scan misfiled
  at T4 caps at L2.5 — the most common suppression in this corpus.
  `first_party` filings (T1-T2) lift a ceiling wherever the
  `limiting_absence` is a document the entity actually publishes.
- **Web search** (the G14 obligation — a ceiling set by absence obliges you
  to have looked): the `limiting_absence` itself as the target — "[Entity]
  digital strategy refresh OR investment envelope 2025 2026" for a strategy
  ceiling, T2 where the entity states it. The five organisational proxies
  where the absence is organisational (board bios, C-suite digital hires,
  LinkedIn digital titles, conference talks, strategic-plan filings) —
  T2-T3. "[Entity] [category capability] deployment OR case study" — a
  vendor case study is T5 (W6) and cannot raise a ceiling above L2
  uncorroborated. Anything found is minted and the ceiling recounted at the
  true tier; a ladder that returns nothing is recorded in the rationale's
  half (b), never as an evidence row.
- **Gap-to-pathway.** `rows` emits `empty_required` — the only kind this
  section emits. A missing row is a category not yet worked, closed by the
  ladder above run against that category's limiting absence.

---

## DD-15 · Ceiling rationale (drilldown from O1/O1b)

Inline expansion from a capability ceiling row (Drilldown atlas: DD-15,
component CeilingEstimateCard). The spec files the drill under O1 — the hero —
while the rows live on `overview.ceilings` (O1b): one drill, two anchors, one
payload. No separate prompt; the expansion renders the row's `rationale` and
`limiting_absence`, so a row that cannot carry the expansion is an O1b row to
finish.

### Baxter positive pattern

> "Bot inventories and run volumes for the three robotic process automation
> products detected — process-mining output or automation logs would show
> which of them carries the work." (P3C1 `limiting_absence` — named,
> searchable, and written FOR this panel: the next run's research backlog
> rendered where the reader asks "why this ceiling")

Shape notes, measured: the P3C1 row carries `ceiling` Differentiating with
`uncertainty_band` 0.8 at its cap and `urf_modifiers` ["URF-02"] — "the band
widens to its cap because bot counts and run volumes for those three are not
publicly determinable, so utilisation cannot be separated from installation",
which is the two-half rationale discipline doing its work.

### Anti-patterns

- **pointer / O1b's entries** — the tier rule (a machine scan is T1, never
  T4), the one-vocabulary rule and the G14 look-before-you-cap obligation are
  homed under O1b; the expansion renders the same row.
- **(no MEM) / spec DD-15** — "This panel renders from the payload its parent
  surface already carries." An expansion that needs content the row does not
  hold means the row is incomplete — fixed in O1b, never patched at the
  drill.
- **(no MEM) / the boundary, current** — O1b is NEVER_SERVED (owner
  instruction 2026-08-19), so this expansion renders nowhere today; the
  spec's contract for it stands, and the row is still promoted, validated and
  read through the connector — produce it fully.

### Exclusion set

As O1b: the section reaches no audience; `ceiling`, `uncertainty_band`,
`urf_modifiers` and `cap_level` are excluded key classes everywhere, so if
the boundary ever changes, what survives is `{category_id, category_name,
claim_label, confidence, e_ids, limiting_absence, rationale}` — exactly the
pair this panel renders plus its envelope. Never let either ceiling
vocabulary out of the section into client-facing prose.

### Enrichment pathways

- **Connector.** The parent's — the T1 technographic pathways that most often
  raise a ceiling, and `first_party` filings where the limiting absence is a
  published document. See O1b.
- **Web search.** The `limiting_absence` is the query: "[Entity] automation
  inventory OR process mining OR bot run volumes" for the P3C1 exemplar —
  T1-T2 where the entity or a regulator states it, T5 where only a vendor
  does (W6). Whatever is found is minted and the ceiling recounted; a ladder
  that returns nothing is the rationale's half (b), never a row.
- **Gap-to-pathway.** None of its own — `rows` reports `empty_required` on
  the parent. A row whose `limiting_absence` is not searchable is invisible
  to the worklist; G14 and the rationale's two-half rule are the check.

---

## O10 · Evidence coverage

### Baxter positive pattern

> "Share of the 706 sub-capabilities this run serves that carry at least one
> linked evidence item, counted over the same cell set the heatmap grid
> renders." (denominator_definition — stated and rendered; the 706 is a v5.0
> fact)

> "Linkage is near complete; depth is not. 133 of 706 served cells carry three
> or more citations, 544 exactly two; the ceilings panel names what would deepen
> each." (note — the census refusing to let a good headline hide a thin middle)

Shape notes, measured: per-pillar rows carry `cells_total` and `cells_covered`
so the reader can recount; overall 98.9 against the 80 gate with `below_gate:
false` per pillar. Logix shows the same card failing honestly: all four pillars
below the gate, `below_gate: true` on each, the lowest named in the note —
a failing census rendered as failing.

### Anti-patterns

- **MEM-0080 / the CG-15 boundary** — the census and the heatmap counted
  different cell sets — measured: O10's per-pillar denominators sum to 705 while
  the heatmap payload declares 72 evidence drawers, and the attempt to close the
  gap by generating drawers for all 633 remainder cells was refused (99 of 633
  syntheses in 23 template groups) — the rule: coverage computes over the SAME
  cell set the heatmap serves, the denominator says exactly what is counted, and
  the gap is stated rather than closed with manufactured drawers
  (EXEMPTION_SATISFIED_BY_A_TEMPLATE is the neighbouring failure: 517 of 517
  uncited cells once bought the absence exemption with one constant two-rung
  ladder).
- **(no MEM) / the pack's HONESTY block** — never round up across the gate:
  79.6% renders as 79.6% with `below_gate: true`; an overall 96% with one pillar
  at 62% is a failing assessment presented as a passing one — the per-pillar
  breakdown is required precisely so the overall cannot hide it.

### Exclusion set

This section is **NEVER_SERVED** — the census is our record of our own method,
and it reached the customer body in full until 2026-08-18 with nothing rendering
it only because the web adapter happened to drop the keys ("a wire leak standing
behind a UI accident", both promoted clients affected). Produce it fully; it is
promoted, validated and read internally. `tier` is an excluded key class — note
the generated allowlist's tiers rows keep `{count, max_evidence_level, pct}`
with the `tier` key itself already absent. `r_layer` reaches no audience.

### Enrichment pathways

- **Connector.** None — the census is computed from this run's cells and
  links (invariant 8); no connector adds to a count. What moves this surface
  is registration elsewhere: every pathway on H2 and H6 that links a row to
  a cell raises `cells_covered`.
- **Web search.** None of its own. A below-gate pillar is closed on the
  heatmap — the H3 ladder run against the cells the `note` names — never by
  searching "coverage". The `note` is this card's handoff to those pathways.
- **Gap-to-pathway.** Every field emits `empty_required`, and every one is
  computed from the payload being written. A gap here means the census was
  not computed, never that research is missing.

---

## O11 · Evidence tier distribution

### Baxter positive pattern

> "Third-party reporting carries this assessment: 74 of 127 linked items are T3
> and only six are T1, so the document's standing verb is 'signals suggest'
> rather than 'uses'. The 26 vendor-collateral items support nothing above L2
> without a second, independent source." (mix_implication — the point of the
> card: what vocabulary this mix licenses, said plainly enough to hold the other
> surfaces to it)

> `item_count: 127` and `fact_count: 4118` — distinct and both reported: one
> annual report is ONE item carrying many facts.

Shape notes, measured: `max_evidence_level` rendered per tier; `self_sourced_pct`
19.7 — under the ~50% mark above which corroboration is structurally weak; the
claim-class histogram reports its 5 unlabelled items as unlabelled rather than
absorbing them.

### Anti-patterns

- **MEM-0047 / CHECK_NEVER_RAN_READS_AS_UNKNOWN** — a required share measured
  against an origin value no row has ever carried — measured: `self_sourced_pct`
  resolved from `origin = 'internal'` (0 of 25,537 evidence rows), and
  `entities.domain` was NULL on all 166 entities with `svc_api` holding no grant
  — the numerator was always zero and the share was always null, for every
  client, since the field was written — the rule: the share is a share OF the O2
  `website` domain (REF-0029 made it the third source); write that field bare
  and lowercased, because a URL-shaped value matches no `source_domain` and
  renders a confident 0%, which is worse than the null it replaced.
- **MEM-0087 / the tier rule** — machine scans (Hubbl / BuiltWith / Wappalyzer /
  Explorium) filed as T4 rather than T1 — measured: +0.85 mean ERS on identical
  content re-registered at T1 — this understates T1 in the histogram AND
  suppresses ceilings at once, and it is the most common misclassification in
  this corpus — the rule: recount at the true tier rather than adjusting the
  histogram; a `ceiling_estimate` count of zero is the companion tell that
  ceilings were asserted as facts rather than labelled.

### Exclusion set

Same section as O10, same boundary: **NEVER_SERVED**, no audience at all — the
tier histogram, the claim-class split, the self-sourced share and the gate line
are how well WE evidenced the assessment. `tier`, `ers` and the rest of the
method vocabulary are excluded key classes everywhere else they might escape
(the evidence index and cell drawers were the measured leak — 4,527 probe
strings and row-level tiers serving before the class strips existed, D1).
`self_sourced_basis` is a contract key — carry it so the share names its
denominator. `r_layer` reaches no audience.

### Enrichment pathways

- **Connector.** None — a census. The histogram changes only when
  registration does: the T1-never-T4 rule for machine scans
  (`clay_taxonomy.json` Tech Stack) is the single correction that most moves
  the mix, and `self_sourced_pct` becomes computable only after O2 states
  `website` bare and lowercased (REF-0029).
- **Web search.** None of its own. A T3-dominant mix is repaired by fetching
  first-party and registry sources (T1-T2) on the surfaces that cite them —
  recount, never adjust; the `mix_implication` then licenses more.
- **Gap-to-pathway.** The counts and `mix_implication` emit `empty_required`.
  The machine contract marks `self_sourced_basis` `not_producer_authored`,
  so the worklist never reports it; the closure for a null `self_sourced_pct`
  lives on O2's `website` member, which IS reported there as
  `must_present_member`.

---

## O12 · Thought leadership signal

### Baxter positive pattern

> "In 2018 BCU was 'awash in data but no strategy.' Led org-wide listening tour:
> 'What are your goals? What are your pain points?'" (John Sahagian, SVP Chief
> Data Officer, PYMNTS panel, 2025-08-01 — a named person, dated to the day,
> verbatim, and the data chief's own account of the arc the root-constraint
> finding describes)

> `alignment: {"value": "CORROBORATES", "clause": "The data chief's own account
> of the strategy-first, infrastructure-second arc the root-constraint finding
> describes"}` — the alignment clause ties the quote to a finding, which is what
> admits it.

> `author_role: "President, BCU (assumed the role 1 July 2026; previously
> Executive Vice President and Chief Operating Officer)"` — the role as stated
> at the time, with the transition noted against the roster.

Shape notes, measured: five entries (this card measurably went 3 → 5 on
resubmission — three is the floor, not the goal), every one a named person with
a role, a headline as published, a verbatim quote of 85–232 characters, a date
to the day, `linked_subcap_ids` and an `e_id`.

### Anti-patterns

- **(no MEM) / CG-26** — two entries citing one document — measured: one
  congressional testimony quoted twice, different quotes, different evidence ids,
  different alignments — not duplicates by any field check, duplicates to every
  reader (same link, same author, same date) — the rule: a second quote from a
  document already cited goes INSIDE that entry, citing both e_ids; the freed
  slot belongs to a document the ladder has not reached (9-antipatterns §3).
- **measured · Logix thought_leadership** — an institution as the author —
  measured: `entries[3]` carries `author_name: "Logix Federal Credit Union"`,
  its quote is the webinar's TITLE ("Logix Drives Analytics Through Data
  Governance"), dated 2021-12-01; and `entries[2]`'s author is a "Director,
  ProSight Fraud Alert Network" — a third party writing ABOUT the client — the
  rule: this card is named client executives speaking in their own words; a
  title is not a quote, an institution is not a person, and third-party coverage
  belongs in the evidence store, not here.
- **measured · Logix thought_leadership** — the flag, the prose and the array
  disagree three ways — measured: `thin: false` while the empty_state reason
  opens "Three admitted entries… The card is marked thin", over an `entries[]`
  of four — the rule: `thin` and every stated count are recomputed from
  `entries[]` at submit; counts are computed, never stored, and prose inherits
  that rule.
- **(no MEM) / CG-27's span exception** — never edit a quote — measured while
  fixing the abbreviation sweep: a tidy-up rewrote the chief executive's
  congressional testimony from "greater CFPB scrutiny" to the full phrase,
  misquoting the source and breaking the verifier — the rule: `quote` and
  `headline` are verbatim spans (headline "as published. Do NOT rewrite it");
  spell out abbreviations in labels, never inside a span
  (`packages/shared/abbreviations.py` holds the boundary).

### Exclusion set

The whole section is **customer-withheld** (`CUSTOMER_WITHHELD`), and both
payloads additionally mark `entries` internal_only — produce it fully for the
internal and AE readers, and read `?audience=internal` before diagnosing an
absence (MEM-0061). Probe ladders in the empty_state (`sources_searched`,
`searched_on` — Logix records the per-executive routes there) are excluded key
classes; the customer empty_state, should the boundary ever change, keeps only
`{reason, closure_condition, closure, kind}`. Contact keys strip here as
everywhere. `r_layer` reaches no audience.

### Enrichment pathways

- **Connector** (facet `thought_leadership`): `clay` — the Find Thought
  Leadership contact data point, T2-T3: T2 for a first-party publication or
  named conference, T3 for trade press. `first_party` — the newsroom and
  trade-press rungs, T1-T2: named executives in their own words. `quartr`
  transcripts (T1-T2) are declared, not wired. The taxonomy's named residual
  gap is conference appearances and published bylines (a Custom data point).
- **Web search** (enrichment-first — the package will not contain this):
  "[executive name] [Entity] LinkedIn article OR post 2024 2025 2026" — T3,
  profile-derived; a repost is not the executive's view. "[executive name]
  conference OR panel OR keynote [year]" — T2 for a named conference
  programme. "[executive name] [Entity] podcast OR webinar OR interview" —
  T2-T3 by publisher. Earnings-call transcripts where public — T1-T2. The
  quote is a SPAN: register its source with a verbatim 50–500 char excerpt
  containing it; a vendor case-study quote is T5 (W6) and needs
  corroboration; the per-executive routes that return nothing are
  `sources_searched` rungs — the thin card's honesty — never rows.
- **Gap-to-pathway.** `entries` emits `empty_required`; `thin` emits
  `empty_optional`. An empty `entries` closes through the per-executive
  ladder or the section's declared `empty_state` with its
  `closure_condition` — and a declared empty state answers the worklist for
  the whole section.
