# DMA Insights — wireframe reference (revision: uploaded 2026-07-02)

This directory holds the **visual + functional contract** for the 1:1 rebuild
of the production React surface (`frontend/src/` → `frontend/dist/`, ADR 0016).
It is **reference material only** — nothing here is imported or built.

> **Revision history**
> - 2026-06 — initial upload (2.3 MB self-extracting single-file bundle).
> - **2026-07-02 — refreshed to the operator's latest revision** (plan
>   Part 11.2). This revision ships as a template HTML + 13 externally-loaded
>   source chunks (uuid-named in the upload; renamed to the readable mapping
>   below, load order preserved). Headline deltas vs 2026-06:
>   - **NEW `05b_cards.js` module** — the five data-driven D1 cards
>     (`EvidenceTierCard` · `SentimentCard` · `FinancialTrajectoryCard` ·
>     `CoverageByPillarCard` · `CeilingEstimateCard`), each tagged with
>     `data-source="<canonical file> :: <field>"` bindings to the real DMA
>     deliverable shapes.
>   - **Deep Why-Now modules on D1** — `WhyNowStrip` signal tiles (tag +
>     body + per-signal E-ID evidence chips, <24-month triggers) feeding the
>     `why_now` IntelligencePanel surface + Meeting-prep entry point.
>   - Mock data layer grew 62 KB → 85 KB (`01_data.js`); D3 heatmap chunk
>     refactored (FocusAreaView / ValueChainView / CustomizableKpiStrip
>     co-located); larger drawers chunk (per-E-ID evidence scoping).
>   - `02_components_a.js`, `11_tweaks.js`, `12_root.js`, `tokens.css` —
>     unchanged between revisions.

## Why this exists separately from `frontend/standalone-src/`

`frontend/standalone-src/` is the existing **backend-wired** stakeholder demo
(it calls `useJobTrigger` / `listJobExecutions` / `backend-loader.js`, and the
`standalone-admin-defects.test.ts` suite asserts its identifiers). The bundle
the operator uploads is a **different, newer wireframe-guide**: ~3× the
inline mock data, refined D1/D3, value-chain mode, `SynthesisDrawer`, 4-tab
`InsightModal`, 3-tab `RecommendationModal`, 5-surface `IntelligencePanel`,
focus-area `CustomizableKpiStrip`, `ImportPage` + `ImportAuditPage`, the five
new D1 deliverable cards, etc. — but **no live-backend wiring**.

To avoid regressing the backend-wired demo (and its tests), the uploaded
wireframe is kept here as the rebuild's reference; `standalone-src/` is left
intact. The rebuild target is the production React tree at `frontend/src/`.

## Contents

- `DMA_Insights__Standalone.html` — the uploaded revision's template HTML
  (decoded). NOTE (2026-07 revision): unlike the 2026-06 self-extracting
  bundle, this template loads its chunks + brand/font assets by uuid
  references, so the mirror copy is **not runnable standalone** — the source
  of truth for review is the readable `src/` chunks below. Binary assets
  (fonts, brand PNGs) are not mirrored.
- `src/01_data.js … 12_root.js` (+ `05b_cards.js`) — the revision's source
  chunks, readable JSX/JS (loaded at runtime via Babel in the original),
  renamed from their upload uuids in load order. Mapping:
  - `01_data.js` — `DMA` mock data layer (schema contract for the rebuild)
  - `02_components_a.js` — utilities / SVG icons / layout primitives
  - `03_components_b.js` — Sidebar, TopBar, ClientShell, **ClientBar**, banners,
    audience toggle, run-selector, search/notifications/settings popovers
  - `04_components_c.js` — EvidenceDrawer (per-E-ID scoping), **InsightModal**,
    IntelligencePanel, RecommendationModal, NewRunModal, ToastStack
  - `05_pages_a.js` — Login, DashboardHome, EntityDirectory
  - `05b_cards.js` — **NEW** data-driven D1 cards (EvidenceTier, Sentiment,
    FinancialTrajectory, CoverageByPillar, CeilingEstimate) with
    `data-source` bindings + `// SOURCE:` comments per card
  - `06_pages_b.js` — D1 ClientOverview (refined; deep Why-Now strip +
    SCQA E-ID chips + Leadership/ThoughtLeadership panels), D2 ClientInsights
  - `07_pages_c.js` — D3 ClientHeatmap (refactored: modes/zoom/
    SynthesisDrawer/FocusAreaView/ValueChainView/CustomizableKpiStrip)
  - `08_pages_d.js` — D4 ClientPlatform (StairstepCurve, TransformationRoadmap,
    Chevron/StepCurve/CustomerImpact views)
  - `09_pages_e.js` — D5 Context, D6 Health, D7 TechStack(+detail), D8 Runs
  - `10_pages_f.js` — Alerts, Prospecting, Admin, ImportPage, ImportAuditPage,
    LiveImportStream
  - `11_tweaks.js`, `12_root.js` — tweaks panel + app root/router
- `tokens.css` — design tokens (identical to `frontend/styles/tokens.css`;
  unchanged in the 2026-07 revision).
- `app.css` — the revision's canonical app-shell sheet (adds
  `.cards-grid-2/-3`, `.subcap-row`, `.import-stages`, `.import-log`, richer
  topbar crumbs, mobile import-pipeline rules over the 2026-06 sheet). The
  rebuilt `frontend/src/` pages target these canonical classes.
