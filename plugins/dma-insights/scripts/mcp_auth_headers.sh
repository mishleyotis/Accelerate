#!/usr/bin/env bash
# headersHelper for the DMA Insights connector.
#
# The connector needs two credentials and they are not the same thing:
#
#   * a Google-signed ID token   — proves who you are. Cloud Run enforces
#     roles/run.invoker on the audience before the request reaches the MCP
#     server, so without this header every call is a 403 whatever else is
#     right. Minted per connection, below.
#   * the capability-path token  — proves which connector you meant. It used
#     to be a URL segment filled from a REQUIRED plugin config option, which
#     meant every install sat "MCP pending" until a human pasted a secret
#     (owner, 2026-08-20: install must be automatic and all tools availed).
#     It now travels as the `X-DMA-Path-Token` header and THIS script fetches
#     it — environment override, then the cache bootstrap_session.sh lands,
#     then Secret Manager with an access token from the same identity rungs.
#     A header is also what an access log or an xtrace does NOT print the way
#     it prints a URL — the 2026-08-20 leak printed the capability URL.
#
# Contract: print a JSON object of headers on stdout, nothing else. Diagnostics
# go to stderr. The tokens appear on stdout because that is the transport;
# they are never logged and never echoed to stderr. The path-token cache file
# is 600 under /root/.dma, the same trust boundary as the key itself.
set -uo pipefail
# Trace-proofing, same incident, same rule as bootstrap_session.sh: a caller's
# bash -x must not print a credential this script handles.
set +x

AUD="${DMA_MCP_HOST:-https://dmai-mcp-dukrne5v4a-uc.a.run.app}"

fail() {
  # A clean 403 from Cloud Run is more diagnosable than a stalled connection,
  # so emit no Authorization header rather than a broken one.
  echo "dma-insights: no identity token ($1); connector calls will 403" >&2
  printf '{}\n'
  exit 0
}

# MCP servers are launched with the session's environment, and a helper that
# only consults PATH is one shell profile away from failing on a machine where
# gcloud is installed and working. Measured: on the container this was packaged
# in, gcloud lives in /root/google-cloud-sdk/bin and is absent from the PATH
# the Bash tool inherits.
find_gcloud() {
  if [ -n "${GCLOUD_BIN:-}" ] && [ -x "$GCLOUD_BIN" ]; then
    printf '%s' "$GCLOUD_BIN"; return 0
  fi
  if command -v gcloud >/dev/null 2>&1; then
    command -v gcloud; return 0
  fi
  for c in "$HOME/google-cloud-sdk/bin/gcloud" \
           /root/google-cloud-sdk/bin/gcloud \
           /usr/local/google-cloud-sdk/bin/gcloud \
           /opt/google-cloud-sdk/bin/gcloud \
           /snap/bin/gcloud; do
    [ -x "$c" ] && { printf '%s' "$c"; return 0; }
  done
  return 1
}

# Fresh routine containers have no gcloud at all (measured 2026-08-19), so
# identity has two rungs: gcloud when present, else gcp_token.py, which finds
# the service-account key itself — the file bootstrap_session.sh lands, or
# failing that the DMA_ROUTINE_SA_KEY_B64 environment value directly.
#
# The environment rung is deliberate and load-bearing. THIS SCRIPT RUNS AT
# SESSION START, when the connector registers; a bootstrap that runs as a
# step inside the session lands its key minutes too late and the connector's
# tools never resolve (measured 2026-08-20). Reading the credential from the
# environment means a scheduled routine authenticates from its first turn
# with nothing having to run beforehand.
mint_from_key() {
  local here; here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local keyfile="${DMA_SA_KEY_FILE:-/root/.dma/sa.json}"
  if [ -s "$keyfile" ]; then
    python3 "$here/gcp_token.py" id --audience "$AUD" --key "$keyfile" 2>/dev/null
  else
    python3 "$here/gcp_token.py" id --audience "$AUD" 2>/dev/null
  fi
}

