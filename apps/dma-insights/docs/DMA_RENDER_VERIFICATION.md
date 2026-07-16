# DMA Render Verification — backend-processing → frontend-presentation coverage

Date: 2026-06-08
Corpus: `dma_val` (full committed corpus seeded via
`historical_backfill --dir tests/fixtures/dma_packages_batches --force`)
Result: **95 active entities, 0 blank names, 0 zero-score entities.**

This document answers the operator's question — *"how is information passed
to the frontend, and what does each of the ~96 DMAs actually present?"* — by

> **2026-06-11 update (QA-driven rebuild):** alerts flipped from
> "0 by design" to **populated** — the thin-evidence producer
> (services/alerts_producer + §2c derive_alerts) materializes 1,552
> alerts across the 95 ACTIVE entities (1,436 high / 116 medium;
> category-aggregated above 5 thin subcaps). Run dates now render the
> ASSESSMENT date (migration 039; backfill_run_dates repaired 79/95 —
> REQ-hex/SYNTH ids fall back to ingest time). Known source-genuine
> gaps surfaced by the rebuild, NOT faked in the UI: recommendations
> carry no effort_band/maturity_lift in this corpus (single-phase
> roadmap, no-uplift staircase); issue_register opened_on/resolved_on
> NULL on all 498 rows (degenerate Gantt spans); timeline events carry
> no signal/cap_impact (signal derived from kind); no license/
> jurisdiction firmographics keys; some CAGRs prose-only.

running `app.scripts.qa_render_validation` (12 page-render endpoints × 95
entities = 1 140 cells) against the live ASGI app on the seeded DB and
classifying every surface OK / PARTIAL / FAIL.

## Headline

```
RENDER QA SUMMARY: 768 OK (67.4%), 372 PARTIAL (32.6%), 0 FAIL (0.0%)
ZERO-SCORE (degraded) entities: 0/95
```

**0 FAIL across all 1 140 cells.** No endpoint 500s, no contract break, no
entity renders an error. The information *is* being passed correctly; the
PARTIALs are honest "this surface is sparse / not-yet-computed for this
source", not bugs.

## Three harness false-negatives fixed (information WAS passing; the QA lied)

Before this pass the matrix under-reported real data as missing on three
surfaces. These were defects in the **QA harness**, not the app — the
endpoints were returning full payloads the whole time:

| Surface | Was reported | Truth | Root cause |
|---|---|---|---|
| **heatmap** | `only 4 cells (typical >= 600)` PARTIAL for 94/95 | up to **1 085 cells** at subcap zoom (e.g. American Homes 4 Rent) | Harness probed the default `?zoom=pillar` (correctly ~4 cells = 4 pillars). Now probes `?zoom=subcap` so the `>=100` floor measures the real grid. |
| **platforms** | `no platform scores` PARTIAL for 95/95 | all **5 platform cards** every time (475 rows = 95×5 in `platform_scores`) | Harness read `body["platforms"]` / `["items"]`; the response field is `cards` (`PlatformsResponse.cards`). |
| **context** | `only N firmographic fields` PARTIAL for 95/95 | **61 OK** — leadership rosters, regulator, narrative prose, issue register | Harness counted scalar keys (`hq`/`employees`/`total_assets`/`branches`) the parser never emits. Now credits the signals the page actually renders. |

These three fixes moved **249 cells** from false-PARTIAL to OK (519→768).

## Per-surface coverage (the honest "what each DMA presents")

| Endpoint | OK | PARTIAL | FAIL | Source / why PARTIAL |
|---|---:|---:|---:|---|
| overview | 94 | 1 | 0 | pillar scores from workbook — present for all |
| heatmap | 93 | 2 | 0 | subcap_scores grid; 2 entities genuinely thin |
| health | 95 | 0 | 0 | alerts/issues/caps — always renders |
| runs | 95 | 0 | 0 | run history — always ≥1 |
| platforms | 95 | 0 | 0 | 5 computed platform cards every entity |
| evidence | 86 | 9 | 0 | `evidence_index`; 9 sources carried no evidence rows |
| context | 61 | 34 | 0 | leadership/narrative/regulator/issues; 34 thin sources |
| focus_areas | 71 | 24 | 0 | parser-emitted; source-dependent |
| recommendations | 56 | 39 | 0 | parser-emitted; 39 packages had 0 recs |
| techstack | 22 | 73 | 0 | `tech_stack_entries`; 73 packages documented no stack |
| insights | 0 | 95 | 0 | **by design** — see Tier C |
| intelligence | 0 | 95 | 0 | **by design** — see Tier C |

## Surface taxonomy — where each surface's data comes from

**Tier A — workbook/scores (parse+persist), present for ~all entities:**
overview, heatmap, health, runs, platforms, evidence. These are computed
deterministically from the persisted `subcap_scores` / `evidence_index` /
`platform_scores` at ingest. A populated DMA always renders these.

**Tier B — present where the source package carries it (genuine sparsity):**
recommendations, focus_areas, techstack, context. PARTIAL here means the
*source DMA package* didn't document that surface (e.g. no tech stack, no
recommendations). Not a bug — the frontend should show its branded empty
state (see Workstream 2 "scores-from-workbook" pending state).

**Tier C — bot-payload / post-deploy enrichment ONLY (empty in a cold seed,
by design):**
- **insights** — `insight_cards` are written *only* by the `/ingest` bot
  payload route (`routers/ingest.py`). `parse_package` / `persist_package`
  do not synthesize them and there is no in-repo rule engine. A
  parsed/Drive-ingested corpus therefore has 0 insight cards until the
  upstream assessment bot supplies them. Honest reason:
  `no insight cards (cold start before rule engine)`.
- **intelligence** — the per-entity intelligence profile is built by the
  post-deploy `intelligence_recompute` worker (`post-deploy-refresh.sh`
  Phase 2), not at ingest. 404 until that runs. Honest reason:
  `intelligence-profile 404 (not yet computed)`.

**DOCX-narrative-derived sub-surfaces — 0 across this corpus:**
`timeline_events`, `acquisitions`, `financials`, `sentiment` (children of
the Context page) are lifted from the `Assessment_Report.docx` narrative.
The sanitized fixture corpus is workbook-heavy / DOCX-light, so these are 0
for all 95. On a production package that ships the DOCX they populate; the
ContextPage styling added in `app.css` (timeline / gantt / acquisitions /
financials blocks) is what renders them when present.

## Why the live app looked "stale / blank"

The dominant cause was the **deploy aborting at Phase 7 verify** (the
`/healthz` false-negative, now fixed in `verify-deploy.sh`), so the old
build + old data kept serving and Phase 8 `post-deploy-refresh.sh` (which
runs `intelligence_recompute` and promotes traffic) never fired — leaving
the Tier-C surfaces (insights / intelligence) empty on the live app. With
the deploy completing end-to-end, Tier A/B render from the workbook
immediately and Tier C populates from the post-deploy worker.

## Reproduce

```bash
cd apps/dma-insights/backend
export DATABASE_URL=postgresql+asyncpg://dma:<pw>@127.0.0.1:5432/dma_val
export DATABASE_URL_SYNC=postgresql+psycopg://dma:<pw>@127.0.0.1:5432/dma_val
export ENV=local
python -m app.scripts.historical_backfill \
  --dir tests/fixtures/dma_packages_batches --force   # 95 active / 9 dropped / 8 error
python -m app.scripts.qa_render_validation            # EXIT 0, 0 FAIL
```
