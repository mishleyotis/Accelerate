# The DMA deliverable gold standard

**Read this, and open the reference package, BEFORE you author anything.** The gold
standard is not a description — it is the **Golden 1 Credit Union** package
(`DMA-2026-GOLDEN1-001`), named by the engagement owner as the best so far. Every
number below is what that package meets. A producer that authors first and discovers
the standard in QA has already failed the one-turn test; the point of this file is to
let you understand the deliverable before you start, and to give you a gate
(`engine/gold_standard.py`) you run on your OWN output before you return.

This file covers three deliverables: the **workbook**, the two **reports**, and the
six **app pages** (overview, heatmap, insights, platform, context, techstack — see
*App pages* below, added 2026-10-04 after the SWBC gold audit found the app pages had
no measurable gold at all: RC-01). Its path from the repository root is
`plugins/dma-insights/docs/GOLD-STANDARD.md`; inside the plugin,
`${CLAUDE_PLUGIN_ROOT}/docs/GOLD-STANDARD.md`. A bare `docs/` path from the repository
root is the read-only design-docs folder, and this file is not in it.

## The deliverable-first loop (do this in order, every time)

1. **Read the contract** — this file — and open the reference package's workbook and
   both reports. Know the shape you are producing before the first cell.
2. **Author to the contract**, mining the full evidence base (the workbook's
   `Evidence_Detail`/`Evidence_Master`, `Tech_Register`, `Entity_Timeline`,
   per-subcap findings), not a summary.
3. **Run the gate on your own output** — `python3 -m engine.gold_standard {workbook|report|package} <path>` —
   and do not return until it prints `PASS`. Mid-session, re-run it after any change
   that touches a score, a section, or a figure. The gate is your pre-flight.

## Workbook — the 43-sheet ASSESSMENT artefact (not the research workbook)

The gold-standard workbook is the **assessment** stage's output, not the research
engine's. It carries, at minimum:

- `Executive_Summary` — a dashboard: Institution, Sub-Vertical, Evidence Mode,
  **Overall Maturity with an M-band label** ("2.25 (M2)"), **Peer Median (est.)** with
  the locked peer set, **Gap to Peer**, **Subcaps Scored** ("561 evidenced of 690,
  81.3% coverage"), **Evidence Gaps (Unknown)**, per-pillar rows, and a one-line
  **Headline**.
- `P1..P4_Subcap_Scoring` — **every subcap carries a numeric score 1..5.** Never blank,
  never 0, never "N/A". `SubCap_Name` filled from the catalogue on every row.
- `Coverage` — **discloses the gaps**: `Category, Subcaps, Scored, Unknown_EvidenceGap,
  Coverage_Pct`. Scoring every cell and hiding which rest on evidence is not the
  standard; scoring every cell AND disclosing coverage is.
- `Pillar_Summary` / `Pillar_Rollup` / `Category_Rollup` — **weighted** rollups (read
  `Pillar_Weights`), an `OVERALL` row, `Gap_to_Peer`, `Maturity` (M-band).
- `Peer_Benchmarks` — one row per peer with an overall estimate and posture, each
  **labelled an estimate from public digital-maturity signals, not a formal DMA score**,
  with a locked peer set.
- `Firmographics` — `Field, Value, Unit, As at, Evidence`. A genuinely-absent field
  reads `ABSENT (see 1.2)` with a route, never blank. (That is the WORKBOOK's word. The
  app payload states the same absence as `quarantined: true` with a
  `quarantine_reason` naming the route, and renders it as a stated absence — one rule
  in two vocabularies; see *App pages → Held fields*. An earlier version of this line
  said "never quarantined", which contradicted the app contract.)
- `Focus_Areas` — client priorities with a **verbatim quote**, document, page, cells.
- `Issue_Register` — real matters with `Severity, Status, Capability impact`.
- `Solution_Catalogue`, `Cap_Triggers`, `Platform_Peer_Adoption`, `Maturity_Rubric`,
  `Capability_Definitions`, `Technographic_Scan`, `Enrichment_Needed`.
- **A 5-year financial trajectory** — the deepest fiscal series in the workbook must span
  **≥5 years** of real financial metrics (revenue, income, assets, loans, ROE…). Carry it
  in a `Financial_Trends` sheet (≥5 fiscal-year columns, ≥5 metric rows, a CAGR/growth
  column) or dispersed across the evidence/scoring sheets as the reference does — either
  satisfies the floor, but the depth is not optional.

Only a **source-link** column (`Source_URLs`) may be empty on a row with no located
source — the contract forbids a placeholder there and a URL cannot be invented.

## Reports — author INTO the branded template, follow it exactly

- **Every numbered section of the template** is reproduced (research: 1 Firmographics …
  8 Workbook References; assessment: 1 Executive Summary … 11 Workbook Traceability,
  plus the alignment appendix). Fill every `{{token}}`; leave none.
- **Branding via the template's header** (the reference uses `header1.xml`, not embedded
  fonts). Authoring a blank `Document()` throws the template away — do not.
