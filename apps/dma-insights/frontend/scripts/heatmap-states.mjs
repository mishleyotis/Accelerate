/**
 * Targeted heatmap interaction-state capture: Standard-view zoom ladder
 * (pillar → category → capability → subcap), synthesis drawer, evidence
 * drawer — the states the corpus sweep misses because the page defaults
 * to Focus view (no .hm-cell rendered there).
 *
 * Usage: PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers node scripts/heatmap-states.mjs <cookie> <entity> [entity...]
 * Output: /tmp/corpus_shots/<entity>/heatmap-std-*.png
 */
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const COOKIE = process.argv[2];
const ENTS = process.argv.slice(3);
if (!COOKIE || !ENTS.length) throw new Error("usage: <cookie> <entity>...");

const APP = "http://127.0.0.1:5173";
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
await ctx.addCookies([
  { name: "dma_session", value: COOKIE, domain: "127.0.0.1", path: "/" },
]);
const page = await ctx.newPage();
page.setDefaultTimeout(15000);

for (const did of ENTS) {
  const dir = `/tmp/corpus_shots/${did}`;
  mkdirSync(dir, { recursive: true });
  await page.goto(`${APP}/#/clients/${did}/heatmap`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2500);
  // switch to Standard view
  await page.getByRole("button", { name: /standard/i }).first().click();
  await page.waitForTimeout(1200);
  await page.screenshot({ path: `${dir}/heatmap-std-pillar.png`, fullPage: true });

  // zoom ladder: pillar zoom renders .card-tile cards; deeper zooms
  // render the .hm-cell grid (HeatmapPage.tsx 432 vs 471).
  for (const [level, sel] of [
    ["category", ".card-tile"],
    ["capability", ".hm-cell"],
    ["subcap", ".hm-cell"],
  ]) {
    try {
      await page.locator(sel).first().click();
      await page.waitForTimeout(900);
      await page.screenshot({ path: `${dir}/heatmap-std-${level}.png`, fullPage: true });
    } catch (e) {
      console.log(`${did} zoom ${level} failed: ${String(e).slice(0, 100)}`);
      break;
    }
  }
  // synthesis drawer: at subcap zoom, click a cell again
  try {
    await page.locator(".hm-cell").first().click();
    await page.waitForSelector('[role="dialog"], .drawer', { timeout: 6000 });
    await page.waitForTimeout(900);
    await page.screenshot({ path: `${dir}/heatmap-synthesis-drawer.png`, fullPage: false });
    // evidence drawer from within the synthesis drawer if present
    const evBtn = page.getByRole("button", { name: /evidence/i }).first();
    if (await evBtn.isVisible().catch(() => false)) {
      await evBtn.click();
      await page.waitForTimeout(900);
      await page.screenshot({ path: `${dir}/heatmap-evidence-drawer.png`, fullPage: false });
    }
    await page.keyboard.press("Escape");
  } catch (e) {
    console.log(`${did} drawer failed: ${String(e).slice(0, 100)}`);
  }
  console.log(`${did} done`);
}
await browser.close();
console.log("HEATMAP STATES DONE");
