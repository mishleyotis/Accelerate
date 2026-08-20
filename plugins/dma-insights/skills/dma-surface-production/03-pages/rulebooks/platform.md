# Rulebook: platform · v2 (2026-08-19)

This is the platform page's anti-pattern rulebook: the measured record of what
a promoted platform page looks like when it is right (Baxter, run `c1351d25`)
and the named failures that reached promotion before the gates existed (chiefly
Logix, run `d7ed1d90`). The **platform producer reads it before authoring, as
Method step 2**, alongside `get_memory_digest` + `search_findings`; the
**rectifier is its only writer** — a producer never edits it, and an edit with
no finding behind it is an opinion. Entries flagged by a USER or REVIEWER are
**PERMANENT and never retired**, whatever later rounds conclude. Baxter is
**v5.0-shaped — 17 categories including P1C5, 706 cells — so every
shape-specific count quoted from it (5 tiles, 8 recommendations, 27–28 gap
rows) is a v5.0 fact of that run, not a contract**; a v7.0 run has its own.

---

## P1 · Platform fit &amp; story

### Baxter positive pattern

The fit figure is read from the engine and its basis says so, renormalisation
included — Baxter's rank-1 card omitted `alignment` (no stated objective
established) and the engine renormalised to the three-term blend exactly as
the contract instructs:

> "Computed by the shared platform-fit engine: 100 x (0.66 x addressable
> opportunity + 0.26 x catalogue interconnect + 0.08 x greenfield family +
> 0.0 x strategic alignment) x 0.85 readiness = 45.5. […] Alignment basis:
> impact_fallback. Rank basis: fit. State: READY." (`fit_basis`, CRM
> Analytics — the 0.66/0.26/0.08 are 0.528/0.208/0.064 renormalised, not a
> second formula)

The story is about THIS client and reconciles to the arithmetic and the date
that beat it:

> "An analytics and reporting platform changes what BCU can evidence on
> demand. UDAAP Compliance sits at 2.0 and Fair Lending Compliance at 2.5
> because the activity is real — the employer-based membership model reaches
> diverse communities — while the documentation infrastructure that would
> show it by geography and income band is assembled by hand." (`story_md`,
> rank-1 — names the cells, names what the platform does not solve)

A peer row that established something carries the date and the source; a peer
row that established nothing carries the searches as its content:

> "Established. GreenState implemented MuleSoft alongside Salesforce Financial
> Services Cloud and Marketing Cloud with Silverline; the case study states
> the programme 'established the MuleSoft foundation that would support
> integration activities during the iterative build period', began in August
> 2021 and went live in May 2022." (`deployed: true`, `as_of: "2022-08-02"`,
> `source_url` to the Silverline case study)

