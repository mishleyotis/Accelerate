# infra/evidence-engine — the research layer's self-hosted backends

Four Cloud Run services, all NEW, none touching `dmai-mcp` or any existing
service (HALT condition in the brief). Nothing here runs until the plan in
`apps/evidence-engine/docs/DEPLOY-PLAN.md` is approved; `deploy-evidence.sh`
refuses to run without `EE_DEPLOY_APPROVED=1`.

| Service | Image | Role | Exposure |
|---|---|---|---|
| `dmai-evidence` | `apps/evidence-engine/Dockerfile` | the evidence engine (FastMCP, streamable HTTP, six tools) | `--no-allow-unauthenticated`, invoker = the plugin's identity rungs; capability header `X-DMA-Path-Token` as a second factor, exactly like `dmai-mcp` |
| `dmai-searxng` | `searxng/Dockerfile` | SearXNG on `127.0.0.1:8080` inside the container + `mcp-searxng` over Supergateway on `$PORT` | reached by the engine over its JSON API through the gateway's `/searx-json` proxy path; raw MCP tools on `/mcp` as the fallback connector |
| `dmai-fetch` | `fetch/Dockerfile` | `mcp-server-fetch` over Supergateway (`supercorp/supergateway:uvx`) | raw fallback read tool |
| `dmai-edgar` | `edgar/Dockerfile` | `sec-edgar-mcp` (AGPL-3.0, run unmodified; `/` links its source) over Supergateway | raw fallback filings tool |

Secret Manager: `dmai-evidence-path-token`, `dmai-searxng-path-token`,
`dmai-fetch-path-token`, `dmai-edgar-path-token`, `dmai-searxng-secret-key`.
Each backend's Supergateway serves its MCP endpoint on a **secret path**
(`--streamableHttpPath /mcp-<token>`) so a wrong path is a 404 and the
smoke test (`smoke.sh`) proves it.

Egress: the engine and SearXNG share one static IP through a Serverless
VPC connector + Cloud NAT with a reserved address (`deploy-evidence.sh`
creates the connector and the NAT only when approved), so SearXNG's engine
health can be measured before and after (`searxng/health.sh`).

Licences (verified 2026-10-10): SearXNG AGPL-3.0 (run unmodified, source
linked), Supergateway MIT, mcp-searxng MIT, mcp-server-fetch MIT,
sec-edgar-mcp AGPL-3.0 (run unmodified, source linked).
