# DMA Insights — build charter

Next.js frontend + FastAPI backend + PostgreSQL, turning completed Digital
Maturity Assessments into 38 client-facing surfaces across 7 dashboards.
**The application never calls a model at request time.** All content is
produced ahead of time by a synthesis agent in Claude Cowork through a
dedicated MCP connector (built here too), which validates page payloads
against structured verdicts and promotes a run atomically — all six pages
or none. This app does ingestion, validation, storage, redaction and
rendering. It performs no inference, ranks nothing, writes no prose.
Target: Google Cloud Run (services `web`/`api`/`mcp`, Jobs
`worker`/`migrate`, three Scheduler triggers). Not done until live in prod.

## Repo layout

| Path | What |
|---|---|
| `docs/` | The six design docs (HTML, **read-only**); `docs/text/` greppable extractions (`scripts/extract_docs.py`) |
| `prototype/` | The working front-end prototype (JSX modules + `data.js` mock + `template.html` CSS). See its README for authority limits |
| `apps/web` `apps/api` `apps/mcp` `apps/worker` | The four deployables |
| `packages/shared` | Cross-service contracts, vocabularies, band fixture |
| `infra/` | `provision.sh` (one-time) + `deploy.sh` (every release), idempotent gcloud |
| `migrations/` | Alembic, expand–migrate–contract |
| `fixtures/` | Golden run (stage 1) driving the invariant tests |
| `apps/dma-insights/` | **Legacy snapshot of the prior app (2026-07-16). Reference only — do not extend it, do not import from it.** |

## Authority order — what wins when sources disagree

1. **Backend Schema** (`docs/text/DMA Insights - Backend Schema.txt`) — table shapes, enums, constraints, generated columns, DDL. 89 tables.
2. **TRD** — architecture, tiers, connector tool contracts, validation, vector tier, data platform config, API contracts, GCP mapping.
3. **Surface Specification** — every payload section's field contract, per-surface prompts, card anatomy, colour/band rules. **Payload shapes are law; never invent a field.**
4. **Implementation Plan** — stage order, per-stage deliverables and QA. Walk it in order; QA bullets are each stage's definition of done, implemented as tests.
5. **PRD** — intent/behaviour; consult when lower docs are silent on *why*.
6. **QA Report** — resolved contradictions. Check here first when two sources disagree.
7. **Prototype** — authoritative for **layout, interaction, visual rendering and band resolver boundaries only**. Data vocabularies partially superseded (below). Never copy its data-fetch logic.

Genuine conflicts this order does not resolve: **stop and ask the user** —
never pick silently. The two `docs/text/*.docx-upload` extractions
(MCP Specification, Surface Design Spec, 2026-07-29) are background
material; the HTML docs above supersede them where they differ.

## Invariants — violating any of these is a bug, whatever the tests say

1. **No model calls at request time.** Only embedding-model use is inside the MCP connector at submit (V4 grounding), local + deterministic. Serving path never touches it.
2. **Content enters only through the connector.** API writes = annotations + alert actions only, both behind `Idempotency-Key`. No endpoint writes serving content.
3. **Promotion is atomic across all six pages** — one transaction, `SELECT … FOR UPDATE` on the run row, ordered writers, all-or-nothing. Promoted staging rows are **retained** (fix one page, re-promote, without re-synthesising five).
4. **Fail-closed evidence.** Every cited id must resolve, belong to this entity and run, carry a verbatim excerpt (50–500 chars). `get_evidence` returns `found / not_found / foreign`; **`foreign` halts production**.
5. **Audience redaction is server-side and default-deny.** `internal_only` paths stripped for customer audience; `entity_ids` in cohort patterns stripped for **every** audience. The walker + tests + contract must make marking unavoidable.
6. **Four maturity bands, strict less-than, on the RAW score** before display rounding: `<2 Activating · <3 Building · <4 Competing · ≥4 Differentiating`; null → no score. `band_t` is a four-value enum; **M5/Transformational must not exist in code, enum or prose.** DB generated column ≡ frontend resolver; fixture test asserts agreement for every score in a golden run.
7. **No colour in any payload.** Raw score + band word + semantic flags (`is_thin_evidence`, `below_threshold`, `is_primary_gap`). Score→band→hex in exactly one frontend module. Thin evidence = dashed outline; fill means maturity and nothing else.
8. **Counts are computed, never stored** where a source of truth exists: T2 landscape recomputes from T1 register; `grounded_on` = length of citation list; directory reads one materialised view for header and rows.
9. **Derived values are computed or null** — never NaN, never a sentinel, never a default that looks like data. Undated evidence is `UNVERIFIED`, never current.
10. **The server allocates identifiers.** Agent creates only `ic_id, f_id, fa_id, ts_id, wn_id` (+ authored `rec_id`); everything else from the catalogue or `register_evidence` (dedup by content hash; ERS computed server-side, ignored if sent).
11. **The writer registry is an ordered list** (34 section writers). Order is load-bearing — unordered acquisition deadlocks under concurrent promotes. Test that the order is stable.
12. **Verdicts name the gate, the JSON path and the arithmetic.** Gate families: AG (analysis), SG (safeguard — renders to client with `plain_label` 8–18 words and explicit `NOT_RUN` + reason), ET (entity/identity), CG (contract/grain, incl. 0.05 grain tolerance). Plus contract pass and evidence pass. A failing SG **discloses and still promotes**; a failing evidence reason never does.

## Corrections to the prototype — do not copy these back in

