// Full-corpus render sweep: EVERY entity x EVERY client route, live backend.
//
// Proves the production bundle renders (mounts chrome + page, no error
// EmptyState, no white screen) for the WHOLE seeded corpus — the
// "across all 96 clients" non-negotiable. Complements side-by-side-live.mjs
// (which proves prototype parity in depth on representative entities) by
// proving breadth: no client x page combination errors out.
//
// Per page-load classification:
//   OK      — [data-page] mounted AND no "Couldn't load" error state
//   EMPTY   — mounted but the page shows an honest EmptyState (data-absent)
//   ERROR   — error EmptyState ("Couldn't load ...") or page never mounted
//
// Outputs /tmp/corpus-sweep/report.tsv + per-entity overview thumbnails +
// a contact-sheet grid PNG per 24 entities, and exits non-zero if any ERROR.
//
// Prereqs: live proxy on :8085 (dist + API), backend seeded.
// Run: node e2e/visual/corpus-sweep.mjs [width=1280] [pagesCsv]
import { chromium } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";

const PROD = "http://127.0.0.1:8085/#";
const ADMIN_EMAIL = "chris.conant@zennify.com";
const W = Number(process.argv[2] ?? 1280);
const H = 900;
const OUT = "/tmp/corpus-sweep";
const PAGES = (process.argv[3] ?? "overview,insights,heatmap,platform,context,health,techstack,runs").split(",");

mkdirSync(OUT, { recursive: true });
const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: W, height: H } });
const login = await ctx.request.post(
  `${PROD.replace(/#$/, "")}api/v1/auth/dev-login?email=${encodeURIComponent(ADMIN_EMAIL)}`,
);
if (login.status() !== 200) { console.error("dev-login failed", login.status()); process.exit(2); }

const entities = [];
{
  const r = await ctx.request.get(`${PROD.replace(/#$/, "")}api/v1/entities?owner=all&limit=500`);
  const body = await r.json();
  for (const e of body.items ?? []) entities.push(e.display_id);
}
console.log(`sweeping ${entities.length} entities x ${PAGES.length} pages @ ${W}px`);

const rows = [["display_id", "page", "verdict", "note"]];
let nOk = 0, nEmpty = 0, nErr = 0;
const thumbs = [];

const p = await ctx.newPage();
for (const [ei, ent] of entities.entries()) {
  for (const page of PAGES) {
    const url = `${PROD}/clients/${ent}/${page}`;
    let verdict = "ERROR", note = "";
    try {
      await p.goto(url, { waitUntil: "domcontentloaded", timeout: 20000 });
      await p.waitForSelector("[data-page], .page, main", { timeout: 12000 });
      // Allow queries to settle (spinner -> content or empty state).
      await p.waitForFunction(
        () => !document.querySelector(".page-loading"),
        { timeout: 15000 },
      ).catch(() => {});
      await p.waitForTimeout(250);
      const txt = await p.evaluate(() => document.body?.innerText || "");
      if (/Couldn't load|Backend data failed|Something went wrong/i.test(txt)) {
        verdict = "ERROR"; note = "error empty-state";
      } else if (await p.$("[data-page], .page-head, .page")) {
        // Honest EmptyState vs populated: presence of `.empty` with no data rows.
        const hasEmpty = await p.$(".empty, [data-source$='-pending']");
        const hasData = await p.evaluate(() =>
          !!document.querySelector("table tbody tr, .ic, .hm-cell, .card-tile, .tl-row, .g2 .card, .stat, .fa-card"));
        verdict = hasData ? "OK" : hasEmpty ? "EMPTY" : "OK";
      } else { verdict = "ERROR"; note = "page never mounted"; }
    } catch (e) {
      verdict = "ERROR"; note = String(e?.message ?? e).split("\n")[0].slice(0, 120);
    }
    rows.push([ent, page, verdict, note]);
    if (verdict === "OK") nOk++; else if (verdict === "EMPTY") nEmpty++; else nErr++;
    if (verdict === "ERROR") console.log("ERROR", ent, page, note);
  }
  // Per-entity overview thumbnail for the contact sheet.
  try {
    await p.goto(`${PROD}/clients/${ent}/overview`, { waitUntil: "domcontentloaded", timeout: 20000 });
    await p.waitForSelector("[data-page]", { timeout: 10000 }).catch(() => {});
    await p.waitForFunction(() => !document.querySelector(".page-loading"), { timeout: 12000 }).catch(() => {});
    await p.waitForTimeout(200);
    const buf = await p.screenshot({ clip: { x: 0, y: 0, width: W, height: 620 } });
    thumbs.push([ent, buf.toString("base64")]);
  } catch { /* thumbnail best-effort */ }
  if ((ei + 1) % 10 === 0) console.log(`  ...${ei + 1}/${entities.length}`);
}

writeFileSync(`${OUT}/report.tsv`, rows.map((r) => r.join("\t")).join("\n"));

// Contact sheets: 24 thumbnails per sheet, 4 columns.
const comp = await b.newPage({ viewport: { width: 4 * 330 + 50, height: 6 * 190 + 60 } });
for (let s = 0; s * 24 < thumbs.length; s++) {
  const batch = thumbs.slice(s * 24, s * 24 + 24);
  const cells = batch.map(([id, b64]) =>
    `<div style="width:320px"><div style="color:#62D7B8;font:600 10px 'DM Sans',Arial;padding:2px">${id}</div>
     <img width="320" style="border:1px solid #1C4A4D" src="data:image/png;base64,${b64}"/></div>`).join("");
  await comp.setContent(`<!doctype html><body style="margin:0;background:#0b1f21">
    <div style="display:flex;flex-wrap:wrap;gap:8px;padding:10px">${cells}</div></body>`);
  await comp.waitForTimeout(120);
  await comp.screenshot({ path: `${OUT}/contact-sheet-${s + 1}.png`, fullPage: true });
}

await b.close();
console.log(`\n# CORPUS SWEEP: ${nOk} OK, ${nEmpty} EMPTY(honest), ${nErr} ERROR across ${entities.length} entities x ${PAGES.length} pages -> ${OUT}/`);
process.exit(nErr > 0 ? 1 : 0);
