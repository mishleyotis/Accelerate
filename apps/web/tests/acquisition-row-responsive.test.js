/* The acquisition row must not push text outside its card, at any width.
 *
 * Reported 2026-08-22 from the promoted T. Rowe Price page: "Acquisition card
 * has text that is skewed; responsive design lacking."
 *
 * The cause, measured on that run's own payload. `kind` came through as
 *
 *     "Private markets and alternative credit investment manager (acquisition)"
 *
 * — 68 characters — and the row renders it inside `.b`, a 10px chip whose CSS
 * is `white-space: nowrap`. Three things then compound:
 *
 *   .row  is `display:flex` with NO `flex-wrap`, so nothing moves to a
 *         second line;
 *   .b    refuses to wrap or shrink;
 *   the target name is `flex:1` with the default `min-width:auto`, so it
 *         cannot shrink below its own text either.
 *
 * The row is therefore wider than the card and the text runs out of it.
 * `status` and `maturity_effect` are enums, so they are safe as chips; `kind`
 * is free text the contract does not bound, which is why it is the field that
 * breaks the layout.
 *
 * MEASURED, NOT ASSERTED. A test that checked for `flexWrap: "wrap"` in the
 * source would pass while a different rule reintroduced the overflow. This
 * renders the real page in Chromium at five widths and compares scrollWidth
 * against clientWidth, which is the property the reader actually sees.
 *
 * Run with `npm run test:web`.
 */
const { test } = require("node:test");
const assert = require("node:assert");

const { resolvePlaywright, startServer, settle, selectAudience,
        resolveChromium, browserSkip } = require("./proto-page-harness");

const ENTITY = "test-asset-manager";
const RUN_ID = "DMA-ASM-TAM-20260801-0001";

const pw = resolvePlaywright();
const CHROME = resolveChromium();
const skip = browserSkip();

/* The real string from the T. Rowe Price run, kept verbatim: a shorter stand-in
   would not reproduce the overflow it was reported for. */
const LONG_KIND = "Private markets and alternative credit investment manager (acquisition)";

const BOOT = {
  authed: true, role: "ADMIN", email: "dma@zennify.com", name: "QA",
  catalogue_version: "v7.0", dev_login: true,
  subvertical_labels: { ASSET_MANAGER: "Asset manager" },
  entities: [{
    id: ENTITY, slug: ENTITY, name: "Test Asset Manager",
    subvertical: "ASSET_MANAGER", size_tier: "LARGE", hq: "Baltimore, MD",
    status: "ACTIVE", data_source: "PROJECT_API", assessment_date: "2026-08-01",
    overall: 3.1, pillar_scores: {}, oss: {}, footprint: ["MD"], runs: [
      { id: RUN_ID, date: "2026-08-01", status: "ACTIVE", overall: 3.1,
        evidence_mode: "PUBLIC", subcap_count: 705 },
    ],
  }],
  active_runs: [], pending_review: [],
};

const ENV = {
  produced_at: "2026-08-01T00:00:00Z", producer_version: "test",
  e_ids: ["E-CC-001"], internal_only: [],
  narrative_thread: "The line through this page, written last.",
};

function contextPage() {
  return {
    sections: {
      acquisitions: { data: { ...ENV, rows: [{
        closed_on: "2021-12-29",
        target_name: "Oak Hill Advisors",
        kind: LONG_KIND,
        status: "COMPLETE",
        scale_metrics: "$4.2B disclosed purchase price; assets under management "
          + "of roughly $53B at announcement",
        integration_target: null,
        affected_subcap_ids: ["P1C1.1.1"],
        maturity_effect: "NEUTRAL",
        effect_note: "The platform was operated as a standalone affiliate, so "
          + "no assessed cell moved on the strength of the transaction alone.",
        e_ids: ["E-CC-001"],
      }] } },
      issue_register: { data: { ...ENV, verified_absent: true, issues: [] } },
      timeline: { data: { ...ENV, events: [], arc_shape: null, storyline: null,
                          verified_sparse: true } },
      context_sentiment: { data: { ...ENV, context_tiles: [] } },
      regulatory_standing: { data: { ...ENV, primary_regulator: "SEC",
        license_type: "Registered investment adviser", charter_date: "1937-01-01",
        jurisdictions: ["US"], additional_regulators: [],
        enforcement_actions: [], absence_of_enforcement: null } },
    },
  };
}

/* Every width the stylesheet has an opinion about, plus one below its
   smallest breakpoint. The card collapses to one column at 900 and 760; the
   overflow was reported at full width, so the wide cases matter most. */
const WIDTHS = [1512, 1180, 900, 760, 420];

async function overflowAt(width) {
  const { server, base } = await startServer(BOOT);
  const browser = await pw.chromium.launch({ executablePath: CHROME, args: ["--no-sandbox"] });
  try {
    const page = await browser.newPage({ viewport: { width, height: 1200 } });
    await page.route("**/api/entity/**", async (route) => {
      const which = new URL(route.request().url()).pathname.split("/").pop().split("?")[0];
      const body = which === "context" ? contextPage() : { sections: {} };
      return route.fulfill({ status: 200, contentType: "application/json",
                             body: JSON.stringify(body) });
    });
    await page.goto(`${base}/#/clients/${ENTITY}/context`, { waitUntil: "domcontentloaded" });
    await settle(page);
    await selectAudience(page, "internal");
    await settle(page);

    return await page.evaluate((kind) => {
      // The card that holds the acquisition row, found by its own heading so
      // the test does not depend on DOM position.
      const cards = [...document.querySelectorAll(".card")];
      const card = cards.find((c) => (c.textContent || "").includes("Acquisition history"));
      if (!card) return { found: false };
      const chip = [...card.querySelectorAll("span")]
        .find((s) => (s.textContent || "").trim() === kind);
      const worst = [card, ...card.querySelectorAll("*")].reduce((acc, n) => {
        const over = n.scrollWidth - n.clientWidth;
        return over > acc.over ? { over, tag: n.tagName, text: (n.textContent || "").slice(0, 60) } : acc;
      }, { over: 0, tag: null, text: "" });
      return {
        found: true,
        chipPresent: !!chip,
        cardOverflow: card.scrollWidth - card.clientWidth,
        worst,
        docOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      };
    }, LONG_KIND);
  } finally { await browser.close(); server.close(); }
}

for (const width of WIDTHS) {
  test(`acquisition row · no overflow at ${width}px`, { skip }, async () => {
    const r = await overflowAt(width);
    assert.ok(r.found, "the Acquisition history card did not render");
    assert.ok(r.chipPresent,
      "the long `kind` value is not on the page — the fixture stopped "
      + "reproducing the reported condition");
    // One pixel of slack for sub-pixel rounding; the reported defect was tens
    // of pixels, so this still fails loudly on a real regression.
    assert.ok(r.cardOverflow <= 1,
      `the acquisition card overflows by ${r.cardOverflow}px at ${width}px. `
      + `Worst node: <${r.worst.tag}> over by ${r.worst.over}px — `
      + `${JSON.stringify(r.worst.text)}`);
  });
}

test("acquisition row · the page never scrolls sideways", { skip }, async () => {
  /* The reader-facing form of the same fault: a card that overflows its own
     box usually drags the document with it. */
  const r = await overflowAt(1180);
  assert.ok(r.found, "the Acquisition history card did not render");
  assert.ok(r.docOverflow <= 1,
    `the document scrolls horizontally by ${r.docOverflow}px`);
});
