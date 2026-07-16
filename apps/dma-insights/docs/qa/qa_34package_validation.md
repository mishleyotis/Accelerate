# v2 QA — 34-package validation corpus (2026-06-07)

**Input:** 5 DMA batch zips (`DMA_batch_01..05`) = **34 real client
packages** spanning banks, credit unions, insurance brokers, wealth
managers, and mortgage servicers.

**Harness:** `apps/dma-insights/backend/qa_v2_34package_audit.py`
(committed, reproducible — point it at a local extraction).

**Purpose (per user):** "Check whether all improvements made above need
to be strengthened while looking at the following sample." Answer:
**YES** — the 34-package corpus surfaced 4 parser-robustness gaps the
5-folder reference sample (Alma / WSFS / Nicola / Odlum / Calprivate)
never exercised. All 4 are now fixed and pinned with contract tests.

---

## Where the corpus lives (maintainer decision 2026-06-07)

The 34 packages extract to **154 MB** and contain client internal-
evidence PDFs (SI decks, leadership dossiers). The tradeoffs (repo
bloat ~20×, client-confidential docs in git history, ADR 0015
sanitized-fixtures policy) were surfaced to the maintainer, who
**explicitly chose to commit the raw packages as-is** as a
full-fidelity regression corpus.

Committed at:

    apps/dma-insights/backend/tests/fixtures/dma_packages_batches/
        batch_01/  (Haventree, Navy Federal, Wintrust, Zions)
        batch_02/  (DovenMuehle, Exchange, IMA, OneDigital, ZipHQ)
        batch_03/  (AAA Club Alliance, Alliant, Amarillo National,
                    American Airlines FCU, Echelon, Empower FCU)
        batch_04/  (First Citizens, Fulton, Penderfund, Rockland,
                    SPG, Security Finance, Tri Counties, Valley)
        batch_05/  (Amegy, AmeriCU, Ameris, Corporate America CU,
                    Financial Partners CU, Frost, Members 1st,
                    South State, Vestgen, [client-redacted], Wescom)

Run the audit against the committed corpus with no args:

    cd apps/dma-insights/backend && python qa_v2_34package_audit.py

This batch also commits:
- the **reproducible audit harness** (`qa_v2_34package_audit.py`);
- this **findings doc**;
- a tiny **synthetic fixture**
  (`tests/fixtures/dma_packages_synthetic/handoff_mode_params_variant/`)
  that exercises the new code paths in CI without depending on the
  full corpus;
- **contract tests** pinning every fix.

> **Note:** the contract tests use the synthetic fixture (not the
> committed corpus) so they stay fast + deterministic. The corpus is
> for the manual `qa_v2_34package_audit.py` sweep + future sanitized-
> fixture extraction.

---

## Audit result (after strengthening)

```
TOTAL: 30 OK, 4 FAIL out of 34
```

| Class | Count | Notes |
|--|--|--|
| Full ingest (evidence + subcaps + manifest) | 24 | banks/CUs/insurers with canonical layout |
| Partial (subcaps but variant-empty evidence / scoring) | 6 | per-pillar evidence or non-03 scoring (deferred §B) |
| Hard FAIL (non-canonical folder taxonomy) | 4 | space-named subdirs / workbook-only (deferred §C) |

---

## A. Gaps fixed this batch (strengthening the prior improvements)

### A1 — Institution-name folder-fallback mangling

**Symptom:** packages whose folder name is `{Name} - DMA` rendered the
institution as `{Name}   DMA` (triple space + retained "DMA") in every
page header. Affected: Ameris Bank, SPG, Valley Bank, ZipHQ, +
the docx-only synthesis path generally.

**Root cause:** `dma_package.py` fallbacks did
`root_p.name.replace("_"," ").replace("-"," ")` — turning ` - DMA` into
`   DMA` and never stripping the suffix.

