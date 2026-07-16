# Production readiness — DMA Insights

What's CI-ready today and what still needs live-IO wiring before the
first production deploy.

Last updated: 2026-05-20.

## CI-ready right now (commit `aa07d33+`)

These are exercised by tests in this repo and run cleanly without any
external service.

| Area | Status | Tests |
|---|---|---|
| Alembic migrations (14 files) | ✅ Round-trip clean against pg-dialect | 122 DDL stmts, single linear head |
| FastAPI app boot | ✅ 45 routes registered | smoke test in `pytest` |
| Auth — admin allow-list, role hierarchy, role-at-least | ✅ | `test_auth` (12) |
| Audience strip (D5/D6 + nested) | ✅ | `test_audience_strip` (5) |
| Grounding validators (V1-V3 regex + DB-existence) | ✅ | `test_grounding_validator` (8) |
| Catalogue resolver (alias bridge + Redis cache) | ✅ | direct unit + integration shape |
| Catalogue loader (parsers + validators + diff + alias bridge) | ✅ Logic; live ingest pending real workbook upload | `test_ccg_loader` (13) |
| Scoring workbook parser (LLM column-map cache) | ✅ | `test_scoring_workbook` (16) |
| Research workbook parser | ✅ | `test_research_workbook` (8) |
| Evidence handoff JSON parser | ✅ | `test_evidence_handoff_parser` (5) |
| Assessment report DOCX section parser | ✅ | `test_assessment_report_parser` (12) |
| Drive crawler dispatch table | ✅ | `test_drive_crawler_dispatch` (7) |
| Sheet poller normalization handlers | ✅ Pure | `test_sheet_poller_handlers` (16) |
| Embedder service (candidate selection + batching + vector validation) | ✅ Pure | `test_embedder_service` (19) |
| Heatmap aggregator (4 zoom levels) | ✅ | `test_heatmap_aggregator` (10) |
| Platform fit + readiness + routing | ✅ | `test_platform_*` (20) |
| Stairstep (per-pillar cumulative uplift) | ✅ | `test_stairstep` (8) |
| Pattern recognition (vector similarity + cohort weighting) | ✅ Pure helpers; live cosine ranking pending pgvector data | `test_pattern_recognition` (9) |
| Pattern drift (per-subcap + per-pillar drift buckets) | ✅ | `test_pattern_drift` (8) |
| Cross-pillar story aggregation | ✅ | `test_cross_pillar` (8) |
| Value-chain clustering (stage/capability/platform-area) | ✅ | `test_value_chain` (11) |
| Gemini orchestrator (fail-closed fallback + cache key) | ✅ Pure with injected SDK | `test_gemini_orchestrator` (8) |
| SSE channel formatter | ✅ | `test_sse_format` (3) |
| Section routing | ✅ | `test_section_routing` (8) |
| Frontend chrome (Sidebar/TopBar/AudienceToggle) | ✅ | utils + AudienceToggle (16) |
| Pages: Dashboard, Directory, ClientOverview, Insights, Heatmap, Platform, Context, Health, TechStack, Alerts, Admin, Login | ✅ Live | wireframe-completeness + a11y (13) |
| AI surfaces: PatternBadge, RecurringThemesBadge, DriftBadge, IntelligencePanel, StairstepCurve, RecommendationModal, CrossPillarBadge | ✅ Wired | per-component (32) |
| Color encoding (ADR 0008) — maturity hex, peer-delta arrow, freshness | ✅ Locked | `maturity.test.ts` (14) |
| Catalogue naming (ADR 0009) — capability/platform_area not L1/L3 | ✅ Locked | grep audit + value_chain tests |
| Hash router round-trip | ✅ | `hash-router.test.ts` (8) |
| Audience helpers | ✅ | `audience.test.ts` (4) |
| Evidence tier helpers | ✅ | `tiers.test.ts` (5) |
| a11y — zero critical/serious WCAG 2.1 AA on key pages | ✅ | `a11y.test.tsx` (7) |
| Standalone single-file build | ✅ | `pnpm run build:standalone` → 280 kB inlined index.html (gzip 83 kB) |
| Wireframe-completeness QA (no dummy/TBD/TODO leaks) | ✅ | `wireframe-completeness.test.tsx` (6) |

**Totals**: 314 backend tests + 110 frontend tests + ruff clean +
tsc clean + 45 backend routes + 12 frontend pages.

## Pending live IO wiring (Cloud Run deploy work)

These boundaries are deliberately stubbed so the pure logic is testable
without external services. Each has a `--dry-run` or injectable callable
demonstrating the call site.

