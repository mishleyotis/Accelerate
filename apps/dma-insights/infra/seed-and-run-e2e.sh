#!/usr/bin/env bash
# apps/dma-insights/infra/seed-and-run-e2e.sh
#
# Self-healing wrapper that runs the Playwright e2e suite against the
# LIVE Cloud Run backend (no localhost stubs).
#
# Operator mandate (2026-06-05):
#   "For the backend tests, can you retrieve the real backend link and
#   use it instead? These errors have been persistent. The deploy should
#   provision the proper backend and get the right link that serves
#   traffic. Ensure seeding of the Postgre environment before even the
#   e2e tests begin."
#
# Flow (each step self-heals or bails with a clear next-action):
#
#   1. Resolve LIVE backend URL via resolve-backend-url.sh
#        - exit 2: deploy-two-phase.sh hasn't run; we tell the operator
#        - exit 1: traffic split — we route to post-deploy-refresh.sh
#                   (auto-fixes with --to-latest) then retry
#
#   2. Verify DB is ready (schemas at alembic head + dma_insights user
#      authenticates). Delegate to ensure-db-ready.sh in --check-only
#      mode — if NOT ready, fall through to full heal (which is
#      idempotent on healthy state).
#
#   3. Seed Postgres with the 5 sanitized DMA fixtures via
#      `python -m app.scripts.seed_ci` running INSIDE the
#      dma-insights-migrations Cloud Run Job (the only execution
#      surface that has VPC + Cloud SQL connector + the fixture files
#      bundled). Idempotent — already-seeded packages are no-ops.
#
#   4. Run Playwright e2e with BACKEND_URL pointed at the live URL.
#
# Usage:
#   ./seed-and-run-e2e.sh                  # full chain
#   ./seed-and-run-e2e.sh --skip-seed      # if PG is already seeded
#   ./seed-and-run-e2e.sh --no-deploy-heal # don't auto-call post-deploy-refresh on traffic-split
#
# Exit codes:
#   0 → all e2e passed
#   2 → service missing (operator must run deploy-two-phase.sh)
#   3 → seed failed AFTER DB-ready chain
#   4 → e2e tests failed (errors logged to stderr; investigate)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
REGION="${REGION:-us-central1}"
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"

SKIP_SEED=false
NO_DEPLOY_HEAL=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-seed)        SKIP_SEED=true; shift ;;
    --no-deploy-heal)   NO_DEPLOY_HEAL=true; shift ;;
    -h|--help)
      sed -n '1,40p' "$0" | sed 's/^# \?//'
      exit 0 ;;
    *) echo "::error::unknown flag: $1" >&2; exit 1 ;;
  esac
done

echo ""
echo "==[ STEP 1: resolve LIVE backend URL ]==="
TMP_ENV=$(mktemp)
trap 'rm -f "$TMP_ENV"' EXIT

if ! BACKEND_URL_OUT=$("${SCRIPT_DIR}/resolve-backend-url.sh" \
                        --require-traffic --export "$TMP_ENV" 2>&1); then
  resolve_exit=$?
  echo "$BACKEND_URL_OUT" >&2
  if [[ $resolve_exit -eq 1 && "$NO_DEPLOY_HEAL" == "false" ]]; then
    # Traffic split detected — auto-heal via post-deploy-refresh.sh.
    echo ""
    echo "  → traffic not on LATEST; running post-deploy-refresh.sh to promote..."
    if "${SCRIPT_DIR}/post-deploy-refresh.sh" --skip-backfill; then
      # Re-resolve after the promotion.
      "${SCRIPT_DIR}/resolve-backend-url.sh" --require-traffic --export "$TMP_ENV"
    else
      echo "::error::post-deploy-refresh.sh failed; cannot guarantee LATEST traffic" >&2
      exit $resolve_exit
    fi
  else
    exit $resolve_exit
  fi
fi

# Source the BACKEND_URL=... line.
set -a
source "$TMP_ENV"
set +a
echo "  ✓ BACKEND_URL=$BACKEND_URL"

