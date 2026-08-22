# api — FastAPI + SQLAlchemy (asyncpg)

Read-only serving of promoted content, plus the only two write surfaces
(annotations, alert actions — both behind `Idempotency-Key`). Server-side
audience redaction (default-deny walker). Cursor pagination via row
comparison; `ETag = run_id.promoted_epoch.audience`; Brotli/gzip as app
middleware. Limits per TRD §19. No model calls, ever.

Deployed as the `api` Cloud Run service (pooled, transaction mode).
