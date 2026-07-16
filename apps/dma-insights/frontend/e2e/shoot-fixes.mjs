// Capture the three remediated surfaces + their drilldowns / button-clicks
// against live data: Context sentiment overview, deep jargon-free insight cards
// (modal), and the prototype-restored Heatmap (pillar rung, subcap synthesis
// drawer, category synthesis, focus-area ScoreRing view, value-chain expansion).
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
const BASE = "http://127.0.0.1:5173";
const OUT = "docs/qa/live";
const ENTS = (process.env.ENTS || "amarillo-national-bank-0001,exchange-bank-0001").split(",");
mkdirSync(OUT, { recursive: true });

const b = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium-1223/chrome-linux64/chrome", args: ["--no-sandbox"] });
const ctx = await b.newContext({ viewport: { width: 1440, height: 1000 } });
await ctx.request.post(`${BASE}/api/v1/auth/dev-login?email=chris.conant@zennify.com`);
const page = await ctx.newPage();

async function go(path) { await page.goto(`${BASE}/#${path}`, { waitUntil: "networkidle" }); await page.waitForTimeout(1600); }
async function shot(name) { await page.screenshot({ path: `${OUT}/fix-${name}.png`, fullPage: false }); console.log("  shot", name); }
async function clickText(txts) {
  for (const t of txts) {
    const el = page.getByText(t, { exact: false }).first();
    if (await el.count() && await el.isVisible().catch(() => false)) { await el.click({ timeout: 3500 }).catch(() => {}); return true; }
  }
  return false;
}
async function clickSel(sels) {
  for (const s of sels) {
    const el = page.locator(s).first();
    if (await el.count() && await el.isVisible().catch(() => false)) { await el.click({ timeout: 3500 }).catch(() => {}); return true; }
  }
  return false;
}
async function scrollToText(t) {
  const el = page.getByText(t, { exact: false }).first();
  if (await el.count()) { await el.scrollIntoViewIfNeeded().catch(() => {}); await page.waitForTimeout(500); return true; }
  return false;
}

for (const ENT of ENTS) {
  const tag = ENT.split("-")[0];
  console.log(`\n=== ${ENT} ===`);

  // 1. Context — sentiment overview (now grounded in the research report)
  try {
    await go(`/clients/${ENT}/context`);
    await scrollToText("Sentiment overview");
    await shot(`${tag}-context-sentiment`);
  } catch (e) { console.log("FAIL context", String(e).slice(0, 80)); }

  // 2. Insights — deep, jargon-free cards + modal (button-click → modal)
  try {
    await go(`/clients/${ENT}/insights`);
    await shot(`${tag}-insights-list`);
    const opened = await clickSel([".ic", "[role='button'].ic", ".card.clickable", ".ic-body"]);
    await page.waitForTimeout(900);
    await shot(`${tag}-insight-modal`);
    if (!opened) console.log("  (no insight card matched)");
    await page.keyboard.press("Escape").catch(() => {});
  } catch (e) { console.log("FAIL insights", String(e).slice(0, 80)); }

  // 3a. Heatmap — pillar-level zoom rung (standard mode + zoom=pillar)
  try {
    await go(`/clients/${ENT}/heatmap?hm=standard&zoom=pillar`);
    await shot(`${tag}-heatmap-pillar`);
  } catch (e) { console.log("FAIL heatmap-pillar", String(e).slice(0, 80)); }

  // 3b. Heatmap — subcap synthesis drawer (peer scale + caps callout)
  try {
    await go(`/clients/${ENT}/heatmap?hm=standard&zoom=subcap`);
    await shot(`${tag}-heatmap-grid`);
    await clickSel([".hm-cell", ".dense-cell", "[class*='cell']", "[data-page='heatmap'] [role='button']", "[data-page='heatmap'] td"]);
    await page.waitForTimeout(1000);
    await shot(`${tag}-heatmap-synthesis`);
    await page.keyboard.press("Escape").catch(() => {});
  } catch (e) { console.log("FAIL heatmap-synthesis", String(e).slice(0, 80)); }

  // 3c. Heatmap — focus-area detail (ScoreRing + pillar contribution + insight grid)
  try {
    await go(`/clients/${ENT}/heatmap`); // default mode is focus
    await clickSel([".fa-card", ".fa-illo", "[data-testid='focus-area']", "[data-page='heatmap'] .card"]);
    await page.waitForTimeout(1000);
    await shot(`${tag}-heatmap-focus`);
  } catch (e) { console.log("FAIL heatmap-focus", String(e).slice(0, 80)); }

  // 3d. Heatmap — value-chain expansion (click a stage → drilled subcaps + insights)
  try {
    await go(`/clients/${ENT}/heatmap?hm=value_chain`);
    await clickSel([".vc-card", ".stage-card", "[data-testid='vc-stage']", "[data-page='heatmap'] .card"]);
    await page.waitForTimeout(900);
    await shot(`${tag}-heatmap-valuechain`);
  } catch (e) { console.log("FAIL heatmap-valuechain", String(e).slice(0, 80)); }
}
await b.close();
console.log("\ndone");
