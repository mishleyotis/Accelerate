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

AUD="${DMA_MCP_HOST:-https://dmai-mcp-306195530103.us-central1.run.app}"
GCLOUD="${GCLOUD_BIN:-gcloud}"

fail() {
  # A clean 403 from Cloud Run is more diagnosable than a stalled connection,
  # so emit no Authorization header rather than a broken one.
  echo "dma-insights: no identity token ($1); connector calls will 403" >&2
  printf '{}\n'
  exit 0
}

command -v "$GCLOUD" >/dev/null 2>&1 || fail "gcloud not on PATH"

# A stale CLOUDSDK_AUTH_ACCESS_TOKEN in the environment overrides the activated
# account and fails with a 401 that reads like a permissions problem.
TOKEN="$(CLOUDSDK_AUTH_ACCESS_TOKEN= "$GCLOUD" auth print-identity-token \
           --audiences="$AUD" 2>/dev/null)" || fail "gcloud auth failed"

[ -n "$TOKEN" ] || fail "gcloud returned an empty token"

printf '{"Authorization": "Bearer %s"}\n' "$TOKEN"