> "Unestablished. Searches for CEFCU with MuleSoft, Boomi and application
> programming interface management surfaced no institution-specific source
> […] Neither a deployment nor its absence can be sourced." (`deployed:
> null` — the basis IS the finding)

Reach is derived, and the derivation is emitted with the numbers:

> "Reach is computed from this run's own technology register: a cell is
> reached when at least one register row lists it in its linked capabilities.
> Cells with no register row against them are stated as not-yet-reached,
> which is a property of the register and not a judgement about any product."
> (`estate_reach.derivation`, with `by_category` counts, `ts_id`s and
> statuses behind it)

A discard is checkable — cell count from the sweep, incumbent from the
register:

> "Twilio reaches two served cells, voice-activated banking and conversational
> IVR with generative AI, which is below the three-cell floor a tile has to
> clear. The layer is also occupied: Genesys Cloud, Glia and Tethr are all
> confirmed in the register, so the open question is what that confirmed
> voice estate is asked to do, not which vendor supplies it." (`discarded[]`,
> relevance 0.35)

Shape notes, measured: 5 tiles, each with its own `r_layer`, `e_ids`,
`estate_reach`, `integration_pathway` and 5 `peer_deployments` rows; 8
discards, every reason a fit-for-this-institution statement (already-owned ×3,
occupied layer, sequencing ×2, below the floor, out-of-layer) and none arguing
from vertical; `depends_on` chains MuleSoft ← Data Cloud ← Service Cloud, and
no card ranks above its foundation; the fifth tile is `state: TOO_NARROW`
with `fit_score: null`, `rank: null` and the reason stated — an honest null,
not an invented figure; `peer_coverage` 0.2 where one of five was established
and **omitted** on the tile where nothing was; `internal_only` marks
`platform_story.platforms[*].zennify_pathway`, keeping the client-facing
pathway sentences and giving the AE the pitch.

### Composite factors — provenance, disqualifiers, the two validations

Owner instruction, 2026-08-20: "the composite factors for platforms should
have clear DQs … greenfield opportunities has no deep search validation and
strategic alignment checks. Ensure thorough reasoning through the composite
factor scoring." The engine (`packages/shared/platform_fit.py`) computes;
this section is the reasoning the producer owes each candidate BEFORE the
engine's number is explained to a reader. Every threshold below is the
engine's own constant, quoted so a story can name the failing figure.

The four factors, each with where its input comes from and what disqualifies
it:

1. **Addressable opportunity** (weight 0.528 stated-alignment / 0.66
   fallback). Input: this run's own scored cells — gap to target × issue
   severity × per-cell evidence strength, over the cells the L3 area
   reaches. Provenance: the DMA package's workbook scores and issue
   register; evidence strength from the evidence register (tier ×
   freshness). Reasoning owed: the tile's `top_contributors` names the
   driving cells — a contribution you cannot walk back to named cells with
   their own gap/severity/strength figures is unexplained and does not ship.
2. **Catalogue interconnect** (0.208 / 0.26). Input: catalogue adjacency
   against ALL of the run's gap cells, from the pinned catalogue version.
   No enrichment moves this figure; a story that attributes it to anything
   but the catalogue is inventing.
3. **Greenfield family** (0.064 / 0.08) — binary: the register confirms the
   family ABSENT. **Deep-search validation is REQUIRED before a greenfield
   point is explained as ground**, because `family_absent` is a register bit
   and the register can be wrong for reasons the engine cannot see (measured:
   the technographic scan "completed with an empty result" twice on one
   client while its own domain 403'd the verifier — RC2). The ladder, in
   order, every rung registered:
   - the techstack register scan actually RETURNED ROWS for this entity — a
     scan that returned nothing proves nothing absent; the greenfield bit is
     then UNVERIFIED, not true;
   - the absence ladder ran for this family: Clay Tech Stack, the entity's
     job postings naming the family's products, and web search
     `"[entity]" uses OR selects OR implements [family vendors]` — each
     negative search recorded as a rung with query and date, never as an
     evidence row;
   - if the entity's own domain refuses the verifier, greenfield claims that
     domain would confirm or deny are stated as provisional, with the refusal
     named.
   A greenfield contribution the ladder cannot back is a `record_finding`
   (the register is wrong or unverifiable), never a selling point. The stakes
   are larger than 6.4 points: greenfield is also the engine's second
   tie-break, so a wrong bit reorders the page.
4. **Strategic alignment** (0.20 stated / 0.0 fallback). **The alignment
   check is REQUIRED**: alignment counts only when `alignment_basis` is
   `stated_objective` and `alignment_quote` is the entity's own words —
   board commitment, strategic plan, RFP, earnings language — resolving
   through `get_evidence` to a T1–T3 item for THIS entity and run. A
   paraphrase, an AE's characterisation, or a vendor's claim about the
   entity is not a stated objective: leave `alignment` null, let the engine
   renormalise (0.66/0.26/0.08, basis `impact_fallback`) and let the card
   DISCLOSE that basis. Renormalisation exists so an unknown is never scored
   as zero; it is not a licence to invent a quote to reach the stated basis.

The disqualification ladder (the engine's states, in evaluation order — a
discard names the state AND the failing figure):

| DQ | Threshold | What the discard reason must say |
|---|---|---|
| `OUT_OF_VERTICAL` | relevance < 0.5 | the vertical judgement and its relevance figure — and note relevance also CAPS the fit multiplicatively, so a borderline family cannot buy its way back with gap surface |
| `TOO_NARROW` | cells addressed < 3 | the sweep's cell count against the three-cell floor |
| `INSUFFICIENT_EVIDENCE` | mean evidence strength of the DRIVING cells < 0.10 | which driving cells are unevidenced — an unevidenced cell counts 0.0 here, not the neutral prior |

`readiness_multiplier` is the fourth brake: not a DQ, but the story must say
when it, not the factors, is what holds a card down. An empty `discarded[]`
on a ranked page fails the only question an AE is asked in the room — *why
not X* — and a discard that says "not a fit" without its DQ state and figure
is that failure wearing a reason.

Rendering discipline (owner, 2026-08-20, from a screenshot of the live
tile): the app gives the scores; the `value×weight` working stays in
`factors[]` for the gates, never in prose or on a surface. Explain each
factor's contribution from its inputs — the reader can add up the block
figures.

### Anti-patterns

- **MEM-0068 / WRITE_PATH_WITH_NO_READ_PATH** — the page renders blanks while
  the payload carries cited peer evidence nothing reads — measured 2026-08-15
  on Baxter: 25 `peer_deployments` rows served, every one with a fully cited
  `basis`, rendered ZERO times (`grep -c peer_deployments` over both page jsx
  files = 0); 28 gap rows with `gap: null` read as blanks while every row
  carried a populated `name`, `current_score` and `catalogue_path`; owner:
  "the platform page has all bad design issues: blanks stated instead of
  sourced or inferred; duplicates etc." — the rule: a `deployed: null` row's
  basis is the content, not decoration; a field the reader will see as blank
  must carry its information under the keys the renderer reads, and the
  producer looks at the rendered page, not the payload, to know.
  **PERMANENT — never retire** (raised_by_kind USER); test:
  `apps/web/tests/acceptance/checks-platform.json` (PF-A1/PF-A4, driven by
  `apps/web/tests/open-app.js`, asserting "unestablished", ESTATE REACH and
  the readiness verdict render).
- **MEM-0095 / CG-31** — one number wearing two factor vocabularies — measured
  2026-08-19: after CG-30 pinned the cards, the overview opportunity tiles
  still rendered legacy factor systems (a six-factor breakdown summing to
  76.5 on one client, a three-factor one summing to 67.0 on the other)
  because the tiles were fixed by hand and zero gates read `tiles[].factors`
  — the rule: the fit, its factors, subtotal and readiness_multiplier are
  COPIED from `get_platform_fit`, never restated; the tile's composite and
  rank equal the card's fit and rank at the 0.05 grain, and legacy factor
  names are refused BY NAME. **PERMANENT — never retire** (raised_by_kind
  USER); test: `apps/mcp/tests/test_platform_fit_gate.py` (CG-31 block, nine
  tests).
- **MEM-0003 / CONTRACT_FIELD_DISCARDED_AT_PROMOTION** — five tiles promoted
  as one — measured on Baxter 2026-08-08: the writer spec sourced gap rows
  from `platforms.0.gaps`, promotion kept tile 0 of 5, and the client clicked
  the other four and found them empty (closed by REF-0002) — the rule: one
  tile per promoted L3 area or the area's tab renders empty; after promotion,
  read the served page and count the tiles.
- **(no MEM) / CG-30** — a fit figure from anywhere but the engine — measured
  in the pack's own history: before the engine existed two clients answered
  the gap two ways, one shipping 76.5 read off the OPPORTUNITY tile and the
  other five nulls, and 570 of 685 cards carried a breakdown disagreeing with
  their own headline — the rule: call `get_platform_fit`, read it, send the
  row back; a card whose `fit_score` differs by more than 0.05, whose `rank`
  disagrees with the engine, or that carries no score is refused at submit.
- **(no MEM) / ET-06** — out-of-vertical rendered as a discard instead of
  excluded before scoring — measured on Baxter's earlier round: a card
  "Insurance policy administration and claims" at relevance 0.15 with the
  reason "Out of vertical: its anchor cells belong to a carrier entity type"
  spent one of six client-facing slots telling a credit union the assessment
  shopped in the wrong industry; six clients ranked an out-of-vertical
  platform FIRST, one at relevance 0.35 — the rule: the vertical bounds the
  candidate set BEFORE relevance is scored, so an out-of-vertical platform
  never enters and has no discard to render; ET-06 refuses a discard reasoned
  from vertical either way; test:
  `apps/mcp/tests/test_candidate_vertical.py`.
- **(measured on Logix) / the pack's state rule + AG-01** — a non-READY state
  argued as a ranking — measured: all 5 Logix tiles carry
  `state: INSUFFICIENT_EVIDENCE` yet ship ranked 1–5 with stories, and 0 of 5
  carry a per-tile `r_layer` or `e_ids` (the section-level trace is the only
  one; Baxter carries one per tile) — the rule: read `state` before writing
  the story — `TOO_NARROW`, `INSUFFICIENT_EVIDENCE` and `OUT_OF_VERTICAL` are
  discards with reasons, not ranking positions; and each tile carries its own
  `r_layer`, because five tiles arguing from one shared trace is one argument
  wearing five hats.
- **(measured on Logix) / RC6, logged in D1** — raw catalogue codes in prose
  fields — measured: `[L3-DB-MLFLOW]`, `[L3-SF-DC-CORE]` and five more render
  inside Logix `l3_area` and `l4_feature` strings ("[L3-DB-MLFLOW] MLflow
  (Databricks-managed)"), where Baxter's `l3_area` is the name a client would
  say ("MuleSoft") — the rule: `platform` and `l3_area` carry sayable names;
  codes live in `catalogue_path`, which the renderer resolves to labels.
- **MEM-0093 / CG-27 + CG-29** — yesterday's content pays today's gate debt,
  and one thread wears five sections — measured 2026-08-19 on the Baxter
  re-promote: a two-field engine re-score returned 15 CG-27 refusals on this
  page plus one word-for-word `narrative_thread` on 4 of 5 platform sections
  — the rule: every section's thread says what THAT section adds; spell out
  abbreviations in prose but never inside `alignment_quote` or
  `catalogue_path` (verbatim spans, exempt via shared EXCERPT_FIELDS,
  REF-0036); when resubmitting one section, budget for the whole page's
  accumulated gates.
- **MEM-0049 / WRITE_PATH_WITH_NO_READ_PATH** — an empty input array read as
  an empty world — measured corpus-wide 2026-08-09: `platform_fits_raw` (with
  three sibling bundle tables) holds 0 rows for every run because nothing
  ever writes it, so a producer handed an empty `fits` array cannot tell "the
  package carried none" from "nothing ever parsed one" — the rule: an empty
  engine tile set or an empty per-cell platform vocabulary is a CATALOGUE or
  ingest LOAD DEFECT to report, never licence to invent candidates or
  figures; an area the analyst promoted and the engine did not rank gets a
  tile with `fit_score: null` and the reason.

### Exclusion set

`r_layer` reaches no audience — `NEVER_SERVED_KEYS` strips it at any depth for
every audience; write it anyway (AG-01 blocks without it) and mark it anyway
(invariant 5: marking is mandatory, the strip is the backstop — `internal_only`
was `[]` on 34 of 34 sections of both clients when MEM-0045 was raised).
`platforms[*].zennify_pathway` is the page's own commercial field: the third
pathway sentence (the offering) goes there and NOWHERE in the client-facing
two; the producer marks the path in `internal_only` (Baxter does) and
`CUSTOMER_ALWAYS` in `apps/api/dma_api/redaction.py` strips it for the
customer whatever the payload said. The excluded key classes drop from the
customer body at any depth: probe-ladder keys (`sources_searched`,
`queries_run`, `searched_on` — measured live on Logix: this section's
`empty_state` carries `searched_on` and a four-rung `sources_searched`
ladder), method keys (`tier`, `ers`, `recency_band`, `discovered_by`,
`provenance`, `link_basis`) and cap keys (`cap_level`, `ceiling`,
`uncertainty_band`, `urf_modifiers`). `empty_state` serves only `{reason,
closure_condition, closure, kind}` — a producer's real reason renders, a
probe never does (owner adjudication 2026-08-14). Contact keys (`email`,
`linkedin_url`, `phone`) strip by KEY at any depth, so a named person inside a
peer row or readiness note loses the route, never the name. No colour, no hex,
no M-code in any prose (invariants 6–7); an invented key drops at serve with
the drop counted in the receipt (D1, fail-closed).

### Enrichment pathways

Connector pathways (`02-inputs/enrichment_sources.json` facet
`platform_readiness` — its serving surface IS this section — plus the pack's
Information sources table): `first_party` (T1-T2, wired) serves the entity's
own careers pages, filings and announced programmes through
`register_evidence`; `clay` Open Jobs (T2-T3, wired, producer-session only)
is the cheapest capability signal — the posting is first-party, the
aggregator is not, and `02-inputs/clay_taxonomy.json` maps it to "P1
readiness" by name; `clay` peer platform deployments (T1 per established
deployment, facet `peer_scores`) serve `peer_deployments`/`peer_coverage`
under AG-04 — one row per peer, unknowns as `deployed: null`, `source_url`
and `as_of` on every `deployed: true` row; the register `estate_reach` reads
is facet `techstack`'s — `explorium` ingest scan (T1, wired, not live) and
`clay` Tech Stack (T1, wired): a machine technographic scan is T1, never T4;
filing it at T4 caps the capability at L2.5. `harmonic` (T3) is declared,
not wired — listing it grants nothing. No connector serves the fit figure:
`get_platform_fit` answers it and no pathway restates it (CG-31).

Web-search pathways (the dma-research discipline: five signal facets, proxy
escalation before any absence, this surface's gaps):

- `"[peer] [SI partner] case study [platform area]"` — the pack's richest
  peer route. Registers as vendor collateral: T5, ceiling L2, corroboration
  required (W6), whatever tier you type; on the peer row it travels as
  `source_url` + `as_of` with the basis quoting the verbatim span.
- `"[peer] selects OR implements OR migrates [vendor] 2019..2026"` — the
  peer's own newsroom is official disclosure, T2; a search that establishes
  nothing becomes the `deployed: null` row's basis — a negative search is a
  ladder rung, never an evidence row.
- `"[entity] [platform area] engineer OR administrator job posting"` — a
  T2-T3 demand signal for an ABSENT layer (STEP 3's priority raise);
  register the posting with a verbatim 50–500 char span before the story
  cites it.
- `"[entity] [platform area] RFP OR board commitment OR strategic plan"` —
  T2 in the entity's own words; the other STEP 3 demand ground.
- `"[entity] [platform] implementation delay OR failure OR criticism"` —
  the contradictory facet, R-Layer step B's falsifier; registers only with
  a resolvable span, and a refused fetch is a rung naming its status code,
  never a clean record.

Gap-to-pathway: this section emits `empty_required` on `platforms` and
`discarded` (two required lists; no must-present member and no conditional
lives here). An empty engine tile set is a CATALOGUE or ingest LOAD DEFECT
to report (MEM-0049), never a gap a search closes; per-tile holes — an
unestablished peer row, a missing demand signal — close through the routes
above; the fit figure closes only through `get_platform_fit`.

---

## DD-11 · Platform tile expansion

Inline expansion from a platform fit tile (component ClientPlatform; the
Drilldown atlas's inline shell). It renders from the payload the tile
already holds — the gap rows, `estate_reach`, `peer_deployments`, the
pathway prose — and fetches nothing, so everything the panel can ever show
is written under P1's contract. The Spec gives it no separate prompt; this
entry pins what the expansion reads.

### Baxter positive pattern

The pathway prose connects the peer's route to THIS client's cells, and the
commercial third sentence lives elsewhere (`zennify_pathway`, marked):

> "BCU already holds the Salesforce side of that route across nine detected
> products; what is missing is the connectivity layer between them and the
> Symitar core, which is why Technology Roadmap & Investment Planning and EA
> Framework & Governance sit in the Building band while the applications
> above them are in place." (`integration_pathway`, rank-1 tile)

The peer synthesis scopes the share to the breakdown:

> "One of five peers is established on this platform area and four are not,
> so the share is stated as one established case rather than a trend."
> (`peer_synthesis`, rank-1 tile)

A gap row with no peer figure says why, on the row:

> "The locked peer set is benchmarked at category grain, so no peer figure
> exists for this cell; the category comparison is stated on the workbook
> surface instead." (`gaps[0].peer_note`, with `peer_basis:
> "cannot_estimate"` and `peer_score: null` — the null carries its basis)

Shape notes, measured: this expansion is where MEM-0068's blanks rendered,
so the check is visual — open the expanded tile and read the gap table, the
reach counts and every peer row; a `deployed: null` row must read as a
searched absence, not a blank. Logix's five tiles carry no `estate_reach`,
no `peer_deployments` and no `integration_pathway` at all — under-filled
tiles, not a second legal shape.

### Anti-patterns

- **MEM-0068 (measured on this panel, badged under P1)** — 25 cited peer
  rows rendered zero times and 28 gap rows read as blanks; the panel's half
  of the rule: after promotion the producer opens the EXPANDED tile, because
  a tile face can look whole over an empty expansion.
- **MEM-0003 (badged under P1)** — five tiles promoted as one: the client
  clicked the other four expansions and found them empty; count the expanded
  tiles on the served page, not the tiles in the payload.
- **RC6 (measured on Logix, badged under P1)** — catalogue codes inside
  expansion strings ("[L3-DB-MLFLOW] MLflow (Databricks-managed)") spend the
  reader's attention on grammar; sayable names in `platform` and `l3_area`,
  codes in `catalogue_path`, which the renderer resolves.

### Exclusion set

The panel renders P1's payload, so P1's exclusion set governs whole:
`platforms[*].zennify_pathway` marked in `internal_only` (and stripped by
`CUSTOMER_ALWAYS` regardless), `r_layer` never served to any audience,
probe, method and cap key classes dropped from the customer body at any
depth. Nothing panel-specific exists to add — which is the point: a field
written for the expansion is still a P1 field and carries P1's marks.

### Enrichment pathways

The panel fetches nothing (Drilldown contracts: every panel renders from the
page response), so its pathways are P1's, scoped to what the expansion
shows: peer rows close through the peer routes (facet `peer_scores`, with
W6's T5 rule on vendor and SI collateral), reach counts through the register
(facet `techstack`, T1 and never T4), demand signals through `clay` Open
Jobs (T2-T3). It emits no `list_enrichment_gaps` kinds of its own — the
worklist is computed per section field — so a hole here surfaces as
`platform_story`'s `empty_required` or as a held field whose reason is the
content.

---

## DD-13 · Readiness gate expansion

Inline expansion from a prerequisite gate row (component ClientPlatform; the
Spec's P1 drilldown — "Readiness · click a row to drill in", rows expanding
to BACKING SUBCAPS with their scores). It renders the readiness objects P1
and P2 already carry; no separate prompt, no separate fetch.

### Baxter positive pattern

The verdict is a measurement with its arithmetic on the row:

> "READY WITH CONDITIONS" (`readiness.verdict`, rank-1 tile) — backed by
> `prerequisite_cells: [{cell: "P4C3", current: 2.19, minimum: 2.0,
> verdict: "MET"}]`, the same cell and threshold REC-001's
> `validation_gate` states, so the gate row and the modal cannot disagree.

What is already true opens the panel, cited:

> "The category threshold this recommendation gates on, Technology
> Architecture & Integration at 2.0, is met at 2.19. Senior platform
> engineering hiring is live, which is the capacity signal a first-phase
> integration build needs." (`readiness.already_true`, excerpted)

What must be true first is a condition with its reason:

> "The core contract position has to be confirmed before the connector
> scope is fixed, because the packaged connector is a vendor artefact and
> its coverage of BCU's own core configuration is not established in this
> run." (`readiness.must_be_true_first`, excerpted)

### Anti-patterns

- **9-antipatterns §7 (measured on Logix, badged under P2)** — prerequisites
  written as plain strings rendered "no readiness gate applies" over nine
  real gates; the panel reads two object shapes — `{cell, minimum, current,
  verdict}` and `{condition, note, basis}` — and readiness reasoning lives
  ONLY in the condition's `note`.
- **one gate, two spellings (measured on the two payloads, badged under
  P2)** — Baxter serves `{threshold, current_value, backing_cells[].score}`,
  Logix `{condition, backing_cells[].served}` with no current value at the
  gate level; emit the reference shape, because the panel reads one.
- **(measured on Logix, badged under P1)** — a gate expansion with no
  per-tile `r_layer` behind it is one argument wearing five hats; each tile
  carries its own trace, and the gate's reasoning resolves to it.

### Exclusion set

The parent sections' sets govern (P1's and P2's); nothing panel-specific
serves or strips. The condition `note` is client-facing prose: no cap
vocabulary, no M-codes, and the threshold speaks in scores ("P4C3 >= 2.0 —
met at 2.19"), which is the panel's whole vocabulary.

### Enrichment pathways

A gate's verdict is pack arithmetic — no connector and no search moves
`current` against `minimum`. The enrichable input is the condition's
evidence: hiring capacity (facet `platform_readiness`: `clay` Open Jobs,
T2-T3 — Baxter's `already_true` closes on a live-hiring signal) and named
ownership (facet `leadership`: `first_party` proxy statements and
leadership pages, T1-T2; `clay` contact routes, T2-T3, with the
title-must-match identity rule). Query pattern: `"[entity] [platform]
engineer OR architect hiring"` → T2-T3, registered with a verbatim 50–500
char span before the note cites it; a condition no search can establish
stays `basis: "Not established"` with the ladder recorded — a negative
search is a rung, never an evidence row. Emits no `list_enrichment_gaps`
kinds of its own; holes surface under `platform_story` and
`recommendations`.

