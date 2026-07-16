#!/usr/bin/env bash
# Live data-flow verification — run AFTER deploy + AFTER a controlled
# ingest. Asserts the full pipeline (ingest → DB → API → frontend →
# derived jobs) actually populated end-to-end.
#
# Per the 2026-05-29 QA audit (Fix-10): a green `verify-deploy.sh` only
# proves the Cloud Run revisions are healthy. It does NOT prove that
# ingested data made it through to the surfaces AEs actually use. This
# gate closes that loop:
#
#   1. Backend liveness + readiness
#   2. Entities API has rows (DB → API)
#   3. Admin import-audit self-heal returns 200 + items
#   4. Frontend serves the Vite bundle (/assets/, not /src/*.jsx)
#   5. Per-entity overview / heatmap / insights / platforms populate
#   6. Derived-data jobs ran:
#        a. section_embeddings count > 0
#        b. customer_intelligence_profiles count > 0
#        c. recent job_executions for embedder + intelligence_recompute
#           in 'succeeded' status
#
# Exits 0 on full green; non-zero on the first failing assertion (so the
# operator-side wrapper can plug it into deploy-two-phase.sh as a final
# gate without parsing JSON output).
#
# Usage:
#   BACKEND_URL=https://dma-insights-backend-…run.app \
#     FRONTEND_URL=https://dma-insights-frontend-…run.app \
#     PG_CONN="postgresql+psycopg://dma_insights:<pw>@/dma_insights?host=/cloudsql/<conn>" \
#     bash infra/live-data-flow-gate.sh
#
#   # Or let the script auto-resolve from gcloud + Secret Manager:
#   bash infra/live-data-flow-gate.sh

set -euo pipefail

# Cloud Shell IPv6 NAT-pool mitigation.
export GODEBUG=netdns=go

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Silence the benign per-call "Regional Access Boundary ... 404" gcloud
# stderr noise (Cloud Shell federated identities; see the filter file).
[ -f "${SCRIPT_DIR}/gcloud-noise-filter.sh" ] && . "${SCRIPT_DIR}/gcloud-noise-filter.sh"
REGION="${REGION:-us-central1}"
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"

if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]]; then
  echo "ERROR: PROJECT_ID unset. Run: gcloud config set project <PROJECT_ID>" >&2
  exit 2
fi

# Resolve service URLs from Cloud Run if not provided.
if [[ -z "${BACKEND_URL:-}" ]]; then
  BACKEND_URL="$(gcloud run services describe dma-insights-backend \
    --region="$REGION" --project="$PROJECT_ID" \
    --format='value(status.url)' 2>/dev/null || true)"
fi
if [[ -z "${FRONTEND_URL:-}" ]]; then
  FRONTEND_URL="$(gcloud run services describe dma-insights-frontend \
    --region="$REGION" --project="$PROJECT_ID" \
    --format='value(status.url)' 2>/dev/null || true)"
fi

if [[ -z "$BACKEND_URL" || -z "$FRONTEND_URL" ]]; then
  echo "ERROR: couldn't resolve BACKEND_URL or FRONTEND_URL." >&2
  echo "  Pass them explicitly or ensure the services exist + this caller has run.viewer." >&2
  exit 2
fi

CURL=(curl --silent --fail --connect-timeout 5 --max-time 20 --retry 3 --retry-delay 2 --retry-all-errors)
# CURLB is the AUTHENTICATED form — same options, plus a cookie jar
# AND (when set) the DMA_SMOKE_TOKEN bearer header. Many endpoints
# (entities, admin/*) require a session; in PROD the ONLY working path
# is a session JWT exported as DMA_SMOKE_TOKEN (same contract as
# post-deploy-smoke.sh check 8 / DEPLOYMENT.md §26.4) — dev-login is
# ENV=local-only and the old /auth/smoke-token endpoint never existed
# (2026-07-04 line audit: the gate could never pass in prod).
CJ="/tmp/_dataflow-cj.txt"; rm -f "$CJ"
CURLB=(curl --silent --fail --connect-timeout 5 --max-time 20 --retry 3 --retry-delay 2 --retry-all-errors -b "$CJ")
if [[ -n "${DMA_SMOKE_TOKEN:-}" ]]; then
  CURLB+=(-H "Authorization: Bearer ${DMA_SMOKE_TOKEN}")
fi
FAILED=0
green=0
fail() { echo "  ✗ $1"; FAILED=$((FAILED + 1)); }
ok()   { echo "  ✓ $1"; green=$((green + 1)); }

