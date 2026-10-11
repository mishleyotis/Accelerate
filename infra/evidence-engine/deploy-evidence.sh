#!/usr/bin/env bash
# DMA Insights — evidence-engine release. Idempotent. Creates ONLY new
# resources (four services, their identities, secrets, buckets, the static
# egress); never touches dmai-mcp, dmai-api, dmai-web, dmai-worker or any
# existing service (brief §10 HALT condition).
#
# GATED. Every resource-creating gcloud command below runs only when
# EE_DEPLOY_APPROVED=1 is set by a person after reading
# apps/evidence-engine/docs/DEPLOY-PLAN.md (brief §7.2 "gate before spend").
# Without it the script prints the plan it WOULD execute and exits 0.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-digital-maturity-assessor}"
REGION="${REGION:-us-central1}"
SA_DOMAIN="${PROJECT_ID}.iam.gserviceaccount.com"
SEC_UA="${SEC_EDGAR_USER_AGENT:-Zennify DMA-Insights evidence-engine (+https://www.zennify.com)}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"

say() { printf '\n== %s ==\n' "$*"; }
run() {
  if [ "${EE_DEPLOY_APPROVED:-0}" = "1" ]; then "$@"; else printf 'PLAN: %q ' "$@"; printf '\n'; fi
}
EXISTING=(dmai-mcp dmai-api dmai-web dmai-worker dmai-share)
for s in "${EXISTING[@]}"; do
  case " $* " in *" $s "*) echo "refusing: this script never names an existing service ($s)" >&2; exit 2;; esac
done

say "0 · identities (new)"
for sa in dmai-evidence dmai-searxng dmai-fetch dmai-edgar; do
  if gcloud iam service-accounts describe "${sa}@${SA_DOMAIN}" --project="$PROJECT_ID" >/dev/null 2>&1; then
    echo "exists: ${sa}@${SA_DOMAIN}"
  else
    run gcloud iam service-accounts create "$sa" --project="$PROJECT_ID" --display-name="DMA Insights $sa"
  fi
  # The project-level binding needs projectIamAdmin, which the CI deployer
  # deliberately lacks: grant-deployer.sh (owner, one-time) makes it.
  if [ "${EE_GRANT_PROJECT_ROLES:-0}" = "1" ]; then
    run gcloud projects add-iam-policy-binding "$PROJECT_ID" \
      --member="serviceAccount:${sa}@${SA_DOMAIN}" --role=roles/logging.logWriter --condition=None --quiet
  fi
done

say "1 · secrets (new; values generated, never printed)"
for secret in dmai-evidence-path-token dmai-searxng-path-token dmai-fetch-path-token dmai-edgar-path-token dmai-searxng-secret-key; do
  if gcloud secrets describe "$secret" --project="$PROJECT_ID" >/dev/null 2>&1; then
    echo "exists: $secret"
  else
    if [ "${EE_DEPLOY_APPROVED:-0}" = "1" ]; then
      openssl rand -hex 24 | tr -d '\n' | gcloud secrets create "$secret" --project="$PROJECT_ID" --data-file=- --replication-policy=automatic
      echo "created: $secret"
    else
      echo "PLAN: openssl rand -hex 24 | gcloud secrets create $secret --data-file=-"
    fi
  fi
done
grant_secret() { run gcloud secrets add-iam-policy-binding "$1" --project="$PROJECT_ID" \
  --member="serviceAccount:${2}@${SA_DOMAIN}" --role=roles/secretmanager.secretAccessor --quiet; }
grant_secret dmai-evidence-path-token dmai-evidence
grant_secret dmai-searxng-path-token dmai-searxng
grant_secret dmai-searxng-secret-key dmai-searxng
grant_secret dmai-fetch-path-token dmai-fetch
grant_secret dmai-edgar-path-token dmai-edgar
# The plugin's identity rungs (dmai-routine, and the owner's gcloud account)
# read the evidence token the way they read dmai-mcp's: through Secret Manager.
grant_secret dmai-evidence-path-token dmai-routine

say "2 · buckets (new; engine text + cache, uniform access)"
for suffix in dmai-evidence-text dmai-evidence-cache; do
  b="gs://${PROJECT_ID}-${suffix}"
  if gcloud storage buckets describe "$b" --project="$PROJECT_ID" >/dev/null 2>&1; then
    echo "exists: $b"
  else
    run gcloud storage buckets create "$b" --project="$PROJECT_ID" --location="$REGION" --uniform-bucket-level-access
  fi
  run gcloud storage buckets add-iam-policy-binding "$b" \
    --member="serviceAccount:dmai-evidence@${SA_DOMAIN}" --role=roles/storage.objectAdmin --quiet
done

