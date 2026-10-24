/* The value chain in the CLIENT view (owner, 2026-10-07): it rendered "did
 * not promote" for clients while the internal view drew every stage (the
 * server allowlist dropped the server-derived keys — apps/api tests pin
 * that half), and "most value chain subcaps are not clickable": the stage
 * tile's cell swatches had no handler, so a click only toggled the stage.
 * Here the client view draws the stages and every swatch opens its cell. */
const { test } = require("node:test");
const assert = require("node:assert");
const { resolvePlaywright, startServer, settle, selectAudience,
        resolveChromium, browserSkip } = require("./proto-page-harness");

const skip = browserSkip();
const ID = "test-credit-union";
const RUN = { id: "DMA-ASM-TCU-20260801-0001", run_id: "run-1", date: "2026-08-01", status: "ACTIVE" };
const BOOT = {
  authed: true, role: "AE", email: "ae@zennify.com", name: "QA", catalogue_version: "v7.0",
  subvertical_labels: {}, active_runs: [], pending_review: [],
  entities: [{ id: ID, slug: ID, name: "Test Credit Union", subvertical: "CREDIT_UNION",
               status: "ACTIVE", runs: [RUN], pillar_scores: {} }],
};
const ENV = { produced_at: "2026-08-01T00:00:00Z", producer_version: "t", e_ids: [], internal_only: [] };
const CELLS = ["P1C1.1.1", "P1C1.1.2", "P2C2.1.1"];
const PAGES = {
  heatmap: { sections: { value_chain: { ...ENV, data: { narrative_thread: "By stage.",
    chains: [{ stage_id: "VC-CU-01", id: "VC-CU-01", name: "Field of membership", stage_order: 1,
               subcaps: ["P1C1.1.1", "P1C1.1.2"], not_scored: 0 },
             { stage_id: "VC-CU-02", id: "VC-CU-02", name: "Onboarding", stage_order: 2,
               subcaps: ["P2C2.1.1"], not_scored: 0 }],
    not_scored_cells: 0, sub_vertical: "CU", version: "v7.0", arrangement_version: "v7.0",
    not_applicable_stages: 0 } } } },
  subcaps: { subcaps: CELLS.map((s, i) => ({ subcap_id: s, subcap_name: `Cell ${s}`, pillar_id: s.slice(0, 2),
             category_id: s.slice(0, 4), capability_id: s.slice(0, 6), score: 1.5 + i * 0.5 })) },
};

test("client view: the value chain draws its stages, and every cell swatch opens that cell", { skip }, async () => {
  const pw = resolvePlaywright();
  const browser = await pw.chromium.launch({ executablePath: resolveChromium(), args: ["--no-sandbox"] });
  const { server, base } = await startServer(BOOT);
  try {
    const page = await (await browser.newContext({ viewport: { width: 1400, height: 1000 } })).newPage();
    const errors = []; page.on("pageerror", (e) => errors.push(String(e.message)));
    await page.route("**/api/usage", (r) => r.fulfill({ status: 204, body: "" }));
    await page.route("**/api/entity/**", (r) => {
      const which = new URL(r.request().url()).pathname.split("/").pop();
      const body = PAGES[which] || { sections: {} };
      r.fulfill({ status: 200, contentType: "application/json",
                  body: JSON.stringify({ entity: { display_id: ID, entity_name: "Test Credit Union" },
                                         run: { run_id: RUN.run_id, request_id: RUN.id }, ...body }) });
    });
    await page.goto(`${base}/#/clients/${ID}/heatmap`, { waitUntil: "domcontentloaded" });
    await settle(page);
    await selectAudience(page, "customer");
    await settle(page);
    // The standard grid is the client's landing view and is not greyed out.
    const std = page.locator(".toggle-row button", { hasText: "Standard" });
    assert.strictEqual(await std.isDisabled(), false, "Standard is greyed out for the client");
    assert.match(await std.getAttribute("class") || "", /\bon\b/, "the client heatmap did not open on Standard");

    await page.locator(".toggle-row button", { hasText: "Value chain" }).click();
    await settle(page);
    const text = await page.evaluate(() => document.body.innerText);
    assert.ok(!/did not promote/i.test(text), "the client value chain says it did not promote");
    assert.match(text, /Field of membership/);
    assert.match(text, /Onboarding/);

    // A swatch in the stage strip opens THAT cell, without toggling the stage.
    const swatch = page.locator('[aria-label="Open P1C1.1.2"]');
    assert.strictEqual(await swatch.count(), 1, "the swatch is not an openable control");
    await swatch.click();
    await settle(page);
    const after = await page.evaluate(() => document.body.innerText);
    assert.match(after, /Cell P1C1\.1\.2/, "clicking a swatch did not open its cell");
    assert.ok(!/Field of membership · subcaps/.test(after), "the click fell through and toggled the stage");
    assert.deepStrictEqual(errors, []);
  } finally { await browser.close(); server.close(); }
});