**Fix:** new shared `_clean_institution_from_folder()` helper strips the
DMA-package suffix set (`_DMA_Complete_Package`, `_DMA_Full_Package`,
` - DMA`, ` DMA`, …), normalizes separators, collapses whitespace, and
re-strips a trailing standalone `DMA` token. Wired into both synthesis
fallbacks.

**Verified:** `Ameris Bank - DMA` → `Ameris Bank`; `SPG - DMA` → `SPG`;
`Valley Bank - DMA` → `Valley Bank`; `ZipHQ - DMA` → `ZipHQ`;
`Empower_FCU_DMA_Full_Package` → `Empower FCU`.

### A2 — Manifest synthesis from `07_governance/00_parameters.json`

**Symptom:** Alliant_Insurance was a hard FAIL (`ValueError: no run
manifest found`) despite shipping a complete canonical package.

**Root cause:** Alliant ships NO `run_manifest.json` / `qa_verdict.json`
(only `phase_*.json` checkpoints). The manifest data lives in
`07_governance/00_parameters.json` (`assessment_id`, `entity`,
`subvertical`, `pillar_weights`) — a source the parser didn't know.

**Fix:** new `_synthesize_run_manifest_from_parameters()` reads that
file, normalizes integer pillar-weight percentages (20/35/…) to 0-1
floats, and is tried BEFORE the export-CSV-header synthesis (richer
source). 

**Verified:** Alliant FAIL → OK (119 evidence, 701 subcaps, 8 recs,
46 sections, 4 leadership).

### A3 — `research_handoff.json` in `01_evidence/`

**Symptom:** Alliant's firmographics + handoff-manifest synthesis
missed the handoff JSON.

**Root cause:** the parser scanned `02_research_workbook/`,
`07_governance/`, `08_appendices/` for `research_handoff.json` —
Alliant ships it in `01_evidence/`.

**Fix:** added `01_evidence` to both the handoff-manifest scan dirs and
the firmographics `handoff_paths`.

### A4 — JSON evidence variant (top-level list + key aliases)

**Symptom:** Rockland_Trust (689 subcaps) and Corporate_America_CU
(700 subcaps) surfaced **0 evidence** despite shipping hundreds of rows.

**Root cause:** the parser's evidence loader only knew
`evidence_index.{csv,json}` (items-wrapped) + a couple CSV variants.
Rockland ships `evidence_index_master.json` as a **top-level JSON list**
with keys `evidence_id` / `mapped_subcaps` / `ers_tier_score`;
Corporate America ships `evidence_index_L0.json`.

**Fix:** new `_evidence_rows_from_json()` helper tolerates both the
items-wrapped and top-level-list shapes + the key-alias set
(`evidence_id|e_id|id`, `source_file|source_name`, `mapped_subcaps|
subcap_mappings`, …). New JSON-variant fallback scans
`evidence_index_master.json` / `evidence_index_L0.json` /
`evidence_unified_by_capability.json` / `*evidence_index*.json`.

**Verified:** Rockland 0 → **312 evidence**; Corporate America 0 →
**327 evidence**.

---

## B. Deferred — additional evidence/scoring variant gaps (6 packages)

These ingest a manifest + (usually) subcaps but have variant-empty
evidence or scoring. Not blocking; documented for the next batch.

| Package | Symptom | Likely source shape |
|--|--|--|
| Security Finance | 708 sub, 0 ev | per-pillar `p1c1_evidence.json` … (no single index — needs file-merge) |
| Echelon Insurance | 183 ev, 0 sub | scoring not in `03_scoring_workbook/export_*.csv` |
| Zions Bancorporation | 0 ev, 0 sub, 30 sec | scoring/evidence under a non-standard nested dir |
| Ameris Bank | 0 ev, 0 sub, 70 sec | same family — needs deep-dir scan |
| DovenMuehle Mortgage | 0 ev, 0 sub, 16 sec | mortgage-servicer layout variant |
| Corporate America CU | CSV `evidence_inventory_L1.csv` has `# RUN_ID=` comment line + non-canonical headers (JSON path recovered it; CSV path still skips) | comment-line-skip + column aliases |

