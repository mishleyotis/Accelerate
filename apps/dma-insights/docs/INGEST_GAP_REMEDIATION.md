# Ingest gap remediation — report → extraction → render, and how each gap heals

**Status:** living doc · created 2026-06-08 after the qa-gates render-harness
failure (18 FAIL = 9 `overview` + 9 `heatmap`, all "zero scores").

This is the canonical map of **what we extract from a DMA package**, **where
it renders in the frontend**, **why a surface is sometimes partial/empty**, and
**which remediation lane heals it** — parser, AI-enrichment (post-deploy,
automatic), or retrieval/drive-backfill (post-deploy).

The corpus is intentionally messy: the 113 sanitised fixtures mirror the
real Drive corpus, where packages arrive in many shapes. The system's job is
to **degrade gracefully, never break**, and **self-heal after deployment**.

---

## 1. The three remediation lanes

| Lane | Owns | Runs | Can it invent maturity scores? |
|---|---|---|---|
| **Parser / extractor** (`app/services/parsers/*`) | Structured truth: subcap scores, evidence, peers, tech, recs, narrative sections | At ingest | **Yes** — when the scoring workbook exists in *any* layout |
| **AI enrichment** (`app/services/enrichment.py`, `synthesis_orchestrator.py`) | Narrative synthesis (SCQA, insight prose, context story) grounded on parsed evidence/sections | Post-deploy, auto (Pub/Sub `dma.ingest.completed`) | **No** — never fabricates 1–5 scores; only prose grounded on real evidence |
| **Retrieval / drive-backfill** (`workers/drive_crawler`, `historical_backfill --retry-failed-only`) | Re-fetching a package that was missing or incomplete at ingest | Post-deploy, scheduled/manual | N/A — it gets the *source* so the parser can run |

**Primary policy — drop pre-subcap-framework assessments at ingest
(2026-06-08 operator mandate):** an assessment that parses to **zero subcap
scores** ran an *old DMA methodology* that predates subcap-level maturity
scoring. It can only ever render an empty ScoreRing / heatmap, so every ingest
entry point **drops** it rather than create a hollow entity:

- `app/scripts/historical_backfill.py::_is_pre_subcap_framework` + the guards
  in `_ingest_local_dir` (local/deploy backfill) and `_ingest_folder` (Drive),
- the live `POST /api/v1/ingest/package` router (returns `422`),
- keyed on the **parsed** package's `subcap_scores` only, so a selective
  re-ingest that *skips* an unchanged-but-populated scoring table is never
  mis-dropped.

Validated end-to-end on the full 113-fixture corpus: **96 ingested, 9 dropped
(pre-subcap framework), 8 error (missing package)** → render harness
**0 FAIL / 0 zero-score** across 95 entities × 12 endpoints.

**Backstop — render harness:** even with the drop in place, the harness keeps
a defensive net: a zero-score surface that somehow reaches it is `PARTIAL`
(degraded), not FAIL; the build only hard-fails on a *systemic* zero-score
regression (aggregate floor) or a real contract break (HTTP ≥ 400, non-JSON,
out-of-range scores, validator crash). See `app/scripts/qa_render_validation.py`
+ `tests/test_qa_render_classification.py` + `tests/test_pre_subcap_framework_drop.py`.

---

## 2. Report artifact → extraction → frontend surface

| Source artifact (in package) | Parser | DB table | API field | Frontend surface | If missing → |
|---|---|---|---|---|---|
| `03_scoring_workbook/export_scoring_detail*.csv` / `*scoring_workbook*.xlsx` / `*_scoring_workbook.md` | `package_csvs.py` + score fallbacks in `dma_package.py` | `subcap_scores` | `overview.pillar_scores`, `overview.overall_score`, `heatmap.cells[].score` | **ScoreRing** (D1), **pillar bars** (D1), **Heatmap grid** (D3) | empty ring + "Context still building" empty state; **parser lane** |
| `04_reports/Assessment_Report*.docx` | `assessment_report.py` → `section_routing.py` | `document_sections`, `document_lineage` | `*.narrative` (overview/insights/heatmap/platform/context/health) | SCQA blurb, insight prose, per-pillar deep-dive text | `narrative:null` → skeleton renders; **enrichment lane** |
| `04_reports/*_Client_Profile_Research_Report.docx` | `client_profile.py` | `focus_areas`, `firmographics` | `focus-areas`, `overview.firmographics` | **Focus-area gradient cards** (D3 heatmap header), firmographics chips | empty focus list; **parser then enrichment** |
| `01_evidence/evidence_index.{csv,json}` | `package_csvs.py` / `package_json.py` | `evidence_index` | `evidence[]` | **EvidenceDrawer** rows + freshness badges | empty drawer; **parser then retrieval** |
| `06_peers/peer_comparison_table.csv` / `peer_scores_*.json` | `package_csvs/json` | `peer_benchmarks` | `overview.peer_*`, heatmap peer overlay | peer ▲/▼ arrows | no peer overlay (fail-closed); **parser** |
| `A*_Tech_*.csv/.xlsx` (tech stack) | `package_csvs.py` | `tech_stack_entries` | `techstack[]`, `platforms` | **Platform page** tech list | empty tech list; **parser then enrichment** |
| `recommendations_detail.json` / `06_recommendations.json` | `package_json.py` | `recommendations` | `recommendations[]` | **Recommendations** tab | "no recommendations" empty; **parser then enrichment** |
| (none — derived) | `customer_intelligence.py` worker | `customer_intelligence_profiles` | `intelligence-profile` (404 until computed) | **PersistentIntelligenceCard** | 404 → card hidden (PARTIAL, expected pre-worker); **enrichment** |

