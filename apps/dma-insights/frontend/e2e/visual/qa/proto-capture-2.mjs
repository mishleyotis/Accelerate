// Continuation: remaining prototype states + responsive pass.
import { createRequire } from "node:module";
const require = createRequire("/home/user/Accelerate/apps/dma-insights/frontend/package.json");
const { chromium } = require("@playwright/test");
import fs from "node:fs";

const OUT = "/tmp/proto-shots";
fs.mkdirSync(OUT, { recursive: true });
const URL = "http://localhost:8082/";
const ENTITY = "fce-001";

async function boot(page) { await page.goto(URL, { waitUntil: "domcontentloaded" }); await page.getByText(/Continue with Google/i).first().waitFor({ timeout: 60000 }); }
async function login(page) { await page.getByText(/Continue with Google/i).first().click(); await page.waitForTimeout(1200); }
async function nav(page, h) { await page.evaluate(x => { location.hash = x; }, h); await page.waitForTimeout(900); }
async function shot(page, n) { await page.screenshot({ path: `${OUT}/proto-${n}.png`, fullPage: true }); console.log("✓", n); }
async function tryBlock(name, fn) { try { await fn(); } catch (e) { console.log("!", name, "-", String(e).split("\n")[0].slice(0, 120)); } }
async function closeAll(page) {
  const ipX = page.locator(".ip .icon-btn").first();
  if (await ipX.isVisible().catch(() => false)) await ipX.click().catch(() => {});
  await page.keyboard.press("Escape").catch(() => {});
  const mask = page.locator(".modal-mask, .drawer-mask").first();
  if (await mask.isVisible().catch(() => false)) await mask.click({ position: { x: 8, y: 8 }, force: true }).catch(() => {});
  await page.waitForTimeout(400);
}

const browser = await chromium.launch();
{
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 })).newPage();
  await boot(page); await login(page);

  await tryBlock("run-selector", async () => {
    await nav(page, `#/clients/${ENTITY}/overview`);
    await page.locator(".run-selector").first().click(); await page.waitForTimeout(400);
    await shot(page, "state-run-selector-open-1440"); await closeAll(page);
  });

  await tryBlock("audience-customer", async () => {
    await page.locator(".audience-toggle button", { hasText: "Customer" }).first().click();
    await page.waitForTimeout(800); await shot(page, "state-overview-customer-1440");
    await nav(page, `#/clients/${ENTITY}/heatmap`); await shot(page, "state-heatmap-customer-1440");
    await nav(page, `#/clients/${ENTITY}/platform`); await shot(page, "state-platform-customer-1440");
    await page.locator(".audience-toggle button", { hasText: "Internal" }).first().click().catch(() => {});
    await page.waitForTimeout(400);
  });

  await tryBlock("popovers", async () => {
    await nav(page, "#/");
    const btns = page.locator(".topbar button, header button");
    const n = await btns.count();
    for (let i = 0; i < n; i++) {
      const t = await btns.nth(i).getAttribute("title").catch(() => null);
      if (t && /notif|bell/i.test(t)) { await btns.nth(i).click(); await page.waitForTimeout(400); await shot(page, "state-popover-notifications-1440"); await page.keyboard.press("Escape"); }
      if (t && /setting/i.test(t)) { await btns.nth(i).click(); await page.waitForTimeout(400); await shot(page, "state-popover-settings-1440"); await page.keyboard.press("Escape"); }
    }
    // search popover
    await page.keyboard.press("Meta+KeyK").catch(() => {});
    await page.waitForTimeout(400);
    await shot(page, "state-popover-search-1440");
    await page.keyboard.press("Escape");
  });

  await tryBlock("newrun-modal", async () => {
    await nav(page, "#/");
    await page.locator("button", { hasText: "New run" }).first().click();
    await page.waitForTimeout(500); await shot(page, "state-newrun-modal-1440"); await closeAll(page);
  });

  await tryBlock("admin-pages", async () => {
    // settings popover hosts the ACTING-AS role switch
    const gear = page.locator('[title*="setting" i], [aria-label*="setting" i]').first();
    if (await gear.isVisible().catch(() => false)) { await gear.click(); await page.waitForTimeout(400); }
    const adminBtn = page.locator("button", { hasText: /^Admin$/ }).first();
    if (await adminBtn.isVisible().catch(() => false)) { await adminBtn.click(); await page.waitForTimeout(500); }
    await page.keyboard.press("Escape");
    for (const [h, n] of [["#/admin", "admin"], ["#/admin/import", "admin-import"], ["#/admin/import/audit", "admin-import-audit"]]) {
      await nav(page, h); await shot(page, `${n}-1440`);
    }
  });

  await page.context().close();
}

for (const width of [1920, 1280, 980, 760]) {
  await tryBlock(`responsive-${width}`, async () => {
    const page = await (await browser.newContext({ viewport: { width, height: 1000 }, deviceScaleFactor: 1 })).newPage();
    await boot(page); if (width === 760) await shot(page, `login-${width}`);
    await login(page);
    for (const [h, n] of [["#/", "dashboard"], ["#/clients", "directory"], [`#/clients/${ENTITY}/overview`, "overview"], [`#/clients/${ENTITY}/insights`, "insights"], [`#/clients/${ENTITY}/heatmap`, "heatmap"], [`#/clients/${ENTITY}/platform`, "platform"], [`#/clients/${ENTITY}/context`, "context"]]) {
      await nav(page, h); await shot(page, `${n}-${width}`);
    }
    await page.context().close();
  });
}
await browser.close();
console.log("DONE2");
