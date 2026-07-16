# DMA Insights — Infra Script Exit Code Key

Every script under `apps/dma-insights/infra/` documents its exit codes
here. CI test `tests/test_infra_exit_codes.py` parses every `exit N`
literal in the scripts and asserts that this file documents the code
for that script — adding a new exit without updating this key fails
the test loud.

## Conventions

- `0` — success (omitted from per-script tables below; default for every
  script unless noted)
- `1` — generic failure / unrecoverable error (script-specific cause in
  the table)
- `2` — caller error (bad argv, missing required env var, malformed
  input) — **except `migrate.sh --verify-only` which uses `2` for
  "drift detected, heal next"** (DELIBERATE inversion; the caller of
  migrate.sh `--verify-only` treats truthy as "go heal"; documented
  here to prevent future drift toward the more common "abort" meaning)
- `3..9` — script-specific failure modes (see per-script tables)

## Per-script

### `deploy-two-phase.sh`
The canonical multi-phase deploy orchestrator.

| Code | When | Recovery |
|------|------|----------|
| `1` | Phase 0.5 image-existence check, Phase 4 readyz probe (3 different sub-causes wired through the same `exit 1`), Phase 5 traffic promote failed, Phase 7 frontend deploy failed | Re-run with `--skip-build` after fixing the root cause printed in the failure block |
| `3` | Phase 1 `gcloud builds submit` failed | Inspect Cloud Build log via the URL the failure message prints |
| `4` | Phase 1.6 pre-deploy password verify failed | Run `recover-db-passwords.sh` manually then re-deploy |
| `5` | Phase 2 `gcloud run deploy --no-traffic` failed | Inspect the new revision via `gcloud run revisions describe` |
| `6` | Phase 3 `migrate.sh` failed | Inspect `gcloud run jobs executions logs read` |
| `7` | Phase 6 post-promotion `/healthz` failed | Check service URL responds via `curl`; re-run Phase 5 to flip back |

### `resolve-deploy-sha.sh`
Resolves the NEWEST deploy-branch SHA (first 7 chars = Cloud Build `SHORT_SHA`)
and syncs the working tree to it. Sourced by every build/deploy entrypoint so a
stale/wrong checkout can never ship an old image.

| Code | When | Recovery |
|------|------|----------|
| `3` | Not a git repo (e.g. a CI source-only tarball) | Run from inside the repo; callers fall back to their local-HEAD path |
| `4` | The deploy branch does not exist on `origin` | `export DEPLOY_BRANCH=<your deploy branch>` (or `git remote set-head origin <branch>`) |
| `5` | Working tree has uncommitted changes; refused to sync | Commit/stash them, or set `ALLOW_DIRTY_DEPLOY=1` to ship them under the resolved SHA |
| `6` | `git checkout -B <branch>` to the deploy-branch tip failed | Resolve the printed git error, then re-run |
| `7` | `git fetch origin <branch>` failed (network/credentials) — refused to fall back to the local HEAD, which may be stale (the old blanket fallback re-opened the bde8329 stale-deploy class) | Fix connectivity/auth and re-run; `DEPLOY_ALLOW_LOCAL_HEAD=1` deliberately deploys the local checkout with a loud warning |

### `migrate.sh`
DB migrations job runner; doubles as standalone drift-heal trigger.

| Code | When | Recovery |
|------|------|----------|
| `1` | Job execute failed / image-pin update failed / secret-roll retry failed twice | Inspect the `gcloud run jobs executions list` for the failed run; re-run with explicit `SHA=<deployed-sha>` if the standalone-mode SHA detection couldn't read the deployed image |
| `2` | (`--verify-only` only) Drift detected: schema delta found between alembic head and the live DB. **NOT** an error condition — caller treats `2` as "go run a heal" | The caller pipeline (deploy-two-phase Phase 3) runs the heal automatically; operator runs `bash migrate.sh` to heal manually |

### `deploy.sh`
The legacy single-phase deploy (kept for hotfix scenarios).

