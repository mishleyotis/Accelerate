#!/usr/bin/env bash
# One-time grants an OWNER of digital-maturity-assessor runs so the
# claude-deployer service account can execute infra/provision.sh.
# Least privilege; each line says which stage needs it.
set -euo pipefail

PROJECT_ID="digital-maturity-assessor"
DEPLOYER="serviceAccount:claude-deployer@${PROJECT_ID}.iam.gserviceaccount.com"

grant() {
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="$DEPLOYER" --role="$1" --condition=None --quiet >/dev/null
  echo "granted $1"
}

# --- Stage 0.1 (blocking): service identities and their role bindings ---
grant roles/iam.serviceAccountAdmin            # create/manage the five dmai-* SAs
grant roles/resourcemanager.projectIamAdmin    # bind least-privilege roles to them

# --- Stage 0.2 / deploy (needed before the api+mcp services roll): ---
grant roles/compute.networkViewer              # see the VPC/subnet for Direct VPC egress
grant roles/compute.networkUser                # attach Cloud Run revisions to the subnet

# --- Stage 0.5 (cache, storage, jobs): ---
grant roles/redis.admin                        # Memorystore instance (skip if reusing dma-insights-redis)
grant roles/cloudscheduler.admin               # the three mandatory Scheduler triggers

# Already granted (verified): run.services/jobs.create, cloudsql.instances/users.create,
# storage.buckets.create, secretmanager.secrets.create, cloudbuild.builds.create,
# iam.serviceAccounts.actAs. Artifact Registry repo creation is NOT needed —
# builds push through the existing cloud-run-source-deploy repo.
echo "done."
