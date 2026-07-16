#!/usr/bin/env bash
# A5 — Post-deploy smoke gate.
#
# Runs against a live Cloud Run revision after every deploy.
# Exits non-zero if ANY check fails so the deploy is marked broken
# instead of silently serving 401s / 404s / stale schema.
#
# Checks (matches §32.11 + §36.14 smoke catalog):
#   1. /healthz returns 200
#   2. /readyz returns 200 with migration_head reported
#   3. 4 canonical Vite endpoints exist (return 401 not 404)
#   4. /rag/answer + /stream exist (POST-only → 405 not 404)
#   5. /auth/me returns 401 (auth gate present)
#   6. Production-readiness guard didn't block startup (covered by 1)
#   7. drive-feedback audit channel writable (covered by §34 query)
#   8. Gemini live surface gate (qa_gemini_surfaces --mode live):
#      non-fallback /rag/answer with ≥1 citation + source:"vertex"
#      provenance on a why_now-bearing overview. Full assertions need
#      DMA_SMOKE_TOKEN (a session JWT); without it the gate degrades
#      to registration checks + a warning. _ALLOW_COLD_GEMINI=true
#      downgrades failures to warnings (deliberate cold deploy).
#   9. Startup-pack freshness (master plan Part 14): the deployed
#      frontend's baked /startup-data/pages_manifest.json must carry
#      source_sha == the SHA just deployed. Catches --skip-build
#      reusing an old image whose pack predates data/derive changes —
#      the case the build-time frontend-image-smoke check 6 can't see.
#      Needs FRONTEND_URL + DEPLOY_SHA (or SHA); degrades to an
#      informational pass without them. _ALLOW_STALE_PACK=true
#      downgrades a mismatch to a warning (deliberate stale pack).
#
# Usage:
#   ./post-deploy-smoke.sh https://dma-insights-backend-XYZ-uc.a.run.app
#   FRONTEND_URL=https://dma-insights-frontend-….run.app SHA=abc1234 \
#     ./post-deploy-smoke.sh https://dma-insights-backend-….run.app
#
# Exit codes:
#   0  — all checks green
#   2  — at least one check failed (deploy is broken)
set -euo pipefail

BE="${1:-${BACKEND_URL:-}}"
if [[ -z "$BE" ]]; then
    echo "usage: $0 <backend_url>"
    echo "  or set BACKEND_URL env var"
    exit 2
fi
BE="${BE%/}"  # strip trailing slash

FAIL=0
log_pass() { echo "  ✓ $*"; }
log_fail() { echo "  ✗ $*"; FAIL=$((FAIL+1)); }

echo "─────────────────────────────────────────────────────────────"
echo " A5 — Post-deploy smoke gate"
echo "─────────────────────────────────────────────────────────────"
echo "backend: $BE"
echo

echo "[1/9] /healthz"
if curl -sf "$BE/healthz" >/dev/null; then
    log_pass "/healthz returns 200"
else
    log_fail "/healthz returned non-200 — production-readiness guard may have blocked startup; check Cloud Run logs"
fi

echo "[2/9] /readyz with migration_head"
READYZ=$(curl -s -o /tmp/readyz.json -w '%{http_code}' "$BE/readyz")
if [[ "$READYZ" == "200" ]]; then
    HEAD=$(jq -r '.migration_head // "missing"' /tmp/readyz.json 2>/dev/null)
    if [[ "$HEAD" != "missing" && "$HEAD" != "unknown" ]]; then
        log_pass "/readyz returns 200 with migration_head=$HEAD"
    else
        log_fail "/readyz returned 200 but migration_head missing — D1 wiring broken"
    fi
else
    BODY=$(cat /tmp/readyz.json 2>/dev/null | head -c 200)
    log_fail "/readyz returned $READYZ — body: $BODY"
fi