### 1. Drive v3 + GCS clients

- **Where**: `workers/drive_crawler/main.py`, `workers/ccg_loader/main.py`
- **Stubbed via**: `--dry-run` flag prints config + describes the
  next-step path.
- **Needs**: Google Drive service account in Secret Manager
  (`dma-insights-drive-sa-key`), GCS reader for the v7.0 catalogue
  workbooks bucket.
- **Wired through**: the existing dispatch table + parsers; no new code
  required, just SDK initialization in `main.py`.

### 2. Live Vertex SDK call sites

- **Where**: `app/services/vertex_client.py` (already lazy-init), used
  by `workers/embedder/main.py` and the Gemini orchestrator.
- **Stubbed via**: VertexClient.stream() and embed() raise
  ImportError if the SDK isn't installed; tests inject fake
  callables.
- **Needs**: `google-cloud-aiplatform` package + Vertex AI service
  account in Secret Manager (`dma-insights-vertex-sa-key`).
- **Verification**: a live `--dry-run` against text-embedding-004
  on a single test document confirms the round-trip.

### 3. Google Sheets v4 client for Ops Sheet poller

- **Where**: `workers/sheet_poller/main.py`
- **Stubbed via**: prints the configured sheet ID + tabs and exits.
  Pure normalizers in `./handlers.py` are fully tested (16 cases).
- **Needs**: Sheets v4 client + the same Drive service account
  (Sheets API enabled on the GCP project).

### 4. Pub/Sub subscription for ingest → embedder fanout

- **Where**: ingest router (`routers/ingest.py`) marks a TODO at the
  bottom of `ingest_assessment` to "emit Pub/Sub event so embedder
  worker picks this up."
- **Stubbed via**: ingest still UPSERTs synchronously; the embedder
  can be run manually with `--run-id` until the trigger is in.
- **Needs**: Pub/Sub topic `dma.ingest.completed` + Eventarc
  subscription on the embedder Cloud Run Job.

### 5. Cloud Run Job manifests

- **Where**: `infra/terraform/` (skeleton, not in this repo yet).
- **Needs**: Terraform manifests for 4 Cloud Run services (frontend,
  backend, RAG read API, worker pool) + 3 Cloud Run Jobs
  (drive_crawler, sheet_poller, embedder, ccg_loader) + Cloud
  Scheduler triggers (6h Drive crawl, 5min Sheet poll during business
  hours).

### 6. Playwright PDF export

- **Where**: not in repo yet — `apps/dma-insights/backend/jobs/pdf_export.py`.
- **Needs**: Playwright + a CSS print stylesheet variant.

## Smoke-test runbook for first deploy

Once the boundaries above are wired:

```bash
# 1. Boot local services
docker compose -f apps/dma-insights/docker-compose.yml up -d

# 2. Migrate
cd apps/dma-insights/backend && alembic upgrade head

# 3. Load v7.0 catalogue
python -m workers.ccg_loader --version v7.0 \
    --workbooks-dir docs/reference/catalogue/v7.0/

# 4. Boot the API
uvicorn app.main:app --reload --port 8000

# 5. Frontend
cd ../frontend && pnpm dev   # → http://localhost:5173

# 6. End-to-end:
#    - Sign in with @zennify.com Google account
#    - Click "+ Request DMA"; observe REQ-{8 hex} + Ops sheet link
#    - Visit /clients/fce-001/overview → live pillar bars + DriftBadge
#    - Visit /clients/fce-001/heatmap → 4-zoom heatmap with peer overlay
#    - Visit /clients/fce-001/platform → 5 platform cards + stairstep
#    - Click a stairstep step → RecommendationModal opens with cited refs
```

## Confidence summary

- **Pure logic** (parsers, services, validators, schemas, encoders):
  100% covered. Every state branch documented in module docstring +
  exercised by tests.
- **API contract**: 45 routes registered + Pydantic round-trip tests on
  every request/response shape.
- **UI dynamic behavior**: 12 pages with documented render-state
  matrices + wireframe-completeness QA asserting no dummy leaks.
- **Accessibility**: WCAG 2.1 AA — zero critical/serious violations on
  Sidebar / TopBar (both audiences) / Modal / Dashboard / ClientOverview
  / AlertsPage.
- **Visual encoding**: maturity color palette + peer-delta arrow
  convention + freshness ladder all locked in ADR 0008 with 14 tests.
- **Live IO**: stubbed at every external boundary with documented
  call-site contract + injectable callables for tests.