say "3 · static egress (new): VPC connector + Cloud NAT with a reserved address"
# Measured before/after by searxng/health.sh (brief §6b). Cost: the connector
# bills per instance-hour; stated in DEPLOY-PLAN.md.
if gcloud compute addresses describe dmai-evidence-egress --region="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "exists: address dmai-evidence-egress"
else
  run gcloud compute addresses create dmai-evidence-egress --region="$REGION" --project="$PROJECT_ID"
fi
if gcloud compute routers describe dmai-evidence-router --region="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "exists: router"
else
  run gcloud compute routers create dmai-evidence-router --network=default --region="$REGION" --project="$PROJECT_ID"
fi
if gcloud compute routers nats describe dmai-evidence-nat --router=dmai-evidence-router --region="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "exists: nat"
else
  run gcloud compute routers nats create dmai-evidence-nat --router=dmai-evidence-router --region="$REGION" \
    --project="$PROJECT_ID" --nat-all-subnet-ip-ranges --nat-external-ip-pool=dmai-evidence-egress
fi

say "4 · the three backends (new services)"
deploy_backend() { # name dir sa extra-env
  local name="$1" dir="$2" sa="$3" extra="$4"
  run gcloud run deploy "$name" --source="$ROOT/infra/evidence-engine/$dir" \
    --project="$PROJECT_ID" --region="$REGION" \
    --service-account="${sa}@${SA_DOMAIN}" \
    --no-allow-unauthenticated --cpu-boost --max-instances=2 --concurrency=10 \
    --memory=1Gi --timeout=120 \
    --network=default --subnet=default --vpc-egress=all-traffic \
    --set-secrets="MCP_PATH_TOKEN=${name}-path-token:latest${extra}" --quiet
  # the engine and the plugin's identity may invoke it
  for member in dmai-evidence dmai-routine; do
    run gcloud run services add-iam-policy-binding "$name" --project="$PROJECT_ID" --region="$REGION" \
      --member="serviceAccount:${member}@${SA_DOMAIN}" --role=roles/run.invoker --quiet
  done
}
deploy_backend dmai-searxng searxng dmai-searxng ",SEARXNG_SECRET_KEY=dmai-searxng-secret-key:latest"
deploy_backend dmai-fetch   fetch   dmai-fetch   ""
EDGAR_ENV="--set-env-vars=SEC_EDGAR_USER_AGENT=${SEC_UA}"
run gcloud run deploy dmai-edgar --source="$ROOT/infra/evidence-engine/edgar" \
  --project="$PROJECT_ID" --region="$REGION" --service-account="dmai-edgar@${SA_DOMAIN}" \
  --no-allow-unauthenticated --cpu-boost --max-instances=2 --concurrency=10 --memory=1Gi --timeout=120 \
  --set-secrets="MCP_PATH_TOKEN=dmai-edgar-path-token:latest" "$EDGAR_ENV" --quiet
for member in dmai-evidence dmai-routine; do
  run gcloud run services add-iam-policy-binding dmai-edgar --project="$PROJECT_ID" --region="$REGION" \
    --member="serviceAccount:${member}@${SA_DOMAIN}" --role=roles/run.invoker --quiet
done

say "5 · the engine (new service): 2Gi, cpu-boost, max 2 instances"
SEARXNG_URL="$(gcloud run services describe dmai-searxng --project="$PROJECT_ID" --region="$REGION" --format='value(status.url)' 2>/dev/null || echo 'https://dmai-searxng.PLAN')"
run gcloud run deploy dmai-evidence --source="$ROOT/apps/evidence-engine" \
  --project="$PROJECT_ID" --region="$REGION" \
  --service-account="dmai-evidence@${SA_DOMAIN}" \
  --no-allow-unauthenticated --cpu-boost --max-instances=2 \
  --concurrency="${EE_CONCURRENCY:-8}" --memory=2Gi --cpu=2 --timeout=300 \
  --network=default --subnet=default --vpc-egress=all-traffic \
  --set-env-vars="^;^SEARXNG_URL=${SEARXNG_URL};EE_GCS_BUCKET=${PROJECT_ID}-dmai-evidence-text;SEC_EDGAR_USER_AGENT=${SEC_UA};PARALLEL_MCP_URL=https://search.parallel.ai/mcp" \
  --set-secrets="EE_PATH_TOKEN=dmai-evidence-path-token:latest,SEARXNG_PATH_TOKEN=dmai-searxng-path-token:latest" --quiet
run gcloud run services add-iam-policy-binding dmai-evidence --project="$PROJECT_ID" --region="$REGION" \
  --member="serviceAccount:dmai-routine@${SA_DOMAIN}" --role=roles/run.invoker --quiet

say "6 · smoke (wrong path 404s; tools/list non-empty) — runs only after an approved deploy"
if [ "${EE_DEPLOY_APPROVED:-0}" = "1" ]; then "$HERE/smoke.sh"; else echo "PLAN: infra/evidence-engine/smoke.sh"; fi