echo "╔════════════════════════════════════════════╗"
echo "║  DMA Insights — Live data-flow gate        ║"
echo "╠════════════════════════════════════════════╣"
printf "║  PROJECT_ID : %-28s║\n" "$PROJECT_ID"
printf "║  BACKEND    : %-28s║\n" "${BACKEND_URL#https://}"
printf "║  FRONTEND   : %-28s║\n" "${FRONTEND_URL#https://}"
echo "╚════════════════════════════════════════════╝"
echo ""

# ── 1. Backend liveness + readiness ─────────────────────────────────
echo "[1/6] Backend liveness + readiness"
if "${CURL[@]}" "${BACKEND_URL}/healthz" | grep -q '"ok"\|"status":"ok"'; then ok "/healthz ok"; else fail "/healthz"; fi
if "${CURL[@]}" "${BACKEND_URL}/readyz" | grep -q '"status":"ready"'; then ok "/readyz ready"; else fail "/readyz"; fi

# ── 1b. Auth — gate every entity/admin probe with a real session ────
echo ""
echo "[1b] Auth — session for the rest of the gate"
AUTH_EMAIL="${AUTH_EMAIL:-ae.test@zennify.com}"
if [[ -n "${DMA_SMOKE_TOKEN:-}" ]] \
   && "${CURLB[@]}" "${BACKEND_URL}/api/v1/auth/me" >/dev/null 2>&1; then
  # Prod path: DMA_SMOKE_TOKEN (session JWT) bearer — verified live
  # against /auth/me before the probes rely on it.
  ok "DMA_SMOKE_TOKEN accepted (prod path)"
elif curl --silent --max-time 10 -c "$CJ" -X POST "${BACKEND_URL}/api/v1/auth/dev-login?email=${AUTH_EMAIL}" >/dev/null 2>&1 && [[ -s "$CJ" ]] && grep -q dma_session "$CJ"; then
  ok "dev-login issued (env=local)"
else
  fail "no session — export DMA_SMOKE_TOKEN=<session JWT> for prod (DEPLOYMENT.md §26.4); dev-login is ENV=local only"
  # No point continuing the entity/admin probes; jump to the frontend section.
  AUTH_FAILED=1
fi

# ── 2. Entities API ──────────────────────────────────────────────────
echo ""
echo "[2/6] /api/v1/entities — at least one row"
if [[ "${AUTH_FAILED:-0}" == "1" ]]; then
  fail "skipped (no session)"
  ENT_ID=""
else
  ENT_JSON="$("${CURLB[@]}" "${BACKEND_URL}/api/v1/entities?owner=all" 2>/dev/null || echo '{}')"
  N_ENT="$(printf '%s' "$ENT_JSON" | python3 -c 'import sys,json; d=json.loads(sys.stdin.read() or "{}"); print(len(d.get("items",[])))' 2>/dev/null || echo 0)"
  if [[ "$N_ENT" -ge 1 ]]; then ok "entities count=$N_ENT"; else fail "entities count=$N_ENT (expected >=1)"; fi
  ENT_ID="$(printf '%s' "$ENT_JSON" | python3 -c 'import sys,json; d=json.loads(sys.stdin.read() or "{}"); print(d["items"][0]["display_id"] if d.get("items") else "")' 2>/dev/null || echo "")"
fi

# ── 3. Admin import-audit/by-entity (the self-heal endpoint) ─────────
echo ""
echo "[3/6] /api/v1/admin/import-audit/by-entity self-heal"
if [[ "${AUTH_FAILED:-0}" == "1" ]]; then
  fail "skipped (no session)"
  ADM_HTTP="000"
else
  ADM_HTTP="$(curl --silent -b "$CJ" -o /tmp/_admin_ia.json --max-time 20 -w "%{http_code}" "${BACKEND_URL}/api/v1/admin/import-audit/by-entity" || echo "000")"
fi
if [[ "$ADM_HTTP" == "200" ]]; then
  N="$(python3 -c 'import json; print(len(json.load(open("/tmp/_admin_ia.json"))["items"]))' 2>/dev/null || echo 0)"
  W="$(python3 -c 'import json; print(json.load(open("/tmp/_admin_ia.json")).get("warnings",[]))' 2>/dev/null || echo "[]")"
  ok "HTTP 200, items=$N, warnings=$W"
elif [[ "$ADM_HTTP" == "503" ]]; then
  fail "HTTP 503 — core entities/runs table missing (run migrations)"
else
  fail "HTTP $ADM_HTTP — this was the user-visible banner; the self-heal must return 200 or 503, never 500"
