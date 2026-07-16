# DMA Insights — Frontend Fidelity Audit & Rebuild Plan

**Date:** 2026-06-18
**Author:** QA engineering audit
**Scope:** Production React/TS surface (`frontend/src/` → `dist/`) vs. the uploaded prototype
(`DMA Insights · Standalone.html` + the modular `react_src/` source)
**Status:** AUDIT + PLAN. No application code has been changed by this document.

---

## 0. TL;DR

The deployed frontend is **functionally** wired to the backend (TanStack Query hooks, auth,
SSE, startup-data hydration all work), and the *deep* client tabs are actually **structurally
close** to the prototype. But the app **does not read as the prototype** on deployment, for four
compounding reasons:

1. **Parallel reimplementation drift.** There are *three* hand-derived copies of the prototype in
   the repo (`react_src/` reference, `frontend/src/` production, `frontend/standalone-src/` demo).
   Each was re-typed by a different pass rather than ported, so they diverge — most badly in the
   **overlays** (drawers/modals/intelligence panel), which are the highest-traffic interactions.
2. **Class-vocabulary divergence.** `app.css` grew from the prototype's **1,378 lines → 2,156**.
   Most of that is additive, but a few surfaces adopted a *parallel* vocabulary
   (`.page-body`, `.admin-table`, `.modal-backdrop`) and some components swapped the prototype's
   exact classes for ad-hoc inline styles (evidence tier chips, `.ip-foot`). Result: the same
   screen rendered with subtly-to-substantially different chrome.
3. **Placeholder glyphs instead of the icon set.** The Dashboard renders raw unicode
   (`◯ ● ⚠ ◈`) where the prototype uses `<Icon name="users|bell|warn|drive">`. Small, but it
   instantly reads as "not the real design."
4. **Sparse deploy data.** The committed `startup-data` backfill is *real but thin*
   (`assessment_date: null`, no `oss`/open-alerts/HQ/freshness, `data_source: MANUAL_BACKFILL`).
   Structurally-faithful pages therefore render **visually barren** against the lush prototype
   mock — several cards hard-render `—`.

**The fix is a presentation rebuild against the prototype's canonical `app.css` + markup, keeping
the existing data hooks** — plus a decision on how to populate the "starter" deploy data so the
pages actually look populated (see §6).

---

## 1. How the deployed frontend actually works

```
frontend/src/*.tsx  ──(vite build)──►  frontend/dist/  ──►  nginx (Cloud Run)
        │                                    ▲
        │  index.html → entry.tsx → App.tsx  │  copyStartupDataPlugin bakes
        │  hash router → pages               │  apps/dma-insights/startup-data
        │                                    │  into dist/startup-data/…
        └── lib/queries.ts (TanStack) ──► live API  ──► (fallback) startup-data JSON
```

- **Production surface = `frontend/dist/`** (ADR 0016). The standalone single-file build is a
  stakeholder demo only.
- On a fresh deploy the **committed `startup-data` JSON pack is the source of truth**
  (`lib/startup-pages.ts` → `snapshotOrApi`, per the 2026-06-18 operator mandate). 94 clients ×
  10 surfaces are baked into the image; the live API only overrides when warm.
- So "**the starter pages that load on deployment**" = the React/TS pages rendered from the
  baked `startup-data` snapshot. They must *both* match the prototype's look **and** survive the
  thinness of the backfilled data.

---

## 2. Root-cause detail

