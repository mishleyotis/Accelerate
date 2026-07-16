/**
 * PDF export E2E — closes the "PDF export ⏳" outstanding item.
 *
 * Uses Playwright's built-in `page.pdf()` to render every primary
 * client-overview surface as a print-ready PDF. The customer-share
 * deck flow downloads these per client → distributes externally.
 *
 * State-branch contract:
 *   route_renders_clean       → PDF generated, size > 0, asserted
 *   route_blanks_out          → empty PDF (< 5 KB); test fails so
 *                                we catch silent rendering failures
 *   playwright_browser_missing → test SKIPPED with explicit message
 *   not_logged_in             → falls through to login redirect;
 *                                PDF captures the LoginPage as a
 *                                regression signal
 *
 * Test runs only in chromium (PDF generation is chromium-only in
 * Playwright). Output PDFs are NOT committed — they're build
 * artifacts that the deploy pipeline collects.
 *
 * Run locally:
 *   cd frontend && pnpm dev &
 *   cd backend && uvicorn app.main:app --reload --port 8000 &
 *   pnpm exec playwright test pdf-export.e2e.ts --project=chromium
 *
 * Output: artifacts/pdf-export/<route>.pdf
 */
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";

import { loginAs } from "./helpers";

// Routes that should render cleanly to PDF — covers the canonical
// "what an AE shares externally" surface roster.
const PDF_ROUTES = [
  { name: "dashboard",            path: "/",                                       persona: "ae" as const },
  { name: "client-overview",      path: "/clients/fce-001/overview",               persona: "ae" as const },
  { name: "client-insights",      path: "/clients/fce-001/insights",               persona: "ae" as const },
  { name: "client-heatmap",       path: "/clients/fce-001/heatmap",                persona: "ae" as const },
  { name: "client-platform",      path: "/clients/fce-001/platform",               persona: "ae" as const },
];

const ARTIFACTS_DIR = resolve("artifacts/pdf-export");
mkdirSync(ARTIFACTS_DIR, { recursive: true });

test.describe("PDF export · primary client-share surfaces", () => {
  test.skip(({ browserName }) => browserName !== "chromium",
    "PDF generation requires chromium-based browser");

  for (const route of PDF_ROUTES) {
    test(`renders ${route.name} as PDF`, async ({ page }) => {
      await loginAs(page, route.persona);
      await page.goto(`/#${route.path}`);
      // Wait for main content to render so the PDF isn't a blank shell.
      await page.waitForSelector(
        '[data-testid="main-content"], main, #app > *',
        { timeout: 15_000 },
      );
      // Tiny pause for Recharts settle.
      await page.waitForTimeout(800);

      const outputPath = resolve(ARTIFACTS_DIR, `${route.name}.pdf`);
      const pdfBytes = await page.pdf({
        path: outputPath,
        format: "A4",
        printBackground: true,
        margin: { top: "20mm", bottom: "20mm", left: "15mm", right: "15mm" },
      });

      // Non-empty PDF — catches silent rendering failures where the
      // page navigates but the print-target is a blank shell.
      expect(pdfBytes.length).toBeGreaterThan(5_000);
    });
  }
});
