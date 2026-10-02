/* The landing page survives a directory row with no legal name.
 *
 * /v1/directory passes `serving_directory.legal_name` through as-is and
 * never invents one (invariant 9), so `name: null` is a live shape. The
 * dashboard's client card built its avatar with `e.name.split(" ")`, and on
 * sign-in the whole page unmounted with "Cannot read properties of null
 * (reading 'split')". Same class at the leadership roster (`ex.name`) and the
 * context timeline axis (`e.title`); `initialsOf` is the one guard.
 *
 * Run with `npm run test:web`; serves the COMPILED bundle via the shared
 * harness, exactly as app/route.js does.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { resolvePlaywright, startServer, settle,
        resolveChromium, browserSkip } = require("./proto-page-harness");

const entity = (id, name) => ({
  id, slug: id, name, subvertical: "CREDIT_UNION", size_tier: "MEDIUM",
  hq: null, status: "ACTIVE", data_source: "DRIVE_PARSE",
  assessment_date: "2026-08-01", overall: 2.9, open_alerts: 0,
  runs: [{ id: `RUN-${id}`, date: "2026-08-01", status: "ACTIVE", overall: 2.9 }],
});

const BOOT = {
  authed: true, role: "ADMIN", email: "dma@zennify.com", name: "QA",
  catalogue_version: "v7.0", dev_login: true,
  subvertical_labels: { CREDIT_UNION: "Credit union" },
  entities: [entity("named-cu", "Named Credit Union"), entity("unnamed-cu", null)],
  active_runs: [], pending_review: [],
};

const pw = resolvePlaywright();
const CHROME = resolveChromium();
const skip = browserSkip();

test("dashboard renders when a directory row has a null name",
     { skip, concurrency: false }, async () => {
  const { server, base } = await startServer(BOOT);
  const browser = await pw.chromium.launch({ executablePath: CHROME,
                                             args: ["--no-sandbox"] });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const pageErrors = [];
    page.on("pageerror", (e) => pageErrors.push(String(e)));
    await page.goto(`${base}/`, { waitUntil: "domcontentloaded" });
    await settle(page);

    const text = await page.evaluate(() => document.body.innerText || "");
    assert.ok(!/could not be rendered/i.test(text),
              "the landing page fell to the page boundary");
    assert.ok(text.includes("Named Credit Union"), "the named client card is missing");
    assert.ok(text.includes("unnamed-cu"),
              "a null-named client must still show its display id");
    assert.deepStrictEqual(pageErrors.filter((e) => /split/.test(e)), []);

    const cases = await page.evaluate(() => [
      initialsOf(null), initialsOf(undefined), initialsOf(""), initialsOf("  "),
      initialsOf({ first: "B" }), initialsOf("Named Credit Union"), initialsOf("Solo"),
    ]);
    assert.deepStrictEqual(cases, ["?", "?", "?", "?", "?", "NC", "S"]);
  } finally {
    await browser.close();
    server.close();
  }
});