- **Depth, scaled from the reference and enforced**: distinct evidence citations at the
  Golden 1 density — 115/690 subcaps for the assessment report, 47/690 for the research
  report, scaled to the run's selected subcaps (`gold_standard.depth_floors`,
  `reports.citation_floor`); words at the pinned Doc's own LENGTH floors (assessment
  8,400, research 3,050, scaled by pillars in scope) and never above what the reference
  itself meets. The old flat "≥60 citations" would have failed Golden 1's own research
  report (47); a floor the reference fails is not a standard. Cite the evidence base, do
  not summarise it. Both floors are checked by `reports.check`, `engine.gold_standard
  report` and `assemble verify` (the gold gate), and `tests/skills/research_engine/
  test_gold_reference.py` proves every floor is one the reference meets.
- **Financial trajectory**: render a **5-year+ financial series** in prose — ≥5 fiscal
  years, real financial metrics, and an explicit trend (CAGR / growth / year-over-year),
  reconciling to the workbook's `Financial_Trends`.
- **Assessment content contracts**: an **AI-and-data overlay in every pillar** (×4); a
  **rebuttal on every recommendation** (steelman the strongest counter, then adjudicate);
  pillar deep-dive headings carry **score vs peer median** ("2.40 vs 3.10").
- **Coverage disclosed** in prose (evidenced vs Unknown), matching the workbook.
- **Bands**: the four display bands only — Activating, Building, Competing, Differentiating.
  The numeric maturity **score** (1–5, e.g. "2.25") is a different axis and is expected; a fifth
  *band* word must never appear, and inventing one is the invariant 6 breach.
- **Reconcile**: every figure the report renders equals the workbook's stated grain
  within 0.01 on the overall.

## Templates are pinned, bound and enforced — before the process begins

- **Pinned**: the owner's two report Docs and the workbook template live in
  `plugins/dma-insights/references/templates/` — `client_profile_template.md`,
  `assessment_report_template.md`, `report_templates.json` (the section spec
  the engine writes to: blocks, feeds, control-block checks), `workbook_template.json`
  and `gold_reference.json` (the Golden 1 shape and depth measured, not recalled).
- **Bound**: `engine.cli start` binds every run to the pinned digest
  (`00_entity_profile/template_binding.json`, `Run_Metadata.template_binding`).
  `orient` withholds the first card until the binding exists; the report
  preconditions refuse without it; `engine.template report-drift` reports a Doc
  export that has moved away from the JSON.
- **Enforced**: `engine.narrative write` refuses a body that is not the Doc's
  (blocks, card shape, countable minimum data); `gold_standard` checks the
  rendered .docx by section number AND heading against the pin (GS-RPT-SECTIONS);
  `workbook.create` seeds every `SubCap_Name` from the catalogue and refuses an
  unnamed cell (GS-WB-NAMES). The session brief names the templates on every
  research and report session, so no agent starts from a remembered shape.
- **Evidence depth is gated per cell, not per category**: every askable volley
  has a logged search for the cell (`volleys_incomplete`, blocking), the
  primary diagnostic question is fired (`primary_unfired`, blocking), an
  empty cell closes only as a DECLARED absence through `engine.cli absence` —
  refused until an enrichment connector was asked (`absence_single_tool`,
  blocking) — and the flag has ONE writer, proven by a Provenance row
  (validator rule 8). Run-level density floors come from `gold_reference.json`
  (rows per subcap, evidenced share) and gate `assessment open`.
- **Mechanical, not advisory (2026-09-04)**: the `deny_artefact_writes`
  PreToolUse hook refuses any `.xlsx`/`.docx` written outside the engine and
  the retired writers (`populate_workbook.py`, `validate_workbook.py`,
  `assessment_runner.py`) refuse and name the engine; `engine.cli start`
  refuses on a stale marketplace install and on a zip whose manifest predates
  its pinned templates (`engine.template zip-guard`); `narrative.write` and
  `reports.render` run the stage preconditions on every call (`--force` is a
  `DRAFT_` no package accepts); the report agents, the scoring tier and the
  category researchers each get their own session brief naming the templates
  and the gold reference; the driver (`engine.pipeline`) dispatches every lane
  over a brief that carries the template paths. Nothing in this list depends
  on an agent choosing to read this document.

