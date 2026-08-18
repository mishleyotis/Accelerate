# DMA Insights onboarding log

2026-08-18, branch `claude/dma-insights-onboarding-0ryrd0`.
Goal: be able to correctly and repeatably ingest new DMAs into the deployed app,
calibrated against Baxter Credit Union.

## Phase status

- [x] **Phase 0** — architecture mapped, ingestion path and the four rulebook
      artifacts located → `10-ARCHITECTURE-MAP.md`
- [x] **Phase 1** — environment stood up → `20-ENV-HEALTH-CHECK.md`
      (all local components green; gcloud auth and the catalogue seed blocked)
- [x] **Phase 2** — rulebook studied and internalised → `30-INGESTION-RULEBOOK.md`
      (login to the *deployed* app blocked by IAP; the same auth path proved locally)
- [x] **Phase 3** — procedure stated → `40-INGESTION-PROCEDURE.md`

## Files

| File | What |
|---|---|
| `10-ARCHITECTURE-MAP.md` | stack, ingestion path, the four rulebook artifacts, setup docs |
| `20-ENV-HEALTH-CHECK.md` | pass/fail per component, every non-passing test traced, reproduce commands |
| `30-INGESTION-RULEBOOK.md` | gold standard · rules tests · enrichment · reasoning, each with how it applies |
| `40-INGESTION-PROCEDURE.md` | the ordered end-to-end procedure, gates named per stage |
| `90-OPEN-QUESTIONS.md` | 3 blockers, 2 findings, 3 resolved ambiguities |

## Readiness

Ready to ingest **against a local stack**. Not ready to ingest **into
production**: the connector is the only door content may enter through, and
reaching it needs a Google identity this container does not have (blocker B1).
