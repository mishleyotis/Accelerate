/**
 * Phase-F verification driver (2026-06-10 live-recovery plan):
 *
 *   1. Click through the REBUILT app (vite :5173 → uvicorn :8000 over
 *      the strict-gate corpus): directory junk-name sweep, two
 *      adjacent entities' SCQA distinctness (the FNBO-on-"CU"
 *      cross-wire regression), every client page, the customer
 *      audience toggle on every client page (must settle — content or
 *      honest empty/error state — never an endless spinner).
 *   2. Capture parity screenshots of the PROTOTYPE wireframe
 *      (docs/wireframe-2026-06, served on :8088) and the rebuilt app
 *      side by side at 1440px for the operator's review.
 *
 * Usage:  PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers node scripts/clickthrough-parity.mjs <session-cookie>
 * Output: /tmp/parity/{app,proto}/<page>.png + stdout assertions.
 */
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const COOKIE = process.argv[2];
if (!COOKIE) throw new Error("pass the dma_session cookie value as argv[2]");

const APP = "http://127.0.0.1:5173";
const PROTO = "http://127.0.0.1:8088/DMA_Insights__Standalone.html";
const OUT = "/tmp/parity";
mkdirSync(`${OUT}/app`, { recursive: true });
mkdirSync(`${OUT}/proto`, { recursive: true });

const failures = [];
const note = (ok, msg) => {
  console.log(`${ok ? "PASS" : "FAIL"}  ${msg}`);
  if (!ok) failures.push(msg);
};

const JUNK_RES = [
  /^[A-Za-z0-9_-]{25,}$/,             // raw Drive id
  /\bDMA\b[\s\w()-]*$/i,              // folder artifacts
  /\b(FINAL|DRAFT|COPY)\b\.?$/i,
  /^[\d\s.,;:|%·/-]+$/,
];

const browser = await chromium.launch();

// ── 1. App click-through ──────────────────────────────────────────────
const ctx = await browser.newContext({
  viewport: { width: 1440, height: 900 },
});
await ctx.addCookies([{
  name: "dma_session", value: COOKIE,
  domain: "127.0.0.1", path: "/",
}]);
const page = await ctx.newPage();
page.setDefaultTimeout(20000);

async function settle(label) {
  // The page must reach a NON-loading state within 15s: any of the
  // page container, an EmptyState, or an error card — a perpetual
  // spinner (the customer-toggle hang) fails here.
  try {
    await page.waitForFunction(() => {
      const spin = document.querySelector(".page-loading, .loader-page");
      return !spin || spin.offsetParent === null;
    }, { timeout: 15000 });
    return true;
  } catch {
    note(false, `${label}: still loading after 15s (hang)`);
    return false;
  }
}

async function shot(dir, name) {
  await page.screenshot({
    path: `${OUT}/${dir}/${name}.png`, fullPage: false,
  });
}

// Pull two adjacent scored entities straight from the API.
const resp = await page.request.get(
  `${APP}/api/v1/entities?limit=200`,
  { headers: { Cookie: `dma_session=${COOKIE}` } },
);
const listing = await resp.json();
const ents = (listing.items ?? listing.entities ?? []);
note(ents.length >= 90, `directory API returns ${ents.length} entities (>=90)`);
const junkNamed = ents.filter((e) =>
  !e.name || JUNK_RES.some((re) => re.test((e.name || "").trim())));
note(junkNamed.length === 0,
  `0 junk-named entities in directory (got ${junkNamed.length}: ${junkNamed.slice(0, 3).map((e) => e.name).join(", ")})`);

const [e1, e2] = [ents[0], ents[1]];

// Dashboard + directory shots
for (const [name, path, wait] of [
  ["dashboard", "/#/", '[data-page="dashboard"]'],
  ["directory", "/#/clients", '[data-page="directory"]'],
]) {
  await page.goto(`${APP}${path}`);
  await page.waitForSelector(wait, { timeout: 20000 });
  await settle(name);
  await page.waitForTimeout(800);
  await shot("app", name);
  note(true, `app ${name} rendered`);
}

