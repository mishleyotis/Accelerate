// Client-link usage, end to end on the real stack (owner, 2026-10-09: "Usage
// analytics for clients provided the link do not get registered … All links
// generated should be logged and usage analytics for each whitelisted login
// be tracked").
//
//   Chromium (Zennify, IAP-signed) ──▶ dmai-web  (next start :3005) mints
//   Chromium (client, no Google)   ──▶ dmai-share (next start :3006, SHARE_MODE=1)
//                                        gate → admit → dashboard → page beacons
//   both services' stdout ──(bq-emulator: what the sink puts in BigQuery)──▶
//   lib/usage-store readUsage ──▶ Admin › Usage analytics, rendered in Chromium
const H = require("../proto-page-harness");
const mint = require(__dirname + "/mint.js");
const emulator = require(__dirname + "/bq-emulator.js");

const AUD = "/projects/1/locations/us-central1/services/dmai-web";
const WEB = "http://localhost:3005", SHARE = "http://localhost:3006";
const ID = "e2e-client-cu", RUN = "e2e-run-0001";
const LOGS = [__dirname + "/web.log", __dirname + "/share.log"];
const results = [];
const check = (name, ok, detail) => { results.push(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`); };
const wait = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  process.env.BQ_ACCESS_TOKEN = "e2e-emulator";   // lib/usage-store token(): local QA only
  const S = await import("../../lib/usage-store.js");
  const emu = emulator(LOGS, S.WIRE_FIELDS);
  const lines = (pred) => emu.lines().filter(pred);
  const pw = H.resolvePlaywright();
  const browser = await pw.chromium.launch({ executablePath: H.resolveChromium(), args: ["--no-sandbox"] });
  const staff = await browser.newContext({ viewport: { width: 1400, height: 1000 },
    extraHTTPHeaders: { "x-goog-iap-jwt-assertion": mint("dma@zennify.com", { aud: AUD, expIn: 3600 }) } });
  const ps = await staff.newPage();
  await ps.goto(`${WEB}/#/`, { waitUntil: "domcontentloaded" });

  // 1. A link is generated on dmai-web: one link_minted line, naming who, for whom.
  const minted = await ps.evaluate(async ({ id, run }) => {
    const r = await fetch("/api/share", { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ entity: id, run, recipients: "Jane.Reader@e2e-cu.org, cfo@e2e-cu.org", days: 14 }) });
    return { status: r.status, body: await r.json() };
  }, { id: ID, run: RUN });
  check("dmai-web mints the link", minted.status === 200 && /\/s\//.test(minted.body.url || ""), `${minted.status} ${JSON.stringify(minted.body).slice(0, 120)}`);
  const jti = minted.body.jti;
  const token = (minted.body.url || "").split("/s/")[1].split("#")[0];
  await wait(400);
  const m = lines(u => u.type === "link_minted" && u.link_jti === jti);
  check("link_minted logged once, by the sharer, with recipients, domains and expiry",
    m.length === 1 && m[0].email === "dma@zennify.com" && m[0].role === "ADMIN" && m[0].client_id === ID && m[0].run_id === RUN
      && JSON.stringify([...m[0].recipients].sort()) === JSON.stringify(["cfo@e2e-cu.org", "jane.reader@e2e-cu.org"])
      && JSON.stringify(m[0].domains) === JSON.stringify(["e2e-cu.org"]) && !!m[0].expires_at,
    JSON.stringify(m[0] || null));

  // 2. The client opens it on dmai-share. An address off the list is refused and is nobody.
  const client = await browser.newContext({ viewport: { width: 1300, height: 900 } });
  const pc = await client.newPage();
  const beacons = [];
  pc.on("request", r => { if (/\/usage$/.test(r.url())) beacons.push(r.url()); });
  pc.on("response", r => { if (/\/usage$/.test(r.url())) beacons.push(`${r.status()} ${r.url()}`); });
  await pc.goto(minted.body.url, { waitUntil: "domcontentloaded" });
  check("the link opens the email gate", await pc.locator('input[name="email"]').count() === 1);
  await pc.fill('input[name="email"]', "intruder@evil.example");
  await Promise.all([pc.waitForLoadState("domcontentloaded"), pc.click('button[type="submit"]')]);
  await wait(300);
  const ref = lines(u => u.type === "link_refused" && u.link_jti === jti);
  check("a refused address is logged as link_refused, with no person behind it",
    ref.length === 1 && ref[0].email === null && ref[0].attempted_email === "intruder@evil.example" && ref[0].reason === "not_on_allowlist",
    JSON.stringify(ref[0] || null));
  check("…and never becomes a usage person", !lines(u => u.email === "intruder@evil.example").length);

  await pc.fill('input[name="email"]', "jane.reader@e2e-cu.org");
  await Promise.all([pc.waitForURL(/\/s\/.*#\/clients\//, { timeout: 15000 }), pc.click('button[type="submit"]')]);
  await H.settle(pc);
  await wait(500);
  const adm = lines(u => u.type === "link_admit" && u.link_jti === jti);
  const opn = lines(u => u.type === "link_open" && u.link_jti === jti);
  check("admitted recipient: link_admit (role CLIENT, method)", adm.length === 1 && adm[0].email === "jane.reader@e2e-cu.org" && adm[0].role === "CLIENT" && adm[0].method === "attest", JSON.stringify(adm[0] || null));
  check("dashboard load: link_open for that recipient", opn.length === 1 && opn[0].email === "jane.reader@e2e-cu.org" && opn[0].client_id === ID && /Chrome/.test(opn[0].device || ""), JSON.stringify(opn[0] || null));

  // 3. Reading: the tracker reports to the link's own route, as the admitted address.
  await pc.evaluate(id => { location.hash = `/clients/${id}/insights?view=client`; }, ID); await wait(2600);
  await pc.evaluate(id => { location.hash = `/clients/${id}/heatmap?view=client`; }, ID); await wait(2200);
  await pc.evaluate(id => { location.hash = `/clients/${id}/overview?view=client`; }, ID); await wait(1200);
  const pv = lines(u => u.type === "page_view" && u.link_jti === jti);
  check("beacons go to /s/<token>/api/usage and are accepted (204)",
    beacons.some(b => b.startsWith("204 ") && b.includes(`/s/${token}/api/usage`)) && !beacons.some(b => / \/api\/usage$/.test(b.replace(/^\d+ https?:\/\/[^/]+/, " "))),
    beacons.slice(0, 4).join(" | "));
  const ins = pv.find(u => u.page === "insights");
  check("page views logged as the recipient, CLIENT, customer audience, this link and client",
    pv.length >= 3 && pv.every(u => u.email === "jane.reader@e2e-cu.org" && u.role === "CLIENT" && u.audience === "customer"
      && u.client_link === true && u.acting_role === null && u.client_id === ID && u.run_id === RUN),
    `n=${pv.length} pages=${pv.map(u => u.page).join(",")}`);
  check("visible dwell is measured (insights ≥ 2 s)", ins && ins.dwell_ms >= 2000, ins ? `${ins.dwell_ms} ms` : "no insights view");

  // 4. The door: no cookie → 401, nothing logged; a forged identity in the body is ignored.
  const before = emu.lines().length;
  const st = (await fetch(`${SHARE}/s/${token}/api/usage`, { method: "POST",
    body: JSON.stringify({ events: [{ type: "heartbeat", sid: "anonymous001", path: "/clients/x/overview" }] }) })).status;
  const forgedCookie = (await fetch(`${SHARE}/s/${token}/api/usage`, { method: "POST",
    headers: { cookie: `dma_share_${jti}=e30.bm90LWEtbWFj` },
    body: JSON.stringify({ events: [{ type: "heartbeat", sid: "anonymous002", path: "/clients/x/overview" }] }) })).status;
  await wait(300);
  check("a beacon with no admitted reader, or a forged cookie, is refused (401) and logs nothing",
    st === 401 && forgedCookie === 401 && emu.lines().length === before, `status ${st} / ${forgedCookie}`);
  const forged = await pc.evaluate(async u => (await fetch(u, { method: "POST", body: JSON.stringify({ events: [{ type: "feature", feature: "evidence", sid: "forgedsid0001", path: "/clients/e2e-client-cu/heatmap", email: "boss@zennify.com", role: "ADMIN", audience: "internal", acting_role: "ADMIN" }] }) })).status, `${SHARE}/s/${token}/api/usage`);
  await wait(300);
  const fl = lines(u => u.sid === "forgedsid0001");
  check("identity, role and audience in the body are ignored", forged === 204 && fl.length === 1 && fl[0].email === "jane.reader@e2e-cu.org" && fl[0].role === "CLIENT" && fl[0].audience === "customer" && fl[0].acting_role === null, JSON.stringify(fl[0] || null));
  const wrongSvc = await ps.evaluate(async u => (await fetch(u, { method: "POST", body: "{}" })).status, `${WEB}/s/${token}/api/usage`);
  check("the share beacon does not exist on dmai-web (404)", wrongSvc === 404, `status ${wrongSvc}`);

  // 5. A colleague at the same organisation, admitted by domain, is tracked as themself.
  const c2 = await browser.newContext(); const p2 = await c2.newPage();
  await p2.goto(minted.body.url, { waitUntil: "domcontentloaded" });
  await p2.fill('input[name="email"]', "ops@e2e-cu.org");
  await Promise.all([p2.waitForURL(/#\/clients\//, { timeout: 15000 }), p2.click('button[type="submit"]')]);
  await H.settle(p2); await wait(1500);
  await p2.evaluate(id => { location.hash = `/clients/${id}/heatmap?view=client`; }, ID); await wait(1200);
  await c2.close(); await wait(500);
  check("domain-admitted reader logged under their own address", lines(u => u.email === "ops@e2e-cu.org" && u.type === "page_view").length >= 1
    && lines(u => u.email === "ops@e2e-cu.org" && u.type === "link_open").length === 1);
  await client.close(); await wait(500);

  // 6. Admin › Usage analytics renders it: the Client role, the people, the link.
  const body = await S.readUsage(30, { env: { GCP_PROJECT: "e2e-proj", USAGE_DATASET: "dmai_usage" }, fetchImpl: emu.fetchImpl });
  check("readUsage carries links and client-only people", body.status === "ok" && body.links.some(l => l[3] === jti)
    && body.client_only.includes("jane.reader@e2e-cu.org") && !body.client_only.includes("dma@zennify.com"),
    `status=${body.status} ${body.detail || ""} links=${(body.links || []).length} client_only=${(body.client_only || []).join(",")}`);
  await staff.route("**/api/admin/usage**", r => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) }));
  const pa = await staff.newPage();
  await pa.goto(`${WEB}/#/`, { waitUntil: "domcontentloaded" }); await H.settle(pa);
  await pa.click('button[aria-label="Settings"]'); await pa.click('.popover .toggle-row button:has-text("Admin")');
  await pa.evaluate(() => { location.hash = "/admin/usage"; }); await H.settle(pa);
  await pa.waitForSelector('[data-screen-label="Usage filters"]', { timeout: 15000 });
  const opts = await pa.locator('select[aria-label="Role"] option').allInnerTexts();
  check("the role filter offers Client (link)", opts.includes("Client (link)"), opts.join(","));
  const linksCard = () => pa.locator('[data-screen-label="Usage · Client links"]').innerText().catch(() => "");
  const lc = await linksCard();
  check("Client links card: the link, who shared it, opened/unopened recipients, opens, read time, refusals",
    /dma@zennify\.com/.test(lc) && /● jane\.reader@e2e-cu\.org/.test(lc) && /○ cfo@e2e-cu\.org/.test(lc) && /● ops@e2e-cu\.org/.test(lc)
      && /\b1 generated\b/.test(lc) && !/None yet/.test(lc), lc.replace(/\n/g, " ").slice(0, 260));
  const signals = await pa.locator(".card", { hasText: "Needs a nudge" }).innerText();
  check("Client links signal: generated and opened, by recipient", /1 link generated .*1 of 2 recipients have opened/.test(signals.replace(/\n/g, " ")), signals.replace(/\n/g, " ").slice(0, 200));
  await pa.selectOption('select[aria-label="Role"]', "CLIENT"); await wait(300);
  const users = await pa.locator(".card", { has: pa.locator("h3", { hasText: "Users · activity" }) }).innerText();
  check("Role = Client lists every recipient and reader, as Client, with their client",
    /jane\.reader@e2e-cu\.org/.test(users) && /cfo@e2e-cu\.org/.test(users) && /ops@e2e-cu\.org/.test(users) && /Client link · /.test(users)
      && !/dma@zennify\.com/.test(users) && /No activity yet|Never/.test(users), users.replace(/\n/g, " ").slice(0, 300));
  check("…and the Client links card stays", /e2e-cu\.org/.test(await linksCard()));
  await pa.selectOption('select[aria-label="Role"]', "AE"); await wait(300);
  check("Role = AE: no client people, no client link", !/e2e-cu\.org/.test(await pa.locator(".card", { has: pa.locator("h3", { hasText: "Users · activity" }) }).innerText()) && !/e2e-cu\.org/.test(await linksCard()));
  await pa.selectOption('select[aria-label="Role"]', "ALL"); await pa.fill('input[aria-label="Search people"]', "jane"); await wait(300);
  check("search narrows to the one recipient", /jane\.reader/.test(await linksCard()) && !/dma@zennify/.test(await pa.locator(".card", { has: pa.locator("h3", { hasText: "Users · activity" }) }).innerText()));
  await pa.fill('input[aria-label="Search people"]', "");
  await pa.locator("tr", { hasText: "jane.reader@e2e-cu.org" }).first().click(); await wait(300);
  const drawer = await pa.locator(".drawer, [role=dialog]").first().innerText().catch(() => "");
  check("the recipient's drawer opens with their sessions", /Client/.test(drawer) && /Insights|Heatmap|Overview/.test(drawer), drawer.replace(/\n/g, " ").slice(0, 160));

  // 7. Users & roles never offers a client a role.
  await pa.evaluate(() => { location.hash = "/admin"; }); await H.settle(pa);
  await pa.waitForFunction(() => !/Loading users/.test(document.body.innerText), null, { timeout: 15000 }).catch(() => {});
  await wait(800);
  const roster = await pa.locator(".card", { has: pa.locator("h3", { hasText: "Users & roles" }) }).innerText();
  check("Users & roles lists no client recipient", !/e2e-cu\.org/.test(roster) && /dma@zennify\.com/.test(roster), roster.replace(/\n/g, " ").slice(0, 160));

  await browser.close();
  console.log(results.join("\n"));
  const failed = results.filter(r => r.startsWith("FAIL")).length;
  console.log(`\nclient links e2e: ${results.length - failed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); console.log(results.join("\n")); process.exit(1); });
