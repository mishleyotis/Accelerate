# The DMA app-pages gold standard

The six app pages' measurable gold. Split from `GOLD-STANDARD.md` (which covers the
workbook and the reports) so a per-surface producer reads only the gold it produces
against — its full reading order is held under a ratchet
(`plugins/dma-insights/scripts/tests/test_reading_load.py`).

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
