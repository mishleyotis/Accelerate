# Phase 1 — environment health check (2026-08-18)

Every command below came from the repo's own docs: `.github/workflows/ci.yml`,
root `CLAUDE.md`, `docker-compose.yml`, `plugins/dma-insights/README.md`.

## Result per component

| Component | Verdict | Proof |
|---|---|---|
| Backend (api) | **PASS** | `uvicorn dma_api.main:app` starts; `GET /healthz` → 200 `{"ok":true,"service":"dmai-api","stage":"walking-skeleton"}`; 17 routes in `/openapi.json` |
| Backend tests | **PASS with 2 known failures** | `pytest apps/worker/tests apps/mcp/tests apps/api/tests scripts/tests -q` → **1239 passed, 2 failed, 4 skipped, 7 errors**. All 9 non-passes traced (below) |
| Frontend (web) | **PASS** | `npm ci` (99 pkgs) · `npm run build:proto` (15 files) · `npm run build` (7 routes) · standalone server serves `/` 200, `/status` 200 |
| Frontend tests | **PASS** | `npm run test:web` → **117/117 pass, 0 fail, 0 skipped** once `playwright-core` was installed (Chromium at `/opt/pw-browsers/chromium`) |
| Database | **PASS (schema) / BLOCKED (catalogue seed)** | pgvector/pg16 + Redis up; IAM parity users present; `alembic upgrade head` → **0050**, 108 tables, VERIFY lines clean; `tests/schema/` → 34 passed, 13 skipped. **`ccg_versions` = 0 rows, `ccg_subcaps` = 0 rows** |
| Architecture gates | **PASS** | `scan_secrets`, gate A, C, D, E, F all exit 0 |
| gcloud | **FAIL** | CLI 581.0.0 installed at `/opt/google-cloud-sdk`; project `digital-maturity-assessor`, region `us-central1` set. `gcloud auth list` → **"No credentialed accounts"**; no ADC; no metadata server |
| Plugin | **PASS (1 config unset)** | marketplace `zennify-dma` added, `dma-insights@zennify-dma` installed + enabled. `mcp_path_token` unset — it is a Secret Manager value, so it is gated on gcloud |
| Skills | **PASS** | `doctor.py` 8/10 (the 2 fails are the gcloud ones). 6 skills, 5 agents. `audit_skills.py`: **70/70 scripts OK, 0 broken refs**. `dma-deps check`: **13/13 present** |
| Login (local) | **PASS** | `ALLOW_DEV_LOGIN=1` + `POST /api/signin` → `{"ok":true,"role":"ADMIN"}`; page renders `authed:true`; non-`@zennify.com` correctly 403 |
| Login (deployed) | **BLOCKED** | `https://dmai-web-dukrne5v4a-uc.a.run.app/` → 302 to Google OAuth, body `Invalid IAP credentials: empty token`. Interactive Google sign-in with a zennify.com account is the only path |

## The 9 non-passing Python tests, traced

**7 errors + 1 failure — one root cause, the unseeded catalogue.**
`apps/api/tests/test_computed_against_the_real_schema.py` (7 errors) fails at
fixture setup with
`insert or update on table "runs" violates foreign key constraint
"runs_ccg_catalog_version_fkey" — Key (ccg_catalog_version)=(v7.0) is not
present in table "ccg_versions"`.
`apps/mcp/tests/test_bundle.py::test_catalogue_pins_the_run_version_with_names`
asserts `ccg_catalog_version == "v7.0"` and gets `None` — same missing row.

The seed step is `python -m ccg_loader --version v7.0 --dir <xlsx dir>`
(`migrations/ccg_loader/__main__.py`). The four pillar workbooks live at
`gs://digital-maturity-assessor-catalogue-staging/v7.0/`
(named in root `CLAUDE.md` and in `packages/shared/catalogue_v70_tier.json`).
No `.xlsx` exists anywhere in the checkout, so **this seed is gated on GCP
access.** Not a code defect.

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

Claim label: **CONFIRMED** that it fails at HEAD against a migrated local DB.
**HIGH** confidence the test, not the promote path, is the stale side.
Why it was never caught: the fixture calls `pytest.skip("no migrated local
database")` when Postgres is absent, and CI's `python-tests` job runs with **no
Postgres service** — so this test has never executed in CI. Reported, not
fixed: fixing it is outside onboarding scope and touches the promote path.

## Running processes (this session)

- Postgres `accelerate-db-1` :5432, Redis `accelerate-redis-1` :6379 (docker compose)
- API `uvicorn dma_api.main:app` :8080 with `LOCAL_DATABASE_URL=postgresql+pg8000://postgres:local@localhost:5432/dma_insights`
- Web `node .next/standalone/server.js` :3000 with `API_URL=http://127.0.0.1:8080 ALLOW_DEV_LOGIN=1`

## Reproduce

```bash
docker compose up -d
cd migrations && LOCAL_DATABASE_URL='postgresql+pg8000://postgres:local@localhost:5432/dma_insights' alembic upgrade head
pip install --ignore-installed PyJWT pytest openpyxl pg8000 -r apps/api/requirements.txt -r migrations/requirements.txt
cd apps/web && npm ci && npm run build
npm --prefix "$SCRATCH" install playwright-core
PLAYWRIGHT_CORE="$SCRATCH/node_modules/playwright-core" npm run test:web
python3 plugins/dma-insights/bin/dma-deps install
```
