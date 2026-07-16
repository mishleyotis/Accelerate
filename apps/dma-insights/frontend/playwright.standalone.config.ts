import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright E2E config — standalone (demo-build) golden-path tests.
 *
 * Per ADR 0016, the standalone bundle at `frontend/standalone-src/` is
 * a stakeholder-demo / wireframe-guide artifact, not the production
 * AE-facing surface. The tests in this config exercise that demo
 * build's runtime contract (auth hydration, role tampering at the
 * window.DMA_USER level, hash-routed standalone pages, XSS in the
 * standalone surface).
 *
 * This config is ADVISORY — Cloud Build does NOT block on it. The
 * blocking React suite lives at `playwright.config.ts`. See the
 * header there for the 2026-05-29 QA-audit Fix-G rationale.
 *
 * Run locally:
 *   cd frontend && pnpm run build:standalone   # produces dist-standalone/
 *   cd frontend && pnpm test:e2e:standalone
 *
 * The standalone bundle is self-contained (inlined mock data + vendored
 * React), so no backend is required for the standalone surface itself.
 * Tests that exercise auth still call /api/v1/auth/dev-login through
 * the configured backend URL.
 */
export default defineConfig({
  testDir: "./e2e",
  // Allowlist — only the standalone-targeted tests run here.
  testMatch: [
    "standalone-auth-hydration.e2e.ts",
    "responsive-standalone-routes.e2e.ts",
    "a11y-drawers.e2e.ts",
    "xss-regressions.e2e.ts",
  ],
  timeout: 30_000,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",

  use: {
    baseURL: "http://localhost:5173",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    trace: "on-first-retry",
    actionTimeout: 15_000,
    navigationTimeout: 20_000,
  },

  projects: [
    {
      name: "chromium-standalone",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  webServer: [
    {
      // Reuses pnpm dev as the standalone source files are served via
      // the same Vite dev server's `/standalone-src/` path. For the
      // built artifact, operators run `pnpm run preview` against
      // `dist-standalone/` instead.
      command: "pnpm dev",
      port: 5173,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
  ],
});
