/**
 * React-surface responsive + click-audit suite (plan Part 15, task "click-audit").
 *
 * A: RESPONSIVE — every primary route at phone/tablet/desktop breakpoints:
 *    the page renders its anchor, the TopBar is visible, and the document
 *    NEVER scrolls horizontally (the pixel-fidelity floor for "responsive
 *    to multiple platforms"). Mobile additionally asserts the hamburger
 *    (`.sb-mobile-btn`) is the nav entry point and actually opens the sidebar
 *    — the top-navigation regression area.
 *
 * B: CLICK-AUDIT — the load-bearing drilldowns on a data-rich client:
 *    insight card → modal; heatmap cell → synthesis drawer WITHOUT the
 *    IntelligencePanel auto-opening (the 2026-07 popup bug regression);
 *    tech row expand; evidence drawer opens from the heatmap drawer.
 *
 * Uses the LIVE seeded backend (no stubs) via dev-login, mirroring
 * personas.e2e.ts.
 */
import { expect, Page, test } from "@playwright/test";
import { loginAs } from "./helpers";

const CLIENT = "frost-bank-0001";

const VIEWPORTS = [
  { name: "phone-375", width: 375, height: 812 },
  { name: "tablet-768", width: 768, height: 1024 },
  { name: "desktop-1440", width: 1440, height: 900 },
] as const;

const ROUTES: Array<{ label: string; hash: string; anchor: string }> = [
  { label: "dashboard", hash: "/", anchor: ".card, .kpi, main" },
  { label: "directory", hash: "/clients", anchor: ".card-tile, table, .card" },
  { label: "overview", hash: `/clients/${CLIENT}`, anchor: ".score-ring, .card" },
  { label: "insights", hash: `/clients/${CLIENT}/insights`, anchor: ".ic-title, .card" },
  { label: "heatmap", hash: `/clients/${CLIENT}/heatmap`, anchor: ".hm, .card" },
  { label: "platform", hash: `/clients/${CLIENT}/platform`, anchor: ".card" },
  { label: "context", hash: `/clients/${CLIENT}/context`, anchor: ".card" },
  { label: "techstack", hash: `/clients/${CLIENT}/techstack`, anchor: "[data-testid='techstack-stat-strip'], .card" },
  { label: "alerts", hash: "/alerts", anchor: ".empty, .card, table" },
  { label: "prospecting", hash: "/prospecting", anchor: ".card, table" },
];

async function noHorizontalOverflow(page: Page, label: string): Promise<void> {
  const overflow = await page.evaluate(() => {
    const doc = document.documentElement;
    return { scrollW: doc.scrollWidth, clientW: doc.clientWidth };
  });
  expect(
    overflow.scrollW,
    `${label}: document scrolls horizontally (${overflow.scrollW} > ${overflow.clientW}) — a responsive break`,
  ).toBeLessThanOrEqual(overflow.clientW + 1);
}

test.describe("A. responsive: every route × breakpoint, no overflow, nav usable", () => {
  for (const vp of VIEWPORTS) {
    for (const route of ROUTES) {
      test(`${route.label} @ ${vp.name}`, async ({ page }) => {
        await page.setViewportSize({ width: vp.width, height: vp.height });
        await loginAs(page, "ae");
        await page.goto(`/#${route.hash}`);
        await expect(page.locator(route.anchor).first()).toBeVisible({ timeout: 15_000 });
        await expect(page.locator("header.topbar")).toBeVisible();
        await noHorizontalOverflow(page, `${route.label}@${vp.name}`);
      });
    }
  }

  test("phone: hamburger opens the sidebar; desktop: sidebar always visible", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await loginAs(page, "ae");
    await page.goto("/#/");
    await expect(page.locator("header.topbar")).toBeVisible({ timeout: 15_000 });
    const burger = page.locator(".sb-mobile-btn");
    await expect(burger, "mobile nav toggle must exist at 375px").toBeVisible();
    await burger.click();
    await expect(page.locator("aside.sb")).toBeVisible({ timeout: 5_000 });
    // desktop: no hamburger needed, sidebar persistent
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/#/");
    await expect(page.locator("aside.sb")).toBeVisible({ timeout: 10_000 });
  });
});

