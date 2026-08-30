# The agent taxonomy

Forty-seven agents, eleven families. In this repository they live in these
folders; in the claude.ai upload zip the same files sit flat under `agents/`
because the upload validator does not read subdirectories (measured
2026-08-20, by rejection) — the family prefix in every filename carries the
taxonomy through the flattening, and this file ships in the zip as docs/AGENT-TAXONOMY.md.

```
orchestration/            surface-producer · package-vetter · page-consolidator
production/
  overview/               overview-surface-producer (router) + hero · narrative ·
                          opportunity · people · whynow · market · findings · governance
  heatmap/                heatmap-surface-producer (router) + grid · focus ·
                          evidence · valuechain · signals · freshness
  platform/               platform-surface-producer (router) + fit · conversation · roadmap
  context/                context-surface-producer (router) + risk · sentiment · timeline
  insights/               insights-surface-producer (router) + cards · landscape
  techstack/              techstack-surface-producer (router) + register · layers
enrichment/               enrichment-planner · enrichment-web-specialist ·
                          enrichment-connector-specialist · enrichment-ledger-auditor
checkers/                 finding-challenger · evidence-integrity-checker ·
                          numeric-reconciliation-checker · exclusion-boundary-auditor
qa/                       adversarial-verifier · deployed-app-auditor · qa-overseer
learning/                 rectifier · learning-grader · learning-testgen
```

Ownership — which payload sections each agent writes, and who may invoke
whom — lives in `docs/AGENTS.md` and the surface map
(`skills/dma-surface-production/05-lifecycle/surface-map.md`). Adding an
agent: `docs/AGENTS.md § Adding a new agent`.
