// Prototype vs LIVE-BACKEND production side-by-side generator.
//
// Unlike side-by-side.mjs (which renders the standalone MOCK build), this
// drives the REAL Vite `dist/` bundle talking to the live Postgres-backed
// API through the same-origin proxy, authenticated as a real ADMIN session
// via /auth/dev-login. It proves the production frontend renders prototype-
// faithful pages when plugged into actual backend data.
//
// Prereqs (all already running for this capture):
//   uvicorn app.main:app --port 8000           # live backend (ENV=local, seeded DB)
//   python e2e/visual/live-proxy.py 8085 dist 8000   # same-origin static+API proxy
//   (cd docs/wireframe-2026-06 && python3 -m http.server 8090)  # prototype
// Run:  node e2e/visual/side-by-side-live.mjs [width] [entity]
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const PE = "fce-001";                                  // prototype demo entity
const DE = process.argv[3] ?? "alma-bank-0001";        // live backend entity
// :8091 = scratchpad/serve_proto.py — resolves the standalone's extension-
// less UUID module imports to the uploaded prototype's .js/.jsx files
// (plain http.server 404s them and the prototype hangs on its boot splash).
const PROTO = "http://127.0.0.1:8091/DMA_Insights__Standalone.html#";
const PROD = "http://127.0.0.1:8085/#";
const ADMIN_EMAIL = "chris.conant@zennify.com";
const W = Number(process.argv[2] ?? 1280);
const H = W < 600 ? 1500 : 900;
// Width-suffixed so a mobile run can't overwrite the desktop set.
const OUT = `/tmp/sbs-live-${W}`;

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

// ── F9: interaction-state drivers ────────────────────────────────────────
// Each entry opens a stateful surface (modal / drawer / tab / view switch)
// BEFORE the screenshot, so transitions and popups are proven by pixels
// rather than source-read. Drivers run identically on both sides — the
// production bundle ships the prototype's class names (.ic, .hm-cell,
// role=tab, roadmap view buttons), so a selector that misses on one side
// is silently skipped (best-effort) and the composite shows the gap.
async function clickSel(p, sel) {
  const el = await p.waitForSelector(sel, { timeout: 6000 }).catch(() => null);
  if (el) await el.click().catch(() => {});
  await p.waitForTimeout(900);
}
async function clickText(p, text) {
  await p.locator(`button:has-text("${text}")`).first()
    .click({ timeout: 6000 }).catch(() => {});
  await p.waitForTimeout(900);
}

const STATES = [
  // InsightModal — tabbed (F4): detail tab on open, then the evidence tab.
  ["insights-modal-detail", `/clients/${PE}/insights`, `/clients/${DE}/insights`,
    async (p) => { await clickSel(p, ".ic"); }],
  ["insights-modal-evidence", `/clients/${PE}/insights`, `/clients/${DE}/insights`,
    async (p) => { await clickSel(p, ".ic"); await clickText(p, "Evidence"); }],
  // Heatmap — cell click opens the SynthesisDrawer; mode toggle to Standard
  // exercises the zoom ladder's top level.
  ["heatmap-synthesis-drawer", `/clients/${PE}/heatmap`, `/clients/${DE}/heatmap`,
    async (p) => { await clickSel(p, ".hm-cell"); }],
  ["heatmap-standard", `/clients/${PE}/heatmap`, `/clients/${DE}/heatmap`,
    async (p) => { await clickText(p, "Standard"); }],
  // TransformationRoadmap — the two non-default views (chevrons is default).
  ["platform-roadmap-curve", `/clients/${PE}/platform`, `/clients/${DE}/platform`,
    async (p) => { await clickText(p, "Step curve"); }],
  ["platform-roadmap-impact", `/clients/${PE}/platform`, `/clients/${DE}/platform`,
    async (p) => { await clickText(p, "Customer impact"); }],
  // Health — non-default tabs (alerts is default).
  ["health-tab-diff", `/clients/${PE}/health`, `/clients/${DE}/health`,
    async (p) => { await clickText(p, "Version diff"); }],
  ["health-tab-gates", `/clients/${PE}/health`, `/clients/${DE}/health`,
    async (p) => { await clickText(p, "Safeguard gates"); }],
  ["health-tab-age", `/clients/${PE}/health`, `/clients/${DE}/health`,
    async (p) => { await clickText(p, "Evidence age"); }],
];

mkdirSync(OUT, { recursive: true });
const b = await chromium.launch(process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {});
const vp = { width: W, height: H };