**Fix scope for next batch:** (1) per-pillar `p{n}c{n}_evidence.json`
merge loader; (2) broaden scoring scan to nested/variant dirs;
(3) comment-line skip + column aliases in `parse_evidence_csv`.

---

## C. Deferred — non-canonical folder taxonomy (4 hard FAILs)

These 4 don't use the `NN_name` numbered-folder layout at all:

| Package | Layout | Files |
|--|--|--|
| Navy Federal CU | single XLSX, deeply nested | 1 |
| Amegy Bank | `Amegy Bank DMA/` + `Amegy Bank Background Research/` (space-named) | 13 |
| IMA Financial | `IMA Financial/IMA Financial DMA/` (double-nested, space-named) | 13 |
| AAA Club Alliance | `AAA Club Alliance DMA/` + `Revised Assessment/ACA DMA/` | 36 |

**Assessment:** Navy Federal is a workbook-only partial deliverable
(legitimately not a full package). The other 3 use a space-named
`{Entity} DMA` sub-folder taxonomy that predates the numbered-folder
contract. **Fix scope for next batch:** a non-canonical-layout
detector that maps `{Entity} DMA` / `{Entity} Background Research`
sibling folders onto the canonical buckets, OR an explicit
"partial-package" ingest path that accepts workbook-only / profile-only
deliverables.

---

## Regression safety (cascade discipline)

- 5-folder reference fixtures (Alma / WSFS / Nicola / Odlum /
  Calprivate): **counts + institution names byte-for-byte unchanged**
  after all 4 fixes.
- Full backend pytest: **1809 → 1813 passed** (+4 corpus contract
  tests), 0 failed, 63 skipped.
- `ruff check` clean on all touched files.
- Every fix is additive (new fallback paths fire only when the
  canonical path yields nothing), so the cascade-regression surface is
  zero for packages already ingesting cleanly.

## Net improvement from this batch

| Metric | Before | After |
|--|--|--|
| Hard FAIL | 5 | 4 |
| Fully-ingesting packages | ~21 | 24 |
| Mangled institution names | 4 | 0 |
| Packages recovered from 0-evidence | — | Rockland (+312), Corporate America (+327) |
| Packages recovered from hard-FAIL | — | Alliant (+119 ev / 701 sub) |

---

# Addendum (2026-06-07 pm): second upload (5 `_1` batches) + live app-render test

A second upload of 5 batches (`DMA_batch_0{1..5}_1`, 31 client folders)
arrived. 30 are **revised re-exports of already-committed clients**
(parse-identical results) + **1 genuinely new client: Chemung Canal
Trust**. To avoid ~150 MB of duplicate data, only Chemung is added to
the committed corpus (`batch_02/Chemung Canal Trust - DMA/`); the 30
re-exports were validated via the audit harness but not re-committed.

## New parser fix: CamelCase `Run_Manifest` (Chemung)

Chemung was a hard FAIL (`no run manifest found`) — its only manifest
is `08_appendices/DMA_CCTRUST_Run_Manifest.json` with **CamelCase**
`Run_Manifest`, which the case-sensitive `glob("*run_manifest*.json")`
missed on Linux (same bug class as the original F1). Fixed Priority-2
manifest discovery to a case-insensitive `iterdir` scan.

**Result:** Chemung FAIL → OK (116 evidence, 698 subcaps, 7 recs,
146 sections). `_1` batch audit: 26 → 27 OK. Pinned by
`test_corpus_camelcase_run_manifest_recognized` (synthetic fixture
`camelcase_manifest_variant`).

## Live app-render test (real ingest → API → 6 surfaces)