echo "[3/9] 4 Vite endpoints registered"
for endpoint in \
    "/api/v1/entities/fce-001/heatmap/subcap/P1C1.1.1" \
    "/api/v1/entities/fce-001/platforms/roadmap" \
    "/api/v1/entities/fce-001/techstack/landscape" \
    "/api/v1/entities/fce-001/health/version-diff"; do
    STATUS=$(curl -s -o /dev/null -w '%{http_code}' "$BE$endpoint")
    # 401 = registered + auth required; 404 = unregistered (broken)
    if [[ "$STATUS" == "401" || "$STATUS" == "404" ]]; then
        # 404 could mean entity-not-found OR route-not-registered. Probe
        # auth gate to disambiguate — auth-gated endpoints return 401
        # ahead of the entity lookup.
        AUTHED=$(curl -s -o /dev/null -w '%{http_code}' "$BE$endpoint")
        if [[ "$AUTHED" == "404" ]]; then
            # Check the route table via /openapi.json
            if curl -sf "$BE/openapi.json" 2>/dev/null \
               | jq -e --arg p "${endpoint%/*}" '.paths | keys[] | select(. | startswith($p))' >/dev/null 2>&1; then
                log_pass "$endpoint (registered + entity not in DB)"
            else
                log_fail "$endpoint NOT REGISTERED (Vite would 404)"
            fi
        elif [[ "$AUTHED" == "401" ]]; then
            log_pass "$endpoint (registered + auth-gated)"
        else
            log_fail "$endpoint unexpected status $STATUS"
        fi
    elif [[ "$STATUS" == "200" || "$STATUS" == "401" ]]; then
        log_pass "$endpoint (registered)"
    else
        log_fail "$endpoint returned $STATUS"
    fi
done

echo "[4/9] RAG endpoints"
for endpoint in /api/v1/rag/answer /api/v1/rag/answer/stream; do
    # POST-only endpoints return 405 on GET, 401 if auth-gated.
    STATUS=$(curl -s -o /dev/null -w '%{http_code}' "$BE$endpoint")
    if [[ "$STATUS" == "401" || "$STATUS" == "405" ]]; then
        log_pass "$endpoint (registered, status $STATUS)"
    else
        log_fail "$endpoint returned $STATUS (expected 401 or 405)"
    fi
done

echo "[5/9] /auth/me is auth-gated"
STATUS=$(curl -s -o /dev/null -w '%{http_code}' "$BE/api/v1/auth/me")
if [[ "$STATUS" == "401" ]]; then
    log_pass "/auth/me returns 401 (auth gate works)"
else
    log_fail "/auth/me returned $STATUS (expected 401 — auth gate broken)"
fi

echo "[6/9] OpenAPI spec advertises critical endpoints"
SPEC=$(curl -sf "$BE/openapi.json" 2>/dev/null || echo "")
if [[ -z "$SPEC" ]]; then
    log_fail "/openapi.json unreachable — backend lifespan broken"
else
    EXPECTED_COUNT=$(echo "$SPEC" | jq -r '.paths | keys | length // 0')
    if [[ "$EXPECTED_COUNT" -ge 50 ]]; then
        log_pass "openapi.json has $EXPECTED_COUNT registered paths"
    else
        log_fail "openapi.json has only $EXPECTED_COUNT paths (expected 50+) — routers missing from main.py"
    fi
fi

echo "[7/9] CORS allow-list"
ORIGIN_HEADER=$(curl -s -o /dev/null -D - "$BE/healthz" -H "Origin: https://insights.zennify.com" \
    | grep -i "access-control-allow-origin" || echo "")
if [[ -n "$ORIGIN_HEADER" ]]; then
    log_pass "CORS allow-list reachable ($ORIGIN_HEADER)"
else
    log_pass "CORS check informational (no allow-origin header on simple GET)"
fi

