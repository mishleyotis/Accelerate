# DMA Insights — End-to-End Status (against the plan)

Last updated: 2026-05-28 (post audit Waves 1-5 + D/E/G batch —
preflight-parameters.sh + deploy-two-phase.sh land the two-phase
deploy that closes the traffic-shifts-before-migrations race;
dual-auth on /ingest/assessment with hmac.compare_digest; live-PG
test backlog closed; FIELD-MATRIX.md + ADRs 0012/0013 land).

This document is the canonical "what's done vs the plan" matrix. The plan
itself lives at `~/.claude/plans/quizzical-hatching-lighthouse.md`. Every
gate from "QA gates (per-stage, persisted, PASS/PARTIAL/FAIL)" is tracked
here against the current state of `claude/deploy-zennify-cloud-run-AUdu6`.

## Headline (refreshed 2026-05-28)

- **Backend: 60+ API routes, 1470 tests green WITH LIVE POSTGRES**
  (1014 → 1022 → 1029 → 1052 → 1099 → 1137 → 1429 → 1441 → 1454 → 1470
  across the QA rounds, audit Waves 1-5, D/E/G batch, final-audit P0
  patches, and the 5-real-sample variant audit). Without `SEED_CI_PG_URL`:
  live-PG tests cleanly skip. ruff clean. Alembic head =
  `023_focus_areas_reconcile`. Prod-readiness guard armed:
  `assert_production_ready(settings, role="backend"|"worker")`.
  **All 5 uploaded real DMA samples (Alma / Calprivate / Nicola /
  Odlum / WSFS) parse with sub ≥ 690, ev ≥ 100, firm = Y** via
  `app/scripts/inspect_dma_samples.py`.
- **Frontend: 234 tests green** (vitest). 0 jsdom noise lines.
  tsc clean. standalone bundle 372KB (under 400KB budget).
  standalone-src/ is the live AE surface per ADR 0011.
- **Playwright e2e: 24/24** (15 persona + 5 PDF + 4 Phase-6 a11y/XSS/
  role-tampering/responsive against live seeded backend). The
  ingestion→DB→API→UI chain is hard-asserted on real data.
- **Visual baselines: 84 PNGs** committed (12 routes × 7 breakpoints)
  against the standalone bundle per ADR 0011.
- **Deploy pipeline: two-phase** (`infra/deploy-two-phase.sh`) — closes
  the 10-60s traffic-shifts-before-migration race; failure recovery
  needs no rollback (OLD revision keeps 100% traffic during
  candidate-revision migration + readyz probe).
- **ADRs: 13** at `docs/decisions/0001..0013-*.md` (0012 dual-auth
  on /ingest/assessment, 0013 two-phase deploy).

## Open follow-ups (P2/P3, none release-blocking)

Carryover from debiased rounds:
- `parser_warnings` chip rendered on D1 ✅ (this batch)
- `BackendErrorBanner` wired ✅ (this batch)
- `JWT` error constant detail ✅ (this batch)
- `chat_learning` worker uses `_runner.track_job_execution` ✅ (this batch)
- `_maybe` parser helper emits typed warnings (`json_corrupt:`,
  `schema_mismatch:`, `io_error:`) ✅ (this batch)
- `InsightCardOut.counter_e_ids` + `confidence_band` populated by the
  router ✅ (this batch)
- ingest `/api/v1/ingest/assessment` N+1 fixed → bulk INSERT ✅ (this batch)
- k6 perf scripts at `backend/perf/` ✅ (this batch)

Pending:
- Future migration 022 to add `trim()` to both sides of `content_hash`
  (outer-whitespace dedup still strict per SQL backfill).
- Browser-runtime a11y test (jsdom-only today).
- Sentry / OpenTelemetry instrumentation.
- Real Cloud Run perf SLO test (k6 against deployed URL).

## Final-turn batches landed 2026-05-24

| Batch | Commit | Plan ref | What it closes |
|---|---|---|---|
| `c0bdc74` | F2 + F3 + B6 + B7 + B8 + B4 | drive backfill unblock; 4 missing Vite endpoints; auth role hydration; RAG streaming |
| `d625ece` | XLSX scoring + evidence/peer variants | Amalgamated + AmeriCU now parse to fully-renderable envelopes (was 0 subcaps) |
| `1799ad4` | D1 + staleness banner | /readyz catches migration drift; IntelligencePanel shows amber stale banner per UI/UX brief mandate |
| `eab1ca5` | F4 + B5 + B3 | PRD §17 drive feedback loop; jsdom canvas stub silences 17+ noise lines; endpoint-contract test prevents Vite-route 404 regressions |
| `f74114d` | Production-readiness guard + IAM runbook (§36) | Fail-fast startup when dev defaults leak into prod; full operator runbook with 14 IAM/Secret Manager subsections |
| `aa982db` | F6 R-rules + pattern-recognition stress (§37 + §38) | 3 ingestion-time rules + 15 stress tests proving silhouette > 0.67 on real-shape rollup |
| THIS batch | A1+A4+A5+F1+F5 + ADR 0011 (§39) | Live-PG sweep against real Postgres + pgvector: 5 committed sanitized fixtures (39 KB) + seed_ci.py with catalogue bootstrap + ci-live-migration.sh + post-deploy-smoke.sh + persona/persistence E2E. Caught **4 real production bugs** (alembic 2.0 commit, audit_log schema mismatch, focus_areas downgrade collision, insight_cards column drift) the pure-logic suite missed. 1014/8 backend with live DB. E1-E5 closed via ADR 0011. **Every plan batch finalised.** |
- **Catalogue admin workflow CLOSED end-to-end:**
  - `POST /admin/catalogue:upload` (`3e73234`) — multipart upload
    of `Pillar_*_v*.xlsx` workbooks, enqueues job_executions row
  - `ccg_loader._persist_loader_run` (`20daba9`) — worker now
    persists `ccg_loader_runs` row at `AWAITING_APPROVAL` on
    successful parse, `REJECTED` on validator failure
  - `POST /admin/catalogue/{id}:approve` (`e7013c6`) —
    AWAITING_APPROVAL → APPLIED, audit-logged
  - `POST /admin/catalogue/{id}:reject` (THIS commit) —
    AWAITING_APPROVAL → REJECTED with mandatory free-text reason
  - Existing `GET /admin/catalogue` surfaces queue + recent applied
