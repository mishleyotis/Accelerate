#!/usr/bin/env bash
# apps/dma-insights/infra/simulate-all-deploy-stages.sh
#
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  END-TO-END DEPLOYMENT-STAGE SIMULATION HARNESS                      ║
# ║                                                                      ║
# ║  Walks every distinct stage of the dma-insights deployment pipeline ║
# ║  in order, records PASS/FAIL/SKIP per stage, NEVER bails on first    ║
# ║  failure, exits non-zero iff any stage failed. Designed so an        ║
# ║  operator (or this script as a CI pre-deploy gate) can see the FULL  ║
# ║  status of every stage in ONE run -- not "stop at first error and    ║
# ║  guess what's next."                                                 ║
# ║                                                                      ║
# ║  Stages map 1:1 to the pipeline:                                     ║
# ║    Stage 1-5    : structural (bash syntax, preflight, alembic,       ║
# ║                   post_migrate, seed_ci idempotency)                 ║
# ║    Stage 6-11   : runtime (uvicorn boot, healthz/readyz, route audit,║
# ║                   13 prod endpoints, 7 entity endpoints, full pytest)║
# ║    Stage 12-16  : quality gates (ruff, tsc, vitest, vite, standalone)║
# ║    Stage 17-21  : contract guards + DMA real-sample audit            ║
# ║                   (terraform↔script names, image-pin, exit-code      ║
# ║                   uniqueness, region substitution, parser fixture    ║
# ║                   roundtrip, DMA --parse-only local audit)           ║
# ║    Stage 22-24  : deploy-gate simulations (master plan Part 14):     ║
# ║                   pack-freshness check-6 logic vs a deliberately-    ║
# ║                   stale manifest (must FAIL; _ALLOW_STALE_PACK must  ║
# ║                   downgrade); qa_gemini_surfaces cold gate vs the    ║
# ║                   _ALLOW_COLD_GEMINI escape hatch; qa_pack_parity    ║
# ║                   report vs the committed pack (wiring check)        ║
# ║                                                                      ║
# ║  Output format per stage:                                            ║
# ║    [ N/24] stage-name                  PASS|FAIL|SKIP  evidence      ║
# ║                                                                      ║
# ║  Final tally:                                                        ║
# ║    22/24 PASS · 1/24 FAIL · 1/24 SKIP                                ║
# ║    Failed stages: <list>                                             ║
# ║                                                                      ║
# ║  Usage:                                                              ║
# ║    bash infra/simulate-all-deploy-stages.sh                          ║
# ║    bash infra/simulate-all-deploy-stages.sh --stages 1,5,7,11        ║
# ║    bash infra/simulate-all-deploy-stages.sh --quiet                  ║
# ║                                                                      ║
# ║  Env-var contract (read but never required):                         ║
# ║    DATABASE_URL, DATABASE_URL_SYNC, SEED_CI_PG_URL,                  ║
# ║    WRITE_SURFACES_PG_URL, REDIS_URL --- inherited from caller's      ║
# ║    shell. When any required env is missing for a stage, that stage   ║
# ║    SKIPs and the harness continues.                                  ║
# ╚══════════════════════════════════════════════════════════════════════╝

# Do NOT `set -e` -- the whole point is to keep going on stage failures.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$APP_DIR/backend"
# Python resolution (2026-06-10 self-heal): prefer the backend venv —
# a bare `python` on a fresh shell lacks psycopg/alembic and fails
# stages 3-10 with ModuleNotFoundError even though the code is fine.
# Falls back to PATH python (CI images install deps globally).
if [[ -x "$BACKEND_DIR/.venv/bin/python" ]]; then
  PY="$BACKEND_DIR/.venv/bin/python"
else
  PY="python"
fi
FRONTEND_DIR="$APP_DIR/frontend"
WORKERS_DIR="$APP_DIR/workers"

# ── Flags ───────────────────────────────────────────────────────────────────
QUIET=0
ONLY_STAGES=""
for arg in "$@"; do
  case "$arg" in
    --quiet) QUIET=1 ;;
    --stages=*) ONLY_STAGES="${arg#--stages=}" ;;
    --stages) shift; ONLY_STAGES="${1:-}" ;;
    --help|-h)
      sed -n '1,40p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
  esac
done

# ── Stage runner ────────────────────────────────────────────────────────────
# 2026-06-06 QA-8: TOTAL_STAGES used to say 20 even though stage 21
# (dma-real-sample-audit) is defined and recorded below. The mismatched
# header was operator-confusing -- with --stages 21 the summary said
# "Total 1/20 PASS" implying 19 silent SKIPs that never ran.
# 2026-07-02: 21 → 24 (stage 22 pack-freshness-gate-sim + stage 23
# gemini-cold-gate-sim + stage 24 pack-parity-report; master plan
# Part 14 deploy gates).
TOTAL_STAGES=24
PASS=0
FAIL=0
SKIP=0
FAILED_STAGES=()
SKIPPED_STAGES=()
STAGE_LOG_DIR="$(mktemp -d)"
trap 'rm -rf "$STAGE_LOG_DIR"' EXIT

_in_only_stages() {
  # Return 0 iff $1 is in ONLY_STAGES (comma-separated list) -- or
  # ONLY_STAGES is empty (run everything).
  [[ -z "$ONLY_STAGES" ]] && return 0
  local needle=",$1,"
  [[ ",$ONLY_STAGES," == *"$needle"* ]] && return 0
  return 1
}

_record() {
  # _record N name PASS|FAIL|SKIP "evidence"
  local n="$1" name="$2" status="$3" evidence="${4:-}"
  printf "[%2d/%2d] %-40s %s  %s\n" "$n" "$TOTAL_STAGES" "$name" "$status" "$evidence"
  case "$status" in
    PASS) PASS=$((PASS+1)) ;;
    FAIL) FAIL=$((FAIL+1)); FAILED_STAGES+=("$name") ;;
    SKIP) SKIP=$((SKIP+1)); SKIPPED_STAGES+=("$name") ;;
  esac
}

_skip_unless() {
  # _skip_unless N name "reason" condition_command...
  # Returns 0 if condition true (proceed). Records SKIP + returns 1 otherwise.
  local n="$1" name="$2" reason="$3"; shift 3
  if "$@" >/dev/null 2>&1; then
    return 0
  fi
  _record "$n" "$name" "SKIP" "$reason"
  return 1
}

echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║  DMA Insights — Deployment Stage Simulation                          ║"
printf "║  Run started: %-55s║\n" "$(date -u +%FT%TZ)"
echo "╠══════════════════════════════════════════════════════════════════════╣"

# ════════════════════════════════════════════════════════════════════════════
# Stage 1: bash syntax across all infra scripts
# ════════════════════════════════════════════════════════════════════════════
if _in_only_stages 1; then
  fail=0
  for f in "$SCRIPT_DIR"/*.sh; do
    if ! bash -n "$f" 2>/dev/null; then
      fail=$((fail+1))
    fi
  done
  if [[ "$fail" -eq 0 ]]; then
    n_scripts=$(ls "$SCRIPT_DIR"/*.sh | wc -l)
    _record 1 "infra-scripts-syntax" "PASS" "$n_scripts scripts clean"
  else
    _record 1 "infra-scripts-syntax" "FAIL" "$fail script(s) failed bash -n"
  fi
fi

# ════════════════════════════════════════════════════════════════════════════
# Stage 2: preflight-parameters with shape-valid fixtures
# ════════════════════════════════════════════════════════════════════════════
if _in_only_stages 2; then
  out=$(PROJECT_ID=zennify-sim-test \
    REGION=us-central1 \
    GOOGLE_OAUTH_CLIENT_ID=1234567890-abc.apps.googleusercontent.com \
    GOOGLE_OAUTH_CLIENT_SECRET=GOCSPX-stub \
    DMA_BOT_API_KEY=stub-bot \
    RAG_API_BEARER_KEY=stub-rag \
    REDIS_URL=redis://localhost:6379/0 \
    DMA_CLAY_DEFERRED=1 \
    bash "$SCRIPT_DIR/preflight-parameters.sh" 2>&1)
  if echo "$out" | grep -q "Pre-deployment validation passed"; then
    _record 2 "preflight-parameters" "PASS" "validation passed"
  else
    _record 2 "preflight-parameters" "FAIL" "$(echo "$out" | tail -3 | tr '\n' '|')"
  fi
fi

# ════════════════════════════════════════════════════════════════════════════
# Stage 3: alembic head + round-trip (requires DATABASE_URL_SYNC)
# ════════════════════════════════════════════════════════════════════════════
if _in_only_stages 3; then
  if _skip_unless 3 "alembic-roundtrip" "DATABASE_URL_SYNC not set" \
       test -n "${DATABASE_URL_SYNC:-}"; then
    cd "$BACKEND_DIR"
    # Via "$PY" -m: the bare `alembic` binary is absent on a fresh
    # shell (it lives in backend/.venv/bin) — stage 3 then failed with
    # "could not read head" AND left the sim DB un-migrated, cascading
    # FAILs into stages 4/5/10 (2026-06-10 end-to-end run).
    head=$("$PY" -m alembic heads 2>/dev/null | tail -1 | awk '{print $1}')
    cur=$("$PY" -m alembic current 2>/dev/null | tail -1 | awk '{print $1}')
    if [[ -z "$head" ]]; then
      _record 3 "alembic-roundtrip" "FAIL" "could not read head"
    elif [[ -z "$cur" || "$head" != "$cur" ]]; then
      # Need to upgrade first to be at head.
      if "$PY" -m alembic upgrade head >/dev/null 2>&1; then
        cur=$("$PY" -m alembic current 2>/dev/null | tail -1 | awk '{print $1}')
      fi
    fi
    # Now exercise the round-trip: downgrade -1, then upgrade head.
    down=$("$PY" -m alembic downgrade -1 2>&1 | grep -c "Running downgrade")
    up=$("$PY" -m alembic upgrade head 2>&1 | grep -c "Running upgrade")
    if [[ "$down" -ge 1 && "$up" -ge 1 ]]; then
      _record 3 "alembic-roundtrip" "PASS" "head=$head down=$down up=$up"
    else
      _record 3 "alembic-roundtrip" "FAIL" "down=$down up=$up (expected ≥1 each)"
    fi
  fi
fi

# ════════════════════════════════════════════════════════════════════════════
# Stage 4: post_migrate grant chain + alembic_version privilege verification
# ════════════════════════════════════════════════════════════════════════════
if _in_only_stages 4; then
  if _skip_unless 4 "post-migrate-grants" "DATABASE_URL_SYNC not set" \
       test -n "${DATABASE_URL_SYNC:-}"; then
    cd "$BACKEND_DIR"
    # Provision the app role exactly as production does (terraform
    # null_resource.db_app_user_setup) and as cloudbuild's migration CI
    # does (CREATE ROLE dma_insights LOGIN … NOSUPERUSER) — without it
    # this stage and the two post_migrate grant tests in stage 10 fail
    # on a fresh local PG for an environment reason, not a code one.
    "$PY" - <<'PYEOF'
import os
import sqlalchemy as sa
eng = sa.create_engine(os.environ["DATABASE_URL_SYNC"])
with eng.begin() as cx:
    cx.execute(sa.text("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dma_insights') THEN
                CREATE ROLE dma_insights LOGIN PASSWORD 'dma_ci_password' NOSUPERUSER;
            END IF;
        END $$;
    """))
print("app role dma_insights present")
PYEOF
    out=$("$PY" -m app.scripts.post_migrate 2>&1)
    if echo "$out" | grep -q "has_table_privilege(dma_insights, alembic_version, SELECT) = True"; then
      n=$(echo "$out" | grep -c "exec:")
      _record 4 "post-migrate-grants" "PASS" "$n grants + alembic_version=SELECT=True"
    else
      _record 4 "post-migrate-grants" "FAIL" "$(echo "$out" | tail -3 | tr '\n' '|')"
    fi
  fi
fi

# ════════════════════════════════════════════════════════════════════════════
# Stage 5: seed_ci idempotency (run twice; second must skip=N where
# N = FIXTURE_NAMES count). 2026-06-07 Batch 10: derive N from
# FIXTURE_NAMES instead of hardcoding 5; Batch 6 added richbank as the
# 6th fixture so the prior `skip=5 fail=0` assertion silently failed.
# Future fixture additions are now picked up automatically.
# ════════════════════════════════════════════════════════════════════════════
if _in_only_stages 5; then
  if _skip_unless 5 "seed-ci-idempotency" "DATABASE_URL not set" \
       test -n "${DATABASE_URL:-}"; then
    cd "$BACKEND_DIR"
    expected_n=$("$PY" -c "from app.scripts.seed_ci import FIXTURE_NAMES; print(len(FIXTURE_NAMES))" 2>/dev/null || echo 5)
    # First pass establishes state (may report new=N where N>0); second
    # pass must be a pure no-op (skip=N/N where N=fixtures).
    "$PY" -m app.scripts.seed_ci >/dev/null 2>&1
    second=$("$PY" -m app.scripts.seed_ci 2>&1 | tail -1)
    if echo "$second" | grep -q "skip=$expected_n fail=0"; then
      _record 5 "seed-ci-idempotency" "PASS" "$second"
    else
      _record 5 "seed-ci-idempotency" "FAIL" "$second (expected skip=$expected_n)"
    fi
  fi
fi

# ════════════════════════════════════════════════════════════════════════════
# Stage 6: uvicorn boot + /healthz + /readyz + route_composition_audit
# ════════════════════════════════════════════════════════════════════════════
if _in_only_stages 6 || _in_only_stages 7 || _in_only_stages 8 \
   || _in_only_stages 9 || _in_only_stages 10; then
  if _skip_unless 6 "uvicorn-boot" "DATABASE_URL not set" \
       test -n "${DATABASE_URL:-}"; then
    cd "$BACKEND_DIR"
    UVI_PORT=8801
    UVI_LOG="$STAGE_LOG_DIR/uvicorn.log"
    GOOGLE_OAUTH_CLIENT_ID="${GOOGLE_OAUTH_CLIENT_ID:-stub.apps.googleusercontent.com}" \
    GOOGLE_OAUTH_CLIENT_SECRET="${GOOGLE_OAUTH_CLIENT_SECRET:-stub}" \
    DMA_BOT_API_KEY="${DMA_BOT_API_KEY:-stub}" \
    RAG_API_BEARER_KEY="${RAG_API_BEARER_KEY:-stub}" \
    REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}" \
    ALLOWED_ORIGINS="${ALLOWED_ORIGINS:-*}" \
    DMA_CLAY_DEFERRED="${DMA_CLAY_DEFERRED:-1}" \
    DRIVE_ROOT_FOLDER_ID="${DRIVE_ROOT_FOLDER_ID:-stub}" \
    OPS_SHEET_ID="${OPS_SHEET_ID:-stub}" \
    VERTEX_PROJECT_ID="${VERTEX_PROJECT_ID:-stub}" \
      "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$UVI_PORT" \
        --log-level warning > "$UVI_LOG" 2>&1 &
    UVI_PID=$!
    # Poll for readyz becoming reachable.
    UVI_READY=0
    for _ in $(seq 1 30); do
      sleep 1
      if curl -sS -o /dev/null --max-time 2 "http://127.0.0.1:$UVI_PORT/healthz" 2>/dev/null; then
        UVI_READY=1
        break
      fi
    done
    if [[ "$UVI_READY" -eq 0 ]]; then
      _record 6 "uvicorn-boot" "FAIL" "never reachable on :$UVI_PORT (see $UVI_LOG)"
      kill "$UVI_PID" 2>/dev/null
    else
      hz=$(curl -sS -o /dev/null -w "%{http_code}" "http://127.0.0.1:$UVI_PORT/healthz")
      rz=$(curl -sS -o /dev/null -w "%{http_code}" "http://127.0.0.1:$UVI_PORT/readyz")
      audit=$(grep "route_composition_audit" "$UVI_LOG" | head -1 | grep -oE "scanned=[0-9]+" || echo "scanned=?")
      if [[ "$hz" == "200" && "$rz" == "200" ]]; then
        _record 6 "uvicorn-boot" "PASS" "healthz=200 readyz=200 $audit"
      else
        _record 6 "uvicorn-boot" "FAIL" "healthz=$hz readyz=$rz"
      fi
      # Keep UVI_PID alive for stages 7-10 below.
    fi
  fi
fi

# ════════════════════════════════════════════════════════════════════════════
# Stage 7: route_composition_audit clean (sub-assertion of Stage 6 log)
# ════════════════════════════════════════════════════════════════════════════
if _in_only_stages 7; then
  if [[ -f "${UVI_LOG:-}" ]]; then
    if grep -q "route_composition_audit.clean" "$UVI_LOG"; then
      _record 7 "route-composition-audit" "PASS" "zero offenders at startup"
    else
      offenders=$(grep "route_composition_audit.unsafe_default" "$UVI_LOG" | wc -l)
      _record 7 "route-composition-audit" "FAIL" "$offenders unsafe-default offender(s)"
    fi
  else
    _record 7 "route-composition-audit" "SKIP" "uvicorn-boot stage didn't run"
  fi
fi

# ════════════════════════════════════════════════════════════════════════════
# Stage 8: 13 production endpoints with admin JWT
# ════════════════════════════════════════════════════════════════════════════
if _in_only_stages 8; then
  if [[ -n "${UVI_PORT:-}" && -n "${UVI_PID:-}" ]] \
     && kill -0 "$UVI_PID" 2>/dev/null; then
    # Session-auth uses the cookie (Bearer is bot/RAG-key only); the
    # admin email must be in admin_emails (chris.conant by default).
    SIM_COOKIES="$STAGE_LOG_DIR/cookies.txt"
    curl -sS -X POST -c "$SIM_COOKIES" -o /dev/null \
      "http://127.0.0.1:$UVI_PORT/api/v1/auth/dev-login?email=${SIM_ADMIN_EMAIL:-chris.conant@zennify.com}"
    H="X-Sim-Auth: cookie"
    okc=0; failc=0; details=""
    for url in \
      /api/v1/dashboard /api/v1/entities /api/v1/alerts /api/v1/prospecting \
      /api/v1/admin/jobs/executions /api/v1/admin/vertex-budget \
      /api/v1/admin/import-audit/summary /api/v1/admin/users \
      /api/v1/admin/build-qa /api/v1/admin/catalogue /api/v1/admin/assignments \
      /api/v1/admin/pending-review /api/v1/archetypes; do
      c=$(curl -sS -o /dev/null -w "%{http_code}" -b "${SIM_COOKIES:-/dev/null}" \
            "http://127.0.0.1:$UVI_PORT$url")
      if [[ "$c" == "200" ]]; then
        okc=$((okc+1))
      else
        failc=$((failc+1))
        details="$details $url=$c"
      fi
    done
    if [[ "$failc" -eq 0 ]]; then
      _record 8 "endpoints-prod-13" "PASS" "$okc/13 ok"
    else
      _record 8 "endpoints-prod-13" "FAIL" "$failc fail:$details"
    fi
  else
    _record 8 "endpoints-prod-13" "SKIP" "uvicorn not running"
  fi
fi

# ════════════════════════════════════════════════════════════════════════════
# Stage 9: 7 entity endpoints + heatmap/subcap (Query-sentinel reproducer)
# ════════════════════════════════════════════════════════════════════════════
if _in_only_stages 9; then
  if [[ -n "${UVI_PORT:-}" && -n "${UVI_PID:-}" ]] \
     && kill -0 "$UVI_PID" 2>/dev/null; then
    TOK="${TOK:-$("$PY" -c "
import uuid
from app.services.jwt_service import issue_token
print(issue_token(user_id=str(uuid.UUID(int=1)), email='admin@zennify.com', role='ADMIN', name='Admin'))
" 2>/dev/null)}"
    H="Authorization: Bearer $TOK"
    # 2026-06-07 Batch 10: hardcoded `americu-credit-union-syn-0001`
    # only exists when the DB was just seed_ci-seeded with synthetic
    # fixtures. The full-corpus DB (104+ entities from
    # tests/fixtures/dma_packages_batches) has the real display_id
    # `americu-credit-union-0001` without the `-syn-` token. Pick the
    # MOST-RECENT run row at query time so this stage works regardless
    # of the DB's seed state. Fallback hardcoded value used only when
    # the live query returns nothing.
    pair=$("$PY" -c "
import os
from sqlalchemy import create_engine, text
url = os.environ.get('DATABASE_URL_SYNC') or os.environ.get('DATABASE_URL', '').replace('+asyncpg', '+psycopg2')
try:
    eng = create_engine(url)
    with eng.connect() as conn:
        row = conn.execute(text(
            'SELECT e.display_id, r.request_id '
            'FROM runs r JOIN entities e ON e.id = r.entity_id '
            'WHERE r.status = :s AND r.completed_at IS NOT NULL '
            'ORDER BY r.completed_at DESC NULLS LAST LIMIT 1'
        ), {'s': 'ACTIVE'}).first()
    if row:
        print(f'{row[0]}|{row[1]}')
except Exception:
    pass
" 2>/dev/null)
    if [[ -n "$pair" && "$pair" == *"|"* ]]; then
      EID="${pair%%|*}"
      RID="${pair##*|}"
    else
      EID="americu-credit-union-syn-0001"
      RID="DMA-RES-AMERICU-20260427-0001"
    fi
    okc=0; failc=0; details=""
    for path in heatmap overview insights platforms platforms/roadmap \
                context health heatmap/subcap/P1C1.1.1; do
      c=$(curl -sS -o /dev/null -w "%{http_code}" -b "${SIM_COOKIES:-/dev/null}" \
            "http://127.0.0.1:$UVI_PORT/api/v1/entities/$EID/$path?run=$RID")
      if [[ "$c" == "200" ]]; then
        okc=$((okc+1))
      else
        failc=$((failc+1))
        details="$details $path=$c"
      fi
    done
    if [[ "$failc" -eq 0 ]]; then
      _record 9 "endpoints-entity-8" "PASS" "$okc/8 ok (Query-sentinel extinct)"
    else
      _record 9 "endpoints-entity-8" "FAIL" "$failc fail:$details"
    fi
  else
    _record 9 "endpoints-entity-8" "SKIP" "uvicorn not running"
  fi
fi

# Tear down uvicorn now that endpoint stages are done.
if [[ -n "${UVI_PID:-}" ]] && kill -0 "$UVI_PID" 2>/dev/null; then
  kill "$UVI_PID" 2>/dev/null
  wait "$UVI_PID" 2>/dev/null || true
fi

# ════════════════════════════════════════════════════════════════════════════
# Stage 10: full backend pytest sweep
# ════════════════════════════════════════════════════════════════════════════
if _in_only_stages 10; then
  cd "$BACKEND_DIR"
  if _skip_unless 10 "backend-pytest" "DATABASE_URL not set" \
       test -n "${DATABASE_URL:-}"; then
    PYTEST_LOG="$STAGE_LOG_DIR/pytest.log"
    # Mirror the cloudbuild backend-tests-live-pg contract EXACTLY
    # (infra/cloudbuild.yaml): this stage runs against the seed_ci
    # 6-fixture DB, so the corpus-gated suites (adversarial, reingest,
    # skip-path integration incl. the 95-entity strict-gate contract)
    # are ignored here — they run in qa-gates against the FULL
    # historical_backfill corpus. Raw `pytest tests/` made stage 10
    # fail with 29 by-design corpus failures (2026-06-10 e2e run).
    if "$PY" -m pytest tests/ \
        --ignore=tests/test_qa_v2_adversarial_resilience.py \
        --ignore=tests/test_qa_v2_reingest_scenarios.py \
        --ignore=tests/test_backfill_skip_path_integration.py \
        --deselect tests/test_persona_e2e.py::TestVisualBaselines \
        --deselect tests/test_seed_ci.py::test_force_regen_rebuilds_fixtures \
        --deselect tests/test_language_rewrite.py::test_rewriter_reduces_violation_count_on_real_corpus_sample \
        --deselect tests/test_catalogue_alias_bridge.py::test_get_category_children_against_live_v70_catalogue \
        --deselect tests/test_catalogue_alias_bridge.py::test_no_silent_dropping_of_data_in_broadcast_path \
        -q --no-header --tb=no > "$PYTEST_LOG" 2>&1; then
      summary=$(tail -1 "$PYTEST_LOG")
      _record 10 "backend-pytest" "PASS" "$summary"
    else
      summary=$(tail -3 "$PYTEST_LOG" | tr '\n' '|')
      _record 10 "backend-pytest" "FAIL" "$summary"
    fi
  fi
fi

# ════════════════════════════════════════════════════════════════════════════
# Stage 11: backend ruff. 2026-06-07 Batch 10: prefer .venv/bin/ruff
# when present so the pinned version matches CI; falls back to system
# ruff only when no .venv exists (e.g. on a fresh clone). Also captures
# the exit code via $? rather than re-running ruff so the rule-count
# diagnostic doesn't double-execute.
# ════════════════════════════════════════════════════════════════════════════
if _in_only_stages 11; then
  cd "$BACKEND_DIR"
  if [[ -x .venv/bin/ruff ]]; then
    ruff_bin=".venv/bin/ruff"
  else
    ruff_bin="ruff"
  fi
  ruff_out=$($ruff_bin check app/ tests/ ../workers/ 2>&1)
  ruff_rc=$?
  if [[ "$ruff_rc" -eq 0 ]]; then
    _record 11 "backend-ruff" "PASS" "app/ tests/ workers/ clean ($ruff_bin)"
  else
    n=$(echo "$ruff_out" | grep -cE "^[A-Z][0-9]+")
    _record 11 "backend-ruff" "FAIL" "$n violations"
  fi
fi

# ════════════════════════════════════════════════════════════════════════════
# Stages 12-15: frontend tsc + vitest + vite + standalone
# ════════════════════════════════════════════════════════════════════════════
# 2026-06-06 QA-8: when `node_modules` is absent the entire block used
# to be silently skipped -- a `--stages 12` invocation got 0/0
# PASS/FAIL/SKIP and exited 0, falsely implying success. Now each
# requested-but-prerequisite-missing stage is recorded as SKIP with the
# explicit "node_modules missing" reason so the summary reflects what
# actually ran. The per-stage SKIP rows give the operator the exact
# fix command (`pnpm install` from the frontend dir).
if _in_only_stages 12 || _in_only_stages 13 || _in_only_stages 14 \
   || _in_only_stages 15; then
  if [[ -d "$FRONTEND_DIR/node_modules" ]]; then
    cd "$FRONTEND_DIR"

    if _in_only_stages 12; then
      if pnpm exec tsc --noEmit >/dev/null 2>&1; then
        _record 12 "frontend-tsc" "PASS" "no type errors"
      else
        _record 12 "frontend-tsc" "FAIL" "tsc reported errors"
      fi
    fi

    if _in_only_stages 13; then
      VT_LOG="$STAGE_LOG_DIR/vitest.log"
      if pnpm exec vitest run > "$VT_LOG" 2>&1; then
        summary=$(grep -E "Tests +[0-9]+ passed" "$VT_LOG" | head -1)
        _record 13 "frontend-vitest" "PASS" "${summary:-tests passed}"
      else
        _record 13 "frontend-vitest" "FAIL" "$(tail -3 "$VT_LOG" | tr '\n' '|')"
      fi
    fi

    if _in_only_stages 14; then
      if pnpm exec vite build >/dev/null 2>&1; then
        _record 14 "frontend-vite-build" "PASS" "dist/ built"
      else
        _record 14 "frontend-vite-build" "FAIL" "build failed"
      fi
    fi

    if _in_only_stages 15; then
      if pnpm run build:standalone >/dev/null 2>&1; then
        _record 15 "frontend-standalone-build" "PASS" "dist-standalone/ built"
      else
        _record 15 "frontend-standalone-build" "FAIL" "standalone build failed"
      fi
    fi
  else
    # 2026-06-06 QA-8 false-pass fix: previously, ONLY_STAGES being
    # non-empty meant SKIPs weren't recorded -- the operator who ran
    # `--stages 12` with no node_modules saw 0/0 PASS and exit 0.
    # Now we record SKIP for EACH explicitly-requested frontend stage
    # so the summary reflects what actually ran. The reason text gives
    # the exact fix.
    for n in 12 13 14 15; do
      if _in_only_stages "$n"; then
        _record "$n" "frontend-stage-$n" "SKIP" "node_modules absent (run pnpm install in $FRONTEND_DIR)"
      fi
    done
  fi
fi

# ════════════════════════════════════════════════════════════════════════════
# Stage 16: terraform↔script job-name contract (parser-based)
# ════════════════════════════════════════════════════════════════════════════
if _in_only_stages 16; then
  cd "$BACKEND_DIR"
  # All-pass, count-agnostic: a hardcoded "3 passed" broke when the
  # derived-surfaces module contract test was added (2026-06-10).
  s16=$("$PY" -m pytest tests/test_post_deploy_refresh_job_names.py \
       --no-header -q 2>&1 | tail -1)
  if echo "$s16" | grep -qE "^[0-9]+ passed" \
     && ! echo "$s16" | grep -qE "failed|error"; then
    _record 16 "tf-job-name-contract" "PASS" "$s16"
  else
    _record 16 "tf-job-name-contract" "FAIL" "contract tests failed: $s16"
  fi
fi

# ════════════════════════════════════════════════════════════════════════════
# Stage 17: migrate.sh image-pin contract
# ════════════════════════════════════════════════════════════════════════════
if _in_only_stages 17; then
  cd "$BACKEND_DIR"
  if "$PY" -m pytest tests/test_migrate_image_pin_contract.py \
       --no-header -q 2>&1 | tail -1 | grep -q "5 passed"; then
    _record 17 "migrate-image-pin-contract" "PASS" "5/5 contract tests pass"
  else
    _record 17 "migrate-image-pin-contract" "FAIL" "contract tests failed"
  fi
fi

# ════════════════════════════════════════════════════════════════════════════
# Stage 18: deploy-two-phase.sh exit-code distinctness
# ════════════════════════════════════════════════════════════════════════════
if _in_only_stages 18; then
  codes=$(grep -hE "^\s*exit [0-9]+" "$SCRIPT_DIR/deploy-two-phase.sh" \
            | awk '{print $NF}' | sort -u)
  # We require codes 1, 3, 4, 5, 6, 7 all present (each phase has its own).
  missing=""
  for needed in 1 3 4 5 6 7; do
    if ! echo "$codes" | grep -q "^$needed$"; then
      missing="$missing $needed"
    fi
  done
  if [[ -z "$missing" ]]; then
    _record 18 "deploy-two-phase-exit-codes" "PASS" "1,3,4,5,6,7 all present"
  else
    _record 18 "deploy-two-phase-exit-codes" "FAIL" "missing codes:$missing"
  fi
fi

# ════════════════════════════════════════════════════════════════════════════
# Stage 19: no hardcoded us-central1 in --region= args
# ════════════════════════════════════════════════════════════════════════════
if _in_only_stages 19; then
  # Exclude this harness file itself -- it contains the grep literal as
  # part of its own check and would self-match.
  hits=$(grep -nE -- "--region=us-central1" "$SCRIPT_DIR"/*.sh 2>/dev/null \
           | grep -v "simulate-all-deploy-stages.sh" \
           | grep -v "REGION=\"\${REGION:-us-central1}\"" \
           | grep -v "Cloud Run region pattern (e.g." \
           || true)
  if [[ -z "$hits" ]]; then
    n_sh=$(ls "$SCRIPT_DIR"/*.sh | wc -l)
    _record 19 "region-substitution" "PASS" "0 hardcodes across $n_sh scripts"
  else
    n_hit=$(echo "$hits" | wc -l)
    _record 19 "region-substitution" "FAIL" "$n_hit hardcoded --region=us-central1 lines"
  fi
fi

# ════════════════════════════════════════════════════════════════════════════
# Stage 20: parser fixture roundtrip — at least one sanitised real fixture
# parses with zero ERROR-level warnings
# ════════════════════════════════════════════════════════════════════════════
if _in_only_stages 20; then
  cd "$BACKEND_DIR"
  FIXTURE_DIR="tests/fixtures/dma_packages_sanitized"
  if [[ -d "$FIXTURE_DIR" ]]; then
    # Pick the first available fixture; parse via dma_package.parse_package.
    sample=""
    for cand in regions wsfs amalgamated americu/AmeriCU_DMA_Deliverable_2026-04-29 \
                anb/ANB_DMA_Complete_Bundle; do
      if [[ -d "$FIXTURE_DIR/$cand" ]]; then
        sample="$FIXTURE_DIR/$cand"
        break
      fi
    done
    if [[ -n "$sample" ]]; then
      out=$("$PY" -c "
import json, pathlib
from app.services.parsers.dma_package import parse_package
pkg = parse_package(pathlib.Path('$sample'))
print(json.dumps({
    'run_id': pkg.run_manifest.run_id,
    'institution': pkg.run_manifest.institution_name,
    'subcap_scores': len(pkg.subcap_scores),
    'evidence': len(pkg.evidence),
    'parser_warnings_count': len(pkg.parser_warnings),
}))
" 2>&1)
      # The probe emits warnings on stderr-style lines THEN the JSON
      # blob on its own line. Grep for the JSON line then parse it
      # in one go.
      json_line=$(echo "$out" | grep -E '^\{.*"run_id".*\}$' | head -1)
      if [[ -n "$json_line" ]]; then
        eval "$(echo "$json_line" | "$PY" -c "
import json,sys
d = json.loads(sys.stdin.read())
print(f'subc={d[\"subcap_scores\"]} ev={d[\"evidence\"]} wn={d[\"parser_warnings_count\"]}')
" 2>/dev/null)"
        _record 20 "parser-fixture-roundtrip" "PASS" \
          "$(basename "$sample"): subcaps=${subc:-?} evidence=${ev:-?} warnings=${wn:-?}"
      else
        _record 20 "parser-fixture-roundtrip" "FAIL" "$(echo "$out" | tail -2 | tr '\n' '|')"
      fi
    else
      _record 20 "parser-fixture-roundtrip" "SKIP" "no sanitised fixture present"
    fi
  else
    _record 20 "parser-fixture-roundtrip" "SKIP" "$FIXTURE_DIR not found"
  fi
fi

# ════════════════════════════════════════════════════════════════════════════
# Stage 21: DMA parse-only audit against in-repo real samples
# ────────────────────────────────────────────────────────────────────────────
# Local-filesystem analog of `historical_backfill.py --parse-only --sample N`
# — same PARSEONLY JSON shape, no Drive credentials. CI runs this on every
# build so a parser regression against the production input distribution
# fails loud before deploy. Production audit against the live Drive folder
# still uses --parse-only --sample 50 against historical_backfill.
# ════════════════════════════════════════════════════════════════════════════
if _in_only_stages 21; then
  cd "$BACKEND_DIR"
  AUDIT_DIR="tests/fixtures/dma_packages_real_samples"
  if [[ -d "$AUDIT_DIR" ]]; then
    audit_out=$("$PY" -m app.scripts.parse_audit_local \
                       --dir "$AUDIT_DIR" 2>&1) || audit_rc=$? && audit_rc=${audit_rc:-0}
    parseonly_lines=$(echo "$audit_out" | grep -c '^PARSEONLY ' || true)
    error_lines=$(echo "$audit_out" | grep -c '^PARSEONLY_ERROR ' || true)
    if [[ "$audit_rc" -eq 0 && "$parseonly_lines" -ge 1 && "$error_lines" -eq 0 ]]; then
      summary=$(echo "$audit_out" | tail -1 | tr -d '\n' | cut -c1-72)
      _record 21 "dma-real-sample-audit" "PASS" \
              "${parseonly_lines} package(s) parsed clean: ${summary}"
    else
      _record 21 "dma-real-sample-audit" "FAIL" \
              "rc=${audit_rc} parseonly=${parseonly_lines} errors=${error_lines}"
    fi
  else
    _record 21 "dma-real-sample-audit" "SKIP" "$AUDIT_DIR not present"
  fi
fi

# ════════════════════════════════════════════════════════════════════════════
# Stage 22: pack-freshness gate simulation (frontend-image-smoke check 6)
# ────────────────────────────────────────────────────────────────────────────
# Master plan Part 14: the regen stage stamps SOURCE_SHA=${_IMAGE_SHA} into
# startup-data/pages_manifest.json via export_startup_pages, and
# frontend-image-smoke check 6 asserts the manifest BAKED into the frontend
# image carries exactly the build SHA (_ALLOW_STALE_PACK=true is the only
# escape). This stage replays the EXACT extraction + comparison logic against
# three synthetic manifests: fresh (must pass), deliberately STALE (must
# fail), and stale-but-allowed (must warn-pass). It also asserts the
# committed manifest still carries a source_sha key at all (shape guard).
# ════════════════════════════════════════════════════════════════════════════
if _in_only_stages 22; then
  # Same extraction pipeline as cloudbuild's check 6 (grep -oE | cut).
  _pack_sha_of() {
    grep -oE '"source_sha": *"[^"]*"' "$1" 2>/dev/null | head -1 | cut -d'"' -f4
  }
  _pack_gate() {
    # _pack_gate <manifest> <expected-sha> <allow-stale true|false>
    # Mirrors check 6: 0 = ship, 1 = block.
    local got
    got="$(_pack_sha_of "$1")"
    [[ "$got" == "$2" ]] && return 0
    [[ "$3" == "true" ]] && return 0   # loud-warning path in the real gate
    return 1
  }
  s22_fail=""
  FRESH_MF="$STAGE_LOG_DIR/manifest-fresh.json"
  STALE_MF="$STAGE_LOG_DIR/manifest-stale.json"
  printf '{\n "gemini": "hot",\n "source_sha": "cafef00d"\n}\n' > "$FRESH_MF"
  printf '{\n "gemini": "hot",\n "source_sha": "deadbeef"\n}\n' > "$STALE_MF"
  # Branch 1: fresh manifest must PASS the gate.
  _pack_gate "$FRESH_MF" "cafef00d" "false" || s22_fail="$s22_fail fresh-pack-blocked"
  # Branch 2: deliberately-stale manifest MUST FAIL the gate.
  if _pack_gate "$STALE_MF" "cafef00d" "false"; then
    s22_fail="$s22_fail stale-pack-shipped"
  fi
  # Branch 3: stale + _ALLOW_STALE_PACK=true must pass (warn) — the ONE hatch.
  _pack_gate "$STALE_MF" "cafef00d" "true" || s22_fail="$s22_fail escape-hatch-broken"
  # Branch 4: manifest with NO source_sha key must FAIL (missing ≠ fresh).
  printf '{\n "gemini": "hot"\n}\n' > "$STAGE_LOG_DIR/manifest-missing.json"
  if _pack_gate "$STAGE_LOG_DIR/manifest-missing.json" "cafef00d" "false"; then
    s22_fail="$s22_fail missing-sha-shipped"
  fi
  # Shape guard: the COMMITTED manifest must carry source_sha (else the
  # real check 6 would always fail-open on extraction).
  COMMITTED_MF="$APP_DIR/startup-data/pages_manifest.json"
  if [[ -f "$COMMITTED_MF" ]]; then
    committed_sha="$(_pack_sha_of "$COMMITTED_MF")"
    [[ -n "$committed_sha" ]] || s22_fail="$s22_fail committed-manifest-missing-source_sha"
  else
    s22_fail="$s22_fail committed-manifest-absent"
  fi
  # Cloudbuild wiring guard: the substitution + SOURCE_SHA env + check 6
  # must all be present in cloudbuild.yaml (belt for the pytest contract).
  CB="$SCRIPT_DIR/cloudbuild.yaml"
  grep -q '_ALLOW_STALE_PACK: "false"' "$CB" || s22_fail="$s22_fail substitution-default-drifted"
  grep -q 'SOURCE_SHA=\${_IMAGE_SHA}' "$CB" || s22_fail="$s22_fail regen-SOURCE_SHA-unwired"
  grep -q 'startup-data/pages_manifest.json' "$CB" || s22_fail="$s22_fail check6-absent"
  if [[ -z "$s22_fail" ]]; then
    _record 22 "pack-freshness-gate-sim" "PASS" \
      "fresh ships · stale blocks · hatch warns · committed sha=${committed_sha:-?}"
  else
    _record 22 "pack-freshness-gate-sim" "FAIL" "broken branches:$s22_fail"
  fi
fi

# ════════════════════════════════════════════════════════════════════════════
# Stage 23: Gemini cold-pack gate vs _ALLOW_COLD_GEMINI (qa_gemini_surfaces)
# ────────────────────────────────────────────────────────────────────────────
# Master plan Part 3.3/14: `qa_gemini_surfaces --mode baked` is the HARD gate
# at the end of the cloudbuild regen stage. Locally (DMA_DISABLE_VERTEX=1 —
# a deliberately COLD bake) it must exit 1 (cold pack blocks the build), and
# the _ALLOW_COLD_GEMINI=true hatch must downgrade to exit 0 while stamping
# the manifest `"gemini": "cold"` so the coldness stays visible downstream.
# ════════════════════════════════════════════════════════════════════════════
if _in_only_stages 23; then
  if _skip_unless 23 "gemini-cold-gate-sim" "DATABASE_URL not set" \
       test -n "${DATABASE_URL:-}"; then
    cd "$BACKEND_DIR"
    s23_fail=""
    G23_MF="$STAGE_LOG_DIR/manifest-gemini.json"
    printf '{\n "source_sha": "cafef00d"\n}\n' > "$G23_MF"
    # Branch 1: cold bake WITHOUT the hatch → must exit non-zero (blocked).
    DMA_DISABLE_VERTEX=1 _ALLOW_COLD_GEMINI=false \
      "$PY" -m app.scripts.qa_gemini_surfaces --mode baked \
        --manifest "$G23_MF" > "$STAGE_LOG_DIR/gemini-cold.log" 2>&1
    rc_cold=$?
    [[ "$rc_cold" -ne 0 ]] || s23_fail="$s23_fail cold-pack-passed-hard-gate"
    # Cold run must stamp gemini:cold (visibility even when blocked).
    grep -q '"gemini": *"cold"' "$G23_MF" || s23_fail="$s23_fail cold-stamp-missing"
    # Branch 2: same cold bake WITH _ALLOW_COLD_GEMINI=true → exit 0 + stamp.
    printf '{\n "source_sha": "cafef00d"\n}\n' > "$G23_MF"
    DMA_DISABLE_VERTEX=1 _ALLOW_COLD_GEMINI=true \
      "$PY" -m app.scripts.qa_gemini_surfaces --mode baked \
        --manifest "$G23_MF" > "$STAGE_LOG_DIR/gemini-allowed.log" 2>&1
    rc_allowed=$?
    [[ "$rc_allowed" -eq 0 ]] || s23_fail="$s23_fail escape-hatch-blocked(rc=$rc_allowed)"
    grep -q '"gemini": *"cold"' "$G23_MF" || s23_fail="$s23_fail allowed-cold-stamp-missing"
    # The stamp must PRESERVE source_sha (the freshness gate reads the
    # same file after qa_gemini_surfaces rewrites it).
    grep -q '"source_sha": *"cafef00d"' "$G23_MF" || s23_fail="$s23_fail stamp-dropped-source_sha"
    if [[ -z "$s23_fail" ]]; then
      _record 23 "gemini-cold-gate-sim" "PASS" \
        "cold rc=$rc_cold blocks · hatch rc=$rc_allowed ships · gemini:cold stamped"
    else
      _record 23 "gemini-cold-gate-sim" "FAIL" "broken branches:$s23_fail"
    fi
  fi
fi

# ════════════════════════════════════════════════════════════════════════════
# Stage 24: qa_pack_parity report vs the committed pack (wiring check)
# ────────────────────────────────────────────────────────────────────────────
# The cloudbuild regen stage runs `qa_pack_parity --strict` HARD against the
# pack it JUST exported (pack==DB by construction). Locally the committed
# pack is expected to drift from a moving DB (pre-regen), so --strict would
# false-fail; this stage runs REPORT-ONLY (exit 0 unless the harness itself
# crashes / env error exit 2) to prove the gate is runnable + wired, and
# additionally asserts cloudbuild.yaml actually carries the --strict gate.
# STRICT_PACK_PARITY=1 opts into the full strict gate (post-regen, Part 13).
# ════════════════════════════════════════════════════════════════════════════
if _in_only_stages 24; then
  if _skip_unless 24 "pack-parity-report" "DATABASE_URL not set" \
       test -n "${DATABASE_URL:-}"; then
    cd "$BACKEND_DIR"
    s24_fail=""
    grep -q "qa_pack_parity" "$SCRIPT_DIR/cloudbuild.yaml" \
      || s24_fail="$s24_fail cloudbuild-parity-gate-unwired"
    PARITY_ARGS=(--clients-dir "$APP_DIR/startup-data/clients" --sample 3)
    [[ "${STRICT_PACK_PARITY:-}" == "1" ]] && PARITY_ARGS+=(--strict)
    DMA_DISABLE_VERTEX=1 "$PY" -m app.scripts.qa_pack_parity \
        "${PARITY_ARGS[@]}" > "$STAGE_LOG_DIR/pack-parity.log" 2>&1
    rc_parity=$?
    if [[ "${STRICT_PACK_PARITY:-}" == "1" ]]; then
      [[ "$rc_parity" -eq 0 ]] || s24_fail="$s24_fail strict-parity-findings(rc=$rc_parity)"
    else
      # Report-only contract: 0 = ran clean; 2 = env error; 1 shouldn't
      # happen without --strict (would mean the report-only contract broke).
      [[ "$rc_parity" -eq 0 ]] || s24_fail="$s24_fail report-mode-rc=$rc_parity"
    fi
    summary=$(grep -m1 -E "SUMMARY|surfaces|findings" "$STAGE_LOG_DIR/pack-parity.log" | cut -c1-60)
    if [[ -z "$s24_fail" ]]; then
      _record 24 "pack-parity-report" "PASS" \
        "rc=$rc_parity${STRICT_PACK_PARITY:+ (strict)} ${summary:-ran clean}"
    else
      _record 24 "pack-parity-report" "FAIL" \
        "broken:$s24_fail $(tail -2 "$STAGE_LOG_DIR/pack-parity.log" | tr '\n' '|' | cut -c1-70)"
    fi
  fi
fi

# ════════════════════════════════════════════════════════════════════════════
# Final tally
# ════════════════════════════════════════════════════════════════════════════
total_run=$((PASS + FAIL + SKIP))
echo "╠══════════════════════════════════════════════════════════════════════╣"
printf "║  Total: %2d/%2d PASS · %2d FAIL · %2d SKIP                              ║\n" \
       "$PASS" "$total_run" "$FAIL" "$SKIP"
if [[ "${#FAILED_STAGES[@]}" -gt 0 ]]; then
  echo "║  Failed:                                                             ║"
  for s in "${FAILED_STAGES[@]}"; do
    printf "║    ✗ %-64s║\n" "$s"
  done
fi
if [[ "${#SKIPPED_STAGES[@]}" -gt 0 ]]; then
  echo "║  Skipped:                                                            ║"
  for s in "${SKIPPED_STAGES[@]}"; do
    printf "║    - %-64s║\n" "$s"
  done
fi
echo "╚══════════════════════════════════════════════════════════════════════╝"

# 2026-06-06 QA-8 exit-code contract:
#   - FAIL > 0          → exit 1 (a stage genuinely failed)
#   - ONLY_STAGES set AND total_run == 0 → exit 1 (operator explicitly
#       requested stages but NONE ran -- 0/0 PASS would mislead CI
#       into believing the deploy gate was green)
#   - ONLY_STAGES set AND SKIP > 0 → exit 1 (the operator explicitly
#       requested a stage AND it was skipped for missing prerequisites;
#       silent-skip on an explicit request hides infra drift)
#   - Otherwise → exit 0 (the unrestricted full sweep tolerates SKIPs;
#       they're informational when no specific stage was demanded)
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
if [[ -n "${ONLY_STAGES:-}" ]]; then
  if [[ "$total_run" -eq 0 ]]; then
    echo "║  ✗ 0 stages ran; --stages '$ONLY_STAGES' matched no stage IDs.       ║" >&2
    exit 1
  fi
  if [[ "$SKIP" -gt 0 ]]; then
    echo "║  ✗ Explicit --stages request includes $SKIP skipped stage(s).        ║" >&2
    echo "║    SKIPs are tolerated on the unrestricted sweep but treated as a    ║" >&2
    echo "║    failure when the operator explicitly requested the stage.         ║" >&2
    exit 1
  fi
fi
exit 0
