# Overview re-extraction + per-script all-94 safeguard (2026-06-24)

QA pass on the DMA Insights startup pages: align the Overview page to the
uploaded prototype (byte-identical to `docs/wireframe-2026-06/`, md5
`669653622478250d1dbe12aa748cd798`) and fix the extraction/synthesis scripts so
every one of the 94 reports is complete, correct and evidence-grounded.

## What landed

### Safeguard (the per-script, all-94 gate)
- `backend/app/scripts/qa_coverage_contract.py` — single source of truth mapping
  every Overview-surface defect to its **owning script**, with an explicit
  honest-null allowlist (branchless cohorts, assets-vs-revenue, no-creds rosters).
- `backend/app/scripts/qa_startup_audit.py` — stdlib, no-DB scanner over
  `startup-data/clients/*`. Prints a per-script × per-client coverage matrix and
  exits non-zero on any hard-check defect. **Baseline 1002 → 0** hard defects.

### Deterministic enrichment (shared, grounded, no fabrication)
- `backend/app/services/startup_enrich.py` — pure helpers (person-name guard,
  trend/cagr/footprint/branches mining, leadership flags, boilerplate scrub,
  subcap→E-ID map with parent-category broadening, 2-3 paragraph SCQA composer,
  platform opportunity narrative). 14 unit tests in `tests/test_startup_enrich.py`.
- `backend/app/scripts/apply_startup_data_fixes.py` — applies those helpers to the
  committed snapshot (used offline; runs **post-export** in deploy). Enriches
  firmographics (trend/footprint/cagr), leadership flags, why-now/findings
  (boilerplate + evidence + platforms + de-template), SCQA (broken/short →
  grounded paragraphs), opportunity_md + evidence_ids, insight pillar + flag.

### Canonical source fixes (so the DB reparse reproduces it)
- `parsers/dma_package._is_person_name` — reject capability-id / digit-heavy names.
- `scripts/deepen_narrative` — gate the 3 verbatim_quote splices through
  `focus_area_sanity.clean_focus_area`; broaden `_eids_for` to the P#C# parent
  category; regenerate SCQA on broken placeholders (not just length) into 2 paragraphs.
- `parsers/report_synthesis._label` — never emit a blank-name `(2.8)` placeholder.

### Frontend (Overview surfaces the enriched data)
- `ClientOverviewPage` opportunity cards render `opportunity_md` + evidence count;
  leadership panel renders the `critical_role` KEY SEAT badge and the `tenure` field.
- Firmographics (trend/footprint/cagr/scale-basis), findings (`platforms`/evidence)
  and the InsightModal (`pillar`/`flag`) already consume the new fields.

## Deploy reparse sequence (all 94, with the gate)
```bash
docker compose -f apps/dma-insights/docker-compose.yml up -d
cd backend && alembic upgrade head
python -m workers.ccg_loader --version v7.0 --workbooks-dir docs/reference/catalogue/v7.0/
python -m app.scripts.historical_backfill --dir backend/tests/fixtures/dma_packages_batches --force
DMA_SEED_CORPUS_DIR=backend/tests/fixtures/dma_packages_batches python -m app.scripts.run_derive_chain
python -m app.scripts.export_startup_pages --verify
python -m app.scripts.apply_startup_data_fixes          # post-export deterministic enrichment
python -m app.scripts.qa_startup_audit                  # per-script × 94 gate — must be 0 hard defects
# (with Vertex/Clay creds) python -m app.scripts.enrich_corpus \
#     --surfaces why_now,platform_story,firmographics_extraction,leadership_extraction
```
`apply_startup_data_fixes` is idempotent; run it before/after each script change and
re-run `qa_startup_audit` to confirm all 94 stay covered.

## Remaining (needs deploy env / larger scope)
- **Gemini/Clay layers** (this env has no creds): empty leadership rosters (24/94),
  per-leader titles/background, thought-leadership (0/94), revenue mining — wire the
  persisted `leadership_extraction` / `firmographics_extraction` / `platform_story`
  surfaces in `intelligence_builder` + `enrich_corpus` so the reparse fills them.
- **Full 1:1 overlay rebuild** — EvidenceDrawer (`.tier-T1..T8`, `.drawer-mask`),
  4-tab InsightModal, 3-tab RecommendationModal + DependencyMap, IntelligencePanel
  `.ip-foot` against the prototype `04_components_c.js` (per `FRONTEND_FIDELITY_AUDIT_2026-06.md`).
- Extend `deploy_parity_gate.py` to import the same `qa_coverage_contract` for the
  DB-side gate (the no-DB `qa_startup_audit` is the primary enforcement today).