---

## P2 · Recommendations

### Baxter positive pattern

A root cause explains why the gap EXISTS, cited, and is not a restatement of
the score:

> "One low-code tool carries the point-to-point connections between the core,
> origination, voice and digital-banking platforms, and it is the only
> integration product in a scan of more than two hundred technologies. The
> packaged connector for this exact core sits on the vendor marketplace
> undeployed, and end-of-life platforms add coupling." (`root_cause`,
> REC-001)

Cost of inaction is grounded in a dated trigger, not invented urgency:

> "The merger announced on 1 June 2026 converts a second institution's
> systems onto the same bespoke links, and Technology Architecture &
> Integration absorbs that work. Each converted system adds connections
> nobody reuses, and the automation ceiling the assessment's cap rules tie to
> this score stays where it is." (`cost_of_inaction`, REC-001)

A prerequisite condition reasons in its `note`, opening on what is already
true:

> `{"condition": "Architecture decision owner named for the platform",
> "basis": "Evidenced", "note": "Established: the chief technology officer's
> remit covers product lines, the technology team and the call centres, and a
> board Technology Committee stands behind it. This is a prerequisite rather
> than a formality because an application programming interface layer governs
> contracts between systems that today have none, and an ungoverned layer
> becomes a second point-to-point estate."}`

