# Rulebook: overview · v1 (2026-08-19)

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
