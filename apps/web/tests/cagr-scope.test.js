/* O2/O8 · a growth rate is never computed over a hold, or from a subsidiary.
 *
 * RC-11 / D-05, gold audit of run 7968492e (2026-10-04). The producer HELD
 * enterprise `cagr` in firmographics — quarantined, with the reason: no group
 * revenue or asset series is published. The financial series it promoted is
 * one SUBSIDIARY's loan originations, every point's `basis` saying "a
 * subsidiary of the group, not the group". `cagrOf` ignored both, computed a
 * compound rate over the subsidiary's four points, and app-root let the
 * computed value win ("computed wins"), so the firmographics strip printed
 * "CAGR -6.8% · 2022–2025" as the firm's growth with no scope label. The
 * adapter also called the series `total_assets` — it was never assets.
 *
 * Owner decision 2 (2026-10-04): a held firmographic RENDERS as a stated
 * absence with its reason — it never disappears. That retires the 2026-08-14 /
 * 08-19 "remove the row" adjudications for held fields (a blank field with no
 * reason still renders no row).
 *
 * `npm run build:proto` first: these read the compiled bundle.
 */
const { test } = require("node:test");
const assert = require("node:assert");

const H = require("./ssr-harness");
const F = require("./fixtures/gold-audit-shape");
const { resolvePlaywright, startServer, settle, selectAudience,
        resolveChromium, browserSkip } = require("./proto-page-harness");

test("D-05 adapter · a held enterprise cagr is never overridden by the series", () => {
  const { win } = H.load();
  const f = win.adaptFinancials(F.FINANCIAL_SERIES, F.FIRMOGRAPHICS, null);
  assert.ok(f, "the series did not adapt at all");
  assert.strictEqual(f.cagr, undefined,
    `a CAGR of ${f.cagr} was computed over a producer HOLD on cagr`);
});

test("D-05 adapter · a subsidiary series yields no enterprise CAGR, hold or no hold", () => {
  const { win } = H.load();
  const noHold = { ...F.FIRMOGRAPHICS,
    fields: F.FIRMOGRAPHICS.fields.filter((x) => x.field !== "cagr") };
  const f = win.adaptFinancials(F.FINANCIAL_SERIES, noHold, null);
  assert.strictEqual(f.cagr, undefined,
    "every point's basis names a subsidiary, and a CAGR was still derived as "
    + "the firm's growth");
  assert.strictEqual(win.cagrOf(F.FINANCIAL_SERIES.series).cagr, undefined,
    "cagrOf itself still computes over a subsidiary-scoped series");
});

test("D-05 adapter · a group series with no hold still computes, with its basis", () => {
  const { win } = H.load();
  const series = F.FINANCIAL_SERIES.series.map((p) => ({ ...p, basis: "Total assets, consolidated" }));
  const f = win.adaptFinancials({ ...F.FINANCIAL_SERIES, series }, { fields: [] }, null);
  assert.ok(f.cagr != null && isFinite(f.cagr), "a legitimate group series lost its CAGR");
  assert.match(f.cagr_basis, /2022–2025/);
});

test("D-05 adapter · the series is called what it is", () => {
  const { win } = H.load();
  const f = win.adaptFinancials(F.FINANCIAL_SERIES, F.FIRMOGRAPHICS, null);
  assert.ok(Array.isArray(f.series_values) && f.series_values.length === 4,
    "series_values is missing");
  assert.ok(!("total_assets" in f),
    "the adapter still labels a loan-origination series `total_assets`");
});

/* ── the strip, rendered ──────────────────────────────────────────────── */

const pw = resolvePlaywright();
const CHROME = resolveChromium();
const skip = browserSkip();
const ENTITY = "gold-audit-shape";
const RUN_ID = "DMA-ASM-EXMP-20261002-0001";
const BOOT = {
  authed: true, role: "ADMIN", email: "dma@zennify.com", name: "QA",
  catalogue_version: "v7.0", dev_login: true,
  subvertical_labels: { INSURANCE_BROKERAGE: "Insurance brokerage" },
  entities: [{
    id: ENTITY, slug: ENTITY, name: "Example Group",
    subvertical: "INSURANCE_BROKERAGE", size_tier: "LARGE", hq: "Riverton, EX",
    status: "ACTIVE", data_source: "PROJECT_API", assessment_date: "2026-10-02",
    overall: 2.0, pillar_scores: {}, oss: {}, footprint: [], runs: [
      { id: RUN_ID, date: "2026-10-02", status: "ACTIVE", overall: 2.0,
        evidence_mode: "HYBRID", subcap_count: 851 },
    ],
  }],
  active_runs: [], pending_review: [],
};

async function overviewText(audience) {
  const { server, base } = await startServer(BOOT);
  const browser = await pw.chromium.launch({ executablePath: CHROME, args: ["--no-sandbox"] });
  try {
    const page = await browser.newPage({ viewport: { width: 1512, height: 1100 } });
    await page.route("**/api/entity/**", async (route) => {
      const which = new URL(route.request().url()).pathname.split("/").pop();
      if (which !== "overview") {
        return route.fulfill({ status: 404, contentType: "application/json", body: '{"error":"not_found"}' });
      }
      const body = { entity: { display_id: ENTITY, name: "Example Group" },
        run: { run_id: RUN_ID, promoted_at: "2026-10-02T00:00:00Z",
               completed_at: "2026-10-02T00:00:00Z", evidence_mode: "HYBRID" },
        audience, sections: {
          firmographics: F.sec(F.FIRMOGRAPHICS),
          financial_series: F.sec(F.FINANCIAL_SERIES),
        } };
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    });
    await page.goto(`${base}/#/clients/${ENTITY}/overview`, { waitUntil: "domcontentloaded" });
    await settle(page);
    await selectAudience(page, audience);
    return await page.evaluate(() => {
      const eb = [...document.querySelectorAll(".eyebrow")].find((n) => /Firmographics/.test(n.textContent || ""));
      return { strip: eb ? (eb.parentElement.innerText || "") : null,
               body: document.body.innerText || "" };
    });
  } finally { await browser.close(); server.close(); }
}

test("D-05 render · the strip prints no subsidiary CAGR as the firm's growth", { skip }, async () => {
  for (const audience of ["internal", "customer"]) {
    const { strip, body } = await overviewText(audience);
    assert.ok(strip, `no firmographics strip on the ${audience} overview`);
    assert.ok(!/CAGR\s*-?\d/.test(strip),
      `the ${audience} strip printed a computed CAGR over a hold: ${strip.replace(/\s+/g, " ")}`);
    // The fixture series' own compound rate (1.9 -> 1.7 over three years is
    // -3.6%): the figure the old code printed as the firm's growth.
    assert.ok(!/-3\.\d%/.test(body), `a subsidiary-derived growth rate rendered on the ${audience} page`);
  }
});

test("decision 2 render · every held field renders as a stated absence with its reason", { skip }, async () => {
  const { strip } = await overviewText("internal");
  const flat = strip.replace(/\s+/g, " ");
  for (const f of F.FIRMOGRAPHICS.fields.filter((x) => x.quarantined)) {
    assert.ok(flat.includes(f.quarantine_reason),
      `held field "${f.field}" disappeared from the strip — a held field `
      + `renders its reason, it never vanishes (owner decision 2)`);
  }
  assert.match(flat, /CAGR/, "the held CAGR row is not labelled");
  // The stated figures are still there.
  assert.match(flat, /1,850/, "the stated employee count vanished");
  assert.match(flat, /1983/, "the stated founding year vanished");
});