The validation gate is traceable to the cells that produce its verdict:

> `{"cell": "P4C3", "threshold": "P4C3 >= 2.0", "current_value": 2.19,
> "verdict": "MET", "backing_cells": [{"subcap_id": "P4C3.1.1", "name": "EA
> Framework & Governance", "score": 2.0}, …]}` — the drilldown renders those
> backing cells, so the verdict opens onto its arithmetic.

Shape notes, measured: 8 recommendations, `provenance` ANALYST on every row
and never blank; every `dma_impact` row carries a `target_basis` naming its
target a projection, so a projected 3.0 can never read as a measurement;
`kpi_triple.baseline` is a figure from the pack with `baseline_as_of:
"2026-03"`; Logix carries the other honest KPI shape — "Not established as at
18 August 2026" with the reason — and the other honest cost shape: REC-1 and
REC-5 open "No dated trigger established" and then say what the cost actually
is. Both are better answers than invented urgency, and an AE can use them.

### Anti-patterns

- **(no MEM) / S32_rec_detail** — a derived recommendation laundered as
  analyst judgement — measured in the pack's history: 32 clients shipped
  synthetic recs presented as analyst output — the rule: `provenance` is
  `ANALYST │ DERIVED`, required, never blank, and DERIVED means composed from
  the pack by rule; the distinction is the reader's basis for trusting the
  rest, and it renders on the internal view even though the customer
  projection strips the key.
