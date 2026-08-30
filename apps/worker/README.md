# worker — batch jobs (Cloud Run Jobs)

- Package scan (TRD §07, ten steps verbatim): Drive intake → runs. Idempotent
  diff against previous scans; source-priority classification; test-case
  exclusion with fired rule; 4-signal entity cascade (low confidence →
  PENDING_REVIEW); dedupe; workbook parse with `source_cell`; artefact bytes
  to GCS; excerpt verification; `scored_cells` stamp; unclaimed run appears
  in `list_pending_runs`. Every 30 min via Cloud Scheduler.
- Parse/embed batch.

### The scan ledger tells the truth or nothing

`import_scans` is a receipt for the **execution**, not for the diff. The row
opens before the tree walk, stays `running` through ingestion, and is closed
exactly once by `finish_scan` with the real `finished_at`, the real
`runs_created`, and — on any failure — an `error` naming the cause. A walk
that returns zero files while the previous scan recorded artefacts refuses
(`EmptyTreeError`) rather than reporting a successful traversal of a tree
that has apparently vanished. A package that raises is a **failed** firing,
named in the row; after `MAX_INGEST_ATTEMPTS` (3) it is quarantined instead
of blanking the same checksums every thirty minutes forever. A different
upload restarts the budget; `FORCE_FOLDER=<name>` retries on demand.

### `INTAKE_STATUS` — what has not been processed

The folder list lives in Drive and the progress lives in Postgres, and until
this nothing joined them: a client folder that never produced a run left no
row anywhere, so nothing in the system could name it. Set `INTAKE_STATUS=1`
(text) or `INTAKE_STATUS=json` on the job — it walks the tree, reads the
ingested tier, writes nothing, and places every folder in one of
`no_run · run_unparsed · parsed_unsynthesised · synthesised_unpromoted ·
promoted_superseded · promoted_current`, with `reason` naming the blocker
where there is one:

```
gcloud run jobs execute dmai-worker --region=us-central1 \
  --project=digital-maturity-assessor --update-env-vars=INTAKE_STATUS=1 --wait
```

This is the answer the scheduled synthesis routine's step 1 needs. There is
no `scripts/preflight.py` in this repo; `scripts/routine_preflight.sh` is
owned outside `apps/worker/` and is the natural caller — its "pending work"
check (currently only asserting `INTAKE_FOLDER_ID` is set) should run the
command above and read the counts. Wiring it is that agent's edit, not this
one's.
- `corpus-gate-scanner` — nightly + every CI run.
- `pack-exporter` — nightly + on demand.