## No hedges

These read as "the work was not finished" and must never ship: "Not established this
run", "to be established at the surface-production stage", "no score yet", "queued for
enrichment", "TBD", "N/A" standing in for a value. If a thing is genuinely unknown, it
is an **Unknown evidence gap disclosed in Coverage** or an **ABSENT firmographic with a
route** — a stated, structured absence, never a hedge. On the app pages the structured
absence is an `empty_state` (reason, `sources_searched`, closure condition), a held
field with its `quarantine_reason`, or a null member with its own `<member>_basis`.

## The gate is the contract, executable

`engine/gold_standard.py` encodes every rule above for the workbook and the reports and
maps each to the goeasy finding it prevents
(`plugins/dma-insights/docs/goeasy-findings-register.md`). Run it on your own output.
Green is the definition of done. For the app pages the executable contract is CG-PAR
and Gate J, below.

## App pages

**Why this section exists (RC-01, RC-02, D-35 — SWBC gold audit, 2026-10-04).** For the
six app pages there was no gold a producer could fall short of: this file covered only
the workbook and the reports, the rulebook's "positive pattern" was prose, the key list
in `fixtures/reference_surface_keys.json` held names only, and the structural gate
(Gate J) compared top-level keys and ran nowhere a real run passed through. A promoted
run served ten firmographic fields with six held, one sentiment bar, and platform cards
without peer rows, and every check read that as parity.

**Where the gold is.** `fixtures/surface_gold.json` — shape only, cut by
`scripts/gen_surface_gold.py` from the staged pages of the three promoted gold runs:
Golden 1 (`40971653`), Baxter (`c1351d25`), Logix (`d7ed1d90`). It keeps keys, list
lengths and each row's null pattern; it keeps **no values and no names** (owner
decision, 2026-10-04). Each gold run records its sub-vertical (`runs.*.sub_vertical`);
all three are credit unions (CU). A run of another sub-vertical is held to them for
**structure only** — the sections and keys every gold run serves — and its own
must-present fields come from its rulebook, not from this fixture. The connector reads a byte-identical copy
(`apps/mcp/dma_mcp/surface_gold.json`); a test keeps them equal, and another keeps the
per-audience dispositions equal to what `apps/api/dma_api/redaction.py` does.

**How it is enforced.**

- **CG-PAR, at promote** — `promote_run` compares every staged page with the gold
  (`apps/mcp/dma_mcp/promote_checks.py`). A **structural** gap refuses — nothing is
  written; resubmit the page named, then promote again. Everything else comes back in
  the verdict as `promote_checks.parity.warnings`, and never refuses.
- **Gate J, before you submit** — the same rules from a repository checkout:
  `python3 scripts/gate_j_surface_parity.py --gold fixtures/surface_gold.json
  --target-dir <dir of six page JSON files> --sub-vertical <code> [--run-id <uuid>]`
  (or `--api URL --target SLUG`). Exit 1 means a structural gap; `(warning)` lines do
  not fail it.
- **CI** runs Gate J against the committed gold with a thin target (structural gaps
  refuse, counts warn), and asserts that each gold run meets the standard of the others.

**What refuses and what warns (owner decision B, 2026-10-04).** Values are never
compared: a lower score is an assessment result. So is a shorter list: how many tech
rows, cited ids or addressable cells a client has is what the assessment found, and a
gate that refused on it would teach producers to pad. Only structure refuses.

| Severity | Kind | Rule |
|---|---|---|
| **block** | `section_absent` / `section_empty` | a section today's contract **requires** and every reference gold run fills is missing, or served empty without an `empty_state` (an optional section — `value_chain`, `cohort_patterns` — warns) |
| **block** | `key_absent` / `key_empty` | a key every reference gold run fills is missing or empty, where today's contract **requires** it — or makes its absence conditional (`absence_is_correct_when`, e.g. `sentiment.gap_analysis`: "only one audience was established") and the section does not say the condition holds by naming the key in its `empty_state` |
| **block** | `item_key_missing` | a row key the contract's machine-readable `item_shape` requires (e.g. `platforms[].peer_synthesis`) and every gold row carries is missing from the rows |
| **block** | `held_beyond_cap` | the must-present set's members not stated — held, null or absent — exceed the cap: at most **2**, or **25%** of the set, whichever is smaller (owner decision 2) |
| warn | `list_len` | fewer rows than **0.5 ×** the gold's (nested lists: per parent row) |
| warn | `item_key_missing` | any other row member every gold row carries and under **60%** of this run's rows do |
| warn | `item_fill` | a member filled on under **0.6 ×** the gold's share of rows — a null member is unfilled; a null beside its own `<member>_basis` is a stated absence |
| warn | `stated_share` | on a fields list, the share of stated, un-held values under **0.6 ×** the gold's |
| warn | `key_absent` / `key_empty` | a key the contract makes optional with no condition (`storyline_challenge`), an empty citation list, a required key in a section that states it is empty |

