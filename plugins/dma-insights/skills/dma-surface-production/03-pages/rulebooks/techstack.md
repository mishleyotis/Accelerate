# Rulebook: techstack · v2 (2026-08-19)

This is the techstack page's anti-pattern rulebook: the measured record of what
a promoted technology register looks like when it is right (Baxter, run
`c1351d25`) and the named failures that reached promotion before the gates
existed (chiefly Logix, run `d7ed1d90`, the worked test client). The
**techstack producer reads it before authoring, as Method step 2**, alongside
`get_memory_digest` + `search_findings`; the **rectifier is its only writer** —
a producer never edits it, and an edit with no finding behind it is an opinion.
Entries flagged by a USER or REVIEWER are **PERMANENT and never retired**,
whatever later rounds conclude. Baxter is **v5.0-shaped — 17 categories
including P1C5, 706 cells — so every shape-specific count quoted from it
(51 register rows, a 5-peer cohort, 16/30/2/3 status split) is a v5.0 fact of
that run, not a contract**; a v7.0 run has its own.

The census for this page, so nothing is minted to fill it: the Surface
Specification's D6 defines exactly two surfaces — T1, the register, and T3,
the per-row detail sub-page a register row opens — and the T-family stops at
T3. T2 recounts THIS register but renders on the insights page (its rulebook
entry is `rulebooks/insights.md § T2`; the split is the spec's own), the
run/version diff is V1 on Health, server-computed with no producer, and there
are no T4–T8 anywhere in the Surface Specification — the surface map
(`05-lifecycle/surface-map.md`) says so and forbids minting ids for the
directory, refresh-cadence and run-history chrome that tasking vocabulary
sometimes calls by those names.

---

## T1 · Technology stack register

What serves to whom is settled (D4, DECISIONS.md, 2026-08-19) and the producer
writes with it in view. A row surfaces on the **customer-audience** page only
when all five hold; the internal audience sees the full register with status
chips:

1. **Status ∈ {CONFIRMED, ABSENT}.** ABSENT stays — Baxter's 3 ABSENT rows
   (Salesforce Data Cloud, CRM Analytics, MuleSoft, each named
   searched-and-not-found) carry the gap argument the page exists to make.
   INFERRED and CLAIMED are internal-audience only.
2. **Corroborated:** ≥2 evidence ids from distinct registrable domains, OR a
   single source of tier T1–T2 that is a filing, a live technical observation,
   the institution's own materials, or a job posting. Logix calibration: 15 of
   32 rows are single-source; of those, the live-observation row passes
   (TS-014, Cloudflare server header read at the domain on 2026-08-18) and the
   scan-only rows fail (TS-029 Avaya, TS-030 Marketo).
3. **Material:** mapped to a DMA layer with `linked_subcap_ids` non-empty.
   Generic web-presence/martech fails materiality unless its `dma_impact`
   names a scored capability it moves — Logix TS-016 (HubSpot CMS), TS-017
   (GA/GTM/Hotjar) and TS-027 (iCIMS careers portal) are the calibration rows,
   and TS-017's DATA-layer placement inflating `layers[].detected` is the
   measured defect.
4. **Correctly attributed:** `identity_ok IS NOT FALSE` on every cited row.
5. **Tier rule preserved:** a machine technographic scan is **T1, never T4**
   (single-sourced in `02-inputs/clay_taxonomy.json`; MEM-0087's measurement:
   re-registering one scan at T1 gained +0.85 mean ERS on identical content).

Applied to Logix today: of its 9 CONFIRMED rows the two generic ones (TS-017
martech, TS-027 careers portal — TS-016 fails materiality too but is already
internal-only as INFERRED) fall to rule 3, plus 1 ABSENT = **8 rows
customer-facing, 32 internal**. Enforced as the serve-side allowlist filter
(D1 mechanism) plus a submit-time **warn, not block**, when a CONFIRMED row is
single-source scan-only.

### Baxter positive pattern

A CONFIRMED basis is one clause, dated, and names who said it:

> "Jack Henry's own April 2025 relationship release names Episys as the core
> BCU has run since 1999, now cloud-hosted." (`detection_basis`, TS-101,
> CONFIRMED, L1 — the vendor naming the institution, with the date)

