#!/usr/bin/env bash
# Evidence for a failed image_smoke.sh run: what is inside each gateway image
# and what its MCP server prints when started directly (no gateway, so the
# server's own error output is not lost). Diagnostics only; it changes nothing
# and decides nothing. The CI job evidence-images runs it when the smoke fails.
#
# Written 2026-10-11 after PR #94's first run: fetch's child exited before the
# first request (EPIPE, no stderr captured) and edgar's crashed importing
# pydantic_core. For each kind it reports, on the pinned base AND on the old
# floating `uvx` tag, so the log says which base the failure belongs to:
#   1. /etc/os-release, python3 / uv / uvx / node versions
#   2. the server started directly on stdin with one `initialize` line
#      (exit 124 means it was still serving at the 90 s cap: it started)
#   3. (fetch) the same with and without the --user-agent argument, both
#      through `sh -c` as Supergateway spawns it
#
#   bash infra/evidence-engine/image_diag.sh [fetch edgar]
#
# No path token or secret is used. EDGAR gets the CI user agent SEC requires.
set -uo pipefail
cd "$(dirname "$0")"
if [ "$#" -gt 0 ]; then KINDS=("$@"); else KINDS=(fetch edgar); fi
INIT='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"image-diag","version":"1"}}}'
UA_ENV=(-e "SEC_EDGAR_USER_AGENT=Zennify DMA Insights CI (+https://www.zennify.com)")

inspect() {   # image
  echo "--- inside $1"
  docker run --rm --entrypoint sh "$1" -c '
    . /etc/os-release 2>/dev/null && echo "os: $PRETTY_NAME" || echo "os: (no /etc/os-release)"
    for b in python3 uv uvx node supergateway; do
      p=$(command -v "$b" 2>/dev/null) || { echo "$b: not on PATH"; continue; }
      v=$("$b" --version 2>&1 | head -1); echo "$b: $p  $v"
    done
    ldd --version 2>&1 | head -1 | sed "s/^/libc: /" || true' 2>&1
}

start_direct() {   # image label command
  echo "--- $2: started directly (sh -c, one initialize line, 90 s cap)"
  local name="ee-diag-$$-$RANDOM"
  printf '%s\n' "$INIT" | timeout 90 docker run -i --rm --name "$name" "${UA_ENV[@]}" --entrypoint sh "$1" -c "$3" 2>&1 \
    | tail -40
  echo "--- $2: exit ${PIPESTATUS[1]} (124 = still running at the cap)"
  docker rm -f "$name" >/dev/null 2>&1 || true
}

for kind in "${KINDS[@]}"; do
  pinned="dmai-$kind:diag-pinned"; floating="dmai-$kind:diag-floating"
  echo "===== $kind"
  docker build -q -t "$pinned" "$kind" >/dev/null || { echo "build failed: $kind (pinned)"; continue; }
  tmp="$(mktemp -d)"; cp -r "$kind"/. "$tmp"/
  sed -i -E 's#^FROM supercorp/supergateway:[^ ]+#FROM supercorp/supergateway:uvx#' "$tmp/Dockerfile"
  grep '^FROM' "$tmp/Dockerfile" | sed 's/^/floating base: /'
  docker build -q -t "$floating" "$tmp" >/dev/null || echo "build failed: $kind (floating)"
  rm -rf "$tmp"
  for img in "$pinned" "$floating"; do
    docker image inspect "$img" >/dev/null 2>&1 || continue
    inspect "$img"
    case "$kind" in
      fetch)
        start_direct "$img" "$img fetch (with --user-agent)" \
          'uvx --from mcp-server-fetch==2026.8.18 mcp-server-fetch --user-agent=Zennify-DMA-Insights-fetch/1.0 (+https://www.zennify.com)'
        start_direct "$img" "$img fetch (no --user-agent)" \
          'uvx --from mcp-server-fetch==2026.8.18 mcp-server-fetch' ;;
      edgar)
        start_direct "$img" "$img edgar" \
          'uvx --python 3.11 --from sec-edgar-mcp==1.1.0 sec-edgar-mcp' ;;
    esac
  done
done
exit 0
