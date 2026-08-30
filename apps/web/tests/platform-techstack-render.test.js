/* D4 Platform and T1 Tech stack: four defects a reader met on screen.
 *
 * Every case here reproduces a SHAPE the promoted payload actually carried on
 * run d7ed1d90 (Logix Federal Credit Union, 2026-08-18) and asserts what a
 * reader sees. The fixture is synthetic — no client content lives in this
 * repo — but the shapes are copied from that run field for field, because a
 * test written against a tidied-up shape would have passed while the app was
 * printing JSON at a client.
 *
 *   P-05  `l3_area` promoted as "[L3-SF-DC-CORE] Data Cloud (count: 3)" — the
 *         producer's own vote count welded onto a human platform label. It
 *         reached the tile sub-line, the platform column of 21 gap rows and
 *         every catalogue-path tooltip, in the CUSTOMER audience as well.
 *   P-06  and because a recommendation states the same area WITHOUT the
 *         tally, `rec.l3 === tile.area` was false on four of five tiles: they
 *         read "0 recs" over recommendations that name them, under a footer
 *         asserting those recommendations "sit in an area no promoted
 *         platform addresses". One defect, two false statements.
 *   P-01  `stairstep.ladder.steps[].blocking_findings[]` promoted as an array
 *         of JSON-ENCODED STRINGS, so the ladder rail printed
 *         {"f_id": "F-77", "e_ids": [...], "title": "…"} at the reader.
 *   T-05  the tech register printed bare catalogue codes — P4C3.2.1 P4C3.2.2
 *         — where the capability's name belongs; the run names all of them on
 *         its own cell grain, which is where the name is READ from.
 *
 * Both audiences, because all four were measured in both. Run with
 * `npm run test:web`; reads the COMPILED bundle, never the jsx.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");

const { resolvePlaywright, startServer, settle,
        resolveChromium, browserSkip } = require("./proto-page-harness");

const ENTITY = "test-credit-union";
const RUN_ID = "DMA-ASM-TCU-20260801-0001";

/* The two areas, exactly as the run stated them: the recommendation writes
   the label clean, the gap rows write it with the tally on the end. The whole
   of P-05 and P-06 is the difference between these two constants. */
const AREA_CLEAN = "[L3-SF-DC-CORE] Data Cloud";
const AREA_TALLIED = "[L3-SF-DC-CORE] Data Cloud (count: 3)";
const AREA2_CLEAN = "[L3-DB-MLFLOW] MLflow (Databricks-managed)";
// What a reader should end up with. The bracketed id is catalogue grammar:
// `ccg_l3_platforms` maps it to a vendor and a platform name, and until
// 2026-08-18 nothing read that table, so the code rendered as itself — 59
// occurrences of 7 distinct codes on one promoted run. Resolved where the
// catalogue knows it, dropped where it does not; either way the human half
// survives and the code does not reach the page.
const AREA_HUMAN = "Data Cloud";
const AREA2_HUMAN = "MLflow (Databricks-managed)";

const BLOCKING_TITLE =
  "Model governance is the one control the compliance build did not buy";
// The shape the payload carried: an object, JSON-encoded into a string.
const BLOCKING_SERIALISED = JSON.stringify({
  f_id: "F-77", e_ids: ["E-CC-195", "E-CC-199"], title: BLOCKING_TITLE,
});

const BOOT = {
  authed: true, role: "ADMIN", email: "dma@zennify.com", name: "QA",
  catalogue_version: "v7.0", dev_login: true,
  subvertical_labels: { CREDIT_UNION: "Credit union" },
  entities: [{
    id: ENTITY, slug: ENTITY, name: "Test Credit Union",
    subvertical: "CREDIT_UNION", size_tier: "MEDIUM", hq: "Chicago, IL",
    status: "ACTIVE", data_source: "PROJECT_API", assessment_date: "2026-08-01",
    overall: 2.0, pillar_scores: { P1: 2.0, P2: 2.0, P3: 2.0, P4: 2.0 },
    oss: {}, footprint: ["IL"], runs: [
      { id: RUN_ID, date: "2026-08-01", status: "ACTIVE", overall: 2.0,
        evidence_mode: "PUBLIC", subcap_count: 4 },
    ],
  }],
  active_runs: [], pending_review: [],
};

