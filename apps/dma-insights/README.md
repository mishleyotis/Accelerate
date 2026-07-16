# DMA Insights

Zennify-internal web app that turns every completed Digital Maturity
Assessment into a queryable, AE-ready surface — and feeds a RAG layer the
Claude project queries when generating new assessments.

## Status

In active build on branch `claude/implement-dma-insights-ieLJy`. See
`~/.claude/plans/quizzical-hatching-lighthouse.md` for the canonical plan and
`docs/decisions/` for ADRs.

## Layout

```
apps/dma-insights/
├── docs/
│   ├── reference/       7 authoritative HTML docs + design-system skill
│   └── decisions/       ADRs (one per architectural fork)
├── frontend/            Vite + React 18 + TypeScript (hash routing)
├── backend/             FastAPI + SQLAlchemy 2.0 + Pydantic v2
├── workers/             Cloud Run Jobs (drive_crawler, sheet_poller, embedder, ccg_loader, …)
├── infra/               Terraform + Cloud Build + Dockerfiles
└── docker-compose.yml   Local dev (Postgres+pgvector, Redis)
```

## Quickstart

```bash
docker compose -f apps/dma-insights/docker-compose.yml up -d
```

See `CLAUDE.md` for full command reference.
