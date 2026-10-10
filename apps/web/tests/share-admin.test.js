/* Admin › Client links: the place an admin takes access back.
 *
 * Owner, 2026-10-07: "The admin page should also have a place where I can
 * revoke access." The rules live server-side (lib/share-ledger, asserted in
 * share-link.test.js); this pins the page: every link listed with who it was
 * shared with and by whom, a recipient removed with one click, a whole link
 * revoked only after a confirm, an unlisted link revoked by pasting it — and
 * each of those sends exactly the request the server expects.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { resolvePlaywright, startServer, settle, resolveChromium, browserSkip } =
  require("./proto-page-harness");

const skip = browserSkip();
const BOOT = {
  authed: true, role: "ADMIN", email: "dma@zennify.com", name: "QA",
  catalogue_version: "v7.0", dev_login: true, subvertical_labels: {},
  entities: [{ id: "baxter-credit-union-bcu", slug: "baxter-credit-union-bcu",
               name: "Baxter Credit Union", subvertical: "CREDIT_UNION", status: "ACTIVE",
               runs: [], pillar_scores: {} }],
  active_runs: [], pending_review: [], import_scans: [],
};
// Everyone lands in the AE view (app-root.jsx _landingRole); an admin
// switches deliberately — Settings → Acting as → Admin — and so does this.
async function openAdmin(page, base) {
  await page.route("**/api/usage", (r) => r.fulfill({ status: 204, body: "" }));
  await page.goto(`${base}/#/`, { waitUntil: "domcontentloaded" });
  await settle(page);
  await page.click('button[aria-label="Settings"]');
  await page.click('.popover .toggle-row button:has-text("Admin")');
  await page.evaluate(() => { location.hash = "/admin"; });
  await settle(page);
}

const LINKS = [
  { jti: "linkActive01", entity: "baxter-credit-union-bcu", run: "r1",
    emails: ["jane@bcu.com"], domains: ["bcu.com"], minted_by: "ae@zennify.com",
    minted_at: "2026-10-07T12:00:00Z", expires_at: "2026-11-06T12:00:00Z",
    revocation: null, status: "active" },
  { jti: "linkRevoked1", entity: "baxter-credit-union-bcu", run: "r1",
    emails: ["cfo@bcu.com"], domains: ["bcu.com"], minted_by: "ae@zennify.com",
    minted_at: "2026-10-06T12:00:00Z", expires_at: "2026-11-05T12:00:00Z",
    revocation: { all: true, emails: [], domains: [], history: [] }, status: "revoked" },
];

