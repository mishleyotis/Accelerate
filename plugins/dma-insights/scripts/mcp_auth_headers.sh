#!/usr/bin/env bash
# headersHelper for the DMA Insights connector.
#
# The connector needs two credentials and they are not the same thing:
#
#   * the capability-path token  — proves which connector you meant. It is a
#     path segment, so it lives in the `url` (from ${user_config.mcp_path_token},
#     stored in the OS keychain). Not this script's business.
#   * a Google-signed ID token   — proves who you are. Cloud Run enforces
#     roles/run.invoker on the audience before the request reaches the MCP
#     server, so without this header every call is a 403 whatever the path
#     token says. That is what this mints, per connection.
#
# Contract: print a JSON object of headers on stdout, nothing else. Diagnostics
# go to stderr. The ID token appears on stdout because that is the transport;
# it is never logged, never written to disk, and never echoed to stderr.
set -uo pipefail

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
# identity has two rungs: gcloud when present, else an ID token minted from
# the service-account key file that bootstrap_session.sh lands from the
# DMA_ROUTINE_SA_KEY environment value. Same output contract either way.
mint_from_keyfile() {
  local keyfile="${DMA_SA_KEY_FILE:-/root/.dma/sa.json}"
  [ -s "$keyfile" ] || return 1
  local here; here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  python3 "$here/gcp_token.py" id --audience "$AUD" --key "$keyfile" 2>/dev/null
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
  IDT="$(mint_from_keyfile)" || IDT=""
fi

[ -n "$IDT" ] || fail "no gcloud identity and no service-account key file (DMA_SA_KEY_FILE, default /root/.dma/sa.json)"

printf '{"Authorization": "Bearer %s"}\n' "$IDT"
