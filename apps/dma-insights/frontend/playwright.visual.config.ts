import { defineConfig } from "@playwright/test";

/**
 * Playwright visual regression config — G12.RESPONSIVE.SUITE / G04.CHROME.RESPONSIVE.
 *
 * Captures screenshots at 7 breakpoints for every primary route and compares
 * against committed baseline PNGs in `e2e/visual/__snapshots__/`.
 *
 * Usage:
 *   pnpm test:visual           → compare against existing baselines
 *   pnpm test:visual:update    → regenerate baselines (commit the diff!)
 *
 * Prerequisites:
 *   - Frontend dev server running on :5173 (started automatically below)
 *   - Backend running on :8000 with env=local
 *   - `pnpm exec playwright install --with-deps` run once
 *
 * Breakpoints (from app.css contract):
 *   1920 — desktop XL (3-col + pinned IntelligencePanel)
 *   1440 — desktop L  (3-col, panel collapses to icon strip)
 *   1280 — desktop M  (2-col, panel becomes drawer)
 *   1180 — tablet landscape (2-col, sidebar icon rail)
 *    980 — tablet portrait  (1-col, sidebar overlay)
 *    900 — small tablet     (1-col, KPI strip scrolls)
 *    760 — mobile degraded  ("Best viewed on tablet+" banner)
 */
export default defineConfig({
  testDir: "./e2e/visual",
  // Only the live-backend variant. The standalone-targeted file
  // (`standalone-responsive.visual.ts`) lives in
  // `playwright.visual.standalone.config.ts` against the static demo
  // build — keeping the two suites separate prevents them from
  // clobbering each other's baselines (different baseURLs, different
  // auth, different fixture state).
  testMatch: "responsive.visual.ts",
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 4 : 1,
  reporter: process.env.CI
    ? [["github"], ["html", { open: "never" }]]
    : "list",

  expect: {
    // 2% pixel diff tolerance (Recharts canvases produce minor jitter)
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.02,
      animations: "disabled",
    },
  },

  use: {
    baseURL: "http://localhost:5173",
    screenshot: "on",
    video: "off",
    trace: "off",
    actionTimeout: 15_000,
    navigationTimeout: 20_000,
    // Freeze time so "X minutes ago" chips are deterministic
    // javaScriptEnabled: true — default, no change needed
  },

  projects: [
    {
      name: "responsive-1920",
      use: { viewport: { width: 1920, height: 1080 } },
    },
    {
      name: "responsive-1440",
      use: { viewport: { width: 1440, height: 900 } },
    },
    {
      name: "responsive-1280",
      use: { viewport: { width: 1280, height: 800 } },
    },
    {
      name: "responsive-1180",
      use: { viewport: { width: 1180, height: 820 } },
    },
    {
      name: "responsive-980",
      use: { viewport: { width: 980, height: 768 } },
    },
    {
      name: "responsive-900",
      use: { viewport: { width: 900, height: 768 } },
    },
    {
      name: "responsive-760",
      use: { viewport: { width: 760, height: 1024 } },
    },
  ],

  webServer: [
    {
      command: "pnpm dev",
      port: 5173,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
  ],
});
