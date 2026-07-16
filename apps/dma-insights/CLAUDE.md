# DMA Insights — Claude project notes

This app is the Zennify-internal surface for every completed Digital Maturity
Assessment (DMA). It ingests artifacts from the DMA Bot pipeline (Drive folder
`folders/1uvt3kh8vPIygFwUNfKQSol0m5OYj2O0P`, Ops Sheet
`1vQq4AMjtcS5eduDf_qIfXQYM7l0xYnVcmo-weqeXPs8`) once and serves 16 client-scoped
views forever — plus a RAG API the Claude project can query for prior evidence.

## Authoritative docs (read first, never deviate from)

All copied verbatim into `docs/reference/`:

1. **PRD v3.0** — `DMA Insights - Product Requirements Document v3.0.html`
2. **TRD v4** — `DMA Insights - TRD.html`
3. **App Flow v3** — `DMA Insights - Application Flow.html`
4. **UI/UX Brief v3.0** — `DMA Insights - UI_UX Design Brief.html`
5. **Backend Schema v2.0** — `DMA Insights - Backend Schema.html`
6. **Implementation Steps v3** — `DMA_Visualizer_Implementation_Steps_v3.html`
7. **V7 Capability Mapping Schema** — `Zennify Capability Mapping Visualized Schema - All 4 Pillars.html`
8. **Design system skill** — `zennify-design-system.skill`

## Wireframe contract

The visual contract is the prototype at
`/tmp/design-pkg/dma-insights-website/project/`. Files copied verbatim into
this repo:

- `assets/tokens.css` → `frontend/styles/tokens.css`
- `assets/app.css` → `frontend/styles/app.css`
- `assets/data.js` → `frontend/src/mock/data.ts` (only used by the `dist-standalone` build)
- `components/{utils,chrome,drawers}.jsx` → `frontend/src/components/*.tsx`
- `pages/*.jsx` → `frontend/src/pages/*.tsx`
- `main.jsx` → `frontend/src/main.tsx`

`DMA Insights · Standalone.html` is a **wireframe-guide / stakeholder-demo**
single-file build with mock data inlined. **Not used by AEs; not connected to
live data.** The live web app is the only production surface.

## Locked decisions

See the plan in `~/.claude/plans/quizzical-hatching-lighthouse.md`. Highlights:

- **Stack**: Vite + React 18 + TS frontend (hash routing, mirroring the
  prototype 1:1); FastAPI + SQLAlchemy 2.0 + Pydantic v2 backend; Postgres 16
  with `pgvector`; Redis 7; Vertex AI (Gemini Flash + Pro + text-embedding-004).
- **AE assignment**: hybrid — Ops Sheet source-of-truth + Drive owner
  inference + admin override.
- **Bot loop**: bidirectional; `request_id = REQ-{8 uppercase hex}` is the
  canonical cross-system ID.
- **Persistence**: ingest once, serve forever. Postgres canonical, Redis
  per-user ephemeral, TanStack Query client cache.
- **Capability catalogue**: V7.0 is canonical, persisted to versioned `ccg_*`
  tables; older DMAs resolved via `ccg_subcap_aliases`.

## Architectural Decision Records (ADRs)

See `docs/decisions/`:

- `0001-stack-choice.md` — why Vite/React, not Next.js
- `0002-ae-assignment.md` — Ops Sheet + Drive owner hybrid
- `0003-bot-loop.md` — bidirectional `request_id` continuity
- `0004-persistence-tiers.md` — Postgres / Redis / TanStack Query layering
- `0005-catalogue-versioning.md` — versioned `ccg_*` tables + `ccg_subcap_aliases`
- `0006-rag-cohort-scoping.md` — three-mode router (`single`/`multi_lob`/`cross_vertical`)
- `0007-admin-editable-adjacency.md` — `ccg_subvertical_adjacency` admin surface
- `0008-color-encoding-canonical.md` — `frontend/src/lib/maturity.ts` is single
  source of truth for score→hex / band / peer-delta-arrow
- `0009-catalogue-layer-naming.md` — DB keeps `ccg_l3_platforms`/`ccg_l4_features`;
  UI/Pydantic renames to `platform_area_*` / `features` (no jargon)
- `0010-clay-connector.md` — Clay table webhook for firmographics +
  leadership (HMAC-signed inbound; fail-closed when secret unset)
