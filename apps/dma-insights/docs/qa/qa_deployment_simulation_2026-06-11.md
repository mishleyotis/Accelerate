# Deployment simulation — 2026-06-11 (post wireframe-fidelity rebuild)

Local end-to-end rehearsal of the deploy contract against the seeded
96-DMA corpus. Every error surfaced is listed with its disposition.

| # | Step | Result | Error captured → disposition |
|---|---|---|---|
| 1 | `scripts/ci-live-migration.sh` | ⚠ env | Needs a running Docker daemon; container ships dockerd stopped → started manually. Runbook note added here. |
| 2 | sidecar image pull | ⚠ transient | docker.io CDN 503 on pgvector blob → fell back to system-PG scratch DB (same contract). |
| 3 | alembic up → base → up (fresh DB) | ✅ | Full chain incl. new 039/040 round-trips clean. |
| 4 | `post-deploy-smoke.sh` vs :8000 | ❌→✅ FIXED | A5 readyz check failed: `migration_head` was prod-gated in `app/main.py`, so smoke false-failed on every non-prod env ("Deploy is silently broken" on a healthy stack). Fix: head now emitted in every env; only the drift-503 stays prod-gated. Re-run: `✓ migration_head=040_alerts_producer · A5 PASSED`. Pinned test re-pinned to the new contract. |
| 5 | §2c chain idempotency | ✅ | `backfill_run_dates` re-run: 0 repaired (79 already done; 16 REQ-hex/SYNTH stay NULL by contract). `derive_alerts` re-run: same 1,552 (DELETE+INSERT per entity; waive-preservation 0 as none waived). |
| 6 | prod-readiness guard | ✅ by design | `assert_production_ready(env=prod)` fail-fasts listing 6 unset secrets (oauth id/secret, …) — the intended cold-start block. NB: env literal is `prod`, not `production`. |
| 7 | suites | ✅ | backend pytest 2,198+ green (incl. re-pinned readyz test), ruff clean; vitest 321, tsc, vite + standalone builds clean. |
| 8 | offline-Gemini posture | ✅ | enrich_corpus honest-cold (570 misses stay PENDING, 0 tokens); intelligence_recompute → 95×vertex_unavailable, fail-closed (no fabricated profiles). Cache warms post-deploy with Vertex creds; no fingerprint changes shipped → no invalidation storm (R7). |

Carry-forward (source-genuine, not deploy blockers): corpus recs lack
effort_band/maturity_lift (1-phase roadmap, no-uplift staircase);
issue_register dates NULL ×498; timeline signal derived from kind.
