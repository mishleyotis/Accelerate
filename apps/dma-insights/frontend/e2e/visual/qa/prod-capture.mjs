// Production capture mirroring the prototype QA shots. Selector failures are findings.
import { createRequire } from "node:module";
const require = createRequire("/home/user/Accelerate/apps/dma-insights/frontend/package.json");
const { chromium } = require("@playwright/test");
import fs from "node:fs";

const OUT = "/tmp/prod-shots";
fs.mkdirSync(OUT, { recursive: true });
const FE = "http://localhost:5173";
const BE = "http://localhost:8000";
const ENTITY = "alma-bank-0001";

async function devLogin(context, email) {
  const res = await context.request.post(`${BE}/api/v1/auth/dev-login?email=${encodeURIComponent(email)}`);
  if (!res.ok()) throw new Error(`dev-login ${res.status()}`);
  const setCookie = res.headers()["set-cookie"] || "";
  const m = setCookie.match(/dma_session=([^;]+)/);
  if (!m) throw new Error("no dma_session cookie");
  await context.addCookies([{ name: "dma_session", value: m[1], domain: "localhost", path: "/" }]);
}
async function nav(page, h) {
  await page.goto(`${FE}/${h}`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1400);
  // wait for skeletons to clear
  for (let i = 0; i < 20; i++) {
    const n = await page.locator(".skel").count().catch(() => 0);
    if (n === 0) break;
    await page.waitForTimeout(500);
  }
}
async function shot(page, n) { await page.screenshot({ path: `${OUT}/prod-${n}.png`, fullPage: true }); console.log("✓", n); }
async function tryBlock(name, fn) { try { await fn(); } catch (e) { console.log("! FINDING:", name, "-", String(e).split("\n")[0].slice(0, 140)); } }
async function closeAll(page) {
  const ipX = page.locator(".ip .icon-btn").first();
  if (await ipX.isVisible().catch(() => false)) await ipX.click().catch(() => {});
  await page.keyboard.press("Escape").catch(() => {});
  const mask = page.locator(".modal-mask, .drawer-mask").first();
  if (await mask.isVisible().catch(() => false)) await mask.click({ position: { x: 8, y: 8 }, force: true }).catch(() => {});
  await page.waitForTimeout(400);
}

const browser = await chromium.launch();

// login page (unauthenticated)
{
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 1000 } })).newPage();
  await page.goto(`${FE}/#/login`, { waitUntil: "networkidle" });
  await page.waitForTimeout(800);
  await shot(page, "login-1440");
  await page.context().close();
}

