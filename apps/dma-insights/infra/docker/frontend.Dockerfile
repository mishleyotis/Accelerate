# DMA Insights frontend — multi-stage Vite + React SPA served by nginx.
#
# Per ADR 0016 (2026-05-29 — supersedes ADR 0011) the production frontend
# is the Vite-built React/TS bundle at `frontend/dist/`. The standalone
# single-file artifact at `frontend/standalone-src/` is kept as a
# stakeholder-demo / wireframe-guide build (mock data inlined; not AE-
# facing). See docs/decisions/0016-react-vite-as-production.md.
#
# Why the switch:
#   • Standalone's data.js intentionally declares EVIDENCE, INSIGHT_CARDS,
#     RECOMMENDATIONS, ROADMAP, FOCUS_AREAS, TECH_STACK, QA_GATES,
#     IMPORT_AUDIT, PENDING_REVIEW, PATTERNS as `[]` "UNTIL WIRED TO
#     BACKEND" (see frontend/standalone-src/src/data.js:143-150). Boot
#     only hydrates ENTITIES + ACTIVE_RUNS + ALERTS — every other surface
#     renders empty even when the backend has the data. AEs called this
#     the "dummy page".
#   • The React tree (frontend/src/) has TanStack-Query hooks pointing
#     at every endpoint (queries.ts) and React-Query handles loading +
#     error per-component, so each page renders real data or its own
#     empty state — never a global app-wide "Backend data failed to
#     load" banner.
#   • CLAUDE.md "Locked decisions" already specifies React + Vite + hash
#     routing as the stack; ADR 0011 was a temporary revert and 0016
#     restores alignment.
#
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  ERROR HISTORY — keep this list in sync with new failure modes.      ║
# ╠══════════════════════════════════════════════════════════════════════╣
# ║  D1  Heredoc 'RUN cat > /file <<EOF' parsed only the first line      ║
# ║      → 'syntax error: unexpected end of file' during docker build    ║
# ║      → Cause: cloud-builders/docker uses classic Docker 20.10        ║
# ║        which can't parse RUN-level heredocs without BuildKit         ║
# ║      FIX: nginx config externalised via COPY of frontend-nginx.template
# ║                                                                      ║
# ║  D5  envsubst didn't substitute ${BACKEND_URL} at container start    ║
# ║      → Cause: missing 'apk add gettext' on the alpine base           ║
# ║      FIX: gettext installed on the runtime stage                     ║
# ║                                                                      ║
# ║  D6  <meta name="x-build-sha"> never landed in served index.html     ║
# ║      → Cause: BusyBox sed mangled the `\\n` round-trip in the prior  ║
# ║        sed-replacement strategy. printf-to-tempfile + `sed /pat/r`   ║
# ║        injects literal newlines that work on GNU + BusyBox sed.      ║
# ║                                                                      ║
# ║  D7  Vite build needs the OAuth client ID at compile time (it's      ║
# ║      inlined via `import.meta.env.VITE_GOOGLE_OAUTH_CLIENT_ID`).     ║
# ║      Threading via ARG → ENV before `vite build` is the only way to  ║
# ║      get it into the bundle. LoginPage.tsx has a hardcoded public    ║
# ║      fallback (the documented digital-maturity-assessor client ID),  ║
# ║      so the ARG is OPTIONAL — empty arg → fallback in bundle.        ║
# ╚══════════════════════════════════════════════════════════════════════╝

# ─── Stage 1: build the Vite/React SPA ────────────────────────────────
FROM node:22-alpine AS build
WORKDIR /app/frontend

# pnpm ships via Corepack on node 22; enable it so `pnpm` works without
# a global install (and we get the lockfile-pinned version).
RUN corepack enable

# Cache the dep install layer — only re-runs when lockfile changes.
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# Now bring in the source.
COPY frontend/ ./

# Committed startup-data snapshot — the dashboard's first-paint payload.
# src/lib/startup-data.ts imports `../../../startup-data/dashboard.json`,
# which resolves to /app/startup-data from /app/frontend/src/lib. The build
# FAILS LOUDLY if this is missing (intentional: never ship a frontend
# without its first-paint data). Must precede `pnpm run build`.
COPY startup-data /app/startup-data

