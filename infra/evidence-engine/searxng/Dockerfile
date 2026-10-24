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
# Built ON the official image. Measured 2026-10-11 after the first approved
# release failed here: the official image is Void Linux (glibc, busybox, no
# package manager, no bash, no curl) — not Alpine, so `apk add` cannot run.
# Node therefore comes from the official node image (glibc-linked; the base
# ships libstdc++ and libgcc_s, so the binary runs as is), and the entrypoint
# is POSIX sh. Every FROM is pinned by digest: an upstream rebase changes this
# file in review, never a release. image_smoke.sh builds and probes the image
# in CI before any deploy.
FROM node:22-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392 AS node
RUN npm install -g --omit=dev --no-audit --no-fund mcp-searxng@2.5.1 supergateway@3.4.0 \
    && npm cache clean --force

FROM searxng/searxng:2026.10.9-f4822b3fc@sha256:85492ba800a861e3e8ff6014c430e81369fe6ca766a9990595f616d1ce95b272
USER root
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules/mcp-searxng /usr/local/lib/node_modules/mcp-searxng
COPY --from=node /usr/local/lib/node_modules/supergateway /usr/local/lib/node_modules/supergateway
RUN chmod +x /usr/local/lib/node_modules/mcp-searxng/dist/cli.js \
             /usr/local/lib/node_modules/supergateway/dist/index.js \
    && ln -sf /usr/local/lib/node_modules/mcp-searxng/dist/cli.js /usr/local/bin/mcp-searxng \
    && ln -sf /usr/local/lib/node_modules/supergateway/dist/index.js /usr/local/bin/supergateway \
    && node --version
COPY settings.yml /etc/searxng/settings.yml
COPY proxy.js /opt/dmai/proxy.js
COPY entrypoint.sh /opt/dmai/entrypoint.sh
RUN chmod +x /opt/dmai/entrypoint.sh
ENV PORT=8000 SEARXNG_PORT=8080 GRANIAN_HOST=127.0.0.1 GRANIAN_PORT=8080 \
    SEARXNG_SETTINGS_PATH=/etc/searxng/settings.yml
EXPOSE 8000
ENTRYPOINT ["/opt/dmai/entrypoint.sh"]
