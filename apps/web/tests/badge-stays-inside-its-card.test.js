/* No badge escapes the card it is drawn in — measured in the DOM, not asserted
 * in the stylesheet.
 *
 * Reported 2026-09-02 from the promoted Golden 1 platform page: readiness
 * chips rendered clipped mid-word at the card edge —
 *
 *     "Governed member domain owed in the cat…"
 *     "Licence and user-seat audit decides a…"
 *
 * `badge-never-shrinks.test.js` pins the CSS contract that fixes this
 * (`white-space: normal` + `max-width: 100%` + `overflow-wrap: anywhere`).
 * That test reads app.css and would keep passing if a call site imposed its
 * own `nowrap`, or wrapped a badge in a fixed-width box, or if a future
 * layout change reintroduced the pressure somewhere else entirely. This one
 * renders the page in a browser and measures pixels, so it fails for any of
 * those.
 *
 * The fixture's basis labels are the promoted run's own, including the two
 * that clipped, and one deliberately longer than any of them: a status label
 * has no contract length, so the layout must hold at any length rather than
 * at the length the producer happened to write.
 *
 * Three widths, because the defect is width-dependent and 1512px hides it.
 *
 * Run with `npm run test:web`.
 */
const { test } = require("node:test");
const assert = require("node:assert");

const { resolvePlaywright, startServer, settle, selectAudience,
        resolveChromium, browserSkip } = require("./proto-page-harness");

const ENTITY = "test-credit-union";
const RUN_ID = "DMA-ASM-TCU-20260801-0001";

const pw = resolvePlaywright();
const CHROME = resolveChromium();
const skip = browserSkip();

const BOOT = {
  authed: true, role: "ADMIN", email: "dma@zennify.com", name: "QA",
  catalogue_version: "v7.0", dev_login: true,
  subvertical_labels: { CREDIT_UNION: "Credit union" },
  entities: [{
    id: ENTITY, slug: ENTITY, name: "Test Credit Union",
    subvertical: "CREDIT_UNION", size_tier: "MEDIUM", hq: "Sacramento, CA",
    status: "ACTIVE", data_source: "PROJECT_API", assessment_date: "2026-08-01",
    overall: 2.25, pillar_scores: {}, oss: {}, footprint: ["CA"], runs: [
      { id: RUN_ID, date: "2026-08-01", status: "ACTIVE", overall: 2.25,
        evidence_mode: "PUBLIC", subcap_count: 690 },
    ],
  }],
  active_runs: [], pending_review: [],
};

const ENV = {
  produced_at: "2026-08-01T00:00:00Z", producer_version: "test",
  e_ids: ["E-CC-188"], internal_only: [],
  narrative_thread: "The line through this page, written last from what was produced.",
};

/* Verbatim from the promoted run, plus one longer than any of them. */
const BASES = [
  "Measured below the 2.5 minimum",
  "Register entry inferred, not confirmed",
  "Decision rights unsettled",
  "Signed event and attribute map owed",
  "Lead-capture audit owed from Golden 1",
  "Governed member domain owed in the catalogue",
  "Licence and user-seat audit decides a phased rollout",
  "Signed household rule set owed",
  "A deliberately longer status label than any the producer has yet written, "
    + "to prove the layout holds at a length no contract bounds",
];

function platformPage() {
  return {
    sections: {
      recommendations: { data: { ...ENV, recommendations: [{
        rec_id: "REC-01", phase: "PH-1",
        title: "Governed data foundation and enterprise reference architecture",
        l3_area: "[L3-DB-UNITY-CATALOG] Databricks Unity Catalog",
        /* Each condition must be DISTINCT: the view groups prerequisites by
           their condition, so nine rows sharing one string collapse to one
           and the test silently measures a single chip. */
        prerequisites: BASES.map((basis, i) => ({
          condition: `Readiness condition ${i + 1}: a governed source of member `
            + `truth exists to hydrate the record`,
          basis,
          note: "A governed source of member truth exists to hydrate the record.",
          verdict: i % 2 ? "MET" : "UNMET",
          /* No `cell`. A prerequisite that names one renders the THRESHOLD
             row instead — cell chip, name, verdict — which has no basis chip
             at all, so a fixture that sets it silently drops that row from
             what this test measures. The reported defect was on condition
             rows, which is what these are. */
          minimum: 2.5, current: 2.1,
        })),
      }] } },
    },
  };
}

async function renderPlatform(width) {
  const { server, base } = await startServer(BOOT);
  const browser = await pw.chromium.launch({ executablePath: CHROME,
                                             args: ["--no-sandbox"] });
  try {
    const page = await browser.newPage({ viewport: { width, height: 1600 } });
    await page.route("**/api/entity/**", async (route) => {
      const which = new URL(route.request().url()).pathname
        .split("/").pop().split("?")[0];
      const body = which === "platform" ? platformPage() : { sections: {} };
      return route.fulfill({ status: 200, contentType: "application/json",
                             body: JSON.stringify(body) });
    });
    await page.goto(`${base}/#/clients/${ENTITY}/platform`,
                    { waitUntil: "domcontentloaded" });
    await settle(page);
    await selectAudience(page, "internal");
    return { page, browser, server };
  } catch (e) {
    await browser.close(); server.close(); throw e;
  }
}

/* Every `.b` badge, with how far it escapes its nearest card ancestor. A
   badge is allowed to touch the card's padding edge; 1px of tolerance keeps
   sub-pixel layout from reporting a defect that does not exist. */
async function escapees(page) {
  return page.evaluate(() => {
    const out = [];
    for (const el of document.querySelectorAll(".b")) {
      const card = el.closest(".card");
      if (!card) continue;
      const b = el.getBoundingClientRect(), c = card.getBoundingClientRect();
      if (b.width === 0 || b.height === 0) continue;
      const over = Math.max(b.right - c.right, c.left - b.left);
      if (over > 1) {
        out.push({ text: (el.textContent || "").trim().slice(0, 46),
                   over: Math.round(over) });
      }
    }
    return out;
  });
}

for (const width of [1512, 1180, 960]) {
  test(`platform readiness · no badge escapes its card at ${width}px`,
       { skip }, async () => {
    const { page, browser, server } = await renderPlatform(width);
    try {
      const bad = await escapees(page);
      assert.deepEqual(bad, [],
        `badge(s) outside their card: ${JSON.stringify(bad)}`);
    } finally { await browser.close(); server.close(); }
  });
}

test("platform readiness · every basis label is rendered in full", { skip },
     async () => {
  /* The other half of the defect, and the one a pixel assertion cannot see:
     a chip that fits because its text was cut is still wrong. The clipping
     was CSS, so the DOM held the whole string either way — this asserts what
     the reader can actually finish reading. */
  const { page, browser, server } = await renderPlatform(960);
  try {
    const texts = await page.evaluate(() =>
      Array.from(document.querySelectorAll(".b"), (e) => (e.textContent || "").trim()));
    const missing = BASES.filter((b) => !texts.includes(b));
    assert.deepEqual(missing, [],
      `basis label(s) not rendered whole: ${JSON.stringify(missing)}`);
  } finally { await browser.close(); server.close(); }
});

test("platform readiness · the page never scrolls sideways", { skip }, async () => {
  const { page, browser, server } = await renderPlatform(960);
  try {
    const over = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth);
    assert.ok(over <= 0, `page scrolls sideways by ${over}px`);
  } finally { await browser.close(); server.close(); }
});
