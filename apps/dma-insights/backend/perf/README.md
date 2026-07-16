# DMA Insights — Performance Scripts

Carryover finding F12 — closes the "no load test" gap surfaced by the
behavioral QA review. Three k6 scripts cover the critical paths
identified in QA-16R:

| Script | Target | SLO |
|---|---|---|
| `k6-dashboard.js` | `GET /api/v1/dashboard` | p95 < 800 ms @ 50 VUs × 30 s |
| `k6-heatmap.js` | `GET /api/v1/entities/{id}/heatmap?zoom=subcap` | p95 < 500 ms @ 20 VUs × 60 s |
| `k6-rag-answer.js` | `POST /api/v1/rag/answer` (offline / mocked Vertex) | p95 < 3000 ms @ 5 VUs × 60 s |

Each script also asserts a sustained error rate < 1 %. A regression
that pushes any SLO past its limit fails the test, NOT a warning.

## Prerequisites

```bash
# Install k6 once (Linux):
sudo apt-get install -y k6
# or via brew on macOS:
# brew install k6

# Spin up backend + Postgres with seeded data:
docker compose -f apps/dma-insights/docker-compose.yml up -d
cd apps/dma-insights/backend
alembic upgrade head
DATABASE_URL=postgresql+asyncpg://... python -m app.scripts.seed_ci

# Run a perf check:
ENV=local \
DATABASE_URL_SYNC=postgresql+psycopg://... \
DATABASE_URL=postgresql+asyncpg://... \
DMA_BOT_API_KEY=ci-bot-key \
  uvicorn app.main:app --host 127.0.0.1 --port 8000 &

# Mint a session cookie that k6 will reuse:
curl -c /tmp/cookies.txt -X POST \
  "http://127.0.0.1:8000/api/v1/auth/dev-login?email=ae.test@zennify.com"

# Run the script:
k6 run --vus=50 --duration=30s perf/k6-dashboard.js
```

## CI integration (future)

Wire these as a Cloud Build advisory stage that reports p95 in the
build summary. NOT release-blocking until baselines are established
across 3 consecutive green deploys.

## Operator runbook on SLO breach

A p95 breach is operator-actionable; the typical root causes are:

| Symptom | Likely cause | First-line fix |
|---|---|---|
| `/dashboard` p95 > 800 ms | Cross-entity JOIN with no LIMIT | Inspect `routers/entities.py` list endpoint plan; add index on `entity_assignments.user_id` |
| `/heatmap` p95 > 500 ms | Missing index on `subcap_scores(run_id, subcap_id)` | `CREATE INDEX … ; ANALYZE;` |
| `/rag/answer` p95 > 3 s with offline Vertex | Synthesis cache warming serially | Check `synthesis_orchestrator` cache hit rate via `/admin/vertex-budget` |