| Code | When | Recovery |
|------|------|----------|
| `1` | terraform apply failed | Inspect terraform output |
| `2` | bad argv / missing required env | Re-invoke with correct args |
| `3` | image build failed | Inspect Cloud Build log |
| `4` | DB password recovery failed | Re-run `recover-db-passwords.sh` |
| `5` | Cloud Run deploy failed | Inspect revision logs |
| `6` | Post-deploy health check failed | curl service URL; check IAM |

### `dma-psql.sh`
Operator psql shell against the live DB.

| Code | When | Recovery |
|------|------|----------|
| `2` | Missing required env (`PROJECT_ID`, `DB_INSTANCE`) | Re-invoke with env set |
| `3` | Cloud SQL Auth Proxy failed to start | Check IAM on the operator account |
| `4` | psql connection refused | Verify network egress allowed |
| `5` | Cloud SQL instance not found | Verify `DB_INSTANCE` matches terraform output |

### `ensure-db-ready.sh`
Pre-deploy DB liveness loop.

| Code | When | Recovery |
|------|------|----------|
| `1` | Cloud SQL describe failed | Check IAM + project ID |
| `2` | Bad argv / missing required env | Re-invoke correctly |
| `3` | Connection refused after retries | Cloud SQL is genuinely down; wait + re-run |
| `4` | Schema version mismatch on alembic_version | Run `migrate.sh` first |
| `5` | DB password drift detected | Run `recover-db-passwords.sh` |

### `force-heal-db.sh`
Aggressive password rotation + grant repair.

| Code | When | Recovery |
|------|------|----------|
| `1` | Secret Manager access denied | Check IAM on the operator |
| `2` | Cloud SQL user update failed | Check role on the SQL admin user |
| `3` | Verify-after-heal still drifting | Re-run with `--force-fresh-secret` |
| `4` | Connection refused mid-heal | Wait + re-run |
| `5` | Bad argv | Re-invoke correctly |

### `live-data-flow-gate.sh`
End-of-deploy live-data check.

| Code | When | Recovery |
|------|------|----------|
| `2` | Backend returned 5xx OR /entities/.../overview missing required keys | Inspect backend logs |

### `load-from-secret-manager.sh`
Hydrates an .env from Secret Manager.

| Code | When | Recovery |
|------|------|----------|
| `1` | Secret Manager access denied | Check IAM |
| `2` | Bad argv | Re-invoke |

### `post-deploy-refresh.sh`
Phase 8 cache invalidation + delta backfill.

| Code | When | Recovery |
|------|------|----------|
| `1` | Cloud Run job execute failed | Inspect job logs |
| `2` | Missing required env | Re-invoke |

### `preflight-cloud-sql.sh`
Pre-deploy Cloud SQL preflight.

| Code | When | Recovery |
|------|------|----------|
| `2..4` | Cloud SQL instance not reachable / wrong tier / missing flag | The failure block prints the exact fix |

### `preflight-drive-folder.sh`
Pre-deploy Drive folder access check.

| Code | When | Recovery |
|------|------|----------|
| `1..6` | Drive folder missing / SA lacks Viewer / quota / IAM | The failure block prints the exact fix |

### `preflight-image-check.sh`
Verifies the SHA-tagged backend + frontend images exist in GCR.

| Code | When | Recovery |
|------|------|----------|
| `1` | Image not found for SHA | Re-run cloudbuild or pass `SHA=<built-sha>` |
| `2` | Bad argv | Re-invoke |

### `preflight-ops-sheet.sh`
Verifies the Ops Sheet is readable by the deployer.

| Code | When | Recovery |
|------|------|----------|
| `1..6` | Sheet missing / SA lacks Viewer / range mismatch | The failure block prints the exact fix |

### `preflight-parameters.sh`
Validates required env vars for the deploy.

| Code | When | Recovery |
|------|------|----------|
| `1` | Required env var missing | Set + re-invoke |
| `2` | Required env var malformed | Inspect format + re-invoke |

### `preflight-redis.sh`
Pre-deploy Memorystore preflight.

