# dmai-searxng: SearXNG (AGPL-3.0, unmodified) on 127.0.0.1:8080, mcp-searxng
# (MIT) over Supergateway (MIT) on 127.0.0.1:8001, and ONE front door on $PORT
# (proxy.js, dependency-free node) that routes
#     /mcp-<token>             -> Supergateway (the raw fallback connector)
#     /searx-json/<token>/...  -> SearXNG's JSON API (the engine's backend)
#     /healthz                 -> 200 when both are up
# and answers 404 to everything else. Nothing reaches SearXNG except through
# this container; the secret segment is the capability (smoke.sh proves a
# wrong path is a 404).
#
# Built ON the official image (Alpine) rather than copying its venv into a
# Debian base: the venv's compiled wheels are musl-linked and would not run
# on glibc. Image pins: the official tag is date-stamped; deploy-evidence.sh
# records the resolved digest on the revision. Verified 2026-10-10.
FROM searxng/searxng:latest
USER root
RUN apk add --no-cache nodejs npm curl bash \
    && npm install -g mcp-searxng@0.11.3 supergateway@3.4.0 \
    && npm cache clean --force
COPY settings.yml /etc/searxng/settings.yml
COPY proxy.js /opt/dmai/proxy.js
COPY entrypoint.sh /opt/dmai/entrypoint.sh
RUN chmod +x /opt/dmai/entrypoint.sh
ENV PORT=8000 SEARXNG_BIND_ADDRESS=127.0.0.1 SEARXNG_PORT=8080 \
    SEARXNG_SETTINGS_PATH=/etc/searxng/settings.yml
EXPOSE 8000
ENTRYPOINT ["/opt/dmai/entrypoint.sh"]
