/**
 * G12.RESPONSIVE.SUITE — STANDALONE-bundle variant.
 *
 * Captures screenshots at 7 breakpoints against the deterministic
 * standalone bundle (`dist-standalone/index.html`) which has
 * `frontend/src/mock/data.ts` baked in. Per ADR 0011 the standalone
 * IS the live AE surface; baselines from this config are the
 * canonical regression target for the chrome / layout / typography
 * contract.
 *
 * No backend, no loginAs, no Vite proxy — pure static-HTML rendering.
 * Routes that require auth render their auth-gated empty state (which
 * is still a deterministic visual artifact).
 *
 * To regenerate baselines:
 *   pnpm run build:standalone
 *   pnpm test:visual:standalone:update
 *   git add e2e/visual/__snapshots__/ && git commit
 */
import { expect, test } from "@playwright/test";

import { VISUAL_ROUTES } from "./routes";

// Freeze the JS clock so "X minutes ago" chips are deterministic.
const FROZEN_ISO = "2026-01-15T09:00:00.000Z";

for (const route of VISUAL_ROUTES) {
  test(`standalone · ${route.name}`, async ({ page }) => {
    await page.clock.install({ time: new Date(FROZEN_ISO) });

    // Determinism guard (2026-06-10): index.html loads DM Sans + DM Mono
    // from fonts.googleapis/gstatic for the LIVE surface. A network
    // webfont makes this BLOCKING contract non-deterministic — it would
    // pass or fail depending on whether the CI build (or the operator's
    // machine) has egress to Google Fonts at capture time. Block those
    // requests so the standalone always renders with the consistent
    // jammy-container fallback stack; the contract still guards layout,
    // chrome, spacing, colour and component structure. Production users
    // are unaffected (the live index.html link is untouched).
    await page.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());

    // Standalone uses hash routing on a static HTML — navigate directly.
    // The bundle ignores BACKEND_URL and reads from inlined mock data.
    await page.goto(`/#${route.path}`);

    // Wait for the content signal, falling back to the generic main
    // selector since standalone may not have all data-testid attrs.
    const waitSelector =
      route.waitFor ?? '[data-testid="main-content"], main, #app > *, .sidebar';
    try {
      await page.waitForSelector(waitSelector, { timeout: 10_000 });
    } catch {
      // Some routes (e.g. /login) render different markup in standalone
      // (no real OAuth button). Fall back to "body has any content".
      await page.waitForSelector("body > *", { timeout: 5_000 });
    }

    // Extra pause for Recharts (deterministic on standalone — mock data
    // produces identical charts every render).
    await page.waitForTimeout(300);

    // Mask selectors that may differ across runs even with frozen
    // clock (e.g. random IDs in React's auto-generated keys).
    const masks = (route.maskSelectors ?? []).map((sel) =>
      page.locator(sel),
    );

    await expect(page).toHaveScreenshot(`standalone-${route.name}.png`, {
      mask: masks,
      fullPage: true,
    });
  });
}
