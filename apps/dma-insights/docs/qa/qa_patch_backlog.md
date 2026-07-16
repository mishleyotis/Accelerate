# DMA Insights — v2 QA Patch Backlog

**10-field template per entry** (per the v2 plan):

```
ID | Title | Status | Severity | Confidence | Surface
Files | Evidence | Impact | Reproduction | Root cause | Fix
Validation (unit + integration + regression-by-revert)
Regression risk | Owner hint
```

**Discipline:** every entry's "Validation" row identifies the unit
test that pins the fix AND the regression-by-revert cycle (revert the
fix → assertion fires → re-apply → assertion passes), matching the
2026-05-28 audit Batches 7-9 + this v2 pass's per-batch evidence.

---

## P0 — closed

All P0s are closed and covered by regression tests. The discipline of
"revert the fix → test FAILs → re-apply → test PASSes" is exercised
per-PR via the `qa-gates` cloudbuild stage (Batch 8).

**0 open P0.** See `qa_confirmed_blockers.md` § P0 historical.

---

## P1 — 1 open

### P1-A — Live Drive J6 walkthrough deferred

```
ID         : P1-A
Title      : Live Drive J6 walkthrough not yet executed against prod SA
Status     : OPEN — deferred
Severity   : P1
Confidence : HIGH (code path identical to harness-covered local path)
Surface    : drive_crawler worker + historical_backfill CLI
```

**Files**:
- `apps/dma-insights/workers/drive_crawler/main.py:103-182`
- `apps/dma-insights/backend/app/scripts/historical_backfill.py:600-756`
- `apps/dma-insights/infra/preflight-drive-folder.sh`
- `apps/dma-insights/backend/app/services/pubsub_publisher.py`

**Evidence**: All 9 batches developed against the local fixture
corpus mirror (113 packages). Live Drive crawl code path wired
(`historical_backfill._ingest_folder`, `drive_crawler.main._run_ingests`,
Pub/Sub publish) but no live-Drive run executed against the prod SA's
`dma-insights-drive-sa-key` Secret Manager binding since the v2 pass
began.

**User/business impact**: None until staging deploy. Risk only on
first live-Drive crawl if Drive scopes / SA permissions drifted since
Batch 0 (`c400580`).

**Reproduction**:
1. Deploy to staging via `infra/deploy-two-phase.sh`.
2. Wait for Cloud Scheduler `drive-crawler-daily-discovery` at 02:00
   CT, OR trigger manually via
   `POST /api/v1/admin/jobs/drive_crawler:execute` with admin JWT.
3. Poll `job_executions/{id}`.
4. Verify `import_scans` audit row landed with `folders_seen >= 1`.

