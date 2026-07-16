// Drilldown / submenu / icon-state capture against real data.
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
const BASE = "http://127.0.0.1:5173";
const ENT = process.env.ENT || "amarillo-national-bank-0001";
const OUT = "docs/qa/live";
mkdirSync(OUT, { recursive: true });

const b = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium-1223/chrome-linux64/chrome", args: ["--no-sandbox"] });
const ctx = await b.newContext({ viewport: { width: 1440, height: 1000 } });
await ctx.request.post(`${BASE}/api/v1/auth/dev-login?email=chris.conant@zennify.com`);
const page = await ctx.newPage();

async function go(path) { await page.goto(`${BASE}/#${path}`, { waitUntil: "networkidle" }); await page.waitForTimeout(1500); }
async function shot(name) { await page.screenshot({ path: `${OUT}/state-${name}.png`, fullPage: false }); console.log("state", name); }
async function tryClick(sels) {
  for (const s of sels) {
    const el = page.locator(s).first();
    if (await el.count() && await el.isVisible().catch(() => false)) {
      await el.click({ timeout: 4000 }).catch(() => {}); return true;
    }
  }
  return false;
}

const states = [
  ["insight-modal", `/clients/${ENT}/insights`, [".ic", "[role='button'].ic", ".card.clickable"]],
  ["evidence-drawer", `/clients/${ENT}/insights`, [".chip", "[data-testid='affected-cap']", "button:has-text('evidence')"]],
  ["heatmap-drawer", `/clients/${ENT}/heatmap`, [".hm-cell", ".dense-cell", "[data-page='heatmap'] [role='button']", "[data-page='heatmap'] td"]],
  ["topfinding-open", `/clients/${ENT}/overview`, [".chip"]],
  ["platform-roadmap", `/clients/${ENT}/platform`, ["button:has-text('Roadmap')", "button:has-text('roadmap')", ".tab:has-text('Roadmap')"]],
  ["request-dma-modal", "/clients", ["button:has-text('New run')", "button:has-text('Request')"]],
  ["audience-customer", `/clients/${ENT}/overview`, ["button:has-text('Customer')", "[role='tab']:has-text('Customer')"]],
  ["run-selector", `/clients/${ENT}/overview`, [".client-bar select", "button:has-text('Apr')", "select"]],
  ["notifications-popover", "/", ["button[aria-label*='otification' i]", "button[aria-label*='nseen' i]", "header button:has(svg[data-icon='bell'])"]],
  ["settings-popover", "/", ["button[aria-label*='ettings' i]", "button[title*='ettings' i]", "header button:last-of-type"]],
  ["search-overlay", "/", ["input[placeholder*='earch']", "[role='searchbox']"]],
];

for (const [name, path, sels] of states) {
  try {
    await go(path);
    const clicked = await tryClick(sels);
    await page.waitForTimeout(800);
    await shot(name);
    if (!clicked) console.log(`  (no target matched for ${name})`);
    await page.keyboard.press("Escape").catch(() => {});
  } catch (e) { console.log(`FAIL ${name}: ${String(e).slice(0, 90)}`); }
}
await b.close();