Keys today's contract no longer declares, `empty_state` and `r_layer` are owed by
nobody. The floors (0.5, 0.6) measure warnings only; they were never adjudicated and
refuse nothing.

**Which gold a run is held to.** A gap counts only when it holds against **every**
reference gold run that has the page — "a key the gold always serves". The reference set
is chosen per run:

- **Leave-one-out.** A gold run is never in its own reference set (matched on the run-id
  prefix the fixture records). Compared with itself it could show nothing, which made
  "the gold runs pass" a statement about nothing.
- **Sub-vertical first.** Gold runs of the run's sub-vertical, when any remain, are the
  reference for structure and for the warnings. When none does, every remaining gold run
  is the reference for **structure only** and no count or fill warning is raised against
  another sub-vertical's shape.

Measured 2026-10-04 on read-only `get_staged_payload` pulls: goeasy-ltd (`02e840d4`, CL)
0 blocking; Golden 1, Baxter and Logix, each against the other two, 0 blocking; SWBC
(`7968492e`, IB) refused on `sentiment.gap_analysis` absent, firmographics 6 of 10
must-present members held, and `platforms[].peer_synthesis` missing.

Thinness warnings (`list_len`, `stated_share`) are not raised when an `empty_state`'s
every `sources_searched` rung reached `RESOLVED`, `VERIFIED_ABSENT` or
`REFUSED+ALTERNATE_TRIED` — "not retrieved", "neither found nor ruled out" and `NOT_RUN`
are not terminal (RC-05). Sections served to no audience are not compared. When no peer
is scored anywhere in the run (peers identified, not scored — settled), the peer-
comparison nulls (`peer_median`, `peer_n`, `peer_score`, `delta`, `direction`) are
disclosed once rather than warned row by row.

**Held fields — one vocabulary (owner decision 2, 2026-10-04).** On the app pages a
firmographic the evidence cannot state is `quarantined: true` with a
`quarantine_reason` naming the route searched. It is not a hedge and it is not a
completed answer:

- a held field **renders as a stated absence with its reason** — it never disappears;
- held fields are capped at **2 or 25% of the must-present set, whichever is smaller**;
- a known registry answer — charter, primary regulator, branches — is **stated**, never
  held: "None — non-depository; licensed by line" is a value;
- a subsidiary or segment figure is admissible on the strip when its `unit`/`basis` names
  the entity it describes (e.g. "SWBC Mortgage Corporation, HMDA 2024").

In the workbook the same absence reads `ABSENT (see 1.2)`. The phrase "Not established
for this run" is a hedge in both places.

**Who sees what.** Generated from `redaction.py` into the fixture's `dispositions`.
`never_served` sections are produced and audited but render for no audience: the
capability ceilings (O1b) and the evidence census (O10) do **not** render on D1, whatever
an older page index says (D-35). `page_withheld` is the context dashboard, locked for the
customer audience. `reduced` is a section the customer receives through a projection
(`redaction.CUSTOMER_PROJECTIONS`), not the internal record. **Owner decision 1
(2026-10-04)** gives customers a REDUCED sentiment card — ratings bars and themes,
without cell codes, internal sources, cap vocabulary or `r_layer` — superseding TRD §11's
withholding for `overview.sentiment` only (`thought_leadership` stays withheld).
Regenerate the dispositions with `python3 scripts/gen_surface_gold.py
--dispositions-only` whenever `redaction.py` changes; a test fails until you do.

CG-PAR compares the INTERNAL record. The customer projection is compared client against
client with Gate J `--api --audience customer`.

**The gold's shape, per page** (rows per top-level list, min–max across the three gold
runs; generated from `fixtures/surface_gold.json` → `summary`):

### overview

