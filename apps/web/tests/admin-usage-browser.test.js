/* Admin › Usage analytics and the admin console, in a browser, in production
 * mode (DMA_LIVE set): the compiled app, the real router, the real tracker.
 *
 *   · the usage page renders what /api/admin/usage returns — the people, the
 *     page time, the client researched — and nothing from the preview mock
 *   · a store that is not recording says so by name, with no chart pretending
 *   · moving between pages sends a page_view beacon carrying the VISIBLE dwell
 *     and no identity (the server takes identity from the session)
 *   · Import & jobs / Import audit are not reachable, by nav or by hash
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { resolvePlaywright, startServer, settle, resolveChromium, browserSkip,
        assertNoStringifiedObjects } = require("./proto-page-harness");

const skip = browserSkip();
const BOOT = {
  authed: true, role: "ADMIN", email: "dma@zennify.com", name: "DMA",
  catalogue_version: "v7.0", dev_login: false,
  subvertical_labels: { CREDIT_UNION: "Credit union" },
  entities: [{ id: "golden-1", slug: "golden-1", name: "Golden 1 Credit Union", subvertical: "CREDIT_UNION",
               status: "ACTIVE", data_source: "PROJECT_API", size_tier: "LARGE" }],
  active_runs: [], pending_review: [], import_scans: [],
  role_grants: { admins: ["dma@zennify.com"], analysts: ["analyst.one@zennify.com"], default: "AE" },
};

const F = ["t", "type", "email", "role", "sid", "page", "client_id", "dwell_ms", "cont", "feature",
           "device", "entered_at", "audience", "acting_role"];
function wire() {
  const now = Date.now();
  const ago = (m) => new Date(now - m * 60000).toISOString();
  const row = (o) => F.map((f) => (f in o ? o[f] : null));
  return {
    status: "ok", generated_at: new Date(now).toISOString(), range_days: 30, fields: F,
    recording_since: ago(60 * 24 * 40), truncated: false,
    last_seen: { "ae.one@zennify.com": ago(1), "dma@zennify.com": ago(60 * 24 * 3) },
    events: [
      row({ t: ago(30), type: "page_view", email: "ae.one@zennify.com", role: "AE", sid: "sessionAAAA1",
            page: "dashboard", dwell_ms: 90000, cont: false, entered_at: ago(31), device: "Desktop · Chrome" }),
      row({ t: ago(20), type: "page_view", email: "ae.one@zennify.com", role: "AE", sid: "sessionAAAA1",
            page: "platform", client_id: "golden-1", dwell_ms: 540000, cont: false, entered_at: ago(29) }),
      row({ t: ago(19), type: "feature", email: "ae.one@zennify.com", role: "AE", sid: "sessionAAAA1",
            page: "platform", client_id: "golden-1", feature: "evidence" }),
      row({ t: ago(1), type: "heartbeat", email: "ae.one@zennify.com", role: "AE", sid: "sessionAAAA1",
            page: "heatmap", client_id: "golden-1" }),
      row({ t: ago(60 * 24 * 3 + 5), type: "page_view", email: "dma@zennify.com", role: "ADMIN", sid: "sessionBBBB1",
            page: "admin", dwell_ms: 120000, cont: false, entered_at: ago(60 * 24 * 3 + 7) }),
    ],
  };
}

async function openApp(browser, base, hash, usageBody, users) {
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 1000 } });
  const p = await ctx.newPage();
  const errors = [], beacons = [];
  p.on("pageerror", (e) => errors.push(String(e.message)));
  if (users) await p.route("**/api/admin/users", users);
  await p.route("**/api/admin/usage**", (r) => r.fulfill({ status: 200, contentType: "application/json",
                                                           body: JSON.stringify(usageBody) }));
  await p.route("**/api/usage", (r) => {
    try { beacons.push(...JSON.parse(r.request().postData() || "{}").events); } catch {}
    r.fulfill({ status: 204, body: "" });
  });
  // Everyone lands in the AE view (app-root.jsx _landingRole); an admin
  // switches deliberately — Settings → Acting as → Admin — and so does this.
  await p.goto(`${base}/#/`, { waitUntil: "domcontentloaded" });
  await settle(p);
  await p.click('button[aria-label="Settings"]');
  await p.click('.popover .toggle-row button:has-text("Admin")');
  await p.evaluate((h) => { location.hash = h.replace(/^#/, ""); }, hash);
  await settle(p);
  return { ctx, p, errors, beacons };
}

test("usage analytics renders the live store and nothing from the mock", { skip }, async () => {
  const pw = resolvePlaywright();
  const browser = await pw.chromium.launch({ executablePath: resolveChromium(), args: ["--no-sandbox"] });
  const { server, base } = await startServer(BOOT);
  try {
    const { ctx, p, errors } = await openApp(browser, base, "#/admin/usage", wire());
    await p.waitForFunction(() => /Users · activity/.test(document.body.innerText), null, { timeout: 10000 });
    const text = await p.evaluate(() => document.body.innerText);
    assert.deepStrictEqual(errors, []);
    await assertNoStringifiedObjects(p, "usage analytics");
    for (const want of ["Ae One", "Analyst One", "No activity yet", "Golden 1 Credit Union",
                        "Client · Platform", "Live now", "Evidence drawers opened"]) {
      assert.ok(text.includes(want), `usage page is missing "${want}"`);
    }
    for (const mock of ["Sara Lin", "Priya Nair", "FSI · East", "Meeting prep generated"]) {
      assert.ok(!text.includes(mock), `usage page shows preview data "${mock}"`);
    }
    if (process.env.UA_SHOT) await p.screenshot({ path: process.env.UA_SHOT, fullPage: true });
    await ctx.close();
  } finally {
    await browser.close();
    server.close();
  }
});

test("a store that is not recording says so, with no chart", { skip }, async () => {
  const pw = resolvePlaywright();
  const browser = await pw.chromium.launch({ executablePath: resolveChromium(), args: ["--no-sandbox"] });
  const { server, base } = await startServer(BOOT);
  try {
    const { ctx, p } = await openApp(browser, base, "#/admin/usage",
      { status: "not_recording", range_days: 30, fields: F, detail: "Not found: Table" });
    await p.waitForFunction(() => /Not recording yet/.test(document.body.innerText), null, { timeout: 10000 });
    const text = await p.evaluate(() => document.body.innerText);
    assert.ok(!text.includes("Daily activity") && !text.includes("Active users"), text.slice(0, 400));
    await ctx.close();
  } finally {
    await browser.close();
    server.close();
  }
});

test("navigation sends page views with visible dwell and no identity", { skip }, async () => {
  const pw = resolvePlaywright();
  const browser = await pw.chromium.launch({ executablePath: resolveChromium(), args: ["--no-sandbox"] });
  const { server, base } = await startServer(BOOT);
  try {
    const { ctx, p, beacons } = await openApp(browser, base, "#/prospecting", wire());
    await p.waitForTimeout(1200);
    await p.evaluate(() => { location.hash = "/admin"; });
    await settle(p);
    await p.waitForFunction(() => true);
    await p.waitForTimeout(300);
    const pv = beacons.filter((b) => b.type === "page_view");
    assert.deepEqual(pv.map((b) => b.path), ["/", "/prospecting"],
                     "one view per page left, in order (the dashboard first: the admin switch happens there)");
    const first = pv[1];
    assert.ok(first.dwell_ms >= 1000 && first.dwell_ms < 60000, `dwell ${first.dwell_ms}`);
    assert.match(first.sid, /^[a-f0-9]{24}$/);
    assert.equal(first.cont, false);
    assert.ok(!("email" in first) && !("role" in first), "identity never travels in the beacon");
    await ctx.close();
  } finally {
    await browser.close();
    server.close();
  }
});

test("Import & jobs and Import audit are unreachable in production", { skip }, async () => {
  const pw = resolvePlaywright();
  const browser = await pw.chromium.launch({ executablePath: resolveChromium(), args: ["--no-sandbox"] });
  const { server, base } = await startServer(BOOT);
  try {
    for (const hash of ["#/admin/import", "#/admin/import/audit"]) {
      const { ctx, p } = await openApp(browser, base, hash, wire());
      const text = await p.evaluate(() => document.body.innerText);
      assert.ok(text.includes("Page not found"), `${hash} rendered: ${text.slice(0, 200)}`);
      assert.ok(!text.includes("SSE LIVE") && !text.includes("Drive import audit"));
      const nav = await p.evaluate(() => [...document.querySelectorAll(".sb-a")].map((n) => n.innerText.trim()));
      assert.ok(nav.includes("Usage analytics"), nav.join(","));
      assert.ok(!nav.some((n) => /^Import/.test(n)), nav.join(","));
      await ctx.close();
    }
  } finally {
    await browser.close();
    server.close();
  }
});

test("Users & roles allocates roles through the users API", { skip }, async () => {
  const pw = resolvePlaywright();
  const browser = await pw.chromium.launch({ executablePath: resolveChromium(), args: ["--no-sandbox"] });
  const { server, base } = await startServer(BOOT);
  const roster = [
    { email: "dma@zennify.com", display_name: "DMA", role: "ADMIN", is_active: true, signed_in: true, last_seen_at: null, created_at: null },
    { email: "owner@zennify.com", display_name: "Owner", role: "ADMIN", is_active: true, signed_in: true, last_seen_at: null, created_at: null },
    { email: "sam.reader@zennify.com", display_name: "Sam Reader", role: "AE", is_active: true, signed_in: true, last_seen_at: null, created_at: null },
  ];
  const posts = [];
  const users = (r) => {
    if (r.request().method() === "GET") {
      return r.fulfill({ status: 200, contentType: "application/json",
                         body: JSON.stringify({ users: roster, owner_floor: ["owner@zennify.com"], default_role: "AE" }) });
    }
    const body = JSON.parse(r.request().postData());
    posts.push({ body, key: r.request().headers()["idempotency-key"] });
    const u = { ...(roster.find(x => x.email === body.email) || { email: body.email, display_name: "New Person", role: "AE", is_active: true, signed_in: false }), ...body };
    return r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ user: u, event: "role_changed" }) });
  };
  try {
    const { ctx, p, errors } = await openApp(browser, base, "#/admin", wire(), users);
    await p.waitForSelector('select[aria-label="Role for Sam Reader"]', { timeout: 10000 });
    // The prototype's card (owner, 2026-10-08): every row is editable; the
    // server, not the page, refuses the owner floor and your own access.
    for (const n of ["Owner", "DMA", "Sam Reader"]) {
      assert.ok(!(await p.isDisabled(`select[aria-label="Role for ${n}"]`)), `${n}'s role select is locked`);
    }
    await p.selectOption('select[aria-label="Role for Sam Reader"]', "ANALYST");
    await p.waitForFunction(() => /Role updated to ANALYST/.test(document.body.innerText), null, { timeout: 5000 });
    assert.deepEqual(posts[0].body, { email: "sam.reader@zennify.com", role: "ANALYST" });
    assert.match(posts[0].key, /^[0-9a-f-]{36}$/, "every write carries an Idempotency-Key");
    // Deactivate, then invite.
    await p.click('tr:has-text("sam.reader@zennify.com") button:has-text("Deactivate")');
    await p.waitForFunction(() => /Sam Reader deactivated/.test(document.body.innerText), null, { timeout: 5000 });
    assert.deepEqual(posts[1].body, { email: "sam.reader@zennify.com", is_active: false });
    await p.fill('input[placeholder="name@zennify.com"]', "new.person@zennify.com");
    await p.selectOption('select[aria-label="Invite role"]', "ADMIN");
    await p.click('button:has-text("Invite user")');
    await p.waitForFunction(() => /Access granted to new.person@zennify.com as Admin/.test(document.body.innerText), null, { timeout: 5000 });
    assert.deepEqual(posts[2].body, { email: "new.person@zennify.com", role: "ADMIN" });
    // A usage-seen account without a row is listed as an AE and can be granted.
    assert.ok(await p.isVisible('select[aria-label="Role for Ae One"]'), "seen-in-usage account is listed");
    assert.deepEqual(errors, []);
    await ctx.close();
  } finally {
    await browser.close();
    server.close();
  }
});

test("usage analytics renders its full layout at zero while awaiting the first event", { skip }, async () => {
  const pw = resolvePlaywright();
  const browser = await pw.chromium.launch({ executablePath: resolveChromium(), args: ["--no-sandbox"] });
  const { server, base } = await startServer(BOOT);
  const empty = { status: "ok", awaiting_first_event: true, generated_at: new Date().toISOString(), range_days: 30,
                  fields: F, recording_since: null, truncated: false, last_seen: {}, events: [] };
  try {
    const { ctx, p, errors } = await openApp(browser, base, "#/admin/usage", empty);
    await p.waitForFunction(() => /Recording is live/.test(document.body.innerText), null, { timeout: 10000 });
    const t = await p.evaluate(() => document.body.textContent);
    for (const want of ["Active users", "Sessions", "Avg session", "Pages / session", "Stickiest surface"]) {
      assert.ok(t.includes(want), `layout section "${want}" missing while awaiting`);
    }
    assert.ok(!/Usage data is not readable|Not recording yet/.test(t));
    assert.deepEqual(errors, []);
    await ctx.close();
  } finally {
    await browser.close();
    server.close();
  }
});
