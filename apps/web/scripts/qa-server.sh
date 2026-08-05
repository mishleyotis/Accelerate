#!/usr/bin/env bash
# Bring up a local web server for visual QA, against the production API.
#
#   apps/web/scripts/qa-server.sh [port]
#
# Exists because the manual version of this went wrong the same way three times in
# one session, each time costing a false negative that looked like a code defect:
#
#  1 The API identity token lasts ONE HOUR. When it expires the proxy route gets a
#    401, the client directory read fails, and every page renders the 100-character
#    "Entity not found" state — with ZERO page errors. That is indistinguishable
#    from a clean render unless you check the character count, and it silently
#    invalidated a whole round of agent verification.
#  2 `next start` spawns a child, so killing the pid you launched leaves the server
#    listening. The replacement then fails with EADDRINUSE and the STALE server
#    keeps answering — so a "restart" changes nothing and the expired token
#    persists.
#  3 `pkill -f "next start"` matches this session's own shell command line and
#    kills the session. It has done so twice. Never pattern-match; match the
#    server's own PORT in /proc/<pid>/environ, which is exact.
#
# So this script mints a fresh token, removes EVERY process that owns the port,
# starts a new server, and then PROVES the page renders real data before returning.
# It exits non-zero if the page comes up empty, which is the whole point: a QA
# server that serves "Entity not found" must fail loudly, not quietly.
set -uo pipefail

PORT="${1:-3490}"
API="${API_URL:-https://dmai-api-dukrne5v4a-uc.a.run.app}"
ENTITY="${QA_ENTITY:-baxter-credit-union-bcu}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGDIR="${TMPDIR:-/tmp}"
LOG="$LOGDIR/qa-server-$PORT.log"

unset CLOUDSDK_AUTH_ACCESS_TOKEN
for p in /root/google-cloud-sdk/bin /usr/lib/google-cloud-sdk/bin; do
  [ -d "$p" ] && PATH="$p:$PATH"
done
export PATH

say() { printf '%-22s %s\n' "$1" "${2:-}"; }

# 1 · a fresh token, and prove it before building anything on it
TOKEN="$(gcloud auth print-identity-token --audiences="$API" 2>/dev/null | tail -1)"
if [ "${#TOKEN}" -lt 100 ]; then
  say "token" "FAILED to mint for $API — is gcloud authenticated?"
  exit 2
fi
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 \
  -H "Authorization: Bearer $TOKEN" \
  "$API/v1/entities/$ENTITY/overview?audience=internal&role=ADMIN")
[ "$code" = "200" ] || { say "api" "http $code for $ENTITY — token or entity is wrong"; exit 2; }
say "token" "minted, api answers 200"

# 2 · remove every process that owns this port. Matched on the process's OWN
#     environ, never on a command-line pattern.
killed=0
# /proc entries vanish between the glob and the read, and it is the REDIRECT that
# reports it, not the command — so the loop's stderr goes away as a whole.
while read -r pid; do
  [ -n "$pid" ] && kill "$pid" 2>/dev/null && killed=$((killed + 1))
done < <(
  for f in /proc/*/environ; do
    pid="$(basename "$(dirname "$f")")"
    case "$pid" in self|thread-self|*[!0-9]*) continue;; esac
    if tr '\0' '\n' < "$f" | grep -qx "PORT=$PORT"; then echo "$pid"; fi
  done 2>/dev/null
)
[ "$killed" -gt 0 ] && sleep 4
say "stale servers" "$killed removed"

# 3 · start, fully detached so it survives this shell
cd "$HERE"
API_URL="$API" \
API_ID_TOKEN="$TOKEN" \
SESSION_SECRET="${SESSION_SECRET:-local-qa-only-not-a-secret}" \
ALLOW_DEV_LOGIN=1 \
ADMIN_EMAILS="${ADMIN_EMAILS:-dma@zennify.com}" \
ANALYST_EMAILS="${ANALYST_EMAILS:-dma@zennify.com}" \
PORT="$PORT" \
  setsid nohup npx next start -p "$PORT" > "$LOG" 2>&1 < /dev/null &
disown 2>/dev/null || true

for _ in $(seq 1 20); do
  sleep 1
  curl -s -o /dev/null --max-time 3 "http://localhost:$PORT/" && break
done

# 4 · prove a real page renders. An empty page here is a FAILURE, because the
#     failure mode this script exists for is a page that looks fine and is empty.
len=$(node -e '
const http = require("http");
const port = process.argv[1], entity = process.argv[2];
const post = (path, body) => new Promise((res, rej) => {
  const r = http.request({ port, path, method: "POST",
    headers: { "content-type": "application/json" } }, (x) => {
      let d = ""; x.on("data", (c) => (d += c));
      x.on("end", () => res({ headers: x.headers, body: d }));
    });
  r.on("error", rej); r.end(JSON.stringify(body));
});
(async () => {
  const r = await post("/api/signin", { email: "dma@zennify.com" });
  const m = String(r.headers["set-cookie"] || "").match(/dma_session=([^;]+)/);
  if (!m) { console.log(-1); return; }
  const g = await new Promise((res, rej) => {
    http.get({ port, path: `/api/entity/${entity}/overview?audience=internal`,
               headers: { cookie: `dma_session=${m[1]}` } }, (x) => {
      let d = ""; x.on("data", (c) => (d += c)); x.on("end", () => res(d));
    }).on("error", rej);
  });
  const j = JSON.parse(g);
  console.log(j.sections ? Object.keys(j.sections).length : 0);
})().catch(() => console.log(-1));
' "$PORT" "$ENTITY" 2>/dev/null)

if [ "${len:-0}" -ge 1 ] 2>/dev/null; then
  say "server" "http://localhost:$PORT — overview serves $len sections"
  say "log" "$LOG"
  exit 0
fi
say "server" "came up but the overview served NO sections — the page will render"
say "" "\"Entity not found\". Check $LOG."
exit 1
