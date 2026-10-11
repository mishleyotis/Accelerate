#!/bin/sh
# Three processes, one door. Any exit ends the container (Cloud Run restarts
# it). MCP_PATH_TOKEN and SEARXNG_SECRET_KEY come from Secret Manager and are
# never printed; set +x guards an xtrace caller.
#
# POSIX sh on busybox: the official image has no bash and no curl (measured
# 2026-10-11), so no arrays, no `wait -n`, and the health probe is wget.
set -eu
set +x
: "${MCP_PATH_TOKEN:?MCP_PATH_TOKEN is required}"
: "${SEARXNG_SECRET_KEY:?SEARXNG_SECRET_KEY is required}"
# SearXNG reads server.secret_key from the SEARXNG_SECRET environment
# variable (documented override); settings.yml deliberately carries none.
export SEARXNG_SECRET="$SEARXNG_SECRET_KEY"
# Loopback only. The image's own entrypoint serves through granian, which
# binds GRANIAN_HOST (default `::`, every interface) and maps SEARXNG_PORT.
export GRANIAN_HOST=127.0.0.1 GRANIAN_PORT=8080 SEARXNG_PORT=8080

# The official Brave Search API (`braveapi`), when the owner has stored a key
# (Secret Manager `dmai-brave-search-api-key`, mounted by deploy-evidence.sh
# only when it exists): the one general engine no CAPTCHA can block. The
# settings ship it inactive; a runtime copy activates it with the key. awk
# reads the key from the environment, so it never reaches a command line.
if [ -n "${BRAVE_SEARCH_API_KEY:-}" ]; then
  awk '
    /^  - name: braveapi$/ { print; print "    disabled: false"; print "    inactive: false";
                             print "    api_key: \"" ENVIRON["BRAVE_SEARCH_API_KEY"] "\""; skip = 1; next }
    skip && /^    inactive: true$/ { skip = 0; next }
    { skip = 0; print }
  ' /etc/searxng/settings.yml > /tmp/searxng-settings.yml
  chmod 600 /tmp/searxng-settings.yml
  export SEARXNG_SETTINGS_PATH=/tmp/searxng-settings.yml
  echo "dmai-searxng: braveapi active (key from Secret Manager)"
fi

# 1 · SearXNG, through the official image's own entrypoint (SEARXNG_CMD only
# for image_smoke.sh's off-image wiring check).
"${SEARXNG_CMD:-/usr/local/searxng/entrypoint.sh}" &
SEARX_PID=$!
i=0
while [ "$i" -lt 90 ]; do
  wget -q -O /dev/null "http://127.0.0.1:8080/healthz" 2>/dev/null && break
  i=$((i + 1))
  sleep 1
done

# 2 · mcp-searxng (stdio) -> streamable HTTP on 127.0.0.1:8001, path /mcp
set -- --stdio "mcp-searxng" --outputTransport streamableHttp \
       --streamableHttpPath "/mcp" --port 8001 --healthEndpoint /healthz
if [ "${STATEFUL:-0}" = "1" ]; then set -- "$@" --stateful --sessionTimeout 60000; fi
SEARXNG_URL=http://127.0.0.1:8080 supergateway "$@" &
GW_PID=$!

# 3 · the door
PORT="${PORT:-8000}" node "${PROXY_JS:-/opt/dmai/proxy.js}" &
PROXY_PID=$!

# busybox ash has no `wait -n`: the first of the three to exit ends the container
while kill -0 "$SEARX_PID" 2>/dev/null && kill -0 "$GW_PID" 2>/dev/null \
      && kill -0 "$PROXY_PID" 2>/dev/null; do
  sleep 2
done
exit 1