// One context per side. The PROD context carries the dev-login cookie.
const protoCtx = await b.newContext({ viewport: vp });
const prodCtx = await b.newContext({ viewport: vp });
const loginResp = await prodCtx.request.post(
  `${PROD.replace(/#$/, "")}api/v1/auth/dev-login?email=${encodeURIComponent(ADMIN_EMAIL)}`,
);
console.log("dev-login:", loginResp.status(), (await loginResp.text()).slice(0, 80));

async function settle(p) {
  // Both bundles boot through an animated loader (glyphPulse/ringSpin) that
  // never settles networkidle; wait for real chrome to mount and the loader
  // text to detach so the composite compares mounted UI, not the splash.
  await p.waitForSelector("aside, nav, .sidebar, .topbar, [data-page], main", {
    timeout: 12000,
  }).catch(() => {});
  await p.waitForFunction(
    () => !/Loading DMA Insights/i.test(document.body?.innerText || ""),
    { timeout: 12000 },
  ).catch(() => {});
  await p.waitForTimeout(1600);
}

// Production: cookie session already in the context — direct goto works.
async function capProd(path, driver) {
  const p = await prodCtx.newPage();
  try { await p.goto(PROD + path, { waitUntil: "domcontentloaded", timeout: 25000 }); }
  catch { /* best-effort */ }
  await settle(p);
  if (driver) await driver(p);
  const buf = await p.screenshot({ clip: { x: 0, y: 0, ...vp } });
  await p.close();
  return buf.toString("base64");
}

// Prototype: in-memory mock auth resets per page, so sign in (admin email →
// ADMIN role, ungated pages) then set the hash to the target route.
async function capProto(path, driver) {
  const p = await protoCtx.newPage();
  try { await p.goto(PROTO + "/login", { waitUntil: "domcontentloaded", timeout: 25000 }); }
  catch { /* best-effort */ }
  // The login form only appears AFTER the prototype's own boot loader
  // mounts — wait for the email input rather than a fixed delay.
  // Older revisions expose an email input; the 2026-06 upload replaced it
  // with a single "Continue with Google" mock button — support both.
  const input = await p.waitForSelector('input[type="email"], button:has-text("Continue with Google")', { timeout: 12000 })
    .catch(() => null);
  if (input) {
    const tag = await input.evaluate((el) => el.tagName.toLowerCase());
    if (tag === "input") {
      await input.fill("admin@zennify.com");
      const btn = await p.$('button.btn-primary');
      if (btn) await btn.click();
    } else {
      await input.click();
    }
    // signIn runs ~1.2s of verifying/granting phases, then navigates to "/".
    await p.waitForFunction(
      () => !/Verifying with Google|Setting up your workspace/i.test(document.body?.innerText || ""),
      { timeout: 12000 },
    ).catch(() => {});
    await p.waitForTimeout(400);
  }
  await p.evaluate((h) => { window.location.hash = h; }, path);
  await settle(p);
  if (driver) await driver(p);
  const buf = await p.screenshot({ clip: { x: 0, y: 0, ...vp } });
  await p.close();
  return buf.toString("base64");
}

const comp = await b.newPage({ viewport: { width: 2 * W + 60, height: H + 54 } });
const summary = [];
// Default-state route sweep, then the F9 interaction states (skip the
// state sweep at mobile widths — popovers/drawers go full-screen there
// and the default sweep already proves the reflow).
const TARGETS = W >= 900
  ? [...PAGES.map(([n, pp, dp]) => [n, pp, dp, null]), ...STATES.map(([n, pp, dp, d]) => [`state-${n}`, pp, dp, d])]
  : PAGES.map(([n, pp, dp]) => [n, pp, dp, null]);
for (const [name, pp, dp, driver] of TARGETS) {
  const [proto, prod] = await Promise.all([
    capProto(pp, driver),
    capProd(dp, driver),
  ]);
  await comp.setContent(
    `<!doctype html><html><body style="margin:0;background:#0b1f21;font-family:'DM Sans',Arial,sans-serif">
      <div style="display:flex;gap:20px;padding:20px">
        <div><div style="color:#62D7B8;font-weight:700;font-size:15px;padding:6px 2px">PROTOTYPE — ${name}</div><img width="${W}" src="data:image/png;base64,${proto}"/></div>
        <div><div style="color:#FE9732;font-weight:700;font-size:15px;padding:6px 2px">PRODUCTION (live ${DE}) — ${name}</div><img width="${W}" src="data:image/png;base64,${prod}"/></div>
      </div></body></html>`,
  );
  await comp.waitForTimeout(150);
  await comp.screenshot({ path: `${OUT}/sbs-${name}.png` });
  summary.push(name);
  console.log("composited", name);
}
await b.close();
console.log(`\nLive side-by-side images -> ${OUT}/ (width ${W}, entity ${DE}): ${summary.join(", ")}`);