Brought up Postgres 16 + pgvector, ran `alembic upgrade head` (all
migrations 027-031 applied cleanly), ingested 5 representative
packages via `persist_package`, and hit all 6 client-detail endpoints
through the FastAPI app. **This proves the v2-QA features render
end-to-end on the real app, not just in the parser.**

| Surface | Frost | Alliant | Rockland | Security Fin | Zions |
|--|--|--|--|--|--|
| overview pillars | 4 | 4 | 4 | 4 | **0** |
| overview firmographics | Y | Y | Y | Y | **N** |
| overview top_findings | 5 | 5 | 5 | 5 | 0 |
| overview **assumptions (C11)** | 0 | **10** | 0 | 0 | 0 |
| heatmap cells (zoom=pillar) | 4 | 4 | 4 | 4 | 0 |
| heatmap cells (zoom=subcap) | **698** | 701 | 689 | 708 | 0 |
| context **about/narrative_md (F5c)** | Y | Y | Y | Y | N |
| health **caps_applied (C10)** | **93** | **85** | **37** | **5** | 0 |
| health **qa_verdict_l1/l2 (C5)** | Y/Y | N/N | Y/Y | N/Y | N/Y |
| health **audit_logs (C7)** | **Y** | N | N | N | N |

### Render findings

1. **All v2-QA features render live** — caps tables (5-93 rows),
   QA verdict chains, audit logs, assumptions cards, about-narrative,
   richer firmographics all populate on the real endpoints. ✓

2. **Heatmap is correct by design** — `cells=4` at the default
   `zoom=pillar`; drilling to `zoom=subcap` returns the full 698/708.
   Not a bug. ✓

3. **`insights items=0` is expected, NOT a gap** — insight CARDS come
   from the async AI-enrichment worker (`insight_cards` table), which
   this parse-only render test didn't run. The InsightsPage `narrative`
   subfield (per-pillar findings from the DOCX) DOES populate, so the
   page renders the prose fallback. ✓

4. **Partial packages render empty on the real app** — Zions confirms
   the §B gap end-to-end: 0 pillars / 0 cells / no firmographics /
   empty about. The AE would see a skeleton ClientOverview + empty
   Heatmap. This is the highest-value remaining work (§B).

## Updated backlog priority (evidence from live render)

| Gap | Live-render impact | Priority |
|--|--|--|
| §B partial packages (Zions, Ameris, Valley, SPG, First Citizens, DovenMuehle) render near-empty | AE sees skeleton pages | **HIGH** |
| §B 0-evidence-with-subcaps (Security Finance per-pillar evidence) | HeatmapPage populates but EvidenceDrawer empty | MEDIUM |
| §C non-canonical layouts (AAA, Amegy, IMA, Navy Federal) | package never ingests | MEDIUM |

---

# Addendum (2026-06-07 pm-2): stress corpus (78 packages) + verdict-fallback fix

A third upload of 10 batches (`DMA_batch_01..09` + `batch_01_3`) = **78
real client packages** (a large, diverse stress set — banks, CUs,
insurers, wealth/RIA, farm credit, mortgage) was run through the audit
harness to stress-test the strengthening fixes.

## Result

```
Initial:  70 OK, 8 FAIL / 78
After fixes below: 74 OK, 4 FAIL / 78
```

The 78 raw packages are **not committed** — they're stress-*validation*
(another ~300 MB, with many clients conceptually overlapping the
committed corpus). The fixes + this writeup are the deliverable. The
audit is reproducible by pointing `qa_v2_34package_audit.py` at a local
extraction.

## New parser fix: case-insensitive `*verdict*.json` manifest fallback

4 packages were hard FAILs ("no run manifest found") because their ONLY
manifest source is a CamelCase verdict file the case-sensitive
discovery missed:

| Package | Manifest file | Was | Now |
|--|--|--|--|
| Farm Credit Mid America | `DMA_Governance_QA_Verdict_FCMA_*.json` | FAIL | OK |
| Interactive Brokers | `IBKR_GOV_QA_Verdict.json` | FAIL | OK |
| Vornado Realty Trust | `L1_QA_Verdict.json` + `L2_QA_Verdict.json` | FAIL | OK |
| American National Bank of Texas | `DMA_GovernanceVerdict_ANBTX_*.json` | FAIL | OK |

