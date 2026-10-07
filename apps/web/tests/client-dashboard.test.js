/* The client dashboard: what a client is shown, and what the frame around it
 * carries.
 *
 * Client-view review, 2026-10-07 (DMA_customer_view_feedback.docx). Eleven
 * comments, each pinned here so the next change to a page cannot put a
 * Zennify surface back in front of a client without a red test:
 *
 *   copy     "Customer" → "Client"; the banner reads "Client Dashboard" and
 *            its action "Switch back to Zennify view →"; O5 is titled
 *            "Platform Opportunities"; Insights is "Key insights ·
 *            Recommendations for <client>"
 *   hidden   Meeting prep (and the Intelligence panel it opens), Request
 *            rerun, the executive narrative, the leadership panel, the
 *            financial trajectory, the technology landscape, and the Platform
 *            and Tech stack tabs
 *   link     `view=client` opens the client dashboard alone — no sidebar, no
 *            top bar, no audience toggle — and nothing in the page walks the
 *            reader out of it
 *
 * Owner follow-up, 2026-10-07: the heatmap is never hidden (the standard grid
 * opens the client heatmap too); a why-now card never renders empty; and a
 * shared link reaches Overview · Insights · Heatmap of its own client and
 * nothing else, whatever is typed into the address bar.
 *
 * The internal view is asserted alongside each one: every hide is an
 * audience rule, and a rule that also emptied the Zennify view would pass a
 * client-only test.
 *
 * SSR half: in-process against the compiled bundle (`npm run build:proto`).
 * Browser half: the link frame, which is about chrome and routing and so
 * cannot be read from one component's markup.
 */
const { test } = require("node:test");
const assert = require("node:assert");

const H = require("./ssr-harness");
const F = require("./fixtures/gold-audit-shape");
const { resolvePlaywright, startServer, settle, resolveChromium, browserSkip } =
  require("./proto-page-harness");

const ID = "test-credit-union";
const NAME = "Test Credit Union";
const RUN = { id: "DMA-ASM-TCU-20260801-0001", run_id: "run-1", date: "2026-08-01",
              status: "ACTIVE", data_source: "PROJECT_API", overall: 1.6 };
const ENTITY = { id: ID, slug: ID, name: NAME, subvertical: "CREDIT_UNION",
                 hq: "Chicago, IL", assessment_date: "2026-08-01", overall: 1.6,
                 pillar_scores: {}, pillar_peer_medians: {}, oss: {}, subcaps: [],
                 footprint: [], runs: [RUN] };

const sec = (data) => ({ data, e_ids: [], produced_at: "2026-08-01T00:00:00Z",
                         producer_version: "test", provenance: "test",
                         data_source: "producer", empty_state: null });

function pages() {
  return {
    overview: { sections: {
      scores: sec({ composite: 1.6, framing: "A framing sentence.",
                    pillars: ["P1", "P2", "P3", "P4"].map((p) => ({ pillar_id: p, score: 1.6 })) }),
      exec_summary: sec({ situation: "The situation.", complication: "The complication.",
                          question: "The question?", answer: "The answer." }),
      leadership: sec({ roster: [{ name: "A Leader", title: "President and Chief Executive Officer",
                                   domain: "enterprise", relevance_note: "Owns the decision." }] }),
      financial_series: F.sec(F.FINANCIAL_SERIES),
      sentiment: F.sec(F.SENTIMENT),
      opportunity: sec({ tiles: [{ platform: "Example Platform", composite: 55.5, rank: 1,
                                   headline: "A headline.", factors: [], addressable_cells: [] }],
                         discarded: [] }),
      findings: sec({ findings: [{ f_id: "F-01", title: "A finding title", theme: "TIMING" }],
                      ranking_basis: "Ranked by consequence." }),
      // WN-2 is the shape the client read takes when the server withholds a
      // trigger that names a person from a contact source: every other field
      // present, `trigger` gone.
      why_now: sec({ signals: [
        { wn_id: "WN-1", kind: "REGULATORY", trigger: "The regulator published a new rule in June 2026. It applies from 2027.",
          window: "Until the 2027 effective date.", why_this_sequence: "First, because the date is fixed.",
          cost_of_acting_now: "Budget moves forward a year.", e_ids: [] },
        { wn_id: "WN-2", kind: "LEADERSHIP", window: "No dated close established.",
          why_this_sequence: "Second.", cost_of_acting_now: "Verification effort.", e_ids: [] },
      ] }),
    } },
    insights: { sections: {
      insights: sec({ cards: [{ ic_id: "IC-001", title: "An insight", pillar_id: "P3",
                                what_text: "What.", why_text: "Why.", so_what_text: "So what.",
                                severity: "high", confidence: "HIGH", supporting_e_ids: [] }] }),
    } },
    techstack: { sections: { techstack: F.sec(F.TECHSTACK) } },
  };
}

