#!/bin/sh
# MCP_PATH_TOKEN from Secret Manager; never printed. robots.txt stays honoured
# (the server's default); the declared UA names the tool and a public URL.
set -eu
: "${MCP_PATH_TOKEN:?MCP_PATH_TOKEN is required}"
STATEFUL_ARGS=""
if [ "${STATEFUL:-0}" = "1" ]; then STATEFUL_ARGS="--stateful --sessionTimeout 60000"; fi
exec supergateway \
  --stdio "uvx --from mcp-server-fetch==2026.8.18 mcp-server-fetch --user-agent=Zennify-DMA-Insights-fetch/1.0 (+https://www.zennify.com)" \
  --outputTransport streamableHttp \
  --streamableHttpPath "/mcp-${MCP_PATH_TOKEN}" \
  --port "${PORT:-8000}" --healthEndpoint /healthz $STATEFUL_ARGS