**Root cause**: Out-of-scope for all 9 batches — v2 explicitly scoped
to local corpus + harness work per the plan ("Out of scope: Live
Cloud Run probes — mocked").

**Fix**: One-shot live Drive crawl from prod SA. **No code change
required.** Environment + SA scope verification only.

**Validation**:
- *Unit* — `tests/test_drive_backfill_e2e_simulation.py` (passes; covers the simulator path)
- *Integration* — `tests/test_drive_backfill_discovery.py::test_recognises_real_folder_names` (passes; 10 real folder name shapes)
- *Regression-by-revert* — N/A (no code change; env verification only)
- *Live verification* — `preflight-drive-folder.sh` exit 0 + `job_executions.status='succeeded'` + `import_scans.folders_seen > 0`

**Regression risk**: Low — code path identical to local-corpus path
which is exercised by 5 Batch-8 live-DB integration tests + 4
production harnesses in CI. Only delta is environmental.

**Owner hint**: Deploy operator on staging cut-over day. ETA: same-day post-deploy.

---

## P2 — 3 open

### P2-A — 12 DOCX-only render-FAIL entities (partial recovery)

```
ID         : P2-A
Title      : 12 entities still PARTIAL on overview + heatmap (DOCX-only sources)
Status     : OPEN — partial recovery shipped Batch 3
Severity   : P2
Confidence : HIGH (root cause documented + path-forward defined)
Surface    : render endpoints (overview + heatmap) for 12 specific entities
```

**Files**:
- `apps/dma-insights/backend/app/services/parsers/subcap_narrative_extractor.py:33-258`
- `apps/dma-insights/backend/app/services/catalogue_alias_bridge.py:80-117`
- `apps/dma-insights/docs/qa/qa_render_validation_findings.md:152-194`

**Evidence**: `qa_render_validation_findings.md` documents 14 packages
initially classed FAIL on overview + heatmap. Batch 3
(`7525c5c`) recovered 5 via shallow catalogue alias bridge (AMH +
Wescom emit full 1085 broadcast subcap_scores rows; Bridgecrest + CI
Segall + East West Bank emit partial). The remaining 9-12 entities
(varies by harness run + corpus state) have ONLY a sanitised
`Assessment_Report.docx` — no scoring workbook, no
`evidence_index.csv`. The subcap rows need `subcap_narrative_extractor`
AI Loop 6 to project narrative paragraphs into scored rows.

**User/business impact**: For these entities, AEs see skeleton
overview cards + empty heatmap. The PARTIAL state IS surfaced via
`data-source="skeleton"` marker, so the UI doesn't lie — it
explicitly shows "no scoring data ingested." Operator workaround: ask
the analyst to re-run the bot pipeline with a scoring workbook.

**Reproduction**:
1. `bash infra/seed-and-run-e2e.sh` against fresh PG.
2. Visit `/clients/{12-entity-display-id}/overview`.
3. Observe: SCQA skeleton + empty heatmap; banner explains.

**Root cause**: Bot pipeline doesn't produce scoring workbooks for
deeply-historic DMAs; their only artifact is the analyst's prose
DOCX. `assessment_report.py` parses the DOCX into `document_sections`
but no `subcap_scores` rows exist.

**Fix (proposed)**: Wire `subcap_narrative_extractor` (Vertex Pro
structured-output, validators V1+V2+V3) into the persist pipeline so
it generates `subcap_scores` rows for these entities with
`data-source="llm"` marker.

**Validation**:
- *Unit* — `tests/test_subcap_narrative_extractor.py` (Vertex prompt + validators)
- *Integration* — re-run `app/scripts/qa_render_validation.py` against the 12 entities; expect FAIL → PARTIAL (with `data-source="llm"`)
- *Regression-by-revert* — disable the extractor wire in `package_persist.py`; expect 12 entities to revert to PARTIAL skeleton state

**Regression risk**: Medium — Vertex calls cost tokens (per Batch 6
synthesis_orchestrator cost model). Cache hit rate determines $/run.

**Owner hint**: Backend AI team. ETA: Q3 2026 alongside AI Loop 6 promote.

---

### P2-B — `parser_observations` automated promoter

```
ID         : P2-B
Title      : parser_observations table populates but no automated promoter
Status     : OPEN — manual operator flow documented
Severity   : P2
Confidence : MEDIUM (observed Batch 7 audit; needs threshold tuning)
Surface    : workers/parser_observations_promoter (NOT YET CREATED)
```

**Files**:
- `apps/dma-insights/backend/app/services/parser_observations.py:1-87`
- `apps/dma-insights/backend/app/services/parsers/package_persist.py:1131-1157`
- `apps/dma-insights/docs/qa/qa_self_healing_learning_matrix.md` § Loop 2

**Evidence**: Batch 7 audit's Loop 2 (parser observations) classified
as DEGRADED — observations populate (`occurrence_count` field
increments per re-occurrence) but no nightly Cloud Run Job consumes
the highest-occurrence rows and either (a) auto-amends the parser, or
(b) opens a CCG-style backlog ticket. Today the operator manually
reads `SELECT parser_name, observation_kind, occurrence_count FROM
parser_observations ORDER BY occurrence_count DESC LIMIT 20;` and
triages.

**User/business impact**: Slower iteration on parser improvements.
No AE-visible impact.

**Reproduction**: Run any fixture re-ingest; observe row counts in
`parser_observations`. No corresponding promoter job runs.

**Root cause**: Plan §4.2 explicitly defers Loop 2 as "needs QA —
threshold + promoter job gap."

**Fix (proposed)**: New `workers/parser_observations_promoter/main.py`
that runs nightly via Cloud Scheduler, fetches top-N rows by
occurrence_count, and either (a) opens a GitHub issue via API or (b)
writes to a `parser_amendment_queue` table for operator review.

**Validation**:
- *Unit* — `tests/test_parser_observations_promoter.py` (mocked Github API + DB fixtures)
- *Integration* — verify nightly job creates queue rows for top-3 observations
- *Regression-by-revert* — disable the worker; expect no new queue rows

**Regression risk**: Low — additive worker; no existing-flow changes.

**Owner hint**: Backend infra team. ETA: Q4 2026 (post-prod stabilisation).

---

### P2-C — Peer-pattern silhouette gate live test

```
ID         : P2-C
Title      : KMeans silhouette gate live test against >=3-entity subverticals
Status     : OPEN — N<3 cohorts in 4 of 6 subverticals
Severity   : P2
Confidence : MEDIUM (test exists; live data doesn't support it yet)
Surface    : workers/peer_patterns
```

**Files**:
- `apps/dma-insights/workers/peer_patterns/service.py:1-187`
- `apps/dma-insights/backend/tests/test_peer_patterns_service.py`
- `apps/dma-insights/docs/qa/qa_self_healing_learning_matrix.md` § Loop 3

**Evidence**: Batch 7 audit's Loop 3 classified as DEGRADED-expected.
The peer-patterns worker runs KMeans on (entity × subcap-score-vector)
matrices per subvertical. Silhouette score thresholds: >0.4 = ship
archetype label; <0.4 = "insufficient_data" placeholder. Live state:
4 of 6 subverticals have N<3 entities so KMeans can't run; the
remaining 2 subverticals (RB = retail banking, CL = credit lending)
have >=3 entities but silhouette gates haven't been triggered against
the full 104-entity corpus yet.

**User/business impact**: AEs don't see archetype chips for entities
in N<3 subverticals. Workaround: live-data acquisition (more DMAs in
those subverticals).

**Reproduction**: Trigger
`POST /api/v1/admin/jobs/peer_patterns:execute`. Observe
`job_executions.status='succeeded'` but per-subvertical archetypes =
"insufficient_data" for 4 subverticals.

**Root cause**: Test corpus distribution — not a code bug.

**Fix (proposed)**: Wait for live corpus to grow OR seed synthetic
N>=3 cohorts in `tests/fixtures/dma_packages_batches/` for the 4
sparse subverticals.

**Validation**:
- *Unit* — `tests/test_peer_patterns_service.py::test_kmeans_silhouette_gate` (passes against synthetic 9-entity 2-cluster cohort)
- *Live* — manual trigger of `peer_patterns:execute` after corpus grows; expect 6/6 subverticals to produce archetypes

**Regression risk**: Low.

**Owner hint**: Operations team. ETA: when corpus grows naturally.

---

## P3 — 2 open

### P3-A — Frontend MSW wiring

```
ID         : P3-A
Title      : mock-service-worker doesn't intercept vitest contract tests
Status     : OPEN — known carry-forward
Severity   : P3
Confidence : LOW (no impact on production; only on test development ergonomics)
Surface    : frontend test infrastructure
```

**Files**:
- `apps/dma-insights/frontend/src/setupTests.ts`
- `apps/dma-insights/frontend/vitest.config.ts`

**Evidence**: Carry-forward from prior planning rounds. MSW server
not registered in `setupTests.ts`; tests hit real fetch handlers.
Currently OK because TanStack-Query tests stub fetch directly.

**User/business impact**: None. AEs unaffected.

**Reproduction**: N/A (test-dev ergonomics only).

**Root cause**: Test infra deferred per "Out of scope" plan.

**Fix (proposed)**: Wire MSW per the standard
`msw/node setupServer()` pattern.

**Validation**: Existing `frontend/src/lib/__tests__/*.test.ts` continue to pass after MSW wires.

**Regression risk**: Very low.

**Owner hint**: Frontend team. ETA: not gating prod.

---

### P3-B — `audit-render-health.ts` discrete deliverable

```
ID         : P3-B
Title      : audit-render-health.ts merged into Batch 5 page matrices, not a standalone deliverable
Status     : OPEN — folded
Severity   : P3
```

**Status**: Plan-mandated deliverable was folded into Batch 5
adversarial-resilience harness coverage. The standalone TS file
`audit-render-health.ts` was deemed redundant. No action required.

---

## Production-Ready Gate decision input

| Severity | Open count | Threshold | Status |
|---|---:|---:|---|
| P0 | 0 | 0 | ✅ within threshold |
| P1 | 1 (P1-A deferred) | ≤ 5 | ✅ within threshold |
| P2 | 3 | ≤ unbounded | ✅ documented |
| P3 | 2 | ≤ unbounded | ✅ documented |

**Verdict**: CONDITIONAL GO — see `qa_executive_summary.md`.
