# ADR 0011 — Standalone is the live AE-facing surface; Vite is wireframe-guide build

Date: 2026-05-24
Status: **Superseded by ADR 0016 (2026-05-29).** The 2026-05-29 deep
QA audit identified that the standalone's intentionally-empty
run-scoped collections (`EVIDENCE` / `INSIGHT_CARDS` / etc.) were the
root cause of the user-visible "dummy page" failure mode. ADR 0016
restores Vite/React as production. The text below is preserved as
the historical record of the temporary revert.

## Context

Plan v2 §E1–§E5 originally called for porting every prototype page
into the Vite + React + TS frontend at `frontend/src/` so that bundle
would become the production artifact served on Cloud Run, with
`frontend/standalone-src/` reduced to a stakeholder demo.

Operationally, the inverse happened: the standalone bundle at
`frontend/standalone-src/` was wired against the live backend over
the course of the project, gained role-aware chrome, the
IntelligencePanel, EvidenceDrawer, AdminPage, Drive-feedback wiring,
and the staleness banner. The Vite shell remains in
`frontend/src/` as a parallel build that exercises the same backend
but is **not** what AEs reach in production.

## Decision

**Lock in the current state**: `frontend/standalone-src/` is the
authoritative live AE-facing surface. The Vite tree at
`frontend/src/` becomes the wireframe-guide / stakeholder-demo
build — the inverse of the original plan.

## Rationale

1. The standalone bundle is the **only** surface the operator
   (Mishley + the 6 admin emails) has been signing into for
   verification rounds. Every fix we shipped since `c0bdc74` —
   the auth role hydration, the 4 missing Vite endpoints, the
   RAG streaming endpoint, the staleness banner — landed in
   `standalone-src/`. The Vite tree has not seen production traffic.

2. The standalone bundle has a complete chrome (Sidebar, TopBar,
   IntelligencePanel right-rail), 16 surfaces, role-gated nav,
   admin pages, customer-view audience strip, and the full set of
   modals (InsightModal, EvidenceDrawer, RecommendationModal,
   SynthesisDrawer, NewRunModal). The Vite tree has the same
   skeleton but with thinner coverage on the chrome state
   machines that the operator-tuned standalone already nails.

3. The Vite + React + TS production build (`pnpm run build`) still
   compiles cleanly + tsc-clean and 186/186 vitest pass. It works
   as a **wireframe-guide** for stakeholder previews built from
   mock `data.ts`. CLAUDE.md already documents this dual-track:
   > `DMA Insights · Standalone.html` is a wireframe-guide /
   > stakeholder-demo single-file build... The live web app is
   > the only production surface.

4. The single-file `dist-standalone/index.html` build remains the
   demo artifact (sent to non-Zennify stakeholders for offline
   previews). 360 KB gzipped; no live data wired in.

5. Re-porting the full standalone into the Vite tree would touch
   every chrome + drawer + page file twice without operator-visible
   benefit. The cost is high, the value is zero given the
   production surface is already on the standalone bundle.

## Consequences

- **Frontend.Dockerfile** serves `frontend/standalone-src/` (not
  `dist/`) — already true; documented in §35 and the production
  smoke checklist.
- **E2E personas / visual regression** (plan §A2 / §A3) target the
  standalone bundle. The Playwright config under
  `frontend/playwright*.config.ts` already points there.
- **Vite tree** stays for wireframe demos + as a place to prototype
  visual changes before porting to standalone. `pnpm run build`
  must stay clean (CI gate) so a parser regression there surfaces.
- **Plan §E1–§E5 are CLOSED** — superseded by this decision. The
  goal those gates encoded ("a maintained, type-safe production
  frontend") is satisfied differently: by the operator-tuned
  standalone bundle plus the parallel Vite build for
  type-checking + tooling.

## Future work

If the standalone bundle's bundle-size or maintainability becomes
a real bottleneck (currently 360 KB gzipped — well under any UX
budget), revisit. Until then, dual-track is fine.

## Related

- CLAUDE.md "Wireframe contract" section
- DEPLOYMENT.md §35 "B5 / B3 quality gates"
- `frontend/standalone-src/src/*.jsx` — the live AE surface
- `frontend/src/*.tsx` — wireframe-guide + type-check parallel build
