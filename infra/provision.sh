#!/usr/bin/env bash
# DMA Insights — one-time resource provisioning. Idempotent: safe to re-run;
# existing resources are left untouched. Run one stage at a time:
#
#   ./provision.sh 0.1     # service identities + role bindings
#   ./provision.sh 0.2     # Cloud SQL instance, database, IAM DB users
#   ./provision.sh 0.5     # buckets, Redis, Cloud Run Jobs, Scheduler
#
# Requires: gcloud authenticated as claude-deployer (see grants-for-admin.sh
# for the roles it needs per stage). deploy.sh handles every-release work.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-digital-maturity-assessor}"
REGION="${REGION:-us-central1}"
SA_DOMAIN="${PROJECT_ID}.iam.gserviceaccount.com"

# The five service identities (Implementation Plan 0.1). The identity
# boundary is where the write-boundary invariant is enforced: the connector
# identity holds the only credential that can write serving tables; the DB
# grants land with the migrations (0.2/0.3).
SERVICE_ACCOUNTS=(
  "dmai-web|DMA Insights web frontend"
  "dmai-api|DMA Insights read API"
  "dmai-mcp|DMA Insights MCP connector (only serving-table writer)"
  "dmai-worker|DMA Insights ingest worker (only artefact-bucket writer)"
  "dmai-migrate|DMA Insights migrations (Alembic, pre-deploy)"
)

# Cloud SQL (TRD: Enterprise Plus for Managed Connection Pooling; private IP;
# IAM auth; PITR 35 days). Smallest Enterprise Plus machine to start —
# resize is an operational change, not a schema one.
SQL_INSTANCE="${SQL_INSTANCE:-dmai-pg}"
SQL_TIER="${SQL_TIER:-db-perf-optimized-N-2}"
DB_NAME="dma_insights"

say()  { printf '\n== %s ==\n' "$*"; }
have() { command -v gcloud >/dev/null; }

stage_0_1() {
  say "0.1 service identities"
  for entry in "${SERVICE_ACCOUNTS[@]}"; do
    sa="${entry%%|*}"; display="${entry##*|}"
    if gcloud iam service-accounts describe "${sa}@${SA_DOMAIN}" \
         --project="$PROJECT_ID" >/dev/null 2>&1; then
      echo "exists: ${sa}@${SA_DOMAIN}"
    else
      gcloud iam service-accounts create "$sa" \
        --project="$PROJECT_ID" --display-name="$display"
      echo "created: ${sa}@${SA_DOMAIN}"
    fi
  done

  say "0.1 project role bindings (least privilege)"
  bind() { # bind SA ROLE
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
      --member="serviceAccount:${1}@${SA_DOMAIN}" --role="$2" \
      --condition=None --quiet >/dev/null
    echo "bound ${1} -> ${2}"
  }
  for sa in dmai-api dmai-mcp dmai-worker dmai-migrate; do
    bind "$sa" roles/cloudsql.client        # connect via the Cloud SQL connector
    bind "$sa" roles/cloudsql.instanceUser  # IAM database authentication
  done
  for sa in dmai-web dmai-api dmai-mcp dmai-worker dmai-migrate; do
    bind "$sa" roles/logging.logWriter
    bind "$sa" roles/monitoring.metricWriter
  done
  # Deliberately absent here: bucket roles (bucket-level, granted in 0.5 with
  # the buckets), secret access (per-secret, granted as each secret is
  # created), Drive intake (a manual share to dmai-worker's email — the scan
  # cannot work until the owner confirms it).

  say "0.1 done. Worker identity for the Drive intake share:"
  echo "  dmai-worker@${SA_DOMAIN}"
}

stage_0_2() {
  say "0.2 Cloud SQL instance (Enterprise Plus, private IP, IAM auth, PITR)"
  if gcloud sql instances describe "$SQL_INSTANCE" --project="$PROJECT_ID" >/dev/null 2>&1; then
    echo "exists: $SQL_INSTANCE"
  else
    # Private services access peering must already exist on the VPC (it does:
    # the legacy Redis instance uses it). svc_mcp needs session-semantics —
    # per-service pool modes are configured after creation.
    gcloud sql instances create "$SQL_INSTANCE" \
      --project="$PROJECT_ID" --region="$REGION" \
      --database-version=POSTGRES_16 --edition=enterprise-plus \
      --tier="$SQL_TIER" \
      --network=default --no-assign-ip \
      --enable-point-in-time-recovery --retained-transaction-log-days=7 \
      --backup-start-time=08:00 --retained-backups-count=35 \
      --enable-connection-pooling \
      --database-flags=cloudsql.iam_authentication=on \
      --storage-auto-increase
  fi

  say "0.2 database + IAM users"
  gcloud sql databases describe "$DB_NAME" --instance="$SQL_INSTANCE" --project="$PROJECT_ID" >/dev/null 2>&1 \
    || gcloud sql databases create "$DB_NAME" --instance="$SQL_INSTANCE" --project="$PROJECT_ID"
  for sa in dmai-api dmai-mcp dmai-worker dmai-migrate; do
    gcloud sql users list --instance="$SQL_INSTANCE" --project="$PROJECT_ID" \
        --format='value(name)' | grep -qx "${sa}@${PROJECT_ID}.iam" \
      || gcloud sql users create "${sa}@${PROJECT_ID}.iam" \
           --instance="$SQL_INSTANCE" --project="$PROJECT_ID" --type=cloud_iam_service_account
  done
  # DB roles (svc_api, svc_mcp, svc_worker, svc_migrate) and default-deny
  # grants are created by the FIRST Alembic migration, before any table
  # exists — see migrations/. No DB password exists anywhere.
}

stage_0_5() {
  say "0.5 buckets, Redis, Jobs, Scheduler — implemented at stage 0.5"
  echo "artefact/export/corpus-pack buckets; corpus-gate-scanner + pack-exporter Jobs;"
  echo "package-scan trigger every 30 min; Redis (decision pending: new vs reuse dma-insights-redis)"
  exit 1
}

have || { echo "gcloud not found"; exit 1; }
case "${1:-}" in
  0.1) stage_0_1 ;;
  0.2) stage_0_2 ;;
  0.5) stage_0_5 ;;
  *) echo "usage: $0 {0.1|0.2|0.5}"; exit 2 ;;
esac
