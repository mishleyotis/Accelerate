#!/usr/bin/env bash
# Build every research-layer backend image and probe it through its door —
# on every pull request, before any release can try (CI job evidence-images).
#
# Why (2026-10-11): the first approved evidence release failed at step 4
# building dmai-searxng — the official SearXNG image had become Void Linux
# (no apk), the npm pin named a version that was never published, and the
# fetch/edgar gateway tag had moved a major version. None of it was visible
# until production, because the images had never been built anywhere else.
#
#   bash infra/evidence-engine/image_smoke.sh [searxng fetch edgar]
#
# Needs docker and python3. The path token is a random throwaway for this
# run, never a production secret, and is never printed. Exit 0 only when
# every image builds and every probe passes.
set -euo pipefail
cd "$(dirname "$0")"
if [ "$#" -gt 0 ]; then KINDS=("$@"); else KINDS=(searxng fetch edgar); fi
TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
export PROBE_TOKEN="$TOKEN"
port=18100
fail=0
started=()
cleanup() { for c in "${started[@]:-}"; do [ -n "$c" ] && docker rm -f "$c" >/dev/null 2>&1 || true; done; }
trap cleanup EXIT

for kind in "${KINDS[@]}"; do
  echo "== $kind: build"
  if ! docker build --pull -q -t "dmai-$kind:ci" "$kind" >/dev/null; then
    echo "FAIL $kind build"; fail=1; continue
  fi
  echo "PASS $kind build"
  extra=()
  case "$kind" in
    searxng) extra=(-e "SEARXNG_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(24))')") ;;
    edgar)   extra=(-e "SEC_EDGAR_USER_AGENT=Zennify DMA Insights CI (+https://www.zennify.com)") ;;
  esac
  port=$((port + 1))
  name="ee-smoke-$kind"
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker run -d --name "$name" -p "127.0.0.1:$port:8000" -e PORT=8000 \
    -e MCP_PATH_TOKEN="$TOKEN" "${extra[@]}" "dmai-$kind:ci" >/dev/null
  started+=("$name")
  echo "== $kind: probe"
  if ! python3 image_probe.py "$kind" "http://127.0.0.1:$port"; then
    fail=1
    echo "--- $kind container log (tail) ---"
    docker logs "$name" 2>&1 | tail -60 | sed "s/$TOKEN/****/g"
  fi
done

[ "$fail" -eq 0 ] && echo "image smoke: every backend builds and answers at its door" \
                  || echo "image smoke: FAILED (see above)"
exit "$fail"