**Fix:** a LATE case-insensitive `*verdict*.json` fallback that runs
AFTER the handoff + 00_parameters synthesis (so Nicola's richer
research-handoff path still wins — verified Nicola still resolves to
`DMA-RES-NICW` via handoff, unchanged). When the verdict file carries
no institution name (ANBTX GovernanceVerdict has run_id only), it falls
back to the cleaned folder name. Pinned by
`test_corpus_camelcase_verdict_manifest_fallback_unit` (pure temp-dir
test).

## Remaining 4 FAILs — report-only / workbook-only (not recoverable)

| Package | Layout |
|--|--|
| Midfirst Bank | 1 DOCX under `Midfirst Bank Background Research/` (report-only) |
| YNCU | 3 DOCX under `YNCU DMA/` (space-named, report-only) |
| The Bank of Missouri | 3 DOCX under `TBOM DMA/` (report-only) |
| Navacord | 2 XLSX under `DMA/` (workbook-only, no manifest) |

These ship no structured scoring/evidence + no manifest — the same
report-only / non-canonical taxonomy class as §C. Recovering narrative-
only rendering would need a space-named-subdir DOCX detector; deferred
(low value — no structured data to present).

## Cumulative parser-robustness scorecard (all 3 uploads, ~113 packages)

| Recovery fix | Packages recovered |
|--|--|
| A1 institution-name cleaner | Ameris, SPG, Valley, ZipHQ (+ all folder-fallback) |
| A2 00_parameters synthesis | Alliant (+ fallback) |
| A3 handoff in 01_evidence | Alliant |
| A4 JSON evidence variants (top-level list, evidence_items, L0) | Rockland, Corporate America, Zions |
| CamelCase run_manifest | Chemung |
| Root-detection (MANIFEST in numbered subfolder) | First Citizens |
| Consolidated XLSX scoring sheet | Zions |
| Misplaced evidence in 03_scoring | First Citizens, Security Finance |
| Case-insensitive verdict fallback | Farm Credit, IBKR, Vornado, ANBTX |

**Genuinely-unrecoverable (no structured data in package):** report-only
DOCX/PNG deliverables (Ameris, SPG, Valley, ZipHQ, IMA, Amegy, AAA,
Navy Federal, Midfirst, YNCU, TBOM, Navacord) — correctly parse to
narrative-only or are flagged as partial.

---

# Addendum (2026-06-07 pm-3): 78 packages committed + deploy-render path + persist hardening

The 78 stress packages are now committed (batches 06-15); the corpus is
**113 real client DMA packages**. Plus a deploy-time local ingestion
path, Drive comments-aware change detection, and persist-layer
truncation hardening surfaced by the full corpus.

## Deploy-time rendering (`historical_backfill --dir`)

New `historical_backfill --dir <path>` mode ingests the committed
corpus into the DB without Drive — deterministic deploy/CI rendering.
IDEMPOTENT + change-aware:
- keyed on `drive_folder_id = "local:{client}"` → re-run upserts, never
  duplicates;
- SKIP when the package's max file-mtime ≤ the prior run's
  completed_at (unchanged since last ingest) — a redeploy does NOT
  re-integrate reports already present + unchanged;
- versioned re-ingest when any file changed.

Verified against the committed corpus on a real Postgres + pgvector +
`alembic upgrade head`:
```
cold run:  98 ingested, 0 skipped, 15 error / 113
warm run:  82 skipped (unchanged), 16 re-ingested*, 15 error / 113
```
*the 16 warm re-ingests + 7 of the 15 errors are **cross-batch
duplicate-client artifacts** of the committed corpus (the same client
appears in two batches → same `local:` key / colliding display_id).
Production Drive has ONE folder per client, so these don't occur there;
the job is resilient (per-package errors are counted, the run exits
cleanly).

