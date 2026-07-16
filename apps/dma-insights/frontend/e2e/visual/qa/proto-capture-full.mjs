// Comprehensive prototype capture: all routes, transition states, responsive widths.
// Run from frontend/ so @playwright/test resolves. Output: /tmp/proto-shots/
import { createRequire } from "node:module";
const require = createRequire("/home/user/Accelerate/apps/dma-insights/frontend/package.json");
const { chromium } = require("@playwright/test");
import fs from "node:fs";

const OUT = "/tmp/proto-shots";
fs.mkdirSync(OUT, { recursive: true });
const URL = "http://localhost:8082/";

async function boot(page) {
  await page.goto(URL, { waitUntil: "domcontentloaded" });
  await page.getByText(/Continue with Google/i).first().waitFor({ timeout: 60000 });
}
async function login(page) {
  await page.getByText(/Continue with Google/i).first().click();
  await page.waitForTimeout(1200);
}
async function nav(page, hash) {
  await page.evaluate(h => { location.hash = h; }, hash);
  await page.waitForTimeout(900);
}
async function shot(page, name) {
  await page.screenshot({ path: `${OUT}/proto-${name}.png`, fullPage: true });
  console.log("✓", name);
}
async function closeOverlays(page) {
  await page.keyboard.press("Escape").catch(() => {});
  const mask = page.locator(".modal-mask, .drawer-mask").first();
  if (await mask.isVisible().catch(() => false)) await mask.click({ position: { x: 8, y: 8 }, force: true }).catch(() => {});
  await page.waitForTimeout(400);
}

const browser = await chromium.launch();
const ENTITY = "fce-001";

