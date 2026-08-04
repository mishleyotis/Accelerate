# worker — batch jobs (Cloud Run Jobs)

- Package scan (TRD §07, ten steps verbatim): Drive intake → runs. Idempotent
  diff against previous scans; source-priority classification; test-case
  exclusion with fired rule; 4-signal entity cascade (low confidence →
  PENDING_REVIEW); dedupe; workbook parse with `source_cell`; artefact bytes
  to GCS; excerpt verification; `scored_cells` stamp; unclaimed run appears
  in `list_pending_runs`. Every 30 min via Cloud Scheduler.
- Parse/embed batch.
- `corpus-gate-scanner` — nightly + every CI run.
- `pack-exporter` — nightly + on demand.
