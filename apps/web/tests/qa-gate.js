/**
 * The repeatable interaction + screenshot QA gate.
 *
 *   node tests/qa-gate.js <base-url> <entity-slug> [--shots <dir>] [--tabs a,b]
 *   exit 0 = clean · 1 = defects found · 2 = harness failure
 *
 * Runs four sweeps against EVERY client tab, then prints one per-page table:
 *
 *   1 CRASH SWEEP        load + reload, count pageerrors; the page must carry
 *                        real text OR explicitly state an empty/withheld state.
 *   2 INTERACTION SWEEP  click every distinct clickable, assert no pageerror,
 *                        assert the four contract drilldowns actually open
 *                        (evidence chip → drawer with a non-empty body · rec
 *                        row → modal · timeline event → detail · tech row →
 *                        techstack/TS-… detail), close/back, continue. Targets
 *                        that change NOTHING in the DOM are reported as DEAD.
 *   3 LAYOUT GATE        at 1440 / 1280 / 1024: clipped leaf text, squeezed
 *                        columns, document horizontal scroll.
 *   4 FIXTURE-LEAK SCAN  prototype fixture sentinels in any DOM state.
 *
 * Screenshots land in --shots as <tab>-<state>.png (full page per tab, plus
 * every drilldown state that opened).
 *
 * Hard-won rules inherited from tests/qa-harness.js — do not relearn these:
 *   · A hash-only page.goto() does NOT reload the document; always reload()
 *     after navigating to a new hash, or you measure the page you left.
 *   · An uncaught exception is a CRASH; a failed fetch is NOT — the app
 *     renders withheld pages as a locked empty state and the browser logs the
 *     403 regardless. NETWORK findings are informational, never blocking.
 *   · A short page that renders `.empty` with an <h3> is the app STATING
 *     something (e.g. "role AE has no route to the context dashboard" — the
 *     context tab's 428-char AE landing state is CORRECT, not a crash).
 *   · Wait for the page to STOP CHANGING, never a fixed delay — a fixed wait
 *     reports the section loader as a blanked page the moment reads slow down.
 *   · text-overflow: ellipsis is deliberate truncation, not clipping.
 *   · Never kill the server from here; scripts/qa-server.sh owns that.
 *
 * New rules this gate added:
 *   · EVERY session lands as AE (app-root's _landingRole), so internal-only
 *     surfaces (context) are withheld on load. The gate asserts that landing
 *     state renders, then switches "Acting as" to ADMIN through the settings
 *     popover — the role state is per-document, so the switch must be redone
 *     after every reload.
 *   · Clicking runs close/back instead of reload-per-click, so targets are
 *     re-found by (tag|class|label) signature, not index — indices shift when
 *     a click re-renders the page.
 *   · The audience toggle is INSIDE the swept region; clicking "Customer"
 *     silently reshapes every later measurement, so the sweep resets the
 *     audience to Internal after every click that flips it.
 *   · Bare vendor names are NOT fixture sentinels (the platform page renders
 *     the partner catalogue legitimately); sentinels here are fixture ids,
 *     fixture institutions and fixture claims, matched on word boundaries so
 *     E-047 does not match E-0473.
 */
const fs = require("fs");
const path = require("path");

const BASE = process.argv[2] || "http://localhost:3490";
const ENTITY = process.argv[3] || "baxter-credit-union-bcu";
const shotsAt = process.argv.indexOf("--shots");
const SHOTS = shotsAt > -1 ? process.argv[shotsAt + 1] : path.join(__dirname, "screens");
const tabsAt = process.argv.indexOf("--tabs");

const TABS = tabsAt > -1
  ? process.argv[tabsAt + 1].split(",")
  : ["overview", "heatmap", "insights", "platform", "context", "techstack", "runs"];

const WIDTHS = [1440, 1280, 1024];
const MIN_PAGE_TEXT = 400;
const MAX_TARGETS = Number(process.env.QA_MAX_TARGETS || 48);
const MAX_PER_CLASS = Number(process.env.QA_MAX_PER_CLASS || 6);

