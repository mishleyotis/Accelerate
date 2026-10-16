// End to end, real stack: Chromium → next start (dmai-web) → uvicorn dma_api → Postgres.
// Every request carries an IAP-shaped signed assertion, as Google's front end adds it.
const H = require("../proto-page-harness");
const mint = require(__dirname + "/mint.js");
const crypto = require("crypto");
const { execSync } = require("child_process");
const AUD = "/projects/1/locations/us-central1/services/dmai-web", BASE = "http://localhost:3005";
const sql = q => execSync(`psql -h localhost -U postgres -d dma_insights -tAc "${q}"`, { env: { ...process.env, PGPASSWORD: "local" } }).toString().trim();
const row = e => sql(`select role||'/'||is_active from users where email='${e}'`);
// A cookie exactly like lib/session.js signs, but already expired: the page was opened 8h+ ago.
const expiredCookie = (email, role, name) => {
  const p = Buffer.from(JSON.stringify({ email, role, name, exp: Math.floor(Date.now() / 1000) - 60 })).toString("base64url");
  return `${p}.${crypto.createHmac("sha256", "e2e-session-secret").update(p).digest("base64url")}`;
};
const results = [];
const check = (name, ok, detail) => { results.push(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`); };

async function asUser(browser, email, fn) {
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 1000 }, extraHTTPHeaders: { "x-goog-iap-jwt-assertion": mint(email, { aud: AUD }) } });
  const p = await ctx.newPage();
  const toasts = [];
  p.on("response", async r => { if (r.url().includes("/api/admin/users") && r.request().method() === "POST") { try { toasts.push(`${r.status()} ${await r.text()}`); } catch {} } });
  try { await fn(ctx, p, toasts); } finally { await ctx.close(); }
}
async function openAdmin(p) {
  await p.goto(`${BASE}/#/`, { waitUntil: "domcontentloaded" }); await H.settle(p);
  await p.click('button[aria-label="Settings"]'); await p.click('.popover .toggle-row button:has-text("Admin")');
  await p.evaluate(() => { location.hash = "/admin"; }); await H.settle(p);
  await p.waitForSelector('input[placeholder="name@zennify.com"]', { timeout: 15000 });
  await p.waitForFunction(() => !/Loading users/.test(document.body.innerText), null, { timeout: 15000 });
}
async function invite(p, email, role) {
  await p.fill('input[placeholder="name@zennify.com"]', email);
  await p.selectOption('select[aria-label="Invite role"]', role);
  await p.click('button:has-text("Invite user")');
  await p.waitForTimeout(1500);
}
const toastText = p => p.evaluate(() => [...document.querySelectorAll(".toast, [class*=toast]")].map(t => t.innerText).join(" | "));

(async () => {
  const pw = H.resolvePlaywright();
  const browser = await pw.chromium.launch({ executablePath: H.resolveChromium(), args: ["--no-sandbox"] });
  sql("delete from session_log where user_id in (select id from users where email like 'e2e.%')");
  sql("delete from idempotency_keys where user_id in (select id from users where email like 'e2e.%')");
  sql("delete from users where email like 'e2e.%'");

  // 1. Owner, fresh page: the roster loads and every grant lands in the database.
  await asUser(browser, "dma@zennify.com", async (ctx, p, posts) => {
    await openAdmin(p);
    const roster = await p.locator(".card", { has: p.locator("h3", { hasText: "Users & roles" }) }).innerText();
    check("roster loads (no error row)", !/could not be read/.test(roster) && /dma@zennify\.com/.test(roster), roster.slice(0, 120).replace(/\n/g, " "));
    await invite(p, "e2e.admin@zennify.com", "ADMIN");
    check("invite as Admin → users row ADMIN", row("e2e.admin@zennify.com") === "ADMIN/true", `${row("e2e.admin@zennify.com")} · ${posts.slice(-1)[0] || "no POST"}`);
    await invite(p, "e2e.analyst@zennify.com", "ANALYST");
    check("invite as Analyst → users row ANALYST", row("e2e.analyst@zennify.com") === "ANALYST/true", posts.slice(-1)[0]);
    await p.selectOption('select[aria-label="Role for E2e Admin"]', "ANALYST"); await p.waitForTimeout(1200);
    check("change Admin → Analyst", row("e2e.admin@zennify.com") === "ANALYST/true", posts.slice(-1)[0]);
    await p.locator("tr", { hasText: "e2e.analyst@zennify.com" }).locator('button:has-text("Deactivate")').click(); await p.waitForTimeout(1200);
    check("deactivate", row("e2e.analyst@zennify.com") === "ANALYST/false", posts.slice(-1)[0]);
    await p.locator("tr", { hasText: "e2e.analyst@zennify.com" }).locator('button:has-text("Reactivate")').click(); await p.waitForTimeout(1200);
    check("reactivate", row("e2e.analyst@zennify.com") === "ANALYST/true", posts.slice(-1)[0]);
    await p.locator("tr", { hasText: "dma@zennify.com" }).locator("select").selectOption("AE"); await p.waitForTimeout(1200);
    check("owner cannot be demoted (409, row unchanged)", row("dma@zennify.com") === "ADMIN/true" && /409/.test(posts.slice(-1)[0] || ""), posts.slice(-1)[0]);
    const n = sql("select count(*) from session_log where user_id in (select id from users where email like 'e2e.%')");
    check("every applied change is one session_log row", n === "5", `rows=${n}`);
  });

  // 2. The reported failure: the page has been open past the 8-hour session cookie.
  await asUser(browser, "dma@zennify.com", async (ctx, p, posts) => {
    await openAdmin(p);
    await ctx.addCookies([{ name: "dma_session", value: expiredCookie("dma@zennify.com", "ADMIN", "DMA"), domain: "localhost", path: "/", httpOnly: true, secure: true, sameSite: "Lax" }]);
    await invite(p, "e2e.late@zennify.com", "ADMIN");
    check("page open past the cookie's 8h: invite still lands", row("e2e.late@zennify.com") === "ADMIN/true", posts.slice(-1)[0]);
    const c = (await ctx.cookies()).find(k => k.name === "dma_session");
    const exp = c ? JSON.parse(Buffer.from(c.value.split(".")[0], "base64url").toString()).exp : 0;
    check("…and the lapsed cookie is re-issued with a fresh 8h", exp > Date.now() / 1000 + 7 * 3600, `exp in ${Math.round((exp - Date.now() / 1000) / 3600)}h`);
    for (const path of ["/api/admin/users", "/api/admin/usage?days=7", "/api/admin/share-links"]) {
      await ctx.addCookies([{ name: "dma_session", value: expiredCookie("dma@zennify.com", "ADMIN", "DMA"), domain: "localhost", path: "/", httpOnly: true, secure: true, sameSite: "Lax" }]);
      const st = await p.evaluate(async u => (await fetch(u)).status, path);
      check(`lapsed cookie: GET ${path} is not refused`, st !== 403 && st !== 401, `status ${st}`);
    }
  });

  // 2b. A deactivated person whose cookie lapsed stays out.
  await asUser(browser, "e2e.analyst@zennify.com", async (ctx, p) => {
    sql("update users set is_active=false where email='e2e.analyst@zennify.com'");
    await ctx.addCookies([{ name: "dma_session", value: expiredCookie("e2e.analyst@zennify.com", "ADMIN", "E2e Analyst"), domain: "localhost", path: "/", httpOnly: true, secure: true, sameSite: "Lax" }]);
    const r = await p.request.get(`${BASE}/api/admin/users`);
    check("deactivated + lapsed cookie: refused", r.status() === 403, `status ${r.status()}`);
    sql("update users set is_active=true where email='e2e.analyst@zennify.com'");
  });

  // 3. The second owner.
  await asUser(browser, "mishley.otiende@zennify.com", async (ctx, p, posts) => {
    await openAdmin(p);
    await invite(p, "e2e.second@zennify.com", "ANALYST");
    check("second owner can grant", row("e2e.second@zennify.com") === "ANALYST/true", posts.slice(-1)[0]);
  });

  // 4. An AE cannot grant anything, even by calling the route directly.
  await asUser(browser, "e2e.someone@zennify.com", async (ctx, p) => {
    await p.goto(`${BASE}/#/`, { waitUntil: "domcontentloaded" }); await H.settle(p);
    check("an AE's first visit enrols them as AE", row("e2e.someone@zennify.com") === "AE/true", row("e2e.someone@zennify.com"));
    const r = await p.evaluate(async () => { const x = await fetch("/api/admin/users", { method: "POST", headers: { "content-type": "application/json", "idempotency-key": crypto.randomUUID() }, body: JSON.stringify({ email: "e2e.evil@zennify.com", role: "ADMIN" }) }); return `${x.status} ${await x.text()}`; });
    check("an AE's direct POST is refused, nothing written", /^403/.test(r) && row("e2e.evil@zennify.com") === "", r);
  });

  console.log(results.join("\n"));
  await browser.close();
  process.exit(results.some(r => r.startsWith("FAIL")) ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