---

## 3. The 9 dropped (zero-score) entities — per-entity classification

These 9 parse to `scores=0` and are now **dropped at ingest** (not surfaced).
The table records *why* each is score-less, so a future re-fetch (retrieval)
or parser upgrade can recover the ones whose scoring data actually exists.
Full dropped set from the validated backfill: DovenMuehle, ZipHQ, Echelon
Insurance, SPG, Valley Bank, Ameris Bank, MidFirst Bank, GESA, Mag Mutual.

| Entity | Scoring artifact in package | Lane | Action |
|---|---|---|---|
| **SPG** | `SPG DMA/spg_scoring_workbook.md` — but only **category/pillar rollups** (`P1C1=3.0 … P1 TOTAL=2.65`), not the ~600 subcap scores | **Parser (partial)** | Mine pillar/category rollups → ScoreRing + pillar bars render; subcap **heatmap** stays empty (cannot fabricate subcaps from category rollups) → enrichment/backfill (§4.1) |
| **DovenMuehle Mortgage** | `02_research_workbook/DMA_Research_Workbook_DMI_*.xlsx` (scoring sheet TBD) | **Parser (verify)** | Confirm the xlsx carries true subcap scores before mining (§4.1) |
| **GESA** | evidence register only; no scoring detail | Retrieval | Drive re-fetch scoring workbook; else score-less |
| **Mag Mutual** | background-research CSVs only | Retrieval | Drive re-fetch; else score-less |
| **MidFirst Bank** | A1–A9 appendices only | Retrieval | Drive re-fetch; else score-less |
| **Ameris Bank** | 15 files, no scoring | Retrieval | Drive re-fetch; else score-less |
| **Valley Bank** | sections only (`REQ-` run) | Retrieval | Drive re-fetch the deliverable |
| **ZipHQ** | near-empty package | Retrieval | Drive re-fetch the deliverable |
| **(9th: aggregation edge)** | subcaps present, pillars 0 | Parser | pillar-rollup guard |

**Takeaway:** ~2 are quick parser wins (SPG, DovenMuehle), the rest are
*genuinely absent at source* → the package itself must be re-fetched
(retrieval lane) before any scores can exist. **No lane fabricates scores**,
so until the source arrives these correctly render the empty state.

---

## 4. Remediation detail

### 4.1 Parser lane — recoverable non-canonical scoring layouts

`dma_package.py` already has root-recursive CSV + xlsx score fallbacks
(added for ProPartners/LPL/ATB — those now score 605–708). Two layouts are
still unmined and are tracked as **follow-up parser work** (not deploy
blockers):

1. **Markdown scoring tables** (`*_scoring_workbook.md`, e.g. SPG). On
   inspection SPG's markdown only carries **category + pillar rollups**
   (`| P1C1 Digital Strategy | 18% | 3.0 | 0.540 |` … `| P1 TOTAL | | | 2.65 |`),
   not the ~600 fine-grained subcap scores. So a `_scores_from_markdown()`
   fallback can faithfully populate **`overview.pillar_scores` + overall**
   (→ ScoreRing + pillar bars render) but **must NOT** synthesise subcap
   cells — expanding a category score onto its child subcaps would be
   fabrication. The subcap **heatmap** stays empty for SPG until the true
   `export_scoring_detail.csv` is retrieved. This is a *partial* parser win.
