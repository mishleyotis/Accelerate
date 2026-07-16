# DMA Insights — Self-healing + Continuous-learning Matrix (Batch 7)

Per the original v2 plan §4.1 + §4.2 and the integrated batched plan
Batch 7 spec: this doc audits the 9 self-healing infra scripts + the
7 continuous-learning loops. Every cell is verified against the live
DB; the cascade gate fails iff any cell reports FAIL.

Refresh:

```bash
cd apps/dma-insights/backend
export DATABASE_URL=postgresql+asyncpg://...
export DATABASE_URL_SYNC=postgresql+psycopg://...
python -m app.scripts.qa_self_healing_learning_audit \
    --output ../docs/qa/qa_self_healing_learning_matrix.tsv
# Exit code 0 if no FAIL cells; CI-gateable.
```

---

## §4.1 — 9-path self-healing audit

Each script is invoked in its safe mode (`--verify-only`, `--dry-run`,
`--check-only`, `--diagnose`, or `--help`). The harness asserts:

1. The script's safe mode RUNS without uncaught exception.
2. The script's safe mode produces ZERO row-count delta against the
   11 critical tables in `_SNAPSHOT_TABLES`. Any mutation in a
   verify-only path is a FAIL.
3. When the script needs GCP credentials and they're absent, the
   exit code + stderr pattern is matched against the "expected:
   no GCP env" classifier so the absence is documented (not flagged
   as a regression).

| # | Script | Safe-mode flag | Blast radius (full run) | Diagnostics | Exit codes | Rollback |
|--:|---|---|---|---|---|---|
| 1 | `ensure-db-ready.sh` | `--check-only` | Creates Cloud SQL instance + secrets + users if absent; pushes Terraform config; rotates passwords as needed | Logs each precondition + each remediation step | `0` ready / `1-4` per missing-state class / `7` lock contention | Each step idempotent; reruns are safe |
| 2 | `recover-db-passwords.sh` | `--verify-only` | Rotates Cloud SQL passwords + updates Secret Manager + rolls Cloud Run revisions | Captures Terraform diff before applying | `0` healed / `1` drift detected / `2` --verify only | Roll back via re-run with stored prior secret |
| 3 | `force-heal-db.sh` | `--verify-only` | Last-resort cred + revision force-roll; terraform `taint` + `apply` on `null_resource.db_*_setup`; revision roll | Each phase printed; cloud-sql-proxy port checked | `0` healed / `1` drift / `2-9` per failure class | Backup taken first via backup-before-heal.sh |
| 4 | `backup-before-heal.sh` | `--help` | Triggers on-demand Cloud SQL backup; verifies PITR + automated backups configured | Backup ID logged on completion | `0` backup taken / `1` PITR missing / `2` automated backups off | Backup snapshots restored via gcloud (operator) |
| 5 | `migrate.sh` | `--verify-only` | Runs alembic upgrade head; supports password recovery + diagnose mode | Per-revision SQL captured; pre-flight password verify | `0` aligned / `1` drift+heal failed / `3` revision-id overflow | `alembic downgrade` (operator) |
| 6 | `deploy-two-phase.sh` | `--diagnose` | Two-phase Cloud Run deploy: tagged revision → /readyz probe → traffic switch | Per-phase Pass/Fail; tag URL captured | `0` deploy success / `1-7` per phase failure | New revision exists but no traffic; old revision serves; deletable |
| 7 | `post-deploy-refresh.sh` | `--help` | Promotes traffic + triggers drive_crawler / embedder / intelligence_recompute jobs | Per-job exit status | `0` refresh complete / `1` promote failed / `2` job dispatch failed | Best-effort; failure leaves deploy LIVE |
| 8 | `build.sh` | `--dry-run` | `gcloud builds submit` → Cloud Build → GCR push | Per-image push log | `0` success / `1` build failed / `2` push denied | No rollback needed; old images stay in GCR |
| 9 | `verify-deploy.sh` | `--help` | Post-deploy smoke against the live revision | /healthz / /readyz / 4 sample API surfaces | `0` green / `1-9` per smoke failure class | None (read-only) |

**Plus 2 additional scripts** documented in the runbook but not in
the 9-path canonical list:
- `preflight-image-check.sh --check-only` — verifies the GCR image
  tag exists before deploy.
- `simulate-all-deploy-stages.sh` — 21-stage simulate harness
  (Batch 10 deliverable).

**Defense-in-depth property pinned** (`tests/test_qa_v2_self_healing_learning.py`):
- Every script's safe-mode invocation produces ZERO mutations against
  the 11-table snapshot. A future change that introduces a write in
  a `--verify-only` code path will fail this test in CI.

---

## §4.2 — 7-loop continuous-learning audit

The AI-chain has 7 closed loops (see CLAUDE.md "End-to-end AI chain").
Batch 7 verifies each loop has its production-impact integrity in
place against the LIVE DB. Live results from the audit harness:

