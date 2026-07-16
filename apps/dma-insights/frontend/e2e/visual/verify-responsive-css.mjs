// Renders the REAL production app.css against a representative chrome/table/grid
// DOM in chromium at 1280 vs 760, asserting every responsive rule changed this
// session. No React needed — validates the CSS rules themselves for deviations.
import { chromium } from "@playwright/test";
import { fileURLToPath } from "node:url";
const STYLES = (f) => fileURLToPath(new URL(`../../styles/${f}`, import.meta.url));
let failures = 0;
const log = (ok, m) => { console.log(`${ok ? "PASS" : "FAIL"} · ${m}`); if (!ok) failures++; };

const DOM = `
<div class="shell">
  <aside class="sb" aria-label="nav"><div class="sb-head"></div><nav class="sb-nav"></nav></aside>
  <div class="main">
    <header class="topbar">
      <button class="sb-mobile-btn">menu</button>
      <div class="topbar-l"><div class="topbar-crumbs"><span class="current">Home</span></div></div>
    </header>
    <main class="page-main">
      <div id="grid" style="display:grid;grid-template-columns:1fr 280px;gap:28px"><div>a</div><div>b</div></div>
      <table class="tbl"><thead><tr><th>Date</th><th>Status</th></tr></thead>
        <tbody><tr><td data-label="Date">2024</td><td data-label="Status">Active</td></tr></tbody></table>
    </main>
  </div>
</div>`;

const b = await chromium.launch();
async function fixture(viewport) {
  const p = await b.newPage({ viewport });
  await p.setContent(`<!doctype html><html><head><meta charset="utf8"></head><body><div id="app">${DOM}</div></body></html>`);
  await p.addStyleTag({ path: STYLES("tokens.css") });
  await p.addStyleTag({ path: STYLES("app.css") });
  await p.waitForTimeout(150);
  return p;
}
const probe = (p) => p.evaluate(() => {
  const cs = (sel, ps) => { const el = document.querySelector(sel); return el ? (ps ? getComputedStyle(el, ps) : getComputedStyle(el)) : null; };
  const sb = document.querySelector(".sb");
  return {
    burger: cs(".sb-mobile-btn")?.display ?? "absent",
    sbLeft: sb ? Math.round(sb.getBoundingClientRect().left) : null,
    sbRight: sb ? Math.round(sb.getBoundingClientRect().right) : null,
    sbPos: cs(".sb")?.position,
    thead: cs(".tbl thead")?.display ?? "absent",
    td: cs(".tbl tbody td")?.display ?? "absent",
    tdBefore: cs(".tbl tbody td", "::before")?.content ?? "none",
    gridCols: cs("#grid")?.gridTemplateColumns,
  };
});

// Desktop 1280
const d = await fixture({ width: 1280, height: 900 });
const D = await probe(d);
log(D.burger === "none", `desktop: hamburger hidden (${D.burger})`);
log(D.sbLeft === 0 && D.sbPos === "sticky", `desktop: sidebar in-flow sticky left=0 (${D.sbPos}, ${D.sbLeft})`);
log(D.thead === "table-header-group", `desktop: table header visible (${D.thead})`);
log(D.gridCols.trim().split(/\s+/).length === 2, `desktop: 1fr 280px grid = 2 tracks (${D.gridCols})`);
await d.screenshot({ path: "/tmp/css-desktop.png" });

// Mobile 760
const m = await fixture({ width: 760, height: 1024 });
let M = await probe(m);
log(M.burger !== "none" && M.burger !== "absent", `mobile: hamburger visible (${M.burger})`);
log(M.sbPos === "fixed" && M.sbRight <= 6, `mobile: sidebar drawer fixed + off-screen (${M.sbPos}, right=${M.sbRight})`);
log(M.thead === "none", `mobile: table header hidden (${M.thead})`);
log(M.td === "flex", `mobile: table cell stacked flex (${M.td})`);
log(M.tdBefore.includes("Date"), `mobile: cell ::before shows data-label (${M.tdBefore})`);
log(M.gridCols.trim().split(/\s+/).length === 1, `mobile: inline 2-col grid reflows to 1 track (${M.gridCols})`);
// drawer opens when .open added
await m.evaluate(() => document.querySelector(".sb").classList.add("open"));
await m.waitForTimeout(250);
const openLeft = await m.evaluate(() => Math.round(document.querySelector(".sb").getBoundingClientRect().left));
log(openLeft >= -2 && openLeft <= 1, `mobile: .sb.open slides drawer to left=0 (${openLeft})`);
await m.screenshot({ path: "/tmp/css-mobile.png" });

await b.close();
console.log(`\n${failures === 0 ? "ALL CSS CHECKS PASSED ✓" : failures + " FAILED ✗"}`);
process.exit(failures === 0 ? 0 : 1);
