#!/usr/bin/env bash
# Preflight Redis URL validator + connectivity probe — replaces the
# multi-line heredoc snippet in DEPLOYMENT.md §0.2.7 that was a
# paste hazard (a copy-paste that lost the closing `PY` heredoc
# terminator hung Cloud Shell at the `>` prompt indefinitely).
#
# What it does:
#   1. Validates REDIS_URL scheme (redis:// or rediss://; rejects all else).
#   2. Auto-classifies the backend from the host (Upstash / Memorystore /
#      unknown) so the verdict is meaningful — a Cloud Shell connectivity
#      failure is FATAL for Upstash but EXPECTED for Memorystore.
#   3. Probes with `redis-cli PING` and `python3 -c redis-py ping`
#      (both — they catch different failure modes).
#   4. Emits a clear summary at the end:
#        OK              → exit 0 (PASS)
#        UPSTASH_FATAL   → exit 1 (URL wrong; FAIL the deploy)
#        MEMORYSTORE_WARN → exit 0 (VPC-internal — Cloud Run will reach
#                                   it through the connector; not a
#                                   deploy blocker)
#        SCHEME_INVALID  → exit 2 (URL malformed)
#        UNKNOWN_HOST    → exit 0 (warn but don't fail — operator should
#                                  manually verify)
#
# Usage:
#   REDIS_URL=... bash infra/preflight-redis.sh
#   # or (auto-pick from Secret Manager when not provided):
#   bash infra/preflight-redis.sh --from-secret
set -euo pipefail
_NF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "${_NF_DIR}/gcloud-noise-filter.sh" ] && . "${_NF_DIR}/gcloud-noise-filter.sh"
export GODEBUG=netdns=go

FROM_SECRET=0
for arg in "$@"; do
  case "$arg" in
    --from-secret) FROM_SECRET=1 ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \?//' | head -32; exit 0 ;;
    *) echo "FATAL: unknown flag '$arg' — use --help" >&2; exit 2 ;;
  esac
done

if [[ "$FROM_SECRET" == "1" ]]; then
  PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
  [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]] && {
    echo "FATAL: PROJECT_ID unset — run 'gcloud config set project …' first" >&2; exit 2; }
  REDIS_URL="$(gcloud secrets versions access latest \
    --secret=dma-insights-redis-url --project="$PROJECT_ID" 2>/dev/null || true)"
fi

if [[ -z "${REDIS_URL:-}" ]]; then
  echo "FATAL: REDIS_URL not set (and --from-secret didn't resolve one)." >&2
  echo "  Set it explicitly:  export REDIS_URL='rediss://default:<token>@<host>:6379'" >&2
  exit 2
fi