An ABSENT row states what was searched and why the absence matters, in the
basis itself:

> "Searched and not found across a profile of more than two hundred platforms,
> while Salesforce already holds the member system of record."
> (`detection_basis`, TS-301 Salesforce Data Cloud, ABSENT, L2 — the searched
> absence is the page's gap argument, not a blank)

A CLAIMED row lets the status carry the epistemics instead of rounding up:

> "Listed by BCU on its own digital banking page; no independent detection of
> the wallet integration is available in the technographic profile."
> (`detection_basis`, TS-222 Apple Pay, CLAIMED, L4)

And the thread reads the register's shape rather than recapping rows:

> "Fifty-one rows tell one story by shape: operations and member-facing layers
> carry the confirmed strength — the Jack Henry core, Lumin at the front door,
> Agentforce in production — while the data layer holds no confirmed product
> at all: two named absences and a parallel audience platform."
> (`narrative_thread`)

Shape notes, measured on the body: 51 rows, every one carrying `status`
(16 CONFIRMED / 30 INFERRED / 2 CLAIMED / 3 ABSENT), so the landscape strip's
four counts recompute; `vendor` and `product` populated and separate on all
51; every row cites `e_ids`; the layer rollup puts `is_primary_gap: true` on
DATA (detected 6, expected 8) — exactly the layer whose two ABSENT rows carry
the argument. `dropped: []` is legal on this run only because nothing was
dropped. Logix's final round adds what Baxter's shape predates: `layers[]`
rows carrying `detected_basis` ("Computed from this section's own items[]…")
and an `expected_basis` that **enumerates the product slots** the denominator
counts — "17 product slots this assessment expects a single-brand credit union
of this size to fill… A product denominator, not a cell count" — so the
denominator can be argued with rather than taken. Both basis fields are in the
served contract; write them.

### Anti-patterns

- **MEM-0062 / CG-20** — a category shipped as a vendor — measured 2026-08-14:
  of 39 distinct vendors across both promoted registers, 3 were categories
  ("Integration platform", "Portal platform (unnamed)", "e-signature vendor
  (unnamed)"), all on the un-enriched client, whose 12-row register's OWN
  `empty_state` said "The technographic scan that would normally widen this
  register did not run" — and nothing read it — the rule: a vendor is one
  company and a product is one named product; a candidate that cannot be named
  and cited goes to `dropped[]` with the reason; a thin register's enrichment
  state is machine-readable (`enrichment_register.json` →
  `enrichment_status`), never a prose note nothing reads.
  **PERMANENT — never retire** (raised_by_kind USER); test:
  `apps/mcp/tests/test_vendor_is_a_company.py` (CG-20, the three placeholder
  rows refused verbatim, the 36 real companies as false-positive controls).
- **MEM-0082 / PROVENANCE_NAMES_THE_TOOL** — detections reported from an
  enrichment that never ran — measured by re-running it for real: the Clay
  task returned Tech Stack `completed` with an EMPTY value, Recent News and
  Open Jobs in `error`, and a grep of the package report for the ten vendor
  names the producer had "detected" returned 0 hits each; 20 strings across 5
  pages depended on that scan — the rule: a detection exists when the
  enrichment's own returned state carries it; provenance names the document,
  never the tool; a scan that returned error or empty grounds nothing and is
  reported as the enrichment gap it is.
- **MEM-0087 / EVIDENCE-TIER-MISCLASSIFICATION** — a machine technographic
  scan registered below T1 — measured: E-CC-308 sat at T4 with ERS 3.75; eight
  re-registrations of the same scan output at T1 returned mean +0.85 ERS on
  identical content, so the wrong tier had been silently capping every cell
  the scan grounded — the rule: register scan output at T1, and expect
  `scan_tier_violation` to refuse the wrong tier by the scan's own name-shape;
  test: `apps/mcp/tests/test_source_rules.py` ("A machine technographic scan
  is T1 (MEM-0087)" block).
- **MEM-0046 / COMPOSED_VALUE_ASSUMES_ITS_INPUTS_ARE_DISJOINT** — vendor and
  product composed blind downstream — measured on Baxter's customer insights:
  landscape tiles printed "Salesforce Salesforce Data Cloud" and a vendor-only
  row gave "Snowflake None" (closed by REF-0020's `_product_label`) — the
  rule: `vendor` and `product` are separate fields and BOTH are populated;
  never a row with the product missing, because labels on other surfaces are
  composed from these two columns and a None or a duplicated vendor becomes
  client-facing text.
- **MEM-0084 / RULE_HELD_IN_TWO_PLACES_DRIFTS** — `is_primary_gap` never
  reached a client — measured on Logix, this section's layer rollup:
  `computed.py` read a DB column no writer populates while `writer_spec.json`
  sourced the flag from the submitted section — the rule: the `layers[]` you
  submit is the source of `is_primary_gap`, so set it deliberately on the
  layer the register's own absences argue for; `detected`/`expected`
  recompute from `items[].status` and the enumerated denominator, never
  asserted; test: `apps/api/tests/test_computed_at_read.py`
  (`test_techstack_layers_NEVER_READS_is_primary_gap_FROM_THE_DB_COLUMN`).
- **MEM-0002 / CONTRACT_FIELD_DISCARDED_AT_PROMOTION** — the dated register
  that cannot age — measured on the served Baxter run 2026-08-08: 51 register
  rows, `as_of` present on 0, while the bases name April 2025, March 2026,
  November 2022 — the rule: carry `as_of` on every row whose basis names a
  date (Logix's final round carries it on its five live-observed rows); a
  register whose rows are dated only inside prose cannot be re-verified or
  aged by anything downstream.
- **MEM-0060 / CG-17** — a required list satisfied by `[]` — measured across
  both promoted clients: `required: true` was passed by an empty list because
  validation only caught `None`, and a whole surface vanished with no
  `empty_state`; `techstack.dropped` is the ONLY field in the whole contract
  allowed to be empty undeclared (`may_be_empty`), because an empty drop list
  is ordinary — the rule: send the items, or declare the section's
  `empty_state`; an empty list is a claim ("there are none") and is made
  deliberately. **PERMANENT — never retire** (raised_by_kind USER); test:
  `apps/mcp/tests/test_required_list_not_silently_empty.py`
  (`test_the_may_be_empty_exemption_has_not_spread` pins the exemption count
  at exactly 1).
- **(measured on Logix) / D4 rule 3** — bundles and martech wearing a layer —
  measured on the promoted body: one row carries three products under vendor
  "Google and Hotjar" (TS-017), and TS-015 ("Microsoft 365 and Azure Active
  Directory") and TS-024 ("Okta and SailPoint") each fold two products into
  one row; TS-017's DATA placement inflated `layers[].detected` — the rule:
  one row per product, one company in the vendor field; generic
  web-presence/martech counts toward a DMA layer only when its `dma_impact`
  names a scored capability it moves.
- **9-antipatterns.md #7 / no gate sees it** — a field the renderer cannot
  read — measured in that entry's table: `rollups.detected` recomputed locally
  rendered "0 of 6 detected" over six named products — the rule: `status` is
  required on every row because the landscape strip recomputes its four counts
  from it and is uncomputable without it; write `layers[]` in the shape the
  renderer reads (`techLayersOf` rolls up over the items), then look at the
  rendered page, because no contract gate can see a legal-but-unread field.
- **9-antipatterns.md #9 + #4 (CG-27)** — an absence explained instead of
  removed, and abbreviations on a client surface — the rule: a row or field
  with nothing in it renders no row; a producer-authored reason that is real
  information renders (Logix's `empty_state.reason` explaining that the
  institution's own site answers the verifier with an HTTP 403 while serving
  ordinary readers is the model), a workflow status word ("queued", "pending",
  "not researched") never does; spell abbreviations out on first use in every
  prose field — Baxter writes "web-services application programming
  interface" in impact prose — but never inside a verbatim span.

### Exclusion set

`r_layer` reaches no audience — `NEVER_SERVED_KEYS` strips it before the
audience branch in `apps/api/dma_api/redaction.py`; write it anyway (the
reasoning trace is owed to the assessment) and mark internal paths anyway
(invariant 5: producer marking is mandatory, the strip is the backstop). The
excluded key classes drop from the customer body at any depth: probe-ladder
keys (`sources_searched`, `queries_run`, `searched_on`), method keys (`tier`,
`ers`, `recency_band`, `discovered_by`, `provenance`, `link_basis` — the
row's contracted `evidence_level` L1–L4 serves; a T-code never does) and cap
keys (`cap_level`, `ceiling`, `uncertainty_band`, `urf_modifiers`).
`empty_state` serves only `{reason, closure_condition, closure, kind}` — a
producer's real reason renders, a probe never does (owner adjudication
2026-08-14). The D4 status filter is itself an exclusion: INFERRED and CLAIMED
rows never reach the customer page, so nothing in the customer-facing argument
may depend on them. The customer serve is allowlist-LAST and fail-closed (D1):
for this section only `compliance_attestations, dropped, e_ids, empty_state,
internal_only, items, layers, narrative_thread, produced_at, producer_version,
r_layer` and the enumerated per-item/per-layer keys survive
(`apps/api/dma_api/customer_allowlist.json`, generated — edit
`packages/shared/serve_classes.json`, never the file); an invented key drops
at serve with the drop counted in the receipt.

### Enrichment pathways

Connector pathways (facet `techstack`, `02-inputs/enrichment_sources.json`,
in precedence order): the `explorium` machine technographic scan — T1, and
**live in a producer session**, corrected 2026-08-23. Two paths carry this
name and only the ingest one is dark: the worker's scan
(`apps/worker/dma_worker/enrichment.py`) needs a Secret Manager key that does
not exist, while the **Vibe Prospecting MCP connector authenticates at the
session, needs no key, and is already auto-approved** — `match-business` with
name and domain, then `enrich-business` with `technographics` + `webstack`.
Measured on three promoted clients: 392 premium technologies for Baxter, 357
for Axos, 147 for Logix, naming Symitar Episys, Temenos, Fiserv, FICO Falcon,
Jack Henry SilverLake, nCino and Yodlee among them. The instruction this
replaces ("no live API … records NOT_RUN with that reason") conflated the two
paths and was costing every run its technographics. What does not change: the
tool console (vibeprospecting.explorium.ai) is never a citable source, so the
scan is the CANDIDATE LIST that makes the recursive search converge and each
row is corroborated to `CONFIRMED`/`INFERRED`/`CLAIMED` from a first-party
source, a posting, a vendor release or a live technical read. Then the `clay` Tech
Stack company data point — T1, producer-session only, so a scheduled run
cannot hold it; and `first_party` — the entity's own platform statements,
T1-T2, which is where a `detection_basis` clause comes from. The tier rule is
single-sourced in `02-inputs/clay_taxonomy.json` and it is D4 rule 5: a
machine technographic scan is T1, never T4 — the misfile was silently capping
every cell one scan grounded until MEM-0087 measured it (+0.85 mean ERS on
identical content). Provenance names the DOCUMENT the scan or call surfaced,
never the tool (MEM-0082): a scan that returned error or empty grounds
nothing, and a thin register's enrichment state is machine-readable
(`enrichment_register.json` → `enrichment_status`), never a prose note
(MEM-0062).

Web-search pathways (the dma-research discipline — decompose per row, proxy
escalation before any ABSENT, entity name in every query, year markers in
two-plus):

- `"[Entity] [system] administrator OR analyst job description"` — a job
  posting naming the system is a D4 rule-2 single-source pass: the posting
  is first-party T2 on the entity's own careers page, T3 through an
  aggregator; register the requirement line as the verbatim 50–500 char
  span. On Logix this route confirmed rows the 403-answering website could
  not.
- A live technical read of the entity's own domain (server headers,
  app-store package identifiers) — T1-T2 and dated by the read: the
  calibration rows are TS-014 (Cloudflare header read at the domain on
  2026-08-18, passes) against the scan-only TS-029/TS-030 (fail); carry
  `as_of` on every row whose basis names a date (MEM-0002).
- `"[Entity] selects OR implements OR migrates [vendor] 2019..2026"` — the
  entity's own newsroom is official disclosure T2; the vendor's release
  naming the institution is vendor collateral, T5 with corroboration
  required (W6), whatever tier you type — it can still name the product,
  and the status carries the epistemics (CLAIMED until corroborated).
- `"[Entity] [absent platform] partnership OR integration platform OR data
  cloud"` — the ABSENT rows' ladder: searched-and-not-found is the page's
  gap argument, and the negative search registers as the row's basis prose
  and the run's ladder, never as an evidence row (W6).
- `"[Entity] [category] replacement OR modernization OR conversion RFP"` —
  the migration signal `clay_taxonomy.json` names as this facet's custom
  gap ("platform migrations announced in the last 24 months"): T2 in the
  entity's own words, T3 in trade press.

Gap-to-pathway: this section emits `empty_required` on `items` and `layers`
and `empty_optional` on `compliance_attestations`; `dropped` is the
contract's ONLY `may_be_empty` list (MEM-0060 pins the exemption count at
exactly 1) and is never reported as a gap. Row-level holes — a missing
`as_of`, an uncited CONFIRMED, an off-vocabulary status — never reach
`list_enrichment_gaps`; CG-09, CG-17, the D4 serve filter and this rulebook
are the guards there, and the rendered-page readback is yours.

---

## T3 · Platform detail

### Baxter positive pattern

The impact makes the four moves in order — deployed capability (cited), the
cells it reaches, the vendor-documented boundary, the pathway across it — in
40–90 words:

> "Episys is BCU's system of record for members, accounts and postings,
> cloud-hosted since the 2025 Jack Henry renewal, and its release train sets
> what Technology Roadmap & Investment Planning can schedule in a quarter.
> Jack Henry publishes the reach beyond that boundary as a separate product:
> SymXchange is the web-services application programming interface third
> parties use to access the Symitar database. Zennify's pathway is that
> service layer and the contracts on top of it, so channel and analytics work
> stops queueing behind core releases." (`dma_impact`, TS-101 — the boundary
> is the vendor describing its own architecture, and it is citable)

An ABSENT row grounds the pathway in the vendor's own scope statement, not in
a hunch:

> "Salesforce describes a data cloud as what gives a single cohesive profile
> when customer data is spread across disparate systems — which is BCU's
> shape, with Agentforce already in production above it." (`dma_impact`,
> TS-301 Data Cloud, ABSENT)

A peer row that established a competing answer carries the source and the
date; `deployed: false` is EARNED, not defaulted:

> "Established competing answer: Alliant selected Backbase's Engagement
> Banking Platform (Backbase press release, fetched, published 2025-01-28;
> independently covered by FinTech Futures and Retail Banker International,
> Jan 2025). Post-2023 announcement of a competing platform → deployed:false
> for Lumin Digital." (`peer_deployments[]`, TS-201, with `source_url` and
> `as_of`)

And a row the producer is privately sure of stays `null` when the evidence
rules are not met — the basis says exactly why:

> "Almost certainly true in fact, but unestablished under the evidence rules:
> Zelle's Jack Henry pay-center page for LMCU states verbatim 'It's easy —
> Zelle® is already available within the Lake Michigan Credit Union mobile
> banking app!', but that page contains no publication date… No single fetched
> source satisfies URL + own-date + 50-500-char excerpt simultaneously, so the
> row is left null rather than asserted." (`peer_deployments[]`, TS-216)

Shape notes, measured: `peer_coverage` is stated only where the breakdown
supports it — 0.2 over 1-of-5 breakdowns, and 0.0 on Lumin where two peers
carry established COMPETING answers; unknowns are in the list with
`deployed: null` and what-was-searched in the basis; the identity-unresolved
peer (two institutions named "Consumers Credit Union") is `null` on every
product with the ambiguity as the reason; a vendor aggregate ("Blend's own
release claims seven of the ten largest credit unions as partners and names
none of them; an unnamed aggregate cannot establish a named institution")
distributes as `null` to every peer with the aggregate named in the basis
(TS-211); a 2004 core
conversion is served as "dated 2004 and uncontradicted rather than current"
(TS-101, Alliant), never as current.

### Anti-patterns

- **(the pack's own recorded history) / AG-04** — impact arithmetic and peer
  verdicts from no source — the shipped card computed `baseline = score − 1.2`
  and `target = score + 1.3` for an ABSENT product, decided "✓ deployed"
  against a NAMED credit union from `hashCode(ts_id + peerName) % 100`, and
  rendered "—% adopted" on a zero-width bar over a `peer_coverage` with no
  contract field — the rule: never derive a score and never project one; AG-04
  refuses a share with no breakdown, a `deployed: true` row missing
  `source_url` or `as_of`, and a share disagreeing with its own breakdown by
  more than one peer; a row with no promoted impact says so rather than
  computing one; tests: `apps/mcp/tests/test_item_evidence.py` (AG-04 block)
  and `apps/web/tests/adapter.test.js` ("a tech row with no promoted impact
  says so rather than computing one").
- **MEM-0068 / WRITE_PATH_WITH_NO_READ_PATH** — cited peer evidence nothing
  reads — measured 2026-08-15 on the sibling platform page: 25
  `peer_deployments` rows served, every one with a fully cited `basis`,
  rendered ZERO times, and the owner's verdict recorded: "the platform page
  has all bad design issues: blanks stated instead of sourced or inferred;
  duplicates etc." — the rule for this page's identical contract: a
  `deployed: null` row's basis IS the content — it is the difference between
  "no peer does this" and "we did not look"; include the peers you could not
  establish; write under the keys the renderer reads and look at the rendered
  page. **PERMANENT — never retire** (raised_by_kind USER); test:
  `apps/web/tests/adapter.test.js` ("the tech item carries the fields its
  detail page exists to explain" — `dma_impact`, `peer_coverage` and
  `peer_deployments` survive the adapter, and "an unestablished peer stays
  null and is not dropped").
- **MEM-0052 / RULE_HELD_IN_TWO_PLACES_DRIFTS** — reasoning that reads as
  pitch, and the withholding rule that never fired — measured: `dma_impact`
  carried sell copy on 51 of 51 rows of one client, 26 opening "Zennify's
  pathway is…", while the declared customer-withholding rule was keyed on a
  section name production never passes, so its only test and the dead rule
  agreed with each other; all 51 were removed by the vendor safety net the
  module itself calls "not a substitute" — the rule: write move 4 as the
  integration work that follows from the boundary, never as an offering
  pitch; no seller vocabulary anywhere (`SELLER_VOCABULARY` and the vendor
  name are safety nets, not the mechanism); `dma_impact` is internal-audience
  until a submit-time gate can tell the reasoning from the pitch
  (`CUSTOMER_ALWAYS` on `('techstack','techstack')` strips
  `items[*].dma_impact` in the meantime); test:
  `apps/api/tests/test_serving_read_path.py` (calls the enforcement point
  with the section name pages.py actually passes).
- **(measured on Logix) / the pack's four moves** — a template impact that
  never leaves the assessment — measured over the 32 promoted impacts: 21
  open on the frame "X is what ⟨Cell⟩ and ⟨Cell⟩ are about", 14 close
  "…rest(s) on the workbook rather than on this row", 0 cite a vendor's own
  documented boundary, 0 state a pathway, and 0 of 32 rows carry
  `peer_deployments` — the rule: four moves, in order, per row — the deployed
  product's capability (cited), the cells it reaches, the vendor-documented
  boundary (fetched and registered as evidence before writing), the pathway
  that follows from it; then research the run's peer set for the core, the
  digital channel, the CRM estate, the integration layer and every ABSENT
  row, because a register that explains a third of its rows reads as a
  register the producer got bored of.
- **CG-12 / a face field is a label** — measured verbatim: TS-201's
  634-character, three-sentence `detection_basis` overflowed every register
  row's right-hand badge — the rule: `detection_basis` is ONE CLAUSE inside
  160 characters; the argument it was carrying moves to `dma_impact`, which
  is where the contradiction-resolution about the Alkami residue now lives on
  the promoted Baxter row; test: `apps/mcp/tests/test_face_budgets.py`.
- **9-antipatterns.md #6 / no gate sees it** — a peer figure from a second
  cohort — measured there as fourteen of sixteen categories carrying a peer
  median computed from a cohort assembled once and never revisited — the rule
  for this page: the peer set is the run's own, read from `peer_table` in the
  bundle, never assembled; every product's `peer_deployments[]` names the
  same peers, and `peer_coverage` is a share of that one named set — two
  bases on one surface is invisible to every check, so the producer is the
  only defence.

### Exclusion set

`items[*].dma_impact` is withheld from the customer audience by rule —
`CUSTOMER_ALWAYS` keyed on `('techstack','techstack')` in
`apps/api/dma_api/redaction.py` — until a submit-time gate can tell the
reasoning from the pitch; write it anyway (the drilldown is the internal
reader's working view), and write it clean, because the strip is default-deny
in the meantime, not permission to sell. `peer_coverage` and
`peer_deployments[]` DO serve to the customer, so every `basis` sentence is
client-readable: no seller vocabulary (the `SELLER_VOCABULARY` net exists
because one AE-addressed sentence reached a customer body), no assessing-firm
name (the `VENDOR_NAME` net records every path it fires on), no probe-ladder
keys smuggled into prose — what was searched belongs in the basis as a
sentence about the world, in the peer's own terms. Method keys (`tier`,
`ers`, `recency_band`, `discovered_by`, `provenance`, `link_basis`) and cap
keys drop from the customer body at any depth; `r_layer` reaches no audience.
Per-item keys are allowlist-bounded to the contract's own
(`as_of, detection_basis, dma_impact, e_ids, evidence_level, layer,
linked_subcap_ids, peer_coverage, peer_deployments, pillar_id, product,
status, ts_id, vendor`) — anything else the producer invents drops at serve
with the drop counted in the receipt (D1, fail-closed). No colour, no hex, no
M-code in any prose (invariants 6–7); scores are served beside the prose and
never restated inside it.

### Enrichment pathways

Connector pathways: the same section, the same `techstack` facet as T1 —
plus the `clay` peer-deployments route under facet `peer_scores`
(`02-inputs/enrichment_sources.json`): peer platform deployments land T1 per
ESTABLISHED deployment, under AG-04's shape — one row per named peer,
unknowns as `deployed: null`, `source_url` and `as_of` on every
`deployed: true` row. No connector serves the peer set itself: it is the
run's own, read from `peer_table` in the bundle, never assembled
(9-antipatterns.md #6, above). The boundary move runs on the vendor's own
documentation: fetch the scope statement and register it before writing move
3 — a vendor-authored page bands as vendor collateral (T5, W6), which is
sufficient here because the claim it grounds is the vendor describing its
own product's architecture, never the assessed entity's capability; the
entity-side claims stay on the register's own evidence.

Web-search pathways (the peer protocol's routes, each named with the verdict
it can earn):

- `"[peer] [vendor] core conversion OR selects OR implements"` plus the
  vendor's customer-story pages — the vendor naming the institution earns
  `deployed: true` with `source_url` and `as_of`; the source is vendor
  collateral (T5, W6) and travels on the peer row as its named source, the
  basis quoting the verbatim span.
- `"[peer] [competing vendor] digital banking OR core platform"` — a peer
  named on a COMPETING product at the same layer earns `deployed: false`
  with that source, the strongest verdict after true (TS-201's
  Backbase-at-Alliant row is the exemplar).
- `"[peer] [system] PowerOn OR administrator job description"` — the peer's
  own careers posting naming the system earns `deployed: true` when the
  posting is the peer's own and dated (T2); an aggregator's copy is T3.
- `"[vendor] [product] API documentation OR developer"` — the boundary
  fetch, usually one page (SymXchange; Salesforce's own Data Cloud scope
  statement); registered before `dma_impact` move 3 is written, because a
  boundary with no fetch behind it is an opinion.
- A vendor aggregate ("seven of the top ten…", naming none) distributes as
  `deployed: null` to every peer with the aggregate named in the basis
  (TS-211) — a number is not a source for a named institution.

A peer search that establishes nothing is the `deployed: null` row's basis,
naming what was searched in the peer's own terms — a negative search is a
ladder rung rendered as honesty, never an evidence row (W6), and "not
researched" describes the producer, not the world.

Gap-to-pathway: none of its own — T3 reads `techstack.techstack`, so the
only worklist rows it can raise are T1's (`empty_required` on
`items`/`layers`, `empty_optional` on `compliance_attestations`). A row
missing its `dma_impact` or its peer breakdown is invisible to
`list_enrichment_gaps` — MEM-0068 is the measured cost of trusting a write
path over a read path on exactly this contract — so the rendered sub-page
readback is the check that sees this panel's content.
