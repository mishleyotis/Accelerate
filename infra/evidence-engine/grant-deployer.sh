#!/usr/bin/env bash
# ONE-TIME, run by a project owner: the roles the CI deployer (the WIF
# service account github-deploy-wif.sh set up) needs to run
# deploy-evidence.sh. Prints the plan; applies only with CONFIRM=1.
# The project-level IAM bindings the engine's own service accounts need
# (logging) are granted HERE too, so the deployer never needs
# roles/resourcemanager.projectIamAdmin (deploy-evidence.sh skips them
# unless EE_GRANT_PROJECT_ROLES=1).
set -euo pipefail
PROJECT_ID="${PROJECT_ID:-digital-maturity-assessor}"
SA_DOMAIN="${PROJECT_ID}.iam.gserviceaccount.com"
DEPLOYER="${GCP_DEPLOYER_SA:-claude-deployer@${SA_DOMAIN}}"
run() { if [ "${CONFIRM:-0}" = "1" ]; then "$@"; else printf 'PLAN: %q ' "$@"; printf '\n'; fi; }
for role in roles/run.admin roles/iam.serviceAccountAdmin roles/iam.serviceAccountUser \
            roles/secretmanager.admin roles/storage.admin roles/compute.networkAdmin \
            roles/cloudbuild.builds.editor roles/artifactregistry.writer roles/serviceusage.serviceUsageConsumer; do
  run gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:${DEPLOYER}" --role="$role" --condition=None --quiet
done
for sa in dmai-evidence dmai-searxng dmai-fetch dmai-edgar; do
  if ! gcloud iam service-accounts describe "${sa}@${SA_DOMAIN}" --project="$PROJECT_ID" >/dev/null 2>&1; then
    run gcloud iam service-accounts create "$sa" --project="$PROJECT_ID" --display-name="DMA Insights $sa"
  fi
  run gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:${sa}@${SA_DOMAIN}" --role=roles/logging.logWriter --condition=None --quiet
done
echo "done (CONFIRM=${CONFIRM:-0}); the CI deploy job can now run infra/evidence-engine/ci_gate.sh once APPROVAL.json clears the threshold"
