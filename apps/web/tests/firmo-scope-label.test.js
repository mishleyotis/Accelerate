/* Decision 2 · a firmographic's scope label is the producer's own words,
 * and only when the unit names a scope.
 *
 * Found rendering the staged sections of the gold-audit run (2026-10-04)
 * through the real customer projection. The strip's scope label was
 * "everything after the unit's first comma". On a registry answer whose unit
 * is "deposit-taking branches; <subsidiary> runs local mortgage branch
 * offices, whose count <the group> does not publish …", the row printed
 *
 *     Branches  None (non-depository) · whose count … does not publish …
 *
 * It dropped the clause that says what the figure is about and kept a
 * dangling relative clause. That reads as if "None" were an unpublished
 * count. A unit like "USD, thousands" would print "· thousands" as though it
 * named an entity. The label now starts at the first clause break (comma or
 * semicolon), and a bare magnitude word is not a scope.
 *
 * Also the round-1 review's silent-CAGR case: a `cagr` firmographic that is
 * neither stated (value null) nor held (not quarantined) suppressed the
 * computed rate, and no absence row replaced it.
 *
 * `npm run build:proto` first: these read the compiled bundle.
 */
const { test } = require("node:test");
const assert = require("node:assert");

const H = require("./ssr-harness");
const F = require("./fixtures/gold-audit-shape");
const { resolvePlaywright, startServer, settle, selectAudience,
        resolveChromium, browserSkip } = require("./proto-page-harness");

const BRANCH_UNIT = "deposit-taking branches; Example Mortgage Corporation "
  + "runs local branch offices, whose count the group does not publish";

test("unitScope · the scope starts at the first clause break", () => {
  const { win } = H.load();
  assert.strictEqual(typeof win.unitScope, "function",
    "no shared scope reader: the strip derives its label inline");
  assert.strictEqual(win.unitScope(BRANCH_UNIT),
    "Example Mortgage Corporation runs local branch offices, whose count "
    + "the group does not publish");
  assert.strictEqual(
    win.unitScope("USD billions, Example Mortgage Corporation, HMDA 2024"),
    "Example Mortgage Corporation, HMDA 2024");
});

test("unitScope · a measure alone, or a magnitude after a comma, is no scope", () => {
  const { win } = H.load();
  for (const u of ["employees", "USD, thousands", "USD, in millions",
                   "USD; billions", "", null, undefined, "count,"]) {
    assert.strictEqual(win.unitScope(u), null, `"${u}" was read as a scope`);
  }
});

test("CAGR · a cagr key that is neither stated nor held does not silence the series", () => {
  const { win } = H.load();
  const series = F.FINANCIAL_SERIES.series.map((p) => ({ ...p,
    basis: "Total assets, consolidated" }));
  const firm = { fields: [{ field: "cagr", value: null, unit: "percent a year",
                            quarantined: false, quarantine_reason: null }] };
  const f = win.adaptFinancials({ ...F.FINANCIAL_SERIES, series }, firm, null);
  assert.ok(f.cagr != null && isFinite(f.cagr),
    "an empty, unheld cagr field suppressed the computed rate with no row "
    + "in its place");
  // …while a held one, and a stated one, still win.
  const heldF = { fields: [{ field: "cagr", value: null, quarantined: true,
                             quarantine_reason: "No group series." }] };
  assert.strictEqual(win.adaptFinancials({ ...F.FINANCIAL_SERIES, series },
    heldF, null).cagr, undefined);
  const stated = { fields: [{ field: "cagr", value: 4.2, quarantined: false }] };
  assert.strictEqual(win.adaptFinancials({ ...F.FINANCIAL_SERIES, series },
    stated, null).cagr, undefined);
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

const FIRMO = { ...F.FIRMOGRAPHICS, fields: F.FIRMOGRAPHICS.fields
  .filter((x) => x.field !== "branches")
  .concat([{ field: "branches", value: "None (non-depository)", unit: BRANCH_UNIT,
             as_of: null, confidence: "HIGH", quarantined: false,
             source_e_id: "E-CC-9200", recency_band: "UNVERIFIED",
             quarantine_reason: null }]) };

async function stripText(audience) {
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
        audience, sections: { firmographics: F.sec(FIRMO),
                              financial_series: F.sec(F.FINANCIAL_SERIES) } };
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    });
    await page.goto(`${base}/#/clients/${ENTITY}/overview`, { waitUntil: "domcontentloaded" });
    await settle(page);
    await selectAudience(page, audience);
    return await page.evaluate(() => {
      const eb = [...document.querySelectorAll(".eyebrow")].find((n) => /Firmographics/.test(n.textContent || ""));
      return eb ? (eb.parentElement.innerText || "") : null;
    });
  } finally { await browser.close(); server.close(); }
}

test("decision 2 render · a registry answer keeps the clause that scopes it", { skip }, async () => {
  for (const audience of ["internal", "customer"]) {
    const strip = await stripText(audience);
    assert.ok(strip, `no firmographics strip on the ${audience} overview`);
    const flat = strip.replace(/\s+/g, " ");
    assert.ok(flat.includes("None (non-depository)"), `the stated branch answer vanished: ${flat}`);
    assert.ok(flat.includes("Example Mortgage Corporation runs local branch offices"),
      `the ${audience} strip dropped the clause naming what the figure is about: ${flat}`);
    assert.ok(!/None \(non-depository\) · whose count/.test(flat),
      `the ${audience} strip printed a dangling relative clause as the scope`);
  }
});
