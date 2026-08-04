#!/usr/bin/env bash
# DMA Insights — every-release deployment. Idempotent. Builds images, runs
# the migrate Job, rolls services, syncs Jobs and Scheduler triggers.
# Sections activate as each deployable lands (walking-skeleton discipline:
# every stage ends with this script run against production).
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-digital-maturity-assessor}"
REGION="${REGION:-us-central1}"
SA_DOMAIN="${PROJECT_ID}.iam.gserviceaccount.com"

say() { printf '\n== %s ==\n' "$*"; }

# --- 1 · migrate (Cloud Run Job, pre-deploy; deploy proceeds only on success)
if [ -f migrations/Dockerfile ]; then
  say "migrate job (runs prod_apply.py: alembic + catalogue loads + VERIFY log lines)"
  gcloud run jobs deploy dmai-migrate --source=migrations \
    --project="$PROJECT_ID" --region="$REGION" \
    --service-account="dmai-migrate@${SA_DOMAIN}" \
    --network=default --subnet=default --vpc-egress=private-ranges-only \
    --set-env-vars="^;^DB_INSTANCE_CONNECTION_NAME=${PROJECT_ID}:${REGION}:dmai-pg;DB_USER=dmai-migrate@${PROJECT_ID}.iam;DB_NAME=dma_insights;LOAD_CATALOGUES=v7.0:current,v5.0" \
    --max-retries=0 --task-timeout=1800 --memory=1Gi --quiet
  gcloud run jobs execute dmai-migrate --project="$PROJECT_ID" --region="$REGION" --wait
fi

# --- 2 · services (api first: web depends on it; mcp independent) ---------
if [ -f apps/api/Dockerfile ]; then
  say "svc_api"
  gcloud run deploy dmai-api --source=apps/api \
    --project="$PROJECT_ID" --region="$REGION" \
    --service-account="dmai-api@${SA_DOMAIN}" \
    --concurrency=80 --min-instances=1 --no-allow-unauthenticated
fi
if [ -f apps/mcp/Dockerfile ]; then
  say "svc_mcp"
  gcloud run deploy dmai-mcp --source=apps/mcp \
    --project="$PROJECT_ID" --region="$REGION" \
    --service-account="dmai-mcp@${SA_DOMAIN}" \
    --concurrency=4 --timeout=900 --min-instances=1 --no-allow-unauthenticated
fi
if [ -f apps/web/Dockerfile ]; then
  say "web"
  gcloud run deploy dmai-web --source=apps/web \
    --project="$PROJECT_ID" --region="$REGION" \
    --service-account="dmai-web@${SA_DOMAIN}" \
    --allow-unauthenticated
fi

# --- 3 · worker Job + Scheduler sync (stage 1 / 0.5) ----------------------
if [ -f apps/worker/Dockerfile ]; then
  say "worker job"
  gcloud run jobs deploy dmai-worker --source=apps/worker \
    --project="$PROJECT_ID" --region="$REGION" \
    --service-account="dmai-worker@${SA_DOMAIN}"
fi
# Scheduler triggers (package scan 30min; corpus-gate-scanner nightly;
# pack-exporter nightly) sync here once stage 0.5 lands.

say "deployed. Service URLs:"
gcloud run services list --project="$PROJECT_ID" --region="$REGION" \
  --filter="metadata.name:dmai-" --format='value(metadata.name,status.url)' || true