const sec = (data, extra) => ({
  data, e_ids: [], produced_at: "2026-08-01T00:00:00Z",
  producer_version: "test", provenance: "test", empty_state: null, ...extra,
});

/* The run's own cell grain. The register and the gap rows cite these ids;
   this is the only place their names exist, which is the point of T-05. */
const SUBCAPS = [
  { subcap_id: "P2C4.5.1", subcap_name: "Product Propensity Modeling",
    pillar_id: "P2", category_id: "P2C4", score: 2.0, is_thin_evidence: true },
  { subcap_id: "P2C4.2.1", subcap_name: "Next Best Action (NBA)",
    pillar_id: "P2", category_id: "P2C4", score: 1.0, is_thin_evidence: true },
  { subcap_id: "P2C4.5.5", subcap_name: "CLV Prediction Models",
    pillar_id: "P2", category_id: "P2C4", score: 1.0, is_thin_evidence: true },
  { subcap_id: "P4C3.2.1", subcap_name: "Application Portfolio Management",
    pillar_id: "P4", category_id: "P4C3", score: 2.0, is_thin_evidence: true },
  { subcap_id: "P4C3.2.2", subcap_name: "Legacy Modernization Strategy",
    pillar_id: "P4", category_id: "P4C3", score: 2.0, is_thin_evidence: false },
];

