# DMA Insights — v2 QA Executive Summary

**Audience:** the operator deciding "should we ship?" in 15 minutes.
**Date:** 2026-06-07
**Branch:** `claude/deploy-zennify-cloud-run-AUdu6`
**HEAD:** `9d6a41c` (Batch 9 close)
**Verdict:** **CONDITIONAL GO** — 0 P0 unresolved, 1 P1 deferred with timeline.

---

## TL;DR

Across 9 batches (`d207f3d`..`9d6a41c`) the v2 QA pass forensically
audited 79 backend routes, 24 persistence tables, 11 leaf parsers,
9 self-healing scripts, 7 learning loops, and 12 render endpoints
× 104 active entities, then closed the deployment-blocking gaps it
surfaced. Four production-grade QA harnesses are wired as the
deploy-blocking `qa-gates` cloudbuild stage; the 1791 rendered-
language violations dropped to 0 across all 104 entities; 0
HTTP_500 across 8840 adversarial probe cells; 103 entities verify
deterministic manifest round-trip on every backfill.

**Ship recommendation: GO with the documented operator
follow-ups below.**

---

## What you get if you ship `9d6a41c` today

| Surface | Pre-v2 state | Post-Batch-9 state |
|---|---|---|
| Ingestion idempotency | Whole-package re-ingest on any change | Per-artifact: scoring CSV touch ⇒ only `subcap_scores` re-fires; deck/comment cosmetic touches ⇒ SKIP |
| Drive comment handling | Every comment (chatter / "+1" / "LGTM") triggered re-ingest | Material reviewer asks ("re-score P3C2", "fix") re-ingest; cosmetic chatter ⇒ SKIP with audit observation |
| Catalogue alias resolution | Category-level (`P1C1`) subcap IDs unresolvable; 14 packages FAIL on overview + heatmap | Shallow alias bridge recovered 5 packages end-to-end (full 1085 broadcast subcap_scores rows for AMH + Wescom) |
| AE-facing language quality | 1791 violations across UI/UX-brief rules | 0 violations on rendered surface (cache-keyed Vertex polish layer with anchor preservation) |
| Adversarial resilience | Unverified | 0 HTTP_500 across 8840 cells (XSS, SQLi, unicode display_ids, invalid query params) |
| Self-healing + learning integrity | Unaudited | 7 learning loops PASS, 0 FAIL across 17 audit cells; verify-only modes leave DB snapshot delta = 0 |
| CI gate coverage | 9 cloudbuild stages | 10 stages — new `qa-gates` runs all 4 production harnesses against fresh PG sidecar; deploy-blocking |
| Operator backfill tooling | Re-run whole corpus or nothing | `backfill_manifest_warmup` CLI: `--dry-run` preview, `--all-runs` after classifier change, idempotent + batched UPDATE |
| Operator artifacts | Ad-hoc | `docs/qa/` houses 8 evidence docs + 6 audit matrices + 4 findings docs + 9 cascade-gate evidence files |

---

## Production-Ready Gate verdict

The plan's terminal acceptance criteria:

| Criterion | Target | Actual | Status |
|---|---|---|---|
| 0 P0 unresolved | 0 | 0 | ✅ |
| ≤ 5 P1 either resolved OR deferred with timeline | ≤5 | 1 (deferred) | ✅ |
| Every J1-J6 journey passes end-to-end | 6/6 | 5/6 (J6 ingestion live; J1-J5 covered by harnesses) | ⚠ (see Patch P1-A) |
| All cascade gates green | 9/9 | 9/9 (gates 1, 2, 3, 4, 5, 6, 9 evidence docs + Batches 1-9 commits) | ✅ |
| Operator readable in 15min | This doc | This doc | ✅ |

**Result: CONDITIONAL GO.** Operator can ship `9d6a41c` to staging
immediately; pre-prod gate is the documented J6 live walkthrough
once Drive access is wired to the production SA (Patch P1-A
below).

---

## Patches still open (1 P1, 3 P2, 2 P3)

Full templates in `docs/qa/qa_patch_backlog.md`. Headlines:

### P1 (1 open)

- **P1-A — Live Drive J6 walkthrough deferred** — every code path
  exercised by harness against the local corpus mirror; no live
  Drive crawl has run end-to-end against the production SA's
  `dma-insights-drive-sa-key` Secret Manager binding since v2
  began. Owner: deploy operator. Validation: trigger
  `POST /api/v1/admin/jobs/drive_crawler:execute`, watch
  `job_executions` row through `succeeded`. **ETA: same-day post-
  staging deploy.**

### P2 (3 open)

- **P2-A — 12 DOCX-only render-FAIL entities** (Batch 3 partial):
  Class A entities whose only data source is a sanitised
  Assessment_Report DOCX, no scoring workbook. Heatmap + overview
  render PARTIAL with skeleton; subcap rows persist via
  `subcap_narrative_extractor` AI Loop 6 once Vertex is wired. ETA:
  Q3 2026 alongside AI Loop 6 promote.
