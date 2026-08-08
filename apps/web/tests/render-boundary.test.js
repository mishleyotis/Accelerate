/* Fault injection: one bad field must cost one card, never the application.
 *
 * Run with `npm run test:web` (node's built-in test runner). It starts a
 * throwaway static server that serves the COMPILED bundle exactly the way
 * app/route.js serves it — same script list, same order, same inline
 * window.DMA_LIVE bootstrap — then drives it with playwright-core and
 * intercepts every /api/entity/** read to hand the page a payload with one
 * deliberate shape defect in it.
 *
 * Why this test exists. The app shipped with exactly one error boundary,
 * SectionBoundary, in pages-live-client.jsx — a module the router never
 * mounts. The live tree therefore had NONE. A single malformed list item
 * threw during render, React unmounted the whole tree, and the application
 * became a literally empty <body>: no message, no chrome, no way back but a
 * reload onto the same payload. Every case below reproduces that class of
 * fault and asserts the opposite outcome: the page keeps its other cards and
 * the body never collapses.
 *
 * Two rules the harness itself must obey, learned in tests/qa-harness.js:
 *   · serve the COMPILED js, never the jsx — the app serves public/proto/js,
 *     so a test that read proto/*.jsx would verify code that never ships.
 *   · a hash change does not reload the document; navigate with the hash
 *     already on the URL, or reload after setting it.
 *
 * Set PROTO_JS_DIR to point the harness at another build of the bundle —
 * that is how the pre-fix behaviour was measured (git archive HEAD~1).
 */
const { test } = require("node:test");
const assert = require("node:assert");
const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");

const WEB = path.join(__dirname, "..");
const PUBLIC = path.join(WEB, "public");
const JS_DIR = process.env.PROTO_JS_DIR || path.join(PUBLIC, "proto", "js");
const ENTITY = "test-credit-union";

/* ── the harness ─────────────────────────────────────────────────────── */

function resolvePlaywright() {
  const candidates = [
    process.env.PLAYWRIGHT_CORE,
    "playwright-core",
    path.join(WEB, "node_modules", "playwright-core"),
    ...fsGlob("/tmp/claude-0", "scratchpad/node_modules/playwright-core"),
  ].filter(Boolean);
  for (const p of candidates) {
    try { return require(p); } catch { /* keep looking */ }
  }
  return null;
}

// Two levels deep under /tmp/claude-0/<repo>/<session>/, which is where the
// QA scripts put their own copy. Not a real glob — just enough of one.
function fsGlob(root, tail) {
  const out = [];
  try {
    for (const a of fs.readdirSync(root)) {
      for (const b of fs.readdirSync(path.join(root, a))) {
        out.push(path.join(root, a, b, tail));
      }
    }
  } catch { /* no scratchpad here */ }
  return out;
}

// The script list is READ from the route handler rather than copied, so the
// test cannot drift out of load order with the page it is standing in for.
function scriptList() {
  const src = fs.readFileSync(path.join(WEB, "app", "route.js"), "utf8");
  const block = src.match(/const SCRIPTS = \[([\s\S]*?)\];/);
  assert.ok(block, "app/route.js no longer declares SCRIPTS — update this test");
  return [...block[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
}

const MIME = { ".js": "text/javascript", ".css": "text/css", ".png": "image/png" };

function startServer(live) {
  const scripts = scriptList();
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>DMA Insights</title><link rel="stylesheet" href="/proto/app.css"></head>
<body><div id="app"></div>
<script>window.DMA_LIVE=${JSON.stringify(live).replace(/</g, "\\u003c")};</script>
${scripts.map((s) => `<script src="/${s}" defer></script>`).join("\n")}
</body></html>`;

  const server = http.createServer((req, res) => {
    const url = (req.url || "/").split("?")[0];
    if (url === "/" || url === "/index.html") {
      res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
      return res.end(html);
    }
    // proto/js comes from JS_DIR (overridable); everything else from public/.
    const file = url.startsWith("/proto/js/")
      ? path.join(JS_DIR, url.slice("/proto/js/".length))
      : path.join(PUBLIC, url.replace(/^\//, ""));
    if (!file.startsWith(JS_DIR) && !file.startsWith(PUBLIC)) {
      res.writeHead(403); return res.end();
    }
    fs.readFile(file, (err, buf) => {
      if (err) { res.writeHead(404); return res.end(); }
      res.writeHead(200, { "content-type": MIME[path.extname(file)] || "application/octet-stream" });
      res.end(buf);
    });
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => resolve(
      { server, base: `http://127.0.0.1:${server.address().port}` }));
  });
}

