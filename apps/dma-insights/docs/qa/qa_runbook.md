# DMA Insights — v2 QA Operator Runbook

**Audience:** the operator running QA harnesses, triaging results,
opening backlog items, or driving the quarterly v2 QA pass.

**Companion docs:**
- `qa_executive_summary.md` — 15-min "should we ship?" verdict
- `qa_full_report.md` — aggregate report across all 10 batches
- `qa_patch_backlog.md` — 10-field template per open issue
- `qa_gates/gate_prod_evidence.md` — Production-Ready Gate certificate
- `docs/QA-CONTRACT.md` — the standing PR contract (15 sections × stress tests)
- `docs/DEPLOYMENT.md` — deploy steps + Cloud Build cluster + post-deploy refresh

This runbook is **operator-facing.** Every command is paste-able from
a checkout at `/home/<user>/Accelerate/apps/dma-insights/`. Where a
command needs a live PG, the operator must have `DATABASE_URL_SYNC`
+ `DATABASE_URL` set; see § Env vars below.

---

## TL;DR — the 4 production-grade QA harnesses

```bash
# All four run automatically in CI as the qa-gates cloudbuild stage
# (Batch 8 `9810008`). Run them locally before pushing.

cd apps/dma-insights/backend

# 1. Render validation — 12 endpoints × 104 entities = 1248 cells
python -m app.scripts.qa_render_validation
# Healthy: ≥ 95% PASS+PARTIAL; PARTIAL = data-source="skeleton" (expected for DOCX-only entities)
# Block-on: any new FAIL beyond the 12 baseline DOCX-only Class A entities

# 2. Adversarial resilience — 104 × 12 × 7 probes = 8840 cells
python -m app.scripts.qa_adversarial_resilience
# Healthy: 0 FAIL_500 across all cells
# Block-on: ANY HTTP_500 (deploy-blocking — the contract is "no 500s")

# 3. Rendered language audit — < 50% of DB-baseline violations on served surface
python -m app.scripts.qa_rendered_language_audit
# Healthy: 0 violations on rendered surfaces
# Block-on: rendered count > db_baseline * 0.5 (the polish layer regressed)

# 4. Self-healing + learning audit — 17 cells (9 scripts + 7 loops + 1 cross)
python -m app.scripts.qa_self_healing_learning_audit
# Healthy: 0 FAIL; DEGRADED is acceptable when documented (Patches P2-B, P2-C)
# Block-on: any new FAIL (self-healing mutated DB; or a learning loop silently broke)
```

Each harness exits non-zero on its block-on condition. The
`qa-gates` cloudbuild stage runs them sequentially with hard-block
on any non-zero exit.

---

## Env vars (set once per shell)

```bash
# Local PG (matches docker-compose.yml + the local seed):
export DATABASE_URL="postgresql+asyncpg://dma:dma@localhost:5432/dma_insights"
export DATABASE_URL_SYNC="postgresql+psycopg2://dma:dma@localhost:5432/dma_insights"
export SEED_CI_PG_URL="postgresql+asyncpg://dma:dma@localhost:5432/dma_insights"
# Optional — only needed for live RAG/Vertex calls (offline default = template fallback):
# export GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa.json
# export DMA_GCP_PROJECT_ID=zennify-app-suite
```

**Hermetic safety:** `tests/conftest.py:_hermetic_secret_manager`
defaults-deny the Secret Manager fallback so a test that delenvs
both DSN vars cannot silently fetch the prod DSN. Override only with
`monkeypatch.delenv("DMA_DISABLE_SECRET_DSN_FALLBACK")` + an explicit
mock of `_try_secret_manager`.

---

## Restoring the canonical 104-entity DB state

The harnesses need ≥ 100 entities to exercise the full coverage
matrix. The destructive `test_seed_ci.py` + `test_live_db_integration.py`
tests DROP-and-RECREATE the schema during their runs, shrinking the
DB to the 6 sanitised fixtures. After such a test run, restore the
canonical corpus:

