# Architecture map — DMA Insights (repo `mishleyotis/Accelerate`)

Sources: root `CLAUDE.md`, `docs/text/*` (6 design docs), service READMEs,
`.github/workflows/ci.yml`, `infra/`, `plugins/dma-insights/README.md`.

## Two trees in one repo — which one is live

| Tree | What | Status |
|---|---|---|
| root `apps/{web,api,mcp,worker}` + `migrations/` + `packages/shared` + `infra/` | **The live build.** Next.js web, FastAPI api, Python MCP connector, Cloud Run Jobs worker/migrate. GCP project `digital-maturity-assessor`, region `us-central1`, services `dmai-web` / `dmai-api` / `dmai-mcp`, Jobs `dmai-worker` / `dmai-migrate`. | ACTIVE |
| `apps/dma-insights/` | Prior app (snapshot 2026-07-16): FastAPI backend + Vite/React frontend + Terraform + `cloudbuild.yaml`, with exported `startup-data/` for 186 clients incl. `baxter-credit-union-bcu-0001`. | LEGACY. Root CLAUDE.md: "Reference only — do not extend it, do not import from it." |

Both trees carry Baxter Credit Union. In the live build Baxter is
`baxter-credit-union-bcu` (sub-vertical SV2, credit union) and is called
"the reference client — the one promoted and serving in production"
(`apps/web/tests/acceptance/ACCEPTANCE.md:1200`).

## Stack and how the pieces connect

```
Google Drive intake tree (General DMAs, folder 1xIClbzw-SRBJ0Et3SOWnb7YhcBM8b6mo)
        │  Cloud Scheduler `dmai-package-scan`, every 30 min
        ▼
dmai-worker (Cloud Run Job, apps/worker/job_main.py)
        │  TRD §07 ten steps: walk tree → diff vs import_scans → classify artefacts
        │  → entity cascade → dedupe → parse scoring + research workbooks (source_cell)
        │  → artefact bytes to GCS → excerpt verification → scored_cells stamp
        ▼
INGESTED tier in Cloud SQL PG16 (read-only once scanned); run shows in list_pending_runs
        │
        │  ── synthesis (the ONLY writer of serving content) ──
        │  Claude Cowork session running skill `dma-surface-production`
        │  through dmai-mcp (streamable HTTP, secret path token + Google ID token)
        ▼
dmai-mcp (apps/mcp): claim_run → get_report_bundle / get_page_contract /
        get_capability_catalogue → register_evidence → open_payload /
        append_payload_part / submit_page_payload (validate pass1+pass2, gates)
        → promote_run  [one transaction, all six pages or none, 34 ordered writers]
        ▼
SERVING tables
        ▼
dmai-api (apps/api, FastAPI + SQLAlchemy/asyncpg) — read-only serving,
        server-side audience redaction (default-deny walker), computed counts,
        ETag = run_id.promoted_epoch.audience, cursor pagination, Brotli/gzip.
        Only writes: annotations + alert actions, behind Idempotency-Key.
        ▼
dmai-web (apps/web, Next.js 14 App Router SSR) — 38 surfaces / 7 dashboards /
        15 drilldowns. Single score→band→hex resolver module. Fronted by
        Cloud Run integrated IAP (Google sign-in, org-internal); the API
        independently verifies the ES256 IAP assertion (apps/api/dma_api/identity.py).
```

Supporting: Memorystore Redis (claim leases, cache), GCS (artefact bytes),
Secret Manager (all secrets; IAM DB auth so no DB password exists).
Two more Schedulers: `dmai-corpus-gate-scanner` (nightly 03:00),
`dmai-pack-exporter` (nightly 02:00), `dmai-enrich-loop` (hourly :07).

**Invariant:** the app never calls a model at request time. The only
embedding-model use is inside the connector at submit (V4 grounding).

## The DMA ingestion path — entry points and where a DMA lands