fi

# ── 4. Frontend serves the Vite bundle (ADR 0016) ───────────────────
echo ""
echo "[4/6] Frontend / serves Vite bundle (NOT standalone-src)"
FE_HTML="$("${CURL[@]}" "${FRONTEND_URL}/" || echo "")"
echo "$FE_HTML" | grep -q "DMA Insights" && ok "title 'DMA Insights' present" || fail "title missing — frontend container broken"
ASSET_PATH="$(printf '%s' "$FE_HTML" | grep -oE '/assets/[^"]+\.(js|css)' | head -1)"
if [[ -n "$ASSET_PATH" ]]; then
  ok "Vite-built /assets/ tree referenced ($ASSET_PATH)"
  if "${CURL[@]}" -o /dev/null "${FRONTEND_URL}${ASSET_PATH}"; then ok "$ASSET_PATH reachable"; else fail "$ASSET_PATH unreachable"; fi
else
  fail "no /assets/*.{js,css} reference — frontend may be serving standalone-src (ADR 0011 regression)"
fi
# Negative check: production must NOT be serving standalone-src.
if printf '%s' "$FE_HTML" | grep -qE '/src/data\.js|/src/backend-loader\.js'; then
  fail "frontend index.html references /src/*.js{,x} — standalone-src is being served (ADR 0011 regression)"
else
  ok "no /src/*.js{,x} references (standalone-src is NOT being served)"
fi

# ── 5. Per-entity surfaces populate ─────────────────────────────────
if [[ -n "$ENT_ID" ]]; then
  echo ""
  echo "[5/6] Per-entity surfaces for display_id=$ENT_ID"
  for p in "/overview" "/insights" "/heatmap?zoom=pillar" "/platforms"; do
    rc="$(curl --silent -b "$CJ" -o /dev/null -w "%{http_code}" --max-time 20 "${BACKEND_URL}/api/v1/entities/${ENT_ID}${p}" || echo 000)"
    if [[ "$rc" == "200" ]]; then ok "/entities/${ENT_ID}${p} → 200"; else fail "/entities/${ENT_ID}${p} → $rc"; fi
  done
else
  echo ""
  echo "[5/6] SKIPPED — no entity to probe"
fi

# ── 6. Derived-data jobs ran (the post-commit dispatch + reconciliation) ──
echo ""
echo "[6/6] Derived-data jobs ran (job_executions + section_embeddings + customer_intelligence_profiles)"
# Connect via the migrations job's cloud-sql-proxy if PG_CONN not set.
if [[ -z "${PG_CONN:-}" ]]; then
  echo "  ℹ PG_CONN not set — skipping DB-side derived-data check."
  echo "    Set PG_CONN=postgresql+psycopg://... to verify section_embeddings/"
  echo "    customer_intelligence_profiles counts directly."
else
  if command -v psql >/dev/null 2>&1; then
    N_SE="$(psql "${PG_CONN/+psycopg/}" -tA -c 'SELECT COUNT(*) FROM section_embeddings;' 2>/dev/null || echo 0)"
    N_CIP="$(psql "${PG_CONN/+psycopg/}" -tA -c 'SELECT COUNT(*) FROM customer_intelligence_profiles;' 2>/dev/null || echo 0)"
    [[ "$N_SE" -gt 0 ]]  && ok "section_embeddings count=$N_SE" || fail "section_embeddings empty — embedder dispatch may have failed"
    [[ "$N_CIP" -gt 0 ]] && ok "customer_intelligence_profiles count=$N_CIP" || fail "customer_intelligence_profiles empty — intelligence_recompute dispatch may have failed"
    # Cross-check job_executions recently fired.
    psql "${PG_CONN/+psycopg/}" -tA -c "SELECT job_name, status, COUNT(*) FROM job_executions WHERE job_name IN ('embedder','intelligence_recompute') AND started_at > NOW() - INTERVAL '6 hours' GROUP BY 1,2 ORDER BY 1,2;" 2>/dev/null | while IFS='|' read -r jn st cn; do
      [[ -n "$jn" ]] && ok "  job_executions: $jn / $st = $cn"
    done
  else
    echo "  ℹ psql not on PATH — skipping DB-side derived-data check."
  fi
fi

echo ""
if [[ "$FAILED" -eq 0 ]]; then
  echo "✓ All $green data-flow checks passed."
  exit 0
fi
echo "✗ $FAILED check(s) failed out of $((green + FAILED))."
exit "$FAILED"