- `0011-standalone-as-live-ae-surface.md` — **SUPERSEDED by 0016**;
  kept for historical record of the 2026-05-24 → 2026-05-29 revert.
- `0012-ingest-dual-auth.md` — ingest accepts bot bearer OR admin cookie
- `0013-two-phase-deploy.md` — deploy-two-phase.sh contract
- `0014-final-audit-p0-patches.md` — 2026-05-28 audit waves
- `0015-real-sample-parser-variants.md` — sanitized fixtures policy
- `0016-react-vite-as-production.md` — **production is `frontend/dist/`**
  (Vite + React + TS + hash routing per CLAUDE.md "Locked decisions");
  standalone-src is stakeholder-demo only

## DMA package ingest

`POST /api/v1/ingest/package` accepts the canonical
`{Entity}_DMA_Complete_Package.zip` that the n8n pipeline emits. The
parser orchestrator is `app/services/parsers/dma_package.py`; leaf
parsers split into `package_csvs.py` (`export_*.csv`, `evidence_index.csv`,
`peer_comparison_table.csv`, `issue_register.csv`) and `package_json.py`
(`MANIFEST.json`, `run_manifest.json`, `recommendations_detail.json`,
`peer_scores_*.json`, `qa_verdict.json`, `research_handoff.json`).
Persistence lives in `package_persist.py`. Verified end-to-end against
the real AlmaBank + WSFS packages with zero parse warnings.

Run-IDs accept both `REQ-{8 hex}` (bot-originated) and
`DMA-ASM-{ENTITY}-{YYYYMMDD}-{NNNN}` (project-originated). Parsing is in
`app/services/parsers/run_id.py`.

### Report narrative parsing

`04_reports/Assessment_Report*.docx` is the analyst's prose — without
it, every surface displays only the skeleton from CSV/JSON inputs.
The flow is:

1. **`parsers/assessment_report.py`** walks the DOCX via `python-docx`,
   classifies each heading into one of 12 canonical section kinds via a
   liberal regex dictionary (handles WSFS / AlmaBank / Regions header
   drift like "Strategic Posture & Governance" → P1 deep-dive). Returns
   a `ReportParseResult` with a `state_kind` ∈
   `no_docx_found | partial_coverage | llm_fallback_used | full_coverage`.
2. **`parsers/dma_package.parse_package`** populates
   `IngestedPackage.report_sections` from the parsed DOCX. Absent DOCX
   is silent — no parser_warnings emitted, `report_sections=[]`.
3. **`parsers/package_persist._persist_document_sections`** writes one
   `document_sections` row per section plus `document_lineage` rows for
   the section_kind, pillar_id (for pillar deep-dives), subcap_ids
   mentioned in the body, and E-IDs mentioned. Re-ingest is idempotent
   via DELETE-then-INSERT per run_id.
4. **`services/section_routing.py`** exposes `load_sections_for_run` +
   six `build_narrative_*` helpers (overview/insights/heatmap/platform/
   context/health). Returns `None` when no lineage exists for the
   surface — endpoints emit `narrative: null` and the frontend keeps
   the skeleton (marker: `data-source="narrative|skeleton"`).
5. **Endpoints** (`/entities/:id/{overview,insights,heatmap,platforms,
   context,health}`) all gained a `narrative` subfield.
6. **Frontend** consumes via the typed `OverviewNarrative` /
   `InsightsNarrative` / `HeatmapNarrative` / `PlatformNarrative` /
   `ContextNarrative` shapes.

State-branch contracts are documented in the module docstrings —
`assessment_report.py`, `section_routing.py`, `package_persist.py`,
`drive_client.py`, `sheets_client.py`.

## Customer intelligence layer