echo ""
echo "==[ STEP 2: verify DB is ready (schemas + user) ]==="
if [[ -x "$SCRIPT_DIR/ensure-db-ready.sh" ]]; then
  if ! "$SCRIPT_DIR/ensure-db-ready.sh" --check-only 2>&1; then
    echo "  ⚠ check-only reports drift; running full heal (idempotent on healthy DB)..."
    if ! "$SCRIPT_DIR/ensure-db-ready.sh"; then
      echo "::error::ensure-db-ready.sh full heal failed" >&2
      exit 3
    fi
  fi
else
  echo "  ⚠ ensure-db-ready.sh not found; proceeding without DB check"
fi

echo ""
echo "==[ STEP 3: seed Postgres with sanitized DMA fixtures ]==="
if $SKIP_SEED; then
  echo "  → --skip-seed: skipping seed_ci"
else
  # The migrations Cloud Run Job is the right execution surface — it
  # already has DATABASE_URL_SYNC, VPC connector, Cloud SQL volume mount,
  # AND the fixture files bundled in /home/app/tests/fixtures/
  # (per Dockerfile.backend). Override the entrypoint args to run
  # seed_ci instead of alembic upgrade head.
  #
  # We use --update-env-vars to set DMA_RUN_SEED_CI=1; post_migrate.py
  # honours that flag and invokes `python -m app.scripts.seed_ci` after
  # the grant chain. Idempotent: re-running is a no-op.
  if gcloud run jobs describe dma-insights-migrations --region="$REGION" \
       --project="$PROJECT_ID" --format='value(name)' >/dev/null 2>&1; then
    echo "  → invoking dma-insights-migrations with DMA_RUN_SEED_CI=1..."
    if gcloud run jobs execute dma-insights-migrations --region="$REGION" \
         --project="$PROJECT_ID" \
         --update-env-vars="DMA_RUN_SEED_CI=1" \
         --wait >/tmp/seed-ci.log 2>&1; then
      n_seeded=$(grep -oE 'seeded [0-9]+ fixtures' /tmp/seed-ci.log | tail -1 || true)
      echo "  ✓ seed complete (${n_seeded:-result in /tmp/seed-ci.log})"
    else
      echo "::error::seed_ci execution failed (see /tmp/seed-ci.log)" >&2
      tail -20 /tmp/seed-ci.log >&2
      exit 3
    fi
  else
    echo "::error::dma-insights-migrations job missing — run deploy-two-phase.sh first" >&2
    exit 3
  fi
fi

echo ""
echo "==[ STEP 4: run Playwright e2e against \$BACKEND_URL ]==="
cd "$REPO_ROOT/apps/dma-insights/frontend"
if [[ ! -d node_modules ]]; then
  echo "  → installing dependencies (pnpm install --frozen-lockfile)..."
  pnpm install --frozen-lockfile
fi
if [[ ! -d /root/.cache/ms-playwright/chromium-* ]] 2>/dev/null; then
  echo "  → installing Playwright browser (chromium)..."
  pnpm exec playwright install --with-deps chromium
fi

# Honour BACKEND_URL we resolved above. Playwright reads process.env
# via the helpers in e2e/helpers.ts.
echo "  → BACKEND_URL=$BACKEND_URL"
echo "  → CI=1 pnpm exec playwright test --config playwright.config.ts"
if CI=1 BACKEND_URL="$BACKEND_URL" \
     pnpm exec playwright test --config playwright.config.ts \
     --reporter=line; then
  echo ""
  echo "✓ e2e suite PASSED against $BACKEND_URL"
  exit 0
else
  echo "" >&2
  echo "::error::e2e suite FAILED. Inspect via:" >&2
  echo "         CI=1 BACKEND_URL=$BACKEND_URL \\" >&2
  echo "           pnpm exec playwright test --config playwright.config.ts --ui" >&2
  exit 4
fi
