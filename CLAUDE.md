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
- **mcp**: Python MCP SDK, streamable HTTP, 36 tools; validation/gates/promote live here. Embedding model (384-dim MiniLM/BGE-small class) bundled in-image, CPU, L2-normalised, `vector_cosine_ops`, **HNSW m=16 ef_construction=64 created once at migration**. Scoped centroids: cell 0.62 / category 0.58 / pillar 0.55 / run 0.50; V4 abstains to recorded `NOT_RUN` when centroid <5 members.
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
- **Synthesis sessions are scheduled by the app, not by a human** (user,
  2026-08-04): when runs are pending, the system sets up a Cowork session
  running the `/dma-surface-production` skill against the client folders
  under the intake tree (General DMAs, folder
  `1xIClbzw-SRBJ0Et3SOWnb7YhcBM8b6mo`). The connector (stage 2) is that
  skill's counterpart; the scheduling automation lands with stages 2–3.
- Prod DB bootstrap (one-time, done 2026-08-04): extensions + database
  ownership to `dmai-migrate` + service-role authority were bootstrapped
  via an ephemeral postgres password, immediately rotated to a discarded
  value. `migrations/prod_apply.py` is the migrate Job entrypoint; its
  VERIFY log lines are the production proof (private-IP DB).

- **Gold-standard audit decisions** (user, 2026-10-04, after the SWBC
  audit — `plugins/dma-insights/docs/GOLD-STANDARD.md` is the gold doc;
  the old `docs/GOLD-STANDARD.md` path never existed):
  - **Sentiment reaches customers as a reduced card** — ratings bars +
    themes, no cell codes, internal sources, cap vocabulary or r_layer.
    Supersedes TRD §11's customer withholding for `overview.sentiment`
    only; `thought_leadership` stays withheld.
  - **Firmographics**: subsidiary/segment figures are admissible when the
    unit/basis names the entity; registry answers (charter, regulator,
    branches) are stated, never held; held fields are capped (≤2 or 25% of
    must-present, whichever is smaller) and a held field renders as a
    stated absence with its reason — never disappears.
  - **Connector-sourced evidence** (Indeed employer rating, CFPB complaint
    API) registers under origin `connector` with tool, query and
    retrieval date; Indeed T3, CFPB T1.
  - Defaults taken: identified peers may be named to customers as
    "identified, not scored"; discovery evidence splits into a shareable
    re-attributed span and an internal span; DECISIONS D4 stands
    (customer techstack rows CONFIRMED/ABSENT only); shape-only gold
    fixtures (no values) may be committed; WebSearch/WebFetch is the
    failover when Exa/Tavily credit runs out.
  - **Raw band vs Backend Schema** (authority #1 vs invariant 6): keep
    `composite` NUMERIC(4,2) for display as the schema states; an
    expand-only `composite_raw` column carries the raw value and the band
    is generated from it. `composite` is never widened.
  - **Gold-parity gate (CG-PAR / Gate J)** blocks only on structural gaps
    (a section or key the gold always serves is missing; a must-present
    field null or held beyond the cap). List-length and fill-ratio
    differences are warnings. Leave-one-out against gold; sub-vertical-
    matched gold preferred, cross-sub-vertical gold for structure only.

- **Enrichment and CAGR decisions** (user, 2026-10-05, after SWBC served
  a held CAGR, an empty sentiment bar and a register no scan had touched):
  - **Clay and Vibe Prospecting are admitted connector origins, tier by
    kind** (`connector.kind`): `technographic` readings T1 (a scan-only
    row stays INFERRED), `firmographic` readings (revenue band, LinkedIn
    headcount and growth) T3. Both scans are mandatory on a hand-driven
    run; ET-12 refuses a register that cites none and records no NOT_RUN.
  - **CAGR**: compute every candidate, rank by validity, serve only a
    figure an independent source corroborates; otherwise hold it with
    each candidate's rate and why (CG-18f).
  - **Star ratings fill from zero** (rating ÷ top star); other scales keep
    the range they state.

- **Arbor Bank audit decisions** (user, 2026-10-07, after the run promoted;
  root causes closed in code with tests, each named here so they do not
  recur):
  - **SG-V4 driver budget counts prose only** — verbatim leaves (`excerpt`,
    `verbatim_quote`, `quote`, `source*`, `title`, `product`, `candidate`,
    `url`) never count; `--sg-v4-budget N` is an owner decision recorded as
    a non-blocking `SG_V4_BUDGET_RAISED` Gate_Log row. SG-V4 itself skips
    producer metadata (`_V4_SKIP_KEYS`) on direct fields and whole subtrees.
  - **Owner ceilings persist**: `--max-usd` is remembered
    (`budget_usd_source: flag`); a resume without the flag never falls back
    to the per-pillar estimate.
  - **Peer figures are the cohort's, at cell grain where a cell is cited**:
    `get_cohort_benchmarks(subcap_ids=[…])`; the workbook's category rows
    are refreshed whenever a row is not cohort-sourced (a `table` row and a
    cohort row are kept; a guess is never replaced by a null); the fit
    engine fills gap-row peers from the same cohort at fit time (invariant 8).
  - **Platform ranking**: `INSUFFICIENT_EVIDENCE` ranks after every READY
    candidate; fusion never lifts it; an unevidenced prerequisite is not
    pulled ahead. `l3_area` names resolve through `ccg_l3_platforms`
    (`platform_name`, with or without vendor) to the `[L3-…]` code; an
    unresolvable label is reported in `unmatched[].resolved_to`.
  - **Evidence tiers**: the entity's own domain is never T1 (ledger refuses;
    `engine.cli retier` re-tiers with the label/ERS cascade and a logged
    reason). Package-local `e_id`s on FK columns resolve through
    `evidence_package_ids` at promote.
  - **Firmographics**: the engine's must-present set IS the connector's
    (`engine/schemas/firmographics_must_present.json`, vendored and
    test-asserted equal to `packages/shared/contracts_data.json`); the
    sub-vertical set is reported to the producer, the generic set gates
    PRELIM.
  - **Enforcement sweeps run as code** (`scripts/enforcement_search.py`:
    FDIC ED&O, CFPB, configured state order searches, with positive
    controls); a zero without a passing control is `NOT_RUN`, never a
    verified absence.
  - **AG-01 verdict vocabulary is read in pass 1** (local precheck), so a
    `WITHDRAWN`/`REJECT` verdict never costs a server round trip.
  - **Driver hygiene**: a passed page with no recorded ship time ships
    again (verdict-file mtime is the fallback); verdict files keep the full
    reason list; the manifest carries `supplementary_sub_verticals`;
    `Search_Log.Seq` is allocated past the highest value, never from the
    row count.
  - **Prevention over repair** (user, 2026-10-07: "I want preventive
    measures, hooks"): PRELIM gates the sub-vertical firmographic set
    while the run is in research; REPORTS runs the enforcement sweep;
    PAGES preflight refills cohort peers before any lane (ET-12 stays
    with `engine.page_preflight` → NEEDS_CONNECTOR; `engine.cli gate-log`
    records a hand-driven step's verdict); a mid-run connector deploy is
    logged as `CONNECTOR_DRIFT`
    and stales the pages passed under the old contract; a section file
    written under `08_sections/` is pass-1 checked by the
    `section_precheck.py` PostToolUse hook at write time.
  - **The search-op ceiling is per conversation, and the run-level reading
    is the worst conversation's window, named** (`ledger.worst_window`;
    `stats()` without a category). orient, the watchdog and the hooks print
    `search_ops_since_checkpoint` for that scope, never the lifetime count
    against the ceiling (a promoted run read "6332 against 60").
- **Client view review** (user, 2026-10-07, `DMA_customer_view_feedback.docx`):
  the customer audience is labelled **Client** in every reader-facing string
  (banner "Client Dashboard", "Switch back to Zennify view →"; the API value
  stays `customer`). The client view carries only Overview · Insights ·
  Heatmap (`CLIENT_TABS`, `apps/web/proto/utils.jsx` — one list for tab
  strip and router), and drops Meeting prep / the Intelligence panel,
  Request rerun, the executive narrative, leadership panel, financial
  trajectory and the Insights technology landscape. These are render-layer
  hides; the sections still promote and serve. `#/clients/<id>/<tab>?view=client`
  is the shareable **client link**: client audience locked, no sidebar /
  top bar / toggle, sticky for the document. Tests:
  `apps/web/tests/client-dashboard.test.js`.

## Open decisions — leave open, do not resolve silently

- Retention policy for superseded runs (default: retain).
- Visual treatment of `CLAIMED` vs `INFERRED` on the tech register (render distinctly-but-provisionally; flagged for design).
- H2/grid thin-evidence flag: DB generated column vs the H2 contract rule
  (they disagree on 144 SWBC cells).
- Techstack layer denominator (T-03/DNR-6): producer product slots vs the
  server's cell count.
- External access for the client link: the web service sits behind IAP and
  PRD v1 scopes out "a customer-facing portal — clients receive exports, not
  logins", so a client link opens only for someone IAP admits. Opening it to
  a non-Zennify recipient (IAP grant per client, or a tokenised public
  route) is a security/product decision for the owner.
- Partitioning: **not yet** (triggers/strategies documented in TRD §17; do not pre-build).