```bash
# 1. Drop + recreate schema with extensions
PGPASSWORD=dma psql -h localhost -U dma -d dma_insights -c "
  DROP SCHEMA public CASCADE;
  CREATE SCHEMA public;
  CREATE EXTENSION pgcrypto;
  CREATE EXTENSION vector;
"

# 2. Apply all migrations (head = 036_widen_data_source)
cd apps/dma-insights/backend
DATABASE_URL_SYNC=postgresql+psycopg2://dma:dma@localhost:5432/dma_insights \
  .venv/bin/python -m alembic upgrade head

# 3. Re-seed the full 113-package corpus (~3-5 min on local PG)
DATABASE_URL="postgresql+asyncpg://dma:dma@localhost:5432/dma_insights" \
DATABASE_URL_SYNC="postgresql+psycopg2://dma:dma@localhost:5432/dma_insights" \
  .venv/bin/python -m app.scripts.historical_backfill \
    --dir tests/fixtures/dma_packages_batches --force

# 4. Verify
PGPASSWORD=dma psql -h localhost -U dma -d dma_insights -c "
  SELECT COUNT(*) AS entities FROM entities;
  SELECT COUNT(*) AS runs FROM runs;
  SELECT COUNT(*) FROM entities e
    WHERE NOT EXISTS (SELECT 1 FROM runs r WHERE r.entity_id = e.id);
"
# Expected: 104 entities, 104 runs, 0 orphans (entities w/o runs)
```

Of the 113 packages, 8 are intentionally erroring per the Batch 0
findings (`The Bank of Missouri - DMA` has no MANIFEST.json or
canonical subfolders, etc.). The 105th entity (Haventree Bank) ingests
without a run when `runs.material_manifest_hash` was NULL pre-Batch-8;
the `backfill_manifest_warmup` operator CLI is the fix.

---

## Operator CLI reference

### Backfill manifest warm-up (Batch 8)

When a prod DB pre-dates migration 033/034, some runs rows have
`material_manifest_hash` + `artifact_manifest_json` columns NULL.
Re-ingests fall back to mtime checks and miss the per-artifact diff
benefit.

```bash
cd apps/dma-insights/backend

# Preview (no DB writes)
python -m app.scripts.backfill_manifest_warmup \
  --dir tests/fixtures/dma_packages_batches --dry-run
# Output: DRYRUN:<entity>: would update N run(s) (hash=..., manifest_files=N)

# Backfill only NULL rows (fast; idempotent)
python -m app.scripts.backfill_manifest_warmup \
  --dir tests/fixtures/dma_packages_batches

# Force refresh ALL runs (slow; use after artifact_manifest.classifier change)
python -m app.scripts.backfill_manifest_warmup \
  --dir tests/fixtures/dma_packages_batches --all-runs
```

Re-running with the same inputs is a no-op. Per-package batched
UPDATE: 1 SQL round-trip per package (`WHERE id = ANY(:ids::uuid[])`).

### 21-stage simulator

```bash
cd apps/dma-insights

# Full chain (5-15 min depending on PG state)
bash infra/simulate-all-deploy-stages.sh

# Subset of stages (skip slow pytest sweep)
bash infra/simulate-all-deploy-stages.sh \
  --stages 1,2,5,6,7,8,9,11,12,13,14,15,16,17,18,19,20,21

# Single stage in isolation (great for debugging)
bash infra/simulate-all-deploy-stages.sh --stages 3
```

Per-stage evidence in `docs/qa/qa_deployment_simulation.md`.

### Single-entity diagnostic

```bash
cd apps/dma-insights/backend

# Re-ingest one package with verbose output
DATABASE_URL=... DATABASE_URL_SYNC=... \
  .venv/bin/python -m app.scripts.historical_backfill \
    --dir tests/fixtures/dma_packages_batches/batch_03/Acuity\ Insurance\ -\ DMA \
    --force

# Inspect what was persisted
PGPASSWORD=dma psql -h localhost -U dma -d dma_insights -c "
  SELECT e.display_id,
         COUNT(DISTINCT s.id) AS scores,
         COUNT(DISTINCT ei.id) AS evidence,
         COUNT(DISTINCT ds.id) AS sections
  FROM entities e
  LEFT JOIN runs r ON r.entity_id = e.id
  LEFT JOIN subcap_scores s ON s.run_id = r.id
  LEFT JOIN evidence_run_links erl ON erl.run_id = r.id
  LEFT JOIN evidence_index ei ON ei.id = erl.evidence_id
  LEFT JOIN document_sections ds ON ds.run_id = r.id
  WHERE e.display_id = 'acuity-a-mutual-insuranc-0001'
  GROUP BY e.display_id;
"
```

