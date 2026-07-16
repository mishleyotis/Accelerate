// Drilldown depth sweep — stratified clients: open the load-bearing
// drilldowns and grade the RENDERED content depth (synthesis drawer,
// insight modal, timeline event detail, sentiment expand, fit breakdown).
import { chromium } from "@playwright/test";
import fs from "node:fs";

const BASE = "http://localhost:5173";
const API = "http://localhost:8000";
// 100% coverage: ALL 94 clients (user mandate — no sampling).
const CLIENTS = JSON.parse(
  fs.readFileSync("/home/user/Accelerate/apps/dma-insights/startup-data/scores.json", "utf8"),
).clients.map((c) => c.display_id);
const OUT = "/tmp/drilldown-sweep.jsonl";

const browser = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
const ctx = await browser.newContext({ baseURL: BASE, viewport: { width: 1440, height: 900 } });
const r = await ctx.request.post(`${API}/api/v1/auth/dev-login?email=ae.test@zennify.com`);
const m = (r.headers()["set-cookie"] || "").match(/dma_session=([^;]+)/);
await ctx.addCookies([{ name: "dma_session", value: m[1], url: BASE }]);
fs.writeFileSync(OUT, "");

let __i = 0;
async function worker() {
 for (;;) {
  const __idx = __i++;
  if (__idx >= CLIENTS.length) return;
  const did = CLIENTS[__idx];
  const page = await ctx.newPage();
  const row = { did };
  try {
    // 1. heatmap synthesis drawer (subcap grid, first cell)
    await page.goto(`${BASE}/#/clients/${did}/heatmap?hm=standard&zoom=subcap`, { waitUntil: "domcontentloaded" });
    await page.waitForSelector(".hm-cell", { timeout: 15000 }).catch(() => {});
    const cell = page.locator(".hm-cell").first();
    if (await cell.count()) {
      await cell.click();
      const dlg = page.locator("[role='dialog'][aria-label='Sub-capability synthesis']");
      await dlg.waitFor({ timeout: 8000 }).catch(() => {});
      if (await dlg.count()) {
        const t = await dlg.innerText();
        row.synth = {
          len: t.length,
          eids: (t.match(/\bE-\d+/g) || []).length,
          hasEvidence: /source reports|evidence/i.test(t),
          hasPeerViz: /peer/i.test(t),
          hasNumbers: (t.match(/\d/g) || []).length >= 4,
          ipAutoOpen: (await page.locator("aside.ip").count()) > 0,
          sample: t.replace(/\s+/g, " ").slice(0, 260),
        };
        await page.keyboard.press("Escape");
      } else row.synth = { open: false };
    }
    // 2. insight modal (first card)
    await page.goto(`${BASE}/#/clients/${did}/insights`, { waitUntil: "domcontentloaded" });
    await page.waitForSelector(".ic-title, .empty", { timeout: 12000 }).catch(() => {});
    const card = page.locator(".ic-title").first();
    if (await card.count()) {
      await card.click();
      const modal = page.locator(".insight-modal");
      await modal.waitFor({ timeout: 8000 }).catch(() => {});
      if (await modal.count()) {
        const t = await modal.innerText();
        row.insightModal = {
          len: t.length,
          eids: (t.match(/\bE-\d+/g) || []).length,
          tabs: await modal.locator("[role='tab'], .tab, button").count(),
          hasWhy: /why/i.test(t),
          namesSystem: /Salesforce|Fiserv|FIS\b|Jack Henry|nCino|MuleSoft|CRM|core/i.test(t),
          sample: t.replace(/\s+/g, " ").slice(0, 260),
        };
        await page.keyboard.press("Escape");
      } else row.insightModal = { open: false };
    } else row.insightModal = { noCards: true };
    // 3. context: timeline event detail + sentiment expand
    await page.goto(`${BASE}/#/clients/${did}/context`, { waitUntil: "domcontentloaded" });
    await page.waitForSelector(".card", { timeout: 12000 }).catch(() => {});
    const dot = page.locator("[data-testid='timeline-dot']").first();
    if (await dot.count()) {
      await dot.click({ force: true });
      const det = page.locator("[data-testid='event-detail']");
      await det.waitFor({ timeout: 6000 }).catch(() => {});
      row.eventDetail = (await det.count())
        ? { len: (await det.innerText()).length, eids: ((await det.innerText()).match(/\bE-\d+/g) || []).length }
        : { open: false };
    } else row.eventDetail = { noDots: true };
    row.finSection = await page.evaluate(() => {
      const t = document.body.innerText;
      const i = t.toLowerCase().indexOf("financial");
      return i >= 0 ? t.slice(i, i + 420).replace(/\s+/g, " ") : "";
    });
    const tile = page.locator("[data-testid='sentiment-tile']").first();
    if (await tile.count()) {
      await tile.click();
      const dd = page.locator("[data-testid='sentiment-drilldown']");
      await dd.waitFor({ timeout: 5000 }).catch(() => {});
      row.sentimentDrill = (await dd.count())
        ? { len: (await dd.innerText()).length }
        : { open: false };
    } else row.sentimentDrill = { noTiles: true };
    // 4. platform: fit breakdown modal (click first fit tile region)
    await page.goto(`${BASE}/#/clients/${did}/platform`, { waitUntil: "domcontentloaded" });
    await page.waitForSelector(".card", { timeout: 12000 }).catch(() => {});
    const fitBtn = page.locator("text=/fit breakdown|why this score/i").first();
    if (await fitBtn.count()) {
      await fitBtn.click().catch(() => {});
      const fm = page.locator("[data-testid='fit-breakdown-modal']");
      await fm.waitFor({ timeout: 5000 }).catch(() => {});
      row.fitBreakdown = (await fm.count()) ? { len: (await fm.innerText()).length } : { open: false };
    }
  } catch (e) {
    row.fatal = String(e).slice(0, 150);
  }
  fs.appendFileSync(OUT, JSON.stringify(row) + "\n");
  if (__idx % 10 === 0) console.log(`[${__idx + 1}/${CLIENTS.length}]`, did);
  await page.close();
 }
}
await Promise.all(Array.from({ length: 4 }, worker));
await browser.close();
console.log("DONE ->", OUT);
