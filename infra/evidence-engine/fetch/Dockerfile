# dmai-fetch: mcp-server-fetch (MIT) over Supergateway (MIT), streamable HTTP
# on a secret path. The raw fallback read tool; the evidence engine never
# calls it (the engine fetches in-process with politeness and robots).
#
# Supergateway's uvx image ships uv/uvx so `uvx mcp-server-fetch` runs
# without a second image. Verified 2026-10-10 (README: "docker run ...
# supercorp/supergateway:uvx --stdio "uvx mcp-server-fetch"").
# Pinned by digest (2026-10-11) to 4.1.0-uvx, the same image the bare `uvx`
# tag named that day. Measured by image_diag.sh: on 3.4.0-uvx (uv 0.7.19)
# sec-edgar-mcp died importing pydantic_core; on 4.1.0-uvx (uv 0.12.15) both
# servers answer `initialize`. image_smoke.sh proves the gateway in CI.
FROM supercorp/supergateway:4.1.0-uvx@sha256:660c97d4ee58498f4654e1dc60682f4f4ccab363025c9b8b415d04b4e823025e
ENV PORT=8000
# Pre-resolve the package at build time so cold starts do not download it.
RUN uvx --from mcp-server-fetch==2026.8.18 mcp-server-fetch --help >/dev/null 2>&1 || true
COPY entrypoint.sh /entrypoint.sh
ENTRYPOINT ["/bin/sh", "/entrypoint.sh"]