### Cloud Shell `git pull` aborts on `.terraform.lock.hcl`

The default branch pins the Terraform lockfile (per Terraform's
recommendation — committed for reproducible provider hashes across
Cloud Build + operator machines; only `.terraform/` + `*.tfstate` +
`*.tfplan` are git-ignored). When an operator's local `terraform init`
modifies the same lockfile that an upstream commit also touched, `git
pull` refuses to overwrite the operator's local changes.

```bash
# Symptom:
# error: Your local changes to the following files would be overwritten by merge:
#         apps/dma-insights/infra/terraform/.terraform.lock.hcl

# Safe default — discard local lockfile edits, pull, regenerate locally:
cd "$HOME/Accelerate"
git diff -- apps/dma-insights/infra/terraform/.terraform.lock.hcl  # inspect first
git checkout HEAD -- apps/dma-insights/infra/terraform/.terraform.lock.hcl
git pull origin claude/deploy-zennify-cloud-run-AUdu6
( cd apps/dma-insights/infra/terraform && terraform init -input=false )
```

If the local diff added a meaningful provider/version the upstream
doesn't have, stash + pull + regenerate + commit:

```bash
git stash push -m "lockfile-local" -- apps/dma-insights/infra/terraform/.terraform.lock.hcl
git pull origin claude/deploy-zennify-cloud-run-AUdu6
git stash pop
( cd apps/dma-insights/infra/terraform && terraform init -input=false )
git add apps/dma-insights/infra/terraform/.terraform.lock.hcl
git commit -m "infra(terraform): reconcile lockfile after upstream pin"
git push origin claude/deploy-zennify-cloud-run-AUdu6
```

Full operator-runbook discussion lives at `docs/DEPLOYMENT.md`
§0.7 (operator note under terraform init/plan/apply).

---

## Interpreting harness output

### `qa_render_validation` output

Per-cell line format:
```
[<status>] <entity>/<endpoint>  <count_evidence> evidence  <count_subcaps> subcaps  data-source=<state>
```

| Status | Meaning | Action |
|---|---|---|
| `OK` | Full data present + rendered correctly | None |
| `PARTIAL` | Some data present; `data-source="skeleton"` for missing | None — expected for DOCX-only Class A entities |
| `FAIL` | Endpoint returned non-200 OR data shape broke | **Investigate immediately** — open backlog row |

The 24 baseline FAILs (12 DOCX-only entities × overview + heatmap)
are Patch P2-A — pending `subcap_narrative_extractor` AI Loop 6 wire.

### `qa_adversarial_resilience` output

Per-probe cell:
```
[<status>] <entity>/<endpoint> probe=<type>  http=<code>  detail=<...>
```

| Status | HTTP | Meaning | Action |
|---|---|---|---|
| `OK_2XX` | 200 | Probe returned valid data | None |
| `EXPECTED_4XX_PATH_MISMATCH` | 404 | Path doesn't match an existing route shape | None (intentional adversarial) |
| `EXPECTED_4XX_VALIDATION` | 400 | Probe rejected by Pydantic validator | None |
| `FAIL_500` | 500 | **Server error** | **Block deploy** — open P0 backlog row |
| `SCHEMA_VIOLATION` | 200 | Response shape broken (Pydantic validator regressed) | **Block deploy** — open P0 backlog row |

Contract: **0 FAIL_500 across the entire matrix** (8840 cells per
the Batch 5 baseline).

### `qa_rendered_language_audit` output

```
RENDERED-LANGUAGE AUDIT SUMMARY: N violations across N/104 entities
By rule: R1 / R2 / R3 / R4 / R5 / R6
PRODUCTION CONTRACT MET: rendered=N < db_baseline=1791 * 0.5 = 896
```

| Outcome | Action |
|---|---|
| `rendered=0` (current baseline) | None — polish layer working as expected |
| `rendered > 0 && rendered <= 896` | Investigate — log per-rule counts; the polish layer may need an additional rule |
| `rendered > 896` | **Block deploy** — the polish layer has fundamentally regressed |

