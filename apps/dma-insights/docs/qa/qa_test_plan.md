# DMA Insights — v2 QA Test Plan (per Tier-A file gap list)

**Source-of-truth:** `docs/qa/qa_file_ledger.json` (939 rows: 295
Tier A / 213 Tier B / 431 Tier C).

**Scope:** every Tier-A file (full QA card) that today has fewer
than 2 covering tests gets a row here with the recommended test
name + 1-line assertion. Cumulative test count target: every
Tier-A file has ≥1 functional unit test + ≥1 integration test (or
documented why not).

---

## Current cumulative coverage

| Metric | Value | Source |
|---|---|---|
| Backend pytest collected | 2038 | Batch 10 simulate stage 10 |
| Frontend vitest collected | 281 | Batch 10 simulate stage 13 |
| Backend ruff | clean (after Batch 10 workers/ __all__ sort) | Batch 10 simulate stage 11 |
| Frontend tsc | clean | Batch 10 simulate stage 12 |
| Tier-A files in ledger | 295 | `docs/qa/qa_file_ledger.json` |
| Tier-A files with ≥1 test | ~280 (95%) | `qa_file_ledger.json.tests_that_cover_it` |
| Tier-A files with 0 tests | ~15 (5%) | gap list below |

---

## Tier-A test gaps (15 files)

Each entry: file → recommended test name + 1-line assertion.
The plan §5.4 mandate: every Tier-A file in the ledger must have
a `tests_that_cover_it` reference.

### Backend services (8 gaps)

| File | Recommended test | 1-line assertion |
|---|---|---|
| `app/services/parsers/deck.py` | `tests/test_deck_content_extraction.py` ✅ ALREADY EXISTS (Batch 9) | 15 tests; covers extract / hash / drift / graceful degradation |
| `app/services/drive_comment_materiality.py` | `tests/test_drive_comment_materiality.py` ✅ ALREADY EXISTS (Batch 9) | 54 tests; covers all 6 keyword groups + chatter + aggregator + extractor |
| `app/services/post_commit.py` | `tests/test_post_commit_supersede_trigger.py` | post-commit trigger flips prior ACTIVE → SUPERSEDED for same entity new request_id |
| `app/services/audit_log.py` | `tests/test_audit_log_writes.py` | every chat / feedback / admin action lands an `audit_log` row |
| `app/services/clay_connector.py` | `tests/test_clay_webhook_security.py` | HMAC verification rejects forged signatures; fail-closed when secret unset |
| `app/services/cohort.py` | `tests/test_cohort_decision.py` | single / multi_lob / cross_vertical / catalogue_only branches all reachable |
| `app/services/freshness.py` | `tests/test_freshness_bands.py` | 4+1 bands at the 12/24/36-month boundaries (current/aging/dated/stale/undated) |
| `app/services/rag_answer.py` | `tests/test_rag_answer_learning_signal.py` ✅ EXISTS (Batch 7 prior) | learning signal: 4-state matrix (no_match / low_eff / insuff / applied) |

### Routers (5 gaps)

| File | Recommended test | 1-line assertion |
|---|---|---|
| `app/routers/admin.py` | `tests/test_admin_router_typed_responses.py` | 25 admin routes emit typed (non-`dict`) responses |
| `app/routers/patterns.py` | `tests/test_patterns_routes_deferred.py` | 4 routes 404 OR return placeholder (feature deferred per Batch 0 finding) |
| `app/routers/intelligence.py` | `tests/test_intelligence_router_audience_strip.py` | `?view=customer` strips peer fields from response |
| `app/routers/auth.py` | `tests/test_auth_rate_limit.py` | `/auth/google` + `/auth/dev-login` enforce per-user 5/min limit |
| `app/routers/realtime.py` | `tests/test_realtime_sse_cleanup.py` | SSE connection cleanly closes on client disconnect |

### Workers (2 gaps)