# Build-time env. The OAuth client ID is OPTIONAL — LoginPage.tsx
# falls back to the public production client ID when unset, so a build
# without the ARG still produces a functional bundle.
ARG VITE_GOOGLE_OAUTH_CLIENT_ID=""
ARG BUILD_SHA=local
ENV VITE_GOOGLE_OAUTH_CLIENT_ID=$VITE_GOOGLE_OAUTH_CLIENT_ID

# `pnpm run build` = `tsc --noEmit && vite build`. Output → dist/.
# Vite produces a content-hashed asset tree under dist/assets/ so the
# cache-bust contract is built-in (different commits → different
# asset filenames → cache MUST refetch). The ?v=<sha> sed pattern the
# standalone Dockerfile used is obsolete with Vite's content hashes.
RUN pnpm run build

# ─── Stage 2: nginx serves the built assets ───────────────────────────
FROM nginx:1.27-alpine

# nginx-alpine auto-runs envsubst on every `*.template` in
# /etc/nginx/templates at container start (entrypoint script does this
# without us asking). gettext provides envsubst — without it the
# template ships literal ${BACKEND_URL} and every /api/* proxy fails.
RUN apk add --no-cache gettext && rm -rf /etc/nginx/conf.d/default.conf
RUN mkdir -p /etc/nginx/templates

# The same nginx template as before — Vite hash-routing means any
# unknown non-/api path still falls through to /index.html. The template
# uses ${BACKEND_URL} substitution to keep image immutable across envs.
COPY infra/docker/frontend-nginx.template /etc/nginx/templates/default.conf.template

# Pull the Vite-built bundle from the build stage. dist/ contains
# index.html + assets/ (content-hashed JS/CSS) + brand/ + favicons.
COPY --from=build /app/frontend/dist/ /usr/share/nginx/html/

# ── Build-time SHA stamping (operator visibility) ───────────────────
# Vite already content-hashes every JS/CSS asset under /assets/, so the
# ?v=<sha> cache-bust the standalone Dockerfile applied is no longer
# needed. We still inject a <meta name="x-build-sha"> + window.__BUILD_SHA__
# into index.html so the operator can verify which revision is live via
# curl OR DevTools — verify-deploy.sh Layer 2 parses this tag.
#
# State branches:
#   build_sha_provided    → <meta> tag inserted; window.__BUILD_SHA__ set
#   build_sha_blank       → no-op (local dev build, no operator stamping)
#   index_already_stamped → idempotent; the printf+sed inject is safe to
#                           re-run; sed -i is a no-op on second pass since
#                           the file already contains the meta tag.
ARG BUILD_SHA=local
RUN if [ -f /usr/share/nginx/html/index.html ] && [ -n "$BUILD_SHA" ]; then \
      # Vite's index.html has <meta charset="UTF-8" /> (with the
      # self-closing slash + space). Use a tolerant regex that matches
      # both that form AND the no-slash form, so a future Vite version
      # change in index.html shape doesn't silently break the stamp.
      printf '  <meta name="x-build-sha" content="%s">\n  <script>window.__BUILD_SHA__="%s";console.info("[DMA] build=%s");</script>\n' "${BUILD_SHA}" "${BUILD_SHA}" "${BUILD_SHA}" > /tmp/dma-meta-stamp ; \
      sed -i -E "/<meta charset=\"UTF-8\" ?\/?>/r /tmp/dma-meta-stamp" /usr/share/nginx/html/index.html ; \
      rm -f /tmp/dma-meta-stamp ; \
      echo "✓ stamped BUILD_SHA=${BUILD_SHA} into index.html" ; \
      grep -q "x-build-sha" /usr/share/nginx/html/index.html \
        || { echo "✗ stamp inject failed — index.html shape changed?"; exit 1; } ; \
    fi

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -q --spider http://localhost:8080/healthz || exit 1