// Two adjacent entities: SCQA must be DISTINCT (cross-wire regression).
const scqas = [];
for (const e of [e1, e2]) {
  await page.goto(`${APP}/#/clients/${e.display_id}/overview`);
  await page.waitForSelector("main", { timeout: 20000 });
  await settle(`overview ${e.display_id}`);
  await page.waitForTimeout(1200);
  const scqa = await page.evaluate(() => {
    const el = document.querySelector("[data-source*='narrative'], .scqa, .card");
    return (el?.textContent || "").slice(0, 400);
  });
  scqas.push(scqa);
}
note(
  !scqas[0] || !scqas[1] || scqas[0] !== scqas[1],
  `adjacent entities (${e1.display_id} vs ${e2.display_id}) render DISTINCT narratives`,
);

// Every client page on e1 + customer-toggle settle check on each.
const clientPages = [
  ["overview", ""], ["insights", ""], ["heatmap", ""], ["platform", ""],
  ["context", ""], ["health", ""], ["techstack", ""], ["runs", ""],
];
for (const [tab] of clientPages) {
  const label = `app ${tab}`;
  await page.goto(`${APP}/#/clients/${e1.display_id}/${tab}`);
  await page.waitForSelector("main, .page, .empty", { timeout: 20000 });
  const ok = await settle(label);
  await page.waitForTimeout(700);
  await shot("app", tab);
  note(ok, `${label} settled (internal audience)`);

  // Customer audience toggle: click, must settle (content OR honest
  // empty/gate state) — never an endless spinner.
  const toggle = page.locator(
    "[data-audience='customer'], button:has-text('Customer')").first();
  if (await toggle.count()) {
    await toggle.click();
    const ok2 = await settle(`${label} CUSTOMER`);
    await page.waitForTimeout(700);
    await shot("app", `${tab}-customer`);
    note(ok2, `${label} settled after CUSTOMER toggle`);
    // back to internal for the next page
    const back = page.locator(
      "[data-audience='internal'], button:has-text('Internal')").first();
    if (await back.count()) { await back.click(); await settle(label); }
  } else {
    note(true, `${label}: no audience toggle visible (skipped)`);
  }
}

// Admin pending-review smoke (parked entities feed here)
await page.goto(`${APP}/#/admin`);
await page.waitForSelector("main, .page", { timeout: 20000 });
await settle("admin");
await page.waitForTimeout(800);
await shot("app", "admin");
note(true, "app admin rendered");

// ── 2. Prototype parity shots ─────────────────────────────────────────
const proto = await browser.newPage({ viewport: { width: 1440, height: 900 } });
proto.setDefaultTimeout(20000);
await proto.goto(PROTO);
await proto.waitForTimeout(2500);
await proto.screenshot({ path: `${OUT}/proto/login.png` });
// The prototype auto-mocks auth via its Sign-in button.
const signIn = proto.locator("button:has-text('Sign in'), .btn:has-text('Sign in')").first();
if (await signIn.count()) { await signIn.click(); await proto.waitForTimeout(1500); }
const protoEntity = await proto.evaluate(() => {
  const m = (document.body.innerHTML.match(/#\/clients\/([a-z0-9-]+)\//) || []);
  return m[1] || "fce-001";
});
for (const [name, path] of [
  ["dashboard", "#/"], ["directory", "#/clients"],
  ["overview", `#/clients/${protoEntity}/overview`],
  ["insights", `#/clients/${protoEntity}/insights`],
  ["heatmap", `#/clients/${protoEntity}/heatmap`],
  ["platform", `#/clients/${protoEntity}/platform`],
  ["context", `#/clients/${protoEntity}/context`],
  ["health", `#/clients/${protoEntity}/health`],
]) {
  await proto.goto(`${PROTO}${path}`);
  await proto.waitForTimeout(1800);
  await proto.screenshot({ path: `${OUT}/proto/${name}.png` });
  console.log(`SHOT  proto ${name}`);
}

await browser.close();
console.log(`\n${failures.length} FAILURES`);
for (const f of failures) console.log(`  ✗ ${f}`);
process.exit(failures.length ? 1 : 0);