### 2.1 Two parallel modal/CSS systems
`app.css` styles **both** `.modal-mask` (line 615, the prototype's) **and** `.modal-backdrop`
(line 1819, the divergent one). The generic `Modal.tsx` renders `.modal-backdrop` + `.modal-head`
+ `.modal-title` + `.modal-body` — *not* the prototype's `.modal-mask` + tabbed `.modal` chrome.
Every overlay routed through `<Modal>` (Insight, Recommendation) therefore loses the prototype
look.

### 2.2 Icon set bypassed on the Dashboard
`DashboardPage.tsx` lines 240/267/298/329 emit `◯`, `●`, `⚠`, `◈` literals. Prototype
`global-pages.jsx` uses `<Icon name="users">`, `<Icon name="bell">`, `<Icon name="warn">`,
`<Icon name="drive">`. The `Icon` component exists and is used elsewhere — this is a regression,
not a missing capability.

### 2.3 Sparse startup-data vs lush mock
Prototype `DMA.ENTITIES` give every card: `overall`, `pillar_scores`, `oss` (5 platform install
scores), `open_alerts`, `in_progress` batch state, `hq`, `subvertical`, `assessment_date`
(freshness dot). Real `startup-data` `overview.json`/`scores.json` give: `name`, `overall`,
`pillars{P1..P4}`, `subvertical` — and **null** `assessment_date`, **no** `oss`, **no**
`open_alerts`, **no** `hq`. The faithful card markup is there; the data to fill it is not.

---

## 3. Per-surface gap report

Severity: **[BLOCKER]** breaks the look/flow · **[MAJOR]** clearly off-prototype ·
**[MINOR]** cosmetic / acceptable.

| Surface | Fidelity | Top gaps |
|---|---|---|
| **Login** | High | Faithful split hero; verify illustration asset path + Google button. **[MINOR]** |
| **Dashboard** | Medium | Unicode glyphs vs `<Icon>` **[MAJOR]**; System-health card all `—` **[MAJOR]**; sparse entity cards (no OSS/alerts/HQ/freshness) **[MAJOR]** |
| **Directory** | Medium | Grid/table toggle OK; sparse cards (no OSS chip, no freshness, no alert badge) **[MAJOR]**; subvertical filter list must come from real data **[MINOR]** |
| **Client Overview** | High | SCQA + score ring + findings faithful; depends on `overview.json` fields **[MINOR]** |
| **Insights** | Medium | Card grid OK, but **Insight modal uses the generic `<Modal>`** (`.modal-backdrop`) instead of the prototype's tabbed `.modal-mask` (detail/evidence/annotations/linked) **[MAJOR]** |
| **Heatmap** | High (88%) | Lock indicator doubles up (lock + count) **[MAJOR]**; category synthesis drawer parity **[MAJOR]**; rest faithful |
| **Platform** | High (88%) | Gap-to-platform table truncated to 2 cols vs 6 **[MAJOR]**; readiness `.co-org` clobbered by inline style **[MAJOR]**; conv-starter bubbles inline-styled **[MINOR]** |
| **Context** | High (95%) | Faithful; honest empty states for sentiment/acquisitions **[MINOR]** |
| **Health** | High (95%) | Patterns tab is a placeholder **[MAJOR]**; per-subcap diff is aggregate-only **[MINOR]** |
| **TechStack (+detail)** | High (95%) | Faithful 4-layer + drilldown; PARTIAL/ABSENT in legend never render **[MINOR]** |
| **Runs** | High | Faithful table; "Trigger rerun" is a toast stub **[MINOR]** |
| **Alerts** | Medium | **Patterns tab is a placeholder** vs full table **[BLOCKER]**; evidence progress bar added **[MINOR]** |
| **Prospecting** | High | Faithful scorecard; top-platforms shows pillar instead of feature snippet **[MAJOR]** |
| **Admin (home)** | Low | **Drive-crawl + Vertex-budget cards removed** (moved to /admin/import) — home no longer matches prototype **[BLOCKER]**; users table uses `.admin-table` not `.tbl` **[MAJOR]**; no inline invite UI **[MAJOR]** |
| **Import (jobs)** | High | Live counters/log faithful; column labels differ **[MINOR]** |
| **Import audit** | Low | Uses `.page-body` (undefined-ish) + `.admin-table`, **no `.page-head`, no `.g4` stat tiles, no All/Review/Excluded tabs, no Import/Exclude actions** vs prototype **[BLOCKER]** |
| **EvidenceDrawer** | Low | **No `.drawer-mask` backdrop** (can't click-out) **[BLOCKER]**; tier chips use inline color not `.tier-T1..T8` classes **[MAJOR]**; subcap links are text not `.chip` **[MAJOR]**; no Copy-citation foot **[MINOR]** |
| **RecommendationModal** | Low | Generic `<Modal>`; **no impact/evidence/dependencies tabs**, **no DependencyMap (3-col)**, **no `.pbar` before/after uplift** **[BLOCKER]** |
| **IntelligencePanel** | Medium | Faithful body/stream; missing `.ip-foot`; `.ip-tab` moved to `top:140px` (QA fix) **[MINOR]** |
| **Z-index ladder** | Exact | toast 110 · popover 96/98 · evid-drawer 95 · drawer-mask 90 · modal 80 · IP 70 · rail 60 · topbar 50 — all match **[OK]** |

> Corroborated by route-by-route reads of `frontend/src/pages/*` + `components/*` against
> `/tmp/dma_proto/{pages,components}/*.jsx` and `assets/app.css`. `tokens.css` is **byte-identical**
> to the prototype — the color system is intact; the divergence is markup + a CSS superset.

---

## 4. What is already good (keep, don't rebuild)

- `tokens.css` — identical to prototype.
- The data layer: `lib/api.ts`, `lib/queries.ts`, `lib/startup-pages.ts`, auth/SSE/stores.
- Deep client tabs (Overview, Heatmap, Platform, Context, Health, TechStack, Runs) — anatomy and
  class vocabulary already match; they need targeted fixes, not rewrites.
- Z-index/overlay stacking, the run selector, audience toggle, role gating.

---

## 5. Rebuild plan (waves)

Each wave: rebuild markup against the prototype's exact classes, keep the existing hooks, then
**verify** (`tsc --noEmit`, `vitest run`, and a Playwright screenshot diff vs the standalone).
One concern per commit.

**Wave 0 — Foundation (no behavior change)**
- Reconcile `app.css`: make the prototype's 1,378-line sheet canonical; fold the genuinely-needed
  additive rules under a clearly-marked section; **delete the divergent duplicates**
  (`.modal-backdrop` → `.modal-mask`; retire `.page-body`/`.admin-table` once their pages are
  rebuilt). Net: one class vocabulary.
- Add a `compare:prototype` Playwright screenshot harness (the repo already scripts
  `e2e/visual/side-by-side.mjs`) wired to the uploaded standalone as the baseline.

**Wave 1 — Starter flow (deployment-visible first)**
- **Login** (verify asset + button), **Dashboard** (restore `<Icon>`s, real System-health values
  or honest states, fix sparse cards), **Directory**, **Client shell + Overview**.
- Resolve the **starter-data decision** (§6) so these pages render populated.

**Wave 2 — Overlays (highest drift)**
- Rebuild `Modal.tsx` to the prototype `.modal-mask` chrome; restore tabbed **Insight modal**
  (detail/evidence/annotations/linked) and **Recommendation modal** (impact/evidence/dependencies
  + DependencyMap + `.pbar` uplift). Restore `EvidenceDrawer` `.drawer-mask` + `.tier-T1..T8`
  chips + `.chip` subcap links. Add `.ip-foot`.

**Wave 3 — Heatmap + Platform polish**
- Heatmap lock indicator unification + category-synthesis parity. Platform gap table → 6 columns,
  readiness `.co-org` fix, conv-starter bubble classes.

**Wave 4 — Admin cluster**
- Restore Admin **home** Drive-crawl + Vertex-budget cards + users `.tbl` + invite UI. Rebuild
  **Import audit** with `.page-head` + `.g4` tiles + tabs + row actions. Alerts **Patterns** tab.

**Wave 5 — Cutover**
- Delete the now-unreferenced divergent CSS, retire dead `standalone-src` page copies if agreed,
  refresh visual baselines, green `tsc`/`vitest`/build, final screenshot diff.

---

## 6. The one decision that needs your call (data population)

The prototype/standalone you provided shows **lush** data on every starter page. The committed
`startup-data` backfill is **thin**. To make the deployed starter pages *look like the prototype*,
pick one:

- **A — Honest live data.** Keep wiring to the real backfill; pages show real values and honest
  empty states where data is missing. Faithful *structure*, but starter pages will look sparser
  than the prototype until the backfill is enriched.
- **B — Enrich the startup-data pack.** Backfill the showcased fields (`oss`/top-platform,
  `open_alerts`, `hq`, `assessment_date`/freshness, `in_progress`) into the committed JSON so the
  faithful markup renders fully. Most faithful to "match the prototype"; needs a data pass.
- **C — Curated demo seed + live override.** Ship a prototype-matching seed for the 94 starter
  clients that the live API overrides when warm. Best first-impression; clearly a seed.

My recommendation: **B** (enrich the pack) for the starter clients, because the operator mandate
already makes the committed pack the deploy source of truth — enriching it makes the faithful UI
*and* the "use the local backfill JSON" rule agree.

---

## 7. Verification strategy

- `pnpm exec tsc --noEmit` · `pnpm exec vitest run` · `pnpm exec vite build` green per wave.
- Playwright screenshot diff: each rebuilt route vs the corresponding frame in the uploaded
  standalone at 5 widths (the repo already has `playwright.visual*.config.ts`).
- Keep `data-page` / `data-source` markers for E2E + the `__build.txt` SHA stamp for deploy parity.

---

## 8. Effort estimate

| Wave | Surfaces | Rough effort |
|---|---|---|
| 0 Foundation | app.css reconcile + screenshot harness | 0.5 day |
| 1 Starter flow | Login/Dashboard/Directory/Overview + data decision | 1–1.5 days |
| 2 Overlays | Modal/Insight/Recommendation/Evidence/IP | 1.5 days |
| 3 Heatmap/Platform | targeted fixes | 0.5 day |
| 4 Admin cluster | Admin home/Import audit/Patterns | 1 day |
| 5 Cutover | cleanup + baselines | 0.5 day |

Total ≈ **5–5.5 engineering days**, sequenced so the **deployment-visible starter flow lands
first and is verifiable on its own**.