2. **Research-workbook xlsx scoring sheets** (DovenMuehle). Before adding a
   fallback, **verify** the `02_research_workbook/*.xlsx` actually contains
   per-subcap scores (vs. evidence-only). Only mine sheets named
   `*scoring*`/`*maturity*` carrying a subcap-id column; otherwise treat as
   a retrieval gap.

Both are additive fallbacks gated behind "canonical candidates yielded
nothing", so they cannot regress entities that already parse. Neither is a
deploy blocker; both are queued as follow-up parser work because the honest
behaviour today (empty state + heal post-deploy) is already correct.

### 4.2 AI-enrichment lane — automatic, post-deploy

Already wired: `package_persist.py` fires enrichment when `evidence_count < 2`
(all 9 zero-score entities have `evidence=0`, so they auto-queue) via the
`dma.ingest.completed` Pub/Sub → `intelligence_recompute` worker. Enrichment
fills **narrative** surfaces (SCQA, insight prose, context) grounded on the
parsed sections/evidence and **persists** (zero token cost on re-read per the
synthesis cache). It does **not** synthesise 1–5 maturity scores.

Industry-grade **iterative** prompt pattern (probe → critique → refine, rather
than accept-first) — to add as `enrichment.py` prompt templates, each run
through the existing post-generation validator (fail-closed → template):

```
PASS 1 — DRAFT (gemini-2.5-flash)
  System: "You are a DMA analyst. Using ONLY the evidence blocks below,
  draft the {surface} narrative for {entity}. Every claim must cite an
  E-ID present in the bundle. If evidence is insufficient for a claim,
  write '[insufficient evidence]' rather than inventing it."

PASS 2 — SELF-CRITIQUE (same model, draft + evidence as input)
  "List every sentence in the draft that is (a) uncited, (b) cites an
  E-ID not in the bundle, or (c) states a maturity score not present in
  subcap_scores. Output a JSON list of {sentence, defect}."

PASS 3 — REFINE (only if Pass 2 found defects; else accept Pass 1)
  "Rewrite the draft removing/repairing every flagged sentence. Do not
  introduce new claims. Re-cite from the bundle only."

PASS 4 — PROBE (only when a required field is still '[insufficient
  evidence]' AND the gap is enrichable from a peer/cohort signal)
  Escalate to gemini-2.5-pro with the cohort bundle (cohort_mode honoured)
  and ask narrowly for the single missing field; re-run Pass 2 on the
  delta. Cap at 2 probe rounds to bound token spend.

STOP CONDITIONS: validator clean OR 2 probe rounds reached → persist with
  data_source='llm'; on any unresolved fabrication → fail-closed to the
  parsed-skeleton template (never serve unvalidated score claims).
```

This is the "keep probing rather than accept the first answer" loop the
brief calls for, bounded so it cannot run away on token cost.

### 4.3 Retrieval lane — the ~8 "no DMA package detected" folders

`ERROR:parse … FileNotFoundError: no DMA package detected` for: IMA Financial
(batch_02 — note IMA Financial **Group** in batch_10 *did* ingest, so this is
a mis-filed/empty dup folder), AAA Club Alliance, Amegy Bank, YNCU, Midfirst
Bank (batch_09 — a dup of the batch_07 MidFirst that ingested), Navacord, The
Bank of Missouri. These folders **contain no MANIFEST.json, < 2 canonical
`01_..08_` subfolders, and no DMA-shaped `.docx` within depth 3** — i.e. the
deliverable was never placed there (a *retrieval* gap, not a parser bug).

**Post-deploy plan:** the live `drive_crawler` re-crawls the source Drive
folder; any entity still missing its deliverable lands in
`backfill_quarantine` and is retried via
`historical_backfill --retry-failed-only`. Empty dup folders (IMA batch_02,
Midfirst batch_09) are deduped by `request_id`/entity and need no action — the
real entity already ingested under its canonical folder.

---

## 5. Why this is safe for the deploy

- The 9 zero-score entities return **HTTP 200 + empty contract** → frontend
  renders its **fail-closed empty state** (verified by the harness: every one
  is 200, none 500). That is correct, designed behaviour.
- The render harness now treats those as **PARTIAL** (degraded) and prints
  them as the explicit post-deploy **parser/enrichment/backfill queue**, while
  the **aggregate zero-score floor (20%)** still fails the build on a systemic
  regression (current ~8% is well under).
- Genuine breakage (HTTP error, non-JSON, out-of-range scores, validator
  crash) stays a hard **FAIL**.

Net: the deploy proceeds with an honest, tracked degradation list; the gaps
heal automatically (enrichment) or on the next crawl (backfill), and the two
parser wins (SPG, DovenMuehle) are queued as additive fallbacks.
