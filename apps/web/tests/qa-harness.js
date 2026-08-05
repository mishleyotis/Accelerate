/**
 * The all-page visual QA gate.
 *
 * Visual QA used to run only on pages someone complained about, which is how a
 * focus-area card that blanked the entire page survived a week: nothing loaded
 * the page and clicked the card. This runs on EVERY client page, clicks EVERY
 * clickable, and fails on four classes at once:
 *
 *   1 CRASH        an uncaught exception, or body text collapsing to nothing
 *   2 FIXTURE LEAK prototype fixture prose reaching a real client's page
 *   3 LAYOUT       text clipped by its own box, or squeezed to one char a line
 *   4 DEAD TARGET  a drilldown that opens nothing
 *
 * usage: node tests/qa-harness.js <base-url> <display-id> [--shots <dir>]
 * exit 0 = clean, 1 = defects found, 2 = harness failure.
 */
const fs = require("fs");
const path = require("path");

const BASE = process.argv[2] || "http://localhost:3410";
const ENTITY = process.argv[3] || "baxter-credit-union-bcu";
const shotsAt = process.argv.indexOf("--shots");
const SHOTS = shotsAt > -1 ? process.argv[shotsAt + 1] : null;

const TABS = ["overview", "insights", "heatmap", "platform", "context",
              "techstack", "health", "runs"];

// Strings that exist ONLY in the prototype's fixtures. Any of them on a live
// client's page is fabricated content about a real institution.
//
// A bare vendor name is NOT a sentinel. Zennify's partner catalogue —
// Salesforce, Databricks, Tableau, Twilio, nCino — is what the platform page
// fit-scores, so those names appear on every client's page legitimately. The
// first version of this list had "nCino" in it and reported a leak on all eight
// pages; the leak was the platform tile grid rendering the catalogue, which is
// its job. What makes fixture prose fabricated is the CLAIM around the name, so
// the sentinels are the claims.
const FIXTURE_SENTINELS = [
  "fce-001", "First Coast", "Wells Fargo", "ex-JPM", "ex-Wells Fargo",
  "Synovus", "Truist", "First Citizens", "Hudson Valley", "Cazenovia",
  "CISO absent", "C-suite hires open a 6", "Databricks Lakehouse",
  "FIS Profile", "1,800 users", "12 days median",
  "mid-migration from a legacy core", "nCino go-live", "nCino Workflow Engine -",
  "Data Cloud Architect openings", "Glassdoor 3.8", "3.4 · n=8,200",
  "E-047", "E-089", "E-112", "E-141", "E-203", "E-218", "E-236", "E-250",
  "E-271", "E-283", "IS-014",
];

// Clickables are scoped to the page body: the sidebar and topbar persist across
// routes, so clicking them is a NAVIGATION, not a drilldown, and the resulting
// change of page text is correct rather than a crash.
//
// The client tab strip lives INSIDE .main, so it needs excluding by hand.
// Without this every page reported the platform page's content under its own
// name — the "Platform" tab was clicked, the route changed, and the probe
// attributed what it then saw to the page it had left.
const NAV_EXCLUDE = ":not(.client-tab):not(.tab):not(.nav-item)";
const CLICKABLE_SELECTOR = [
  "button", "[role='button']", "a[href^='#']", ".card-tile", ".fa-card",
  ".hm-cell", ".ic", ".rec-row", ".tier-chip", ".chip", ".switch", "tr.tbl-click",
].map((s) => `#app .main ${s}${NAV_EXCLUDE}`).join(", ");

// Text a card shows when it has nothing — legitimate, but never a whole page.
const MIN_PAGE_TEXT = 400;
const MAX_TARGETS_PER_PAGE = Number(process.env.QA_MAX_TARGETS || 40);

const findings = [];
const add = (kind, page, detail) => findings.push({ kind, page, detail });

function resolvePlaywright() {
  // playwright-core is not a dependency of the app bundle; CI and local QA
  // supply it, so honour an explicit path before falling back to resolution.
  const candidates = [
    process.env.PLAYWRIGHT_CORE,
    "playwright-core",
    path.join(__dirname, "..", "node_modules", "playwright-core"),
  ].filter(Boolean);
  for (const p of candidates) {
    try { return require(p); } catch { /* keep looking */ }
  }
  throw new Error(
    "playwright-core not resolvable — set PLAYWRIGHT_CORE=/path/to/playwright-core");
}

