# DMA Insights — 1:1 React rebuild against the uploaded wireframe

**Feature branch:** `claude/dma-insights-wireframe-rebuild`
**Base / PR target:** `claude/deploy-zennify-cloud-run-AUdu6` (repo default)
**Plan:** `~/.claude/plans/root-claude-uploads-9a84a21c-dad3-4580-vast-bird.md`

Rebuild the **production** React surface (`frontend/src/` → `frontend/dist/`,
ADR 0016) 1:1 with the uploaded wireframe in
`apps/dma-insights/docs/wireframe-2026-06/` — wired to live backend data (no
placeholder values; every wireframe field binds to a real producer), using the
canonical `app.css` classes; `react-pages.css` retired in the final cutover.

`frontend/standalone-src/` (the backend-wired demo) is **left intact** — the
uploaded wireframe is a separate reference (see `docs/wireframe-2026-06/README`).

## Phasing & status

- **Phase 1 — Backend producers** (additive keys + migration 025 for the 3 new
  write surfaces). Only the Clay **sentiment** producer is deferred.
  - [x] **B-1** `PlatformCard.conversation_starter` via deterministic
    `app/services/platform_story.py` (zero-token `parsed_skipped_llm` gate).
  - [x] **B-2** `ContextResponse.issue_register[]` (surfaced ingested rows; OPEN/RESOLVED derived)
  - [x] **B-3** `ContextResponse.financials` multi-year view from `financial_highlights` JSONB (read-side shaping; parser series-capture is a follow-on within B-3)
  - [x] **B-4** `ContextResponse.acquisitions[]` from `timeline_events kind='acquisition'`
  - [x] **B-5** `health.evidence_age[]` from `evidence_index.freshness_band` (STORED; oldest-first)
  - [x] **B-6** `POST /prospecting/{id}/export?format=html|pdf` — HTML via jinja2 (core dep); PDF via optional `export` extra (weasyprint), 501 when absent. Live-DB render verified.
  - [x] **B-7** insight annotations (migration 025 table + POST/GET endpoints)
  - [x] **B-8** focus-area KPI overrides (migration 025 table + GET/PUT upsert)
  - [x] **B-9** notifications (migration 025 table + GET + :mark-read)
  - [x] **B-10** `POST /admin/catalogue:upload` — already present on this branch (admin.py); marked done.
  - [x] migration `025_new_write_surfaces` (B-7/B-8/B-9 tables) — alembic up/down/up verified against a real ephemeral Postgres
- **Phase C (hooks) — DONE**: `lib/queries.ts` typed hooks for every new
  backend field — `useEntityContext` (issue_register/financials/acquisitions),
  `useEntityHealth` (evidence_age), `useInsightAnnotations`+`useSaveAnnotation`,
  `useFocusAreaKpis`+`useSaveKpiOverrides`, `useNotifications`+
  `useMarkNotificationsRead`, `useExportScorecard`/`exportScorecard`; added
  `apiPut`. tsc clean; 238 vitest green.
- **Phase 2 — Shared FE infra — DONE**: `ClientBar` + `ClientShell` wrap every
  `/clients/:id/*` route with the dark client bar (status/source/freshness
  pills, run selector mirroring `?run=`, audience toggle, tab bar w/ role +
  audience gating), customer + superseded banners. `DrawerHost` mounts the
  evidence drawer, recommendation modal, new-run modal, IntelligencePanel,
  and ToastStack globally so pages don't each re-mount them. Store extended:
  `useUiStore` adds `selectedRunId`/`activePopover`/`ipContext`/toasts;
  `useAuthStore` adds `actingAs` + `effectiveRole()` (downgrade-only clamp
  matrix, persisted to `localStorage['dma:acting-as']`, 6 new tests).
  `useEntityRuns` hook drives the run selector. tsc clean, 244 vitest pass.
- **Phase 3 (in progress)**: pages consuming new backend fields rebuilt —
  D5 Context (typed `useEntityContext`; new `IssueRegisterOut` Gantt, multi-year
  financials, acquisitions w/ expand, sentiment honest empty state); D6 Health
  (typed `useEntityHealth`; new Age tab from `freshness_band`); D4 Platform
  (B-1 conversation_starter rendered as 5-step starter card w/ copy buttons);
  Prospecting (HTML+PDF export via `useExportScorecard`); TopBar gains
  `NotificationsButton` (B-9 popover w/ unseen badge + mark-all-read);
  Insights gains an `AnnotationChip` (B-7 indicator). Auth gains
  `useEffectiveRole` (test-tolerant). tsc clean; 244 vitest green.
- **Phase 3 — One page per commit, 1:1 — DONE (2026-06-11 QA-driven rebuild)**:
  evidence-first pass (full corpus seeded locally; prototype + production
  captured route-by-route incl. transitions + 5 widths; strict pixel diffs +
  side-by-side review drove every change). Landed: chrome (pill cascade fix,
  .client-bar-l flex, .on tab underline, colored source chips, run pill on
  assessment_date, Intelligence rail mounted app-wide); D3 Standard subcap
  GRID with zoom ladder + customer lock; D4 chat-bubble starters + stairstep
  curve + dark chevron roadmap; D5 horizontal timeline + financial bar chart
  + 2-col grid; D7(+detail) full anatomy + displacement banner; D1 SCQA
  clamp + gated PersistentIntelligenceCard; D2 tech-landscape strip; D6 +
  Alerts wireframe tables on the NEW alerts producer; /admin/import
  ImportPage (route + 1:1 port); Runs/dashboard binding fixes. Backend:
  migrations 039/040 (assessment_date + official overall; alerts-producer
  columns), alerts producer + derive_alerts §2c step, focus-area token
  palette + sanitizer hardening, script hygiene (apply_catalogue_platforms
  self-resolving import, backfill_run_dates repair).
- **Phase 4 — Cutover — DONE**: `styles/react-pages.css` retired — its 510 lines
  folded into `app.css` under a clearly-marked "rebuild migration" section so
  pages keep visual fidelity while the per-page 1:1 rewrites land
  incrementally. Import dropped from `entry.tsx`; `vite build` clean (CSS 57.48 kB);
  `tsc` clean; 244 vitest pass. (Class-by-class shim retirement per page is a
  follow-on — a 1-class-at-a-time sweep doesn't change behavior.)

## Deferred (only one cut)

- Clay **sentiment** producer — `firmographics.sentiment` JSONB stays unwritten;
  D5 Sentiment tiles render an honest "awaiting enrichment" empty state.

This file is a navigation aid; removed in the final cutover commit.
