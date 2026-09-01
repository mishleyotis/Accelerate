# The DMA deliverable gold standard

**Read this, and open the reference package, BEFORE you author anything.** The gold
standard is not a description — it is the **Golden 1 Credit Union** package
(`DMA-2026-GOLDEN1-001`), named by the engagement owner as the best so far. Every
number below is what that package meets. A producer that authors first and discovers
the standard in QA has already failed the one-turn test; the point of this file is to
let you understand the deliverable before you start, and to give you a gate
(`engine/gold_standard.py`) you run on your OWN output before you return.

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
  reads `ABSENT (see 1.2)` with a route, never blank and never "quarantined".
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
- **Depth**: ≥60 distinct evidence citations; assessment ≥3,500 words, research ≥2,500.
  Cite the evidence base, do not summarise it.
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

## No hedges

These read as "the work was not finished" and must never ship: "Not established this
run", "to be established at the surface-production stage", "no score yet", "queued for
enrichment", "TBD", "N/A" standing in for a value. If a thing is genuinely unknown, it
is an **Unknown evidence gap disclosed in Coverage** or an **ABSENT firmographic with a
route** — a stated, structured absence, never a hedge.

## The gate is the contract, executable

`engine/gold_standard.py` encodes every rule above and maps each to the goeasy finding
it prevents (`docs/goeasy-findings-register.md`). Run it on your own output. Green is
the definition of done.
