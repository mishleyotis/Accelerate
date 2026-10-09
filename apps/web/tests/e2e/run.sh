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
# Client links (client-links.e2e.js / .stress.js), on a second `next start`
# in SHARE_MODE=1 as dmai-share, with a stub upstream (stub-api.js) for the
# one client's customer envelope: mint → gate → refuse → admit → read →
# beacons, every usage line both services write fed through bq-emulator.js to
# lib/usage-store readUsage and rendered on Admin › Usage analytics; then
# 6 concurrent mints, 600 concurrent beacon events from 12 readers, and a
# reader removed mid-stream.
#
# Needs root (scripts/local_db.sh) and the repo's node_modules. The signing
# key is generated per run and never committed.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); ROOT=$(cd "$HERE/../../../.." && pwd); WEB="$ROOT/apps/web"
AUD=/projects/1/locations/us-central1/services/dmai-web
OWNERS=mishley.otiende@zennify.com,dma@zennify.com
bash "$ROOT/scripts/local_db.sh" >/dev/null
node "$HERE/keys.js"
# By port, not by PID: `(cd … && npx next start) &` records the subshell, and
# killing it leaves the server listening — the next run then talks to a server
# holding the previous run's keys.
free_ports() { fuser -k 3005/tcp 3006/tcp 8090/tcp 8091/tcp >/dev/null 2>&1 || true; }
cleanup() { kill "${API_PID:-}" "${WEB_PID:-}" "${SHARE_PID:-}" "${STUB_PID:-}" 2>/dev/null || true; free_ports
            rm -rf "$HERE/jwks.json" "$HERE/iap-private.pem" "$HERE"/share-*.pem "$HERE/share-ledger"; }
free_ports; sleep 1
trap cleanup EXIT
LOCAL_DATABASE_URL='postgresql://dmai-api%40digital-maturity-assessor.iam:local@localhost:5432/dma_insights' \
  IAP_AUDIENCE=$AUD ADMIN_EMAILS=$OWNERS ANALYST_EMAILS=$OWNERS \
  python3 "$HERE/api_launch.py" > "$HERE/api.log" 2>&1 & API_PID=$!
(cd "$WEB" && npm run build:proto >/dev/null && npx next build >/dev/null)
rm -rf "$HERE/share-ledger"; mkdir -p "$HERE/share-ledger"
SIGN="$(cat "$HERE/share-private.pem")"; VERIFY="$(cat "$HERE/share-public.pem")"
(cd "$WEB" && API_URL=http://127.0.0.1:8090 ADMIN_EMAILS=$OWNERS ANALYST_EMAILS=$OWNERS IAP_AUDIENCE=$AUD \
  SESSION_SECRET=e2e-session-secret NODE_OPTIONS="--require $HERE/preload.js" \
  SHARE_SIGNING_KEY="$SIGN" SHARE_BASE_URL=http://localhost:3006 SHARE_LEDGER_DIR="$HERE/share-ledger" \
  npx next start -p 3005 > "$HERE/web.log" 2>&1) & WEB_PID=$!
node "$HERE/stub-api.js" & STUB_PID=$!
(cd "$WEB" && SHARE_MODE=1 API_URL=http://127.0.0.1:8091 SHARE_VERIFY_KEY="$VERIFY" \
  SHARE_COOKIE_SECRET=e2e-share-cookie-secret-at-least-32-characters SHARE_LEDGER_DIR="$HERE/share-ledger" \
  NODE_OPTIONS="--require $HERE/preload.js" npx next start -p 3006 > "$HERE/share.log" 2>&1) & SHARE_PID=$!
for i in $(seq 1 60); do curl -sf -o /dev/null http://127.0.0.1:3005/ && break; sleep 1; done
for i in $(seq 1 60); do curl -s -o /dev/null http://127.0.0.1:3006/s/x && break; sleep 1; done
# E2E_ONLY=client-links skips the grants scenarios (their database writes are
# independent of these).
if [ "${E2E_ONLY:-}" != "client-links" ]; then
  (cd "$WEB" && node "$HERE/admin-grants.e2e.js")
  (cd "$WEB" && node "$HERE/admin-grants.stress.js")
fi
(cd "$WEB" && node "$HERE/client-links.e2e.js")
(cd "$WEB" && node "$HERE/client-links.stress.js")
