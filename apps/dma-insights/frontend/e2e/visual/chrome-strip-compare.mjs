// Chrome-strip comparison: prototype vs production TOP of every route.
//
// The 2026-06-10 operator screenshots showed top-of-page divergences the
// full-page composites under-weighted (crumb composition, ClientBar pill
// styling, audience-toggle placement). This harness clips ONLY the chrome
// region (topbar + client bar + tabs + page-head ≈ top 240px) for every
// route on both sides and tiles them into one contact sheet per width,
// so a chrome regression on ANY page is visible at a glance.
//
// Run: node e2e/visual/chrome-strip-compare.mjs [width=1280] [entity]
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const PE = "fce-001";
const DE = process.argv[3] ?? "corporate-america-credit-0001";
const PROTO = "http://127.0.0.1:8090/DMA_Insights__Standalone.html#";
const PROD = "http://127.0.0.1:8085/#";
const ADMIN_EMAIL = "chris.conant@zennify.com";
const W = Number(process.argv[2] ?? 1280);
const STRIP_H = 250;
const OUT = `/tmp/chrome-strips-${W}`;

const PAGES = [
  ["dashboard", "/", "/"],
  ["directory", "/clients", "/clients"],
  ["overview", `/clients/${PE}/overview`, `/clients/${DE}/overview`],
  ["insights", `/clients/${PE}/insights`, `/clients/${DE}/insights`],
  ["heatmap", `/clients/${PE}/heatmap`, `/clients/${DE}/heatmap`],
  ["platform", `/clients/${PE}/platform`, `/clients/${DE}/platform`],
  ["context", `/clients/${PE}/context`, `/clients/${DE}/context`],
  ["health", `/clients/${PE}/health`, `/clients/${DE}/health`],
  ["techstack", `/clients/${PE}/techstack`, `/clients/${DE}/techstack`],
  ["runs", `/clients/${PE}/runs`, `/clients/${DE}/runs`],
  ["alerts", "/alerts", "/alerts"],
  ["admin", "/admin", "/admin"],
];

mkdirSync(OUT, { recursive: true });
const b = await chromium.launch();
const vp = { width: W, height: 900 };
const protoCtx = await b.newContext({ viewport: vp });
const prodCtx = await b.newContext({ viewport: vp });
await prodCtx.request.post(
  `${PROD.replace(/#$/, "")}api/v1/auth/dev-login?email=${encodeURIComponent(ADMIN_EMAIL)}`,
);

async function settle(p) {
  await p.waitForSelector("aside, nav, .sidebar, [data-page], main", { timeout: 12000 }).catch(() => {});
  await p.waitForFunction(
    () => !/Loading DMA Insights/i.test(document.body?.innerText || ""),
    { timeout: 12000 },
  ).catch(() => {});
  await p.waitForTimeout(1500);
}

const protoPage = await protoCtx.newPage();
await protoPage.goto(PROTO + "/login", { waitUntil: "domcontentloaded", timeout: 25000 }).catch(() => {});
const inp = await protoPage.waitForSelector('input[type="email"]', { timeout: 12000 }).catch(() => null);
if (inp) {
  await inp.fill("admin@zennify.com");
  const btn = await protoPage.$("button.btn-primary");
  if (btn) await btn.click();
  await protoPage.waitForFunction(
    () => !/Verifying with Google|Setting up your workspace/i.test(document.body?.innerText || ""),
    { timeout: 12000 },
  ).catch(() => {});
  await protoPage.waitForTimeout(400);
}
const prodPage = await prodCtx.newPage();

const strips = [];
for (const [name, pp, dp] of PAGES) {
  await protoPage.evaluate((h) => { window.location.hash = h; }, pp);
  await settle(protoPage);
  const a = (await protoPage.screenshot({ clip: { x: 0, y: 0, width: W, height: STRIP_H } })).toString("base64");
  try { await prodPage.goto(PROD + dp, { waitUntil: "domcontentloaded", timeout: 25000 }); } catch { /* */ }
  await settle(prodPage);
  const c = (await prodPage.screenshot({ clip: { x: 0, y: 0, width: W, height: STRIP_H } })).toString("base64");
  strips.push([name, a, c]);
  console.log("strip", name);
}

const comp = await b.newPage({
  viewport: { width: W + 40, height: Math.min(12000, strips.length * (2 * STRIP_H + 56) + 40) },
});
const rows = strips.map(([n, a, c]) => `
  <div style="margin-bottom:18px">
    <div style="color:#62D7B8;font:700 13px Arial;padding:4px 2px">${n} — PROTOTYPE</div>
    <img width="${W}" src="data:image/png;base64,${a}" style="display:block;border:1px solid #1C4A4D"/>
    <div style="color:#FE9732;font:700 13px Arial;padding:4px 2px">${n} — PRODUCTION</div>
    <img width="${W}" src="data:image/png;base64,${c}" style="display:block;border:1px solid #1C4A4D"/>
  </div>`).join("");
await comp.setContent(`<!doctype html><body style="margin:0;background:#0b1f21;padding:20px">${rows}</body>`);
await comp.waitForTimeout(200);
// Split into 4-page sheets so each PNG stays reviewable.
for (let s = 0; s * 4 < strips.length; s++) {
  const slice = strips.slice(s * 4, s * 4 + 4);
  const rs = slice.map(([n, a, c]) => `
    <div style="margin-bottom:18px">
      <div style="color:#62D7B8;font:700 13px Arial;padding:4px 2px">${n} — PROTOTYPE</div>
      <img width="${W}" src="data:image/png;base64,${a}" style="display:block;border:1px solid #1C4A4D"/>
      <div style="color:#FE9732;font:700 13px Arial;padding:4px 2px">${n} — PRODUCTION</div>
      <img width="${W}" src="data:image/png;base64,${c}" style="display:block;border:1px solid #1C4A4D"/>
    </div>`).join("");
  await comp.setContent(`<!doctype html><body style="margin:0;background:#0b1f21;padding:20px">${rs}</body>`);
  await comp.waitForTimeout(150);
  await comp.screenshot({ path: `${OUT}/chrome-${s + 1}.png`, fullPage: true });
}
await b.close();
console.log(`\nchrome strips -> ${OUT}/`);
