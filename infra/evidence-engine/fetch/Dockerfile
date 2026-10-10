# dmai-fetch: mcp-server-fetch (MIT) over Supergateway (MIT), streamable HTTP
# on a secret path. The raw fallback read tool; the evidence engine never
# calls it (the engine fetches in-process with politeness and robots).
#
# supercorp/supergateway:uvx ships uv/uvx so `uvx mcp-server-fetch` runs
# without a second image. Verified 2026-10-10 (README: "docker run ...
# supercorp/supergateway:uvx --stdio "uvx mcp-server-fetch"").
FROM supercorp/supergateway:uvx
ENV PORT=8000
# Pre-resolve the package at build time so cold starts do not download it.
RUN uvx --from mcp-server-fetch==2026.8.18 mcp-server-fetch --help >/dev/null 2>&1 || true
COPY entrypoint.sh /entrypoint.sh
ENTRYPOINT ["/bin/sh", "/entrypoint.sh"]
