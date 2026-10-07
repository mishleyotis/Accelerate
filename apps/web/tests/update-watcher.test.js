/* A release while the page is open (owner, 2026-10-07: the client heatmap
 * still greyed out after the fix shipped, because the tab predated the
 * release). The page compares the build it booted on with /api/version and,
 * when they differ, says so and reloads on the next tab change. */
const { test } = require("node:test");
const assert = require("node:assert");
const { resolvePlaywright, startServer, settle, resolveChromium, browserSkip } =
  require("./proto-page-harness");

const skip = browserSkip();
const BOOT = { authed: true, role: "AE", email: "ae@zennify.com", name: "QA", entities: [],
               active_runs: [], pending_review: [], subvertical_labels: {}, build: "build-A" };

async function open(browser, base, boot, serverBuild) {
  const page = await (await browser.newContext()).newPage();
  const asked = [];
  await page.route("**/api/version", (r) => { asked.push(1); r.fulfill({ status: 200,
    contentType: "application/json", body: JSON.stringify({ build: serverBuild }) }); });
  await page.route("**/api/usage", (r) => r.fulfill({ status: 204, body: "" }));
  await page.goto(`${base}/#/clients`, { waitUntil: "domcontentloaded" });
  await settle(page);
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await page.waitForTimeout(400);
  return { page, asked };
}

test("same build: no banner; a new build: banner, and the next tab change reloads", { skip }, async () => {
  const pw = resolvePlaywright();
  const browser = await pw.chromium.launch({ executablePath: resolveChromium(), args: ["--no-sandbox"] });
  const { server, base } = await startServer(BOOT);
  try {
    const same = await open(browser, base, BOOT, "build-A");
    assert.ok(same.asked.length >= 1, "the page never asked which build is live");
    assert.strictEqual(await same.page.locator("[data-update-banner]").count(), 0, "banner on an unchanged build");

    const { page } = await open(browser, base, BOOT, "build-B");
    await page.locator("[data-update-banner]").waitFor();
    assert.match(await page.locator("[data-update-banner]").innerText(), /has been updated[\s\S]*Reload/);
    let loads = 0;
    page.on("load", () => { loads++; });
    await page.evaluate(() => { location.hash = "/prospecting"; });
    await page.waitForLoadState("load");
    await page.waitForTimeout(300);
    assert.strictEqual(loads, 1, "the next tab change did not reload onto the new build");
    assert.match(page.url(), /#\/prospecting$/, "the reload lost the address");
  } finally { await browser.close(); server.close(); }
});

test("a public client link never asks: that service has no /api", { skip }, async () => {
  const pw = resolvePlaywright();
  const browser = await pw.chromium.launch({ executablePath: resolveChromium(), args: ["--no-sandbox"] });
  const { server, base } = await startServer({ ...BOOT, api_base: "/s/tok/api",
    share: { entity: "x", expires_at: "2026-11-01T00:00:00Z" } });
  try {
    const { asked } = await open(browser, base, BOOT, "build-B");
    assert.strictEqual(asked.length, 0);
  } finally { await browser.close(); server.close(); }
});
