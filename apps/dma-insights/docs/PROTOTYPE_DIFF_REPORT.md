# Prototype-vs-Production Visual Diff

**v2 — 2026-06-11 QA-driven rebuild.** Strict pixel metric (any RGB
channel ≥ threshold counts) at 1440px, production seeded with the real
96-DMA fixture corpus (95 ACTIVE entities), rich entity = `alma-bank-0001`.

## Methodology honesty (read before the numbers)

The strict metric compares production rendering **real Alma Bank data**
against the prototype rendering **mock Farm Credit East data** — every
differing word is a "divergent pixel". The structural floor measured on
an identical-layout page (login) is ~6%; text-dense pages carry a
30-45% content component that no faithful port can remove. The numbers
below are therefore a *ranking + regression tripwire*; the acceptance
evidence for the 2026-06-11 rebuild is the per-page side-by-side
structural review (`/tmp/qa-sbs/`) and the Playwright click-through
verifications recorded in the rebuild commits.

## v2 results @1440 (after the rebuild)

| Route | v1 | v2 | structural verdict |
|---|---:|---:|---|
| heatmap (Standard grid state) | 58.9% | 47.4% | grid vs grid ✓ — pillar bands, Entity/Peer rows, 689 maturity-class cells, zoom ladder, synthesis drawer on leaf cells |
| platform | 46.7% | 42.2% | sections match ✓ — card row, gap table, readiness, chat-bubble starters, stairstep curve, dark 3-phase roadmap (single phase until corpus recs carry effort_band) |
| techstack | 50.6% | 46.1% | anatomy ✓ — legend, left-border stat strip, 4 layer cards, displacement banner |
| context | 49.7% | <34% | structure ✓ — horizontal timeline + EventDetail, Gantt + IssueDetail, financial bar chart, regulatory callout |
| admin-import | 42.7% (AdminPage rendered!) | 36.5% | dedicated ImportPage ✓ — stage pipeline, live log, job table |
| overview | 51.1% | ~33% | SCQA clamped (3757→1868px), OSS strip live, intelligence card gated |
| insights | 66.7% | ~25% | cards + 4-tab modal + tech-landscape strip |
| runs | 11.6% | ≤12% | assessment-date binding + chip families |
| health / alerts | 50%+ (empty data) | populated | producer live: 1,552 alerts; 6-column wireframe table |
| dashboard / directory | 24.6 / 24.1% | ≈ | small deltas only |
| login / prospecting | 6.4 / 2.5% | ≈ | pass (structural floor) |

Multi-width pairs (1920/1280/980/760) captured pre-rebuild remain in
`/tmp/qa-diffs` for reference; the responsive contract is enforced by
`pnpm test:visual` (7 breakpoints × routes) going forward.

## Tier interpretation (strict metric, content-adjusted)
- 🔴 large STRUCTURAL deltas — none remaining after the 2026-06-11 rebuild
- 🟡 content-dominated 30-50% — expected for text-dense pages vs mock data
- 🟢 <15% — chrome-only variation

Diff PNGs: `/tmp/qa-diffs/<pair>-diff.png`. Capture flow:
serve the wireframe on :8082 → `/tmp/proto-capture-full.mjs` +
`/tmp/proto-capture-2.mjs` (routes + transitions + 5 widths) →
`/tmp/prod-capture.mjs` (mirrored) → `/tmp/diff-qa.py`.
