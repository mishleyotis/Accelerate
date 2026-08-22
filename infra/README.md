# infra — idempotent gcloud deployment scripts

- `provision.sh` — one-time resources: Cloud SQL PG16 Enterprise Plus
  (Managed Connection Pooling), Memorystore Redis, VPC + Direct VPC egress,
  GCS buckets, Secret Manager entries, service accounts + IAM bindings,
  Cloud Scheduler triggers.
- `deploy.sh` — every release: build images, run the `migrate` Job
  (Alembic), roll `web`/`api`/`mcp` services, sync Jobs and Scheduler.

Every stage ends with `deploy.sh` against production. IAM DB auth
(no DB passwords); secrets only in Secret Manager.
