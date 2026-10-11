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
# Pinned by digest (2026-10-11): the bare `uvx` tag moved to Supergateway 4.1.0
# on 2026-09-30; the entrypoint's flags are 3.4's, the version dmai-searxng
# pins on npm and image_smoke.sh proves in CI.
FROM supercorp/supergateway:3.4.0-uvx@sha256:219f3ca136730894ec089350a3cc4c01c0a9dc50103dcb67b8fa7664b0170a22
ENV PORT=8000
RUN uvx --python 3.11 --from sec-edgar-mcp==1.1.0 sec-edgar-mcp --help >/dev/null 2>&1 || true
COPY entrypoint.sh /entrypoint.sh
ENTRYPOINT ["/bin/sh", "/entrypoint.sh"]