/* ── the payload ─────────────────────────────────────────────────────── */

const RUN_ID = "DMA-ASM-TCU-20260801-0001";

const BOOT = {
  authed: true, role: "ADMIN", email: "dma@zennify.com", name: "QA",
  catalogue_version: "v7.0", dev_login: true,
  subvertical_labels: { CREDIT_UNION: "Credit union" },
  entities: [{
    id: ENTITY, slug: ENTITY, name: "Test Credit Union",
    subvertical: "CREDIT_UNION", size_tier: "MEDIUM", hq: "Chicago, IL",
    status: "ACTIVE", data_source: "PROJECT_API", assessment_date: "2026-08-01",
    overall: 2.9, pillar_scores: { P1: 3.1, P2: 2.7, P3: 2.9, P4: 2.6 },
    oss: { SF: 61, DB: 40 }, footprint: ["IL"], runs: [
      { id: RUN_ID, date: "2026-08-01", status: "ACTIVE", overall: 2.9,
        evidence_mode: "HYBRID", subcap_count: 706 },
    ],
  }],
  active_runs: [], pending_review: [],
};

const sec = (data, extra) => ({
  data, e_ids: [], produced_at: "2026-08-01T00:00:00Z",
  producer_version: "test", provenance: "test", empty_state: null, ...extra,
});

// A payload with nothing wrong with it. Every case below is this, with one
// value replaced — so a failure names the SHAPE that broke, not the fixture.
function payloadFor(page) {
  const run = { run_id: RUN_ID, promoted_at: "2026-08-01T00:00:00Z",
                completed_at: "2026-08-01T00:00:00Z" };
  const entity = { display_id: ENTITY, name: "Test Credit Union" };
  const sections = {};
  if (page === "overview") {
    sections.scores = sec({ composite: 2.9, framing: "A test framing sentence.",
      pillars: [
        { pillar_id: "P1", score: 3.1, peer_median: 2.9 },
        { pillar_id: "P2", score: 2.7, peer_median: 2.8 },
        { pillar_id: "P3", score: 2.9, peer_median: 2.7 },
        { pillar_id: "P4", score: 2.6, peer_median: 2.8 },
      ] });
    sections.firmographics = sec({ fields: [
      { field: "total_assets", value: "6.5", unit: "USD billions" },
      { field: "employees", value: "1200" },
      { field: "branches", value: "27" },
    ] });
    sections.findings = sec({ ranking_basis: "test", findings: [
      { f_id: "F-01", title: "First finding", theme: "Data", body: "What it is.",
        consequence: "It costs time.", e_ids: [], linked_subcap_ids: [] },
      { f_id: "F-02", title: "Second finding", theme: "Ops", body: "What it is.",
        consequence: "It costs money.", e_ids: [], linked_subcap_ids: [] },
    ] });
    sections.leadership = sec({ roster: [
      { name: "A Person", title: "Chief Data Officer", domain: "data",
        tenure_months: 40, relevance_note: "Owns the warehouse." },
      { name: "B Person", title: "Chief Technology Officer", domain: "tech",
        tenure_months: 8, relevance_note: "Owns the core." },
    ] });
    sections.why_now = sec({ signals: [
      { category: "TECHNOLOGY", label: "A core decision lands this year.",
        detail: "Longer detail.", strength: "STRONG", claim_label: "FACT" },
    ] });
    sections.exec_summary = sec({ situation: "The situation.",
      complication: "The complication.", question: "The question?",
      answer: "The answer." });
    sections.opportunity = sec({ tiles: [
      { platform_id: "SF", fit_score: 61, headline: "Fit" },
    ] });
    sections.thought_leadership = sec({ entries: [
      { title: "A talk", excerpt: "A quote.", author: "A Person",
        published_on: "2026-05-01", kind: "TALK" },
    ] });
  } else if (page === "insights") {
    sections.insights = sec({ cards: [
      { ic_id: "IC-01", title: "First card", what_text: "What the first card says.",
        why_text: "Why.", severity: "high", confidence: "HIGH",
        affects: ["P1C1.1.1"], supporting_e_ids: [] },
      { ic_id: "IC-02", title: "Second card", what_text: "What the second card says.",
        why_text: "Why.", severity: "medium", confidence: "MEDIUM",
        affects: ["P2C1.1.1"], supporting_e_ids: [] },
      { ic_id: "IC-03", title: "Third card", what_text: "What the third card says.",
        why_text: "Why.", severity: "low", confidence: "LOW",
        affects: ["P3C1.1.1"], supporting_e_ids: [] },
    ] });
  }
  return { entity, run, audience: "internal", sections };
}

