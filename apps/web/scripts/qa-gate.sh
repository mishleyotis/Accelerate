#!/usr/bin/env bash
# The one-command interaction + screenshot QA gate.
#
#   apps/web/scripts/qa-gate.sh [port]        (default 3496)
#
# Brings the QA server up via qa-server.sh — which mints a fresh identity
# token, sweeps the port by /proc environ (NEVER pkill -f, which matches the
# session's own shell and kills it), starts next, and PROVES the overview
# serves sections before returning — then runs tests/qa-gate.js against it.
#
# Exit codes: 0 clean · 1 the gate found defects · 2 setup/harness failure.
set -uo pipefail

PORT="${1:-3496}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENTITY="${QA_ENTITY:-baxter-credit-union-bcu}"

# 1 · server. qa-server.sh fails loudly when the page would render "Entity not
#     found" (expired token, wrong entity) — a state that otherwise looks
#     exactly like a clean render and silently invalidates the whole sweep.
bash "$HERE/scripts/qa-server.sh" "$PORT" || exit 2

# 2 · playwright-core. Not a dependency of the app bundle; CI and local QA
#     supply it. Honour an explicit path, then look in the usual places.
if [ -z "${PLAYWRIGHT_CORE:-}" ]; then
  for c in "$HERE/node_modules/playwright-core" \
           /tmp/claude-0/*/*/scratchpad/node_modules/playwright-core \
           "$(npm root -g 2>/dev/null)/playwright-core"; do
    if [ -d "$c" ]; then export PLAYWRIGHT_CORE="$c"; break; fi
  done
fi
if [ -z "${PLAYWRIGHT_CORE:-}" ] && ! node -e 'require("playwright-core")' 2>/dev/null; then
  echo "playwright-core not found — npm i -D playwright-core, or set PLAYWRIGHT_CORE=/path/to/it" >&2
  exit 2
fi

# 3 · the gate. Screenshots land in tests/screens/ (gitignored).
node "$HERE/tests/qa-gate.js" "http://localhost:$PORT" "$ENTITY" \
  --shots "$HERE/tests/screens"