| Prototype has | Build instead |
|---|---|
| Tech-stack layer keys `L2 L3 L4 L5` | `OPS · CUST · DATA · INFRA` (same four labels/pillar tags) — avoids collision with evidence levels L1–L4 |
| 3 stack statuses (no CLAIMED) | `CONFIRMED · INFERRED · CLAIMED · ABSENT`, **required** per row |
| Reachable-looking M5 band + hex `#185F60` | Four bands only; resolver has four branches |
| M2 hex ambiguity (`#B0EDD3` in docs) | **`#62D7B8`** (the resolver's value renders) |
| Freshness dot `Current/Aging/Stale` at 6/12mo | Keep dot, **relabel** (e.g. Fresh/Aging/Needs refresh); the evidence ladder (12/24/36/48mo, `CURRENT…ARCHIVAL`) governs all payload fields |
| One `safeguard gates` blob | Two arrays: `caps[]` (assessment applied) + `gates[]` (SG results) |
| Static client-side data | Everything through `svc_api` from serving tables |
| Its own surface naming | Surface Specification IDs (H4 = workbook grid, H1 = focus areas, H2 = cell evidence, …) |

Prototype-only surfaces **in scope**: value chain (optional heatmap
section), context sentiment, run/version diff — contracts in Surface Spec.

## Stack & deployment (GCP project `digital-maturity-assessor`)

- **web**: Next.js App Router SSR, Tailwind tokens per prototype; one colour-resolver module.
- **api**: FastAPI + SQLAlchemy(asyncpg). Cursor pagination by row comparison `(a,b) < (x,y)`; `ETag = run_id.promoted_epoch.audience`; Brotli/gzip as **app middleware** (Cloud Run doesn't compress); limits per TRD §19.
- **mcp**: Python MCP SDK, streamable HTTP, 12 tools; validation/gates/promote live here. Embedding model (384-dim MiniLM/BGE-small class) bundled in-image, CPU, L2-normalised, `vector_cosine_ops`, **HNSW m=16 ef_construction=64 created once at migration**. Scoped centroids: cell 0.62 / category 0.58 / pillar 0.55 / run 0.50; V4 abstains to recorded `NOT_RUN` when centroid <5 members.
- **worker + migrate**: Cloud Run Jobs (parse/embed batch; Alembic pre-deploy).
- **DB**: Cloud SQL PostgreSQL 16 Enterprise Plus, Managed Connection Pooling — transaction mode; **`mcp` on session mode** (promote holds locks). IAM auth via Cloud SQL Python Connector, `pool_recycle=1800` + `pool_pre_ping`. asyncpg behind pooler: `statement_cache_size=0`, `NullPool`. Extensions: `vector, citext, pg_trgm, pgcrypto`.
- **Redis**: Memorystore (claim leases, cache), Direct VPC egress. **GCS**: artefact bytes. **Secret Manager**: anything secret — never committed, never echoed. IAM DB auth → no DB password exists. No Anthropic key, no Clay key anywhere in this app.
- **Scheduler (all three mandatory)**: package scan → worker Job every 30 min; `corpus-gate-scanner` nightly + every CI run; `pack-exporter` nightly + on demand. The package scan is how runs come to exist — TRD §07's ten steps verbatim; idempotent (unchanged tree ⇒ creates nothing); `source_cell` and GCS artefact bytes cannot be backfilled; ingested tier read-only once scanned.
- **Local dev**: docker-compose (`pgvector/pgvector:pg16`, Redis, filesystem artefact store), prod-parity flags via env.

## Working discipline

- Follow the Implementation Plan's stage register **in order**; one stage per PR; each stage's QA bullets implemented **as tests**.
- Golden-run fixture early (stage 1); it drives the invariant tests (band DB↔frontend, redaction snapshots, grain tolerance, writer order, cross-page reconciliation, ETag/304, cursor stability).
- Deploy continuously: every stage ends with `infra/deploy.sh` against production and DoD verified at the production URL.
- Small diffs; expand–migrate–contract; `CREATE INDEX CONCURRENTLY`; grants in the same revision as the table.

## Adjudications made during the build (user-confirmed)

- **v7.0 has 16 categories (C1–C4 × four pillars), not the docs' 17** —
  the 17 was v5.0's count; user confirmed 2026-08-04. Cell counts are
  unchanged (851 = 205+292+164+190, including 165 sub-vertical variant
  cells like `P1C1.3.CU1`). v5.0 workbooks (17 categories, for lineage
  work): Drive folder `1rF9zdx1qF7BJ9t21eFdvZQW11Y5dUjy3`, staged at
  `gs://digital-maturity-assessor-catalogue-staging/v5.0/`. v5.0 loads as
  HISTORICAL (never `--make-current`): 836 cells, 17 categories.
  v5→v7 resolution: 795 direct · 10 bridged renames · 31 NOT_COMPARABLE —
  all 31 are P1C5 (ESG), the killed 17th category. Runs pinned to v5.0
  serve against it; cross-version diffs render P1C5 as NOT_COMPARABLE.
- v7.0 catalogue source of record: `gs://digital-maturity-assessor-catalogue-staging/v7.0/`.

## Open decisions — leave open, do not resolve silently

- Retention policy for superseded runs (default: retain).
- Visual treatment of `CLAIMED` vs `INFERRED` on the tech register (render distinctly-but-provisionally; flagged for design).
- Partitioning: **not yet** (triggers/strategies documented in TRD §17; do not pre-build).