// ── primary 1440 pass: routes + transitions ──────────────────────────
{
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 })).newPage();
  await boot(page); await shot(page, "login-1440"); await login(page);

  await nav(page, "#/alerts"); await shot(page, "alerts-1440");

  for (const tab of ["overview", "insights", "heatmap", "platform", "context", "techstack", "health", "runs"]) {
    await nav(page, `#/clients/${ENTITY}/${tab}`); await page.waitForTimeout(400);
    await shot(page, `${tab}-1440`).catch(() => {});
  }

  // Intelligence panel (right rail)
  await nav(page, `#/clients/${ENTITY}/overview`);
  if (await page.locator(".ip-tab").isVisible().catch(() => false)) {
    await page.locator(".ip-tab").click(); await page.waitForTimeout(800);
    await shot(page, "state-intelligence-panel-1440"); await closeOverlays(page);
  }

  // Insight modal + tabs + evidence drawer
  await nav(page, `#/clients/${ENTITY}/insights`);
  const card = page.locator(".ic").first();
  if (await card.isVisible().catch(() => false)) {
    await card.click(); await page.waitForTimeout(600);
    await shot(page, "state-insight-modal-detail-1440");
    for (const t of ["Evidence", "Annotations", "Linked"]) {
      const tb = page.locator(".modal .client-tab", { hasText: t }).first();
      if (await tb.isVisible().catch(() => false)) { await tb.click(); await page.waitForTimeout(400); await shot(page, `state-insight-modal-${t.toLowerCase()}-1440`); }
    }
    await closeOverlays(page);
  }
  const echip = page.getByText(/^E-\d+/).first();
  if (await echip.isVisible().catch(() => false)) {
    await echip.click(); await page.waitForTimeout(700);
    await shot(page, "state-evidence-drawer-1440"); await closeOverlays(page);
  }

  // Heatmap modes / zoom / drawers / overlays / KPI edit
  await nav(page, `#/clients/${ENTITY}/heatmap`);
  const editBtn = page.locator('[title="Edit values"]').first();
  if (await editBtn.isVisible().catch(() => false)) { await editBtn.click(); await page.waitForTimeout(400); await shot(page, "state-heatmap-kpi-edit-1440"); await page.keyboard.press("Escape"); }
  const stdBtn = page.locator("button", { hasText: "Standard" }).first();
  if (await stdBtn.isVisible().catch(() => false)) {
    await stdBtn.click(); await page.waitForTimeout(700); await shot(page, "state-heatmap-standard-1440");
    const cell = page.locator(".hm-cell").first();
    if (await cell.isVisible().catch(() => false)) { await cell.click(); await page.waitForTimeout(800); await shot(page, "state-heatmap-synthesis-drawer-1440"); await closeOverlays(page); }
  }
  const vcBtn = page.locator("button", { hasText: "Value chain" }).first();
  if (await vcBtn.isVisible().catch(() => false)) { await vcBtn.click(); await page.waitForTimeout(700); await shot(page, "state-heatmap-valuechain-1440"); }

  // Platform: select another card + roadmap alt view
  await nav(page, `#/clients/${ENTITY}/platform`);
  const db = page.getByText("Databricks").first();
  if (await db.isVisible().catch(() => false)) { await db.click(); await page.waitForTimeout(700); await shot(page, "state-platform-databricks-1440"); }
  for (const label of ["Gantt", "Impact", "Curve"]) {
    const b = page.locator("button", { hasText: label }).first();
    if (await b.isVisible().catch(() => false)) { await b.click(); await page.waitForTimeout(500); await shot(page, `state-platform-${label.toLowerCase()}-1440`); }
  }

  // Chrome transitions: run selector, audience toggle, popovers, new-run modal
  await nav(page, `#/clients/${ENTITY}/overview`);
  const rs = page.locator(".run-selector").first();
  if (await rs.isVisible().catch(() => false)) { await rs.click(); await page.waitForTimeout(400); await shot(page, "state-run-selector-open-1440"); await page.keyboard.press("Escape"); }
  const cust = page.locator(".audience-toggle button", { hasText: "Customer" }).first();
  if (await cust.isVisible().catch(() => false)) {
    await cust.click(); await page.waitForTimeout(700); await shot(page, "state-overview-customer-1440");
    await nav(page, `#/clients/${ENTITY}/heatmap`); await shot(page, "state-heatmap-customer-1440");
    await page.locator(".audience-toggle button", { hasText: "Internal" }).first().click().catch(() => {});
  }
  await nav(page, "#/");
  for (const [icon, name] of [["bell", "notifications"], ["settings", "settings"]]) {
    const btn = page.locator(`.topbar [class*="icon"], .topbar button`).filter({ has: page.locator(`svg`) });
    // fall back to title-based lookup
    const b2 = page.locator(`[title*="${name}" i], [aria-label*="${name}" i]`).first();
    if (await b2.isVisible().catch(() => false)) { await b2.click(); await page.waitForTimeout(400); await shot(page, `state-popover-${name}-1440`); await page.keyboard.press("Escape"); await page.waitForTimeout(300); }
  }
  const newRun = page.locator("button", { hasText: "New run" }).first();
  if (await newRun.isVisible().catch(() => false)) { await newRun.click(); await page.waitForTimeout(500); await shot(page, "state-newrun-modal-1440"); await closeOverlays(page); }

  // Admin (switch role via settings popover)
  const gear = page.locator('[title*="settings" i], [aria-label*="settings" i]').first();
  if (await gear.isVisible().catch(() => false)) {
    await gear.click(); await page.waitForTimeout(400);
    const adminBtn = page.locator("button", { hasText: /^Admin$/ }).first();
    if (await adminBtn.isVisible().catch(() => false)) {
      await adminBtn.click(); await page.waitForTimeout(600);
      await page.keyboard.press("Escape");
      for (const [h, n] of [["#/admin", "admin"], ["#/admin/import", "admin-import"], ["#/admin/import/audit", "admin-import-audit"]]) {
        await nav(page, h); await shot(page, `${n}-1440`);
      }
    } else { console.log("! admin role switch not found"); await page.keyboard.press("Escape"); }
  }
  await page.context().close();
}

// ── responsive pass ──────────────────────────────────────────────────
for (const width of [1920, 1280, 980, 760]) {
  const page = await (await browser.newContext({ viewport: { width, height: 1000 }, deviceScaleFactor: 1 })).newPage();
  await boot(page); if (width === 760) await shot(page, `login-${width}`);
  await login(page);
  for (const [h, n] of [["#/", "dashboard"], ["#/clients", "directory"], [`#/clients/${ENTITY}/overview`, "overview"], [`#/clients/${ENTITY}/insights`, "insights"], [`#/clients/${ENTITY}/heatmap`, "heatmap"], [`#/clients/${ENTITY}/platform`, "platform"], [`#/clients/${ENTITY}/context`, "context"]]) {
    await nav(page, h); await shot(page, `${n}-${width}`);
  }
  await page.context().close();
}
await browser.close();
console.log("DONE");