| # | Loop | Read-side health | Live counts | Status |
|--:|---|---|---|---|
| 1 | `chat_learning` (nightly KMeans rolls feedback into `chat_learning_signals`; RAG router applies signals) | 4 tables queryable: chat_sessions, chat_messages, chat_feedback, chat_learning_signals | All 4 at 0 (no chat traffic in dev DB) | PASS |
| 2 | `parser_observations` (best-effort writes from sub-parsers; operator promotes recurring variants into source-code aliases) | Table writable; reads return int; aggregation by observation_kind succeeds | 166 rows; `unknown_column`=166 (the workbook-header variant kind) | PASS |
| 3 | `peer_patterns` (weekly KMeans rolls (entity x subcap-score) into peer_archetypes) | peer_archetypes table queryable | 0 rows (weekly worker hasn't run); 4 distinct subverticals available | PASS — populates on next weekly run |
| 4 | RAG feedback (chat_feedback POSTs feed Loop 1) | chat_feedback rating column queryable | 0 with rating (no AE feedback yet in dev DB) | PASS |
| 5 | `synthesis_cache` invalidation (`build_invalidation_for_new_run`, `build_invalidation_for_catalogue_bump`, `build_invalidation_for_feedback`) | vertex_synthesis_cache queryable; invalidation_reason populated correctly | **active=400, invalidated=249** (all 249 = `catalogue_bump_invalidate`; Batch 4 Scenario D's contract has been firing live) | PASS |
| 6 | `catalogue_alias_bridge` (category-shaped subcap_ids broadcast to v7.0 children) | subcap_scores.data_source='shallow_broadcast' rows; parent_category_id integrity check | **2776 broadcast rows across 5 entities, 17 distinct parent categories** (all matching `^P[1-4]C\\d+$`) | PASS |
| 7 | `intelligence_recompute` (Pub/Sub rollup into customer_intelligence_profiles) | customer_intelligence_profiles table queryable | 0 profiles / 104 entities (worker hasn't run; Pub/Sub-gated) | DEGRADED-expected — populates on Pub/Sub fan-out post-ingest |

**Cross-loop corpus_health:**
- 104 active entities; **0 entities with 0 runs** (persist pipeline holds across the full corpus)
- 12 entities with 0 subcap_scores (matches the Class A DOCX-only baseline documented in `qa_render_validation_findings.md`)

**Defense-in-depth properties pinned**:
- Loop 6 integrity: every broadcast row's `parent_category_id` matches `^P[1-4]C\\d+$` — a regression that wrote a malformed parent (`'garbage'`) would surface as a UI rendering bug; the audit catches it in CI before deploy.
- Loop 5 invalidation: the 249 live `catalogue_bump_invalidate` rows confirm the Batch 4 Scenario D contract is actively firing (not just test-time).
- Loop 1 chat_learning: tables are queryable with the expected schema (regression in chat_sessions / chat_messages / chat_feedback / chat_learning_signals would FAIL the test).

---

## Audit results (live DB)

Live results from `python -m app.scripts.qa_self_healing_learning_audit`:

| Category | PASS | DEGRADED | FAIL |
|---|---:|---:|---:|
| Self-healing scripts (9) | 2 | 7 (all DEGRADED-expected: no GCP env) | 0 |
| Learning loops (7) | 6 | 1 (Loop 7 worker not yet run) | 0 |
| Cross-loop (corpus_health) | 1 | 0 | 0 |
| **Total (17 cells)** | **9** | **8** | **0** |

**0 FAIL** — cascade gate PASSES.

---

## Operator playbook

When `qa_self_healing_learning_audit` reports a FAIL, the operator
runbook:

1. **Self-healing FAIL** — `_exec_script` rc != 0 AND not GCP-env-expected:
   - Inspect the stderr-tail in the harness output.
   - Run the script manually with `bash infra/<script>.sh --help` to
     see flag changes.
   - If the script's `--verify-only` mode crashed, the script itself
     has drifted — fix in source.

2. **Self-healing FAIL — `mutated state` observation**:
   - The verify-only mode wrote to one of the 11 snapshot tables.
   - This is a deploy-blocking regression.
   - `git blame` the script's most recent changes to find the
     mutation source.
   - Add the mutation back behind an explicit `--apply` flag.

3. **Learning-loop FAIL**:
   - Loop 2 (parser_observations) FAIL → migration 026 needs re-apply.
   - Loop 5 (synthesis_cache_invalidation) FAIL → vertex_synthesis_cache
     schema regressed (migration 019); re-apply.
   - Loop 6 (catalogue_alias_bridge) FAIL with `INTEGRITY: malformed
     parent_category_id` → a regression wrote a malformed broadcast
     row; check `package_persist.py:1090+` (the SubcapNotFound branch).

4. **Loop 7 (intelligence_recompute) DEGRADED**:
   - This is the expected dev-env state.
   - In prod, run `gcloud run jobs execute dma-insights-intelligence-recompute`
     to populate `customer_intelligence_profiles`.

---

## Files shipped by Batch 7

| Path | Status |
|---|---|
| `apps/dma-insights/backend/app/scripts/qa_self_healing_learning_audit.py` | NEW — 9 + 7 + 1 cell harness, CI-gateable |
| `apps/dma-insights/backend/tests/test_qa_v2_self_healing_learning.py` | NEW — pytest gate; single asyncio.run for engine-loop affinity |
| `apps/dma-insights/docs/qa/qa_self_healing_learning_matrix.md` | NEW (this file) |
| `apps/dma-insights/docs/qa/qa_self_healing_learning_matrix.tsv` | NEW — full audit TSV |
| `apps/dma-insights/docs/qa/qa_gates/gate_4_evidence.md` | NEW |