// Faults are addressed by "<page>.<section>.<json path>" and applied to the
// base payload, so each case reads as one sentence about one value.
function applyFault(body, page, fault) {
  if (!fault || fault.page !== page) return body;
  const s = body.sections[fault.section];
  if (!s) return body;
  fault.mutate(s.data);
  return body;
}

/* ── the cases ───────────────────────────────────────────────────────── */

const CASES = [
  {
    name: "control · a well-formed payload renders every card",
    tab: "overview",
    fault: null,
    expect: { failures: 0, mustSee: ["Top findings", "Leadership panel",
                                     "Why now signals", "Firmographics"] },
  },
  {
    name: "a finding that is null where the contract says object",
    tab: "overview",
    fault: { page: "overview", section: "findings",
             mutate: (d) => { d.findings[0] = null; } },
    // Reading `f.f_id` off null threw in ClientOverview's own body — above
    // every card — and took the entire application with it.
    expect: { failedCards: ["top findings"],
              mustSee: ["Leadership panel", "Why now signals", "Firmographics",
                        "Could not render"] },
  },
  {
    name: "a roster entry that is a string where the contract says object",
    tab: "overview",
    fault: { page: "overview", section: "leadership",
             mutate: (d) => { d.roster[1] = "B Person, CTO"; } },
    // Every field on a string entry reads undefined, and the adapter files a
    // nameless entry as a role GAP — so a malformed value rendered as
    // "critical role absent from evidence", a finding nobody made. An entry
    // with neither a name nor a role is named as unreadable and counted as
    // neither a person nor a gap.
    expect: { failures: 0,
              mustSee: ["Top findings", "A Person",
                        "neither a name nor a role"],
              mustNotSee: ["absent"] },
  },
  {
    name: "a roster entry whose name is an object where a string is expected",
    tab: "overview",
    fault: { page: "overview", section: "leadership",
             mutate: (d) => { d.roster[1].name = { first: "B", last: "Person" }; } },
    // `ex.name.split(" ")` — not a function on an object. The leadership card
    // threw for a payload whose other six sections were fine, and the whole
    // application unmounted with it.
    expect: { failedCards: ["leadership panel"],
              mustSee: ["Top findings", "Why now signals", "Could not render"] },
  },
  {
    name: "an insight card that is a string where the contract says object",
    tab: "insights",
    fault: { page: "insights", section: "insights",
             mutate: (d) => { d.cards[1] = "IC-02"; } },
    // The measured defect, verbatim: one malformed list item on the insights
    // page emptied the <body>. It now costs one tile.
    //
    // A string never reaches the grouping as a string: adaptInsights maps it
    // into a card object whose every field is undefined (live-adapter.jsx,
    // not this file's to fix — reported). So the shape defect surfaces where
    // the card is DRAWN, `c.what.slice` on undefined, which is precisely the
    // throw the item boundary is there to hold.
    expect: { failedItems: 1,
              mustSee: ["First card", "Third card", "Could not render"] },
  },
  {
    name: "an insight card whose prose field is an object",
    tab: "insights",
    fault: { page: "insights", section: "insights",
             mutate: (d) => { d.cards[0].title = { statement: "First card" }; } },
    // React throws "Objects are not valid as a React child" — the same crash
    // asText exists to prevent, arriving through a field nobody wrapped.
    expect: { failedItems: 1, mustSee: ["Second card", "Third card"] },
  },
  {
    name: "a firmographics field list that is a number",
    tab: "overview",
    fault: { page: "overview", section: "firmographics",
             mutate: (d) => { d.fields = 7; } },
    // `for…of 7` threw in app-root's entity merge, which is ABOVE the shell:
    // no boundary can catch it, so the shape is checked and the panel says so
    // rather than printing an em dash per row as though nothing was stated.
    expect: { failures: 0,
              mustSee: ["did not arrive as a list of fields", "Top findings",
                        "Leadership panel"] },
  },
  {
    name: "a leadership roster that is a number where a list is expected",
    tab: "overview",
    fault: { page: "overview", section: "leadership",
             mutate: (d) => { d.roster = 3; } },
    // `roster.map` throws inside the adapter, which runs in a promise — an
    // unhandled rejection that left the page on its loading spinner for ever,
    // with no error and nothing to say why. It is a failed read, and says so.
    expect: { failures: 0, mustSee: ["could not be read into the page"] },
  },
];