### `qa_self_healing_learning_audit` output

```
[ PASS ] Loop N <name>
         <counters per loop>
[ DEGRADED ] Loop M <name>
         <counters per loop>
[ FAIL ] Loop K <name>
         <counters per loop>

# SUMMARY: N PASS, N DEGRADED, N FAIL (17 cells total)
```

| Cell | Acceptable states | Action on FAIL |
|---|---|---|
| Loops 1-7 | PASS or DEGRADED-expected (with documented reason) | Trace to source loop; open backlog |
| 9 self-healing scripts | All PASS in verify-mode | Trace mutation; revert pending fix |
| corpus_health (cross-loop) | PASS (0 entities with 0 runs) | Trace orphan entities; backfill |

When corpus_health FAILS with "entities with 0 runs > 0", restore
the corpus per § Restoring the canonical DB state above.

---

## Recurring discipline (Batch 11 cadence)

Per the integrated batched plan §11:

### Every PR

The `qa-gates` cloudbuild stage runs:

1. `qa_render_validation` against the seeded sidecar
2. `qa_adversarial_resilience` against the seeded sidecar
3. `qa_rendered_language_audit` against the seeded sidecar
4. `qa_self_healing_learning_audit` against the seeded sidecar

**Any non-zero exit hard-blocks the deploy.** No "warning-only"
mode by design — operator chose hard-block at Batch 8.

### Every quarter (full v2 QA pass)

Re-run the condensed Batches 1-10 against the current corpus:

```bash
# Step 1 — Spin up local stack
docker compose -f apps/dma-insights/docker-compose.yml up -d
# (or: sudo pg_ctlcluster 16 main start)

# Step 2 — Restore canonical 104-entity corpus
# (see § Restoring the canonical DB state above)

# Step 3 — Run the 4 harnesses + simulator
cd apps/dma-insights
python -m app.scripts.qa_render_validation
python -m app.scripts.qa_adversarial_resilience
python -m app.scripts.qa_rendered_language_audit
python -m app.scripts.qa_self_healing_learning_audit
bash infra/simulate-all-deploy-stages.sh

# Step 4 — Re-evaluate the patch backlog
less docs/qa/qa_patch_backlog.md

# Step 5 — Update qa_executive_summary.md with new metrics
```

### Per fixture addition

`FIXTURE_NAMES` in `backend/app/scripts/seed_ci.py` is the
source-of-truth tuple. Adding a fixture:

1. Add directory to `backend/tests/fixtures/dma_packages_sanitized/`
2. Add name to `FIXTURE_NAMES` tuple in `seed_ci.py`
3. Run `python -m pytest tests/test_seed_ci.py tests/test_live_db_integration.py` to confirm all hardcoded count assertions derive from `len(FIXTURE_NAMES)` (Batch 10 lesson)
4. Re-run all 4 harnesses against the expanded corpus

### When a P0 / P1 surfaces

Per `docs/QA-CONTRACT.md` § "When the contract is broken":

1. Triage finding → file follow-up issue → mark "in-doc-only" if not yet implemented → escalate to ADR if architecturally significant.
2. Add a stress test in the relevant PD/DEP/PROD segment.
3. Update `docs/qa/qa_patch_backlog.md` with a 10-field entry; include the TDD-by-revert validation.
4. Open commit; the `qa-gates` cloudbuild stage will block deploy if the new test FAILs.

---

## J1-J6 journey walkthroughs

### J1 — AE morning routine (8min, ~22 actions)

Login → Dashboard → Directory → ClientOverview(active) → Runs → Health(?tab=alerts)

```bash
# Smoke test as ADMIN JWT
TOK=$(python -c "
import uuid
from app.services.jwt_service import issue_token
print(issue_token(user_id=str(uuid.UUID(int=1)), email='admin@zennify.com', role='ADMIN', name='Admin'))
")
for path in \
  /api/v1/entities \
  /api/v1/entities/acuity-a-mutual-insuranc-0001/overview \
  /api/v1/entities/acuity-a-mutual-insuranc-0001/runs \
  /api/v1/entities/acuity-a-mutual-insuranc-0001/health; do
  curl -sS -H "Authorization: Bearer $TOK" "http://localhost:8000$path" | jq -r '.data | keys // []'
done
```

