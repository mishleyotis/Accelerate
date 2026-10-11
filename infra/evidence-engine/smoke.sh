#!/usr/bin/env bash
# Post-deploy door probes for the four evidence services. Prints PASS/FAIL
# per probe; never prints a token (the path token is read into a variable
# and used in a URL that is NOT echoed; set +x guards an xtrace caller).
set -euo pipefail
set +x
PROJECT_ID="${PROJECT_ID:-digital-maturity-assessor}"
REGION="${REGION:-us-central1}"
fail=0
probe() { # name secret kind
  local name="$1" secret="$2" kind="$3"
  local url tok idt
  url="$(gcloud run services describe "$name" --project="$PROJECT_ID" --region="$REGION" --format='value(status.url)')"
  idt="$(gcloud auth print-identity-token --audiences="$url")"
  tok="$(gcloud secrets versions access latest --secret="$secret" --project="$PROJECT_ID")"
  # 1 · a wrong path is a 404 (the capability path is the second factor)
  code="$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $idt" -X POST "$url/mcp-not-the-token" \
          -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}')"
  [ "$code" = "404" ] && echo "PASS $name wrong path -> 404" || { echo "FAIL $name wrong path -> $code"; fail=1; }
  # 2 · tools/list is non-empty on the right path
  if [ "$kind" = "engine" ]; then path="$url/mcp"; hdr="X-DMA-Path-Token: $tok"; else path="$url/mcp-$tok"; hdr="X-Smoke: 1"; fi
  sid="$(curl -s -D - -o /dev/null -H "Authorization: Bearer $idt" -H "$hdr" -X POST "$path" -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
          -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}' | awk 'tolower($1)=="mcp-session-id:"{print $2}' | tr -d '\r')"
  n="$(curl -s -H "Authorization: Bearer $idt" -H "$hdr" ${sid:+-H "Mcp-Session-Id: $sid"} -X POST "$path" -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
        -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' | sed -n 's/^data: //p; /^{/p' | tail -1 | python3 -c 'import sys,json; print(len(json.load(sys.stdin)["result"]["tools"]))' 2>/dev/null || echo 0)"
  [ "${n:-0}" -gt 0 ] && echo "PASS $name tools/list -> $n tools" || { echo "FAIL $name tools/list empty"; fail=1; }
}
probe dmai-evidence dmai-evidence-path-token engine
probe dmai-searxng  dmai-searxng-path-token  gateway
probe dmai-fetch    dmai-fetch-path-token    gateway
probe dmai-edgar    dmai-edgar-path-token    gateway
exit $fail
