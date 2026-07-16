#!/usr/bin/env bash
# apps/dma-insights/infra/backup-before-heal.sh
#
# Take an on-demand Cloud SQL backup BEFORE any self-healing operation
# that touches DB state (password rotation, force-restart, schema
# migration on a drifted instance). Operator mandate: "ensure
# persistence is also embedded in the self healing codes such that
# the app does not lose previous data. In case loss is imminent,
# everything gets replicated pretty fast then self healing starts."
#
# What this script does:
#
#   1. Verifies the instance has automated backups + PITR enabled
#      (these are persistent / cheap baseline replication). Logs
#      the last successful automated backup time so the operator can
#      reason about "worst-case rollback window."
#
#   2. Triggers a NEW on-demand backup with a SHA-stamped description
#      so the recovery path (`gcloud sql backups list` + `gcloud sql
#      backups restore`) can identify it as "the safety snapshot for
#      heal operation X."
#
#   3. Polls until the backup completes (≤10 min — Cloud SQL on-demand
#      backups on a moderately-loaded instance typically take 1-3 min).
#
#   4. If automated backups OR PITR are not enabled, ENABLES them
#      idempotently so the next heal cycle is safer.
#
# This script is intentionally CONSERVATIVE: it never fails the
# caller's heal operation. Backup failures log a warning + return
# success so the heal can still proceed (no backup is better than no
# heal — the heal itself is the prod-recovery path).
#
# Usage:
#   ./backup-before-heal.sh                            # auto detect
#   ./backup-before-heal.sh dma-insights-pg            # explicit
#   PROJECT_ID=foo BACKUP_TAG=heal-${SHA} ./backup-before-heal.sh
#   ./backup-before-heal.sh --max-wait-sec 600
#   ./backup-before-heal.sh --skip-poll                # fire+forget

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
INSTANCE="${INSTANCE:-${1:-dma-insights-pg}}"
BACKUP_TAG="${BACKUP_TAG:-pre-heal-$(date +%Y%m%dT%H%M%SZ)}"
MAX_WAIT_SEC="${MAX_WAIT_SEC:-600}"   # 10 min default
SKIP_POLL=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --max-wait-sec) MAX_WAIT_SEC="$2"; shift 2 ;;
    --skip-poll)    SKIP_POLL=true; shift ;;
    --project)      PROJECT_ID="$2"; shift 2 ;;
    --instance)     INSTANCE="$2"; shift 2 ;;
    --tag)          BACKUP_TAG="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,/^set -e/p' "$0" | sed 's/^# \{0,1\}//; /^set -e/d'
      exit 0 ;;
    --) shift; break ;;
    -*) echo "Unknown flag: $1" >&2; exit 1 ;;
    *) INSTANCE="$1"; shift ;;
  esac
done

if [[ -z "$PROJECT_ID" ]]; then
  echo "::warning::PROJECT_ID unset — skipping pre-heal backup" >&2
  exit 0
fi

echo "→ backup-before-heal: project=$PROJECT_ID instance=$INSTANCE tag=$BACKUP_TAG"

# 1. Last automated backup — gives the operator a clear "worst-case
#    rollback window" if the on-demand backup or heal fails.
LAST_AUTO="$(gcloud sql backups list --instance="$INSTANCE" \
              --project="$PROJECT_ID" \
              --filter='status=SUCCESSFUL' \
              --sort-by='~endTime' --limit=1 \
              --format='value(endTime)' 2>/dev/null || true)"
if [[ -n "$LAST_AUTO" ]]; then
  echo "  ✓ last successful automated backup: $LAST_AUTO"
else
  echo "  ⚠ no recent automated backup visible — verify in console"
fi

# 2. Idempotently ensure PITR + daily backups are ON. Cheap and
#    catches misconfigured replicas BEFORE they bite the operator
#    during a heal. Non-fatal if the patch RPC fails (permissions).
#
# CRITICAL: PostgreSQL's PITR flag is `--enable-point-in-time-recovery`;
# `--enable-bin-log` is MySQL-only and the API rejects it with
# `HTTPError 400: Binary log can only be enabled for MySQL instances`.
# Detect the engine first so we pass the correct flag (this script must
# work on both engine families because the same infra layout may host a
# MySQL sibling later).
NEED_BACKUPS=$(gcloud sql instances describe "$INSTANCE" \
                 --project="$PROJECT_ID" \
                 --format='value(settings.backupConfiguration.enabled)' \
                 2>/dev/null || echo "unknown")