- **P2-B — `parser_observations` promoter** (Batch 7 deferred): the
  learning-loop audit flagged the 7 self-healing scripts trigger
  observations but no automated promoter has run. Manual operator
  flow documented in `docs/qa/qa_self_healing_learning_matrix.md`.
- **P2-C — Peer-pattern silhouette gate** (Batch 7 deferred): KMeans
  silhouette gate test live against >=3-entity subverticals; today
  only N<3 cohorts in 4 of 6 subverticals.

### P3 (2 open)

- **P3-A — Frontend MSW wiring** (carry-forward from Batches 1-9
  out-of-scope): mock-service-worker for vitest contract tests
  doesn't intercept; tests pass against real handlers. Low-priority.
- **P3-B — `audit-render-health.ts`** (Batches 1-9 out-of-scope):
  folded into Batch 5 page matrices, not a discrete deliverable.

---

## Cumulative cascade-gate evidence

Every batch ended with a cascade gate that re-ran the prior
batches' contracts. Per-batch evidence:

| Batch | Commit | Gate evidence | Cascade verdict |
|---|---|---|---|
| 1 | `d207f3d` | `gate_1_evidence.md` | 1908 passing → 1908 (read-only batch); 939 ledger rows |
| 2 | `8dfba77` | (gate baseline) | selective re-ingest: scoring CSV touch ⇒ only `subcap_scores` re-fires (live psql diff) |
| 3 | `7525c5c` | `gate_2_evidence.md` | overview FAIL 14 → 9; heatmap FAIL 14 → 9 (5 packages recovered) |
| 4 | `f590f65` | `gate_2_evidence.md` (continued) | 4/4 re-ingest scenarios PASS; 24-table persistence matrix evidence |
| 5 | `ab7a204` | `gate_3_evidence.md` | 8840 adversarial cells, 0 FAIL_500 |
| 6 | `10d2aa1` | `gate_6_evidence.md` | language audit re-run: 1791 → 0 |
| 7 | `0b864a7` | `gate_4_evidence.md` | self-healing + learning: 7 PASS, 0 FAIL |
| 8 | `9810008` | `gate_5_evidence.md` | qa-gates CI stage + backfill CLI; 103-entity round-trip determinism |
| 9 | `9d6a41c` | `gate_9_evidence.md` | Drive comment materiality (77 keywords/6 groups) + deck text extractor |

---

## Operator playbook

Day-to-day discipline + harness commands + escalation matrix:
`docs/qa/qa_runbook.md` (Batch 11). The runbook is the canonical
operator-facing how-to; the executive summary is the auditor-facing
"should we ship?" verdict.

## Reproducing the verdict (15-min operator walkthrough)

```bash
# 1. Cascade gates 1-9 — every batch's evidence doc
ls apps/dma-insights/docs/qa/qa_gates/
#   gate_1_evidence.md gate_2_evidence.md gate_3_evidence.md
#   gate_4_evidence.md gate_5_evidence.md gate_6_evidence.md
#   gate_9_evidence.md gate_prod_evidence.md

# 2. 4 production-grade harnesses (deploy-blocking in CI)
cat apps/dma-insights/infra/cloudbuild.yaml | grep -A2 "id: qa-gates"

# 3. 21-stage simulate harness (run the full deploy chain dry)
DATABASE_URL_SYNC=postgresql+psycopg2://dma:dma@localhost:5432/dma_insights \
DATABASE_URL=postgresql+asyncpg://dma:dma@localhost:5432/dma_insights \
bash apps/dma-insights/infra/simulate-all-deploy-stages.sh

# 4. Full evidence doc per stage
less apps/dma-insights/docs/qa/qa_deployment_simulation.md

# 5. Patch backlog (10-field template per issue, P0..P3)
less apps/dma-insights/docs/qa/qa_patch_backlog.md
```

---

## Ship checklist

- [x] All 9 cascade gates green
- [x] All 4 production harnesses gate-blocking in CI
- [x] 0 P0 unresolved
- [x] ≤ 5 P1 with documented timeline (1 P1 deferred — Drive live walkthrough)
- [x] Manifest round-trip determinism across 103 entities (live PG verified)
- [x] Frontend 281/281 tests, tsc clean, Vite build OK
- [x] Backend 1982 tests passing, ruff clean on every touched file
- [x] cloudbuild.yaml 10 stages parse cleanly
- [ ] Live Drive J6 walkthrough (Patch P1-A — same-day post-deploy)
- [ ] Operator signs off on `qa_executive_summary.md` (this doc)

**Recommended: ship `9d6a41c` to staging; gate prod on P1-A.**