// Fixture sentinels. Word-boundary matched: short ids and bank names must not
// match inside longer tokens (E-047 vs E-0473, BMO vs "BMO Harris" is fine but
// not "ABMO…"). "nCino" appears here as the bare name deliberately: the
// partner CATALOGUE tiles render platform names from the API, so if this ever
// fires, check whether the hit is a catalogue tile (then narrow this to the
// fixture CLAIM, per qa-harness.js's history) or fixture prose (a real leak).
const SENTINELS = [
  "fce-001", "nCino", "Wells Fargo", "ex-JPM", "Synovus", "BMO", "Truist",
  "Hudson Valley", "Cazenovia", "CISO absent", "E-047", "E-089", "E-218",
  "E-236", "IS-014",
];
const SENTINEL_SRC = SENTINELS.map((s) => {
  const esc = s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const head = /^\w/.test(s) ? "\\b" : "";
  const tail = /\w$/.test(s) ? "\\b" : "";
  return { s, re: `${head}${esc}${tail}` };
});

// Clickables are scoped to the page body (#app .main): the sidebar/topbar
// persist across routes so clicking them is navigation, and the client tab
// strip lives INSIDE .main so it needs excluding by hand — without this every
// page reports the neighbouring tab's content under its own name.
const NAV_EXCLUDE = ":not(.client-tab):not(.tab):not(.nav-item)";
const CLICKABLE_SELECTOR = [
  "button", "[role='button']", "a[href^='#']", ".card-tile", ".fa-card",
  ".hm-cell", ".ic", ".rec-row", ".tier-chip", ".chip", ".switch",
  ".subcap-row", ".tbl-clickable tbody tr",
].map((s) => `#app .main ${s}${NAV_EXCLUDE}`).join(", ");

const findings = [];   // { kind, page, detail }  kinds: CRASH, FIXTURE_LEAK, LAYOUT, DEAD_DRILLDOWN, NETWORK
const deadTargets = []; // { page, label, cls }
const perTab = {};     // per-page table rows
const add = (kind, page, detail) => findings.push({ kind, page, detail });

