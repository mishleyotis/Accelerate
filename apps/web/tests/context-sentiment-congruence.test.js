/* The Context sentiment grid renders every reading the Overview bars carry,
 * and adding one does not distort the page.
 *
 * Owner, 2026-08-23: "Gulf still has no sentiment overview on the context
 * page; wasn't there supposed to be congruency with the overview page? Which
 * autocorrecting tests are there to ensure this usually happens without
 * distorting the UI of the context page?"
 *
 * CG-43 makes the two surfaces agree in the PAYLOAD — a reading drawn as a
 * bar on the Overview must exist as a row in the Context grid, keyed on e_id.
 * That is a data rule and it cannot see a page. This is the other half: the
 * second reading has to reach a reader, and the card that gains it has to
 * stay inside its box.
 *
 * The distinction the card makes, and the reason this test does not simply
 * count values on screen: the grid renders ONE TILE PER AUDIENCE, leading
 * with that audience's first row and saying how many more it holds. So a
 * customer tile with two readings shows one number and "+1 more". That is
 * deliberate — flattening every row into its own tile made this card seven
 * tiles and three rows deep — and it means congruence is proved by the count
 * being carried, not by both numbers being on the face.
 *
 * WHAT WOULD REGRESS WITHOUT THIS. Adding the second Axos bar was a
 * one-line payload change; if the tile silently dropped it, the Context page
 * would keep saying "one reading" while the Overview said two, and CG-43
 * would still pass because the payloads agree. A gate on the data and a test
 * on the render answer different questions.
 *
 * Run with `npm run test:web`.
 */
const { test } = require("node:test");
const assert = require("node:assert");

const { resolvePlaywright, startServer, settle, selectAudience,
        resolveChromium, browserSkip } = require("./proto-page-harness");

const ENTITY = "test-bank";
const RUN_ID = "DMA-ASM-TB-20260801-0001";

const pw = resolvePlaywright();
const CHROME = resolveChromium();
const skip = browserSkip();

const BOOT = {
  authed: true, role: "ADMIN", email: "dma@zennify.com", name: "QA",
  catalogue_version: "v7.0", dev_login: true,
  subvertical_labels: { REGIONAL_BANK: "Regional bank" },
  entities: [{
    id: ENTITY, slug: ENTITY, name: "Test Bank",
    subvertical: "REGIONAL_BANK", size_tier: "LARGE", hq: "San Diego, CA",
    status: "ACTIVE", data_source: "PROJECT_API", assessment_date: "2026-08-01",
    overall: 1.9, pillar_scores: {}, oss: {}, footprint: ["CA"], runs: [
      { id: RUN_ID, date: "2026-08-01", status: "ACTIVE", overall: 1.9,
        evidence_mode: "PUBLIC", subcap_count: 355 },
    ],
  }],
  active_runs: [], pending_review: [],
};

const ENV = {
  produced_at: "2026-08-01T00:00:00Z", producer_version: "test",
  e_ids: ["E-CC-280"], internal_only: [],
  narrative_thread: "The line through this page, written last.",
};

/* Axos's two customer readings, verbatim in the fields the grid renders: the
   flagship application and UFB Direct, the bank's own direct-to-consumer
   brand. Two surfaces of one bank, which is why they share an audience. */
const ROW_A = {
  source: "Apple App Store lookup application programming interface (API) - "
        + "Axos All-In-One Mobile Banking (lifetime average across all versions)",
  rating: 4.71, scale: 5, n: 19139, as_of: "2026-08-17", e_id: "E-CC-280",
  url: "https://apps.apple.com/us/app/axos-all-in-one-mobile-banking/id1396586421",
  note: "A lifetime average over a large sample on the channel that carries "
      + "the whole relationship for a branchless bank.",
};
const ROW_B = {
  source: "Apple App Store lookup application programming interface (API) - "
        + "UFB Direct (lifetime average across all versions)",
  rating: 4.83, scale: 5, n: 19831, as_of: "2026-08-23", e_id: "E-CC-370",
  url: "https://apps.apple.com/us/app/ufb-direct/id1448396485",
  note: "The bank's own direct-to-consumer brand, on the same store and the "
      + "same channel as the row above.",
};

function contextPage(rows) {
  return {
    sections: {
      context_sentiment: { data: { ...ENV,
        context_tiles: rows.length
          ? [{ audience: "customer", rows, e_ids: rows.map((r) => r.e_id) }]
          : [] } },
      issue_register: { data: { ...ENV, verified_absent: true, issues: [] } },
      timeline: { data: { ...ENV, events: [], arc_shape: null, storyline: null,
                          verified_sparse: true } },
      acquisitions: { data: { ...ENV, rows: [] } },
      regulatory_standing: { data: { ...ENV, primary_regulator: "OCC",
        license_type: "National bank", charter_date: "2000-07-04",
        jurisdictions: ["US"], additional_regulators: [],
        enforcement_actions: [], absence_of_enforcement: null } },
    },
  };
}

