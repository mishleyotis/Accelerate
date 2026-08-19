/* The Context issue register's cap list, in every shape a producer writes it.
 *
 * Reported 2026-08-18 from a promoted client's rendered page: the issue
 * drilldown printed "[object Object]" three times — as the cell chip, as the
 * cell name, and inside "Open [object Object] in the heatmap".
 *
 * The cause is a shape the adapter never learned. `capped_subcap_ids` is
 * `[{subcap_id, cap_level}]`, which is what the producer prompt asks for in
 * as many words (03-pages/5-context.md: "the level -> the cap_level on those
 * ids"). The adapter handled two other shapes — a bare list of ids, and a
 * {id: level} map — and used the record itself as an object key for the
 * third, which JavaScript coerces to "[object Object]".
 *
 * The display bug is the smaller half. The cell resolver then looked
 * "[object Object]" up in the served set, missed, and printed "Not carried by
 * this run" under a cell the run carries and caps at M3. A cosmetic failure
 * produced a false statement about the assessment, which is why this is
 * pinned in the DOM rather than as a unit test on the adapter.
 *
 * Run with `npm run test:web`.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");

const { resolvePlaywright, startServer, settle, selectAudience,
        assertNoStringifiedObjects,
        resolveChromium, browserSkip } = require("./proto-page-harness");

const ENTITY = "test-credit-union";
const RUN_ID = "DMA-ASM-TCU-20260801-0001";
const CAPPED_CELL = "P3C3.1.1";

const pw = resolvePlaywright();
const CHROME = resolveChromium();
const skip = browserSkip();

const BOOT = {
  authed: true, role: "ADMIN", email: "dma@zennify.com", name: "QA",
  catalogue_version: "v7.0", dev_login: true,
  subvertical_labels: { CREDIT_UNION: "Credit union" },
  entities: [{
    id: ENTITY, slug: ENTITY, name: "Test Credit Union",
    subvertical: "CREDIT_UNION", size_tier: "MEDIUM", hq: "Chicago, IL",
    status: "ACTIVE", data_source: "PROJECT_API", assessment_date: "2026-08-01",
    overall: 2.9, pillar_scores: {}, oss: {}, footprint: ["IL"], runs: [
      { id: RUN_ID, date: "2026-08-01", status: "ACTIVE", overall: 2.9,
        evidence_mode: "PUBLIC", subcap_count: 705 },
    ],
  }],
  active_runs: [], pending_review: [],
};

/* The three shapes, named by what a producer would have been reading when it
   wrote each one. All three must render the same cell. */
const SHAPES = {
  "objects with a level (what the prompt asks for)":
    [{ subcap_id: CAPPED_CELL, cap_level: "M3" }],
  "objects with a numeric level":
    [{ subcap_id: CAPPED_CELL, cap_level: 3 }],
  "a bare list of ids (level lives on the run's caps[])":
    [CAPPED_CELL],
  "an id-to-level map":
    { [CAPPED_CELL]: 3 },
};

function contextPage(capped) {
  const env = {
    produced_at: "2026-08-01T00:00:00Z", producer_version: "test",
    e_ids: ["E-CC-188"], internal_only: [],
    narrative_thread: "The line through this page, written last from what was produced.",
  };
  return {
    sections: {
      issue_register: { data: { ...env, verified_absent: false, issues: [{
        issue_id: "IR-001",
        title: "Bureau supervision on crossing ten billion, costed in advance",
        severity: "HIGH", status: "OPEN", opened_on: "2025-03-26",
        resolved_on: null, provenance: "analyst",
        rationale: "The institution states five years of preparation and a "
          + "staffing step of at least thirty people, and its own chief "
          + "executive describes the cost as diverting funds from member "
          + "programmes.",
        capped_subcap_ids: capped,
        linked_subcap_ids: [CAPPED_CELL, "P1C2.7.1"],
        e_ids: ["E-CC-188"],
      }] } },
      timeline: { data: { ...env, events: [], arc_shape: null, storyline: null,
                          verified_sparse: true } },
      acquisitions: { data: { ...env, rows: [], empty_state: {
        reason: "No acquisition, merger or charter change appears in the "
          + "regulator's record for this institution.",
        sources_searched: ["regulator merger register", "trade press"] } } },
      context_sentiment: { data: { ...env, context_tiles: [] } },
      regulatory_standing: { data: { ...env, primary_regulator: "NCUA",
        license_type: "Federal credit union", charter_date: "1937-01-01",
        jurisdictions: ["US"], additional_regulators: [],
        enforcement_actions: [], absence_of_enforcement: null } },
    },
  };
}

async function renderContext(capped) {
  const { server, base } = await startServer(BOOT);
  const browser = await pw.chromium.launch({ executablePath: CHROME, args: ["--no-sandbox"] });
  try {
    const page = await browser.newPage({ viewport: { width: 1512, height: 1400 } });
    await page.route("**/api/entity/**", async (route) => {
      const which = new URL(route.request().url()).pathname.split("/").pop().split("?")[0];
      const body = which === "context" ? contextPage(capped) : { sections: {} };
      return route.fulfill({ status: 200, contentType: "application/json",
                             body: JSON.stringify(body) });
    });
    await page.goto(`${base}/#/clients/${ENTITY}/context`, { waitUntil: "domcontentloaded" });
    await settle(page);
    await selectAudience(page, "internal");
    // The chips live in the matter's drilldown, which is where the reported
    // failure was seen — the register list alone never showed it.
    await page.evaluate((title) => {
      const hit = [...document.querySelectorAll("button, [role=button], a, tr, li, div")]
        .filter((n) => (n.textContent || "").includes(title))
        .sort((a, b) => (a.textContent || "").length - (b.textContent || "").length)[0];
      if (hit) hit.click();
    }, "Bureau supervision on crossing ten billion");
    await settle(page);
    return { page, browser, server };
  } catch (e) {
    await browser.close(); server.close(); throw e;
  }
}

for (const [name, capped] of Object.entries(SHAPES)) {
  test(`context caps · ${name} · no record reaches a text slot`, { skip }, async () => {
    const { page, browser, server } = await renderContext(capped);
    try {
      await assertNoStringifiedObjects(page, `context with capped_subcap_ids as ${name}`);
    } finally { await browser.close(); server.close(); }
  });

  test(`context caps · ${name} · the capped cell is named`, { skip }, async () => {
    const { page, browser, server } = await renderContext(capped);
    try {
      const text = await page.evaluate(() => document.body.innerText || "");
      assert.ok(text.includes(CAPPED_CELL),
        `the cell this matter caps (${CAPPED_CELL}) is not named anywhere on the `
        + `page when capped_subcap_ids is sent as ${name}. A cap the reader `
        + `cannot resolve to a cell is a padlock over nothing.`);
    } finally { await browser.close(); server.close(); }
  });
}

test("context caps · an unreadable cap is dropped, not printed", { skip }, async () => {
  /* Absent beats wrong. A record with no recognisable id must leave no chip
     rather than a chip the reader cannot act on — the failure this whole
     file exists for was a chip nobody could act on. */
  const { page, browser, server } = await renderContext(
    [{ cap_level: "M3" }, { subcap_id: CAPPED_CELL, cap_level: "M3" }]);
  try {
    await assertNoStringifiedObjects(page, "context with one unreadable cap entry");
    const text = await page.evaluate(() => document.body.innerText || "");
    assert.ok(text.includes(CAPPED_CELL), "the readable cap was dropped too");
  } finally { await browser.close(); server.close(); }
});