function resolvePlaywright() {
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
  fs.mkdirSync(SHOTS, { recursive: true });

  // One sign-in, one cookie, reused by every context.
  const authCtx = await browser.newContext();
  const r = await authCtx.request.post(`${BASE}/api/signin`,
                                       { data: { email: "dma@zennify.com" } });
  const m = (r.headers()["set-cookie"] || "").match(/dma_session=([^;]+)/);
  await authCtx.close();
  if (!m) { console.error("could not sign in at " + BASE); process.exit(2); }
  const cookie = { name: "dma_session", value: m[1], url: BASE,
                   httpOnly: true, sameSite: "Lax" };

  const newPage = async (width) => {
    const ctx = await browser.newContext({ viewport: { width, height: 1100 } });
    await ctx.addCookies([cookie]);
    // Collector + signature live in the page across reloads, so the click
    // side filters EXACTLY like the enumeration side.
    await ctx.addInitScript(() => {
      window.__qaCollect = (sel) => {
        const out = [];
        document.querySelectorAll(sel).forEach((el) => {
          if (!el.offsetParent || el.disabled) return;
          // The per-tab sweep exercises the PAGE. The app chrome (topbar
          // popovers, sidebar nav, ⌘K) is identical on all seven tabs, is
          // exercised deliberately by actAsAdmin/audienceGuard, and its
          // popover buttons measured against whatever page state the
          // PREVIOUS click left — which is how "Notifications" got reported
          // as blanking a page it never touched (isolated: 1589 → 1638
          // chars, popover renders). Sweep once per app, not once per tab.
          if (el.closest("header.topbar, aside.sidebar, .popover")) return;
          const interactive = el.tagName === "BUTTON" || el.tagName === "A"
            || el.getAttribute("role") === "button"
            || getComputedStyle(el).cursor === "pointer";
          if (interactive) out.push(el);
        });
        return out;
      };
      window.__qaSig = (el) => {
        const label = (el.textContent || "").trim().slice(0, 40)
          || el.getAttribute("aria-label") || "";
        return `${el.tagName}|${String(el.className || "").trim().slice(0, 60)}|${label}`;
      };
    });
    const page = await ctx.newPage();
    page.__errors = [];
    page.__net = [];
    page.on("pageerror", (e) => page.__errors.push(String(e.message).split("\n")[0]));
    page.on("console", (msg) => {
      if (msg.type() !== "error") return;
      const t = msg.text().slice(0, 160);
      if (/Failed to load resource/i.test(t)) page.__net.push(t);
      else page.__errors.push(`console: ${t}`);
    });
    page.on("response", (res) => {
      if (res.status() >= 500) page.__net.push(`${res.status()} ${new URL(res.url()).pathname}`);
    });
    return { ctx, page };
  };

  const textLen = (page) => page.evaluate(() => {
    const app = document.getElementById("app");
    return app ? app.textContent.trim().length : 0;
  });

  const statesSomething = (page) => page.evaluate(() => {
    const e = document.querySelector("#app .main .empty");
    return !!(e && e.querySelector("h3")
              && e.querySelector("h3").textContent.trim().length > 8);
  });

  // Wait for the page to STOP changing rather than for a fixed delay.
  async function settle(page, maxMs = 12000) {
    // Stability alone is NOT arrival: the section loader is a CSS-animated
    // spinner that mutates no DOM, so a page mid-refetch reads as "stable"
    // at ~300 chars. Accepting that early is why the same tab measured 290
    // and 17,930 chars in one run, with the failure moving between tabs on
    // every rerun. A small page is accepted only when it is STATING
    // something (.empty with an h3 — a withheld state is an answer) or when
    // the deadline expires — a genuinely blanked page is still caught, just
    // at maxMs instead of at 2.5s.
    const t0 = Date.now();
    let last = -1, stableFor = 0;
    while (Date.now() - t0 < maxMs) {
      await page.waitForTimeout(250);
      const n = await textLen(page).catch(() => -1);
      if (n === last) {
        stableFor += 250;
        if (stableFor >= 750 && n >= MIN_PAGE_TEXT) return;
        if (stableFor >= 2500 && await statesSomething(page).catch(() => false)) return;
      } else { stableFor = 0; last = n; }
    }
  }

  const tabHash = (tab) => `clients/${ENTITY}/${tab}`;

  async function loadTab(page, tab) {
    page.__errors = [];
    page.__net = [];
    await page.goto(`${BASE}/#/${tabHash(tab)}`, { waitUntil: "networkidle" });
    await page.reload({ waitUntil: "networkidle" }); // hash-only goto: no reload
    await settle(page);
  }

  // Every session lands as AE; internal surfaces need "Acting as: Admin".
  // Role state is per-document — redo this after every reload.
  async function actAsAdmin(page) {
    const opened = await page.evaluate(() => {
      const gear = document.querySelector(
        "header.topbar button.icon-btn[aria-label='Settings']");
      if (!gear) return false;
      gear.click();
      return true;
    });
    if (!opened) return false;
    await page.waitForTimeout(350);
    const clicked = await page.evaluate(() => {
      const pop = document.querySelector(".popover");
      if (!pop) return false;
      const btn = [...pop.querySelectorAll(".toggle-row button")]
        .find((b) => /^admin$/i.test((b.textContent || "").trim()));
      if (!btn) return false;
      btn.click(); // SettingsPopover closes itself on selection
      return true;
    });
    if (!clicked) { // no Acting-as block (plain AE grant) — close and move on
      await page.keyboard.press("Escape").catch(() => {});
      return false;
    }
    // The switch triggers a REFETCH with role=ADMIN (the acting-as role is
    // part of the read key), and the loading state is a spinner whose DOM is
    // STABLE — so settle() alone returns mid-load and the sweep measures the
    // spinner. Measured: every tab's "ADMIN" chars came out at exactly
    // AE+51 (the sidebar footer's longer role name) while the real ADMIN
    // context view is 3,687 chars. Wait for the role=ADMIN response first,
    // then for the DOM to settle on what it rendered.
    await page.waitForResponse(
      (res) => res.url().includes("/api/entity/") && res.url().includes("role=ADMIN"),
      { timeout: 15000 }).catch(() => {});
    await settle(page, 10000);
    return page.evaluate(() => {
      const el = document.querySelector(".sb-foot-role");
      return !!el && /admin/i.test(el.textContent || "");
    });
  }

  // The audience toggle sits inside the swept region. Flipped to Customer, it
  // silently reshapes every later measurement — flip it back.
  async function audienceGuard(page) {
    return page.evaluate(() => {
      const t = document.querySelector(".audience-toggle");
      if (!t || !t.className.includes("customer")) return false;
      const internal = [...t.querySelectorAll("button")]
        .find((b) => /internal/i.test(b.textContent || ""));
      if (internal) internal.click();
      return true;
    });
  }

  async function scanFixtures(page, tab, state) {
    const hits = await page.evaluate((sentinels) => {
      const body = document.body.textContent || "";
      const out = [];
      for (const { s, re } of sentinels) {
        const m = body.match(new RegExp(`.{0,50}(${re}).{0,50}`));
        if (m) out.push({ s, ctx: m[0].replace(/\s+/g, " ").trim() });
      }
      return out;
    }, SENTINEL_SRC);
    for (const h of hits) add("FIXTURE_LEAK", tab, `"${h.s}" in ${state}: …${h.ctx}…`);
    return hits.length;
  }

  const shot = async (page, name) => {
    const p = path.join(SHOTS, `${name}.png`);
    await page.screenshot({ path: p, fullPage: true }).catch(() => {});
    return p;
  };

  const overlayState = (page) => page.evaluate(() => {
    const q = (s) => document.querySelector(s);
    const drawer = q(".drawer .drawer-body");
    const modal = q(".modal .modal-body");
    const main = q("#app .main");
    return {
      drawer: drawer ? drawer.innerText.trim().length : -1,
      modal: modal ? modal.innerText.trim().length : -1,
      hash: location.hash,
      // innerText reflects CSS text-transform (the heading renders as
      // "EFFECT ON ASSESSED MATURITY"), so this match must be
      // case-insensitive. The heading names the AXIS — the direction the
      // event moved the assessed position of the cells it lists — which is
      // what `signal` and `maturity_effect` both mean; "assessed" is optional
      // here so the probe survives either wording.
      eventDetail: /effect on (assessed )?maturity/i.test(main ? main.innerText : ""),
    };
  });

  // Body-wide DOM signature: portals (drawer, modal, popover, toast) mount on
  // document.body, so #app alone would miss the very drilldowns we assert.
  const domSig = (page) => page.evaluate(() => {
    const html = document.body.innerHTML;
    let h = 0;
    for (let i = 0; i < html.length; i += 3) h = (h * 33 + html.charCodeAt(i)) | 0;
    return `${location.hash}:${html.length}:${h}`;
  });

  async function closeOverlays(page) {
    for (let i = 0; i < 5; i++) {
      const closed = await page.evaluate(() => {
        const masks = document.querySelectorAll(
          ".drawer-mask, .modal-mask, .popover-mask");
        const top = masks[masks.length - 1];
        if (top) { top.click(); return true; }
        return false;
      });
      if (!closed) break;
      await page.waitForTimeout(250);
    }
  }

  // Bring the page back to the tab after a click, WITHOUT a document reload
  // when possible (a reload resets acting-as back to AE).
  async function restore(page, tab) {
    await closeOverlays(page);
    await audienceGuard(page);
    let hash = await page.evaluate(() => location.hash);
    if (!hash.includes(`/${tab}`)) {
      await page.evaluate(() => history.back());
      await page.waitForTimeout(600);
      hash = await page.evaluate(() => location.hash);
    }
    if (!hash.includes(`/${tab}`)
        || ((await textLen(page)) < MIN_PAGE_TEXT && !(await statesSomething(page)))) {
      await loadTab(page, tab);
      await actAsAdmin(page);
      return "reloaded";
    }
    return "ok";
  }

  /* ── contract drilldowns ──────────────────────────────────────────
     The four flows the gate must prove open, per Surface Spec surfaces:
     evidence chip → drawer (H2/T-row citations), rec row → rec modal,
     timeline event → event detail, tech row → techstack/TS-… detail.   */

  const clickFirst = (page, sel, filterSrc) => page.evaluate(({ sel, filterSrc }) => {
    let els = [...document.querySelectorAll(sel)].filter((e) => e.offsetParent);
    if (filterSrc) {
      const f = new Function("el", `return (${filterSrc})(el);`);
      els = els.filter((e) => f(e));
    }
    if (!els[0]) return false;
    els[0].scrollIntoView({ block: "center" });
    els[0].click();
    return true;
  }, { sel, filterSrc: filterSrc || null });

  async function probe(page, tab, kind, openFn, checkFn) {
    page.__errors = [];
    const opened = await openFn();
    if (!opened) return { kind, status: "absent" };
    await settle(page, 9000);
    let fail = null;
    if (page.__errors.length) fail = `pageerror: ${page.__errors[0]}`;
    if (!fail) fail = await checkFn();
    await shot(page, `${tab}-${kind}`);
    await scanFixtures(page, tab, kind);
    if (fail) add("DEAD_DRILLDOWN", tab, `${kind}: ${fail}`);
    return { kind, status: fail ? "FAIL" : "ok" };
  }

  const drawerCheck = async (page) => {
    const o = await overlayState(page);
    if (o.drawer < 0) return "no .drawer opened";
    if (o.drawer < 40) return `drawer body nearly empty (${o.drawer} chars)`;
    return null;
  };
  const modalCheck = async (page) => {
    const o = await overlayState(page);
    if (o.modal < 0) return "no .modal opened";
    if (o.modal < 40) return `modal body nearly empty (${o.modal} chars)`;
    return null;
  };

  async function mustProbes(page, tab) {
    const out = [];
    const run = async (kind, openFn, checkFn) => {
      out.push(await probe(page, tab, kind, openFn, checkFn));
      await restore(page, tab);
    };

    // Evidence chip → drawer, wherever the tab renders clickable chips.
    // (On insights the on-card chips are SPANs; the BUTTON chips live in the
    // insight modal, probed below. On techstack the chips are .chip.purple.)
    if (["overview", "platform", "heatmap"].includes(tab)) {
      await run("evidence-drawer",
        () => clickFirst(page, "#app .main button.tier-chip"),
        () => drawerCheck(page));
    }
    if (tab === "techstack") {
      await run("evidence-drawer",
        () => clickFirst(page, "#app .main button.chip.purple"),
        () => drawerCheck(page));
    }

    if (tab === "insights") {
      // Insight card → modal, then a citation chip inside the modal → drawer.
      await run("insight-modal",
        () => clickFirst(page, "#app .main .ic"),
        () => modalCheck(page));
      out.push(await probe(page, tab, "modal-evidence-drawer",
        async () => (await clickFirst(page, "#app .main .ic"))
          && (await settle(page, 6000), clickFirst(page, ".modal button.tier-chip")),
        () => drawerCheck(page)));
      await restore(page, tab);
    }

    if (tab === "platform") {
      await run("rec-modal",
        () => clickFirst(page, "#app .main .rec-row"),
        () => modalCheck(page));
    }

    if (tab === "context") {
      // Timeline event → detail. Both the dot and the label row carry
      // title="<date> · <title>", which nothing else on the page does.
      // NOTE: no restore() between the two probes — clicking the same event
      // again TOGGLES the detail closed, so the evidence probe rides on the
      // detail the first probe opened.
      out.push(await probe(page, tab, "event-detail",
        () => clickFirst(page, "#app .main button[title*='·']"),
        async () => (await overlayState(page)).eventDetail
          ? null : "event detail (Effect on assessed maturity) did not open"));
      out.push(await probe(page, tab, "event-evidence-drawer",
        () => clickFirst(page, "#app .main button.tier-chip"),
        () => drawerCheck(page)));
      await restore(page, tab);
    }

    if (tab === "heatmap") {
      // Focus-area card → drill-in (H1 → its subcap clusters).
      const before = await domSig(page);
      await run("focus-drill",
        () => clickFirst(page, "#app .main .fa-card"),
        async () => {
          if (await domSig(page) === before) return "focus-area card changed nothing";
          if ((await textLen(page)) < MIN_PAGE_TEXT
              && !(await statesSomething(page))) return "drill-in rendered nearly empty";
          return null;
        });
      // Standard grid → cell drilldown (H4 → H2). The first click may be a
      // category drill (zoom-dependent), so only a DOM change is required;
      // an OPEN drawer must still be non-empty.
      out.push(await probe(page, tab, "cell-drill",
        async () => (await clickFirst(page, "#app .main .toggle-row button",
            "el => /standard/i.test(el.textContent || '')"))
          && (await settle(page, 6000), clickFirst(page, "#app .main .hm-cell")),
        async () => {
          const o = await overlayState(page);
          if (o.drawer > -1 && o.drawer < 40)
            return `cell drawer nearly empty (${o.drawer} chars)`;
          return null;
        }));
      await restore(page, tab);
    }

    if (tab === "techstack") {
      // Tech register row → detail page. Top-level TechRow buttons are the
      // class-less buttons carrying a status word.
      await run("ts-detail",
        () => clickFirst(page, "#app .main button",
          "el => !el.className && /\\b(CONFIRMED|INFERRED|CLAIMED|ABSENT|PARTIAL)\\b/.test(el.innerText || '')"),
        async () => {
          const o = await overlayState(page);
          if (!/\/techstack\/TS-[A-Za-z0-9_-]+/.test(o.hash))
            return `row did not navigate to techstack/TS-… (hash ${o.hash})`;
          if ((await textLen(page)) < MIN_PAGE_TEXT
              && !(await statesSomething(page))) return "TS detail rendered nearly empty";
          return null;
        });
    }
    return out.filter((p) => p.status !== "absent");
  }

  /* ── per-tab crash + interaction sweep (1440, acting as ADMIN) ──── */

  const { ctx: mainCtx, page } = await newPage(WIDTHS[0]);

  for (const tab of TABS) {
    const row = perTab[tab] = {
      aeChars: 0, adminChars: 0, clicked: 0, found: 0, dead: 0,
      drills: [], leaks: 0, layout: {}, crashes: 0,
    };
    const before = findings.length;

    // 1 · AE landing state (the view the field sees first).
    await loadTab(page, tab);
    row.aeChars = await textLen(page);
    if (page.__errors.length) add("CRASH", tab, `on load: ${page.__errors[0]}`);
    for (const n of page.__net.slice(0, 2)) add("NETWORK", tab, `on load: ${n}`);
    let aeStates = await statesSomething(page);
    if (row.aeChars < MIN_PAGE_TEXT && !aeStates) {
      // One retry before declaring: the first tab swept after qa-server.sh
      // restarts hits a cold token-proxied API, and settle()'s 2.5s stability
      // window can expire while that first fetch is still in flight — the
      // gate then reported a healthy page as "nearly empty (288 chars)".
      await page.waitForTimeout(4000);
      await loadTab(page, tab);
      row.aeChars = await textLen(page);
      aeStates = await statesSomething(page);
    }
    if (row.aeChars < MIN_PAGE_TEXT && !aeStates) {
      add("CRASH", tab, `AE landing nearly empty (${row.aeChars} chars), no empty state`);
      await shot(page, `${tab}-crash`);
    }
    if (aeStates) await shot(page, `${tab}-withheld`);
    row.leaks += await scanFixtures(page, tab, "AE landing");

    // 2 · Acting as ADMIN — the full internal view is what the sweep exercises.
    page.__errors = [];
    const admin = await actAsAdmin(page);
    if (!admin) add("CRASH", tab, "could not switch Acting-as to ADMIN");
    if (page.__errors.length) add("CRASH", tab, `on role switch: ${page.__errors[0]}`);
    row.adminChars = await textLen(page);
    if (row.adminChars < MIN_PAGE_TEXT && !(await statesSomething(page))) {
      add("CRASH", tab, `ADMIN view nearly empty (${row.adminChars} chars), no empty state`);
      await shot(page, `${tab}-crash`);
    }
    row.leaks += await scanFixtures(page, tab, "ADMIN view");
    await shot(page, `${tab}-page`);

    // 3 · Contract drilldowns.
    row.drills = await mustProbes(page, tab);
    await restore(page, tab);

    // 4 · Generic interaction sweep. Distinct targets, capped per class so 92
    //     identical evidence chips do not starve the rest of the page.
    const all = await page.evaluate((sel) =>
      window.__qaCollect(sel).map((el) => window.__qaSig(el)), CLICKABLE_SELECTOR);
    const perClass = {};
    const targets = [];
    const ords = {};
    for (const sig of all) {
      const cls = sig.split("|").slice(0, 2).join("|");
      // Class-less buttons (timeline labels, filter chips) are heterogeneous —
      // capping them as one class starved the timeline. Distinct labels each
      // count as their own "class"; identical ones still share the cap.
      const capKey = cls.endsWith("|") ? sig : cls;
      const ord = ords[sig] = (ords[sig] ?? -1) + 1;
      perClass[capKey] = (perClass[capKey] || 0) + 1;
      if (perClass[capKey] <= MAX_PER_CLASS && targets.length < MAX_TARGETS) {
        targets.push({ sig, ord, cls, label: sig.split("|")[2] || cls });
      }
    }
    row.found = all.length;
    if (all.length > targets.length) {
      console.log(`  note: ${tab} has ${all.length} clickables; testing ${targets.length} distinct (cap ${MAX_PER_CLASS}/class, ${MAX_TARGETS}/page)`);
    }

    for (const t of targets) {
      page.__errors = [];
      page.__net = [];
      const sig0 = await domSig(page);
      const clicked = await page.evaluate(({ sel, sig, ord }) => {
        const els = window.__qaCollect(sel).filter((el) => window.__qaSig(el) === sig);
        const el = els[ord] || els[0];
        if (!el) return false;
        el.scrollIntoView({ block: "center" });
        el.click();
        return true;
      }, { sel: CLICKABLE_SELECTOR, sig: t.sig, ord: t.ord });
      if (!clicked) continue; // target belonged to a state a prior click left
      row.clicked++;
      try {
        await settle(page, 8000);
      } catch {
        add("CRASH", tab, `browser died clicking "${t.label}"`);
        return report();
      }
      const where = `"${t.label.slice(0, 40)}"`;
      if (page.__errors.length) {
        add("CRASH", tab, `click ${where}: ${page.__errors[0]}`);
        await shot(page, `${tab}-crash`);
      }
      for (const n of page.__net.slice(0, 1)) add("NETWORK", tab, `click ${where}: ${n}`);
      const after = await textLen(page);
      if (after < MIN_PAGE_TEXT && !(await statesSomething(page))) {
        add("CRASH", tab, `click ${where} blanked the page (${after} chars)`);
        await shot(page, `${tab}-crash`);
      }
      const sig1 = await domSig(page);
      // An already-selected toggle ("Internal" while internal, the active
      // group-by, the active filter) changes nothing BY DESIGN — clicking the
      // state you are in is a no-op, not a dead control. Recording those as
      // DEAD buried the real findings under one identical row per tab.
      const alreadyActive = /\bon\b/.test(t.cls || "") || /\bactive\b/.test(t.cls || "");
      if (sig1 === sig0 && !alreadyActive) {
        row.dead++;
        deadTargets.push({ page: tab, label: t.label.slice(0, 48), cls: t.cls });
      }
      row.leaks += await scanFixtures(page, tab, `after click ${where}`);
      await restore(page, tab);
    }

    row.crashes = findings.filter(
      (f, i) => i >= before && f.page === tab && f.kind === "CRASH").length;
  }
  await mainCtx.close();

  /* ── layout gate: 1440 / 1280 / 1024, ADMIN view, fresh load ────── */

  for (const width of WIDTHS) {
    const { ctx, page: lp } = await newPage(width);
    for (const tab of TABS) {
      await loadTab(lp, tab);
      await actAsAdmin(lp);
      const res = await lp.evaluate(() => {
        const bad = { clip: [], squeeze: [], hscroll: false };
        // Fixed overlays (drawer/modal/popover/panel) legitimately sit over
        // the page mask — they are not measured here, and none is open on a
        // fresh load anyway.
        const overlay = ".drawer, .modal, .popover, .ip";
        document.querySelectorAll("#app *").forEach((el) => {
          if (el.children.length) return;           // leaf nodes only
          if (el.closest(overlay)) return;
          const t = (el.textContent || "").trim();
          const r = el.getBoundingClientRect();
          if (!r.width || !r.height) return;
          const cs = getComputedStyle(el);
          if (t.length >= 3 && el.clientWidth > 0
              && el.scrollWidth > el.clientWidth + 1
              && cs.textOverflow !== "ellipsis") {
            bad.clip.push(t.slice(0, 48));
          }
          if (t.length > 12 && r.width > 0 && r.width < 26 && r.height > 60) {
            bad.squeeze.push(t.slice(0, 48));
          }
        });
        bad.hscroll = document.documentElement.scrollWidth > window.innerWidth + 1;
        return bad;
      });
      perTab[tab].layout[width] = {
        clip: res.clip.length, squeeze: res.squeeze.length, hscroll: res.hscroll,
      };
      for (const c of res.clip.slice(0, 4))
        add("LAYOUT", tab, `${width}px clipped: "${c}"`);
      if (res.clip.length > 4)
        add("LAYOUT", tab, `${width}px clipped: … ${res.clip.length - 4} more`);
      for (const s of res.squeeze.slice(0, 3))
        add("LAYOUT", tab, `${width}px squeezed column: "${s}"`);
      if (res.hscroll) {
        add("LAYOUT", tab, `${width}px document scrolls horizontally`);
        await shot(lp, `${tab}-hscroll-${width}`);
      }
      if (res.clip.length || res.squeeze.length) await shot(lp, `${tab}-layout-${width}`);
    }
    await ctx.close();
  }

  await browser.close();
  return report();
}