/* ── the run ─────────────────────────────────────────────────────────── */

const pw = resolvePlaywright();
const CHROME = process.env.CHROMIUM_PATH || "/opt/pw-browsers/chromium";
const skip = !pw ? "playwright-core not resolvable"
  : !fs.existsSync(CHROME) ? `no chromium at ${CHROME}` : false;

test("fault injection: one bad field costs one card, never the app",
     { skip, concurrency: false }, async (t) => {
  const { server, base } = await startServer(BOOT);
  const browser = await pw.chromium.launch({ executablePath: CHROME,
                                             args: ["--no-sandbox"] });
  try {
    for (const c of CASES) {
      await t.test(c.name, async () => {
        const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
        const pageErrors = [];
        page.on("pageerror", (e) => pageErrors.push(String(e)));
        if (process.env.DEBUG_BOUNDARY) {
          page.on("console", (m) => console.log(`  [console.${m.type()}] ${m.text()}`));
          page.on("requestfailed", (r) => console.log(`  [reqfail] ${r.url()}`));
        }
        await page.route("**/api/entity/**", async (route) => {
          const which = new URL(route.request().url()).pathname.split("/").pop();
          const body = applyFault(payloadFor(which), which, c.fault);
          await route.fulfill({ status: 200, contentType: "application/json",
                                body: JSON.stringify(body) });
        });

        await page.goto(`${base}/#/clients/${ENTITY}/${c.tab}`,
                        { waitUntil: "domcontentloaded" });
        // The app boots on a 600ms timer and then reads eight endpoints; wait
        // for the DOM to stop changing rather than for a fixed delay, which
        // would measure the loading spinner on a slow machine.
        await settle(page);

        const text = await page.evaluate(() => document.body.innerText || "");
        if (process.env.DEBUG_BOUNDARY) console.log(`  [text ${text.length}]\n${text}`);
        const failures = await page.evaluate(() => window.__DMA_RENDER_FAILURES || []);
        const marked = await page.$$eval("[data-render-failed]",
                                         (els) => els.map((e) => e.getAttribute("data-render-failed")));

        // 1 · the body never collapses. This is the regression that must never
        //     return: the measured defect was an EMPTY <body>, not a bad card.
        assert.ok(text.length > 400,
          `body collapsed to ${text.length} chars — the whole app unmounted:\n${text.slice(0, 200)}`);
        assert.ok(await page.$("#app *"), "#app rendered nothing at all");

        // 2 · the surfaces that had nothing wrong with them still rendered.
        //     Matched case-insensitively: innerText carries text-transform, so
        //     a card heading the stylesheet uppercases reads FIRMOGRAPHICS.
        const flat = text.toLowerCase();
        for (const needle of c.expect.mustSee || []) {
          assert.ok(flat.includes(needle.toLowerCase()),
            `"${needle}" is missing — the fault spread beyond its own card:\n${text.slice(0, 400)}`);
        }
        for (const needle of c.expect.mustNotSee || []) {
          assert.ok(!flat.includes(needle.toLowerCase()),
            `"${needle}" is on the page — a malformed value became an assertion`);
        }

        // 3 · the damage is exactly where it was injected, and named.
        if (c.expect.failedCards) {
          for (const nm of c.expect.failedCards) {
            assert.ok(failures.some((f) => f.name === nm),
              `no boundary trip recorded for "${nm}" — got ${JSON.stringify(failures.map((f) => f.name))}`);
            assert.ok(marked.includes(nm), `no rendered notice for "${nm}" — got ${JSON.stringify(marked)}`);
          }
          assert.strictEqual(marked.length, c.expect.failedCards.length,
            `more cards degraded than the one fault warranted: ${JSON.stringify(marked)}`);
        }
        if (c.expect.failedItems != null) {
          assert.strictEqual(marked.length, c.expect.failedItems,
            `expected ${c.expect.failedItems} degraded item(s), got ${JSON.stringify(marked)}`);
        }
        if (c.expect.failures === 0) {
          assert.deepStrictEqual(marked, [],
            `a card degraded that should have been handled in place: ${JSON.stringify(marked)}`);
        }

        // 4 · a boundary must not become a place for crashes to hide. Anything
        //     it caught is on the list; anything it did not catch is a
        //     pageerror, and neither may be silent.
        const uncaught = pageErrors.filter((e) => !/ResizeObserver/.test(e));
        assert.deepStrictEqual(uncaught, [],
          `uncaught page error escaped every boundary:\n${uncaught.join("\n")}`);

        await page.close();
      });
    }
  } finally {
    await browser.close();
    await new Promise((r) => server.close(r));
  }
});

