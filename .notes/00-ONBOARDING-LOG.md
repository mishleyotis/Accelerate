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

**Ready to ingest into production.** A GCP service-account credential arrived
after the first pass and resolved the two blockers that mattered: the
connector is reachable and answering (`doctor.py` all checks passed, live
pending-run queue read), and the v7.0 catalogue is seeded locally
(851 cells, 16 categories), which took the local suite to 1247 passed /
1 failed.

The gold standard is confirmed serving: `baxter-credit-union-bcu`, SV2,
composite 2.71, 765 cells, pinned to v5.0, all six pages promoted
2026-08-15.

One capability is still missing and one thing needs your attention:

- **B2** — `dmai-web` cannot be signed into from here. IAP admits
  `domain:zennify.com` only and a service account is not in that domain. The
  only check this actually costs is
  `audit_promoted_client.py --api`, the post-promotion render audit.
- **F3** — the credential arrived in a plaintext Google Doc alongside a live
  GitHub PAT. Rotation recommended. Nothing secret was written into the repo.
