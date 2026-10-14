# infra — idempotent gcloud deployment scripts

- `provision.sh` — one-time resources: Cloud SQL PG16 Enterprise Plus
  (Managed Connection Pooling), Memorystore Redis, VPC + Direct VPC egress,
  GCS buckets, Secret Manager entries, service accounts + IAM bindings,
  Cloud Scheduler triggers.
- `deploy.sh` — every release: build images, run the `migrate` Job
  (Alembic), roll `web`/`api`/`mcp` services, sync Jobs and Scheduler.
  Runs automatically from CI (`deploy` job in `.github/workflows/ci.yml`)
  on every push to the default branch, after every other job passes.
- `github-deploy-wif.sh` — one-time, run by a project owner: Workload
  Identity Federation so that CI deploy signs in as `claude-deployer` with no
  key. Trusts only this repository's default branch. Prints the two
  repository variables (`GCP_WIF_PROVIDER`, `GCP_DEPLOYER_SA`) the job reads;
  until they are set the job warns and skips.

Every stage ends with `deploy.sh` against production. IAM DB auth
(no DB passwords); secrets only in Secret Manager.