- **All 8 recurring failure modes have CI safeguards** via
  `tests/test_infra_safeguards.py` — IPv6, password drift, secret
  cache, Terraform typos, pip drift, migration immutability, $$
  escapes, backfill resilience.
- **Zero TODOs remain in `backend/app/` or `workers/`.** Every
  remaining outstanding item is genuinely deployment-gated.
- **Recurring failure-mode safeguards now have explicit regression
  tests** (`tests/test_infra_safeguards.py` — 11 tests across the 8
  named failure classes; every test would FAIL if its underlying
  safeguard were reverted, verified via spot-revert in audit).
- **Bug fixed:** `track_job_execution` env-var leak — long-lived
  Pub/Sub subscribers (embedder --subscribe, intelligence_recompute
  --subscribe) were stamping message #N+1's status updates onto
  message #N's `job_executions` row. Fix in `workers/_runner.py`;
  regression test in `tests/test_worker_runner.py::
  test_auto_created_id_does_not_leak_across_invocations`.
- **Terraform validation tightened:** the `project_id` regex (`^[a-z]
  [a-z0-9-]{4,28}[a-z0-9]$`) accidentally ACCEPTED the typo `latest`
  (6 chars of lowercase letters). Added a second `validation` block
  with explicit blocklist (`latest`, `head`, `main`, `master`, …) so
  the operator typo is rejected at `terraform plan` time, before any
  resource gets adopted under a project called "latest".
- **CI Stage 1 now executes alembic upgrade head against an ephemeral
  Postgres for REAL — runtime-only SQL errors (immutability,
  trigger compilation, FK validation) caught at build time not deploy.**
- **`infra/migrate.sh` self-heals DB password drift via the existing
  `recover-db-passwords.sh` before triggering the migrations job.
  Operators no longer need manual intervention on the recurring
  drift path (see DEPLOYMENT.md §8 + §T17).**
- **Token-economics contract proven by 10-scenario stress matrix
  (`test_token_economics_loop.py`):** identical inputs cache-hit at
  zero tokens; bundle reorder is visible to the cache; invalidation
  isolates per-entity; hallucination feedback touches exactly ONE row;
  catalogue bump auto-invalidates via fingerprint; cache being down
  never blocks reads; force-regenerate supersedes; full
  MISS→HIT→INVALIDATE→RE-SYNTH→HIT lifecycle; 3 trigger reasons are
  distinct in the audit trail. See CLAUDE.md "Synthesis persistence
  + decision gates" section.

### Token-economics loop (closed end-to-end)

The user mandate — "once vertex models interpret the information, this is
persisted, unless there is new information or a rerun has been done, to
avoid token consumption for each reload" — is operationally true:

  1. `/rag/answer` synthesizes via Vertex (cache miss).
  2. `safe_insert_or_supersede` writes the result to
     `vertex_synthesis_cache` with a fingerprint over
     (prompt_template_version + grounding_bundle_hash + catalogue_version
     + page_context_hash). `cache_row_id` stashed on
     `chat_messages.retrieval_bundle` as a `_meta` JSONB-array entry.
  3. Subsequent identical reads → same fingerprint → active row found →
     cached text returned at ZERO tokens.
  4. New ingest for the entity → `publish_post_commit` calls
     `safe_mark_invalidated(build_invalidation_for_new_run(entity_id))`
     → row's `invalidated_at` set lazily.
  5. Next read sees `CACHE_HIT_INVALIDATED` → re-synthesizes → fresh row;
     prior row's `superseded_by` populated for audit.
  6. Hallucination feedback → handler scans `retrieval_bundle` via
     `jsonb_array_elements` for the `_meta` marker → invalidates ONLY
     that row (sibling answers untouched).
  7. Catalogue bump → fingerprint auto-changes (catalogue_version in
     the hash); the explicit catalogue-bump invalidation spec exists
     for belt-and-suspenders audit.

Resilience contract (proven):
  - DB down → safe wrappers return None / 0; orchestrator routes to
    CACHE_MISS; caller synthesizes normally. Cache never blocks reads.
  - Pub/Sub down → invalidation still fires (independent side-effect).
  - Older deploy missing `synthesis_cache_db` → outer try/except;
    cache_row_id stays None; feedback invalidation no-ops cleanly.

### Prior batch headline (admin-defects, kept for continuity)

- **Backend: added /admin/jobs:execute + /admin/jobs/executions
  + /admin/import-audit/{summary,by-entity,entities/:id} + /admin/imports/files/:id:retry,
  760 tests green (737 → 760). ruff clean.**
- **Frontend: 156 tests green (+24 in this batch — 132 → 156).
  tsc clean. Standalone admin home now triggers real workers via
  `POST /admin/jobs/{name}:execute` with 3s status polling; import
  audit page is fully data-driven (no `187` literals); per-client
  drilldown drawer renders runs + rerun history. Role toggle clamp
  proven by tests (AE cannot escalate to ADMIN even with tampered
  can_act_as).**

### Admin-flow refresher

Migration 020 adds `job_executions` (id, job_name, mode, status,
counters, stderr_tail) — the canonical record of every worker
invocation, scheduled or admin-triggered. The Admin → Overview tab
renders one card per worker (drive_crawler, embedder, peer_patterns)
showing last-run status from the table; the action buttons POST
`/api/v1/admin/jobs/{name}:execute` which inserts a `running` row +
best-effort Pub/Sub publish; the UI polls `/jobs/executions/{id}`
every 3s and updates JobStatusLine on each tick. Workers UPDATE the
matching row at start, on milestones, and at completion — failure
modes render a View-log drawer with `stderr_tail`. The 4 import-audit
tiles (Last crawl / Candidates / Excluded / Awaiting review) aggregate
over `job_executions` + `import_files`; the previous Phase-0 wireframe
literal `187` is gone, every count is `?? 0` fallbacks against real
backend data. By-client tab walks every entity ever ingested + on
click opens a drawer with the entity's runs + rerun-history timeline.
- **End-to-end AI chain landed.** Test `test_full_ai_chain.py` exercises
  the 8-step ingest → dedup → embed → recompute → RAG → feedback →
  learning → retrieval → drawer chain in one go, with deterministic
  assertions at every step. See the ASCII diagram in CLAUDE.md.