- **(no MEM) / 9-antipatterns §7, measured on Logix** — prerequisites written
  in a shape the panel cannot read — measured: every Logix
  `prerequisites[]` entry is a plain string ("An inventory of models actually
  in production, which public evidence cannot establish"; "P4C2.1.1 >= 2.5,
  which the run serves at 3.0") while the readiness panel reads two object
  shapes; §7's measured cost of exactly this: `prerequisites:
  ["P4C2.1.1 >= 2.5"]` rendered "no readiness gate applies" over nine real
  gates — the rule: a cell threshold is `{cell, minimum, current, verdict}`,
  a condition is `{condition, note, basis}`, and readiness reasoning lives
  ONLY in the condition's `note` (40–80 words, what-is-true → what-must-be
  → sequencing basis); reasoning written anywhere else renders nowhere.
- **(measured on the two payloads) / 9-antipatterns §7** — one gate, two
  spellings — measured: Baxter's `validation_gate` serves `{threshold,
  current_value, backing_cells[].score}`; Logix's serves `{condition,
  backing_cells[].served}` with no current value at the gate level — two
  promoted clients, two vocabularies for one drilldown, and a renderer reads
  one — the rule: emit the shape the reference client serves (`threshold`,
  `current_value`, `backing_cells[].score`); a second legal shape someone
  introduces must be said out loud, because someone has to teach the reader
  about it.
- **(no MEM) / pack-measured, reconciled by `scripts/check_consistency.py`** —
  a sequence that contradicts its own roadmap — measured: 17 clients shipped
  `sequencing_reason` disagreeing with their own phases — the rule: the
  sequencing reason agrees with the roadmap AND the stair-step, and the
  cross-page check runs BEFORE submit, because no per-page gate can see it.
- **(measured on Baxter) / invariant 8** — a citation list that repeats an id
  — measured: REC-001's `evidence_ids` lists `E-BCU-065-R2` twice, and
  `grounded_on` is the LENGTH of the citation list, so a duplicate inflates
  the count the reader trusts — the rule: each evidence id appears once per
  list; dedupe before emitting.
- **(no MEM) / AG-03 + CG-13, recurred as MEM-0001** — a field that validates
  and then vanishes — measured: 18 item-grain contract keys across 9 serving
  tables (two of them on this page's family) were validated at submit and
  dropped at promotion because no column existed — the rule: per-item detail
  (`root_cause`, `cost_of_inaction`, `kpi_triple`, `validation_gate`) is
  render-bound, so after promotion read the served drilldown and confirm the
  detail the panel promises actually arrived.

### Exclusion set

The customer-audience row is exactly the allowlist's: `{rec_id, title,
l3_area, l4_feature, phase, dma_impact, root_cause, evidence_ids,
cost_of_inaction, prerequisites, dependencies, sequencing_reason,
effort_band, kpi_triple, validation_gate, claim_label}` plus the envelope —
note `provenance` is NOT in it: it is an excluded method-vocabulary class, so
it serves the internal view only, and it is still required at submit.
`r_layer` per item never serves to anyone; write it for AG-01. Cap vocabulary
stays out of `root_cause` and `cost_of_inaction` prose — a ceiling may be
described in plain words (Baxter does), but `cap_level`, `ceiling`,
`uncertainty_band`, `urf_modifiers` keys and M-codes (`M1`–`M5`) never reach
the customer body. `empty_state` serves `{reason, closure_condition, closure,
kind}` only; searches go in `sources_searched` knowing they drop at the
customer boundary.

### Enrichment pathways

Connector pathways: no facet in `02-inputs/enrichment_sources.json` serves
this section directly — the rows are the analyst's own, from
`recommendations_detail.json` and the workbook (the pack's Information
sources table), never enriched into existence. The inputs the contract makes
the producer ground travel facet `why_now`'s routes: `first_party` press
releases and filings (T1, wired) for the dated event itself; `clay` Recent
News (T3, wired), Latest Funding (T1-T2 when a filing is behind it —
otherwise an inference, the tier follows the source) and Open Jobs (T2-T3);
`quartr` (T1-T2) and `moodys` (T2-T3) are declared, not wired — listing
grants nothing. `kpi_triple.baseline` is a pack figure with an `as_of`; a
connector value with no traceable source is an inference and cannot be one.

Web-search pathways (each closing a named contract requirement):

- `"[entity] [regulator] deadline OR effective date 2025..2027"` — a dated
  regulator milestone, T1 from the regulator's own page; register the order
  or rule with a verbatim 50–500 char span before `cost_of_inaction` cites
  it.
- `"[entity] core OR platform contract renewal OR expiry"` — T2 from the
  entity's own disclosure, T3 from trade press; a migration date already in
  evidence grounds the horizon.
- `"[peer] [platform area] implementation results 2023..2026"` — a peer
  trajectory; the peer's own newsroom is T2, vendor or SI collateral is T5
  with corroboration required (W6).
- `"[entity] board OR strategic plan commitment [capability]"` — T2; a
  stated board commitment is one of the contract's five grounding classes.
- When every route misses, "No dated trigger established" IS the content
  (Logix REC-1 and REC-5 are the exemplar); the misses are ladder rungs,
  recorded, never evidence rows — an absence registers as INFERENCE with its
  ladder, never as a FACT about urgency (W6).

Gap-to-pathway: this section emits `empty_required` on `recommendations`
only (one required list; no must-present member, no conditional). Per-item
holes — a null KPI baseline, an ungrounded cost — never reach the worklist:
they are held fields whose stated reason is the content, and the routes
above are how the reason gets to say something dated.

---

## DD-4 · Recommendation

Modal from a recommendation row (component RecommendationModal) — the
card-to-detail drill, with DMA impact, Root cause & evidence and Sequencing
tabs plus the dependency map. It renders the P2 row whole; the Spec gives it
its own prompt, and S32_rec_detail is its gate.

### Baxter positive pattern

The sequencing tab's reason is the dependency that fixes the position:

> "Phase one because nothing else in the plan starts cleanly without it:
> the member-data layer, the onboarding flow and the orchestration work all
> name it as their own predecessor." (`sequencing_reason`, REC-001)

The KPI baseline is a pack figure with its date:

> "0 of more than 200 technologies scanned" (`kpi_triple.baseline`,
> REC-001, with `baseline_as_of: "2026-03"`)

An impact target names itself a projection on the row the tab renders:

> "Projection: the assessment's stated uplift for Technology Architecture &
> Integration at its low end, applied to this cell — a projection, not a
> measurement" (`dma_impact[0].target_basis`, REC-001)

Shape notes, measured: `dependencies: []` on REC-001 is a true root, not an
omission — the dependency map draws from it; every `dma_impact` row's
`current` equals the heatmap's serve within 0.05, which is what lets the
impact tab's arithmetic be checked from the modal itself.

### Anti-patterns

- **MEM-0001 / AG-03 + CG-13 (badged under P2)** — the modal is where a
  validated-then-dropped field becomes visible: after promotion open the
  modal and confirm `root_cause`, `cost_of_inaction`, `kpi_triple` and
  `validation_gate` actually arrived; the panel promising detail it does
  not carry is the measured shape of this class.
- **invariant 8 (measured on REC-001, badged under P2)** — a duplicated
  evidence id inflates `grounded_on`, and the modal prints that count;
  each id once per list, deduped before emitting.
- **S32_rec_detail** — a DERIVED row presented as analyst judgement in the
  modal's provenance line; the line renders on the internal view only and
  is still required at submit.

### Exclusion set

P2's customer-audience allowlist is the modal's: `{rec_id, title, l3_area,
l4_feature, phase, dma_impact, root_cause, evidence_ids, cost_of_inaction,
prerequisites, dependencies, sequencing_reason, effort_band, kpi_triple,
validation_gate, claim_label}` plus the envelope; `provenance` is the
excluded method class, internal view only; no cap vocabulary or M-codes in
the two prose tabs.

### Enrichment pathways

The modal fetches nothing; P2's routes close its tabs — the dated trigger
behind `cost_of_inaction` (facet `why_now`: `first_party` T1; `clay` Recent
News T3, Latest Funding T1-T2 when a filing is behind it), the peer
trajectory (peer newsroom T2; vendor or SI collateral T5 with corroboration
required, W6). A KPI baseline never comes from a search — it exists in the
pack with an `as_of` or the triple says so in plain words. Emits no
`list_enrichment_gaps` kinds of its own; holes surface as
`recommendations`' `empty_required` or as held fields whose reason renders.

---

## P2b · Conversation starters

### Baxter positive pattern

The opener names what exists before what is missing, and the E-IDs stay out of
the spoken text:

> "You have nine products from one vendor in production, five AI systems live
> and a core relationship a quarter of a century old. What we could not find
> anywhere in a scan of your estate is an integration platform, so those
> systems are wired to each other one connection at a time." (rank 1,
> `opens_on: gap`)

> "You announced the merger in June, and the design decisions for systems
> integration get made in the next couple of quarters rather than at
> conversion. That is the window that matters here." (rank 2, `opens_on:
> timing` — the window and what closes it, dated by the client's own event)

The follow-up is a discovery question, not a diagnostic:

> "What does your conversion plan assume about how member data moves between
> the two cores?" (`followup_question`, rank 2)

Shape notes, measured: 5 starters, 5 DISTINCT opening shapes (gap, timing,
their_words, contradiction, system) — at most one per move; every
`their_system_reference` names something from the register (Azure Logic Apps,
the announced merger, the cloud-migrated Symitar core, Genesys/Glia, Tealium
AudienceStream); `peer_reference` is OMITTED on all five rather than filled
with "peers are investing…" filler; the rank-3 their-words opener quotes the
chief technology officer verbatim and dated, and agrees with the quote before
adding to it. Logix's promoted rank-1 and rank-5 are the corrected forms of
9-antipatterns §2's refused openers, worth reading side by side.

### Anti-patterns

- **MEM-0060 / CG-17** — a required list satisfied by `[]` writes no rows and
  the surface vanishes — measured 2026-08-14: `platform.starters.starters`
  on the second promoted client passed every gate as an empty list, promotion
  wrote zero rows, and the page served no starters and no `empty_state`;
  owner report: "Conversation starters disappeared" — the rule: an empty list
  is a claim ("there are none") and must be made deliberately — send the
  items or declare the section's `empty_state`; `may_be_empty` belongs to
  `techstack.dropped` alone. **PERMANENT — never retire** (raised_by_kind
  USER); test: `apps/mcp/tests/test_required_list_not_silently_empty.py`.
- **(no MEM) / AG-12 + 9-antipatterns §2** — an opener that reads as an
  accusation — measured on Logix's earlier round, refused and rewritten:
  "Two things you have told the market do not quite line up", "What it
  cannot do is answer a question", "You do not measure contact-centre
  deflection" — the rule: state the same fact from the value end ("There is
  money sitting in the gap between two things you have already said publicly,
  and I think it is yours to take"); the follow-up question is part of the
  starter, and a consultative opening followed by "why do you not track
  that?" is still an accusation.
- **(no MEM) / S31_platform_distinctiveness** — one opening shape stamped
  five times — measured: 685 of 685 starters across the corpus used one
  shape — the rule: vary the move, at most one starter per opening shape; a
  set that all opens the same way is a template, not a set.
- **(no MEM) / pack-measured quote hygiene** — a garbled quote repaired into
  fiction — measured: 76 starters across 39 clients shipped truncated or
  mid-word quotes — the rule: quoted material is a clean, complete, verbatim
  sentence from a resolvable source; if the mined excerpt is broken, drop to
  a non-quoting shape — never invent the missing half.
- **MEM-0086 / CITATION_NAMES_THE_CONTAINER_NOT_THE_SPAN** — a peer figure
  cited to a page that does not carry it — measured on Logix: Patelco
  $9.62bn, First Technology $28.58bn and Golden 1's 9.94% net worth ratio
  cited to E-CC-296/297, whose excerpts are the NCUA download-table row and
  a file-format sentence; a regex for every named peer and figure over all
  37 cited rows matched 0 — the rule: the cited span carries the figure; a
  derivation trail is a disclosure, not a citation; a `peer_reference` is a
  NAMED institution with a DATED action or the field is omitted.
- **MEM-0085 / ET-09 (CHECKER_FALSE_POSITIVE)** — the run's own recorded
  cohort refused as contamination — measured on Logix: `peer_reference`
  naming Patelco and Golden 1 in full legal form drew 2 of 4 blocking
  reasons while the same run's heatmap named the same five peers in short
  form and passed — the rule: this is a recorded checker defect, not a fact
  about your payload; when ET-09 refuses the run's own named cohort, report
  the recurrence against MEM-0085 rather than silently un-naming the peer or
  shopping for a spelling that slips past.
- **MEM-0081 / DEFAULT_DENY_DELEGATED_TO_THE_PRODUCER** — an all-internal
  section that empties in place instead of being withheld whole — measured:
  Logix marks `starters.starters` internal, and `redact_section(...,
  audience='customer')` serves `{e_ids, produced_at, internal_only,
  producer_version}` — a husk with no content and no reason — while Baxter
  marks nothing and its starters serve to the customer body whole; two
  promoted clients answer "who may read a starter" two ways — the rule: P2b
  is AE-facing by its own contract definition ("openers an AE can say out
  loud"), so mark `starters.starters` and declare the `empty_state` that
  explains the customer view; the real fix — `('platform','starters')` in
  `CUSTOMER_WITHHELD` — is the open finding's, not yours to improvise.

### Exclusion set

The section's content is AE preparation by contract definition: until
`CUSTOMER_WITHHELD` carries `('platform','starters')` (MEM-0081, open), the
producer marks `starters.starters` and `r_layer` in `internal_only` and
accepts that the customer body serves the declared `empty_state` reason in
their place. `provenance` (`TEMPLATE_FILL │ ANALYST`) is required and renders
internal-only — it is an excluded method class at the customer boundary.
`r_layer` never serves to any audience. The customer-visible item row, where
starters serve at all, is `{rank, text, opens_on, named_gap_subcap_id,
peer_reference, their_system_reference, followup_question, e_ids}` —
`opens_on` is a matched vocabulary (lower-case, exact spelling; capitalising
it drops the row out of its filter, AG-05). Probe ladders stay in
`sources_searched`/`searched_on` (Logix's starters `empty_state` carries
both) and drop at the customer boundary; the `reason` is what the customer
reads, so write it as real information, not workflow status.

### Enrichment pathways

Connector pathways, one per opening shape's input: `their_system_reference`
reads the run's own register — facet `techstack` (`explorium` scan T1,
wired, not live; `clay` Tech Stack T1, wired — a machine technographic scan
is T1, never T4; `first_party` platform statements T1-T2). The their-words
opener quotes O12 — facet `thought_leadership` (`clay` Find Thought
Leadership T2-T3 — T2 for a first-party publication or named conference, T3
for trade press, per `02-inputs/clay_taxonomy.json`; `first_party` newsroom
and trade-press rungs T1-T2; `quartr` transcripts T1-T2, declared, not
wired). `peer_reference` — facet `peer_scores`, `clay` peer deployments (T1
per established deployment): a NAMED institution with a DATED action or the
field is omitted (MEM-0086's rule).

Web-search pathways:

- `"[executive] [entity] keynote OR interview OR podcast 2024..2026"` — the
  their-words opener's source; T2 for a first-party publication or named
  conference, T3 for trade press; the registered span is the verbatim
  sentence itself (50–500 chars), and a broken excerpt drops the shape —
  never repair a quote into fiction.
- `"[peer] [action] announcement [year]"` — dates the peer opener; T2 from
  the peer's own newsroom, T3 trade press; cite the span that carries the
  figure, never the container (MEM-0086).
- `"[entity] [system] migration OR rollout OR go-live"` — grounds the
  system opener in the register's own facts at T1-T2; a vendor release
  about the entity is T5 and requires corroboration (W6).
- The contradiction opener adds no search class of its own — both facts
  must already be registered evidence of THIS run, or the opener cannot
  cite and is replaced with a different shape (the prompt's REJECT); the
  searches that failed a shape are ladder rungs, never evidence rows.

Gap-to-pathway: this section emits `empty_required` on `starters` only —
and MEM-0060 is the reason the kind matters: `[]` passes every gate and the
surface vanishes, so the pathway answer is items or a declared
`empty_state`, decided deliberately, never silence.

---

## P3 · Transformation roadmap

### Baxter positive pattern

A rationale argues the dependency, not the title:

> "This phase cannot precede the backbone: unifying member data over
> point-to-point links would move the fragmentation rather than remove it.
> Once the member layer exists, service consolidation and the origination
> flow both have one record to work from, and governance extends the
> analytics platform already standing." (PH-2 `rationale`)

The thread says what the section adds, written last, from what was produced:

> "Three phases sequence the eight recommendations by prerequisite: backbone
> and statutory analytics in the next two quarters, the member-data layer
> and console this year, orchestration beyond. Order is the content here —
> no phase precedes what it depends on, and each rationale names the gate
> that fixes its position." (`narrative_thread`)

Shape notes, measured: 3 phases, `sequencing_basis: "prerequisites"`;
`depends_on` chains PH-1 ← PH-2 ← PH-3 acyclically; every `rec_ids` entry
resolves to one of the 8 recommendations THIS payload describes; `horizon`
uses the pinned vocabulary exactly (`next two quarters │ this year │
beyond`); `capabilities` carry category NAMES the card can render. Logix adds
the honest discovery shape: a PH-0 with `rec_ids: []` whose rationale states
which three unresolved dependencies it exists to resolve — an unordered truth
stated rather than an order invented to look decisive.

### Anti-patterns

- **MEM-0001 / CG-13 (RECURRED)** — a contract field with no column to be
  promoted into — measured: 18 item-grain keys across 9 serving tables,
  `platform_roadmap` twice among them, validated at submit and dropped at
  promotion, every gate green, surfaces empty under a real client's name —
  the rule: the phase detail you write is only real once it survives
  promotion; read the served page after promoting, and treat a
  written-but-absent field as this recurred class, not as your own typo.
- **(no MEM) / pack-measured** — a fixture rendered under a real client's
  name — measured: the roadmap rationale and the starters rendered PROTOTYPE
  prose naming Synovus, BMO, Truist and "1,800 users" because the promoted
  fields were never read; the fields are read now — the rule: a thin
  `rationale` is visibly thin, which is the honest failure; write 30–60
  words on why THIS phase sits here and not earlier, and never a restatement
  of the phase's own title.
- **(no MEM) / pack-measured, `narrative_thread` null on all 34 sections of a
  real run** — a thread written by nobody — the rule: this section carries a
  thread like every other, written last, from what was actually produced;
  and never the same words as another section's (CG-29 — measured word for
  word on 4 of 5 platform sections in the MEM-0093 re-promote).
- **(no MEM) / referential integrity + acyclicity gates** — a phase citing a
  recommendation the payload does not describe — measured in the pack's
  history: 17 clients shipped phase order contradicting their own
  recommendation prerequisites — the rule: every `rec_id` resolves within
  THIS payload (a dead link in a document an AE reads aloud); assert the
  dependency graph acyclic before emitting; if prerequisites do not
  determine a sequence, emit the phases unordered with
  `sequencing_basis: undetermined` rather than inventing an order.
- **(measured on the two payloads) / one field, two vocabularies** —
  `phases[].capabilities` as names on Baxter ("Technology Architecture &
  Integration") and as subcap ids on Logix ("P4C2.5.1") — two promoted
  clients, one renderer — the rule: emit the shape the reference client
  serves (names); a code in a card chip spends the reader's attention on
  grammar they do not have.

### Exclusion set

`r_layer` never serves to any audience; write it because sequencing is a
causal claim and AG-01 blocks a causal claim with no recorded reasoning. The
customer-audience phase row is exactly `{phase_id, phase, horizon, rec_ids,
capabilities, depends_on, rationale}` plus `sequencing_basis` and the
envelope — `provenance` on a phase (Logix carries one per phase) is an
excluded method class and serves internal-only. `horizon` is a matched
vocabulary: `next two quarters │ this year │ beyond`, exact spelling,
lower-case — a capitalised value silently drops the row out of its filter.
Metrics quoted in a rationale come from THIS run and resolve to their named
cell; no M-code or cap vocabulary in phase prose. `empty_state` serves
`{reason, closure_condition, closure, kind}` only.

### Enrichment pathways

Connector pathways: the phases come from `recommendations_detail.json` plus
the assessment report, and any metric quoted comes from THIS run's workbook
(the pack's Information sources table) — no facet in
`02-inputs/enrichment_sources.json` serves this section directly. The one
enrichable input is the timing constraint sequencing carries: an integration
in flight or a migration date already in evidence, which travel `clay`
Recent News (T3 — recorded against O3 and C5 in
`02-inputs/clay_taxonomy.json`, reaching this page through the acquisitions
and why-now surfaces) and `first_party` disclosures (T1-T2).

Web-search pathways (searches date constraints; they never invent an order):

- `"[entity] conversion OR cutover timetable [year]"` — dates a phase
  boundary; T2 from the entity's own disclosure; the intention-vs-completion
  probe applies, because a vendor release describing an intention fixes no
  date.
- `"[entity] [vendor] migration completion OR go-live"` — T2-T3; a
  mid-migration platform is a timing constraint on everything downstream of
  it, carried into the phase whose rationale names it.
- `"[regulator] [rule] effective date"` — T1; fixes a statutory phase's
  horizon (Baxter's statutory-analytics phase turns on one).

Every result registers with a verbatim 50–500 char span before a rationale
quotes it; a search that dates nothing is a ladder rung, never an evidence
row. The order itself never comes from search — prerequisites determine it,
or `sequencing_basis: undetermined` is emitted with the phases unordered.

Gap-to-pathway: this section emits `empty_required` on `phases` and on
`sequencing_basis` (no must-present member, no conditional). Neither closes
by searching: `phases` closes from the recommendation set this payload
already describes, and `sequencing_basis` closes by saying which basis
ordered them — including the honest `undetermined`.

---

## P4 · Stair-step curve

### Baxter positive pattern

A step's unlock is a client outcome, not a capability name:

> "A new system, or a whole merged institution, connects through interfaces
> that already exist, so integration stops being the item that sets every
> project's start date." (step 2 `unlocks`)

The entry condition is a threshold with its served value, matching the
recommendation's gate:

> "Technology Architecture & Integration >= 2.5 — not met at 2.19" (step 3
> `entry_condition` — the same cell and threshold REC-003's
> `validation_gate` states, so ladder and panel cannot disagree)

Blocking findings are plain ids that resolve into the pack:

> `"blocking_findings": ["F-1", "F-2"]` (step 3 — ids, not prose, not
> serialisations; the chip opens the finding and its citations)

Shape notes, measured: theme "Data foundation" — a scoped curve, not a
whole-assessment ladder; 4 steps; `current_position: true` on exactly one
step, and its entry condition states "met at 1.95" so the position is a
measurement; every step above the position carries at least one blocking
finding and the step below carries none; `covered_subcap_ids` all belong to
the theme's categories (P4C1/P4C2/P4C3); `effort_band` S/L/L/M is consistent
with the platform page's effort profile. One measured gap to not copy: the
pack's ladder shape is `{from_level, to_level, steps[]}` — Logix carries
`from_level`/`to_level` and Baxter's ladder is `{theme, steps}` only, so the
reference client under-fills the contract here; emit both levels.

### Anti-patterns

- **MEM-0064 / CG-21** — a payload leaf carrying a JSON-encoded string
  renders as literal JSON — measured 2026-08-14: `ladder.steps[*]
  .blocking_findings` carried values like `'{"f_id": "F-1", "e_ids":
  ["E-CC-139"]}'` rendered straight into chips at
  `pages-live-client.jsx:1972`, 5 leaves per client on BOTH promoted clients
  — including the gold-standard reference, which had never been checked —
  the rule: a payload leaf is the value, not a serialisation of it; a
  blocking finding is an id (`"F-2"`) that resolves to a finding the pack
  serves; CG-21 refuses any string leaf that parses as a JSON object or
  array. **PERMANENT — never retire** (raised_by_kind USER); test:
  `apps/mcp/tests/test_serialised_leaves.py`.