Per the user mandate ("persistent memory within the app such that the
layer of intelligence and deep customization at the customer level is
usually achieved"), DMA Insights maintains a per-entity persistent
intelligence layer that survives across runs.

### Components

1. **`services/parsers/research_workbook.py`** — `parse_per_pillar_sheets`
   walks the AlmaBank / WSFS / Regions per-pillar-category sheets
   (P1C1..P4C4) and emits one `ParsedEvidence` per E-ID with multi-
   value Evidence_IDs / Source_URLs split on `;`, `|`, newline.
   `cross_reference_with_handoff` then reconciles those rows against
   `research_handoff.json` — handoff JSON wins on E-ID conflict.

2. **`services/parsers/client_profile.py`** — `parse_client_profile_path`
   walks the separate `04_reports/*_Client_Profile_Research_Report.docx`
   and extracts focus areas (verbatim quote + source_path + page
   number + auto-extracted subcap IDs), leadership entries (from
   paragraphs OR from tables — the AlmaBank fixture renders leaders
   in a 5-column table), financial highlights, and the firmographics
   narrative_md.

3. **`services/evidence_dedup.py`** — `compute_content_hash` =
   SHA256(url + claim_type + normalize(excerpt[:500])). `decide()`
   is a pure 5-branch decision engine: `kept` /
   `dedup_same_entity` / `cross_entity_kept` /
   `duplicate_within_run` / `tier_upgrade`. The persistence layer
   does the actual lookups + audit-row inserts.

4. **`services/evidence_staleness.py`** — 4+1 freshness bands keyed
   to a `today` parameter so tests pin the 2026-05-23 reference:
     - `current` ≤ 12 months
     - `aging`  > 12 ≤ 24 months
     - `dated`  > 24 ≤ 36 months
     - `stale`  > 36 months (the 3-year mandate's "⚠ >3y")
     - `undated` when both `published_date` and `recency_months` are NULL.
   The SQL-side authority is `evidence_index.freshness_band` —
   STORED generated column maintained by Postgres.

5. **`services/customer_intelligence.py`** — pure compute primitives
   (`compute_maturity_history`, `compute_velocity`, `compute_themes`,
   `compute_gaps`, `compute_tech_drift`, `compute_profile`) plus the
   5-branch `classify_state` matrix: `first_run` /
   `incremental_update` / `re_ingest_same_request_id` /
   `gemini_unavailable` / `validator_rejected`. The Gemini summary
   prompt builder lives here too; the persistence layer calls
   vertex_client and validates citations against the bundled evidence.

### Tables added by migration `018_intelligence_layer`

- `evidence_index.content_hash` (VARCHAR(64)) — backfilled from
  existing rows. Used by dedup; same input → same hash both in SQL
  and in `evidence_dedup.compute_content_hash`.
- `evidence_index.is_stale` (BOOLEAN GENERATED STORED) — 3-year flag.
- `evidence_index.freshness_band` (VARCHAR(8) GENERATED STORED) —
  one of `current / aging / dated / stale / undated`.
- `evidence_run_links (evidence_id, run_id, first_seen_in_run,
  surfaces_in_run TEXT[])` — many-to-many that powers the "Seen in
  N prior runs" chip on EvidenceDrawer.
- `dedup_audit (run_id, source_e_id, kept_evidence_id, action,
  reason, content_hash)` — append-only audit; action is one of
  `kept / dedup_same_entity / cross_entity_kept /
  duplicate_within_run / tier_upgrade`.
- `customer_intelligence_profiles` — per-entity row with the full
  longitudinal rollup + summary_embedding + intelligence_summary_md.
- `focus_areas` — verbatim source quote + page number + involved
  subcap IDs from the Client Profile parser.

### UI surfaces

- D1 `ClientOverview` gains a `PersistentIntelligenceCard` above the
  SCQA: total_runs + velocity arrow + recurring themes chips +
  "Read summary" drawer.
- `EvidenceDrawer` shows a freshness badge per row (green
  `current`, amber `aging`, orange `dated`, red `⚠ >3y` `stale`,
  grey `undated`).
- `/api/v1/entities/{id}/intelligence-profile` returns the full
  profile JSON (404 when not yet computed).
- `/api/v1/rag/answer` response adds `bundle_stale_pct` +
  `stale_disclaimer` — UI surfaces the "Most evidence is dated"
  banner when > 40% of the bundle is `stale`.

### Recompute cadence

Recompute fires on `dma.ingest.completed` Pub/Sub — see
DEPLOYMENT.md §27 for the subscription wiring and §28 for the
content-hash backfill playbook.

## Synthesis persistence + decision gates

Per the user's explicit mandate: "once Vertex models interpret the
information, this is persisted, unless there is new information or a
rerun has been done, to avoid token consumption for each reload."

`app/services/synthesis_orchestrator.py` is the unified persistence +
decision layer that sits in front of every Vertex/Gemini call. It
consolidates the four prior caches (`gemini_cache`, `ai_enrichments`,
`customer_intelligence_profiles.intelligence_summary_md`, per-module
in-memory dicts) behind a single hard contract:

> Once Vertex interprets information, the output is persisted;
> subsequent reads consume zero tokens until the input fingerprint
> changes.

### Decision gates (the 8 states)

| Gate | When it fires | Token cost |
|---|---|---|
| `parsed_skipped_llm` | Surface is fully derivable from parsed CSV/DOCX (leadership panel, tech stack list, raw scores, recommendation metadata) — no Vertex call ever | 0 |
| `cache_hit` | Active `vertex_synthesis_cache` row with matching fingerprint, not expired, not invalidated | 0 |
| `invalidated_re_synthesized` | Row exists but `invalidated_at IS NOT NULL` OR `expires_at < NOW()` — re-synthesize, supersede prior row | full |
| `cache_miss_synthesized` | No row matches fingerprint — synthesize + insert | full |
| `user_regenerate` | Explicit `force_regenerate=True` (user clicked "Regenerate") — supersede + re-synthesize | full |
| `feedback_invalidated` | A 👎 with `unhelpful_reason='hallucinated'` invalidates only the responsible cache row | full on next read |
| `rerun_invalidate_all` | A new run for an entity invalidates entity-level + subcap-level rows lazily | full on next read |
| `catalogue_bump_invalidate` | New catalogue version invalidates rows tagged with the old version (alias bridge handles subcap renames) | targeted |

### Fingerprint

`input_fingerprint = SHA256(prompt_template_version + grounding_bundle_hash + catalogue_version + page_context_hash)`

- Bundle order is part of the hash (rerank is visible to the cache).
- Volatile page-context fields (`user_id`, `session_id`, `request_ts`)
  are stripped before hashing — different users sharing the same view
  share cached answers.
- Catalogue version is always in the fingerprint, so a catalogue bump
  auto-misses every row without explicit invalidation.

### Tables

- `vertex_synthesis_cache` (migration `019`) — the unified store.
  `UNIQUE(target_kind, target_id, surface, input_fingerprint)`.
  Partial index `WHERE invalidated_at IS NULL` for hot reads.
- `system_config` rows seeded with the 8 surface TTLs (`vertex_synth_ttl_*_sec`)
  and `vertex_synth_gc_retention_days=90`.

### Invalidation triggers

- `package_persist.persist_package` (after a successful commit) emits
  `build_invalidation_for_new_run(entity_id, affected_subcap_ids)` → caller
  runs a single UPDATE SET `invalidated_at=NOW(), invalidation_reason='rerun_invalidate_all'`
  on the affected rows.
- Catalogue loader emits `build_invalidation_for_catalogue_bump(old_version, renamed_subcap_ids)`.
- `chat_feedback` POST with `rating=-1` + `unhelpful_reason='hallucinated'`
  emits `build_invalidation_for_feedback(cache_row_id)`.

### Token accounting

`MODEL_RATES_USD_PER_1K` per the Q2 2026 Vertex pricing. `estimate_cost_usd()`
turns cached `prompt_tokens` + `completion_tokens` into USD for the
`/admin/vertex-budget` panel. `compute_cache_hit_rate()` is bounded
[0, 1] and zero-call-safe. `estimate_tokens_saved()` quantifies how
many tokens the cache prevented from being spent.

### Tests

`tests/test_synthesis_orchestrator.py` covers all 8 decision gates,
fingerprint stability under dict reorder, bundle reorder sensitivity,
volatile-field stripping, full lifecycle (miss → hit → invalidate →
re-synth → hit), and token economics. 22 tests, all pure-logic, no
flakes.

## Stage gates

CI writes one row to `build_qa_gates` per gate per build. A stage advances
only when all gates are PASS or DEFERRED-with-reason. See the
"QA gates" section of the plan for the per-stage matrix.

## Commands

```bash
# Bring up local services (Postgres+pgvector, Redis)
docker compose -f apps/dma-insights/docker-compose.yml up -d

# Backend dev server
cd apps/dma-insights/backend && uvicorn app.main:app --reload --port 8000

# Frontend dev server
cd apps/dma-insights/frontend && pnpm dev

# Run migrations
cd apps/dma-insights/backend && alembic upgrade head

# Re-load v7.0 catalogue from the 4 pillar workbooks (entrypoint is
# workers.ccg_loader.main — the package has no __main__)
python -m workers.ccg_loader.main --version v7.0 --workbooks-dir docs/reference/catalogue/v7.0/

# Poll the Ops Sheet once (Cloud Run Job entrypoint; live IO pending stage 11 finalize)
python -m workers.sheet_poller --once

# Build the wireframe-guide single-file artifact
cd apps/dma-insights/frontend && pnpm build:standalone

# Backend test sweep + lint
cd apps/dma-insights/backend && .venv/bin/python -m pytest tests/ -q
cd apps/dma-insights/backend && .venv/bin/ruff check app/ tests/ ../workers/

# Frontend test sweep + tsc + build
cd apps/dma-insights/frontend && pnpm exec vitest run
cd apps/dma-insights/frontend && pnpm exec tsc --noEmit
cd apps/dma-insights/frontend && pnpm exec vite build
```

## AI layer (new)

The AI layer is the grounded retrieval + LLM generation + adversarial-
learning surface that sits on top of the canonical Postgres data.

### Surfaces

| Surface | Model | Cache TTL | Role gate | Validator policy |
|---|---|---|---|---|
| `rag_answer` (concise) | gemini-2.5-flash | 15 min | AE+ | V1+V2 regex+DB; fail-closed → template |
| `rag_answer` (deeper) | gemini-2.5-pro | 15 min | AE+ | V1+V2 |
| `subcap_narrative` | flash | 1 hour | AE+ | V1+V2+V3 |
| `platform_story` | flash | 1 hour | AE+ | V1+V2 |
| `insight_explanation` | flash | 1 hour | AE+ | V1+V2 |
| `meeting_prep` | pro | 30 min | AE+ (20/day) | V1+V2 |
| `why_now` | flash | 10 min | AE+ | V1+V2 |
| `enrichment` | flash | n/a (persisted) | server-side | V1+V2 lite |

### RAG /answer endpoint

`POST /api/v1/rag/answer` and `POST /api/v1/rag/answer/stream` (SSE).
Request:
```json
{
  "question": "...",
  "page_context": {"route":"/clients/x/heatmap","entity_id":"...","subcap_id":"P1C1.1.1","user_role":"AE"},
  "response_style": "concise|deeper",
  "max_paragraphs": 3,
  "require_citations": true,
  "session_id": "uuid|null"
}
```

Pipeline:
1. Resolve entity profile → catalogue version pinning.
2. `cohort_from_profile` decides single / multi_lob / cross_vertical / catalogue_only.
3. Fetch top-k evidence via tier+recency SQL ordering; cap bundle at
   16k estimated tokens.
4. Daily rate-limit check via Redis (`rl:{surface}:{user_id}:{ymd}`).
5. Cache key = SHA256(question + entity_id + subcap_id + catalogue_version
   + response_style) — catalogue bump auto-invalidates.
6. Call Vertex (flash or pro per style); the lazy client falls back to
   a deterministic offline string if creds are missing.
7. Citation extraction by regex; any fabricated E-ID triggers fail-closed
   fallback + a `gemini_hallucination_alerts` row.
8. Persist user + assistant chat_messages rows; bump session.last_message_at.
9. Audit-log row written (best-effort; never blocks the user).

### Chat persistence

Tables: `chat_sessions`, `chat_messages`, `chat_feedback`,
`chat_learning_signals`. The session_id round-trip lets the UI resume a
conversation across page reloads; `GET /api/v1/chat/sessions[/{id}]`
returns the thread. Feedback POSTs (rating + optional better_answer)
land in chat_feedback and feed the nightly `workers/chat_learning`
rollup → `chat_learning_signals`.

### AI enrichment with evidence threading

`app/services/enrichment.py` provides the pure pipeline; results land in
`ai_enrichments` with `grounding_evidence_ids` set to the E-IDs the
narrative is grounded on. Idempotency via `superseded_by` chain when
re-running or bumping catalogue.

Thin evidence (`evidence_count < 2`) does NOT synchronously fire enrichment
at ingest — that would put a Vertex round-trip on the commit path. Instead
`package_persist.py` records `subcap_scores.is_thin_evidence=True` and derives
a thin-evidence alert (`derive_thin_evidence_alerts`); the subcap surface
renders the provisional-score state; and the deploy-time `enrich_corpus`
sweep (gated by the G1–G10 trigger matrix in `enrichment_triggers.py`) fills
the empty/thin surface fields. `enrichment.enrich_with_fallback` is the pure
runtime hook the sweep composes on top of (2026-07-14 audit corrected the
prior "auto-fires on ingest" wording).

### Adversarial-learning workflow

```
chat_messages + chat_feedback
  ↓ (nightly Cloud Run Job: workers/chat_learning)
chat_learning_signals (one row per surface × prompt cluster,
                       with effectiveness + preferred_evidence_ids)
  ↓ (every /api/v1/rag/answer call — see "Closed loop" below)
re-ranks retrieval bundle toward preferred E-IDs for the
matching cluster
```

### Closed loop

`apps/dma-insights/backend/app/services/rag_answer.py` exposes
`pick_best_cluster` + `apply_learning_signal`. On every `/api/v1/rag/answer`
the router fetches `chat_learning_signals` for the call's surface
(5-min TTL cache), embeds the user's question via Vertex
`text-embedding-004`, then:

1. Picks the closest cluster by cosine similarity (threshold ≥ 0.75).
2. Gates by effectiveness ≥ 0.5 and sample_count ≥ 5.
3. Boosts in-bundle items whose `e_id ∈ preferred_evidence_ids` by
   +0.15 (re-sorts the bundle).
4. Pulls in up to 3 preferred E-IDs that weren't already retrieved,
   subject to cohort filtering: when `cohort_mode == "single"` only
   E-IDs owned by the current entity may be pulled.
5. Writes `learning_signal: {applied, reason, cluster_id, effectiveness,
   sample_count, items_boosted, items_pulled}` to the audit_log
   `after_json` and into the response body so the UI can show "+ 2
   items pulled from past helpful turns" badges.

The state-transition matrix (in the `rag_answer.py` docstring):
`no_match | low_effectiveness | insufficient_samples | applied`. When
`chat_learning_signals` is empty the path is identical to the prior
batch — the boost is purely additive.

### Pub/Sub ingest fan-out

After every successful `persist_package()` commit (live `/ingest/package`
endpoint AND `historical_backfill.py`), we publish a
`dma.ingest.completed` Pub/Sub message with:

```json
{
  "run_id": "<uuid>", "entity_id": "<uuid>", "request_id": "REQ-…",
  "ccg_catalog_version": "v7.0", "completed_at": "<iso>",
  "is_rerun": false, "parent_request_id": null
}
```

The embedder worker exposes a long-lived `--subscribe` mode that
consumes this topic and dispatches `embed_run(run_id=…)` per message.
Publish failures are logged + swallowed — ingest never wedges on a
Pub/Sub outage. See `apps/dma-insights/backend/app/services/pubsub_publisher.py`
docstring for the full state matrix.

### Cross-DMA pattern recognition

`workers/peer_patterns` runs KMeans on the (entity × subcap-score-vector)
matrix per subvertical and writes `peer_archetypes` rows ("compliance-
first", "experience-first", etc.). The `/entities/{id}/archetype`
endpoint surfaces the closest archetype on D3 as a chip.

Stress-tested against synthetic 9-entity 2-cluster cohorts (silhouette
> 0.4) and N<3 cohorts (writes a single insufficient_data row).

## End-to-end AI chain (now CLOSED)

```
┌──────────────────────────────────────────────────────────────────┐
│                    AlmaBank package arrives                       │
│              (n8n bot drops zip in Drive folder)                  │
└──────────────────────────┬───────────────────────────────────────┘
                           ▼
        ┌────────────────────────────────────────┐
        │  ingest_package router →                │
        │  parsers.dma_package.parse_package      │
        │  parsers.package_persist.persist_package│
        │                                         │
        │  per-evidence: content_hash + dedup     │  ← LOOP 1 CLOSED
        │  decision engine routes to 1 of 5       │    (deliverable #2)
        │  branches; dedup_audit row written;     │
        │  evidence_run_links populated.          │
        └────────────────────────────────────────┘
                           ▼
        ┌────────────────────────────────────────┐
        │  Pub/Sub publish: dma.ingest.completed  │
        │   (best-effort; ingest never wedges)    │
        └────────────────────────────────────────┘
                       │           │
              ┌────────┘           └─────────┐
              ▼                              ▼
   ┌──────────────────────┐      ┌──────────────────────────┐
   │ embedder worker      │      │ intelligence_recompute   │ ← LOOP 2 CLOSED
   │ (--subscribe)        │      │ worker (--subscribe)     │   (deliverable #1)
   │ writes evidence_,    │      │ rolls runs into profile, │
   │ insight_, rec_,      │      │ calls Vertex Pro for     │
   │ SECTION_embeddings   │      │ summary, validates       │
   └──────────────────────┘      │ citations, UPSERTs       │
              │                  │ customer_intelligence_   │
              │                  │ profiles row.            │
              │                  └──────────────────────────┘
              ▼                              ▼
        ┌────────────────────────────────────────┐
        │  /rag/answer endpoint                   │
        │  • cohort decision                      │
        │  • fetch evidence_embeddings + new      │  ← LOOP 3 CLOSED
        │    section_embeddings UNION             │    (deliverable #3)
        │  • merge_bundles weights sections 0.85x │
        │  • learning_signal re-rank toward       │
        │    preferred_evidence_ids               │
        │  • Vertex flash/pro → validator         │
        │  • cite chips: evidence + section kinds │
        └─────────────────┬──────────────────────┘
                          ▼
        ┌────────────────────────────────────────┐
        │  AE reads answer; clicks 👍 / 👎        │
        │  /chat/messages/:id/feedback            │
        └─────────────────┬──────────────────────┘
                          ▼
        ┌────────────────────────────────────────┐
        │  chat_learning nightly rollup           │  ← carried over
        │  KMeans on question embeddings          │    (prior batch)
        │  → chat_learning_signals row            │
        │  with preferred_evidence_ids signal     │
        └─────────────────┬──────────────────────┘
                          ▼  next /rag/answer call
        ┌────────────────────────────────────────┐
        │  apply_learning_signal boosts the new   │  ← LOOP 4 CLOSED
        │  retrieval bundle toward the           │    (re-rank lands prior)
        │  preferred_evidence_ids; +pull-ins      │
        │  subject to cohort filter.              │
        └────────────────────────────────────────┘

           AE opens EvidenceDrawer on any row →
        ┌────────────────────────────────────────┐
        │ GET /evidence/:id/run-history           │
        │ chip renders "Seen in N runs"; click →  │  ← LOOP 5 CLOSED
        │ popover lists each prior run's          │    (deliverable #4)
        │ request_id + completed_at + surfaces.   │
        └────────────────────────────────────────┘

           Per-subcap rationale on D3 heatmap →
        ┌────────────────────────────────────────┐
        │ parsers.subcap_narrative_extractor      │  ← LOOP 6 CLOSED
        │ Vertex Pro structured-output            │    (deliverable #5)
        │ classifies pillar deep-dive body into   │
        │ per-subcap narrative rows; validator    │
        │ strips fabricated subcap_ids; heuristic │
        │ fallback fills any gaps. Cell rendered  │
        │ with data-source="llm"|"heuristic".     │
        └────────────────────────────────────────┘
```

The end-to-end contract (deliverable #6) is asserted by
`tests/test_full_ai_chain.py` — one test per step, 8 + 1 cross-step
assertions, all pure-logic so no flakes.

## Admin flow (job_executions, migration 020)

The admin surface is the operator console; every visible count must be
sourced from real backend data (never from the standalone wireframe
fixture). The contract:

| Surface | Backend source |
|---|---|
| Admin → Overview: "Drive crawl / Embeddings / Peer patterns" cards | `POST /api/v1/admin/jobs/{name}:execute` + 3s polling on `/jobs/executions/{id}` |
| Admin → Overview: Vertex budget mini-tile | `GET /api/v1/admin/vertex-budget` |
| /admin/import: Job history table | `GET /api/v1/admin/jobs/executions?limit=50` |
| /admin/import: Drive crawl tiles | `GET /api/v1/admin/import-audit/summary` |
| /admin/import/audit: 4 tiles | `GET /api/v1/admin/import-audit/summary` |
| /admin/import/audit: Files tab | `GET /api/v1/admin/imports/audit` (existing) |
| /admin/import/audit: By-client tab | `GET /api/v1/admin/import-audit/by-entity` |
| /admin/import/audit: client-drilldown drawer | `GET /api/v1/admin/import-audit/entities/{id}` |
| File retry button | `POST /api/v1/admin/imports/files/{id}:retry` |

`job_executions` (migration `020`) is the canonical row workers MUST
update at start, at meaningful milestones (counters), and at completion.
The 4-branch status matrix (`running / succeeded / failed / cancelled`)
gates UI polling — once status flips, the View-log drawer surfaces
`stderr_tail` for failed runs.

Role toggle (chrome.jsx → app-root.jsx): `effectiveRole(realRole, actingAs)`
is downgrade-only — an AE who tampers with `can_act_as` to include
"ADMIN" still gets clamped to AE via the `a <= r` rank guard. The
SettingsPopover "ACTING AS" segmented control persists the selection
to `localStorage['dma:acting-as']` and rehydrates on signIn / reload.
Sidebar links re-render on role change because the `role` value is the
same React state cell that gates the JSX.

## Standalone surface — additional loader contracts

> **Status (ADR 0016, 2026-05-29):** the standalone single-file build
> (`frontend/standalone-src/`) is the **stakeholder-demo / wireframe-
> guide artifact**, NOT the live AE surface. Production is the
> Vite/React bundle at `frontend/dist/`. The loader contracts below
> document the standalone bundle's `window.DMA.*` keys for that
> demo build; the React tree at `frontend/src/` uses TanStack-Query
> hooks in `lib/queries.ts` for the same endpoints.

The following `window.DMA.*` loader keys are part of the standalone
demo build's contract — pages read them on mount and fail-closed
when absent:

- `DMA.evidence.runHistory(evidenceId)` → `/api/v1/evidence/{id}/run-history`
  Drives `SeenInRunsChip` inside `EvidenceDrawer`. State branches:
  `404` (silent), `n_runs<=1` ("First seen" muted), `n_runs>=2`
  ("Seen in N runs" + popover).
- `DMA.crossPillar.storiesForEntity(entityId, {pillar})` →
  `/api/v1/entities/{id}/cross-pillar-stories?pillar=P1..P4`. Drives
  `CrossPillarStoriesPanel` on D5 Context. Empty/404 → panel renders
  nothing (fail-closed); empty after filter → contextual empty state.
- `DMA.admin.uploadCatalogue(file, version?)` → POST FormData to
  `/api/v1/admin/catalogue:upload`. Drives the "Upload next version"
  button on the V7 catalog tab. Backend endpoint is not yet exposed
  (frontend wired; server returns 404 → actionable toast).

Standalone files now exported on `window` for cross-module re-use +
test reach: `SeenInRunsChip`, `CrossPillarStoriesPanel`,
`CatalogUploadCard`.

## Live progress

See `docs/STATUS.md` for the full end-to-end QA matrix mapping every plan
gate to PASS / PARTIAL / PENDING. Headline as of the current commit
(2026-05-28 audit waves 1-5 landed):

- Backend: 60+ API routes registered, 1137 tests green, ruff clean.
  Alembic head = `023_focus_areas_reconcile` (focus_areas schema reconcile +
  hot-path indexes on runs + evidence_index). Prod-readiness guard armed:
  `assert_production_ready(settings, role="backend"|"worker")` -- enforces
  7 secrets for backend (Clay deferred this version — ADR 0010 fail-closed), 2 for workers.
- Frontend: Vite-built React/TS bundle at `frontend/dist/` is the
  production surface per **ADR 0016** (2026-05-29, supersedes ADR
  0011). `frontend/standalone-src/` retained as the stakeholder-demo /
  wireframe-guide build only. React tree has TanStack-Query hooks on
  every endpoint (queries.ts) and renders real data or per-page empty
  state — no global "Backend data failed to load" banner. 222 vitest
  tests green, tsc clean.
- Workers: 7 Cloud Run Jobs declared in Terraform (drive_crawler,
  sheet_poller, embedder, ccg_loader, peer_patterns, intelligence_recompute,
  chat_learning), all wired through `_runner.track_job_execution` for live
  job_executions tracking. historical_backfill (backend image) writes per-
  folder backfill_quarantine rows for `--retry-failed-only`.

## Hard rules

- Do NOT modify `apps/capability-intelligence/` — that's the sibling app.
  Import `app.services.dma_handoff` as a vendored package; never duplicate.
- Do NOT introduce Next.js, React Router, or any state library beyond Zustand
  + TanStack Query. The prototype uses hash routing — we port it verbatim.
- Do NOT commit secrets. OAuth `client_secret`, bot API key, RAG API key all
  live in Google Secret Manager only.
- Do NOT bypass the per-run `ccg_catalog_version` resolver. Every UI/API
  surface that touches a `subcap_id` reads through `CatalogueResolver`.
- Do NOT serve un-validated Gemini output to AEs. Every surface runs the
  post-generation validator and falls back to template-fill on any flag.
