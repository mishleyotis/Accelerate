// ALL-94 rendered-depth sweep: drives the LIVE app and measures what an AE
// actually SEES per client x page — component counts, empty-state markers,
// text density, citations, named systems — to grade AE-worthiness and find
// NLP-extraction gaps. Writes JSON lines to /tmp/depth-sweep.jsonl.
import { chromium } from "@playwright/test";
import fs from "node:fs";

const BASE = "http://localhost:5173";
const API = "http://localhost:8000";
const OUT = "/tmp/depth-sweep.jsonl";
const WORKERS = 5;

const clients = JSON.parse(
  fs.readFileSync("/home/user/Accelerate/apps/dma-insights/startup-data/scores.json", "utf8"),
).clients.map((c) => c.display_id);

const NAMED_SYS = /Salesforce|Fiserv|FIS\b|Jack Henry|nCino|Temenos|Finastra|MuleSoft|Snowflake|Databricks|ServiceNow|Okta|Q2|Alkami|Backbase|DocuSign|HubSpot|Marketo|AWS|Azure|GCP|Data Cloud|Agentforce|Marketing Cloud|Service Cloud|Experience Cloud|core banking|CRM/i;
const EID = /\bE-\d+/;

async function metrics(page) {
  return page.evaluate(() => {
    const $ = (s) => document.querySelectorAll(s);
    const txt = (s) => [...$(s)].map((e) => e.innerText || "").join(" ");
    return {
      apiEmpty: $('[data-source="api-empty"]').length,
      apiFull: $('[data-source="api"]').length,
      cards: $(".card").length,
      bodyLen: (document.querySelector("main, .client-content, .page")?.innerText || "").length,
      wn: $(".wn-signal").length,
      wnText: txt(".wn-signal").slice(0, 4000),
      icTitles: $(".ic-title").length,
      icBodies: [...$(".ic-body")].map((e) => (e.innerText || "").length),
      faCards: $(".fa-card").length,
      faText: txt(".fa-card").slice(0, 3000),
      hmCells: $(".hm-cell").length,
      firmoRows: document.querySelector('[data-testid="firmographics-rows"]')?.children?.length ?? 0,
      leadFooter: document.querySelector('[data-testid="leadership-footer"]')?.innerText ?? "",
      timelineDots: $('[data-testid="timeline-dot"]').length,
      acqRows: $('[data-testid="acq-row"]').length,
      finBars: $('[data-testid="fin-bar"]').length,
      sentTiles: $('[data-testid="sentiment-tile"]').length,
      techRows: $('[data-testid="tech-row"]').length,
      techAbsent: $('[data-testid="tech-row"][data-status="ABSENT"]').length,
      gapRows: document.querySelector('[data-testid="gap-table"]')?.querySelectorAll("tbody tr")?.length ?? 0,
      subcapRows: $('[data-testid="subcap-row"]').length,
      ganttRows: $('[data-testid="gantt-row"]').length,
      pageText: (document.querySelector("main, .client-content, .page")?.innerText || "").slice(0, 6000),
    };
  });
}

async function sweepClient(ctx, did) {
  const page = await ctx.newPage();
  await page.route("**/*.{png,jpg,jpeg,svg,woff,woff2}", (r) => r.abort());
  const row = { did };
  const visits = [
    ["overview", `/clients/${did}`],
    ["insights", `/clients/${did}/insights`],
    ["heatmapFocus", `/clients/${did}/heatmap`],
    ["heatmapGrid", `/clients/${did}/heatmap?hm=standard&zoom=subcap`],
    ["platform", `/clients/${did}/platform`],
    ["context", `/clients/${did}/context`],
    ["techstack", `/clients/${did}/techstack`],
  ];
  for (const [key, hash] of visits) {
    try {
      await page.goto(`${BASE}/#${hash}`, { waitUntil: "domcontentloaded", timeout: 20000 });
      await page.waitForSelector(".card, .hm-cell, .fa-card, .empty", { timeout: 12000 }).catch(() => {});
      await page.waitForTimeout(1400);
      row[key] = await metrics(page);
      row[key].error = (await page.locator("text=/couldn't load|something went wrong/i").count()) > 0;
    } catch (e) {
      row[key] = { fatal: String(e).slice(0, 120) };
    }
  }
  await page.close();
  return row;
}

const browser = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
const ctx = await browser.newContext({ baseURL: BASE, viewport: { width: 1440, height: 900 } });
const r = await ctx.request.post(`${API}/api/v1/auth/dev-login?email=ae.test@zennify.com`);
const m = (r.headers()["set-cookie"] || "").match(/dma_session=([^;]+)/);
await ctx.addCookies([{ name: "dma_session", value: m[1], url: BASE }]);

fs.writeFileSync(OUT, "");
let i = 0;
async function worker() {
  for (;;) {
    const idx = i++;
    if (idx >= clients.length) return;
    const did = clients[idx];
    const row = await sweepClient(ctx, did);
    fs.appendFileSync(OUT, JSON.stringify(row) + "\n");
    if (idx % 10 === 0) console.log(`[${idx + 1}/${clients.length}] ${did}`);
  }
}
await Promise.all(Array.from({ length: WORKERS }, worker));
await browser.close();
console.log(`DONE -> ${OUT} (${clients.length} clients)`);