| Section | Internal | Customer | Gold runs filling it | Rows per list |
|---|---|---|---|---|
| `ceilings` | never_served | never_served | 3 of 3 | `rows` 16–17 |
| `evidence_coverage` | never_served | never_served | 3 of 3 | `claim_classes` 3–4; `per_pillar` 4; `tiers` 4–5 |
| `exec_summary` | served | served | 3 of 3 | — |
| `financial_series` | served | served | 3 of 3 | `series` 5–6 |
| `findings` | served | served | 3 of 3 | `findings` 5 |
| `firmographics` | served | served | 3 of 3 | `fields` 15–16, stated and un-held ≥ 93% |
| `leadership` | served | served | 3 of 3 | `roster` 6–10 |
| `opportunity` | served | served | 3 of 3 | `discarded` 4–8; `tiles` 4–5 |
| `scores` | served | served | 3 of 3 | `pillars` 4 |
| `sentiment` | served | reduced (bars + themes, owner decision 1) | 3 of 3 | `bars` 2–7; `themes` 2–7 |
| `thought_leadership` | served | withheld | 3 of 3 | `entries` 4–5 |
| `why_now` | served | served | 3 of 3 | `signals` 3–4 |

### heatmap

| Section | Internal | Customer | Gold runs filling it | Rows per list |
|---|---|---|---|---|
| `alerts` | served | withheld | 3 of 3 | `alerts` 11–116 |
| `cell_evidence` | served | served | 3 of 3 | `cells` 690–706 |
| `cohort_patterns` | served | withheld | 3 of 3 | `insufficient_cohorts` 1–11; `patterns` 0 |
| `evidence` | served | served | 3 of 3 | `evidence` 16–541 |
| `evidence_age` | served | withheld | 3 of 3 | `rows` 26–537 |
| `focus_areas` | served | served | 3 of 3 | `focus_areas` 3–5 |
| `safeguard_gates` | served | reduced | 3 of 3 | `caps` 1–14; `gates` 0–2 |
| `value_chain` | served | served | 2 of 3 (optional section; no floor) | — |
| `workbook_scores` | served | served | 3 of 3 | `categories` 16–17; `pillars` 4 |

### insights

| Section | Internal | Customer | Gold runs filling it | Rows per list |
|---|---|---|---|---|
| `insights` | served | served | 3 of 3 | `cards` 6–8 |
| `landscape` | served | reduced | 3 of 3 | `tiles` 4 |

### platform

| Section | Internal | Customer | Gold runs filling it | Rows per list |
|---|---|---|---|---|
| `platform_story` | served | served | 3 of 3 | `discarded` 7–8; `platforms` 5 |
| `recommendations` | served | served | 3 of 3 | `recommendations` 5–8 |
| `roadmap` | served | served | 3 of 3 | `phases` 3–5 |
| `stairstep` | served | served | 3 of 3 | — |
| `starters` | served | withheld | 3 of 3 | `starters` 5–6 |

### context

| Section | Internal | Customer | Gold runs filling it | Rows per list |
|---|---|---|---|---|
| `acquisitions` | served | page_withheld | 3 of 3 | `rows` 0–1 |
| `context_sentiment` | served | page_withheld | 3 of 3 | `context_tiles` 3 |
| `issue_register` | served | page_withheld | 3 of 3 | `issues` 3–5 |
| `regulatory_standing` | served | page_withheld | 3 of 3 | `additional_regulators` 1–2; `jurisdictions` 1–5 |
| `timeline` | served | page_withheld | 3 of 3 | `events` 7–14 |

### techstack

| Section | Internal | Customer | Gold runs filling it | Rows per list |
|---|---|---|---|---|
| `techstack` | served | reduced (CONFIRMED/ABSENT rows only, DECISIONS D4) | 3 of 3 | `items` 32–56; `layers` 4; `dropped` 0–7; `compliance_attestations` 0–6 |

Per-member fill ratios and nested lists (cards' `gaps[]`, `peer_deployments[]`,
`estate_reach[]`, …) are in the fixture, not repeated here; the gate reads them.

**Open adjudications — not resolved here.** The thin-evidence flag (the DB generated
column, or the H2 contract rule "fewer than three linked items, or inherited/declared
provenance" — they disagree on 144 SWBC cells) and the techstack layer denominator
(producer-written product slots, or the server's cell count; T-03/DNR-6) are open. The
gold records whether `thin` and `expected` are filled, never which rule produced them;
a null `expected` beside its `expected_basis` is a stated absence and passes.
