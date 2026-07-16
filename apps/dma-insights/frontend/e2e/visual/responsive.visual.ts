/**
 * G12.RESPONSIVE.SUITE — Visual regression at 7 breakpoints × 12 routes.
 *
 * Each test logs in as the appropriate persona (via dev-login), navigates
 * to the hash route, waits for the page to stabilise, masks dynamic
 * selectors (timestamps, live counts), and captures a screenshot which
 * Playwright compares against the baseline in `__snapshots__/`.
 *
 * To regenerate baselines after intentional UI changes:
 *   pnpm test:visual:update
 *
 * Failure threshold: 2% max pixel ratio (configured in playwright.visual.config.ts).
 */
import { expect, test } from "@playwright/test";
import { loginAs } from "../helpers";
import { VISUAL_ROUTES } from "./routes";

// Freeze the JS clock so "X minutes ago" chips are deterministic.
// We pick an arbitrary fixed date that doesn't affect business logic.
const FROZEN_ISO = "2026-01-15T09:00:00.000Z";

for (const route of VISUAL_ROUTES) {
  test(`responsive · ${route.name}`, async ({ page }) => {
    // Install a frozen clock before any navigation so all Date.now() calls
    // and setTimeout/setInterval timers are deterministic.
    await page.clock.install({ time: new Date(FROZEN_ISO) });

    if (route.persona) {
      await loginAs(page, route.persona);
    }

    await page.goto(`/#${route.path}`);

    // Wait for the content signal, falling back to the generic main-content check.
    const waitSelector =
      route.waitFor ??
      '[data-testid="main-content"], main, #app > *';
    await page.waitForSelector(waitSelector, { timeout: 15_000 });

    // Extra pause for Recharts renders (ScoreRing, Heatmap, StairstepCurve).
    await page.waitForTimeout(300);

    // Mask selectors that change every render (timestamps, live counts).
    const masks = (route.maskSelectors ?? []).map((sel) =>
      page.locator(sel),
    );

    await expect(page).toHaveScreenshot(`${route.name}.png`, {
      mask: masks,
      // Full-page capture so below-the-fold content is also tested.
      fullPage: true,
    });
  });
}
