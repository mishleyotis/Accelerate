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
    --network=default --subnet=default --vpc-egress=private-ranges-only \
    --set-env-vars="^;^DB_INSTANCE_CONNECTION_NAME=${PROJECT_ID}:${REGION}:dmai-pg;DB_USER=dmai-api@${PROJECT_ID}.iam;DB_NAME=dma_insights" \
    --concurrency=80 --min-instances=1 --no-allow-unauthenticated --quiet
  # web calls api service-to-service with an ID token
  gcloud run services add-iam-policy-binding dmai-api \
    --project="$PROJECT_ID" --region="$REGION" \
    --member="serviceAccount:dmai-web@${SA_DOMAIN}" \
    --role="roles/run.invoker" --quiet >/dev/null
fi
if [ -f apps/mcp/Dockerfile ]; then
  say "svc_mcp"
  # Capability-URL token: the streamable-HTTP path embeds it, so the
  # Cowork connector needs only the URL. Rotating the secret rotates the
  # URL. Created once, never echoed.
  if ! gcloud secrets describe dmai-mcp-path-token --project="$PROJECT_ID" >/dev/null 2>&1; then
    head -c 24 /dev/urandom | base64 | tr '+/' '-_' | tr -d '=' | gcloud secrets create dmai-mcp-path-token \
      --project="$PROJECT_ID" --data-file=- --quiet
  fi
  gcloud secrets add-iam-policy-binding dmai-mcp-path-token \
    --project="$PROJECT_ID" \
    --member="serviceAccount:dmai-mcp@${SA_DOMAIN}" \
    --role="roles/secretmanager.secretAccessor" --quiet >/dev/null
  gcloud run deploy dmai-mcp --source=apps/mcp \
    --project="$PROJECT_ID" --region="$REGION" \
    --service-account="dmai-mcp@${SA_DOMAIN}" \
    --network=default --subnet=default --vpc-egress=private-ranges-only \
    --set-env-vars="^;^DB_INSTANCE_CONNECTION_NAME=${PROJECT_ID}:${REGION}:dmai-pg;DB_USER=dmai-mcp@${PROJECT_ID}.iam;DB_NAME=dma_insights" \
    --set-secrets="MCP_PATH_TOKEN=dmai-mcp-path-token:latest" \
    --memory=2Gi --cpu=2 \
    --concurrency=4 --timeout=900 --min-instances=1 --allow-unauthenticated --quiet
fi
if [ -f apps/web/Dockerfile ]; then
  say "web"
  # Session-cookie signing secret: created once, never echoed (Secret Manager).
  if ! gcloud secrets describe dmai-session-secret --project="$PROJECT_ID" >/dev/null 2>&1; then
    head -c 48 /dev/urandom | base64 | gcloud secrets create dmai-session-secret \
      --project="$PROJECT_ID" --data-file=- --quiet
  fi
  gcloud secrets add-iam-policy-binding dmai-session-secret \
    --project="$PROJECT_ID" \
    --member="serviceAccount:dmai-web@${SA_DOMAIN}" \
    --role="roles/secretmanager.secretAccessor" --quiet >/dev/null
  API_URL="$(gcloud run services describe dmai-api --project="$PROJECT_ID" \
    --region="$REGION" --format='value(status.url)' 2>/dev/null || true)"
  # Role grants (interim allowlist until the auth stage's users table):
  # override per deploy with ADMIN_EMAILS/AE_EMAILS in the environment.
  ADMIN_EMAILS="${ADMIN_EMAILS:-mishley.otiende@zennify.com,dma@zennify.com}"
  AE_EMAILS="${AE_EMAILS:-}"
  gcloud run deploy dmai-web --source=apps/web \
    --project="$PROJECT_ID" --region="$REGION" \
    --service-account="dmai-web@${SA_DOMAIN}" \
    --set-env-vars="^;^API_URL=${API_URL};ADMIN_EMAILS=${ADMIN_EMAILS};AE_EMAILS=${AE_EMAILS}" \
    --set-secrets="SESSION_SECRET=dmai-session-secret:latest" \
    --allow-unauthenticated --quiet
fi

# --- 3 · worker Job + Scheduler sync (stage 1 / 0.5) ----------------------
if [ -f apps/worker/Dockerfile ]; then
  say "worker job (package scan; requires the intake folder shared with dmai-worker@)"
  gcloud run jobs deploy dmai-worker --source=apps/worker \
    --project="$PROJECT_ID" --region="$REGION" \
    --service-account="dmai-worker@${SA_DOMAIN}" \
    --network=default --subnet=default --vpc-egress=private-ranges-only \
    --set-env-vars="^;^DB_INSTANCE_CONNECTION_NAME=${PROJECT_ID}:${REGION}:dmai-pg;DB_USER=dmai-worker@${PROJECT_ID}.iam;DB_NAME=dma_insights;INTAKE_FOLDER_ID=${INTAKE_FOLDER_ID:-1xIClbzw-SRBJ0Et3SOWnb7YhcBM8b6mo};MAX_PACKAGES=3" \
    --max-retries=0 --task-timeout=3600 --memory=2Gi --cpu=2 --quiet
  gcloud run jobs add-iam-policy-binding dmai-worker \
    --project="$PROJECT_ID" --region="$REGION" \
    --member="serviceAccount:dmai-worker@${SA_DOMAIN}" \
    --role="roles/run.invoker" --quiet >/dev/null
  # package scan every 30 minutes (charter: mandatory trigger #1)
  if ! gcloud scheduler jobs describe dmai-package-scan --project="$PROJECT_ID" --location="$REGION" >/dev/null 2>&1; then
    gcloud scheduler jobs create http dmai-package-scan \
      --project="$PROJECT_ID" --location="$REGION" \
      --schedule="*/30 * * * *" \
      --uri="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/dmai-worker:run" \
      --http-method=POST \
      --oauth-service-account-email="dmai-worker@${SA_DOMAIN}" --quiet
  fi
fi
# Remaining Scheduler triggers (corpus-gate-scanner nightly; pack-exporter
# nightly) sync here with stage 8.

say "deployed. Service URLs:"
gcloud run services list --project="$PROJECT_ID" --region="$REGION" \
  --filter="metadata.name:dmai-" --format='value(metadata.name,status.url)' || true
