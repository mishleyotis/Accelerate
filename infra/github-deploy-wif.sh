#!/usr/bin/env bash
# One-time setup an OWNER of digital-maturity-assessor runs so GitHub Actions
# can run infra/deploy.sh on every merge to the default branch — with no
# service-account key anywhere. GitHub's OIDC token is exchanged through
# Workload Identity Federation for a short-lived claude-deployer token, the
# same identity a hand-run deploy uses (grants-for-admin.sh holds its roles).
#
# The trust is narrow on purpose: only this repository, and only a workflow
# running on the default branch, can impersonate claude-deployer. A pull
# request, a fork or any other branch gets nothing.
#
# Idempotent: re-running leaves existing resources untouched. At the end it
# prints the two repository variables the deploy job reads; set them under
# GitHub → Settings → Secrets and variables → Actions → Variables. Until they
# are set, the deploy job records "skipped" and CI stays green.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-digital-maturity-assessor}"
REPO="${REPO:-mishleyotis/Accelerate}"
DEFAULT_BRANCH="${DEFAULT_BRANCH:-claude/dma-insights-onboarding-0ryrd0}"
POOL="github"
PROVIDER="accelerate"
DEPLOYER="claude-deployer@${PROJECT_ID}.iam.gserviceaccount.com"

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"

gcloud services enable iamcredentials.googleapis.com sts.googleapis.com \
  --project="$PROJECT_ID" --quiet

if ! gcloud iam workload-identity-pools describe "$POOL" \
     --project="$PROJECT_ID" --location=global >/dev/null 2>&1; then
  gcloud iam workload-identity-pools create "$POOL" \
    --project="$PROJECT_ID" --location=global \
    --display-name="GitHub Actions"
fi

# attribute-condition is the gate: the token must come from this repository
# AND from a push to the default branch. Changing the default branch means
# re-running this script with DEFAULT_BRANCH set.
CONDITION="assertion.repository == '${REPO}' && assertion.ref == 'refs/heads/${DEFAULT_BRANCH}'"
if ! gcloud iam workload-identity-pools providers describe "$PROVIDER" \
     --project="$PROJECT_ID" --location=global \
     --workload-identity-pool="$POOL" >/dev/null 2>&1; then
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" \
    --project="$PROJECT_ID" --location=global \
    --workload-identity-pool="$POOL" \
    --display-name="Accelerate default branch" \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
    --attribute-condition="$CONDITION"
else
  gcloud iam workload-identity-pools providers update-oidc "$PROVIDER" \
    --project="$PROJECT_ID" --location=global \
    --workload-identity-pool="$POOL" \
    --attribute-condition="$CONDITION"
fi

POOL_ID="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}"
gcloud iam service-accounts add-iam-policy-binding "$DEPLOYER" \
  --project="$PROJECT_ID" \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/${POOL_ID}/attribute.repository/${REPO}" \
  --condition=None --quiet >/dev/null

echo
echo "Set these GitHub repository variables (not secrets — neither is sensitive):"
echo "  GCP_WIF_PROVIDER = ${POOL_ID}/providers/${PROVIDER}"
echo "  GCP_DEPLOYER_SA  = ${DEPLOYER}"
