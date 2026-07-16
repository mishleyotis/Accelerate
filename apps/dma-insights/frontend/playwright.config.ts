import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright E2E config — persona golden-path tests against the
 * React/Vite production surface (per ADR 0016, supersedes ADR 0011).
 *
 * Runs against a live dev server (frontend on :5173, backend on :8000).
 * Backend must be in env=local so /api/v1/auth/dev-login is active.
 *
 * For CI (Cloud Build stage 7), the servers are started in the build step
 * before running `pnpm test:e2e`. Locally:
 *   cd frontend && pnpm dev &
 *   cd backend && uvicorn app.main:app --reload --port 8000 &
 *   pnpm test:e2e
 *
 * 2026-05-29 QA audit P1 (Fix G — E2E split): this BLOCKING suite now
 * covers ONLY the React/Vite production surface. The standalone-
 * targeted tests (`standalone-*.e2e.ts`, `responsive-standalone-
 * routes.e2e.ts`, `a11y-drawers.e2e.ts`, `xss-regressions.e2e.ts`)
 * moved to `playwright.standalone.config.ts` + `pnpm test:e2e:standalone`
 * (advisory/demo-only). Mixing them broke against pnpm dev (which
 * serves the React tree): standalone tests asserted on the standalone
 * surface that wasn't being served, so fixing one suite kept breaking
 * the other. The 4 standalone tests stay in the repo for the demo
 * build; they can be promoted back here when ported to the React shell.
 *
 * Visual regression tests (G12.RESPONSIVE.SUITE / G04.CHROME.RESPONSIVE)
 * live in playwright.visual.config.ts and use a separate `pnpm test:visual`.
 */
export default defineConfig({
  testDir: "./e2e",
  // React/Vite-only blocking suite (allowlist — a new standalone-*.e2e.ts
  // file silently dropped into ./e2e can't accidentally re-mix suites).
  testMatch: [
    "personas.e2e.ts",
    "role-tampering.e2e.ts",
    "pdf-export.e2e.ts",
    // Plan Part 15 click-audit + responsive sweep on the PRODUCTION React
    // surface (phone/tablet/desktop, no-overflow, drilldowns, IP no-auto-open).
    "react-clickaudit.e2e.ts",
  ],
  timeout: 30_000,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",

  use: {
    baseURL: "http://localhost:5173",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    trace: "on-first-retry",
    // Disable animations for deterministic screenshots
    actionTimeout: 15_000,
    navigationTimeout: 20_000,
  },

  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        // Managed-env preinstalled browser (PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD):
        // honour PW_CHROMIUM_PATH when the pinned playwright build doesn't
        // match the baked browser revision. Unset locally → default resolution.
        //
        // --disable-dev-shm-usage: in containers /dev/shm defaults to 64MB
        // and chromium SIGSEGVs under it intermittently (the 2026-07-05
        // build's headless-shell exit-148 flakes). --disable-gpu avoids the
        // no-GPU-device fallback probe in headless CI.
        launchOptions: {
          args: ["--disable-dev-shm-usage", "--disable-gpu"],
          ...(process.env.PW_CHROMIUM_PATH
            ? { executablePath: process.env.PW_CHROMIUM_PATH }
            : {}),
        },
      },
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