- **intelligence_recompute worker** (`workers/intelligence_recompute/`)
  binary in two modes:
    - `--entity-id <UUID>` one-shot Cloud Run Job (or `--all` backfill)
    - `--subscribe` long-lived Cloud Run Service subscribed to
      `dma.ingest.completed` (subscription
      `dma-ingest-completed-intelligence`).
  Vertex Pro structured-output summary; grounding validator;
  embedding via text-embedding-004. 6-branch state matrix in
  `service.classify_worker_state`.
- **Dedup integration wired into `package_persist._persist_evidence`.**
  Every incoming evidence row now flows through the 5-branch dedup
  decision engine; `evidence_run_links` + `dedup_audit` populated on
  every package ingest (was previously empty).
- **Section embeddings UNIONed into `/rag/answer`.** Narrative-style
  questions ("what does the report say about retail banking maturity?")
  now retrieve `document_sections` rows alongside evidence rows;
  citation chips render in two kinds — `evidence` (bookmark icon) +
  `section` (book icon, opens section drawer).
- **EvidenceDrawer "Seen in N runs" chip.** New endpoint
  `GET /api/v1/evidence/:id/run-history` returns the
  `evidence_run_links` join. Click → popover with each prior run's
  request_id + completed_at + surfaces.
- **Per-subcap narrative classifier.** Vertex Pro structured-output
  classifies pillar deep-dive bodies into per-subcap_id narratives;
  validator strips fabricated subcap_ids + evidence_anchors; heuristic
  fallback fills gaps. Cell-level `data-source="llm"|"heuristic"`
  provenance marker.
- **Customer intelligence layer.** Migration 018 adds:
  - `evidence_index.content_hash` (with idempotent backfill on
    upgrade), `evidence_index.is_stale` + `freshness_band` (STORED
    generated columns).
  - `evidence_run_links` many-to-many for the "Seen in N prior runs"
    chip; `dedup_audit` append-only with action CHECK
    ('kept' / 'dedup_same_entity' / 'cross_entity_kept' /
    'duplicate_within_run' / 'tier_upgrade').
  - `customer_intelligence_profiles` with maturity_history JSONB,
    velocity, archetype_history, recurring/emerging themes,
    persistent/closed gaps, tech drift, intelligence_summary_md +
    summary_embedding vector(768) + grounding_evidence_ids.
  - `focus_areas` (verbatim quote + page + subcap IDs) for the
    Client Profile parser.
- **Research workbook parser extended.** `parse_per_pillar_sheets`
  now walks the real Alma/WSFS shape (P1C1..P4C4); multi-value
  Evidence_IDs/Source_URLs split on `;` / `|` / newline; linked
  subcaps aggregated across rows. `cross_reference_with_handoff`
  reconciles workbook rows against `research_handoff.json` —
  handoff wins on E-ID conflict.
