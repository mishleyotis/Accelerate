# ADR 0004 — Three persistence tiers: Postgres / Redis / TanStack Query

**Status**: Accepted (2026-05-20)

## Context

DMA Insights serves 16 surfaces per client, plus a RAG API. Data freshness
needs vary wildly: SCQA narrative changes only on rerun (months); active-runs
counter changes second-by-second. The Claude project also queries our RAG
across all entities. We need clear ownership of "where does this value live
and when does it become stale?".

## Decision

Three tiers, with explicit invalidation contracts:

### 1. Postgres (canonical, shared, forever)

Authoritative for everything. **Once a DMA is ingested, all derived
artifacts persist forever.** Re-ingestion only on rerun (new `request_id` →
new `runs` row supersedes prior ACTIVE; `parent_request_id` links them).
Superseded runs stay queryable for version diff and historical RAG.

Tables: `entities`, `runs`, `subcap_scores`, `evidence_index`, `insight_cards`,
`recommendations`, `tech_stack_entries`, `firmographics`, `timeline_events`,
`issue_register`, `peer_benchmarks`, `platform_scores`, `safeguard_gates`,
`annotations`, `alerts`, `import_*`, `audit_log`, `document_*`,
`entity_assignments`, `dma_runs_requested`, `ops_*`, `evidence_embeddings`,
`insight_embeddings`, `recommendation_embeddings`, `user_session_state`,
`prompt_templates`, all `ccg_*` (versioned catalogue), `focus_areas`,
`build_qa_gates`.

### 2. Redis (per-user, ephemeral, ≤24h TTL)

- `dma:session:{user_id}:ui_state` — last-viewed entity, open drawers,
  current filters.
- `dma:session:{user_id}:recent_entities` — last 10 entities (App Flow §04).
- `dma:gemini:{cache_key}` — hot-path duplicate of `gemini_cache` table; DB
  is fallback.
- `dma:sse:entity:{entity_id}` — pub/sub channel for SSE fanout.
- `dma:catalogue:{version}:*` — hot read-through cache for `ccg_*` rows;
  invalidated when a new version is `frozen_at`.

### 3. TanStack Query client cache (per-user, per-tab, IndexedDB)

Page-level GETs cached with stale-while-revalidate (5 min default, 1h for
static V7 catalogue). Invalidated by SSE events: `run_ingested`,
`subcap_scores_updated`, `entity_updated`, `catalogue_version_promoted`.
Persisted via `persistQueryClient` so a tab refresh restores the cache.

## Consequences

- Drive is *not* a live cache. The `drive_crawler` worker reads it only on
  its 6h schedule (or admin-triggered), and only newly-modified files are
  re-parsed (`drive_modified_time` dedup).
- The Claude project's RAG API reads only from Postgres + pgvector — never
  hits Drive.
- A Postgres outage degrades the app to "last server-side cache" via Redis,
  then to "last client-side cache" via IndexedDB. The user still sees data;
  the chip in the top-right of each card says "data from cache" with the
  stamp time.
