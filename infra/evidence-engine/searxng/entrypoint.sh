#!/usr/bin/env bash
# Three processes, one door. Any exit ends the container (Cloud Run restarts
# it). MCP_PATH_TOKEN and SEARXNG_SECRET_KEY come from Secret Manager and are
# never printed; set +x guards an xtrace caller.
set -euo pipefail
set +x
: "${MCP_PATH_TOKEN:?MCP_PATH_TOKEN is required}"
: "${SEARXNG_SECRET_KEY:?SEARXNG_SECRET_KEY is required}"
# SearXNG reads server.secret_key from the SEARXNG_SECRET environment
# variable (documented override); settings.yml deliberately carries none.
export SEARXNG_SECRET="$SEARXNG_SECRET_KEY"
export SEARXNG_BIND_ADDRESS=127.0.0.1 SEARXNG_PORT=8080

# 1 · SearXNG, through the official image's own entrypoint when present
# (granian server, settings merged from /etc/searxng), else the webapp.
if [ -x /usr/local/searxng/entrypoint.sh ]; then
  /usr/local/searxng/entrypoint.sh >/proc/1/fd/1 2>&1 &
elif [ -x /usr/local/searxng/dockerfiles/docker-entrypoint.sh ]; then
  /usr/local/searxng/dockerfiles/docker-entrypoint.sh >/proc/1/fd/1 2>&1 &
else
  (cd /usr/local/searxng && /usr/local/searxng/venv/bin/python -m searx.webapp) >/proc/1/fd/1 2>&1 &
fi
SEARX_PID=$!
for _ in $(seq 1 90); do
  curl -sf "http://127.0.0.1:8080/healthz" >/dev/null 2>&1 && break
  sleep 1
done

# 2 · mcp-searxng (stdio) -> streamable HTTP on 127.0.0.1:8001, path /mcp
GW_ARGS=(--stdio "mcp-searxng" --outputTransport streamableHttp
         --streamableHttpPath "/mcp" --port 8001 --healthEndpoint /healthz)
if [ "${STATEFUL:-0}" = "1" ]; then GW_ARGS+=(--stateful --sessionTimeout 60000); fi
SEARXNG_URL=http://127.0.0.1:8080 supergateway "${GW_ARGS[@]}" >/proc/1/fd/1 2>&1 &
GW_PID=$!

# 3 · the door
MCP_PATH_TOKEN="$MCP_PATH_TOKEN" PORT="${PORT:-8000}" node /opt/dmai/proxy.js >/proc/1/fd/1 2>&1 &
PROXY_PID=$!

wait -n "$SEARX_PID" "$GW_PID" "$PROXY_PID"
exit 1
