import { defineConfig } from "@playwright/test";

/**
 * Visual regression — STANDALONE bundle variant.
 *
 * Captures baselines against `dist-standalone/index.html` which has
 * `frontend/src/mock/data.ts` baked in (no backend dependency, no Vite
 * proxy). Per ADR 0011 the standalone IS the live AE surface; this
 * config is the canonical visual-regression source of truth.
 *
 * The live-backend variant (`playwright.visual.config.ts`) is still
 * useful for end-to-end smoke once a sidecar backend is wired in CI
 * — but baselines committed there represent live-data state and drift
 * with every fixture change. The standalone baselines are
 * deterministic (mock data is checked in) so they're the right
 * regression target for the chrome / layout / typography contract.
 *
 * Prerequisites:
 *   pnpm run build:standalone        (produces dist-standalone/index.html)
 *   pnpm exec playwright install --with-deps chromium
 *
 * Usage:
 *   pnpm test:visual:standalone           → compare against baselines
 *   pnpm test:visual:standalone:update    → regenerate (commit the diff!)
 *
 * The 7 breakpoints exactly mirror `playwright.visual.config.ts` — the
 * single source of truth is the app.css media-query ladder.
 */
export default defineConfig({
  testDir: "./e2e/visual",
  testMatch: "**/standalone-responsive.visual.ts",
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 4 : 1,
  reporter: process.env.CI
    ? [["github"], ["html", { open: "never" }]]
    : "list",

  expect: {
    // 2% pixel diff tolerance (Recharts canvases produce minor jitter).
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.02,
      animations: "disabled",
    },
  },

  use: {
    // Standalone is served by a static HTTP server (see webServer below)
    // on port 8081. The bundle uses hash routing so the URL stays
    // `http://localhost:8081/#/...`.
    baseURL: "http://localhost:8081",
    screenshot: "on",
    video: "off",
    trace: "off",
    actionTimeout: 15_000,
    navigationTimeout: 20_000,
  },

  projects: [
    { name: "standalone-1920", use: { viewport: { width: 1920, height: 1080 } } },
    { name: "standalone-1440", use: { viewport: { width: 1440, height: 900 } } },
    { name: "standalone-1280", use: { viewport: { width: 1280, height: 800 } } },
    { name: "standalone-1180", use: { viewport: { width: 1180, height: 820 } } },
    { name: "standalone-980",  use: { viewport: { width: 980,  height: 768 } } },
    { name: "standalone-900",  use: { viewport: { width: 900,  height: 768 } } },
    { name: "standalone-760",  use: { viewport: { width: 760,  height: 1024 } } },
  ],

  webServer: [
    {
      // Serve `dist-standalone/` from port 8081 via a stubbing wrapper
      // that returns 401 (not 404) on /api/v1/auth/me and {} on other
      // /api/v1/* paths. The standalone bundle is a self-contained HTML
      // with inlined mock data — there's no real backend during these
      // tests — but the React app still hits the auth/me endpoint on
      // mount. Vanilla `python3 -m http.server` would log a wall of
      // 404 entries that look like deployment failures in the cloudbuild
      // log; the wrapper mirrors the actual backend's no-session reply
      // so the log stays clean and the rendered UI matches production.
      command: "python3 dist-standalone-server.py 8081 dist-standalone",
      port: 8081,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
  ],
});