function payloadFor(page, audience) {
  const run = { run_id: RUN_ID, promoted_at: "2026-08-01T00:00:00Z",
                completed_at: "2026-08-01T00:00:00Z" };
  const entity = { display_id: ENTITY, name: "Test Credit Union",
                   sub_vertical: "CREDIT_UNION" };
  const sections = {};

  if (page === "overview") {
    sections.scores = sec({ composite: 2.0, framing: "A test framing sentence.",
      pillars: [{ pillar_id: "P2", score: 2.0 }, { pillar_id: "P4", score: 2.0 }] });
    // Two promoted tiles. Tile 1's cells are filed under the TALLIED area by
    // the story rows; tile 2's under the clean one — so the join is exercised
    // from both sides in one fixture.
    sections.opportunity = sec({ tiles: [
      { rank: 1, platform: "Salesforce Data Cloud", composite: 66.8,
        addressable_cells: [
          { subcap_id: "P2C4.5.1", name: null, current: 2.0,
            feature_that_addresses_it: "Data Stream" },
          { subcap_id: "P2C4.2.1", name: null, current: 1.0,
            feature_that_addresses_it: "Data Stream" },
          { subcap_id: "P2C4.5.5", name: null, current: 1.0,
            feature_that_addresses_it: "Data Stream" },
        ] },
      { rank: 2, platform: "MLflow (Databricks-managed)", composite: 67.0,
        addressable_cells: [
          { subcap_id: "P4C3.2.1", name: null, current: 2.0,
            feature_that_addresses_it: "MLflow Tracking" },
          { subcap_id: "P4C3.2.2", name: null, current: 2.0,
            feature_that_addresses_it: "MLflow Tracking" },
        ] },
    ] });
  } else if (page === "platform") {
    sections.platform_story = sec({ platforms: [
      { platform: "A member profile that decides", fit_score: null,
        story_md: "A promoted paragraph about the member profile.",
        gaps: [
          { subcap_id: "P2C4.5.1", name: "Product Propensity Modeling",
            pillar: "P2", current_score: 2.0, peer_score: null,
            peer_basis: "cannot_estimate", l3_area: AREA_TALLIED,
            l4_feature: "Data Stream",
            catalogue_path: `P2 > P2C4 > P2C4.5 > P2C4.5.1 > ${AREA_TALLIED} > Data Stream`,
            e_ids: [] },
          { subcap_id: "P2C4.2.1", name: "Next Best Action (NBA)",
            pillar: "P2", current_score: 1.0, peer_score: null,
            peer_basis: "cannot_estimate", l3_area: AREA_TALLIED,
            l4_feature: "Data Stream",
            catalogue_path: `P2 > P2C4 > P2C4.2 > P2C4.2.1 > ${AREA_TALLIED} > Data Stream`,
            e_ids: [] },
          /* The cell no recommendation cites. It matters: the run's
             (cell → area) index refuses an ambiguous answer, so a cell filed
             by BOTH a rec (clean) and a gap row (tallied) resolves to nothing
             at all, and it is the unambiguous rows that carry the tally onto
             the tile. That is the shape the run promoted, and a fixture
             without it would let the tile resolve to no area and hide the
             very leak this asserts. */
          { subcap_id: "P2C4.5.5", name: "CLV Prediction Models",
            pillar: "P2", current_score: 1.0, peer_score: null,
            peer_basis: "cannot_estimate", l3_area: AREA_TALLIED,
            l4_feature: "Data Stream",
            catalogue_path: `P2 > P2C4 > P2C4.5 > P2C4.5.5 > ${AREA_TALLIED} > Data Stream`,
            e_ids: [] },
        ] },
      { platform: "Models that are known and governed", fit_score: null,
        story_md: "A promoted paragraph about model governance.",
        gaps: [
          { subcap_id: "P4C3.2.1", name: "Application Portfolio Management",
            pillar: "P4", current_score: 2.0, peer_score: null,
            peer_basis: "cannot_estimate", l3_area: AREA2_CLEAN,
            l4_feature: "MLflow Tracking",
            catalogue_path: `P4 > P4C3 > P4C3.2 > P4C3.2.1 > ${AREA2_CLEAN} > MLflow Tracking`,
            e_ids: [] },
        ] },
    ], discarded: [
      { platform: "Tableau",
        reason: "Tableau is the reporting layer this institution's own "
          + "business intelligence manager describes her team working in, "
          + "alongside a credit union data warehouse (E-CC-285, E-CC-204), "
          + "so visualisation is an adoption conversation at that layer." },
      { platform: AREA2_CLEAN,
        reason: "Its addressable cells sit inside the service tile and depend "
          + "on the model-governance work at rank two." },
    ] });
    // Both recommendations state their area CLEAN — the shape that made the
    // tile join fail on every tallied area.
    sections.recommendations = sec({ recommendations: [
      { rec_id: "REC-1", title: "Extend the governed data estate",
        l3_area: AREA_CLEAN, l4_feature: "Identity Resolution", phase: 2,
        dma_impact: [{ subcap_id: "P2C4.5.1" }, { subcap_id: "P2C4.2.1" }],
        e_ids: [] },
      { rec_id: "REC-2", title: "Stand up model governance",
        l3_area: AREA2_CLEAN, l4_feature: "MLflow Tracking", phase: 1,
        dma_impact: [{ subcap_id: "P4C3.2.1" }], e_ids: [] },
    ] });
    sections.stairstep = sec({ ladder: { theme: "Data", steps: [
      { step_level: 1, label: "A governed pipeline that reports",
        covered_subcap_ids: ["P4C3.2.1"], current_position: true,
        blocking_findings: [], unlocks: "What rung one unlocks.",
        effort_band: "S", entry_condition: "Held today.", e_ids: [] },
      { step_level: 2, label: "Models that are known and governed",
        covered_subcap_ids: ["P2C4.5.1"], current_position: false,
        blocking_findings: [BLOCKING_SERIALISED],
        unlocks: "What rung two unlocks.", effort_band: "M",
        entry_condition: "Not met today.", e_ids: [] },
    ] } });
    sections.roadmap = sec({ sequencing_basis: "A stated basis.", phases: [
      { phase_id: "PH-1", label: "this year", rec_ids: ["REC-2"] },
      { phase_id: "PH-2", label: "beyond", rec_ids: ["REC-1"] },
    ] });
    sections.starters = sec({ starters: [] });
  } else if (page === "techstack") {
    sections.techstack = sec({ items: [
      { ts_id: "TS-01", product: "Symitar Episys", vendor: "Jack Henry",
        layer: "OPS", status: "CLAIMED", evidence_level: "L2",
        detection_basis: "Named as the core banking system in a case study.",
        // One citation, so the detail sub-page's count badge has to decline
        // its own noun: it read "1 items" on every single-citation product.
        e_ids: ["E-CC-197"], pillar_id: "P4",
        linked_subcap_ids: ["P4C3.2.1", "P4C3.2.2"],
        dma_impact: "What the core reaches, and where it stops.",
        peer_coverage: null, peer_deployments: [] },
      { ts_id: "TS-02", product: "Customer data platform", vendor: null,
        layer: "DATA", status: "ABSENT", evidence_level: "L3",
        detection_basis: "Searched the public record; no platform is named.",
        e_ids: [], pillar_id: "P2",
        linked_subcap_ids: ["P2C4.5.1"],
        dma_impact: null, peer_coverage: null, peer_deployments: [] },
    ], layers: [] });
  }
  return { entity, run, audience: audience || "internal", sections };
}

