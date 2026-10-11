# dmai-fetch: mcp-server-fetch (MIT) over Supergateway (MIT), streamable HTTP
# on a secret path. The raw fallback read tool; the evidence engine never
# calls it (the engine fetches in-process with politeness and robots).
#
# Supergateway's uvx image ships uv/uvx so `uvx mcp-server-fetch` runs
# without a second image. Verified 2026-10-10 (README: "docker run ...
# supercorp/supergateway:uvx --stdio "uvx mcp-server-fetch"").
# Pinned by digest (2026-10-11): the bare `uvx` tag moved to Supergateway 4.1.0
# on 2026-09-30; the entrypoint's flags are 3.4's, the version dmai-searxng
# pins on npm and image_smoke.sh proves in CI.
FROM supercorp/supergateway:3.4.0-uvx@sha256:219f3ca136730894ec089350a3cc4c01c0a9dc50103dcb67b8fa7664b0170a22
ENV PORT=8000
# Pre-resolve the package at build time so cold starts do not download it.
RUN uvx --from mcp-server-fetch==2026.8.18 mcp-server-fetch --help >/dev/null 2>&1 || true
COPY entrypoint.sh /entrypoint.sh
ENTRYPOINT ["/bin/sh", "/entrypoint.sh"]
