# Card-population census — 94 clients × Standalone 5 template

Generated 2026-07-10 on the consolidated branch
(`claude/web-app-cloud-run-redeploy-4rrmp6`) against the full 113-package
fixture corpus: `historical_backfill --force` (96 ingested, 0 errors) →
`run_derive_chain` (29/29 green, Vertex-cold) → `qa_render_validation`
(94 entities × 15 endpoints).

## Template conformance (page structure vs the Standalone 5 prototype)

Every prototype page's component inventory was extracted from the uploaded
`DMA_Insights___Standalone_5.html` bundle and diffed against the production
React pages:

| Page | Verdict |
|---|---|
| D1 Overview | Matches (incl. CoverageByPillarCard, SCQA, WhyNowStrip, leadership, all five deep cards) |
| D2 Insights | Matches (filters, cards, technology-landscape strip) |
| D3 Heatmap | Matches (pillar/category/subcap views, focus view, KPI strip, synthesis drawer, issue banner) |
| D4 Platforms | Matches (fit table, drilldown w/ recs + conversation starters, stairstep, TransformationRoadmap) |
| D5 Context | **FIXED this release** — dropped cross-pillar stories, leadership panel, peer-comparison card (template renders leadership on Overview; peer deployment on the tech-stack drilldown; Context = timeline, issue gantt, financial-trajectory chart, regulatory standing, sentiment, acquisitions) |
| D6 Health | Matches (thin-evidence alerts, version diff, evidence age, cross-entity patterns as tabs) |
| Tech stack (+detail) | Matches (tier legend, rows → platform matrix link; peer deployment in detail) |

## Render census (endpoint level, Vertex-cold)

1,389 OK (98.5%) · 21 PARTIAL (1.5%) · **0 FAIL** across 94 entities × 15 endpoints.

| Endpoint | OK | PARTIAL | FAIL | Notes |
|---|---|---|---|---|
| context, evidence, health, heatmap_category, heatmap_pillar, insights, intelligence, overview, platforms, platforms_roadmap, recommendations, runs, techstack | 94 each | 0 | 0 | |
| focus_areas | 75 | 19 | 0 | Honest deferral **by operator mandate** (2026-07-08): focus areas are never synthesized deterministically; Vertex-cold runs ship nothing rather than wrong strategic objectives. The Vertex-enabled post-deploy refresh fills these 19 via validated Gemini synthesis. |
| heatmap | 92 | 2 | 0 | bank-of-utah (52 cells), sunflower-bank (92 cells) — honestly-thin packages; the scored cells render, empty cells show the honest empty state. |

## Card-data census (SQL level, per ACTIVE client)

| Check | Count | Disposition |
|---|---|---|
| Clients with zero insight cards / firmographics / platform scores | 0 | — |
| Clients with zero recommendations | 1 (`atb-f860`) | ATB's package ships **zero evidence rows**; grounded gap-fill cannot cite what does not exist (no-fabrication rule). Honest empty states render. |
| Clients with zero timeline events | 1 (`atb-f860`) | Same root cause. |
| Clients with zero issues | 6 | Packages without issue registers — prototype's "No issues on record" empty state. |
| Clients with zero focus areas | 15 | The Gemini-refresh set above (subset of the 19 PARTIALs). |
| Farm Credit Mid-America recommendations | **16** | Zero-rec gap-fill working: grounded recs from below-M4 categories → D4 recommendations + TransformationRoadmap now populate. |
| Post-derive shipped-hollow gate | **0** | No scored client ships with zero recs+evidence. |

## NLP-script refinements landed in this release

1. **Exec-summary multi-anchor grading** — every executive narrative was
   hard-failing G2/G7 because citations threaded from findings 2–4 were
   judged against finding 1's capability. `Item.anchor_subcaps` +
   grader/composer/refine wiring fixes the false fails (pre-existing,
   deploy-blocking on the source branch).
2. **Zero-rec gap-fill verified corpus-wide** (`_MAX_RECS = 16`) — the
   Farm-Credit-class "no recommendations/roadmap" defect.
3. **Per-metric financial-trajectory outlier band** — 5× balance-sheet /
   50× net-income guard band (drops mis-grabbed series points before the
   anchor rung can double-error-rescue them).
4. **Hollow census re-pinned 16 → 14** — two packages un-hollowed by the
   merged rec parser (measured, deliberate).
5. **Notes API hardening** — malformed note/assessment ids now 404
   instead of 500 (no-5xx regression net green).