/* ── the run ─────────────────────────────────────────────────────────── */

const pw = resolvePlaywright();
const CHROME = resolveChromium();
const skip = browserSkip();

async function openRoute(browser, base, tab, audience, steps) {
  const page = await browser.newPage({ viewport: { width: 1512, height: 1100 } });
  const pageErrors = [];
  page.on("pageerror", (e) => pageErrors.push(String(e)));
  await page.route("**/api/entity/**", async (route) => {
    const url = new URL(route.request().url());
    const which = url.pathname.split("/").pop();
    const aud = url.searchParams.get("audience") || audience;
    if (which === "subcaps") {
      await route.fulfill({ status: 200, contentType: "application/json",
                            body: JSON.stringify({ rows: SUBCAPS, subcaps: SUBCAPS }) });
      return;
    }
    const body = payloadFor(which, aud);
    await route.fulfill({ status: 200, contentType: "application/json",
                          body: JSON.stringify(body) });
  });
  await page.goto(`${base}/#/clients/${ENTITY}/${tab}`, { waitUntil: "domcontentloaded" });
  await settle(page);
  for (const s of steps || []) {
    await page.evaluate((needle) => {
      const want = String(needle).toLowerCase();
      const hits = [...document.querySelectorAll("button, [role=button], summary")]
        .filter((n) => ((n.textContent || "") + " " +
                        (n.getAttribute("aria-label") || "")).toLowerCase().includes(want));
      hits.slice(0, 1).forEach((n) => n.click());
    }, s);
    await settle(page);
  }
  const text = await page.evaluate(() => document.body.innerText || "");
  const titles = await page.evaluate(() =>
    [...document.querySelectorAll("[title]")].map((n) => n.getAttribute("title") || ""));
  // The tile row on its own. A page-wide count of "1 rec" also catches the
  // roadmap chevrons, which legitimately count the recommendations in a
  // phase — so the tile assertion reads the tiles.
  const tiles = await page.evaluate(() =>
    [...document.querySelectorAll(".card-tile.clickable")].map((n) => n.innerText || ""));
  return { page, text, titles, tiles, pageErrors };
}