// main analyst pass @1440
{
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await devLogin(context, "richard.odhiambo@zennify.com"); // ANALYST — matches prototype persona
  const page = await context.newPage();

  for (const [h, n] of [["#/", "dashboard"], ["#/clients", "directory"], ["#/alerts", "alerts"], ["#/prospecting", "prospecting"]]) {
    await tryBlock(n, async () => { await nav(page, h); await shot(page, `${n}-1440`); });
  }
  for (const tab of ["overview", "insights", "heatmap", "platform", "context", "techstack", "health", "runs"]) {
    await tryBlock(tab, async () => { await nav(page, `#/clients/${ENTITY}/${tab}`); await shot(page, `${tab}-1440`); });
  }

  await tryBlock("intelligence-panel", async () => {
    await nav(page, `#/clients/${ENTITY}/overview`);
    await page.locator(".ip-tab").first().click({ timeout: 4000 });
    await page.waitForTimeout(900); await shot(page, "state-intelligence-panel-1440"); await closeAll(page);
  });

  await tryBlock("insight-modal", async () => {
    await nav(page, `#/clients/${ENTITY}/insights`);
    await page.locator(".ic").first().click({ timeout: 4000 });
    await page.waitForTimeout(700); await shot(page, "state-insight-modal-detail-1440");
    for (const t of ["Evidence", "Annotations", "Linked"]) {
      const tb = page.locator(".modal .client-tab, [role=dialog] .client-tab, dialog .client-tab", { hasText: t }).first();
      if (await tb.isVisible().catch(() => false)) { await tb.click(); await page.waitForTimeout(400); await shot(page, `state-insight-modal-${t.toLowerCase()}-1440`); }
      else console.log("! FINDING: insight-modal tab missing:", t);
    }
    await closeAll(page);
  });

  await tryBlock("evidence-drawer", async () => {
    await nav(page, `#/clients/${ENTITY}/insights`);
    await page.getByText(/^E-\d+/).first().click({ timeout: 4000 });
    await page.waitForTimeout(800); await shot(page, "state-evidence-drawer-1440"); await closeAll(page);
  });

  await tryBlock("heatmap-states", async () => {
    await nav(page, `#/clients/${ENTITY}/heatmap`);
    const stdBtn = page.locator("button", { hasText: "Standard" }).first();
    await stdBtn.click({ timeout: 4000 }); await page.waitForTimeout(900);
    await shot(page, "state-heatmap-standard-1440");
    const cell = page.locator(".hm-cell").first();
    if (await cell.isVisible().catch(() => false)) { await cell.click(); await page.waitForTimeout(900); await shot(page, "state-heatmap-synthesis-drawer-1440"); await closeAll(page); }
    else console.log("! FINDING: no .hm-cell in standard mode");
    const vc = page.locator("button", { hasText: "Value chain" }).first();
    if (await vc.isVisible().catch(() => false)) { await vc.click(); await page.waitForTimeout(900); await shot(page, "state-heatmap-valuechain-1440"); }
    else console.log("! FINDING: no Value chain mode button");
  });

  await tryBlock("platform-states", async () => {
    await nav(page, `#/clients/${ENTITY}/platform`);
    await page.getByText("Databricks").first().click({ timeout: 4000 });
    await page.waitForTimeout(900); await shot(page, "state-platform-databricks-1440");
  });

  await tryBlock("run-selector", async () => {
    await nav(page, `#/clients/${ENTITY}/overview`);
    await page.locator(".run-selector").first().click({ timeout: 4000 });
    await page.waitForTimeout(400); await shot(page, "state-run-selector-open-1440"); await closeAll(page);
  });

  await tryBlock("audience-customer", async () => {
    const cust = page.locator(".audience-toggle button", { hasText: "Customer" }).first();
    await cust.click({ timeout: 4000 }); await page.waitForTimeout(900);
    await shot(page, "state-overview-customer-1440");
    await nav(page, `#/clients/${ENTITY}/heatmap`); await shot(page, "state-heatmap-customer-1440");
    await nav(page, `#/clients/${ENTITY}/platform`); await shot(page, "state-platform-customer-1440");
    await page.locator(".audience-toggle button", { hasText: "Internal" }).first().click().catch(() => {});
  });

  await tryBlock("newrun-modal", async () => {
    await nav(page, "#/");
    await page.locator("button", { hasText: "New run" }).first().click({ timeout: 4000 });
    await page.waitForTimeout(600); await shot(page, "state-newrun-modal-1440"); await closeAll(page);
  });

  await context.close();
}

// admin pass @1440
{
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await devLogin(context, "mishley.otiende@zennify.com"); // ADMIN persona
  const page = await context.newPage();
  for (const [h, n] of [["#/admin", "admin"], ["#/admin/import", "admin-import"], ["#/admin/import/audit", "admin-import-audit"]]) {
    await tryBlock(n, async () => { await nav(page, h); await shot(page, `${n}-1440`); });
  }
  await context.close();
}

// responsive pass
for (const width of [1920, 1280, 980, 760]) {
  await tryBlock(`responsive-${width}`, async () => {
    const context = await browser.newContext({ viewport: { width, height: 1000 } });
    await devLogin(context, "richard.odhiambo@zennify.com");
    const page = await context.newPage();
    if (width === 760) { await page.goto(`${FE}/#/login`); await page.waitForTimeout(700); }
    for (const [h, n] of [["#/", "dashboard"], ["#/clients", "directory"], [`#/clients/${ENTITY}/overview`, "overview"], [`#/clients/${ENTITY}/insights`, "insights"], [`#/clients/${ENTITY}/heatmap`, "heatmap"], [`#/clients/${ENTITY}/platform`, "platform"], [`#/clients/${ENTITY}/context`, "context"]]) {
      await nav(page, h); await shot(page, `${n}-${width}`);
    }
    await context.close();
  });
}
await browser.close();
console.log("DONE-PROD");