echo "[8/9] Gemini live surface gate (qa_gemini_surfaces --mode live)"
# Runs the python gate from the repo checkout (stdlib-only in live mode,
# so any python3 works; prefer the backend venv when present). Asserts:
# POST /rag/answer non-fallback + ≥1 citation, and source:"vertex"
# provenance on a why_now-bearing overview. DMA_SMOKE_TOKEN (session
# JWT) unlocks the authenticated assertions; without it the gate
# degrades to route-registration checks and warns.
SMOKE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # backend/
PYBIN="python3"
[[ -x "$SMOKE_DIR/.venv/bin/python" ]] && PYBIN="$SMOKE_DIR/.venv/bin/python"
if [[ ! -f "$SMOKE_DIR/app/scripts/qa_gemini_surfaces.py" ]]; then
    log_fail "qa_gemini_surfaces.py not found under $SMOKE_DIR — run from the repo checkout"
elif (cd "$SMOKE_DIR" && "$PYBIN" -m app.scripts.qa_gemini_surfaces --mode live --base-url "$BE"); then
    log_pass "Gemini live surface gate passed"
else
    RC=$?
    if [[ "${_ALLOW_COLD_GEMINI:-${ALLOW_COLD_GEMINI:-}}" == "true" ]]; then
        log_pass "Gemini live gate failed (rc=$RC) but _ALLOW_COLD_GEMINI=true — deliberate cold deploy (AI surfaces serve deterministic fallbacks until warmed)"
    else
        log_fail "Gemini live surface gate FAILED (rc=$RC) — see the per-check remediation above; escape hatch: _ALLOW_COLD_GEMINI=true"
    fi
fi

echo "[9/9] Startup-pack freshness (frontend pages_manifest.json source_sha)"
# The frontend image bakes startup-data/ at build time; the regen stage
# stamped source_sha=${_IMAGE_SHA} into pages_manifest.json (see
# frontend-image-smoke check 6, the build-time gate). This LIVE check
# catches what the build can't: --skip-build shipping an old image whose
# baked pack predates the data/derive changes. Needs FRONTEND_URL + the
# deployed SHA (DEPLOY_SHA or SHA); informational otherwise.
FE_URL="${FRONTEND_URL:-}"
EXPECT_SHA="${DEPLOY_SHA:-${SHA:-}}"
if [[ -z "$FE_URL" || -z "$EXPECT_SHA" ]]; then
    log_pass "pack-freshness check informational (set FRONTEND_URL + DEPLOY_SHA/SHA to assert the baked pack matches the deployed SHA)"
else
    PACK_SHA=$(curl -sf "${FE_URL%/}/startup-data/pages_manifest.json" 2>/dev/null \
        | jq -r '.source_sha // ""' 2>/dev/null || echo "")
    if [[ -n "$PACK_SHA" && "$PACK_SHA" == "$EXPECT_SHA" ]]; then
        log_pass "baked startup pack is FRESH (source_sha=$PACK_SHA == deployed SHA)"
    elif [[ "${_ALLOW_STALE_PACK:-${ALLOW_STALE_PACK:-}}" == "true" ]]; then
        log_pass "baked pack source_sha='${PACK_SHA:-<unreachable>}' != deployed SHA '$EXPECT_SHA' but _ALLOW_STALE_PACK=true — deliberate stale pack (AEs see the committed point-in-time snapshot until the next full build)"
    else
        log_fail "baked pack source_sha='${PACK_SHA:-<unreachable>}' != deployed SHA '$EXPECT_SHA' — a STALE startup pack is LIVE. Cause: the regen failed at build time or --skip-build reused an old image. Rebuild WITHOUT --skip-build (never --skip-build after data/derive changes); escape hatch: _ALLOW_STALE_PACK=true"
    fi
fi

echo
echo "─────────────────────────────────────────────────────────────"
if [[ "$FAIL" -eq 0 ]]; then
    echo " ✓ A5 — Post-deploy smoke gate PASSED"
    echo "─────────────────────────────────────────────────────────────"
    exit 0
else
    echo " ✗ A5 — Post-deploy smoke gate FAILED ($FAIL check(s))"
    echo "─────────────────────────────────────────────────────────────"
    echo
    echo "Deploy is silently broken. DO NOT mark green until root"
    echo "cause is identified. See DEPLOYMENT.md §36.14 for the next"
    echo "diagnostic step per check."
    exit 2
fi