## Drive backfill: comments-aware change detection

Per the operator mandate ("the backfill should look for any new changes
or comments that may influence the DMA presentation"), the Drive path
now probes file COMMENTS (`_latest_comment_time`) and folds the latest
comment timestamp into the mtime-based change signal — a reviewer
comment (which does NOT bump file mtime) now triggers a versioned
re-ingest. Best-effort + bounded; a comments-API error never blocks the
backfill.

## Persist-layer truncation hardening (real production bugs)

The 113-package corpus surfaced 3 `StringDataRightTruncation` aborts
(genuine production bugs — would crash a Drive backfill on these
clients):

| Column | Width | Offending input | Fix |
|--|--|--|--|
| `firmographics.primary_regulator` | VARCHAR(64) | Amalgamated/Kitsap multi-agency regulator string | truncate to 64 at persist |
| `evidence_index.linked_subcap_ids[]` | VARCHAR(32)[] | SL Green 525-char / Kitsap 55-char `mapped_subcaps` free text | filter to valid `P#C…` shape AND ≤32 (parser + persist) |
| `evidence_index.e_id` | VARCHAR(16) | Sunflower 58-char malformed id | bound to 16 (parser + persist) |
| `evidence_index.claim_type` | VARCHAR(32) | (defensive) | bound to 32 at persist |

After: **StringData errors 3 → 0**. Pinned by
`test_corpus_evidence_json_bounds_oversized_fields`.

## Known follow-up (documented, not blocking)

Cross-batch duplicate clients in the committed corpus collide on the
entity `display_id` / `drive_folder_id` UNIQUE constraints (7 of 113).
The job handles this gracefully (per-package error, continues). A
collision-safe entity-upsert (disambiguate display_id when the slug
exists under a different folder) would close it but is a deeper
persist-layer change deferred to avoid late-session regression risk.
Production (Drive, one folder per client) is unaffected.

## Cumulative corpus scorecard (113 packages)

- 98 fully ingest (manifest + scoring/evidence)
- 8 report-only deliverables (DOCX + chart PNGs, no structured data —
  not recoverable: IMA, Amegy, AAA, Navy Federal, Midfirst, YNCU,
  The Bank of Missouri, Navacord)
- 7 cross-batch duplicate-client artifacts (resilient, production N/A)

## 100+ DMA presentation summary (live ingest → API)

Full corpus ingested into a real Postgres via `historical_backfill
--dir`, then every entity probed across the client-detail endpoints:

```
PRESENTATION across 85 ingested entities (113 packages; report-only +
dup-client artifacts excluded by ingest):
  overview pillars : 69/85  (81%)
  heatmap (subcap) : 69/85  (81%)
  firmographics    : 69/85  (81%)
  qa_verdict (C5)  : 67/85  (78%)
  caps_applied(C10): 47/85  (55%)
  recommendations  : 21/85  (24%)
```

81% of ingested entities render the core surfaces (overview ScoreRing +
PillarBars, HeatmapPage 698-cell matrix, firmographics) end-to-end on
the real API. QA-verdict chains + cap-event tables populate on the
majority. The lower recs % reflects packages that ship no
recommendations JSON/DOCX-§9 (source-side); evidence + about-narrative
populate per the earlier detailed per-entity probe.

## Deployment rendering — how the DMAs load on deploy

- **Production**: `infra/deploy.sh` post-deploy refresh fires the Drive
  delta backfill (idempotent + now comments-aware) — ingests new/changed
  DMA folders so they render after each deploy without re-integrating
  unchanged reports.
- **Deterministic / CI / offline**: `python -m app.scripts.historical_backfill
  --dir apps/dma-insights/backend/tests/fixtures/dma_packages_batches`
  renders the committed corpus without Drive (same idempotent skip).
