// Post-fix re-measure: rendered focus-card grounding across ALL 94.
import { chromium } from "@playwright/test";
import fs from "node:fs";
const BASE = "http://localhost:5173", API = "http://localhost:8000";
const CLIENTS = JSON.parse(fs.readFileSync("/home/user/Accelerate/apps/dma-insights/startup-data/scores.json","utf8")).clients.map(c=>c.display_id);
const b = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
const ctx = await b.newContext({ baseURL: BASE, viewport: { width: 1440, height: 900 } });
const r = await ctx.request.post(`${API}/api/v1/auth/dev-login?email=ae.test@zennify.com`);
const m = (r.headers()["set-cookie"] || "").match(/dma_session=([^;]+)/);
await ctx.addCookies([{ name: "dma_session", value: m[1], url: BASE }]);
let pass = 0; const fails = [];
let i = 0;
async function worker() {
  for (;;) {
    const idx = i++; if (idx >= CLIENTS.length) return;
    const did = CLIENTS[idx];
    const p = await ctx.newPage();
    try {
      await p.goto(`${BASE}/#/clients/${did}/heatmap`, { waitUntil: "domcontentloaded", timeout: 30000 });
      await p.waitForSelector(".fa-card", { timeout: 15000 });
      await p.waitForTimeout(500);
      const t = await p.evaluate(() => [...document.querySelectorAll(".fa-card")].map(e=>e.innerText).join(" "));
      if (/p\.\s*\d|E-\d|\$|%|Client research report|capability gaps/.test(t)) pass++;
      else fails.push(did.slice(0,24));
    } catch { fails.push(did.slice(0,20)+"(err)"); }
    await p.close();
    if (idx % 20 === 0) console.log(`[${idx+1}/${CLIENTS.length}]`);
  }
}
await Promise.all(Array.from({length:4}, worker));
console.log(`RESULT focus grounded-rendered: ${pass}/${CLIENTS.length}; fails:`, fails);
await b.close();