# Named IDT, not TOKEN: scripts/scan_secrets.py reads `token="<20 chars>"` as
# a hardcoded credential, and a command substitution is indistinguishable
# from a literal to a regex. The scanner is right to be blunt — the variable
# renames instead.
IDT=""
if GCLOUD="$(find_gcloud)"; then
  # A stale CLOUDSDK_AUTH_ACCESS_TOKEN in the environment overrides the
  # activated account and fails with a 401 that reads like a permissions
  # problem.
  IDT="$(CLOUDSDK_AUTH_ACCESS_TOKEN= "$GCLOUD" auth print-identity-token \
             --audiences="$AUD" 2>/dev/null)" || IDT=""
fi
if [ -z "$IDT" ]; then
  IDT="$(mint_from_key)" || IDT=""
fi

[ -n "$IDT" ] || fail "no gcloud identity, no key file (DMA_SA_KEY_FILE, default /root/.dma/sa.json) and no DMA_ROUTINE_SA_KEY_B64 in the environment"

# ── the capability-path token, by rung ─────────────────────────────────────
# 1 · DMA_MCP_PATH_TOKEN in the environment (explicit override, and tests)
# 2 · the cache file bootstrap_session.sh writes (survives within a container)
# 3 · Secret Manager, read with an access token from the same identity rungs
#     as above — then cached for rung 2, so rotation propagates on the next
#     fresh connection and a Secret Manager blip does not break an
#     established container.
PATHTOK_FILE="${DMA_PATHTOK_FILE:-/root/.dma/pathtok}"
PATHTOK="${DMA_MCP_PATH_TOKEN:-}"
if [ -z "$PATHTOK" ] && [ -s "$PATHTOK_FILE" ]; then
  PATHTOK="$(cat "$PATHTOK_FILE" 2>/dev/null | tr -d '[:space:]')"
fi
if [ -z "$PATHTOK" ]; then
  ACT=""
  if [ -n "${GCLOUD:-}" ]; then
    ACT="$(CLOUDSDK_AUTH_ACCESS_TOKEN= "$GCLOUD" auth print-access-token 2>/dev/null)" || ACT=""
  fi
  if [ -z "$ACT" ]; then
    here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    keyfile="${DMA_SA_KEY_FILE:-/root/.dma/sa.json}"
    if [ -s "$keyfile" ]; then
      ACT="$(python3 "$here/gcp_token.py" access --key "$keyfile" 2>/dev/null)" || ACT=""
    else
      ACT="$(python3 "$here/gcp_token.py" access 2>/dev/null)" || ACT=""
    fi
  fi
  if [ -n "$ACT" ]; then
    PATHTOK="$(curl -sf -H "Authorization: Bearer $ACT" \
      "https://secretmanager.googleapis.com/v1/projects/digital-maturity-assessor/secrets/dmai-mcp-path-token/versions/latest:access" \
      | python3 -c 'import sys,json,base64;sys.stdout.write(base64.b64decode(json.load(sys.stdin)["payload"]["data"]).decode())' 2>/dev/null)" || PATHTOK=""
    if [ -n "$PATHTOK" ]; then
      ( umask 077 && mkdir -p "$(dirname "$PATHTOK_FILE")" 2>/dev/null \
        && printf '%s' "$PATHTOK" > "$PATHTOK_FILE" ) 2>/dev/null || true
    fi
  fi
fi

if [ -n "$PATHTOK" ]; then
  printf '{"Authorization": "Bearer %s", "X-DMA-Path-Token": "%s"}\n' "$IDT" "$PATHTOK"
else
  # Identity without the path token: a URL-segment install still works with
  # this; a static-URL install will 404 on /mcp, which stderr names here.
  echo "dma-insights: no connector path token (DMA_MCP_PATH_TOKEN, $PATHTOK_FILE, or Secret Manager via the identity above); static-URL connections will 404" >&2
  printf '{"Authorization": "Bearer %s"}\n' "$IDT"
fi
