# dmai-edgar: sec-edgar-mcp 1.1.0 (AGPL-3.0, run UNMODIFIED) over Supergateway.
#
# AGPL §13: a modified program offered over a network must offer its source
# to users. The program is not modified; the container's root page (served by
# Supergateway's health endpoint description, and the service's README)
# links https://github.com/stefanoamorelli/sec-edgar-mcp. Nothing from it is
# imported by the evidence engine, which uses edgartools (MIT) in-process.
#
# SEC fair access: SEC_EDGAR_USER_AGENT is REQUIRED by the server and set
# at deploy from an env var (company name + contact URL, never a mailbox).
# Pinned by digest (2026-10-11) to 4.1.0-uvx, the same image the bare `uvx`
# tag named that day. Measured by image_diag.sh: on 3.4.0-uvx (uv 0.7.19)
# sec-edgar-mcp died importing pydantic_core; on 4.1.0-uvx (uv 0.12.15) both
# servers answer `initialize`. image_smoke.sh proves the gateway in CI.
FROM supercorp/supergateway:4.1.0-uvx@sha256:660c97d4ee58498f4654e1dc60682f4f4ccab363025c9b8b415d04b4e823025e
ENV PORT=8000
RUN uvx --python 3.11 --from sec-edgar-mcp==1.1.0 sec-edgar-mcp --help >/dev/null 2>&1 || true
COPY entrypoint.sh /entrypoint.sh
ENTRYPOINT ["/bin/sh", "/entrypoint.sh"]