for (const AUDIENCE of ["internal", "customer"]) {
  test(`D4 platform · the reader never meets the producer's plumbing (${AUDIENCE})`,
       { skip, concurrency: false }, async (t) => {
    const { server, base } = await startServer(BOOT);
    const browser = await pw.chromium.launch({ executablePath: CHROME,
                                               args: ["--no-sandbox"] });
    try {
      const { page, text, titles, tiles, pageErrors } =
        await openRoute(browser, base, "platform", AUDIENCE);

      await t.test("P-05 · no vote count survives into a human label", () => {
        assert.ok(!/\(count:\s*\d+\)/.test(text),
          `the producer's tally reached the page:\n${
            (text.match(/.*\(count:[^\n]*/g) || []).slice(0, 4).join("\n")}`);
        const leaky = titles.filter((x) => /\(count:\s*\d+\)/.test(x));
        assert.deepStrictEqual(leaky, [],
          `the tally reached a tooltip: ${JSON.stringify(leaky.slice(0, 3))}`);
        // and the label itself still renders — stripping must not blank it
        assert.ok(text.includes(AREA_HUMAN),
          "the area label vanished with its tally; the strip took the label too");
        // P-05b · and the catalogue code does not reach the reader. This is
        // the half that was missing: the assertion above passed for a year
        // while `[L3-SF-DC-CORE]` sat in front of every one of these labels.
        const codes = text.match(/\[L3-[A-Za-z0-9._-]+\]/g) || [];
        assert.deepStrictEqual(codes, [],
          `a raw catalogue code reached the page: ${JSON.stringify(codes.slice(0, 4))}`);
        const codedTitles = titles.filter((x) => /\[L3-/.test(x));
        assert.deepStrictEqual(codedTitles, [],
          `a raw catalogue code reached a tooltip: ${JSON.stringify(codedTitles.slice(0, 3))}`);
      });

      await t.test("P-06 · a tile counts the recommendations that name it", () => {
        // Both tiles' areas carry exactly one promoted recommendation. Before
        // the fix the tallied one read "0 recs" over REC-1.
        assert.strictEqual(tiles.length, 2,
          `expected the two promoted tiles, saw ${tiles.length}`);
        for (const tile of tiles) {
          assert.ok(/\b1 rec\b/.test(tile) && !/\b0 recs?\b/.test(tile),
            `a tile reported no recommendation over one that names its area:\n${tile}`);
        }
      });

      await t.test("P-06 · the orphan footer is not asserted against the truth", () => {
        // "sit"/"sits" — the line pluralises, so match the half that does not.
        assert.ok(!text.includes("in an area no promoted platform addresses"),
          "the page told the reader its recommendations reach no platform, " +
          "over two tiles that each lead one");
      });

      await t.test("P-01 · a serialised finding renders as its own sentence", () => {
        assert.ok(!text.includes('{"f_id"') && !text.includes('"e_ids"'),
          `raw JSON on the ladder:\n${
            (text.match(/.*\{"[a-z_]+"[^\n]*/g) || []).slice(0, 2).join("\n")}`);
        assert.ok(text.includes(BLOCKING_TITLE),
          "the finding's title was dropped along with its punctuation — the " +
          "guard must yield the human field, not silence");
        assert.ok(text.includes("F-77"),
          "the finding's id is the reader's handle on it and must render as a chip");
      });

      await t.test("R3-02 · the discards render HERE, and only here", async () => {
        /* Owner's third round: "Considered and set aside" was on the
           Overview, which is the wrong page — it is a platform argument. It
           was also told twice, because `platform_story.discarded` carries the
           same list with its own wording and rendered inside a drawer. It now
           renders openly on this page and nowhere else. */
        assert.ok(text.includes("Considered and set aside"),
          "the platforms considered and not ranked do not render on the "
          + "Platform page, which is where they belong");
        assert.ok(text.includes("Tableau is the reporting layer"),
          "a discard rendered without the reason it was discarded for");

        const overview = await openRoute(browser, base, "overview", AUDIENCE);
        assert.ok(!overview.text.includes("Considered and set aside"),
          "the discards are still on the Overview as well — the same analysis "
          + "told twice, and the copy a reader meets first is on the wrong page");
        await overview.page.close();
      });

      await t.test("R3-03 · no evidence id reaches client prose", () => {
        /* Measured live: "…alongside a credit union data warehouse
           (E-CC-285, E-CC-204), so visualisation is…". E-CC-285 is our
           internal handle for a row in our own evidence index.

           Bracketed groups only — a bare inline id is a payload defect,
           because removing one mid-sentence ("named in E-CC-197 and
           corroborated" → "named in and corroborated") is worse than leaving
           it, and a renderer cannot rewrite a sentence. */
        assert.ok(!/\((?:\s*E-[A-Z]{0,4}-?\d+\s*[,;]?)+\)/.test(text),
          `a bracketed evidence citation reached the page:\n${
            (text.match(/[^\n]*\(E-[^\n]*/g) || []).slice(0, 2).join("\n")}`);
        assert.ok(text.includes("credit union data warehouse, so visualisation"),
          "the sentence did not survive having its citation removed");
      });

      await t.test("R3-04 · no card title is clipped", async () => {
        /* The live app showed "Readiness · MLflow (Databricks-…". A card
           title is the one string on a card that must survive: a reader who
           cannot tell WHICH platform the gates below belong to cannot use
           them.

           Measured from geometry rather than from text, because a CSS clamp
           leaves the full string in the DOM and only the pixels say it is
           cut. */
        const clipped = await page.evaluate(() => {
          const out = [];
          for (const el of document.querySelectorAll("h1, h2, h3, .card-head div, [class*=txt-fit]")) {
            const t = (el.textContent || "").trim();
            if (!t || el.children.length > 2) continue;
            if (el.scrollHeight > el.clientHeight + 2
                || el.scrollWidth > el.clientWidth + 2) {
              out.push(t.slice(0, 80));
            }
          }
          return out;
        });
        assert.deepStrictEqual(clipped, [],
          `card titles are cut off:\n  ${clipped.join("\n  ")}`);
      });

      assert.deepStrictEqual(pageErrors.filter((e) => !/ResizeObserver/.test(e)), []);
      await page.close();
    } finally {
      await browser.close();
      await new Promise((r) => server.close(r));
    }
  });

  test(`T1 tech stack · a catalogue code is not a capability name (${AUDIENCE})`,
       { skip, concurrency: false }, async (t) => {
    const { server, base } = await startServer(BOOT);
    const browser = await pw.chromium.launch({ executablePath: CHROME,
                                               args: ["--no-sandbox"] });
    try {
      const reg = await openRoute(browser, base, "techstack", AUDIENCE);

      await t.test("T-05 · the register names the cells it links", () => {
        for (const nm of ["Application Portfolio Management",
                          "Legacy Modernization Strategy",
                          "Product Propensity Modeling"]) {
          assert.ok(reg.text.includes(nm),
            `the register printed a bare code where "${nm}" belongs:\n${
              reg.text.slice(0, 600)}`);
        }
        // The code stays beside the name: every other surface is keyed on it.
        assert.ok(reg.text.includes("P4C3.2.1"),
          "the catalogue id was dropped; a reader following the row needs both");
      });
      assert.deepStrictEqual(reg.pageErrors.filter((e) => !/ResizeObserver/.test(e)), []);
      await reg.page.close();

      const det = await openRoute(browser, base, "techstack", AUDIENCE,
                                  ["Symitar Episys"]);
      await t.test("the detail sub-page keeps its names and counts one item once", () => {
        assert.ok(det.text.includes("Cells this product is linked to"),
          `the register row did not open its detail sub-page:\n${det.text.slice(0, 400)}`);
        assert.ok(det.text.includes("Application Portfolio Management"),
          "the sub-page lost the capability name");
        assert.ok(!/\b1 items\b/.test(det.text),
          "a singular count took a plural noun on the detail sub-page");
      });
      assert.deepStrictEqual(det.pageErrors.filter((e) => !/ResizeObserver/.test(e)), []);
      await det.page.close();
    } finally {
      await browser.close();
      await new Promise((r) => server.close(r));
    }
  });
}
