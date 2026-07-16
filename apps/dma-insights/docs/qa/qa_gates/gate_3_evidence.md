# Gate 3 evidence — Phase 3 page-render + adversarial resilience (Batch 5 close)

**Gate purpose** (from the original v2 plan):

> Validates the per-page render contract end-to-end against the
> wireframe baseline + the adversarial-input contract. Cascade-checks
> Phases 1+2 still hold. **0 regressions required; 0 HTTP-500s on
> adversarial inputs required for deploy-readiness.**

**Batch 5 status: PASS — 0 regressions, 0 unrelated breaks, 0 FAIL_500.**

---

## Baseline at gate entry (state immediately before Batch 5)

| Metric | Value |
|---|---|
| HEAD SHA | `f590f65` (Batch 4 — 24-table persistence matrix + Gate 2) |
| Branch | `claude/deploy-zennify-cloud-run-AUdu6` (default) |
| Working tree | clean |
| Backend tests passing | 1882 (63 skipped: env-secret gated) |
| Backend tests failing | 0 |
| Lint | clean (1 pre-existing RUF021 in `package_csvs.py:159`) |
| Alembic head | `036_widen_data_source` |
| Live DB entities | 104 |
| Render harness | 536 OK / 688 PARTIAL / 24 FAIL across 1248 cells |
| Language audit | 1791 violations across 98/104 entities |

---

## Per-section verification

### §3.1 — Per-page render contract

Captured in `docs/qa/qa_visual_matrix.md`:
- 15 frontend pages documented with interactive elements + relevant
  states + harness coverage references
- 14 baseline-anchor entities mapped per (page × state)

### §3.2 — Adversarial resilience contract (NEW; Batch 5)

`app/scripts/qa_adversarial_resilience.py` — for every ACTIVE
entity, exercises every page-render endpoint with 7-10 adversarial
inputs (per endpoint):

- NORMAL (control)
- RUN_NONEXISTENT (`?run=REQ-DOES-NOT-EXIST-12345678`)
- RUN_EMPTY (`?run=`)
- RUN_SQL_INJECTION (`?run=' OR 1=1 --`)
- ZOOM_INVALID (`?zoom=bogus`)  (heatmap-only)
- VIEW_CUSTOMER (`?view=customer`)
- VIEW_INVALID (`?view=garbage`)
- XSS_DISPLAY_ID (`display_id="<script>alert(1)</script>"`)
- LONG_DISPLAY_ID (256-char display_id)
- UNICODE_DISPLAY_ID (`acuity-嗯-🦄`)

Live results (104 entities × 85 (probes × endpoints) = **8840 cells**):

| Classification | Count | % | Notes |
|---|---:|---:|---|
| OK (HTTP 200) | 3640 | 41.2% | control + RUN_EMPTY-graceful + VIEW_CUSTOMER + VIEW_INVALID-fallback + tolerant endpoints |
| DEGRADED (404/422 with operator-friendly detail) | 5200 | 58.8% | XSS/LONG/UNICODE → 404; SQL injection / nonexistent run → 422 pydantic rejection; invalid zoom → 422 |
| **FAIL_500** | **0** | **0%** | **Server-side resilience guarantee MET** |
| TRANSPORT_ERROR | 0 | 0% | No connection / parse failures |

### §3.3 — Visual baseline coverage

The visual baseline pipeline (Playwright + image-snapshot) is
documented in `qa_visual_matrix.md` "Visual baseline runbook" with
the canonical 14-page × 6-state matrix and the operator-runnable
capture commands.

---

## Cascade-effect classification (delta vs Gate 2 baseline)

| Check | Gate 2 | Gate 3 | Classification |
|---|---:|---:|---|
| Backend tests passing | 1882 | 1882 | `expected` (no new tests required for Batch 5; the harnesses live in `app/scripts/`) |
| Backend tests failing | 0 | 0 | `expected` |
| Backend lint | clean (1 pre-existing) | clean (1 pre-existing) | `expected` |
| Alembic head | 036 | 036 | `expected` (no schema changes) |
| Live DB entities | 104 | 104 | `expected` (no live data changes) |
| Render harness OK count | 536 | 536 | `expected` |
| Render harness FAIL count | 24 | 24 | `expected` (same 12 DOCX-only entities × 2 endpoints) |
| **NEW: adversarial harness FAIL_500 count** | n/a (didn't exist) | **0** | first run; baseline established |
| Language audit violations | 1791 | 1791 | `expected` |
| Frontend tests | 281 | 281 | `expected` |
| TS compilation | clean | clean | `expected` |
| Vite build | OK | OK | `expected` |

**0 regressions. 0 unrelated breaks. 0 FAIL_500 on adversarial inputs.** Gate 3 PASSES.

---

## Defense-in-depth properties pinned (no fixes required this batch)

The 0-FAIL_500 result across 8840 adversarial cells confirms the
following defensive properties of the page-render surface — all
were already in place from prior batches; Batch 5 contracts them
into a permanent regression gate.

| Property | Mechanism | Test cells |
|---|---|---:|
| Path-param XSS-shape returns 404, never 500 | FastAPI URL-encodes path params; SQLAlchemy parameterized queries | 1248 |
| Path-param length overflow returns 404, never DB error | Parameterized SELECT bounded by `display_id VARCHAR(32)` | 1248 |
| Path-param unicode passes through to SQL safely | asyncpg + utf-8 client encoding | 1248 |
| Query-param `?run=` malformed returns 422 pydantic rejection, never SQL injection | Pydantic `Field(pattern=...)` on request_id types | 832 |
| Query-param `?run=` empty falls back to ACTIVE run | Router-layer empty-check | 832 |
| Query-param `?zoom=` invalid returns 422, never crashes aggregator | `Literal["pillar", "category", ...]` enforces enum | 104 |
| Query-param `?view=` invalid falls back to internal view | Router-layer Literal fallback | 624 |
| Audience-strip on `?view=customer` produces sanitized payload, never 500 | Audience-strip middleware tested by entity contract tests | 624 |

---

## Artifacts shipped by Batch 5

| Path | Status |
|---|---|
| `apps/dma-insights/backend/app/scripts/qa_adversarial_resilience.py` | NEW — 10-probe × 12-endpoint × N-entity adversarial harness; exit code 0/1 CI-gateable |
| `apps/dma-insights/docs/qa/qa_visual_matrix.md` | NEW — 15-page render contract with elements × states × coverage |
| `apps/dma-insights/docs/qa/qa_adversarial_matrix.tsv` | NEW — 8841-line TSV (header + 8840 cells) full audit trail |
| `apps/dma-insights/docs/qa/qa_gates/gate_3_evidence.md` | NEW (this file) |

No code changes in any router for Batch 5 — the existing routers
were already resilient to the operator-mandated adversarial input
set. Batch 5 contracts this property into a permanent regression
gate.

---

## Next: Batch 6 readiness check

Batch 6 (Vertex language rewrite pass for the 1791 audit violations)
needs:
- ✓ Render contract pinned (this batch)
- ✓ Adversarial resilience pinned (this batch)
- ✓ Language audit baseline (1791 violations from Batch 3)
- → Open: `synthesis_orchestrator` extension to surface
  language_rewrite as a cached surface (build in Batch 6)
- → Open: prompt template that enforces the 6 UI/UX brief rules

Proceed to Batch 6.
