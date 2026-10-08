#!/usr/bin/env bash
# Read-only production diagnostics for Admin › Usage analytics and Users &
# roles. Prints what production actually holds, so "the panel is blank" is
# answered from evidence rather than guessed at:
#
#   1. the dmai-usage sink: destination, filter, writer identity
#   2. sink write errors the log router recorded (the sink cannot write)
#   3. usage lines dmai-web wrote to Cloud Logging (the browser reports)
#   4. the BigQuery table: does it exist, how many rows, newest event
#   5. who holds what on the dataset (access list + conditioned bindings)
#   6. refusals on the admin read paths (web /api/admin/*, api /v1/admin/*, /v1/me)
#
# Emails are masked (first letter + domain): the output lands in CI logs.
# The only write is a self-grant of roles/logging.viewer to the deployer
# (it holds projectIamAdmin), because reading log entries needs it.
set -uo pipefail

PROJECT_ID="${PROJECT_ID:-digital-maturity-assessor}"
USAGE_DATASET="${USAGE_DATASET:-dmai_usage}"
USAGE_TABLE="${USAGE_TABLE:-run_googleapis_com_stdout}"
FRESHNESS="${FRESHNESS:-24h}"

mask() { sed -E 's/([A-Za-z0-9])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+)/\1***@\2/g'; }
hdr() { printf '\n== diagnose: %s ==\n' "$*"; }

ACCT="$(gcloud config get-value account 2>/dev/null || true)"
case "$ACCT" in
  *.iam.gserviceaccount.com)
    if ! gcloud projects get-iam-policy "$PROJECT_ID" --flatten='bindings[].members' \
         --filter="bindings.role=roles/logging.viewer AND bindings.members=serviceAccount:${ACCT}" \
         --format='value(bindings.role)' 2>/dev/null | grep -q .; then
      gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:${ACCT}" \
        --role=roles/logging.viewer --condition=None --quiet >/dev/null 2>&1 \
        && echo "  (granted ${ACCT} roles/logging.viewer to read log entries; propagation can take a minute)"
    fi ;;
esac

hdr "1. sink dmai-usage"
gcloud logging sinks describe dmai-usage --project="$PROJECT_ID" \
  --format='yaml(destination,filter,writerIdentity,bigqueryOptions,disabled)' 2>&1 | mask

hdr "2. sink write errors (last ${FRESHNESS})"
gcloud logging read 'logName:"logging.googleapis.com%2Fsink_error" OR (resource.type="logging_sink" AND severity>=WARNING)' \
  --project="$PROJECT_ID" --freshness="$FRESHNESS" --limit=10 \
  --format='table(timestamp,severity,jsonPayload.error.details.message:label=ERROR)' 2>&1 | mask | head -30

hdr "3. usage lines dmai-web wrote (last ${FRESHNESS})"
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="dmai-web" AND jsonPayload.usage_v=1' \
  --project="$PROJECT_ID" --freshness="$FRESHNESS" --limit=500 \
  --format='value(jsonPayload.usage.type)' 2>&1 | sort | uniq -c | head -20
echo "  newest:"
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="dmai-web" AND jsonPayload.usage_v=1' \
  --project="$PROJECT_ID" --freshness="$FRESHNESS" --limit=3 \
  --format='table(timestamp,jsonPayload.usage.type,jsonPayload.usage.page,jsonPayload.usage.email)' 2>&1 | mask

hdr "4. BigQuery ${USAGE_DATASET}.${USAGE_TABLE}"
bq --project_id="$PROJECT_ID" ls "${PROJECT_ID}:${USAGE_DATASET}" 2>&1 | head -10
bq --project_id="$PROJECT_ID" --format=prettyjson query --nouse_legacy_sql \
  "SELECT COUNT(*) AS rows_total, FORMAT_TIMESTAMP('%FT%TZ', MAX(timestamp)) AS newest FROM \`${PROJECT_ID}.${USAGE_DATASET}.${USAGE_TABLE}\`" 2>&1 | mask | head -20

echo "  the app's own read (lib/usage-store.js eventsSql, 30 days), run as this account:"
if command -v node >/dev/null 2>&1; then
  APP_SQL="$(cd "$(dirname "$0")/.." && node --input-type=module -e "
import { eventsSql } from './apps/web/lib/usage-store.js';
process.stdout.write(eventsSql({ project: '${PROJECT_ID}', dataset: '${USAGE_DATASET}', table: '${USAGE_TABLE}' }));" 2>/dev/null)"
  if APP_OUT="$(bq --project_id="$PROJECT_ID" --format=csv query --nouse_legacy_sql --max_rows=1000000 \
                 --parameter=days:INT64:30 "$APP_SQL" 2>&1)"; then
    printf '%s\n' "$APP_OUT" | grep -v '^WARNING' \
      | awk -F, 'NR==1{next} {n++; t[$2]++} END {printf "  OK rows %d:", n; for (k in t) printf " %s=%d", k, t[k]; print ""}'
  else
    echo "  QUERY FAILED:"; printf '%s\n' "$APP_OUT" | grep -v '^WARNING' | head -8 | mask
  fi
else
  echo "  (node not on PATH; skipped)"
fi

hdr "5. grants on ${USAGE_DATASET}"
bq --project_id="$PROJECT_ID" --format=prettyjson show "${PROJECT_ID}:${USAGE_DATASET}" 2>/dev/null \
  | python3 -c 'import json,sys
raw = sys.stdin.read()
try:
    for a in json.loads(raw[raw.find("{"):]).get("access", []): print("  acl", a.get("role"), a.get("userByEmail") or a.get("specialGroup") or a.get("groupByEmail") or "")
except ValueError: print("  (no readable dataset JSON)")' | mask
gcloud projects get-iam-policy "$PROJECT_ID" --flatten='bindings[].members' \
  --filter='bindings.role~^roles/bigquery' \
  --format='table(bindings.role,bindings.members,bindings.condition.title)' 2>&1 | mask | head -30

hdr "6. refusals on the admin read paths (last ${FRESHNESS})"
gcloud logging read 'resource.type="cloud_run_revision" AND (resource.labels.service_name="dmai-web" OR resource.labels.service_name="dmai-api") AND httpRequest.status>=400 AND (httpRequest.requestUrl:"/admin/" OR httpRequest.requestUrl:"/v1/me" OR httpRequest.requestUrl:"/api/usage")' \
  --project="$PROJECT_ID" --freshness="$FRESHNESS" --limit=20 \
  --format='table(timestamp,resource.labels.service_name,httpRequest.status,httpRequest.requestMethod,httpRequest.requestUrl)' 2>&1 | sed -E 's/\?.*//' | mask | head -30
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="dmai-web" AND jsonPayload.usage_read.status!="ok"' \
  --project="$PROJECT_ID" --freshness="$FRESHNESS" --limit=5 \
  --format='table(timestamp,jsonPayload.usage_read.status,jsonPayload.usage_read.detail)' 2>&1 | mask
echo "  why dmai-api refused an identity:"
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="dmai-api" AND jsonPayload.actor_refused.code:*' \
  --project="$PROJECT_ID" --freshness="$FRESHNESS" --limit=10 \
  --format='table(timestamp,jsonPayload.actor_refused.path,jsonPayload.actor_refused.code,jsonPayload.actor_refused.detail)' 2>&1 | mask

exit 0
