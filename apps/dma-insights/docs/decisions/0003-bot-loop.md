# ADR 0003 — Bot loop: bidirectional `request_id` continuity

**Status**: Accepted (2026-05-20)

## Context

Today the DMA Bot is the only entry point for new DMA runs (Slack form +
Cloud Run service). It writes to the Ops Sheet `Requests` tab and generates a
`request_id = REQ-{8 uppercase hex}`. The Claude project eventually posts
results to a callback URL. DMA Insights needs to:

1. Let AEs submit new runs from `/clients` without leaving the app.
2. Track in-flight runs so the Dashboard shows live progress.
3. Reconcile the bot's row in the Ops Sheet with our local `runs` row.
4. Accept the Claude project's `/ingest/assessment` payload when finished.

## Decision

**Same `request_id` everywhere — bot, sheet, insights, Claude project, Drive
filenames.** Format = `REQ-{8 uppercase hex}` (the bot's canonical format).

Bidirectional flow:

- **Outbound**: `POST /api/v1/runs/new` → backend uploads materials to a
  dedicated GCS bucket → POSTs to bot `/run` → bot returns `{ request_id,
  sheet_row_url, eta_min }` → backend inserts `dma_runs_requested` +
  `ops_requests` + `runs` with `status=IN_PROGRESS`.
- **Polling**: `sheet_poller` worker runs every 5 min during business hours,
  hourly otherwise. Upserts all 8 Ops Sheet tabs by `last_updated_utc`.
- **Inbound**: `POST /api/v1/ingest/assessment` matches the `request_id` to
  the in-progress run; if unknown, creates a fresh run with
  `data_source=PROJECT_API` (out-of-band reconciliation on next poll).

Evidence mode auto-derives: `mode='hybrid'` if any `materials[]` or Drive
URLs in `urls[]`, else `mode='public'`. Persisted on `runs.evidence_mode`.

## Consequences

- The bot's existing Slack form still works unchanged.
- If the bot dies mid-run, `sheet_poller` flips the run to STALE after 4×
  ETA; admin can manually inject the payload.
- If the Claude project posts with an unknown `request_id`, we still ingest
  — the next sheet poll reconciles the row.
- Every Gemini cache key, every embedding row, every Drive filename keys on
  the same `request_id` for end-to-end forensics.