- **(no MEM) / S33_pack_surface_completeness** — the surface simply absent —
  measured: the stair-step was exported for no one across 138 clients until
  the exporter was fixed — the rule: an absent ladder renders a STATED
  empty state ("no ladder is derivable because …"), never "Couldn't load
  stairstep"; a blank card is a defect even when the absence is honest.
- **(no MEM) / the pack's generic-ladder probe** — a ladder that would look
  the same for any client — the rule, with its own test built in: if no step
  names a client-specific blocker, the curve is a template with a name on
  it; `blocking_findings` ⊂ the findings the pack actually serves (a blocker
  invented for the ladder is a fabrication), and a step above the client's
  position with no blockers is unexplained — find the blockers or drop the
  step.
- **(no MEM) / consistency block, pack-measured** — a ladder that disagrees
  with the page it sits on — the rule as blocking checks: `current_position`
  equals the served scores of `covered_subcap_ids` (the step the client
  stands on is a measurement, not a judgement); step order equals roadmap
  phase order equals the recommendations' `sequencing_reason`; `effort_band`
  is consistent with the platform page's effort profile; `entry_condition`
  matches the corresponding recommendation's `validation_gate` cell and
  threshold.

### Exclusion set

`r_layer` never serves to any audience; write it for the gates. The
customer-audience step row is exactly `{step_level, label,
covered_subcap_ids, current_position, blocking_findings, unlocks,
effort_band, entry_condition, e_ids}` inside `ladder` — nothing on this
surface is page-specifically stripped, so everything you write here is
client-facing: no M-codes, no cap or ceiling vocabulary in `label`, `unlocks`
or `entry_condition` prose (`cap_level`, `ceiling`, `uncertainty_band`,
`urf_modifiers` are excluded key classes; the ladder speaks in scores and
band words). `empty_state` serves `{reason, closure_condition, closure,
kind}`; the searches that established a non-derivable ladder go in
`sources_searched`, which drops at the customer boundary — the `reason` is
what the client reads.