# ── 1. Scheme validation ────────────────────────────────────────────
echo "→ Preflight Redis check"
if [[ "$REDIS_URL" != redis://* && "$REDIS_URL" != rediss://* ]]; then
  echo "  ✗ scheme INVALID (got '${REDIS_URL%%:*}://…') — must be redis:// or rediss://"
  echo ""
  echo "═══════════════════════════════════════════════════════════════"
  echo "  VERDICT: SCHEME_INVALID — FIX REDIS_URL before deploying"
  echo "═══════════════════════════════════════════════════════════════"
  exit 2
fi
echo "  ✓ scheme OK (${REDIS_URL%%:*}://…)"

# ── 2. Auto-classify Upstash vs Memorystore vs unknown ──────────────
# Extract host:port out of the URL (`scheme://[user:pass@]HOST:PORT/db?…`).
HOSTPORT="$(printf '%s' "$REDIS_URL" | sed -E 's#^[^:]+://([^@]*@)?([^/?]+).*$#\2#')"
HOST="${HOSTPORT%%:*}"
PORT="${HOSTPORT##*:}"
[[ "$PORT" == "$HOST" ]] && PORT="6379"   # no explicit port → default

# ── 2a. Detect the literal-placeholder paste-trap ───────────────────
# 2026-05-31 operator pasted `REDIS_URL='rediss://...'` verbatim from a
# stale doc snippet. The script then "detected backend=unknown,
# host=..." which was confusing — the actual problem was the literal
# `...` placeholder. Bail early with a verdict that names the cause.
case "$HOST" in
  ""|"..."|"<host>"|"YOUR_HOST"|"HOST")
    echo "  ✗ host='$HOST' is a literal placeholder, not a real Redis host."
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "  VERDICT: PLACEHOLDER_URL — you set REDIS_URL to a placeholder,"
    echo "  not a real value. Two fixes:"
    echo ""
    echo "    A. Use the live secret (recommended for already-deployed"
    echo "       Redis):"
    echo "         bash \"\$(git rev-parse --show-toplevel)/apps/dma-insights/infra/preflight-redis.sh\" --from-secret"
    echo ""
    echo "    B. Set REDIS_URL to a real value first, then re-run:"
    echo "         export REDIS_URL='rediss://default:<token>@<host>:6379'"
    echo "         bash \"\$(git rev-parse --show-toplevel)/apps/dma-insights/infra/preflight-redis.sh\""
    echo "═══════════════════════════════════════════════════════════════"
    exit 2
    ;;
esac

# Hint masking — operators sometimes paste DSNs to share; do NOT print
# the password segment. The HOST is non-sensitive by itself.
case "$HOST" in
  *.upstash.io)        BACKEND="upstash" ;;
  10.*|172.1[6-9].*|172.2[0-9].*|172.3[01].*|192.168.*)
                       BACKEND="memorystore" ;;
  *)                   BACKEND="unknown" ;;
esac
echo "  ℹ detected backend: $BACKEND (host=$HOST, port=$PORT)"

# ── 2b. Auto-install redis-py if missing ────────────────────────────
# Without redis-py, the script's only probe is redis-cli — and Cloud
# Shell's redis-cli sometimes can't TLS to rediss:// hosts depending
# on its build flags. redis-py's `from_url('rediss://…')` is the
# reliable second probe. Auto-install is silent + best-effort; if pip
# is missing or offline, the script still works (redis-py probe just
# skips). One-time cost; subsequent runs hit the import cache.
if command -v python3 >/dev/null 2>&1; then
  if ! python3 -c "import redis" 2>/dev/null; then
    if command -v pip3 >/dev/null 2>&1; then
      pip3 install --user --quiet redis 2>/dev/null || true
    elif command -v pip >/dev/null 2>&1; then
      pip install --user --quiet redis 2>/dev/null || true
    fi
  fi
fi

# ── 3. redis-cli + python redis-py round-trip probes ────────────────
# For Memorystore we ALREADY know the probe will fail (Cloud Shell can't
# reach a VPC-internal address) and the failure is expected. Running the
# probes anyway just produces 6-12s of ⚠ "failed" lines that look like
# real problems but aren't — operators reported confusion (2026-05-30).
# Short-circuit: skip the probes for Memorystore, print a single info
# line, hand off to the post-deploy gate as the actual verification.
#
# Upstash + unknown backends DO run the probes — those should succeed
# from Cloud Shell, so a failure there IS meaningful.
CLI_OK=0; PY_OK=0
REACHABLE=0
if [[ "$BACKEND" == "memorystore" ]]; then
  echo "  ℹ Memorystore is VPC-internal — skipping Cloud Shell probes"
  echo "    (they would fail by design; expected, not an error)."
  echo "    Real verification: post-deploy via /readyz, which the"
  echo "    backend serves from inside the VPC."
