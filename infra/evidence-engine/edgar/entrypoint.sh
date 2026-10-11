#!/bin/sh
set -eu
: "${MCP_PATH_TOKEN:?MCP_PATH_TOKEN is required}"
: "${SEC_EDGAR_USER_AGENT:?SEC_EDGAR_USER_AGENT is required by SEC fair-access policy}"
STATEFUL_ARGS=""
if [ "${STATEFUL:-0}" = "1" ]; then STATEFUL_ARGS="--stateful --sessionTimeout 60000"; fi
exec supergateway \
  --stdio "uvx --python 3.11 --from sec-edgar-mcp==1.1.0 sec-edgar-mcp" \
  --outputTransport streamableHttp \
  --streamableHttpPath "/mcp-${MCP_PATH_TOKEN}" \
  --port "${PORT:-8000}" --healthEndpoint /healthz $STATEFUL_ARGS
