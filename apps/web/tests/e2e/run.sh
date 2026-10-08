#!/usr/bin/env bash
# Admin › Users & roles, end to end on the real stack — run before claiming a
# grants/session change works (owner, 2026-10-08: "stress test your solutions
# before claiming you have fixed things").
#
#   Chromium ──(signed IAP-shaped assertion on every request)──▶ next start
#     ──▶ uvicorn dma_api (as the dmai-api role, svc_api grants) ──▶ Postgres
#
# Scenarios (admin-grants.e2e.js): roster loads; invite Admin / Analyst;
# change role; deactivate / reactivate; owner cannot be demoted; one
# session_log row per change; a tab open past the 8h cookie still grants and
# gets a fresh cookie; lapsed cookie on every admin GET; deactivated + lapsed
# is refused; second owner grants; an AE is enrolled as AE and refused.
# Stress (admin-grants.stress.js): 5 simultaneous invites of one person, 20
# simultaneous role flips, 10 simultaneous first visits.
#
# Needs root (scripts/local_db.sh) and the repo's node_modules. The signing
# key is generated per run and never committed.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); ROOT=$(cd "$HERE/../../../.." && pwd); WEB="$ROOT/apps/web"
AUD=/projects/1/locations/us-central1/services/dmai-web
OWNERS=mishley.otiende@zennify.com,dma@zennify.com
bash "$ROOT/scripts/local_db.sh" >/dev/null
node "$HERE/keys.js"
cleanup() { kill "${API_PID:-}" "${WEB_PID:-}" 2>/dev/null || true; rm -f "$HERE/jwks.json" "$HERE/iap-private.pem"; }
trap cleanup EXIT
LOCAL_DATABASE_URL='postgresql://dmai-api%40digital-maturity-assessor.iam:local@localhost:5432/dma_insights' \
  IAP_AUDIENCE=$AUD ADMIN_EMAILS=$OWNERS ANALYST_EMAILS=$OWNERS \
  python3 "$HERE/api_launch.py" > "$HERE/api.log" 2>&1 & API_PID=$!
(cd "$WEB" && npm run build:proto >/dev/null && npx next build >/dev/null)
(cd "$WEB" && API_URL=http://127.0.0.1:8090 ADMIN_EMAILS=$OWNERS ANALYST_EMAILS=$OWNERS IAP_AUDIENCE=$AUD \
  SESSION_SECRET=e2e-session-secret NODE_OPTIONS="--require $HERE/preload.js" \
  npx next start -p 3005 > "$HERE/web.log" 2>&1) & WEB_PID=$!
for i in $(seq 1 60); do curl -sf -o /dev/null http://127.0.0.1:3005/ && break; sleep 1; done
(cd "$WEB" && node "$HERE/admin-grants.e2e.js")
(cd "$WEB" && node "$HERE/admin-grants.stress.js")
