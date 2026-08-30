# Phase 1 — environment health check (2026-08-18)

Every command below came from the repo's own docs: `.github/workflows/ci.yml`,
root `CLAUDE.md`, `docker-compose.yml`, `plugins/dma-insights/README.md`.

**Updated after the GCP service-account credential arrived.** The first pass
ran with no Google identity; the rows below are the state after
`mishleyotiende@digital-maturity-assessor.iam.gserviceaccount.com` was
activated. Superseded verdicts are shown struck through so the sequence stays
readable.

## Result per component

| Component | Verdict | Proof |
|---|---|---|
| Backend (api) | **PASS** | `uvicorn dma_api.main:app` starts; `GET /healthz` → 200 `{"ok":true,"service":"dmai-api","stage":"walking-skeleton"}`; 17 routes in `/openapi.json` |
| Backend tests | **PASS with 1 known failure** | `pytest apps/worker/tests apps/mcp/tests apps/api/tests scripts/tests -q` → **1247 passed, 1 failed, 4 skipped** (was 1239/2/4 + 7 errors before the catalogue was seeded). The one failure is F1 below |
| Frontend (web) | **PASS** | `npm ci` (99 pkgs) · `npm run build:proto` (15 files) · `npm run build` (7 routes) · standalone server serves `/` 200, `/status` 200 |
| Frontend tests | **PASS** | `npm run test:web` → **117/117 pass, 0 fail, 0 skipped** once `playwright-core` was installed (Chromium at `/opt/pw-browsers/chromium`) |
| Database | **PASS** | pgvector/pg16 + Redis up; IAM parity users present; `alembic upgrade head` → **0050**, 108 tables, VERIFY lines clean; `tests/schema/` → 34 passed, 13 skipped. Catalogue seeded: **`ccg_versions` v7.0 current, 851 cells, 16 categories, 851 platform-mapped** — matches the charter's adjudicated counts exactly |
| Architecture gates | **PASS** | `scan_secrets`, gate A, C, D, E, F all exit 0 |
| gcloud | **PASS** | CLI 581.0.0 at `/opt/google-cloud-sdk`; service account activated; project `digital-maturity-assessor`, region `us-central1`. Can list Cloud Run services and jobs, list Secret Manager secrets, read the catalogue bucket, and mint identity tokens |
| Connector (`dmai-mcp`) | **PASS** | `doctor.py --base-url …` → **all checks passed**, including "connector rejects an unauthenticated call — HTTP 403, IAM rejected it before the request was routed". `scripts/dma_connector.py list_pending_runs` returns the live queue |
| Plugin | **PASS** | marketplace `zennify-dma` added; `dma-insights@zennify-dma` installed + enabled with all three config values — `repo_root`, `mcp_base_url`, `mcp_path_token` (read from Secret Manager via command substitution, never echoed, never written to the repo) |
| Skills | **PASS** | 6 skills, 5 agents. `audit_skills.py`: **70/70 scripts OK, 0 broken refs**. `dma-deps check`: **13/13 present** |
| Login (local) | **PASS** | `ALLOW_DEV_LOGIN=1` + `POST /api/signin` → `{"ok":true,"role":"ADMIN"}`; page renders `authed:true`; non-`@zennify.com` correctly 403 |
| Login (deployed) | **BLOCKED — and now for a precise reason** | See B2 in `90-OPEN-QUESTIONS.md`. IAP on `dmai-web` grants `roles/iap.httpsResourceAccessor` to `domain:zennify.com` only; a `.iam.gserviceaccount.com` identity is not in that domain. Both candidate audiences return `Invalid JWT audience` |

## `CLOUDSDK_AUTH_ACCESS_TOKEN` — the trap the repo already documented

The harness injects a 14-character `CLOUDSDK_AUTH_ACCESS_TOKEN` into every
Bash call. It **outranks the activated service account**, and every gcloud
call then fails `UNAUTHENTICATED … ACCESS_TOKEN_TYPE_UNSUPPORTED`, which reads
like a permissions problem and is not.

`scripts/verify_deployed.py` and `plugins/dma-insights/scripts/mcp_auth_headers.sh`
both already strip it, with a comment saying why. **Every gcloud command in
this session must be preceded by `unset CLOUDSDK_AUTH_ACCESS_TOKEN`.**

## Production state read through the connector

`get_client_state("baxter-credit-union-bcu")`:

- entity `bea0d6e1-7e57-4818-a0cd-d788b8ac4787`, sub-vertical **SV2**, ACTIVE
- **run_seq 1 PROMOTED** · run_seq 2 SUPERSEDED · run_seq 3 INGESTED
- all three pinned to **`ccg_catalog_version: v5.0`**, composite **2.71**,
  **765 scored cells** — so the gold standard serves against v5.0, not v7.0,
  exactly as the charter says a v5.0-pinned run should