### Enrichment pathways

Connector pathways: the ladder is pack arithmetic — workbook current scores
plus the roadmap (the pack's Information sources table) — and
`blocking_findings` ⊂ the findings the pack serves, so no connector and no
search may mint one (a blocker invented for the ladder is a fabrication). No
facet in `02-inputs/enrichment_sources.json` serves this section; what the
register contributes (theme scoping, effort consistency) arrives through the
techstack and platform surfaces, already registered at their own tiers.

Web-search pathways (bounded — searches inform the ladder's honesty; they
never populate its steps):

- `"[entity] [system] go-live OR completion [year]"` — T2; dates the work
  behind a step's `effort_band` so it stays consistent with the platform
  page's effort profile.
- `"[entity] [theme] failure OR outage OR criticism"` — the contradictory
  facet run against the theme's step claims; registers only with a
  resolvable verbatim span, and a refused fetch is a rung with its status
  code.
- `"[entity] [theme] program OR initiative announcement"` — T2-T3;
  corroborates the `unlocks` framing in client outcomes without entering
  the ladder — the steps stay derived from cells and findings.

A non-derivable ladder's empty state names what was searched
(`sources_searched`), and every miss is a rung, never an evidence row — a
negative search registers as the absence's ladder, not as a row (W6).

Gap-to-pathway: this section emits `empty_required` on `ladder` only. The
kind's honest closures are two: a ladder derived from the served scores and
the pack's findings, or a STATED empty state ("no ladder is derivable
because …") — S33 is the class where neither shipped, and no search closes
it because the absence was the exporter's, not the evidence's.