else
  if command -v redis-cli >/dev/null 2>&1; then
    # 2026-06 fix: for rediss:// URLs (Upstash TLS), the default
    # Cloud Shell redis-cli build lacks OpenSSL/TLS support, so the
    # probe always fails with a misleading ⚠ even though Upstash is
    # reachable (redis-py confirms). Downgrade the message to INFO
    # when the URL is TLS + the redis-cli probe fails; the redis-py
    # probe below is the authoritative one. CLI_OK still requires a
    # real PONG, so this doesn't mask actual outages.
    if timeout 6 redis-cli -u "$REDIS_URL" --no-auth-warning -t 4 PING 2>/dev/null \
         | grep -q PONG; then
      echo "  ✓ redis-cli PING → PONG"; CLI_OK=1
    elif [[ "$REDIS_URL" == rediss://* ]]; then
      echo "  ℹ redis-cli skipped (TLS unsupported by this Cloud Shell build —"
      echo "    redis-py probe below is authoritative for rediss:// hosts)"
    else
      echo "  ⚠ redis-cli PING failed (or timed out after 6s)"
    fi
  else
    echo "  ⚠ redis-cli not installed; skipping CLI probe"
  fi
  if command -v python3 >/dev/null 2>&1; then
    if python3 -c "
import os, sys
try:
    import redis
except ImportError:
    sys.exit(2)
try:
    r = redis.from_url(os.environ['REDIS_URL'], socket_connect_timeout=4)
    r.ping()
except Exception as e:
    print(f'    redis-py exception: {type(e).__name__}: {e}', file=sys.stderr); sys.exit(1)
" 2>&1; then
      echo "  ✓ redis-py round-trip OK"; PY_OK=1
    else
      rc=$?
      if [[ $rc -eq 2 ]]; then
        echo "  ⚠ redis-py not installed (pip install redis); skipping"
      else
        echo "  ⚠ redis-py round-trip failed"
      fi
    fi
  else
    echo "  ⚠ python3 not on PATH; skipping redis-py probe"
  fi
  [[ "$CLI_OK" == "1" || "$PY_OK" == "1" ]] && REACHABLE=1
fi

# ── 4. Verdict (the actionable bit) ─────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════"
case "$BACKEND" in
  upstash)
    if [[ "$REACHABLE" == "1" ]]; then
      echo "  VERDICT: OK — Upstash reachable from Cloud Shell. Proceed to deploy."
      exit 0
    fi
    echo "  VERDICT: UPSTASH_FATAL — Upstash should be reachable from"
    echo "  Cloud Shell over the public internet but the probe failed."
    echo "  Likely causes:"
    echo "    • REDIS_URL has the wrong host, port, or password"
    echo "    • Upstash database is paused (check Upstash console)"
    echo "    • Cloud Shell egress is blocked (rare — retry from another shell)"
    echo "  DO NOT deploy until the probe succeeds."
    exit 1
    ;;
  memorystore)
    if [[ "$REACHABLE" == "1" ]]; then
      echo "  VERDICT: OK — Memorystore reachable (you're inside its VPC)."
      exit 0
    fi
    echo "  VERDICT: OK (Memorystore VPC-internal — proceed to deploy)."
    echo ""
    echo "  $HOST:$PORT is an RFC-1918 address; Cloud Shell can't reach"
    echo "  it by design. Cloud Run reaches Memorystore through the VPC"
    echo "  connector. This is the EXPECTED preflight outcome, not an error."
    echo ""
    echo "  → Next: continue with the deploy. The post-deploy gate"
    echo "    (\`infra/live-data-flow-gate.sh\` → /readyz) will surface"
    echo "    any real Redis connectivity issue from Cloud Run itself."
    exit 0
    ;;
  unknown)
    if [[ "$REACHABLE" == "1" ]]; then
      echo "  VERDICT: OK — host '$HOST' reachable and responding to PING."
      exit 0
    fi
    echo "  VERDICT: UNKNOWN_HOST — host '$HOST' is neither Upstash nor"
    echo "  a recognized RFC-1918 (VPC) range, and the probe failed."
    echo "  This MIGHT be a non-blocker (e.g. peered VPC) or a real"
    echo "  problem. Manually verify the URL is correct before deploying."
    exit 0
    ;;
esac