### J2 — Historical run audit (5min, ~15 actions)

Runs → ClientOverview(?run=OLD) → Heatmap(?run=OLD) → cell click → SynthesisDrawer(?run=OLD)

Test: `backend/tests/test_qa_v2_reingest_scenarios.py::test_scenario_c_new_run_same_entity_creates_superseded_chain`.

### J3 — Customer view share (4min, ~8 actions)

Audience toggle → ClientOverview rerender → Prospecting preview → Export PDF

Test: `backend/tests/test_audience_strip.py::test_internal_only_fields_stripped_on_view_customer`.

### J4 — Admin operations + healing (10min, ~18 actions)

Admin → Operations → trigger Drive crawl → poll job → see failure → force-heal `--no-roll`

Test: `backend/tests/test_qa_v2_self_healing_learning.py::test_self_healing_and_learning_loops_end_to_end`.

### J5 — Chat / RAG / learning (6min, ~10 actions)

Meeting prep → IntelligencePanel SSE → RAG question → response + evidence chips → 👍/👎 → re-rank next call

Test: `backend/tests/test_rag_answer_reranking.py` + `backend/tests/test_chat_learning_service.py`.

### J6 — Drive ingestion (operator-run, 5-15 min/fixture)

Drive folder upload → drive_crawler picks up zip → parse_package → 11 leaf parsers → persist_package → `dma.ingest.completed` Pub/Sub publish → embedder + intelligence_recompute fire

**This journey has the deferred P1-A live walkthrough.** Local
mirror covered by `backend/tests/test_backfill_skip_path_integration.py` (103 entities round-trip).

Live walkthrough on staging cut-over day:

```bash
# 1. Verify preflight
bash apps/dma-insights/infra/preflight-drive-folder.sh
# Expect: exit 0, "SA <email> has Viewer on folder <id>"

# 2. Trigger Cloud Run Job
ADMIN_TOK=...
JOBID=$(curl -sS -X POST -H "Authorization: Bearer $ADMIN_TOK" \
  https://<service>.run.app/api/v1/admin/jobs/drive_crawler:execute \
  | jq -r '.id')

# 3. Poll job_executions until status flips
for i in $(seq 1 60); do
  STATUS=$(curl -sS -H "Authorization: Bearer $ADMIN_TOK" \
    https://<service>.run.app/api/v1/admin/jobs/executions/$JOBID \
    | jq -r '.status')
  echo "[$i] $STATUS"
  [[ "$STATUS" == "succeeded" ]] && break
  [[ "$STATUS" == "failed" ]] && break
  sleep 30
done

# 4. Inspect import_scans audit row
psql -c "SELECT * FROM import_scans ORDER BY completed_at DESC LIMIT 1;"
# Expected: folders_seen >= 1, folders_new >= 0, folders_changed >= 0
```

---

## Defense-in-depth properties pinned (21 cumulative)

Per `qa_gates/gate_prod_evidence.md`. Re-verify periodically — each
property has its dedicated regression test:

1. Material vs cosmetic file classifier (`artifact_manifest.classify_path`)
2. Per-artifact diff → table set (`artifact_manifest.affected_tables`)
3. Selective `skip_tables` in `persist_package`
4. Manifest round-trip determinism across 103 entities
5. Cosmetic touch → hash unchanged
6. Material touch → hash changes
7. Catalogue alias bridge — broadcast subcap_scores
8. Heatmap data_source rollup (direct / shallow_broadcast / mixed)
9. 0 HTTP_500 across 8840 adversarial cells
10. Language anchor preservation (7-pattern validator)
11. Language rewrite reduces violations (1791 → 0 on rendered surface)
12. Self-healing scripts don't mutate in verify-only mode
13. 7 learning loops integrity (every entity has ≥1 run)
14. Operator backfill CLI idempotent
15. Drive comment classifier: empty body fails CLOSED (MATERIAL)
16. Drive comment classifier: word-boundary rejects affix/prefix
17. Drive comment classifier: material wins over cosmetic chatter
18. Deck text extractor: graceful degradation when python-pptx absent
19. Deck text drift: double-None returns False (no spurious flag)
20. Simulator harness: `FIXTURE_NAMES` source-of-truth (no stale `skip=5`)
21. Simulator harness: runtime entity_id lookup (handles clean + dirty DB)

