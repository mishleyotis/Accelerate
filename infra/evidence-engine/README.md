# infra/evidence-engine — the research layer's self-hosted backends

Four Cloud Run services, all NEW, none touching `dmai-mcp` or any existing
service (HALT condition in the brief). Nothing here runs until the plan in
`apps/evidence-engine/docs/DEPLOY-PLAN.md` is approved; `deploy-evidence.sh`
refuses to run without `EE_DEPLOY_APPROVED=1`.

| Service | Image | Role | Exposure |
|---|---|---|---|
| `dmai-evidence` | `apps/evidence-engine/Dockerfile` | the evidence engine (FastMCP, streamable HTTP, six tools) | `--no-allow-unauthenticated`, invoker = the plugin's identity rungs; capability header `X-DMA-Path-Token` as a second factor, exactly like `dmai-mcp` |
| `dmai-searxng` | `searxng/Dockerfile` | SearXNG (official image, digest-pinned; Void Linux, so Node is copied in from `node:22-bookworm-slim`) on `127.0.0.1:8080` inside the container + `mcp-searxng@2.5.1` over Supergateway 3.4.0 behind the door on `$PORT` | reached by the engine over its JSON API through the gateway's `/searx-json` proxy path; raw MCP tools on `/mcp` as the fallback connector |
| `dmai-fetch` | `fetch/Dockerfile` | `mcp-server-fetch` over Supergateway (`supercorp/supergateway:4.1.0-uvx`, digest-pinned) | raw fallback read tool |
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

## Images are proved before a release

`image_smoke.sh` builds `searxng`, `fetch` and `edgar` and probes each through its door (`image_probe.py`: healthz, wrong path 404, `tools/list` names the tools the plugin binds, and for SearXNG the engine's JSON door). CI job `evidence-images` runs it on every pull request and `deploy` waits for it. Every `FROM` is digest-pinned; raising a pin is a reviewed change that this job proves (2026-10-11: the first approved release failed building `dmai-searxng` against a floating `latest`).

## SearXNG is paced per upstream engine (2026-10-11)

Measured on the live instance: only Bing answered (0 results about the
entity); Brave and Google CSE were suspended for *too many requests*,
DuckDuckGo and Qwant on CAPTCHA, Google on *access denied*. Three causes,
three fixes:

| cause | fix |
|---|---|
| mojeek and startpage — the profile's primary engines — are `inactive` in this SearXNG release (Proof-of-Work CAPTCHA); `use_default_settings: true` then fanned every query to ~57 default engines | `searxng/settings.yml` `keep_only`: Google CSE, Bing, Brave, mwmbl, DuckDuckGo, Qwant, Wikipedia(+data), three news and four academic engines, each explicitly enabled |
| every upstream engine saw the whole query stream from Cloud Run's shared egress | the evidence engine's `search.EnginePool` sends each query only to engines with budget left (Google CSE 0.2/s, Bing 0.5/s, mwmbl 0.4/s, Brave 0.15/s, …, per instance; `EE_SEARXNG_ENGINES` overrides) and rests an engine SearXNG reports blocked for the cool-off its reason earns; with no engine free the query skips SearXNG instead of waiting. A named engine list is sent WITHOUT `categories` — SearXNG queries the union of the two |
| `useragent_suffix: "dmai-evidence-engine"` labelled every request automated | removed |

Pacing ends the blocks we caused; it cannot vouch for an egress IP other
tenants share. The one general engine no CAPTCHA can block is the official
Brave Search API: store a key as Secret Manager secret
`dmai-brave-search-api-key` (an owner decision — a paid key, see
`APPROVAL.json`) and the next deploy mounts it, `searxng/entrypoint.sh`
activates `braveapi`, and the engine's pool puts it first. Watch the pacing
live in `coverage_report` → `sources_health.searxng_engines`.