| Code | When | Recovery |
|------|------|----------|
| `1` | Memorystore not reachable | Check IAM + network |
| `2` | Wrong region | Match terraform output |

### `recover-db-passwords.sh`
Rotate the Cloud SQL user password to match Secret Manager.

| Code | When | Recovery |
|------|------|----------|
| `1` | Secret Manager / Cloud SQL access denied | Check IAM |
| `2` | Bad argv / `--verify-only` reported drift | Run without `--verify-only` to heal |

### `resolve-backend-url.sh`
Helper that prints the backend service URL.

| Code | When | Recovery |
|------|------|----------|
| `1` | Backend service missing | Re-deploy backend |
| `2` | Bad argv | Re-invoke |
| `3` | Backend service exists but `/healthz` returned 5xx | Inspect backend logs |

### `seed-and-run-e2e.sh`
CI: seed DB + run Playwright suite.

| Code | When | Recovery |
|------|------|----------|
| `3` | seed_ci failed | Inspect the seed log |
| `4` | Playwright suite failed | Inspect the Playwright HTML report |

### `setup-cloud-sql.sh`
One-shot Cloud SQL provisioning.

| Code | When | Recovery |
|------|------|----------|
| `2` | Bad argv / missing env | Re-invoke |
| `5` | Provisioning failed (quota / IAM / network) | The failure block prints the actionable hint |

### `setup-memorystore.sh`
One-shot Memorystore provisioning.

| Code | When | Recovery |
|------|------|----------|
| `2..5` | Provisioning failures (quota / IAM / network / wrong tier) | The failure block prints the actionable hint |

### `setup-pg-extensions.sh`
Enables pgvector + pgcrypto on a fresh Cloud SQL instance.

| Code | When | Recovery |
|------|------|----------|
| `2..5` | Connection / IAM / extension already present-but-different-version | The failure block prints the actionable hint |

### `verify-deploy.sh`
End-to-end deploy verifier.

| Code | When | Recovery |
|------|------|----------|
| `9` | One or more checks failed | Inspect the printed summary |

### `verify-frontend-sha.sh`
Confirms the frontend serves the deploying SHA via `<meta x-build-sha>`.

| Code | When | Recovery |
|------|------|----------|
| `1` | Backend service missing | Re-deploy backend |
| `2` | Bad argv | Re-invoke |
| `3` | SHA mismatch after retries | Force frontend redeploy |

### `simulate-all-deploy-stages.sh`
The local pre-push harness. Exits non-zero (`1`) iff any of its 24
stages FAIL; SKIPs are tolerated on the unrestricted sweep (but fail
an explicit `--stages` request). Stages 22–24 simulate the deploy-gate
logic added by master plan Part 14: the pack-freshness check-6
extraction vs a deliberately-stale manifest (must block; the
`_ALLOW_STALE_PACK` hatch must warn-pass), the `qa_gemini_surfaces`
cold gate vs `_ALLOW_COLD_GEMINI`, and a report-only `qa_pack_parity`
wiring check (`STRICT_PACK_PARITY=1` opts into the full strict gate
the cloudbuild regen stage runs).

### `backup-before-heal.sh`
Snapshots the live DB before a `force-heal-db.sh` run.

| Code | When | Recovery |
|------|------|----------|
| `0` | Backup snapshot succeeded (the only meaningful code; failure cases bubble through `set -e` rather than explicit `exit N`) | n/a |

### `build.sh`
Lightweight wrapper around `gcloud builds submit`.

| Code | When | Recovery |
|------|------|----------|
| `1` | Cloud Build submit failed | Inspect Cloud Build log via the URL printed |

### `drive_crawler` (workers/drive_crawler/main.py)
Cloud Run Job (6h Cloud Scheduler + daily discovery). Not an infra `*.sh`
script, but documented here because Cloud Run marks the scheduled
execution failed on any non-zero exit and `workers/_runner` flips the
`job_executions` row to FAILED — so the exit contract IS the run-status
contract the admin UI and scheduler alerts consume.