---

## On-call escalation matrix

| Symptom | First check | Likely cause | Owner |
|---|---|---|---|
| `qa-gates` cloudbuild stage FAILs | Stage logs in Cloud Build console | Test data drifted in PR | PR author |
| 0 entities visible on `/clients` | `SELECT COUNT(*) FROM entities;` | Live DB was wiped or restore mid-flight | Deploy operator |
| Heatmap renders all skeleton | `SELECT COUNT(*) FROM subcap_scores WHERE run_id=$RUN_ID;` | Persist regression OR DOCX-only entity | Backend on-call |
| Adversarial harness FAIL_500 spike | Cell logs from `qa_adversarial_resilience` | Pydantic schema change without migration | Backend on-call |
| Rendered language violations > 0 | `python -m app.scripts.qa_rendered_language_audit` | Language polish layer regressed | Backend on-call |
| Self-healing audit FAIL on Loop K | Loop K source in `qa_self_healing_learning_audit.py` | Worker schema drifted | Worker on-call |
| Drive crawl returns 0 folders | `bash infra/preflight-drive-folder.sh` | SA lost Drive Viewer access | Deploy operator |

---

## Cumulative test count tracker

Updated automatically by `test_qa_contract_freshness.py` per push.
Current state:

| Surface | Count | Source |
|---|---|---|
| Backend pytest | 2038 | `pytest --collect-only -q tests/` |
| Frontend vitest | 281 | `pnpm exec vitest run --reporter=dot` |
| Live PG integration tests | 25 | seed_ci.py + live_db_integration.py + qa_v2_self_healing_learning.py + backfill_skip_path_integration.py + qa_v2_reingest_scenarios.py |
| QA harnesses | 4 | render / adversarial / language / self-heal+learning |
| Cascade gates | 10 | gate_1..6 + gate_9 + gate_prod evidence docs |

---

## Appendix — file inventory

```
apps/dma-insights/docs/qa/
├── qa_executive_summary.md        # 15-min ship verdict
├── qa_confirmed_blockers.md       # P0/P1 only
├── qa_full_report.md              # aggregate (every batch + every gate)
├── qa_patch_backlog.md            # 10-field template per entry
├── qa_test_plan.md                # per-Tier-A file gap list
├── qa_deployment_simulation.md    # 21-stage simulator evidence
├── qa_evidence_snippets.txt       # operator-grep'able file:line + cmd output
├── qa_runbook.md                  # THIS DOC
├── qa_contract_matrix.md          # 79 routes / 30+ hooks / 30 schemas / etc.
├── qa_file_ledger.{md,json}       # 939 rows (Tier A/B/C)
├── qa_visual_matrix.md            # 84 baselines
├── qa_persistence_matrix.md       # 24 tables × ACID × idempotency
├── qa_self_healing_learning_matrix.{md,tsv}  # 17 cells
├── qa_render_matrix.tsv           # 1248 cells (pre-v2 baseline)
├── qa_render_validation_findings.md  # 14 → 5 recovered (Batch 3)
├── qa_language_audit.{tsv,findings.md}  # 1515 → 0 violations
├── qa_rendered_language_audit.tsv # rendered surface = 0
├── qa_adversarial_matrix.tsv      # 8840 cells / 0 FAIL_500
├── qa_5folder_{live_findings,parse_audit}.{md,json}  # Phase 2 real-sample
├── qa_34package_validation.md     # Phase 2B real-sample matrix
├── qa_ingestion_under_leveraged.md  # Phase 2A under-leveraged matrix
└── qa_gates/
    ├── gate_1_evidence.md         # Batch 1 — ledger + matrices
    ├── gate_2_evidence.md         # Batch 4 — 24-table persistence
    ├── gate_3_evidence.md         # Batch 5 — adversarial
    ├── gate_4_evidence.md         # Batch 7 — self-heal + learning
    ├── gate_5_evidence.md         # Batch 8 — qa-gates CI + backfill CLI
    ├── gate_6_evidence.md         # Batch 6 — language rewrite
    ├── gate_9_evidence.md         # Batch 9 — comment materiality + deck
    └── gate_prod_evidence.md      # Batch 10 — Production-Ready certificate
```