function page(Component, audience, props) {
  const { win } = H.load();
  H.installEntity(ID, pages());
  const ctx = { audience, tweaks: { overview_layout: "balanced" },
                setIpSurface() {}, setIpContext() {}, setIpOpen() {},
                openEvidence() {}, openInsight() {}, openSubcap() {} };
  return H.textOf(H.render(win[Component], { entity: ENTITY, run: RUN, ...(props || {}) }, ctx));
}

/* ── Overview ──────────────────────────────────────────────────────────── */

test("overview · the client view drops every Zennify-only surface", () => {
  const text = page("ClientOverview", "customer");
  for (const gone of ["Meeting prep", "Request rerun", "Executive narrative",
                      "Leadership panel", "Financial trajectory",
                      "Opportunity Surface", "Open matrix", "View timeline"]) {
    assert.ok(!text.includes(gone), `the client overview still renders "${gone}"`);
  }
  assert.match(text, /Platform Opportunities/, "O5 is not titled Platform Opportunities");
  assert.match(text, /Top findings/, "the hide took the findings with it");
  assert.match(text, /Scorecard/, "the client-safe scorecard action is gone");
});

test("overview · the Zennify view keeps all of it", () => {
  const text = page("ClientOverview", "internal");
  for (const kept of ["Meeting prep", "Request rerun", "Executive narrative",
                      "Leadership panel", "Financial trajectory", "Platform Opportunities"]) {
    assert.ok(text.includes(kept), `the internal overview lost "${kept}"`);
  }
  assert.ok(!text.includes("Opportunity Surface"), "the old O5 title is back");
});

/* ── Insights ──────────────────────────────────────────────────────────── */

test("why now · a signal whose trigger the client read withholds draws no empty card", () => {
  for (const audience of ["customer", "internal"]) {
    const text = page("ClientOverview", audience);
    assert.match(text, /1 trigger ·/, `${audience}: the strip counts the faceless signal`);
    assert.match(text, /The regulator published a new rule in June 2026\./, `${audience}: the real card is gone`);
    assert.ok(!/MERGER|LEADERSHIP/.test(text), `${audience}: the faceless card still draws its chip`);
  }
});

test("heatmap · the standard grid opens the client view too; the issue overlay stays internal", () => {
  const client = page("ClientHeatmap", "customer");
  const zennify = page("ClientHeatmap", "internal");
  for (const [who, text] of [["client", client], ["zennify", zennify]]) {
    assert.match(text, /Standard/, `${who}: no Standard view`);
    assert.match(text, /Zoom/, `${who}: the heatmap did not open on the standard grid`);
    assert.ok(!text.includes("not part of the customer view"), `${who}: the grid is still locked`);
  }
  assert.ok(!client.includes("Issues"), "the client heatmap offers the Context issue overlay");
  assert.match(zennify, /Issues/, "the Zennify heatmap lost its issue overlay");
});

test("insights · the client view is headed for its reader, without the landscape", () => {
  const text = page("ClientInsights", "customer");
  assert.match(text, /Key insights/i);
  assert.match(text, new RegExp(`Recommendations for ${NAME}`));
  assert.ok(!/\d+ insight cards/.test(text), "the client heading still counts cards");
  assert.ok(!text.includes("Technology landscape"), "the client view renders the technology landscape");
});

test("insights · the Zennify view keeps its count and the landscape", () => {
  const text = page("ClientInsights", "internal");
  assert.match(text, /1 insight cards/);
  assert.ok(text.includes("Technology landscape"));
  assert.ok(!text.includes("Recommendations for"), "the client heading leaked into the internal view");
});