- all six pages served, promoted `2026-08-15T11:51:20Z`
- a newer INGESTED run (seq 3) exists and has not been synthesised

`list_pending_runs` shows a live queue with multiple runs per entity — the
duplicate-re-upload shape `scripts/synthesis_queue.py` exists to resolve
(e.g. Cathay Bank seq 1 and 2 under one request id; Capital Farm Credit seq 1
carries a stale claim from `cowork-scheduled-synthesis-20260805`).

## The catalogue seed, now done

```bash
gcloud storage cp 'gs://digital-maturity-assessor-catalogue-staging/v7.0/Pillar_*_v7.0.xlsx' <dir>/
cd migrations && LOCAL_DATABASE_URL=… python3 -m ccg_loader --version v7.0 --dir <dir>/
```

Loaded 21 `ccg_*` tables. Four `WARN … same-id rows (migrated, not bridged)`
lines are the loader reporting on `_R1_Source_Reference`, not failures.
The 7 API errors and 1 MCP failure it was causing all pass now (10/10).

## The remaining failure

**1 failure — a genuine finding, unrelated to the catalogue.**
`apps/mcp/tests/test_promote.py::test_a_retained_pass_is_revalidated_and_disclosed`
injects an off-vocabulary `timeline.arc_shape` into a *retained* context page
and asserts the promote still succeeds with disclosure. Actual result:

```
promoted: false
error:    retained_pages_fail_current_gates
pages:    [context]
reasons:  context → CG-09 at timeline.arc_shape (severity: block)
hint:     "... Safeguard (SG) reasons are excluded from this refusal and
           still disclose-and-promote, per the charter."
```

The implementation refuses only on **blocking** gates and its own hint states
that SG reasons still disclose-and-promote — which matches charter invariant
12. The test injects **CG-09**, a blocking contract gate, and still expects a
promote. Reading: the implementation was narrowed (commit `6e008b1` "A
retained PASS is a dated observation; promote was treating it as current") and
this test still encodes the older behaviour.

Claim label: **CONFIRMED** that it fails at HEAD against a migrated local DB —
and it still fails identically **after** the catalogue was seeded, which rules
out the catalogue as a contributing cause and leaves the attribution clean.
**HIGH** confidence the test, not the promote path, is the stale side.
Why it was never caught: the fixture calls `pytest.skip("no migrated local
database")` when Postgres is absent, and CI's `python-tests` job runs with **no
Postgres service** — so this test has never executed in CI. Reported, not
fixed: fixing it is outside onboarding scope and touches the promote path.

## Running processes (this session)

- Postgres `accelerate-db-1` :5432, Redis `accelerate-redis-1` :6379 (docker compose)
- API `uvicorn dma_api.main:app` :8080 with `LOCAL_DATABASE_URL=postgresql+pg8000://postgres:local@localhost:5432/dma_insights`
- Web `node .next/standalone/server.js` :3000 with `API_URL=http://127.0.0.1:8080 ALLOW_DEV_LOGIN=1`

**The docker daemon does not survive between tool calls unless it is
detached.** Start it as `setsid nohup dockerd … </dev/null &`, or the
containers vanish mid-session and the next database call fails with
`Can't create a connection to host localhost and port 5432`.

## Reproduce

```bash
setsid nohup dockerd >/dev/null 2>&1 </dev/null &
docker compose up -d
cd migrations && LOCAL_DATABASE_URL='postgresql+pg8000://postgres:local@localhost:5432/dma_insights' alembic upgrade head
pip install --ignore-installed PyJWT pytest openpyxl pg8000 -r apps/api/requirements.txt -r migrations/requirements.txt
cd apps/web && npm ci && npm run build
npm --prefix "$SCRATCH" install playwright-core
PLAYWRIGHT_CORE="$SCRATCH/node_modules/playwright-core" npm run test:web
python3 plugins/dma-insights/bin/dma-deps install

# with a Google identity:
unset CLOUDSDK_AUTH_ACCESS_TOKEN            # every gcloud call, without exception
gcloud auth activate-service-account --key-file=<key outside the repo>
gcloud storage cp 'gs://digital-maturity-assessor-catalogue-staging/v7.0/Pillar_*_v7.0.xlsx' "$SCRATCH/catalogue/v7.0/"
cd migrations && LOCAL_DATABASE_URL=… python3 -m ccg_loader --version v7.0 --dir "$SCRATCH/catalogue/v7.0/"
python3 plugins/dma-insights/scripts/doctor.py --base-url https://dmai-mcp-dukrne5v4a-uc.a.run.app
```
