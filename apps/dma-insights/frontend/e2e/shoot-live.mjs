// Ad-hoc screenshot harness for prototype-parity QA against the REAL 94-client
// data (the visual suite seeds only `richbank`). Logs in as an admin via
// dev-login, then captures each page + key drilldown state at 1440px.
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const BASE = process.env.BASE || "http://127.0.0.1:5173";
const EMAIL = process.env.EMAIL || "chris.conant@zennify.com";
const ENT = process.env.ENT || "amarillo-national-bank-0001";
const OUT = process.env.OUT || "docs/qa/live";
mkdirSync(OUT, { recursive: true });

const PAGES = [
  ["dashboard", "/"],
  ["directory", "/clients"],
  ["overview", `/clients/${ENT}/overview`],
  ["insights", `/clients/${ENT}/insights`],
  ["heatmap", `/clients/${ENT}/heatmap`],
  ["platform", `/clients/${ENT}/platform`],
  ["context", `/clients/${ENT}/context`],
  ["health", `/clients/${ENT}/health`],
  ["techstack", `/clients/${ENT}/techstack`],
  ["alerts", "/alerts"],
  ["prospecting", "/prospecting"],
  ["admin", "/admin"],
];

const browser = await chromium.launch({
  executablePath: process.env.PW_CHROME || "/opt/pw-browsers/chromium-1223/chrome-linux64/chrome",
  args: ["--no-sandbox"],
});
const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
const resp = await ctx.request.post(`${BASE}/api/v1/auth/dev-login?email=${encodeURIComponent(EMAIL)}`);
console.log("dev-login", resp.status());
const page = await ctx.newPage();
const errors = [];
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 140)); });

for (const [name, path] of PAGES) {
  try {
    await page.goto(`${BASE}/#${path}`, { waitUntil: "networkidle", timeout: 30000 });
    await page.waitForTimeout(1800);
    await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
    // crude empty-state probe: count visible "—" / "No " placeholders in main
    const empties = await page.locator("text=/^(—|No \\w|empty|not yet|coming soon)/i").count().catch(() => 0);
    console.log(`shot ${name}  empties≈${empties}`);
  } catch (e) {
    console.log(`FAIL ${name}: ${String(e).slice(0, 120)}`);
  }
}
// ── Drilldown / popup states ───────────────────────────────────────────
async function state(name, path, action) {
  try {
    await page.goto(`${BASE}/#${path}`, { waitUntil: "networkidle", timeout: 30000 });
    await page.waitForTimeout(1500);
    await action();
    await page.waitForTimeout(900);
    await page.screenshot({ path: `${OUT}/state-${name}.png`, fullPage: false });
    console.log(`state ${name}`);
    await page.keyboard.press("Escape").catch(() => {});
  } catch (e) {
    console.log(`STATE FAIL ${name}: ${String(e).slice(0, 110)}`);
  }
}
const click = async (sel) => { const el = page.locator(sel).first(); await el.scrollIntoViewIfNeeded(); await el.click({ timeout: 5000 }); };
await state("insight-modal", `/clients/${ENT}/insights`, () => click(".insight-card, [data-testid='insight-card'], .card.clickable"));
await state("heatmap-drawer", `/clients/${ENT}/heatmap`, () => click(".hm-cell, [class*='cell'], td[role='button']"));
await state("topfinding-open", `/clients/${ENT}/overview`, () => click(".chip"));
await state("request-dma-modal", "/clients", () => click("button:has-text('New run'), button:has-text('Request'), button:has-text('New DMA')"));
await state("settings-popover", "/", () => click("[aria-label*='ettings'], [title*='ettings'], .icon-btn:last-child"));
await state("notifications-popover", "/", () => click("[aria-label*='otification'], [title*='otification']"));

if (errors.length) console.log("CONSOLE ERRORS:", [...new Set(errors)].slice(0, 8));
await browser.close();