1. **Entry point A (automatic):** client folder lands in the Drive intake
   tree → `dmai-worker` package scan Job → ingested tier rows. Idempotent:
   unchanged tree creates nothing.
   Manual/inspection: `gcloud run jobs execute dmai-worker … --update-env-vars=INTAKE_STATUS=1`
   classifies every folder as `no_run · run_unparsed · parsed_unsynthesised ·
   synthesised_unpromoted · promoted_superseded · promoted_current`.
2. **Entry point B (the write door):** `dmai-mcp` tools. `apps/mcp/server.py`
   exposes the production tools (get_report_bundle, get_capability_catalogue,
   get_page_contract, get_evidence, get_run_progress, get_staged_payload,
   get_client_state, list_pending_runs, claim_run, register_evidence,
   open_payload, append_payload_part, submit_page_payload, promote_run,
   withdraw_run, list_withdrawn_runs, get_validation_verdict, explain_gate,
   list_enrichment_gaps) plus 11 findings-memory tools.
   Local transport client: `scripts/dma_connector.py`.
3. **Selection:** `scripts/synthesis_queue.py` decides which ingested run to
   synthesise next and states a reason for each skip (duplicate re-uploads,
   live claims, reruns).
4. **Landing:** promoted content lands in the serving tables, is read by
   `dmai-api` and rendered by `dmai-web`. Promoted staging rows are RETAINED,
   so one page can be fixed and re-promoted without re-synthesising five.

## The four rulebook artifacts

| # | Artifact | Where |
|---|---|---|
| 1 | **Gold standard — Baxter Credit Union** | The promoted, production-serving run `baxter-credit-union-bcu` (SV2). Cited as the calibration reference across `apps/api/dma_api/*`, `apps/mcp/dma_mcp/*`, `apps/worker/dma_worker/persist.py`, `apps/web/tests/acceptance/ACCEPTANCE.md`. Auditor: `scripts/audit_promoted_client.py` (nightly against prod; in CI against `fixtures/served` when present). Legacy exported copy of its 13 page payloads: `apps/dma-insights/startup-data/clients/baxter-credit-union-bcu-0001/`. |
| 2 | **Rules tests (pass/fail gates)** | `plugins/dma-insights/skills/dma-surface-production/05-lifecycle/1-gates.md` (the doc) → implemented in `apps/mcp/dma_mcp/{gates,validation,validation2,source_rules,vacuity,claims}.py`; tested by `apps/mcp/tests/*` (50 files). Local pre-submit checkers: `plugins/.../scripts/{check_payload,check_language,check_repetition,check_evidence,check_consistency,precheck_gates}.py`. Repo-level architecture gates: `scripts/gate_[a-f]_*.py` + `scripts/scan_secrets.py` in CI. Serving-side acceptance: `apps/web/tests/acceptance/`. |
| 3 | **Enrichment guidelines** | `plugins/dma-insights/skills/dma-surface-production/02-inputs/2-clay-enrichment.md` + `scripts/clay_plan.py`. App-side enrichment loop: `packages/shared/enrichment_register.json`, `packages/shared/enrichment_gaps.py`, `apps/worker/dma_worker/enrichment.py`, MCP `list_enrichment_gaps`. |
| 4 | **Reasoning guidelines** | `plugins/dma-insights/skills/dma-surface-production/04-craft/1-reasoning.md` (the R-Layer A–E). Supporting: `04-craft/2-platform-story.md`, `04-craft/7-storyline-challenge.md`, `04-craft/8-answered-questions.md`, `01-start-here/4-absence-protocol.md`. |

## Setup / onboarding docs to follow in Phase 1

- Root `CLAUDE.md` — charter, invariants, stack, local dev (docker-compose).
- `.github/workflows/ci.yml` — the authoritative command list for deps,
  migrate and every test suite.
- `docker-compose.yml` + `infra/local/pg-init/` — local Postgres/Redis parity.
- `plugins/dma-insights/README.md` — plugin + skill install, the two
  credentials, `/dma-insights:doctor`, `/dma-insights:setup-routines`,
  `bin/dma-deps`.
- `infra/README.md`, `infra/provision.sh`, `infra/deploy.sh` — GCP.
- `apps/{web,api,mcp,worker}/README.md` — per-service detail.