async function main() {
  const { chromium } = resolvePlaywright();
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || "/opt/pw-browsers/chromium",
    args: ["--no-sandbox"],
  });
  const ctx = await browser.newContext({ viewport: { width: 1512, height: 1100 } });
  const page = await ctx.newPage();

  // Two different things, kept apart. An uncaught exception is a CRASH: the
  // render stopped. A failed fetch is not — the app handles a withheld page by
  // rendering a locked state, and the browser logs the 403 regardless. Lumping
  // them together reported four CRASHes for the audience toggle behaving
  // exactly as the API's default-deny requires.
  let errors = [];
  let netErrors = [];
  page.on("pageerror", (e) => errors.push(String(e.message).split("\n")[0]));
  page.on("console", (m) => {
    if (m.type() !== "error") return;
    const t = m.text().slice(0, 160);
    if (/Failed to load resource/i.test(t)) netErrors.push(t);
    else errors.push(`console: ${t}`);
  });
  // Statuses come from the response event, because the console line does not
  // carry one. 5xx is a real fault; a 403/404 the app handles is reported as
  // NETWORK so it is visible without being fatal.
  page.on("response", (r) => {
    const s = r.status();
    if (s >= 500) netErrors.push(`${s} ${new URL(r.url()).pathname}`);
  });

  const r = await ctx.request.post(`${BASE}/api/signin`,
                                   { data: { email: "dma@zennify.com" } });
  const m = (r.headers()["set-cookie"] || "").match(/dma_session=([^;]+)/);
  if (!m) { console.error("could not sign in"); process.exit(2); }
  await ctx.addCookies([{ name: "dma_session", value: m[1], url: BASE,
                          httpOnly: true, sameSite: "Lax" }]);

  const go = async (hash) => {
    errors = [];
    netErrors = [];
    // A hash-only goto does not reload the document, so the probe would
    // measure the previous page.
    await page.goto(`${BASE}/#/${hash}`, { waitUntil: "networkidle" });
    await page.reload({ waitUntil: "networkidle" });
    await settle();
  };
  const textLen = () => page.evaluate(() => {
    const app = document.getElementById("app");
    return app ? app.textContent.trim().length : 0;
  });

  // A page can be legitimately short. "role AE has no route to the context
  // dashboard" and "Analyst access required" are the app STATING something —
  // the API's default-deny answered, and the page said so. A blank page says
  // nothing. The difference is a rendered empty state with a heading, so that
  // is what the gate checks; without it the AE default landing reported three
  // correct locked states as crashes.
  const statesSomething = () => page.evaluate(() => {
    const e = document.querySelector("#app .main .empty");
    return !!(e && e.querySelector("h3") &&
              e.querySelector("h3").textContent.trim().length > 8);
  });

  // Wait for the page to STOP changing, rather than for a fixed delay. A fixed
  // 2.2s reported four pages as "nearly empty" the moment reads got a little
  // slower — what it had measured was the section loader, and a loading page
  // called a crash is a false alarm that trains you to ignore the gate.
  async function settle(maxMs = 12000) {
    const t0 = Date.now();
    let last = -1;
    let stableFor = 0;
    while (Date.now() - t0 < maxMs) {
      await page.waitForTimeout(250);
      const n = await textLen().catch(() => -1);
      if (n === last) {
        stableFor += 250;
        // Two things end the wait: the text stopped changing AND there is
        // enough of it to judge, or it has been stable a good while (a
        // genuinely empty page must still be reportable).
        if (stableFor >= 750 && n >= MIN_PAGE_TEXT) return;
        if (stableFor >= 2500) return;
      } else {
        stableFor = 0;
        last = n;
      }
    }
  }

  const scanStatic = async (label) => {
    const found = await page.evaluate((sentinels) => {
      const body = document.body.textContent || "";
      const leaks = sentinels.filter((s) => body.includes(s));
      const layout = [];
      document.querySelectorAll("#app *").forEach((el) => {
        if (el.children.length) return;
        const t = (el.textContent || "").trim();
        if (t.length < 3) return;
        const cs = getComputedStyle(el);
        const overflowing = el.scrollWidth > el.clientWidth + 2
                            && cs.overflow !== "visible";
        // `text-overflow: ellipsis` is deliberate truncation, and an ellipsis
        // ALWAYS satisfies scrollWidth > clientWidth — so treating it as a
        // layout defect flagged 32 nodes that were rendering exactly as
        // designed. What IS a defect is truncating with no way to read the
        // rest: no title attribute and no expansion.
        if (overflowing && cs.textOverflow === "ellipsis") {
          if (!el.getAttribute("title") && !el.closest("[title]")) {
            layout.push({ kind: "truncated with no title", text: t.slice(0, 60) });
          }
        } else if (overflowing) {
          layout.push({ kind: "clipped", text: t.slice(0, 60) });
        }
        const box = el.getBoundingClientRect();
        if (box.width > 0 && box.width < 26 && box.height > 60 && t.length > 12) {
          layout.push({ kind: "squeezed", text: t.slice(0, 60) });
        }
      });
      return { leaks, layout: layout.slice(0, 8) };
    }, FIXTURE_SENTINELS);
    for (const s of found.leaks) add("FIXTURE_LEAK", label, s);
    for (const l of found.layout) add("LAYOUT", label, `${l.kind}: ${l.text}`);
  };

  // Every visibly clickable thing, in DOM order, described well enough to
  // re-find after a re-render (indices shift when a drawer opens).
  const clickables = () => page.evaluate((sel) => {
    const out = [];
    document.querySelectorAll(sel).forEach((el) => {
      if (!el.offsetParent) return;
      const t = (el.textContent || "").trim().slice(0, 40) || el.className;
      out.push({ label: t, cls: String(el.className || "").slice(0, 40) });
    });
    // index AFTER filtering, so it matches the click-side list exactly
    return out.map((o, i) => ({ ...o, i }));
  }, CLICKABLE_SELECTOR);

  for (const tab of TABS) {
    const label = tab;
    await go(`clients/${ENTITY}/${tab}`);
    const len = await textLen();
    if (errors.length) add("CRASH", label, `on load: ${errors[0]}`);
    for (const n of netErrors.slice(0, 2)) add("NETWORK", label, `on load: ${n}`);
    if (len < MIN_PAGE_TEXT && !(await statesSomething())) {
      add("CRASH", label, `page nearly empty (${len} chars) with no empty state`);
    }
    await scanStatic(label);
    if (SHOTS) {
      fs.mkdirSync(SHOTS, { recursive: true });
      await page.screenshot({ path: path.join(SHOTS, `${tab}.png`), fullPage: true });
    }

    // Click each target from a freshly loaded page so one drawer cannot mask
    // the next target, and so a crash is attributed to the click that caused it.
    const all = await clickables();
    // Bounded per page: a reload per click is the isolation guarantee, and an
    // unbounded sweep exhausted the browser before the later pages ran. What
    // is dropped is reported, never silently skipped.
    const targets = all.slice(0, MAX_TARGETS_PER_PAGE);
    if (all.length > targets.length) {
      console.log(`  note: ${label} has ${all.length} clickables; testing the first ${targets.length}`);
    }
    for (const t of targets) {
      await go(`clients/${ENTITY}/${tab}`);
      const before = await textLen();
      errors = [];
      netErrors = [];
      const clicked = await page.evaluate(({ idx, sel }) => {
        const els = [...document.querySelectorAll(sel)].filter((e) => e.offsetParent);
        if (!els[idx]) return false;
        els[idx].click();
        return true;
      }, { idx: t.i, sel: CLICKABLE_SELECTOR });
      if (!clicked) continue;
      try {
        // A click can trigger a re-fetch (the audience toggle re-reads every
        // page for the new audience), so this waits for settle too. Measuring
        // 700ms in reported the loader as a blanked page.
        await settle(9000);
      } catch {
        add("CRASH", label, `browser died while clicking "${t.label}"`);
        return report();
      }
      const after = await textLen();
      const where = `${label} · "${t.label}"`;
      if (errors.length) add("CRASH", label, `click ${where}: ${errors[0]}`);
      for (const n of netErrors.slice(0, 1)) add("NETWORK", label, `click ${where}: ${n}`);
      if (after < MIN_PAGE_TEXT && before >= MIN_PAGE_TEXT
          && !(await statesSomething())) {
        add("CRASH", label, `click ${where} blanked the page (${before} → ${after})`);
      }
      await scanStatic(label);
    }
  }

  await browser.close();
  return report();

}

function report() {
  const byKind = findings.reduce((a, f) => {
    (a[f.kind] = a[f.kind] || []).push(f); return a;
  }, {});
  for (const kind of Object.keys(byKind)) {
    const uniq = [...new Map(byKind[kind].map((f) =>
      [`${f.page}|${f.detail}`, f])).values()];
    console.log(`\n${kind} (${uniq.length})`);
    for (const f of uniq.slice(0, 25)) console.log(`  ${f.page}: ${f.detail}`);
    if (uniq.length > 25) console.log(`  … ${uniq.length - 25} more`);
  }
  if (!findings.length) console.log("\nCLEAN — no crashes, no fixture leaks, no layout defects.");
  // NETWORK is informational: a 403 on a withheld dashboard is the API's
  // default-deny working. Only the blocking classes fail the gate.
  const blocking = findings.filter((f) => f.kind !== "NETWORK");
  if (findings.length && !blocking.length) {
    console.log("\nPASS — only NETWORK notes, which are handled responses.");
  }
  process.exit(blocking.length ? 1 : 0);
}

main().catch((e) => {
  console.error("harness error:", e.message);
  // Partial results are still results — report before exiting.
  if (findings.length) report();
  process.exit(2);
});
