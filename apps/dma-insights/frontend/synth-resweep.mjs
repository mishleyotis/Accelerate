// Re-measure the synthesis drawer for ALL 94 with a proper content wait
// (the first sweep read the drawer's "Loading…" skeleton on 67 clients).
// Also re-runs the full drilldown row for clients whose first pass was fatal.
import { chromium } from "@playwright/test";
import fs from "node:fs";

const BASE = "http://localhost:5173";
const API = "http://localhost:8000";
const CLIENTS = JSON.parse(
  fs.readFileSync("/home/user/Accelerate/apps/dma-insights/startup-data/scores.json", "utf8"),
).clients.map((c) => c.display_id);
const OUT = "/tmp/synth-resweep.jsonl";

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
    await page.goto(`${BASE}/#/clients/${did}/heatmap?hm=standard&zoom=subcap`, { waitUntil: "domcontentloaded", timeout: 45000 });
    await page.waitForSelector(".hm-cell", { timeout: 20000 });
    const cell = page.locator(".hm-cell").first();
    await cell.click();
    const dlg = page.locator("[role='dialog'][aria-label='Sub-capability synthesis']");
    await dlg.waitFor({ timeout: 10000 });
    // WAIT for async content: skeleton says "Loading…"; real content is long.
    await page.waitForFunction(() => {
      const d = document.querySelector("[role='dialog'][aria-label='Sub-capability synthesis']");
      return d && !/Loading…/.test(d.innerText) && d.innerText.length > 150;
    }, { timeout: 20000 }).catch(() => {});
    const t = await dlg.innerText();
    row.synth = {
      len: t.length,
      eids: (t.match(/\bE-\d+/g) || []).length,
      hasEvidence: /source reports|evidence/i.test(t),
      hasPeerViz: /peer/i.test(t),
      hasNumbers: (t.match(/\d/g) || []).length >= 4,
      stillLoading: /Loading…/.test(t),
      ipAutoOpen: (await page.locator("aside.ip").count()) > 0,
      sample: t.replace(/\s+/g, " ").slice(0, 300),
    };
  } catch (e) {
    row.fatal = String(e).slice(0, 140);
  }
  fs.appendFileSync(OUT, JSON.stringify(row) + "\n");
  if (__idx % 10 === 0) console.log(`[${__idx + 1}/${CLIENTS.length}]`, did);
  await page.close();
 }
}
await Promise.all(Array.from({ length: 3 }, worker));
await browser.close();
console.log("DONE ->", OUT);