/* ── Chrome ────────────────────────────────────────────────────────────── */

test("client bar · client copy, client tabs, a link to share", () => {
  const text = page("ClientBar", "customer", { tab: "overview" });
  assert.match(text, /Client Dashboard/);
  assert.match(text, /Switch back to Zennify view/);
  assert.match(text, /Generate client link/);
  assert.ok(!/Customer/.test(text), `"Customer" is still on the client bar: ${text}`);
  assert.ok(!/share-safe presentation mode/.test(text), "the old banner sentence is back");
  for (const tab of ["Platform", "Tech stack", "Context", "Health", "Runs"]) {
    assert.ok(!new RegExp(`\\b${tab}\\b`).test(text), `the client tab strip carries ${tab}`);
  }
  for (const tab of ["Overview", "Insights", "Heatmap"]) {
    assert.ok(text.includes(tab), `the client tab strip lost ${tab}`);
  }
});

test("generate client link · recipients first, then the link", () => {
  const { win } = H.load();
  H.installEntity(ID, pages());
  const html = H.render(win.ShareDialog, { entity: ENTITY, run: RUN, onClose() {} },
                        { audience: "customer", pushToast() {} });
  const text = H.textOf(html);
  assert.match(text, /Generate client link/);
  assert.match(text, /Recipient email\(s\) · added to this link's allowlist/);
  assert.match(html, /<textarea[^>]*id="share-recipients"/, "no recipient field before the link exists");
  // Nothing is minted with an empty allowlist: the button is disabled until
  // an address is entered (and /api/share refuses an empty list as well).
  assert.match(html, /<button[^>]*disabled=""[^>]*>Generate link<\/button>/,
    "Generate link is pressable with no recipient");
  assert.ok(!/readonly/i.test(html), "a link is shown before one was generated");
});

test("client bar · the Zennify view keeps Platform and Tech stack, and no banner", () => {
  const text = page("ClientBar", "internal", { tab: "overview" });
  assert.ok(text.includes("Platform") && text.includes("Tech stack"));
  assert.ok(!text.includes("Client Dashboard"));
});

test("one list decides the client tabs, and the link builder honours it", () => {
  const { win } = H.load();
  assert.deepStrictEqual([...win.CLIENT_TABS], ["overview", "insights", "heatmap"]);
  for (const t of ["platform", "techstack", "context", "health", "runs"]) {
    assert.strictEqual(win.clientTabAllowed(t), false, t);
  }
  win.location.origin = "https://dmai.example";
  win.location.pathname = "/";
  const url = win.clientLinkUrl(ID, "techstack", RUN.id);
  assert.strictEqual(url,
    `https://dmai.example/#/clients/${ID}/overview?view=client&run=${encodeURIComponent(RUN.id)}`);
});

/* ── The link frame, in a browser ─────────────────────────────────────── */

const skip = browserSkip();
const BOOT = {
  authed: true, role: "ADMIN", email: "dma@zennify.com", name: "QA",
  catalogue_version: "v7.0", dev_login: true,
  subvertical_labels: { CREDIT_UNION: "Credit union" },
  entities: [{ ...ENTITY, subcaps: undefined, status: "ACTIVE", data_source: "PROJECT_API",
               size_tier: "MEDIUM" },
             { ...ENTITY, id: "other-client", slug: "other-client", name: "Other Client",
               subcaps: undefined, status: "ACTIVE", size_tier: "MEDIUM" }],
  active_runs: [], pending_review: [],
};

async function open(browser, base, hash, then) {
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const p = await ctx.newPage();
  const errors = [];
  p.on("pageerror", (e) => errors.push(String(e.message)));
  const P = pages();
  await p.route("**/api/entity/**", (r) => {
    const m = new URL(r.request().url()).pathname.match(/\/api\/entity\/[^/]+\/([^/]+)/);
    const body = m && P[m[1]];
    r.fulfill(body
      ? { status: 200, contentType: "application/json",
          body: JSON.stringify({ entity: { display_id: ID, entity_name: NAME },
                                 run: { run_id: RUN.run_id, request_id: RUN.id }, ...body }) }
      : { status: 404, contentType: "application/json", body: '{"error":"not_found"}' });
  });
  await p.goto(`${base}/${hash}`, { waitUntil: "domcontentloaded" });
  await settle(p);
  if (then) { await p.evaluate((h) => { location.hash = h; }, then); await settle(p); }
  const seen = await p.evaluate(() => ({
    hash: location.hash,
    nav: !!document.querySelector(".sb-a"),
    topbar: !!document.querySelector(".topbar"),
    toggle: !!document.querySelector(".audience-toggle"),
    ip: !!document.querySelector(".ip-tab"),
    banner: !!document.querySelector(".customer-banner"),
    tabs: [...document.querySelectorAll(".client-tab")].map((n) => n.innerText.trim()),
    text: document.body.innerText || "",
  }));
  await ctx.close();
  return { ...seen, errors };
}

test("client link · the dashboard alone, and no way out of it", { skip }, async () => {
  const pw = resolvePlaywright();
  const browser = await pw.chromium.launch({ executablePath: resolveChromium(), args: ["--no-sandbox"] });
  const { server, base } = await startServer(BOOT);
  try {
    const link = await open(browser, base, `#/clients/${ID}/overview?view=client`);
    assert.deepStrictEqual(link.errors, []);
    assert.deepStrictEqual(link.tabs, ["Overview", "Insights", "Heatmap"]);
    for (const k of ["nav", "topbar", "toggle", "ip", "banner"]) {
      assert.strictEqual(link[k], false, `the client link renders the ${k}`);
    }
    assert.match(link.text, new RegExp(NAME));
    assert.ok(!link.text.includes("Meeting prep"));

    // A withdrawn tab lands on the overview, still inside the link.
    const tech = await open(browser, base, `#/clients/${ID}/techstack?view=client`);
    assert.match(tech.hash, new RegExp(`^#/clients/${ID}/overview\\?.*view=client`));
    assert.strictEqual(tech.nav, false);

    // Every way out — the directory, the dashboard, another client — answers
    // with the shared client, never the Zennify app.
    // Typed into the address bar, not just clicked: the login page, admin,
    // alerts, a withdrawn tab, a sub-route under one, Context.
    for (const out of ["#/clients", "#/", "#/clients/other-client/overview", "#/prospecting",
                       "#/login", "#/alerts", "#/admin", "#/admin/import",
                       `#/clients/${ID}/platform`, `#/clients/${ID}/techstack/T-01`,
                       `#/clients/${ID}/context`, `#/clients/${ID}/health`, "#/nonsense"]) {
      const esc = await open(browser, base, `#/clients/${ID}/insights?view=client`, out);
      assert.strictEqual(esc.nav, false, `${out} reached the sidebar`);
      assert.strictEqual(esc.topbar, false, `${out} reached the top bar`);
      assert.ok(!esc.text.includes("Other Client"), `${out} reached another client`);
      assert.match(esc.text, new RegExp(NAME), `${out} lost the shared client`);
      assert.match(esc.hash, new RegExp(`^#/clients/${ID}/(overview|insights|heatmap)\\?.*view=client`),
                   `${out} left the client tabs (${esc.hash})`);
      assert.deepStrictEqual(esc.tabs, ["Overview", "Insights", "Heatmap"], `${out} changed the tab strip`);
      assert.ok(!/Sign in|Not authorised|Page not found/.test(esc.text), `${out} drew a Zennify page`);
    }

    // The three client tabs stay where they are.
    for (const tab of ["overview", "insights", "heatmap"]) {
      const on = await open(browser, base, `#/clients/${ID}/overview?view=client`, `#/clients/${ID}/${tab}?view=client`);
      assert.match(on.hash, new RegExp(`^#/clients/${ID}/${tab}\\?`), `${tab} bounced (${on.hash})`);
    }

    // The same app without the param is the Zennify app, unchanged.
    const app = await open(browser, base, `#/clients/${ID}/overview`);
    assert.strictEqual(app.nav, true);
    assert.strictEqual(app.toggle, true);
    assert.ok(app.tabs.includes("Platform") && app.tabs.includes("Tech stack"));
  } finally {
    await browser.close();
    server.close();
  }
});
