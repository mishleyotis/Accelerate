// Prototype vs production side-by-side comparison generator.
//
// Renders each route in BOTH the 2026-06 prototype (served from
// docs/wireframe-2026-06 on :8090) and the populated production standalone
// build (served on :8081), then composites them into one labelled image per
// page under /tmp/sbs/. Pure Playwright — no image deps.
//
// Prereqs:
//   pnpm build:standalone
//   (cd dist-standalone && python3 ../dist-standalone-server.py 8081 .)  # prod
//   (cd ../docs/wireframe-2026-06 && python3 -m http.server 8090)        # prototype
// Run:  node e2e/visual/side-by-side.mjs [width]
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const PE = "fce-001";                              // prototype entity
const DE = "richbank-community-trust-0001";        // production mock entity
const PROTO = "http://localhost:8090/DMA_Insights__Standalone.html#";
const PROD = "http://localhost:8081/#";
const W = Number(process.argv[2] ?? 1280);
const H = W < 600 ? 1400 : 880;
const OUT = "/tmp/sbs";

const PAGES = [
  ["dashboard", "/", "/"],
  ["directory", "/clients", "/clients"],
  ["overview", `/clients/${PE}/overview`, `/clients/${DE}/overview`],
  ["insights", `/clients/${PE}/insights`, `/clients/${DE}/insights`],
  ["heatmap", `/clients/${PE}/heatmap`, `/clients/${DE}/heatmap`],
  ["platform", `/clients/${PE}/platform`, `/clients/${DE}/platform`],
  ["context", `/clients/${PE}/context`, `/clients/${DE}/context`],
  ["health", `/clients/${PE}/health`, `/clients/${DE}/health`],
  ["runs", `/clients/${PE}/runs`, `/clients/${DE}/runs`],
  ["alerts", "/alerts", "/alerts"],
  ["prospecting", "/prospecting", "/prospecting"],
  ["admin", "/admin", "/admin"],
];

mkdirSync(OUT, { recursive: true });
const b = await chromium.launch();
const vp = { width: W, height: H };

async function cap(base, path) {
  const p = await b.newPage({ viewport: vp });
  try { await p.goto(base + path, { waitUntil: "networkidle", timeout: 20000 }); } catch { /* best-effort */ }
  await p.waitForTimeout(1200);
  const buf = await p.screenshot({ clip: { x: 0, y: 0, ...vp } });
  await p.close();
  return buf.toString("base64");
}

const comp = await b.newPage({ viewport: { width: 2 * W + 60, height: H + 54 } });
for (const [name, pp, dp] of PAGES) {
  const [proto, prod] = await Promise.all([cap(PROTO, pp), cap(PROD, dp)]);
  await comp.setContent(
    `<!doctype html><html><body style="margin:0;background:#0b1f21;font-family:'DM Sans',Arial,sans-serif">
      <div style="display:flex;gap:20px;padding:20px">
        <div><div style="color:#62D7B8;font-weight:700;font-size:15px;padding:6px 2px">PROTOTYPE — ${name}</div><img width="${W}" src="data:image/png;base64,${proto}"/></div>
        <div><div style="color:#FE9732;font-weight:700;font-size:15px;padding:6px 2px">PRODUCTION — ${name}</div><img width="${W}" src="data:image/png;base64,${prod}"/></div>
      </div></body></html>`,
  );
  await comp.waitForTimeout(150);
  await comp.screenshot({ path: `${OUT}/sbs-${name}.png` });
  console.log("composited", name);
}
await b.close();
console.log(`\nSide-by-side images written to ${OUT}/ (width ${W}).`);