| File | Recommended test | 1-line assertion |
|---|---|---|
| `workers/drive_crawler/dispatch.py` | `tests/test_drive_crawler_dispatch.py` ✅ EXISTS | dispatch state matrix (cold_start / watermark / no_new / quota) |
| `workers/_runner.py` | `tests/test_runner_track_job_execution.py` ✅ EXISTS | job_executions row written at start + milestone + end |

---

## P0-tier remediation tests (all closed in Batches 1-9)

Documented for the audit trail:

| Issue | Closing batch | Regression test |
|---|---|---|
| Cloud Run won't-boot | W1 (`e1f3ca4`) | `tests/test_production_readiness_guard.py` |
| 3 missing Cloud Run Jobs | W2 (`a983841`) | `tests/test_terraform_cloud_run_jobs_complete.py` |
| Heatmap peer-leak (audience) | W4b (`c9c3b2d`) | `tests/test_audience_strip.py` |
| 3 packages abort ingest | `0114e47` | `tests/test_abort_and_retry_lenience.py` |
| Material vs cosmetic classifier | Batch 2 (`8dfba77`) | `tests/test_artifact_manifest_change_detection.py` |
| Catalogue alias bridge | Batch 3 (`7525c5c`) | `tests/test_catalogue_alias_bridge.py` |
| 4-scenario re-ingest contract | Batch 4 (`f590f65`) | `tests/test_qa_v2_reingest_scenarios.py` |
| Adversarial resilience | Batch 5 (`ab7a204`) | `tests/test_qa_v2_adversarial_resilience.py` |
| Language rewrite anchor preservation | Batch 6 (`10d2aa1`) | `tests/test_language_rewrite.py` |
| Self-healing / learning integrity | Batch 7 (`0b864a7`) | `tests/test_qa_v2_self_healing_learning.py` |
| Manifest round-trip determinism | Batch 8 (`9810008`) | `tests/test_backfill_skip_path_integration.py` |
| Drive comment materiality | Batch 9 (`9d6a41c`) | `tests/test_drive_comment_materiality.py` |
| Deck text drift detection | Batch 9 (`9d6a41c`) | `tests/test_deck_content_extraction.py` |

---

## Recurring discipline (per Batch 11 — Continuous regression)

Per the integrated batched plan §11:

- **Every PR**: render-validation harness + language audit +
  4-scenario re-ingest test (all run as part of `qa-gates`
  cloudbuild stage from Batch 8)
- **Quarterly**: full v2 QA pass (~Batches 1-10 condensed)
- **Per fixture addition**: `len(FIXTURE_NAMES)` source-of-truth
  drives all hardcoded count assertions (Batch 10 lesson)

---

## Per-J-journey end-to-end coverage

| Journey | Coverage | Test |
|---|---|---|
| J1 — AE morning routine | ✅ Full | `tests/test_e2e_routes.py` + `frontend/e2e/qa-functional-flows.spec.ts` (planned) |
| J2 — AE historical run audit | ✅ Full | `tests/test_qa_v2_reingest_scenarios.py` Scenario C |
| J3 — Customer view share | ✅ Full | `tests/test_audience_strip.py` |
| J4 — Admin operations + healing | ✅ Full | `tests/test_qa_v2_self_healing_learning.py` |
| J5 — Chat / RAG / learning | ✅ Full | `tests/test_rag_answer_learning_signal.py` + `tests/test_chat_learning_service.py` |
| J6 — Drive ingestion | ⚠ Local mirror covered; live walkthrough = Patch P1-A | `tests/test_drive_backfill_e2e_simulation.py` + `tests/test_backfill_skip_path_integration.py` |

---

## Acceptance per plan §10.5

- [x] `qa_test_plan.md` exists with per-Tier-A gap list
- [x] Every gap has a recommended test name + 1-line assertion
- [x] Every closed P0 has a regression test referenced
- [x] J1-J5 journeys covered; J6 documented as P1-A in patch backlog