| Code | When | Recovery |
|------|------|----------|
| `0` | Success — **including PARTIAL-OK**: ≥1 folder ingested OK while others failed. Per-folder failures are printed as ✗ lines and counted in `files_errored`; a failed folder has no ACTIVE run, so the DB-ledger reconciliation re-picks it on the next 6h crawl. One flaky folder must not poison the run status (2026-07-06 contract) | None — check `files_errored` in the audit row if curious; the folder self-heals next cycle |
| `2` | `DRIVE_ROOT_FOLDER_ID` not set | Set the env var (terraform wires it) and re-run |
| `3` | Backend module import failed | Run on the backend image (PYTHONPATH must include `backend/`) |
| `4` | ADC unavailable — no Drive service | Check the job's service account / Workload Identity; see DEPLOYMENT.md §25.1 |
| `5` | Root-folder listing failed (`list_dma_folders`) | Verify SA Viewer access on the Drive root (preflight-drive-folder.sh) |
| `6` | Invalid `--since` value | Pass an ISO date |
| `7` | SYSTEMIC ingest failure — folders were attempted, ≥1 failed and ZERO ingested OK (every download dying, e.g. the 2026-07-06 shared-TLS-session incident) | Inspect the ✗ lines in the execution log; the failed folders stay candidates and are retried next crawl once the cause is fixed |

### `qa_gemini_surfaces` (backend/app/scripts/qa_gemini_surfaces.py)
Deploy-time per-surface Gemini assertions (master plan Part 3.3). Not an
infra `*.sh` script, but documented here because three deploy surfaces
consume its exit code: the `regen-startup-pack` Cloud Build stage
(`--mode baked`, HARD gate), `post-deploy-refresh.sh` §2c (`--mode
baked` against the live DB, best-effort), and
`backend/scripts/post-deploy-smoke.sh` check 8 (`--mode live`).

| Code | When | Recovery |
|------|------|----------|
| `0` | Every hard surface assertion PASSed — or failures were explicitly downgraded via `_ALLOW_COLD_GEMINI=true` (loud warning printed; pack manifest stamped `"gemini": "cold"`) | n/a |
| `1` | ≥1 hard surface assertion FAILED — the bake/deploy is Gemini-cold (no validator-passed `vertex_synthesis_cache` rows / no `parsed_facts._gemini_extracted` / heuristic-only focus areas / fallback RAG answer / no `source:"vertex"` why_now provenance) | Follow the per-check remediation the script prints: grant `roles/aiplatform.user` to the Cloud Build SA (`{project_number}@cloudbuild.gserviceaccount.com`; terraform `cloud_build_aiplatform_user`) for bake, the compute SA for runtime; verify `VERTEX_PROJECT_ID`/`GOOGLE_CLOUD_PROJECT` and that `DMA_DISABLE_VERTEX` is unset; or set `_ALLOW_COLD_GEMINI=true` to ship cold deliberately |
| `2` | Caller error — bad argv, `DATABASE_URL` unset (baked), `--base-url` missing (live) | Re-invoke with the missing parameter |
| `3` | Live mode: the deployed service is unreachable (`/healthz` never answered) | Check the Cloud Run revision/logs; this is an availability failure, not a Gemini one |

Note: `_ALLOW_COLD_GEMINI` is also honored by `assert_production_ready`'s
Vertex startup probe (backend role) and mirrors the Cloud Build
substitution of the same name — see DEPLOYMENT.md §26 "Gemini at deploy".

### Pack-freshness gates (`infra/cloudbuild.yaml` regen + frontend-image-smoke check 6; `backend/scripts/post-deploy-smoke.sh` check 9)
Master plan Part 14. Not infra `*.sh` scripts, but documented here because
the `_ALLOW_STALE_PACK` escape hatch spans three deploy surfaces. The
contract: the `regen-startup-pack` stage passes `SOURCE_SHA=${_IMAGE_SHA}`
into the regen containers; `export_startup_pages` stamps it into
`startup-data/pages_manifest.json` `source_sha` (and `export_startup_data`
into `manifest.json`/`scores.json`/`dashboard.json`); local runs without
the env stamp a truthful `local-<git short sha>`.