async function renderAt(width, rows) {
  const { server, base } = await startServer(BOOT);
  const browser = await pw.chromium.launch({ executablePath: CHROME,
                                             args: ["--no-sandbox"] });
  try {
    const page = await browser.newPage({ viewport: { width, height: 1200 } });
    await page.route("**/api/entity/**", async (route) => {
      const which = new URL(route.request().url()).pathname.split("/").pop().split("?")[0];
      const body = which === "context" ? contextPage(rows) : { sections: {} };
      return route.fulfill({ status: 200, contentType: "application/json",
                             body: JSON.stringify(body) });
    });
    await page.goto(`${base}/#/clients/${ENTITY}/context`,
                    { waitUntil: "domcontentloaded" });
    await settle(page);
    await selectAudience(page, "internal");
    await settle(page);

    return await page.evaluate(() => {
      const cards = [...document.querySelectorAll(".card")];
      const card = cards.find((c) => /sentiment/i.test(c.textContent || ""));
      if (!card) return { found: false };
      const text = card.textContent || "";
      // The worst overflow anywhere inside the card, and the document's own.
      const worst = [card, ...card.querySelectorAll("*")].reduce((acc, n) => {
        const over = n.scrollWidth - n.clientWidth;
        return over > acc.over
          ? { over, tag: n.tagName, text: (n.textContent || "").slice(0, 70) }
          : acc;
      }, { over: 0, tag: null, text: "" });
      return {
        found: true,
        text,
        cardOverflow: card.scrollWidth - card.clientWidth,
        worst,
        docOverflow: document.documentElement.scrollWidth
                   - document.documentElement.clientWidth,
      };
    });
  } finally { await browser.close(); server.close(); }
}

/* Wide first: the card lays out as a row of tiles and an overflow shows up
   there before it shows up narrow. 420 is below the smallest breakpoint. */
const WIDTHS = [1512, 1180, 900, 420];

test("context sentiment · the second reading is carried, not dropped",
     { skip }, async () => {
  const one = await renderAt(1512, [ROW_A]);
  const two = await renderAt(1512, [ROW_A, ROW_B]);
  assert.ok(one.found && two.found, "the sentiment card did not render");

  // The lead reading is on the face in both.
  assert.match(one.text, /4\.7/, "the first reading is missing with one row");
  assert.match(two.text, /4\.7/, "the first reading is missing with two rows");

  // …and the second is ACKNOWLEDGED rather than silently absent. One tile per
  // audience is the card's design, so the proof is the count it carries.
  assert.match(two.text, /\+1 more/,
    "a second customer reading rendered no '+1 more' — the Context grid is "
    + "showing one reading while the Overview shows two, which is exactly the "
    + "divergence CG-43 refuses in the payload");
  assert.ok(!/\+1 more/.test(one.text),
    "'+1 more' appeared with only one row — the affordance no longer tracks "
    + "the row count, so it cannot prove anything");
});

test("context sentiment · both samples reach the reader", { skip }, async () => {
  const r = await renderAt(1512, [ROW_A, ROW_B]);
  assert.ok(r.found);
  // n is the interpretability field the contract insists on: "no n -> not a
  // signal, do not render a number". The lead row states its own.
  assert.match(r.text, /19,139/,
    "the lead reading's sample size is not rendered, so the number on the "
    + "card is a rating nobody can weigh");
});

for (const width of WIDTHS) {
  test(`context sentiment · two readings do not distort the card at ${width}px`,
       { skip }, async () => {
    const r = await renderAt(width, [ROW_A, ROW_B]);
    assert.ok(r.found, "the sentiment card did not render");
    assert.equal(r.cardOverflow, 0,
      `the sentiment card overflows by ${r.cardOverflow}px at ${width}px`);
    assert.equal(r.worst.over, 0,
      `${r.worst.tag} overflows by ${r.worst.over}px at ${width}px: `
      + `"${r.worst.text}"`);
    assert.equal(r.docOverflow, 0,
      `the context page scrolls horizontally by ${r.docOverflow}px at ${width}px`);
  });
}

test("context sentiment · an entity with no rated source says so", { skip },
     async () => {
  /* Gulf: a business-to-business receivables lender accumulates no consumer
     review estate, so neither surface carries a reading. CG-43 calls that
     congruent and passes it; the page still owes the reader a sentence. A
     blank card here is the defect that made an honest thin run look broken. */
  const r = await renderAt(1512, []);
  assert.ok(r.found, "the sentiment card vanished entirely when empty");
  assert.ok((r.text || "").replace(/\s+/g, " ").trim().length > 20,
    "the sentiment card rendered empty rather than stating its absence");
  assert.equal(r.docOverflow, 0);
});