// Wait for the DOM to stop changing. Never a fixed delay: a fixed wait reports
// the section loader as a blanked page the moment the reads slow down.
//
// The boot screen is the trap. App() holds the tree behind a 600ms font/boot
// timer, and that screen is STATIC — it satisfies "stopped changing" perfectly
// while showing nothing but "Loading DMA Insights…". So the page shell has to
// arrive first, and only then is stillness meaningful.
async function settle(page, quietMs = 400, timeoutMs = 15000) {
  try {
    // Both loaders are traps for a "has it stopped changing" wait: the boot
    // screen and the section loader are STATIC, so a settle that only watched
    // the DOM would call either of them a finished page. The wait is therefore
    // for a shell with no loader in it.
    await page.waitForFunction(
      () => !!document.querySelector("#app .main, #app .empty, #app .loader-card .btn")
            && !document.querySelector(".loader-section, .loader-page"),
      null, { timeout: timeoutMs });
  } catch {
    // Report the DEFECT, not the harness. Before this repair every case below
    // ended here, and "waitForSelector timed out" says nothing; what actually
    // happened is that React unmounted the tree and #app is empty, or the read
    // failed in a promise and the page is still on its boot screen for ever.
    const seen = await page.evaluate(() => ({
      len: (document.body.innerText || "").length,
      appChildren: document.getElementById("app")
        ? document.getElementById("app").childElementCount : -1,
      head: (document.body.innerText || "").slice(0, 160),
    }));
    assert.fail(`no page ever rendered: #app has ${seen.appChildren} children, `
      + `body is ${seen.len} chars — the tree unmounted or never left the boot `
      + `screen.\n${seen.head}`);
  }
  const started = Date.now();
  let last = "", lastChange = Date.now();
  while (Date.now() - started < timeoutMs) {
    const now = await page.evaluate(() => (document.body.innerText || "").length + ":"
      + document.querySelectorAll("*").length);
    if (now !== last) { last = now; lastChange = Date.now(); }
    else if (Date.now() - lastChange > quietMs) return;
    await new Promise((r) => setTimeout(r, 100));
  }
}
