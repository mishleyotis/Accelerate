# ADR 0016 — React/Vite is the production frontend (supersedes ADR 0011)

Date: 2026-05-29
Status: Accepted (supersedes ADR 0011)

## Context

ADR 0011 (2026-05-24) locked in `frontend/standalone-src/` as the
production AE-facing surface, on the grounds that the standalone
bundle was visually faithful to the prototype while the Vite/React
port at `frontend/src/` had visual-fidelity gaps (empty SVGs, missing
chat drawer, sidebar bullet fallback). That ADR was a temporary
revert; the underlying "Stack" lock in `CLAUDE.md` always specified
**Vite + React 18 + TS + hash routing**.

The 2026-05-29 deep QA audit found that ADR 0011 was producing a
user-visible failure mode the team labeled the "dummy page":

1. `frontend/standalone-src/src/data.js` initializes run-scoped
   collections — `EVIDENCE`, `INSIGHT_CARDS`, `RECOMMENDATIONS`,
   `ROADMAP`, `FOCUS_AREAS`, `TECH_STACK`, `QA_GATES`, `IMPORT_AUDIT`,
   `PENDING_REVIEW`, `PATTERNS` — as `[]` with the literal comment
   "UNTIL WIRED TO BACKEND" (lines 143-150). It also ships a
   `WIRING_NEEDS` object listing the backend endpoints intended to
   eventually populate each one.
2. `frontend/standalone-src/src/backend-loader.js` boot only fetches
   four endpoints (`/auth/me`, `/entities?owner=all`, `/dashboard`,
   `/alerts`) and only mutates three globals (`DMA.ENTITIES`,
   `DMA.ACTIVE_RUNS`, `DMA.ALERTS`). Every other surface reads
   directly from the empty arrays in `data.js`, so it renders empty
   even when the backend has real data.
3. The React tree at `frontend/src/` has TanStack-Query hooks
   pointing at the full set of endpoints (`queries.ts` enumerates
   dashboard / entities / overview / insights / heatmap / platforms
   / alerts / etc.), and each page handles `isLoading` + `error` +
   `empty` locally. There is no global "fail the whole app" surface.

The visual-fidelity reasons that drove ADR 0011 have since been
resolved (the Vite tree gained the missing components, and the
prototype's `tokens.css` + `app.css` + components are still the
single source of truth shared between both builds — see CLAUDE.md
"Wireframe contract").

## Decision

**Production serves `frontend/dist/` (the Vite-built React/TS bundle).**
The standalone single-file bundle at `frontend/standalone-src/` is
retained as the **wireframe-guide / stakeholder-demo** artifact,
matching the original characterization in CLAUDE.md "Wireframe
contract" ("DMA Insights · Standalone.html is a wireframe-guide /
stakeholder-demo single-file build with mock data inlined. **Not
used by AEs; not connected to live data.**").

Concretely:

- `infra/docker/frontend.Dockerfile` is a multi-stage build:
  - **Stage 1** (`node:22-alpine`): `pnpm install --frozen-lockfile`,
    then `pnpm run build` (= `tsc --noEmit && vite build`) outputs
    `dist/`. `VITE_GOOGLE_OAUTH_CLIENT_ID` threads in via build-arg
    (optional — LoginPage.tsx has a documented public fallback).
  - **Stage 2** (`nginx:1.27-alpine`): `apk add gettext` for
    `envsubst`, COPY the nginx template, `COPY --from=build
    /app/frontend/dist/` into the site root, stamp
    `<meta name="x-build-sha">` + `window.__BUILD_SHA__` so
    `verify-deploy.sh` Layer 2 can confirm which revision is live.
- `infra/cloudbuild.yaml` stage 7b (frontend-image-smoke) verifies:
  - `/healthz` returns `ok`
  - `/` returns the Vite-built index.html
  - the `<meta x-build-sha>` stamp is present
  - the index.html references a `/assets/*.{js,css}` content-hashed
    bundle AND that asset is reachable
  - `/api/*` is reverse-proxied (status ≠ 404; SPA-fallback regression
    is caught)
- `backend/tests/test_docker_and_cloudbuild_contracts.py::test_frontend_image_serves_vite_dist_not_standalone_src`
  pins the new contract.

The `frontend-nginx.template` is **unchanged** — its `${BACKEND_URL}`
proxy + `try_files $uri /index.html` SPA fallback already work
identically for Vite hash-routed URLs.

## Consequences

### Positive
- Eliminates the "dummy page" failure mode at the source.
- Each surface renders real data or its own empty state (no global
  "Backend data failed to load" banner — those are now scoped per
  request via React Query's per-component error handling).
- Re-aligns the Dockerfile with the "Locked decisions" stack
  (React + Vite + hash routing) so the codebase stops contradicting
  itself.
- Vite's content-hashed assets (`/assets/*.[hash].js`) make the
  no-cache `?v=<sha>` URL stamping the standalone Dockerfile used
  obsolete — the URL itself changes per build.

### Negative
- First deploy on the new image rebuilds **node_modules** in CI;
  cold builds add ~60-90s vs the no-build standalone path. Cached
  builds (frozen lockfile hit) recover this.
- The OAuth client ID is inlined at build time. Per-env overrides
  require either a `--build-arg VITE_GOOGLE_OAUTH_CLIENT_ID=…` or
  the `_GOOGLE_OAUTH_CLIENT_ID` cloudbuild substitution; the
  documented public fallback ships in the bundle otherwise.
- Operators viewing source via DevTools see `index-[hash].js`
  filenames instead of `app-root.jsx` — a slight loss for live
  debugging that's offset by source-map availability.

### Compensating contracts
- `backend/scripts/run-local-tests.sh` runs `pnpm run build`
  through the same path so a broken Vite build trips locally before
  any image push.
- Stage 7b's `/assets/*.js` check catches a Dockerfile regression
  that ships an empty `dist/`.
- The standalone tree stays in the repo (under
  `frontend/standalone-src/`) for stakeholder demos. The
  `pnpm run build:standalone` script in `package.json` is
  unchanged.

## Migration

This is a **deploy-time** change — no DB migration, no API change.
The operator's next deploy will:

1. Cloud Build runs the new Dockerfile, which `pnpm install` +
   `vite build` + COPY dist/ + stamps the BUILD_SHA.
2. Stage 7b probes the new image and refuses the push if the asset
   tree is broken.
3. The Cloud Run frontend service rolls to the new revision.
4. `verify-deploy.sh` Layer 1/2/3/4 all green as before
   (`x-build-sha` lookup still works on the Vite-emitted index.html).

If a rollback is needed, the prior revision (still tagged in gcr.io)
serves the old standalone bundle — no incremental migration steps
to undo.

## Related

- ADR 0011 (superseded)
- CLAUDE.md "Locked decisions" — stack
- CLAUDE.md "Wireframe contract" — standalone's role as demo-only
- 2026-05-29 deep QA validated report — root-cause analysis