function report() {
  // Per-page table.
  const W = [10, 8, 9, 9, 4, 10, 5, 8, 8, 8, 6];
  const cell = (v, i) => String(v).padEnd(W[i]);
  const lay = (l) => l ? `c${l.clip}/s${l.squeeze}${l.hscroll ? "/H" : ""}` : "-";
  console.log("\n" + ["TAB", "AE-CHR", "ADM-CHR", "CLICKED", "DEAD",
    "DRILLDOWNS", "LEAK", "L1440", "L1280", "L1024", "RESULT"]
    .map(cell).join(" "));
  console.log("-".repeat(W.reduce((a, b) => a + b, 0) + W.length - 1));
  let anyBlocking = false;
  for (const tab of Object.keys(perTab)) {
    const r = perTab[tab];
    const tabFindings = findings.filter((f) => f.page === tab);
    const blocking = tabFindings.filter((f) => f.kind !== "NETWORK");
    if (blocking.length) anyBlocking = true;
    const drills = r.drills.length
      ? `${r.drills.filter((d) => d.status === "ok").length}/${r.drills.length} ok`
      : "-";
    console.log([
      tab, r.aeChars, r.adminChars, `${r.clicked}/${r.found}`, r.dead, drills,
      r.leaks, lay(r.layout[1440]), lay(r.layout[1280]), lay(r.layout[1024]),
      blocking.length ? "FAIL" : "PASS",
    ].map(cell).join(" "));
  }
  console.log("  (L#### = c<clipped>/s<squeezed> at that width, /H = horizontal scroll)");

  const byKind = findings.reduce((a, f) => {
    (a[f.kind] = a[f.kind] || []).push(f); return a;
  }, {});
  for (const kind of Object.keys(byKind)) {
    const uniq = [...new Map(byKind[kind].map((f) =>
      [`${f.page}|${f.detail}`, f])).values()];
    console.log(`\n${kind} (${uniq.length})`);
    for (const f of uniq.slice(0, 30)) console.log(`  ${f.page}: ${f.detail}`);
    if (uniq.length > 30) console.log(`  … ${uniq.length - 30} more`);
  }
  if (deadTargets.length) {
    console.log(`\nDEAD TARGETS (${deadTargets.length}) — clicked, nothing changed in the DOM`);
    for (const d of deadTargets.slice(0, 30))
      console.log(`  ${d.page}: "${d.label}" [${d.cls}]`);
    if (deadTargets.length > 30) console.log(`  … ${deadTargets.length - 30} more`);
  }

  const blocking = findings.filter((f) => f.kind !== "NETWORK");
  if (!findings.length && !deadTargets.length) {
    console.log("\nCLEAN — no crashes, leaks, layout defects or dead drilldowns.");
  } else if (!blocking.length) {
    console.log("\nPASS — only NETWORK notes and/or dead-target notes; nothing blocking.");
  } else {
    console.log(`\nGATE FAILED — ${blocking.length} blocking finding(s). Screenshots: ${SHOTS}`);
  }
  process.exit(blocking.length ? 1 : 0);
}

main().catch((e) => {
  console.error("harness error:", e.stack || e.message);
  if (findings.length || Object.keys(perTab).length) return report();
  process.exit(2);
});
