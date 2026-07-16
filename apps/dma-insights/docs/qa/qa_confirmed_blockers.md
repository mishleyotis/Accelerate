# DMA Insights — v2 QA Confirmed Blockers (P0 / P1 only)

**Source-of-truth:** every entry here is also in
`docs/qa/qa_patch_backlog.md` with full 10-field template + TDD-by-
revert validation. This doc is the operator's "what blocks ship?"
filter.

**Verdict:** **CONDITIONAL GO** — 0 P0 unresolved, 1 P1 deferred
with documented same-day ETA.

---

## P0 (deploy-blocking) — 0 open

All P0s from the 2026-05-28 audit + Batches 1-9 are closed and
covered by regression tests. Nothing here.

### P0 historical — closed in v2 QA pass

| ID | Title | Closed in | Test that prevents regression |
|----|-------|-----------|-------------------------------|
| P0-WAVE-1 | Cloud Run won't-boot from missing prod env vars | 2026-05-28 W1 (`e1f3ca4`) | `tests/test_production_readiness_guard.py` |
| P0-WAVE-2 | 3 missing Cloud Run Jobs declared | 2026-05-28 W2 (`a983841`) | `tests/test_terraform_cloud_run_jobs_complete.py` |
| P0-WAVE-4 | `/ingest/assessment` dual-auth missing | 2026-05-28 W4 (`395a59c`) | `tests/test_ingest_security_and_idempotency.py` |
| P0-WAVE-4b | Heatmap peer-leak in customer view | 2026-05-28 W4b (`c9c3b2d`) | `tests/test_audience_strip.py` |
| P0-CORPUS | 3 packages aborted ingest on tier/score/cap-uniq | `0114e47` | `tests/test_abort_and_retry_lenience.py` |
| P0-RENDER | 14 entities FAIL render on overview + heatmap | partial — Batch 3 (`7525c5c`) recovered 5; 12 remain as P2 | `tests/test_catalogue_alias_bridge.py` |
| P0-LANGUAGE | 1791 rendered-surface violations | Batch 6 (`10d2aa1`) | `tests/test_language_rewrite.py` |
| P0-ADVERSARIAL | Unverified XSS / SQLi resilience | Batch 5 (`ab7a204`) | `tests/test_qa_v2_adversarial_resilience.py` |
| P0-SELFHEAL | Self-heal scripts could mutate prod DB | Batch 7 (`0b864a7`) | `tests/test_qa_v2_self_healing_learning.py` |
| P0-COMMENT | Cosmetic chatter triggered full re-ingest | Batch 9 (`9d6a41c`) | `tests/test_drive_comment_materiality.py` |
| P0-MANIFEST | No CI gate on the 4 production harnesses | Batch 8 (`9810008`) | `infra/cloudbuild.yaml` § `qa-gates` stage |

---

## P1 (pre-prod-blocking) — 1 open

### P1-A — Live Drive J6 walkthrough deferred

| Field | Value |
|---|---|
| **Title** | Live Drive J6 (operator ingestion) walkthrough not yet executed against production SA |
| **Severity** | P1 |
| **Surface** | `workers/drive_crawler/main.py`, `app/scripts/historical_backfill.py` |
| **Files** | `apps/dma-insights/workers/drive_crawler/main.py:103-182`, `apps/dma-insights/backend/app/scripts/historical_backfill.py:600-756`, `apps/dma-insights/infra/preflight-drive-folder.sh` |
| **Evidence** | All 9 batches developed against the local fixture corpus mirror (`tests/fixtures/dma_packages_batches/`, 113 packages). The live Drive crawl path is wired (`historical_backfill._ingest_folder`, `drive_crawler.main._run_ingests`, Pub/Sub publish, `dma.ingest.completed` subscription) but has not been triggered against the prod SA `dma-insights-drive-sa-key` since the v2 pass began. CI's `qa-gates` stage spawns a fresh PG sidecar with local-corpus seed; live Drive is environment-only. |
| **User/business impact** | None visible to AEs until the operator pushes to staging. Risk surfaces only on the first live-Drive crawl after deploy — if Drive scopes or SA permissions changed since `c400580` (Batch 0 — daily NEW-folder Drive probe), the crawl would fail with `403` / `404` on `_list_dma_folders`. |
| **Functional reproduction** | (a) Deploy to staging via `infra/deploy-two-phase.sh`. (b) Wait for Cloud Scheduler `drive-crawler-daily-discovery` at 02:00 CT, OR trigger manually via `POST /api/v1/admin/jobs/drive_crawler:execute` with admin JWT. (c) Poll `job_executions/{id}`. (d) Verify `import_scans` audit row landed with `folders_seen >= 1`. |
| **Root cause** | Out-of-scope for any of Batches 1-9 — v2 explicitly scoped to local corpus + harness work per the plan's "Out of scope: Live Cloud Run probes — mocked." |
| **Fix** | One-shot live Drive crawl from prod SA. Code change required = NONE; environment + SA scope verification only. |
| **Validation** | (1) `preflight-drive-folder.sh` exits 0 against the prod folder ID. (2) Trigger crawl; observe `job_executions.status = succeeded`. (3) `import_scans` row shows folders_seen > 0. (4) Embedder consumer `dma.ingest.completed` processes the published message. |
| **Regression risk** | Low — code path identical to the local-corpus path which is exercised by 5 Batch-8 live-DB integration tests + 4 production harnesses in CI. The only delta is environmental (real Drive API vs in-memory stub). |
| **Owner hint** | Deploy operator on the day of staging cut-over. ETA: same-day post-staging deploy. |
| **Status** | **OPEN — deferred** |

---

## P1 — historical closed

| ID | Title | Closed in |
|----|-------|-----------|
| P1-WAVE-5a | Schema drift on `focus_areas` + missing hot-path indexes | 2026-05-28 W5a (`707db15`) |
| P1-WAVE-5c | Chunked-upload OOM + zip-bomb + auth rate-limit | 2026-05-28 W5c (`13edb6f`) |
| P1-INGESTION | Synthetic `SYNTH-{sha1[:12]}` request_id when manifest omits | Batch 0 (`0114e47`) |
| P1-MTIME | Folder mtime change-detection missed file-level edits | Batch 2 (`8dfba77`) |
| P1-CATALOGUE | Category-level (`P1C1`) `SubCap_ID`s unresolvable | Batch 3 (`7525c5c`) — partial recovery (5 of 14) |
| P1-CACHE | Synthesis cache had no per-batch invalidation | Batch 6 (`10d2aa1`) — `language_rewrite` surface with TTL + fingerprint |

---

## Outstanding non-blocking (P2/P3) — see `qa_patch_backlog.md`

| ID | Headline | Severity |
|----|----------|----------|
| P2-A | 12 DOCX-only render-FAIL entities | P2 |
| P2-B | `parser_observations` automated promoter | P2 |
| P2-C | Peer-pattern silhouette gate live test | P2 |
| P3-A | Frontend MSW wiring | P3 |
| P3-B | `audit-render-health.ts` discrete deliverable | P3 |

---

## Decision matrix

```
P0 unresolved?          → 0  → ✓
P1 unresolved?          → 1  → ≤ 5 ✓
P1 with timeline?       → 1/1 ✓
J1-J5 journeys passing? → 5/5 ✓ (J6 = P1-A above)
Cascade gates green?    → 9/9 ✓
Operator ready to ship? → CONDITIONAL GO
```

Verdict: **CONDITIONAL GO**. Ship to staging; gate prod on the P1-A live walkthrough.