| Surface | Code | When | Recovery |
|------|------|------|----------|
| regen-startup-pack (exporter `step_hard`) | `1` | `export_startup_data` / `export_startup_pages` / `qa_pack_parity --strict` exited non-zero, or the freshly-exported manifest's `source_sha` ≠ `${_IMAGE_SHA}` — the frontend build would bake the STALE committed pack (the pre-Part-14 fail-open shipped this silently) | Fix the exporter failure printed above the error; re-run the build. Deliberate stale ship: `--substitutions=_ALLOW_STALE_PACK=true` (loud warning) |
| frontend-image-smoke check 6 | `4` | The BAKED image's `/startup-data/pages_manifest.json` `source_sha` ≠ `${_IMAGE_SHA}` — regen failed upstream (committed pack baked) or a stale image/cache was reused | Same as above; check 6 measures the OUTCOME, so any upstream freshness miss lands here |
| post-deploy-smoke check 9 | contributes to `2` | The LIVE frontend serves a pack whose `source_sha` ≠ the deployed SHA — typically `--skip-build` reused an old image after data/derive changes | Rebuild + redeploy WITHOUT `--skip-build`; never `--skip-build` after data/derive changes (DEPLOYMENT.md §26.5 checklist) |
| regen-startup-pack / qa-gates (`qa_hollow_census --expect 15`) | `1` (script; qa-gates wraps as `12`) | The committed-corpus seed gated a hollow-package count ≠ the pinned 15. Both CI corpus stages seed with `DMA_ALLOW_HOLLOW=1` (the 15 known hollow baseline packages must ship as live clients — 2026-07-04 incident: the gate + repark parked them and only ~80 of 94 clients exported); the census re-arms the DATA_LOSS detection that escape disarms | MORE than 15 ⇒ diagnose a parser regression hollowing recs/evidence before touching the pin; FEWER ⇒ the corpus baseline improved — update `--expect` in `infra/cloudbuild.yaml` (both stages) deliberately. Live Drive ingestion never sets `DMA_ALLOW_HOLLOW` |

**`_ALLOW_STALE_PACK=true` is the ONE sanctioned escape** for all three
gates (Cloud Build substitution for the first two; env var for smoke
check 9, `ALLOW_STALE_PACK` also honored). Every use prints a loud
WARNING naming exactly what stale artifact ships. It does NOT downgrade
the Gemini gates — coldness (`_ALLOW_COLD_GEMINI`) and staleness are
separate escapes by design.

### Gemini enrichment sweeps (`app.scripts.enrich_corpus` / `app.scripts.enrich_empty_surfaces`)
2026-07-05 (a52f723 post-mortem: the sequential, unbudgeted sweeps ate
both their 1500s step timeouts AND the build's global deadline —
"context deadline exceeded"). Both sweeps now run bounded-parallel under
a wall-clock budget via `app/services/enrichment_runner.py`:
`DMA_ENRICH_BUDGET_SEC` (default 1200, auto-clamped under
`DERIVE_STEP_TIMEOUT_SEC` when set), `DMA_ENRICH_CONCURRENCY` (default 6;
8 in Cloud Build), `DMA_ENRICH_CALL_TIMEOUT_SEC` (default 120),
`DMA_ENRICH_BREAKER_THRESHOLD` (default 4 consecutive failures per
surface). The regen stage's `step_soft` additionally hard-guards every
best-effort step at 1800s.

| Code | When | Recovery |
|------|------|----------|
| `0` | Always — including budget exhaustion (`remaining=N BUDGET-EXHAUSTED` in the summary line) and Vertex-cold (`vertex cold: <reason>`) | None needed: every synthesized row persisted immediately; the NEXT invocation (explicit warm step, post-deploy refresh, next deploy) fast-skips done work via cache fingerprints and CONVERGES on full warmth. A persistent `vertex_cold` count with the same reason across builds ⇒ fix the IAM/env cause it names |
| `2` | Caller error — `DATABASE_URL` unset / unknown `--queries` name | Re-invoke with the missing parameter |