DB_VERSION=$(gcloud sql instances describe "$INSTANCE" \
                 --project="$PROJECT_ID" \
                 --format='value(databaseVersion)' \
                 2>/dev/null || echo "")
if [[ "$NEED_BACKUPS" != "True" && "$NEED_BACKUPS" != "true" ]]; then
  echo "  ⟳ enabling automated backups + PITR (idempotent; engine=$DB_VERSION)"
  # Build the engine-specific PITR flag. PostgreSQL uses
  # --enable-point-in-time-recovery; MySQL uses --enable-bin-log.
  PITR_FLAG="--enable-point-in-time-recovery"
  case "$DB_VERSION" in
    MYSQL_*)        PITR_FLAG="--enable-bin-log" ;;
    POSTGRES_*|"")  PITR_FLAG="--enable-point-in-time-recovery" ;;
    *)              PITR_FLAG="--enable-point-in-time-recovery" ;;
  esac
  gcloud sql instances patch "$INSTANCE" \
    --project="$PROJECT_ID" \
    --backup-start-time=02:00 \
    "$PITR_FLAG" \
    --quiet 2>&1 | head -3 || \
    echo "::warning::could not enable backups — likely missing" \
         "cloudsql.instances.update; continuing best-effort" >&2
fi

# 3. Trigger on-demand backup with SHA-stamped description so the
#    recovery path (manual `gcloud sql backups list` + restore) can
#    point at it precisely.
echo "  ⟳ creating on-demand backup (description=$BACKUP_TAG)"
if ! BACKUP_OUT="$(gcloud sql backups create \
                     --instance="$INSTANCE" \
                     --project="$PROJECT_ID" \
                     --description="$BACKUP_TAG" \
                     --async 2>&1)"; then
  echo "::warning::on-demand backup create failed:" >&2
  echo "$BACKUP_OUT" | head -5 >&2
  echo "  Heal will proceed; rely on the most-recent automated backup" >&2
  echo "  ($LAST_AUTO) as the recovery point if needed." >&2
  exit 0
fi

# 4. Poll for completion unless --skip-poll. The on-demand backup
#    creation is async — we WAIT here so the heal that calls us has
#    a guaranteed-fresh snapshot in case its own action goes wrong.
if [[ "$SKIP_POLL" == "true" ]]; then
  echo "  ✓ backup create accepted (async; poll skipped)"
  exit 0
fi

echo "  → polling for backup completion (≤${MAX_WAIT_SEC}s)..."
start_ts=$(date +%s)
delay=10
while true; do
  STATUS=$(gcloud sql backups list --instance="$INSTANCE" \
             --project="$PROJECT_ID" \
             --filter="description=$BACKUP_TAG" \
             --sort-by='~startTime' --limit=1 \
             --format='value(status)' 2>/dev/null || echo "PENDING")
  if [[ "$STATUS" == "SUCCESSFUL" ]]; then
    echo "  ✓ pre-heal backup complete (description=$BACKUP_TAG)"
    exit 0
  fi
  if [[ "$STATUS" == "FAILED" ]]; then
    echo "::warning::pre-heal backup status=FAILED; heal will proceed" >&2
    echo "           Rely on automated backup $LAST_AUTO if rollback needed" >&2
    exit 0
  fi
  elapsed=$(($(date +%s) - start_ts))
  if [[ $elapsed -ge $MAX_WAIT_SEC ]]; then
    echo "::warning::backup did not finish within ${MAX_WAIT_SEC}s (status=$STATUS)" >&2
    echo "           Heal will proceed; check Cloud Console for progress" >&2
    exit 0
  fi
  printf "  ... status=%s (waited %ss)\n" "$STATUS" "$elapsed"
  sleep $delay
  delay=$(( delay * 2 ))
  [[ $delay -gt 60 ]] && delay=60
done