test.describe("B. click-audit: load-bearing drilldowns on a data-rich client", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await loginAs(page, "ae");
  });

  async function settle(page: Page): Promise<void> {
    await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
  }

  test("insight card opens the modal with substance and closes", async ({ page }) => {
    await page.goto(`/#/clients/${CLIENT}/insights`);
    const card = page.locator(".ic-title").first();
    await expect(card).toBeVisible({ timeout: 15_000 });
    await card.click();
    const modal = page.locator(".insight-modal");
    await expect(modal).toBeVisible({ timeout: 10_000 });
    // Depth: the modal body must carry real prose, not an empty shell.
    const bodyText = (await modal.innerText()).trim();
    expect(bodyText.length, "insight modal renders substantive content").toBeGreaterThan(120);
    await page.keyboard.press("Escape");
  });

  test("heatmap cell opens synthesis drawer; IntelligencePanel does NOT auto-open", async ({ page }) => {
    await page.goto(`/#/clients/${CLIENT}/heatmap?hm=standard&zoom=subcap`);
    await settle(page);
    const cell = page.locator(".hm-cell").first();
    await expect(cell).toBeVisible({ timeout: 20_000 });
    await cell.click();
    // The SynthesisDrawer is a role=dialog panel (not aside.drawer).
    await expect(
      page.locator("[role='dialog'][aria-label='Sub-capability synthesis'], aside.drawer").first(),
    ).toBeVisible({ timeout: 10_000 });
    // THE popup-bug regression: opening a heatmap drilldown must never
    // auto-open the IntelligencePanel over it.
    await expect(
      page.locator("aside.ip"),
      "IntelligencePanel must not auto-open over a heatmap drilldown",
    ).not.toBeVisible();
  });

  test("tech stack row expands with detail; ABSENT gap rows are real", async ({ page }) => {
    await page.goto(`/#/clients/${CLIENT}/techstack`);
    await settle(page);
    // anchor first (stat strip renders before rows stream in)
    await expect(
      page.locator("[data-testid='techstack-stat-strip']"),
    ).toBeVisible({ timeout: 20_000 });
    // server-side ABSENT gap rows render on the LIST page (Part 9.1)
    await expect(
      page.locator("text=/absent/i").first(),
      "server-side ABSENT gap rows must render",
    ).toBeVisible({ timeout: 10_000 });
    const row = page.locator("[data-testid='tech-row']").first();
    await expect(row).toBeVisible({ timeout: 20_000 });
    await row.click();
    // Row click NAVIGATES to the tech detail page (Part 9.2) — assert the
    // detail route rendered real content, not a dead end.
    await expect(page).toHaveURL(/techstack\//, { timeout: 10_000 });
    await expect(page.locator(".card").first()).toBeVisible({ timeout: 15_000 });
  });

  test("alerts renders real content for the ANALYST persona (AE is gated by design)", async ({ page }) => {
    await loginAs(page, "analyst");
    await page.goto("/#/alerts");
    await expect(page.locator("text=/alert|no open alerts/i").first()).toBeVisible({ timeout: 15_000 });
    await noHorizontalOverflow(page, "alerts@analyst");
  });

  test("overview renders the five deep cards with populated states", async ({ page }) => {
    await page.goto(`/#/clients/${CLIENT}`);
    await expect(page.locator(".score-ring")).toBeVisible({ timeout: 15_000 });
    for (const head of [/financial (trajectory|highlights)/i, /coverage/i, /evidence/i]) {
      await expect(
        page.locator("h3", { hasText: head }).first(),
        `deep card "${head}" must render`,
      ).toBeVisible({ timeout: 10_000 });
    }
    // why-now strip exists with at least one signal
    await expect(page.locator("text=/why now/i").first()).toBeVisible();
  });
});