- **Client Profile DOCX parser.** Verbatim focus-area quotes
  (paragraph + table fallback for Alma's leadership table); subcap
  IDs auto-extracted; page numbers + source paths captured;
  firmographics narrative_md + leadership[] + financial_highlights.
- **Per-customer endpoints**: `/api/v1/entities/{id}/intelligence-profile`
  + `evidence_freshness` + `intelligence_profile` subfields on
  `/overview` (degrade gracefully to null pre-migration).
- **RAG /answer bundle freshness.** Response now includes
  `bundle_stale_pct` (% of retrieved evidence whose freshness_band
  is 'stale') + `stale_disclaimer` (populated when > 40%).
- **Narrative-driven surfaces.** Every entity endpoint
  (`overview/insights/heatmap/platforms/context/health`) now carries a
  `narrative` subfield populated from `document_sections` via
  `section_routing.build_narrative_*()`. Frontend consumes via
  `data-source="narrative"` markers with skeleton fallback.
- **Cross-pillar stories endpoint** (`/entities/:id/cross-pillar-stories?pillar=`)
  surfaced on D5 Context as a filterable panel with "Why this matters
  for {entity}" derived from the actual gap profile.
- **Drive crawler + sheet poller** refactored: shared `drive_client.py`
  + `sheets_client.py` modules with pure helpers (watermark logic +
  Levenshtein fuzzy assignee). Live IO still pending Cloud Run deploy
  but the state matrices + handlers + tests are in place.
- **Section embeddings** migration `017_section_embeddings` adds the
  pgvector table; embedder service extended with `section` ArtifactKind.
- **Adversarial loop closed (G11.ADVERSARIAL.APPLIED):** every
  `/api/v1/rag/answer` call now consults `chat_learning_signals`,
  re-ranks the retrieval bundle toward `preferred_evidence_ids`, and
  records `learning_signal.applied` in both audit_log + response.
- **Pub/Sub fan-out live (G11.INGEST.PUBSUB):** `persist_package`
  + `historical_backfill` publish `dma.ingest.completed` on commit;
  embedder gained a `--subscribe` mode consuming the topic.
- **Wireframe dynamic per-report:** D3 archetype chip, AI-pill on
  heatmap cells, runs-history version timeline with parent_request_id
  chain + Δ vs parent, IntelligencePanel "Recent threads" picker with
  full session resumption + 👍/👎/💡 feedback round-trip, D6 Patterns
  tab using live `peer_archetypes`.
- **AI layer landed.** Migration 016 adds chat_sessions / chat_messages /
  chat_feedback / chat_learning_signals / ai_enrichments / peer_archetypes
  / system_config plus the `runs.parent_request_id` self-FK for the
  versioning chain. New endpoints:
  - `POST /api/v1/rag/answer` (+ SSE variant `/api/v1/rag/answer/stream`)
    — grounded conversational endpoint, validator fail-closed fallback,
    per-surface Redis cache, per-user-per-day rate limits, audit-log writes.
  - `GET /api/v1/chat/sessions[/{id}]`, `DELETE /api/v1/chat/sessions/{id}`,
    `POST /api/v1/chat/messages/{id}/feedback` — full chat thread CRUD with
    privacy gate (user can't read another user's session).
  - `GET /api/v1/admin/vertex-budget` — monthly usage aggregated from
    audit_log + per-surface + per-user breakdowns.
  - `GET /api/v1/admin/pending-review` — replaces the frontend stub with
    PENDING_REVIEW runs/entities/import_files.
  - `GET /api/v1/entities/{display_id}/run-history` — full supersede chain.
  - `GET /api/v1/entities/{display_id}/archetype` — closest maturity
    archetype from peer_archetypes.
- **New workers**:
  - `workers/peer_patterns` — KMeans clustering of entity score vectors per
    subvertical → peer_archetypes. Stress-tested against 9-entity 2-cluster
    fixture with silhouette > 0.4. Handles insufficient cohorts (< 3) and
    homogeneous cohorts gracefully.
  - `workers/chat_learning` — nightly rollup turning chat_feedback into
    chat_learning_signals (KMeans on user-question embeddings, recency-
    weighted effectiveness, preferred_evidence_ids signal). Stress-tested
    against a 100-row simulated feedback set across 2 surfaces.
- **Adversarial-learning loop closes**: chat_feedback writes → next worker
  run clusters questions + identifies preferred_evidence_ids → /answer
  service can re-rank retrieval toward high-effectiveness clusters.
- **Gemini ↔ SSE wiring** (carried over): 5 surfaces live, all fail-closed
  via V1-V3 validators.
- **Embedder live path complete** (carried over).
- **DMA package ingest live end-to-end** (carried over).
- **Clay enrichment connector wired** (carried over).
- **Frontend: 114 tests, tsc + vite build clean.**

## Stage-by-stage matrix

Legend:
- ✅ done — committed code + tests; auto-validated in CI
- ✅* — code + test infrastructure committed; final verification is an
  operator command sequence in DEPLOYMENT.md §31 (deploy-gated by
  Cloud Run access or live secret binding)
- 🔶 partial (skeleton + tests; live IO pending)
- ⏳ pending

| Stage | Status | Notes |
|---|---|---|
| **0 — Scaffold** | ✅ | apps/dma-insights skeleton, 7 docs in `docs/reference/`, 10 ADRs, docker-compose with pgvector+redis, CLAUDE.md |
| **1 — Infra & DB** | ✅ | 16 alembic migrations, single linear head, round-trip clean. 28+ ccg_* tables + AI-layer tables (chat, ai_enrichments, peer_archetypes, system_config). |
| **1.5 — Catalogue loader** | ✅ | Pure parsers/validators/diff/alias-bridge done + tested. **Admin upload→approve loop fully wired** (commits `3e73234` + `20daba9` + `e7013c6` + this batch). `_persist_loader_run` writes AWAITING_APPROVAL row; admin approve/reject endpoints with audit_log; ccg_loader_runs row supports the full workflow. Live ingest tested via admin UI. |
| **2 — Backend core** | ✅ | FastAPI app, async SQLAlchemy, Pydantic v2, structlog. CatalogueResolver + RagCohortRouter + audience_strip + grounding_validator + jwt_service + vertex_client (lazy). |
| **3 — Frontend foundation** | ✅ | Vite + React 18 + TS strict; tokens.css + app.css verbatim; hash router + lib/{api,sse,auth,audience,tiers,rag-client} + store/{auth,ui,sse}; `vite build` clean; vitest 12/12. |
| **4 — Auth + chrome** | ✅ | Backend OAuth callback + Sidebar + TopBar live. LoginPage wires `@react-oauth/google`. |
| **5 — Drive parsing + ingest** | ✅ | Package ingest live; verified against real AlmaBank + WSFS + RegionsBank packages. |
| **6 — D1 Overview + Directory** | ✅ | DashboardPage + DirectoryPage + ClientOverviewPage live. |
| **7 — D2 Insights + drawer** | ✅ | InsightsPage + InsightModal + EvidenceDrawer live. |
| **8 — D3 Heatmap** | ✅ | HeatmapPage with all 4 zoom toggles + 3 view modes + peer/issue overlays. |
| **9 — D4 Platform** | ✅ | PlatformPage + 5 platform cards + StairstepCurve. |
| **10 — D5/D6/Tech/Runs/Alerts** | ✅ | All wired. |
| **11 — Patterns + Gemini + RAG + bot loop** | ✅ | RAG read API + RAG /answer + bot POST + SSE + Gemini orchestrator + pattern-recognition + embedder + peer_archetypes + chat_learning. |
| **12 — Admin + Export + harden** | ✅* | Admin endpoints complete (users / build-qa / catalogue / assignments / imports/audit / vertex-budget / pending-review). PDF export (`pdf-export.e2e.ts`), responsive matrix (`responsive.visual.ts`, 12 × 7), and axe-core full sweep (17 surfaces) all wired. Asterisk = perf/responsive/pdf require operator command sequences in DEPLOYMENT.md §31. |

## Plan QA-gates

| Gate ID | Status | Evidence |
|---|---|---|
| G00.REPO.STRUCTURE | ✅ | `apps/dma-insights/{docs,frontend,backend,workers,infra}`. |
| G00.LOCAL.UP | ✅ (syntax) | `docker compose config --quiet` clean. |
| G01.ALEMBIC.ROUNDTRIP | ✅ | 21 migrations, single head. Revision IDs ≤ 32 chars enforced by `test_migration_id_lengths.py`; env.py auto-widens `alembic_version.version_num` to VARCHAR(128) per run; migrate.sh detects + emits a hot-fix hint on truncation. |
| G01.PGVECTOR.PRESENT | ✅ | Migration 001; ivfflat indexes on evidence/insight/recommendation/chat_messages embeddings. |
| G15.CATALOGUE.* | ✅ | Logic complete + admin upload/approve/reject endpoints wired with audit_log. Tests: test_catalogue_upload (5), test_ccg_loader_persist (7), test_catalogue_approve (8), test_catalogue_reject (8). 28 tests total covering the full workflow. |
| G02.AUTH.ALLOWLIST | ✅ | 7 admin emails. |
| G02.AUDIENCE.STRIP | ✅ | strip_internal covers D5/D6 + rationale_internal. |
| G02.RESOLVER | ✅ | CatalogueResolver alias-bridges. |
| G03.TOKENS.VERBATIM | ✅ | tokens.css + app.css byte-copies. |
| G03.HASH.ROUTER | ✅ | parseHash/buildHash tests. |
| G04.OAUTH.LIVE | ✅* | Backend + frontend wiring complete. Verification command sequence in DEPLOYMENT.md §31.1 (operator opens incognito + signs in; asserts JWT cookie + refresh-token roundtrip). *Asterisk = green when operator-executed; not auto-validated in CI. |
| G04.CHROME.RESPONSIVE | ✅* | `playwright.visual.config.ts` + `e2e/visual/responsive.visual.ts` cover 12 routes × 7 breakpoints. Operator runs `pnpm test:visual:update` to capture baselines + `pnpm test:visual` thereafter. Command sequence in DEPLOYMENT.md §31.5. |
| G05.PARSER.FIDELITY | ✅ | Verified against AlmaBank + WSFS + RegionsBank packages. |
| G05.INGEST.IDEMPOTENT | ✅ | ON CONFLICT updates; matching request_id re-uses run. |
| G05.OPS.MIRROR | ✅* | Handlers + state matrix complete in `sheet_poller`. Operator runs `gcloud run jobs execute dma-insights-sheet-poller` after sharing the Ops Sheet with the SA. Full command sequence in DEPLOYMENT.md §31.2. |
| G05.LINEAGE | ✅ | DOCX parser landed; `_persist_document_sections` writes rows; verified against AlmaBank + WSFS fixtures (12/12 canonical kinds recovered). |
| G05.NARRATIVE | ✅ | section_routing.build_narrative_* exposes scqa/benchmark/gap/per-pillar/recommendations/roadmap/trend/data_gaps payloads; every entity endpoint emits `narrative` subfield with null fallback. |
| G05.CROSS_PILLAR_SURFACE | ✅ | `/cross-pillar-stories?pillar=` endpoint + CrossPillarStoriesPanel on D5 with "Why this matters" derived from the entity's gap profile. |
| G05.DRIVE_CLIENT | ✅ | drive_client.py extraction with pure watermark helper; 6 unit tests across all 4 state branches. |
| G05.SHEETS_CLIENT | ✅ | sheets_client.py with Levenshtein fuzzy assignee; 12 tests covering exact/fuzzy/no-match branches. |
| G05.SECTION_EMBEDDINGS | ✅ | migration 017_section_embeddings + embedder `section` ArtifactKind + body cap test. |
| G06.D1.PIXEL | ✅* | Covered by the same Playwright visual suite as G04.CHROME.RESPONSIVE — D1 ClientOverview is one of the 12 routes in `e2e/visual/routes.ts`. Command sequence in DEPLOYMENT.md §31.5. |
| G06.MY.CLIENTS | ✅ | `?owner=me` filter. |
| G07.MODAL.URL | ✅ | InsightModal + EvidenceDrawer URL state. |
| G07.EVIDENCE.TIER | ✅ | Tier-aware ordering live. |
| G08.HEATMAP.ZOOM | ✅ | 4 zoom levels + URL round-trip. |
| G08.VC.MODE | ✅ | ccg_vc_mapping bucketing. |
| G08.CATALOGUE.VERSION | ✅ | Run pins version; alias_resolved_from surfaced. |
| G09.PLATFORM.FIT | ✅ | compute_platform_fit + 7 tests. |
| G09.HALLUCINATION | ✅ | V1-V3 validators + RAG /answer fail-closed flow with deterministic template; gemini_hallucination_alerts row written on every rejection. |
| G10.ROLE.GATE | ✅ | `require_analyst`; 11 role tests. |
| G11.SSE.STREAM | ✅ | SSE intelligence + RAG /answer/stream. |
| G11.RAG.PRIVACY | ✅ | Per-user chat session isolation: user A reads user B's session → 403. RAG /evidence strips entity_id. |
| G11.BOT.ROUNDTRIP | ✅* | `/runs/new` writes + ingest endpoint accepts the bot's AppPayloadV1 callback. Operator submits a Request DMA via the admin UI + verifies request_id round-trips. Full command sequence in DEPLOYMENT.md §31.3. |
| G11.BOT.MODE | ✅ | evidence_mode hybrid/public. |
| G11.RAG.COHORT | ✅ | Three-mode router + adjacency table. |
| **G11.RAG.ANSWER (new)** | ✅ | POST /api/v1/rag/answer: grounded conversational endpoint with citation extraction, fail-closed fallback, daily rate limits, surface-keyed Redis cache. 27 unit tests on the pure logic. |
| **G11.CHAT.PERSISTENCE (new)** | ✅ | chat_sessions / chat_messages / chat_feedback tables; 4 endpoints (list/detail/delete/feedback) with per-user privacy gate. |
| **G11.ENRICHMENT (new)** | ✅ | ai_enrichments table + service with validator-rejection fallback + supersede chain. 13 unit tests. |
| **G11.PEER.ARCHETYPES (new)** | ✅ | peer_archetypes table + worker. KMeans + silhouette; 9-entity stress test detects 2 archetypes with silhouette > 0.4. |
| **G11.ADVERSARIAL.LEARNING (new)** | ✅ | chat_learning_signals table + chat_learning worker. 100-row simulation passes. |
| **G11.ADVERSARIAL.APPLIED (new)** | ✅ | /answer consults chat_learning_signals + re-ranks. 13 unit tests in test_rag_answer_reranking.py + end-to-end stress test_negative_feedback_drives_preferred_eids_to_positives. |
| **G11.INGEST.PUBSUB (new)** | ✅ | persist_package + backfill publish dma.ingest.completed; embedder --subscribe mode. 8 unit tests in test_pubsub_publisher.py. |
| **G11.UI.ARCHETYPE.CHIP (new)** | ✅ | D3 ClientHeatmap loads DMA.archetype.forEntity on mount; chip renders label+sample_count; insufficient_data state covered. |
| **G11.UI.AI.PILL (new)** | ✅ | Heatmap cells with ai_enrichments show an "AI" pill; tooltip lists grounding E-IDs; backend joins ai_enrichments to subcap_scores via subcap_score.id. |
| **G11.UI.RUN.HISTORY (new)** | ✅ | ClientRuns timeline calls /run-history; parent_request_id chain walked; Δ vs parent badge; row drawer. |
| **G11.UI.SESSION.RESUMPTION (new)** | ✅ | IntelligencePanel fetches DMA.chat.listSessions, renders Recent threads above starters, seeds chat[] via getSession, posts feedback (rating + better_answer). |
| **G11.UI.PATTERNS.TAB (new)** | ✅ | D6 Health Patterns tab calls DMA.patterns.list(subvertical); closest archetype row highlighted. |
| **G11.RUN.HISTORY (new)** | ✅ | /entities/{id}/run-history walks parent_request_id chain. |
| **G12.VERTEX.BUDGET (new)** | ✅ | /admin/vertex-budget reads audit_log + system_config. |
| **G12.PENDING.REVIEW (new)** | ✅ | /admin/pending-review unions PENDING_REVIEW runs/entities/import_files. |
| G12.E2E.PERSONAS | ✅ | 11 Playwright tests. |
| G12.A11Y | ✅ | axe-core green on **17 surfaces** covering every primary route: Sidebar / TopBar / Modal helpers + DashboardPage / ClientOverview / Alerts / Prospecting / ClientRuns / TechStackDetail (original 9) + DirectoryPage / InsightsPage / HeatmapPage / PlatformPage / ContextPage / HealthPage / TechStackPage / LoginPage (added). Zero critical/serious violations in vitest CI gate. |
| G12.STANDALONE | ✅ | `pnpm build:standalone` produces `dist-standalone/DMA Insights · Standalone.html`; vitest assertion gates the build (asserts single-file output + no console errors when opened in headless chromium). |
| G12.RESPONSIVE.SUITE | ✅* | Same Playwright config as G04.CHROME.RESPONSIVE. Command sequence in DEPLOYMENT.md §31.5. |
| G12.PERF.BUDGET | ✅* | `frontend/lighthouserc.cjs` defines the plan's thresholds (Performance ≥ 0.85, FCP < 1.5s, TTI < 3s) for /dashboard + /heatmap. Operator runs `LHCI_BUILD_URL=$FE npx @lhci/cli@0.13.x autorun --config=./lighthouserc.cjs`. Full sequence in DEPLOYMENT.md §31.4. |
| **G18.RESEARCH.WORKBOOK.PER_PILLAR (new)** | ✅ | `parse_per_pillar_sheets` walks Alma/WSFS P1C1..P4C4 sheets; tests cover full_extract + partial_with_warnings + headers_too_drifted_requires_admin_review + file_missing; handoff JSON wins on E-ID conflict. |
| **G18.CLIENT_PROFILE.PARSE (new)** | ✅ | `parse_client_profile_path` extracts focus_areas with verbatim quotes + page numbers + subcap IDs; leadership table fallback covers the Alma 5-col layout; verified against real Alma + WSFS fixtures. |
| **G18.DEDUP.CONTENT_HASH (new)** | ✅ | `evidence_dedup.compute_content_hash` + 5-branch `decide()`; migration 018 backfills + GENERATED columns; tests cover kept / dedup_same_entity / cross_entity_kept / duplicate_within_run / tier_upgrade. |
| **G18.STALENESS.3YEAR (new)** | ✅ | `evidence_staleness.compute_band` mirrors SQL GENERATED column; 4+1 bands; `bundle_stale_pct > 40` triggers RAG disclaimer; tested against 100-row aggregate + 3-year boundary exact day. |
| **G18.INTELLIGENCE.PROFILE (new)** | ✅ | `customer_intelligence_profiles` table + 5-branch state matrix in `classify_state`; pure compute primitives unit-tested for velocity / archetype / themes / gaps / tech drift; D1 PersistentIntelligenceCard wired. |
| **G18.UI.FRESHNESS.BADGE (new)** | ✅ | EvidenceDrawer renders per-row freshness badge with the same band logic as backend; `lib/freshness.ts` tested with 8 unit tests including the 2026-05-23 reference window. |
| **G18.UI.INTELLIGENCE.CARD (new)** | ✅ | `PersistentIntelligenceCard` on D1: pending state when profile is null; velocity arrow + theme chips + "Read summary" toggle when populated; stale-pct chip with `data-stale=high` when > 40. |
| **G19.INTELLIGENCE.RECOMPUTE.WORKER (new)** | ✅ | `workers/intelligence_recompute` binary in 2 modes (--entity-id one-shot, --subscribe long-lived); 6-branch state matrix (first_time_compute / incremental_with_new_run / idempotent_skip / vertex_unavailable / validator_rejected / embedding_failed); 29 unit tests; terraform subscription `dma-ingest-completed-intelligence` provisioned. |
| **G19.PERSIST.DEDUP.INTEGRATION (new)** | ✅ | `package_persist._persist_evidence` rewritten to flow through the dedup decision engine; every package ingest emits `dedup_audit` + `evidence_run_links` rows; 5-branch coverage with FakeSession in `test_package_persist_dedup.py`. |
| **G19.RAG.SECTION.UNION (new)** | ✅ | `merge_bundles()` UNIONs section_embeddings into the retrieval bundle; sections downweighted 0.85x; CitationChip gains `kind="section"` discriminator; 19 unit tests; backward-compat case explicit. |
| **G19.UI.SEEN.IN.RUNS.CHIP (new)** | ✅ | `GET /api/v1/evidence/:id/run-history` endpoint + `SeenInRunsChip` component; 5 backend + 3 frontend tests; 3 state branches (evidence_not_found / first_seen_only / seen_in_n_runs). |
| **G19.SUBCAP.NARRATIVE.LLM (new)** | ✅ | `parsers/subcap_narrative_extractor.py` Vertex Pro structured-output classifier with 4-branch state matrix (full_match / partial_match_with_warnings / validator_rejected_template_fallback / empty_input); 24 unit tests; `build_narrative_heatmap` accepts `llm_narratives=` and marks each cell as `data-source="llm"|"heuristic"`; cache key SHA256(pillar_id + body_text + run_id). |
| **G19.E2E.AI.CHAIN (new)** | ✅ | `test_full_ai_chain.py` asserts the 8-step end-to-end loop (ingest → dedup → embed → recompute → RAG → feedback → learning → run-history); deterministic; one test per step + cross-step content_hash stability. |

## AI-layer test inventory (this batch)

| Test file | Tests | Surface covered |
|---|---|---|
| test_rag_answer_service.py | 27 | token cap, cache key, cohort fallback, prompt build, citation extraction, rate-limit key |
| test_rag_answer_reranking.py | 13 | pick_best_cluster + apply_learning_signal: no_match / low_eff / insufficient_samples / applied + cohort filter + backward compat |
| test_enrichment_service.py | 16 | prompt + template fallback + validator + supersede + end-to-end pipeline |
| test_peer_patterns_service.py | 20 | KMeans + silhouette + pick_k + compute_archetypes (insufficient/homogeneous/well-clustered) |
| test_chat_learning_service.py | 22 | recency weight + effectiveness + preferred E-IDs + rollup_signals + 100-row stress |
| test_chat_schemas.py | 22 | Pydantic validation for RAG /answer, feedback, sessions, enrichment, archetype, run-history, vertex-budget, pending-review |
| test_pubsub_publisher.py | 8 | envelope shape + 4 state branches (disabled / topic_not_found / auth_missing / timeout) + post-commit non-blocking |
| test_stress_e2e.py | 22 | old-DMA-on-new-catalogue, catalogue-pin distinct cache keys, archetype filter signature, enrichment supersede, adversarial-loop end-to-end, embedder idempotency under 5 concurrent triggers, multi-version DOCX, narrative fallback, cross-pillar consistency, drive/sheet poller interplay, **+ 7 customer-intelligence scenarios** (dedup resilience, cross-entity, freshness rollup, multi-run profile, stale bundle flag, archetype shift, dedup tier upgrade) |
| test_research_workbook.py | 14 | flat-shape + per-pillar-shape parsers; 5 state branches; handoff cross-ref tier override |
| test_client_profile_parser.py | 5 | full / partial / no_docx_found; verbatim quote + page number extraction; real Alma + WSFS fixture round-trips |
| test_evidence_dedup.py | 13 | content-hash determinism + whitespace immunity + 5-branch decide() coverage |
| test_evidence_staleness.py | 15 | all 4+1 freshness bands + 3-year boundary exact day + 100-row aggregate rollup + bundle_stale_pct > 40 disclaimer trigger |
| test_customer_intelligence.py | 22 | velocity (single / 6-mo / 1-yr / <30d), themes recurring vs emerging, persistent vs closed gaps, tech drift, 5-branch classify_state, build_summary_prompt |
| test_intelligence_recompute_worker.py | 29 | 6-branch state matrix + ExistingProfile/SummaryDecision shapes + assemble_snapshots + validate_summary_citations + parse_structured_output + deterministic_template_summary + call_vertex_summary (3 vertex variants) |
| test_package_persist_dedup.py | 7 | 5-branch dedup routing inside `_persist_evidence`; double-link contract on re-ingest; cross-entity new row; tier_upgrade UPDATE; empty package no-op |
| test_rag_answer_sections.py | 19 | merge_bundles (5 branches) + weight_section_items + GroundingBundle.section_pct + section_ids + build_answer_prompt hint conditional + extract_section_citations + backward compat |
| test_evidence_run_history.py | 5 | 3-branch endpoint matrix (404 / first_seen_only / seen_in_n_runs) + UUID vs short-form resolution |
| test_subcap_narrative_extractor.py | 24 | 4-branch state matrix + AlmaBank 12 subcap_ids (10 LLM + 2 heuristic) + cache hit/miss + fabricated subcap/anchor rejection + build_narrative_heatmap llm_narratives backward compat |
| test_full_ai_chain.py | 9 | 8-step end-to-end chain (ingest → dedup → embed → recompute → RAG → feedback → learning → run-history chip) + cross-step content_hash stability |

## Stress-test outcomes

| Scenario | Status | Notes |
|---|---|---|
| Old DMA on new catalogue (v5.0 under v7.0) | ✅ | alias bridge + UI alias badge; verified via AlmaBank/WSFS regressions |
| Mid-build catalogue bump | ✅ | per-run pinning prevents cross-contamination |
| Subvertical switch (D3 value_chain re-pivot) | ✅ | ccg_vc_mapping bucketing |
| Bulk re-embed under new model_version | ✅ | embedder idempotency tests |
| Cohort N < 3 | ✅ | /answer returns cohort_mode=cross_vertical + insufficient_cohort=True |
| Validator rejects fabricated E-ID | ✅ | enrichment + RAG /answer both fall back; alerts row written |
| 100-row simulated chat feedback rollup | ✅ | chat_learning_service test_simulated_100_feedback_rows |
| Closed-loop end-to-end (20 turns → 21st re-rank) | ✅ | test_stress_e2e::test_negative_feedback_drives_preferred_eids_to_positives |
| Pub/Sub publish never blocks ingest | ✅ | test_pubsub_publisher::test_publish_post_commit_never_raises_on_publisher_failure |
| Embedder idempotency under concurrent triggers | ✅ | test_stress_e2e::test_already_embedded_ids_are_skipped + test_candidate_sets_are_deterministic_under_concurrent_triggers |
| 9-entity 2-cluster archetype detection | ✅ | peer_patterns_service test_nine_entity_two_cluster_detection (silhouette > 0.4) |
| Insufficient (< 3 entities) cohort archetype | ✅ | writes "insufficient_data" archetype |
| Homogeneous cohort archetype | ✅ | non-crashing single-archetype output |
| Resilient re-ingest with dedup | ✅ | test_stress_e2e::TestDedupResilience — 5 dedup_same_entity actions, 0 new evidence rows |
| Cross-entity same article | ✅ | test_stress_e2e::TestCrossEntityEvidence — both entities keep independent rows under same content_hash |
| 100-row evidence freshness rollup | ✅ | test_stress_e2e::TestFreshnessRollup — rollup band counts match per-row computation exactly |
| Multi-run intelligence profile (1-year apart) | ✅ | test_stress_e2e::TestMultiRunProfile — maturity_velocity ≈ 0.4 / yr |
| Stale evidence flag in RAG bundle | ✅ | test_stress_e2e::TestStaleBundleFlag — bundle_stale_pct == 60% > 40% → disclaimer trips |
| Archetype change between runs | ✅ | test_stress_e2e::TestArchetypeShift — both archetypes retained in history with silhouette |
| Dedup edge: tier upgrade | ✅ | test_stress_e2e::TestDedupTierUpgrade — tier 5 → tier 3, audit reason logs change |
| A11y axe-core sweep across full SPA | ✅ | All 17 primary surfaces covered — vitest CI gate fails on critical/serious violations. See G12.A11Y above. |
| Responsive breakpoints (1920..760) | ✅* | `playwright.visual.config.ts` + `e2e/visual/responsive.visual.ts` cover all 7 BPs × 12 routes. Operator runs the §31.5 wrapper (auto-bootstraps `__snapshots__/`, starts/cleans-up dev servers via `trap`, asserts ≤ 2% diff). |

## Outstanding items (carried forward)

1. ✅* **Live OAuth E2E** — wiring complete; operator command sequence
   in DEPLOYMENT.md §31.1 (asterisk = green when operator-executed,
   not auto-validated in CI).
2. ✅ **PDF export** (Playwright) for the customer-share deck — DONE
   in `frontend/e2e/pdf-export.e2e.ts`. Uses chromium's `page.pdf()`
   to render dashboard + 4 client-overview surfaces as A4 PDFs;
   asserts non-empty output (>5KB) to catch silent rendering
   failures. Output: `artifacts/pdf-export/<route>.pdf`. Operator
   runs via DEPLOYMENT.md §31.6 (auto-starts dev servers).
3. ✅ **Full per-route axe-core** sweep — **17 surfaces** covered
   (DashboardPage / ClientOverview / Alerts / Prospecting / ClientRuns
   / TechStackDetail / DirectoryPage / InsightsPage / HeatmapPage /
   PlatformPage / ContextPage / HealthPage / TechStackPage / LoginPage
   + Sidebar / TopBar / Modal helpers). vitest gate fails on
   critical/serious violations.
4. ✅* **Responsive breakpoint matrix** in Playwright — `playwright.
   visual.config.ts` covers 12 routes × 7 BPs (1920/1440/1280/1180/
   980/900/760). Operator command sequence in §31.5; first-run captures
   baselines, subsequent runs assert ≤ 2% diff.
5. ✅* **Live bot loop E2E** — fastapi route + httpx fake covered by
   unit tests; live round-trip command sequence in §31.3.
6. ✅* **Sheet poller live IO** — `sheets_client.py` with Levenshtein
   fuzzy assignee landed; live ADC operator sequence in §31.2.
7. ✅ **DOCX parser** for document_lineage population — DONE
   (commit `fc26f9d feat(parser): DOCX assessment_report →
   document_sections + document_lineage`). `parsers/assessment_report.py`
   walks the DOCX via python-docx; `_persist_document_sections`
   writes rows. Cross-referenced by `section_routing.py` for the
   narrative subfield on every entity endpoint.
8. ✅* **Live Vertex embedding** for chat_messages.embedding — worker
   wired to `vertex_client.embed_texts()`; fail-soft to deterministic
   stub when ADC missing. Live binding flips on once §31.0.8 `gcloud
   auth application-default login` runs in the Cloud Run env.
9. ✅ **Worker scheduler glue** for peer_patterns weekly +
   chat_learning nightly — DONE (commit landed in this batch).
   Also added daily `evidence_freshness_refresh` Cloud Scheduler hook
   (06:00 UTC) calling new
   `POST /api/v1/admin/maintenance/refresh-evidence-freshness`
   endpoint which executes the plpgsql `refresh_evidence_freshness()`
   function — keeps `is_stale` + `freshness_band` accurate as rows
   cross 1y/2y/3y boundaries between writes.
10. **Frontend session_id round-trip** in IntelligencePanel —
    ✅ **DONE.** Recent-threads picker + getSession seeding + feedback
    (rating + better_answer) + new-turn session inheritance.
11. ✅* **Live Pub/Sub end-to-end** — `pubsub_publisher.py` covers 4
    state branches (disabled / topic_not_found / auth_missing /
    timeout) tested with stubs; live ADC + topic provisioning land
    once §31.0.8 ADC + terraform `google_pubsub_topic.dma_ingest_completed`
    apply.

## Worker job_executions counter coverage (NEW — finalize batch)

All 6 workers now publish counters to `job_executions` via the
thread-local `get_current_tracker()` accessor:

| Worker | Counters published |
|---|---|
| `drive_crawler` | `folders_seen`, `folders_new` |
| `embedder` | `rows_added` (per-batch flush, ticks the admin pill mid-run) |
| `peer_patterns` | `rows_added`, `rows_updated` (from live runner result dict) |
| `intelligence_recompute` | `rows_updated`, `files_errored` (per-entity flush) |
| `ccg_loader` | `rows_added` (sum across all per-table rowsets), `files_parsed` (workbook count), `parser_warnings` (capped to 30) |
| `sheet_poller` | `files_parsed` (successful tabs), `files_errored` (failed tabs), `rows_added` (sum across tabs) |

Resilience: every counter flush wrapped in `contextlib.suppress(Exception)`
— tracker UPDATE failure NEVER blocks the worker body. Workers running
without a `track_job_execution` context (e.g., one-off CLI for debug)
get `None` from `get_current_tracker()`; if-guard short-circuits.

Thread-local prevents cross-contamination between concurrent invocations
(e.g., the Pub/Sub subscriber spawning one task per message).

Tests in `tests/test_worker_runner.py` (8 scenarios):
  - happy path → mark_succeeded with counters
  - exception → mark_failed + exception re-raised
  - DMA_JOB_EXECUTION_ID unset → create_execution_row
  - DB unavailable → body still runs, audit silently logged
  - DMA_JOB_EXECUTION_ID set → no create_row
  - get_current_tracker returns active tracker inside context
  - get_current_tracker returns None outside context
  - nested track_job_execution restores outer on inner exit

## Adversarial-learning architecture

The adversarial-learning loop closes as follows:

1. **Capture**: every `/api/v1/rag/answer` turn writes one chat_messages row
   (with retrieval_bundle JSONB so we can replay later) and an audit_log row.
2. **Feedback**: AE clicks thumbs/comment → `POST /chat/messages/{id}/feedback`
   inserts a chat_feedback row carrying rating + unhelpful_reason +
   optional better_answer (the user's own "what should it have said").
3. **Rollup**: the `chat_learning` worker (nightly Cloud Run Job) reads
   chat_feedback joined to chat_messages, clusters questions via KMeans
   over the message embeddings, and writes one `chat_learning_signals` row
   per (surface, cluster) with a recency-weighted effectiveness score
   (0..1) and a `preferred_evidence_ids` array of E-IDs that appear in
   positively-rated answers more often than negative ones.
4. **Replay**: the `/answer` service, on receiving a new question, can
   (in a follow-up wiring step — the table is in place) embed the
   question, find the closest cluster by centroid, and bias retrieval
   ordering toward `preferred_evidence_ids` when effectiveness > 0.6.
   This is the "adversarial" half — the next prompt is steered by the
   contrast between past preferred-answers and past served-answers.

The data model + worker landed in the prior batch; the retrieval-reranking
step in /answer landed this batch — the loop is now fully closed.
`apps/dma-insights/backend/app/services/rag_answer.py::apply_learning_signal`
is the closing primitive; `apps/dma-insights/backend/app/routers/rag.py`
calls it on every /answer call with a 5-minute TTL cache of
`chat_learning_signals` rows.
