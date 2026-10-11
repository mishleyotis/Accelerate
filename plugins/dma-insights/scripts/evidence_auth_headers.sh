#!/usr/bin/env bash
# headersHelper for the research-layer services (evidence engine and its
# three self-hosted backends). A SIBLING of mcp_auth_headers.sh, not a
# change to it: that script's rungs and exit-0 semantics are frozen (brief
# §7.1); this one takes the audience and the Secret Manager name as
# arguments so one helper serves four services.
#
#   evidence_auth_headers.sh <audience-url> <secret-name> [header|segment]
#
# Prints a JSON object of headers on stdout, nothing else. In `header` mode
# (the engine, which checks X-DMA-Path-Token like dmai-mcp) the token is a
# header; in `segment` mode (the Supergateway backends, whose capability is
# the URL path /mcp-<token>) the token is returned under the pseudo-header
# "X-DMA-Path-Segment" for evidence_proxy.py to place in the path — it is
# never sent as a header to those services. Diagnostics go to stderr. No
# token is ever logged or echoed; set +x guards an xtrace caller.
#
# Rungs, identical to mcp_auth_headers.sh: identity from gcloud, else the
# key file bootstrap_session.sh lands, else DMA_ROUTINE_SA_KEY_B64; the
# token from DMA_<SECRET>_TOKEN in the environment, else the cache file
# /root/.dma/<secret-name>, else Secret Manager with an access token from
# the same identity.
set -uo pipefail
set +x

AUD="${1:?audience url}"
SECRET="${2:?secret name}"
MODE="${3:-header}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

fail() {
  echo "dma-insights: no identity token for ${AUD} ($1); calls will 403" >&2
  printf '{}\n'
  exit 0
}

find_gcloud() {
  if [ -n "${GCLOUD_BIN:-}" ] && [ -x "$GCLOUD_BIN" ]; then printf '%s' "$GCLOUD_BIN"; return 0; fi
  if command -v gcloud >/dev/null 2>&1; then command -v gcloud; return 0; fi
  for c in "$HOME/google-cloud-sdk/bin/gcloud" /root/google-cloud-sdk/bin/gcloud \
           /usr/local/google-cloud-sdk/bin/gcloud /opt/google-cloud-sdk/bin/gcloud /snap/bin/gcloud; do
    [ -x "$c" ] && { printf '%s' "$c"; return 0; }
  done
  return 1
}

keyfile="${DMA_SA_KEY_FILE:-/root/.dma/sa.json}"
mint() { # id|access
  if [ -s "$keyfile" ]; then
    python3 "$HERE/gcp_token.py" "$1" ${2:+--audience "$2"} --key "$keyfile" 2>/dev/null
  else
    python3 "$HERE/gcp_token.py" "$1" ${2:+--audience "$2"} 2>/dev/null
  fi
}

IDT=""
if GCLOUD="$(find_gcloud)"; then
  IDT="$(CLOUDSDK_AUTH_ACCESS_TOKEN= "$GCLOUD" auth print-identity-token --audiences="$AUD" 2>/dev/null)" || IDT=""
fi
[ -n "$IDT" ] || IDT="$(mint id "$AUD")" || IDT=""
[ -n "$IDT" ] || fail "no gcloud identity, no key file ($keyfile) and no DMA_ROUTINE_SA_KEY_B64"

ENVKEY="DMA_$(printf '%s' "$SECRET" | tr 'a-z-' 'A-Z_')"
TOK="${!ENVKEY:-}"
CACHE="${DMA_TOKEN_CACHE_DIR:-/root/.dma}/${SECRET}"
if [ -z "$TOK" ] && [ -s "$CACHE" ]; then TOK="$(tr -d '[:space:]' < "$CACHE")"; fi
if [ -z "$TOK" ]; then
  ACT=""
  if [ -n "${GCLOUD:-}" ]; then ACT="$(CLOUDSDK_AUTH_ACCESS_TOKEN= "$GCLOUD" auth print-access-token 2>/dev/null)" || ACT=""; fi
  [ -n "$ACT" ] || ACT="$(mint access)" || ACT=""
  if [ -n "$ACT" ]; then
    TOK="$(curl -sf -H "Authorization: Bearer $ACT" \
      "https://secretmanager.googleapis.com/v1/projects/${DMA_PROJECT_ID:-digital-maturity-assessor}/secrets/${SECRET}/versions/latest:access" \
      | python3 -c 'import sys,json,base64;sys.stdout.write(base64.b64decode(json.load(sys.stdin)["payload"]["data"]).decode())' 2>/dev/null)" || TOK=""
    if [ -n "$TOK" ]; then
      ( umask 077 && mkdir -p "$(dirname "$CACHE")" 2>/dev/null && printf '%s' "$TOK" > "$CACHE" ) 2>/dev/null || true
    fi
  fi
fi

if [ -z "$TOK" ]; then
  echo "dma-insights: no capability token for ${SECRET} (env ${ENVKEY}, ${CACHE}, or Secret Manager); ${AUD} will 404" >&2
  printf '{"Authorization": "Bearer %s"}\n' "$IDT"
elif [ "$MODE" = "segment" ]; then
  printf '{"Authorization": "Bearer %s", "X-DMA-Path-Segment": "%s"}\n' "$IDT" "$TOK"
else
  printf '{"Authorization": "Bearer %s", "X-DMA-Path-Token": "%s"}\n' "$IDT" "$TOK"
fi