test("admin · client links: list, remove a recipient, revoke with a confirm, revoke by paste", { skip }, async () => {
  const pw = resolvePlaywright();
  const browser = await pw.chromium.launch({ executablePath: resolveChromium(), args: ["--no-sandbox"] });
  const { server, base } = await startServer(BOOT);
  try {
    const page = await (await browser.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
    const errors = []; page.on("pageerror", (e) => errors.push(String(e.message)));
    const posts = [];
    await page.route("**/api/admin/share-links", (r) => {
      if (r.request().method() === "POST") {
        posts.push(JSON.parse(r.request().postData()));
        return r.fulfill({ status: 200, contentType: "application/json",
                           body: JSON.stringify({ jti: "x", revocation: {} }) });
      }
      return r.fulfill({ status: 200, contentType: "application/json",
                         body: JSON.stringify({ status: "ok", links: LINKS }) });
    });
    await page.route("**/api/admin/usage**", (r) => r.fulfill({ status: 200, contentType: "application/json",
      body: JSON.stringify({ status: "not_configured" }) }));
    await openAdmin(page, base);
    const card = page.locator('[data-screen-label="Admin · Client links"]');
    await card.waitFor();

    // Active links by default; the revoked one only under "All".
    let text = await card.innerText();
    assert.match(text, /Baxter Credit Union/);
    assert.match(text, /jane@bcu\.com/);
    assert.match(text, /anyone @bcu\.com/);
    assert.match(text, /ae@zennify\.com/, "who shared it is not shown");
    assert.match(text, /Link ID linkActive01/);
    assert.ok(!text.includes("linkRevoked1"), "a revoked link is listed among the active ones");
    await card.getByRole("button", { name: /^All/ }).click();
    text = await card.innerText();
    assert.match(text, /linkRevoked1/);
    assert.match(text, /Revoked/);
    await card.getByRole("button", { name: "Active", exact: true }).click();

    // Remove one recipient: one click, one request.
    await card.getByRole("button", { name: "Remove access for jane@bcu.com" }).click();
    await settle(page);
    assert.deepStrictEqual(posts.shift(), { link: "linkActive01", action: "remove", email: "jane@bcu.com" });
    await card.getByRole("button", { name: "Remove access for bcu.com" }).click();
    await settle(page);
    assert.deepStrictEqual(posts.shift(), { link: "linkActive01", action: "remove", domain: "bcu.com" });

    // Revoking the whole link asks first; Cancel sends nothing.
    await card.getByRole("button", { name: /Revoke link/ }).click();
    await card.getByRole("button", { name: "Cancel" }).click();
    assert.strictEqual(posts.length, 0, "Cancel revoked the link");
    await card.getByRole("button", { name: /Revoke link/ }).click();
    await card.getByRole("button", { name: "Confirm revoke" }).click();
    await settle(page);
    assert.deepStrictEqual(posts.shift(), { link: "linkActive01", action: "revoke" });

    // A link that is not listed: paste it.
    await page.fill("#share-revoke-paste", "https://dmai-share.example/s/abc.def#/clients/x/overview");
    await card.getByRole("button", { name: "Revoke", exact: true }).click();
    await settle(page);
    assert.deepStrictEqual(posts.shift(),
      { link: "https://dmai-share.example/s/abc.def#/clients/x/overview", action: "revoke" });
    assert.deepStrictEqual(errors, []);
  } finally {
    await browser.close();
    server.close();
  }
});

test("admin · client links says so when the ledger is not configured, rather than listing nothing", { skip }, async () => {
  const pw = resolvePlaywright();
  const browser = await pw.chromium.launch({ executablePath: resolveChromium(), args: ["--no-sandbox"] });
  const { server, base } = await startServer(BOOT);
  try {
    const page = await (await browser.newContext()).newPage();
    await page.route("**/api/admin/share-links", (r) => r.fulfill({ status: 200,
      contentType: "application/json", body: JSON.stringify({ status: "not_configured", links: [] }) }));
    await page.route("**/api/admin/usage**", (r) => r.fulfill({ status: 200, contentType: "application/json",
      body: JSON.stringify({ status: "not_configured" }) }));
    await openAdmin(page, base);
    const text = await page.locator('[data-screen-label="Admin · Client links"]').innerText();
    assert.match(text, /not configured/);
    assert.match(text, /share-revoked\.txt/);
  } finally {
    await browser.close();
    server.close();
  }
});

/* Owner, 2026-10-08: "the whitelist should show me a list of whitelisted
   client domains and allow me to revoke access. Similar to the user list
   above" — and the user list itself "100% similar to the prototype": a role
   select and a Deactivate button on every row, a server refusal a toast. */
test("admin · whitelisted client domains revoke in one request; users & roles is the prototype's card", { skip }, async () => {
  const pw = resolvePlaywright();
  const browser = await pw.chromium.launch({ executablePath: resolveChromium(), args: ["--no-sandbox"] });
  const { server, base } = await startServer(BOOT);
  try {
    const page = await (await browser.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
    const errors = []; page.on("pageerror", (e) => errors.push(String(e.message)));
    const posts = [], userPosts = [];
    await page.route("**/api/admin/share-links", (r) => {
      if (r.request().method() === "POST") {
        posts.push(JSON.parse(r.request().postData()));
        return r.fulfill({ status: 200, contentType: "application/json",
                           body: JSON.stringify({ domain: "bcu.com", action: "revoke", links: ["linkActive01"] }) });
      }
      return r.fulfill({ status: 200, contentType: "application/json",
                         body: JSON.stringify({ status: "ok", links: LINKS }) });
    });
    await page.route("**/api/admin/users", (r) => {
      if (r.request().method() === "POST") {
        userPosts.push({ body: JSON.parse(r.request().postData()), key: r.request().headers()["idempotency-key"] });
        return r.fulfill({ status: 409, contentType: "application/json",
          body: JSON.stringify({ error: "owner_floor", detail: "dma@zennify.com is on the deploy-time owner list (ADMIN_EMAILS) and stays an active Admin" }) });
      }
      return r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ users: [
        { email: "dma@zennify.com", display_name: "DMA", role: "ADMIN", is_active: true, last_seen_at: new Date().toISOString() },
        { email: "sam.ae@zennify.com", display_name: "Sam Ae", role: "AE", is_active: true, last_seen_at: null },
      ], owner_floor: ["dma@zennify.com"] }) });
    });
    await page.route("**/api/admin/usage**", (r) => r.fulfill({ status: 200, contentType: "application/json",
      body: JSON.stringify({ status: "not_configured" }) }));
    await openAdmin(page, base);

    const users = page.locator(".card", { has: page.locator("h3", { hasText: "Users & roles" }) });
    await users.locator("tbody tr", { hasText: "sam.ae@zennify.com" }).waitFor();
    assert.equal(await users.locator("tbody select").count(), 2, "a row lost its role select");
    assert.equal(await users.getByRole("button", { name: "Deactivate" }).count(), 2, "a row lost its Deactivate button");
    assert.equal(await users.locator("tbody select:disabled").count(), 0);
    const ut = await users.innerText();
    assert.match(ut, /Invited/, "a user never seen reads as Invited, as in the prototype");
    assert.match(ut, /1 min ago/);
    assert.ok(!/Owner account|Any other @zennify\.com/.test(ut), ut);
    await users.locator("tbody tr", { hasText: "dma@zennify.com" }).locator("select").selectOption("AE");
    await settle(page);
    assert.equal(userPosts.length, 1);
    assert.deepStrictEqual(userPosts[0].body, { email: "dma@zennify.com", role: "AE" });
    assert.match(userPosts[0].key, /^[0-9a-f-]{36}$/, "no Idempotency-Key on the write");
    assert.match(await page.locator("body").innerText(), /owner list/, "the refusal was not shown");
    assert.equal(await users.locator("tbody tr", { hasText: "dma@zennify.com" }).locator("select").inputValue(), "ADMIN",
                 "a refused change left the row showing a role it does not hold");

    const card = page.locator('[data-screen-label="Admin · Whitelisted client domains"]');
    await card.locator('tr[data-domain="bcu.com"]').waitFor();
    const text = await card.innerText();
    assert.match(text, /@bcu\.com/);
    assert.match(text, /Baxter Credit Union/);
    assert.match(text, /jane@bcu\.com/);
    assert.ok(!text.includes("cfo@bcu.com"), "a revoked link's recipient is listed as whitelisted");
    await card.getByRole("button", { name: "Revoke access" }).click();
    await settle(page);
    assert.deepStrictEqual(posts, [{ domain: "bcu.com", action: "revoke" }]);
    assert.deepStrictEqual(errors, []);
  } finally {
    await browser.close();
    server.close();
  }
});
