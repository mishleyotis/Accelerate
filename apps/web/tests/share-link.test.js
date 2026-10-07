/* Client share links: the capability, its allowlist, and the public service's
 * door.
 *
 * Owner's rules (2026-10-07):
 *   · a client link opens without a Zennify login, on its own public service;
 *   · it is shared TO named people — their addresses and their organisations'
 *     domains are the allowlist, for that one DMA;
 *   · no mail provider, no identity provider, no third-party key.
 *
 * What makes it safe is asserted here rather than described: the token is
 * signed by a key the public service never holds, binds one client and one
 * run, expires, can be revoked, and refuses every edit; the allowlist admits
 * exact domains only and never a consumer mailbox provider; and every route
 * in the app either belongs to the share service or refuses to run there.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const S = require("../lib/share.js");

const KEYS = crypto.generateKeyPairSync("ed25519");
const OTHER = crypto.generateKeyPairSync("ed25519");
const NOW = Date.parse("2026-10-07T12:00:00Z");
const BASE = { entity: "baxter-credit-union-bcu", run: "d7ed1d90-d406-4e8e-9ab0-75f91a0c15bb" };

const make = (over, now = NOW) =>
  S.mint({ ...BASE, recipients: "jane@bcu.com", ...over }, KEYS.privateKey, now);
const check = (token, { now = NOW, revoked = new Set(), key = KEYS.publicKey } = {}) =>
  S.verify(token, key, now, revoked);

test("a minted link verifies, and names its client, run and allowlist", () => {
  const { token, payload } = make();
  const p = check(token);
  assert.ok(p);
  assert.strictEqual(p.e, BASE.entity);
  assert.strictEqual(p.r, BASE.run);
  assert.deepStrictEqual(p.a, { m: ["jane@bcu.com"], d: ["bcu.com"] });
  assert.strictEqual(p.exp - p.iat, 30 * 86400, "default lifetime is 30 days");
  assert.strictEqual(p.jti, payload.jti);
});

test("sharing with jane@bcu.com admits jane and anyone @bcu.com — and nobody else", () => {
  const p = check(make().token);
  for (const ok of ["jane@bcu.com", "JANE@BCU.COM", " cfo@bcu.com ", "it.ops@bcu.com"]) {
    assert.strictEqual(S.allowed(p, ok), true, ok);
  }
  for (const no of ["jane@bcu.org", "x@evil-bcu.com", "x@bcu.com.evil.net", "x@mail.bcu.com",
                    "bcu.com", "", null, "jane@bcu.com>", "a@b"]) {
    assert.strictEqual(S.allowed(p, no), false, String(no));
  }
});

test("a consumer mailbox admits the exact address, never its whole provider", () => {
  const p = check(make({ recipients: "cfo.personal@gmail.com; jane@bcu.com" }).token);
  assert.deepStrictEqual(p.a.d, ["bcu.com"]);
  assert.strictEqual(S.allowed(p, "cfo.personal@gmail.com"), true);
  assert.strictEqual(S.allowed(p, "anyone@gmail.com"), false);
});

test("a recipient that is not an email refuses the whole link, not just the typo", () => {
  assert.throws(() => make({ recipients: "jane@bcu.com, sam@bcu" }), /not an email address/);
  assert.throws(() => make({ recipients: "" }), /at least one recipient/);
  assert.throws(() => make({ recipients: Array.from({ length: 26 }, (_, i) => `u${i}@bcu.com`) }),
                /at most 25/);
});

test("lifetime is bounded, and the bound is enforced on verify too", () => {
  assert.throws(() => make({ days: 0 }), /days must be/);
  assert.throws(() => make({ days: 91 }), /days must be/);
  const { token } = make({ days: 90 });
  assert.ok(check(token, { now: NOW + 89 * 86400e3 }));
  assert.strictEqual(check(token, { now: NOW + 90 * 86400e3 + 1000 }), null, "expired link still opens");
});

test("revoking a jti closes that link and no other", () => {
  const a = make(), b = make();
  const revoked = new Set([a.payload.jti]);
  assert.strictEqual(check(a.token, { revoked }), null);
  assert.ok(check(b.token, { revoked }));
});

test("every edit to a token is refused — client, run, allowlist, expiry, key", () => {
  const { token } = make();
  const [body, sig] = token.split(".");
  const p = JSON.parse(Buffer.from(body, "base64url").toString());
  const forge = (over) => `${Buffer.from(JSON.stringify({ ...p, ...over })).toString("base64url")}.${sig}`;
  for (const [what, t] of [
    ["another client", forge({ e: "other-client" })],
    ["another run", forge({ r: "another-run" })],
    ["a wider allowlist", forge({ a: { m: ["x@evil.com"], d: ["evil.com"] } })],
    ["a later expiry", forge({ exp: p.exp + 86400 })],
    ["a truncated signature", `${body}.${sig.slice(0, -2)}`],
    ["no signature", body],
    ["garbage", "not.a.token"],
  ]) {
    assert.strictEqual(check(t), null, `accepted a token with ${what}`);
  }
  assert.strictEqual(check(token, { key: OTHER.publicKey }), null, "verified under another key");
  // A link nobody is named on admits nobody, even correctly signed.
  const bare = Buffer.from(JSON.stringify({ ...p, a: { m: [], d: [] } })).toString("base64url");
  const bareTok = `${bare}.${crypto.sign(null, Buffer.from(bare), KEYS.privateKey).toString("base64url")}`;
  assert.strictEqual(check(bareTok), null);
});

test("token fields that reach an API path are validated at both ends", () => {
  assert.throws(() => make({ entity: "../v1/directory" }), /bad entity/);
  assert.throws(() => make({ run: "x?audience=internal" }), /bad run/);
});

test("the public service can verify but cannot mint", () => {
  // The share service is configured with the PUBLIC key only (infra/deploy.sh).
  assert.throws(() => S.mint({ ...BASE, recipients: "a@bcu.com" }, null), /not configured/);
  assert.throws(() => S.mint({ ...BASE, recipients: "a@bcu.com" }, KEYS.publicKey));
});

const SECRET = "x".repeat(48);

test("the access cookie is signed, per link, path-scoped, expiring and re-checked", () => {
  const { token } = make();
  const p = check(token);
  const c = S.accessCookie(p, token, "cfo@bcu.com", "otp", NOW, SECRET);
  assert.match(c, new RegExp(`^dma_share_${p.jti}=`));
  assert.match(c, new RegExp(`Path=/s/${token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")};`));
  assert.match(c, /HttpOnly; Secure; SameSite=Lax/);
  const value = c.split(";")[0].slice(c.indexOf("=") + 1);
  assert.strictEqual(S.readAccess(p, value, NOW, SECRET), "cfo@bcu.com");
  // At most ACCESS_DAYS, never past the link itself.
  assert.strictEqual(S.readAccess(p, value, NOW + (S.ACCESS_DAYS * 86400 + 5) * 1e3, SECRET), null);
  // Forged: an unsigned address, a wrong key, another link's jti.
  assert.strictEqual(S.readAccess(p, Buffer.from("cfo@bcu.com").toString("base64url"), NOW, SECRET), null);
  assert.strictEqual(S.readAccess(p, value, NOW, "y".repeat(48)), null);
  const other = check(make().token);
  assert.strictEqual(S.readAccess(other, value, NOW, SECRET), null, "a cookie carried to another link");
  // Without a secret nothing is admitted, and nothing can be signed.
  assert.strictEqual(S.readAccess(p, value, NOW, null), null);
  assert.throws(() => S.accessCookie(p, token, "cfo@bcu.com", "otp", NOW, null), /not configured/);
});

test("OTP mode is on exactly when Identity Platform is configured", () => {
  const was = process.env.SHARE_IDP_API_KEY;
  delete process.env.SHARE_IDP_API_KEY;
  assert.strictEqual(S.verifyMode(), "attest");
  process.env.SHARE_IDP_API_KEY = "test-key";
  assert.strictEqual(S.verifyMode(), "otp");
  if (was === undefined) delete process.env.SHARE_IDP_API_KEY; else process.env.SHARE_IDP_API_KEY = was;
});

test("the sign-in sender is rate-limited per link and address", async () => {
  const O = require("../lib/share-otp.js");
  for (let i = 0; i < 5; i++) assert.strictEqual(O.mayResend("j1", "a@bcu.com", NOW + i), true);
  assert.strictEqual(O.mayResend("j1", "a@bcu.com", NOW + 10), false, "a sixth send inside the window");
  assert.strictEqual(O.mayResend("j1", "b@bcu.com", NOW + 10), true, "another address is its own budget");
  assert.strictEqual(O.mayResend("j1", "a@bcu.com", NOW + 16 * 60e3), true, "the window passes");
});

test("share responses are unframeable, unindexed, uncached and leak no Referer", () => {
  const h = S.SHARE_HEADERS;
  assert.match(h["content-security-policy"], /frame-ancestors 'none'/);
  // The gate posts to its own origin; 'none' here silently broke the gate.
  assert.match(h["content-security-policy"], /form-action 'self'/);
  assert.strictEqual(h["referrer-policy"], "no-referrer");
  assert.match(h["x-robots-tag"], /noindex/);
  assert.match(h["cache-control"], /no-store/);
});

test("only the client dashboard's own reads are shareable", () => {
  assert.deepStrictEqual([...S.SHARE_PAGES].sort(),
    ["evidence", "heatmap", "insights", "overview", "subcaps"]);
});

/* ── The door ─────────────────────────────────────────────────────────
   Every route file in the app either IS a share route (under app/s/, and
   refuses to run anywhere BUT the share service) or refuses to run ON the
   share service. A new route that forgets is a red test, not a public
   endpoint. */
function routes(dir, out = []) {
  for (const f of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, f.name);
    if (f.isDirectory()) routes(p, out);
    else if (/^(route|page)\.(js|jsx)$/.test(f.name)) out.push(p);
  }
  return out;
}

test("no route runs on the share service unless it is a share route", () => {
  const APP = path.join(__dirname, "..", "app");
  const all = routes(APP);
  assert.ok(all.length >= 10, `found only ${all.length} routes`);
  for (const f of all) {
    const rel = path.relative(APP, f);
    const src = fs.readFileSync(f, "utf8");
    if (rel.startsWith(`s${path.sep}`)) {
      assert.match(src, /if \(!shareMode\(\)\) return new Response\("Not found", \{ status: 404 \}\)/,
        `${rel} serves outside the share service`);
      // A link's own routes go through liveLink (signature + ledger
      // revocation); the auth-action redirector only validates its target.
      assert.match(src, /liveLink\(params\.token\)|verify\(m\[1\]\)/, `${rel} does not verify the token`);
    } else {
      assert.match(src, /if \(shareMode\(\)\) (return new Response\("Not found", \{ status: 404 \}\)|notFound\(\))/,
        `${rel} runs on the public share service`);
    }
  }
});

test("a share read never asks the API for anything but the customer audience", () => {
  const src = fs.readFileSync(path.join(__dirname, "..", "lib", "share-read.js"), "utf8");
  assert.match(src, /searchParams\.set\("audience", "customer"\)/);
  assert.match(src, /searchParams\.set\("role", "AE"\)/);
  assert.match(src, /searchParams\.set\("run", payload\.r\)/);
  assert.ok(!/audience", "internal"|directory/.test(src.replace(/\/\/.*$/gm, "")),
    "share-read reaches the internal audience or the directory");
});

/* ── Revocation (Admin › Client links, lib/share-ledger) ─────────────────
   Owner, 2026-10-07: "The admin page should also have a place where I can
   revoke access." The ledger is a directory here and a bucket in
   production; the rules are the same code. */
const os = require("node:os");
const L = require("../lib/share-ledger.js");
function ledger() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "share-ledger-"));
  return { dir, backend: L.ledgerBackend({ SHARE_LEDGER_DIR: dir }) };
}
const withKey = async (fn) => {
  const was = process.env.SHARE_VERIFY_KEY;
  process.env.SHARE_VERIFY_KEY = KEYS.publicKey.export({ type: "spki", format: "pem" });
  try { return await fn(); } finally {
    if (was === undefined) delete process.env.SHARE_VERIFY_KEY; else process.env.SHARE_VERIFY_KEY = was;
  }
};
const live = (over) => S.mint({ ...BASE, recipients: "jane@bcu.com, cfo.home@gmail.com", ...over }, KEYS.privateKey);

test("a removed address is refused even under its still-listed domain; a removed domain keeps named addresses", () => {
  const p = { ...check(make({ recipients: "jane@bcu.com, sam@bcu.com" }).token) };
  p.x = { m: ["jane@bcu.com"], d: [] };
  assert.strictEqual(S.allowed(p, "jane@bcu.com"), false, "a removed address still opens");
  assert.strictEqual(S.allowed(p, "cfo@bcu.com"), true, "removing jane closed the whole domain");
  p.x = { m: [], d: ["bcu.com"] };
  assert.strictEqual(S.allowed(p, "cfo@bcu.com"), false, "a removed domain still admits its people");
  assert.strictEqual(S.allowed(p, "sam@bcu.com"), true, "a named address fell with its domain");
});

test("revoking a link closes it at the door; restoring reopens it; every change is kept", async () => {
  const { backend } = ledger();
  const { token, payload } = live();
  await withKey(async () => {
    assert.ok((await L.liveLink(token, backend)).p, "a fresh link does not open");
    await L.changeRevocation(payload.jti, { action: "revoke", by: "admin@zennify.com" }, backend);
    L.clearRevocationCache();
    assert.deepStrictEqual(await L.liveLink(token, backend), { p: null, why: "revoked" });
    const r = await L.changeRevocation(payload.jti, { action: "restore", by: "admin@zennify.com" }, backend);
    L.clearRevocationCache();
    assert.ok((await L.liveLink(token, backend)).p, "a restored link stays closed");
    assert.deepStrictEqual(r.history.map((h) => h.action), ["revoke", "restore"]);
    assert.strictEqual(r.history[0].by, "admin@zennify.com");
  });
});

test("removing a recipient refuses them at the gate AND ends a session they already hold", async () => {
  const { backend } = ledger();
  const { token, payload } = live();
  const SECRET = "s".repeat(48);
  await withKey(async () => {
    const before = (await L.liveLink(token, backend)).p;
    const { value } = S.signAccess(before, "cfo@bcu.com", "otp", NOW, SECRET);
    assert.strictEqual(S.readAccess(before, value, NOW, SECRET), "cfo@bcu.com");
    await L.changeRevocation(payload.jti, { action: "remove", domain: "@BCU.com" }, backend);
    L.clearRevocationCache();
    const after = (await L.liveLink(token, backend)).p;
    assert.ok(after, "removing a domain killed the whole link");
    assert.strictEqual(S.readAccess(after, value, NOW, SECRET), null, "an open session outlived the removal");
    assert.strictEqual(S.allowed(after, "cfo@bcu.com"), false);
    assert.strictEqual(S.allowed(after, "jane@bcu.com"), true, "jane is named; only the domain was removed");
    assert.strictEqual(S.allowed(after, "cfo.home@gmail.com"), true);
    await L.changeRevocation(payload.jti, { action: "readd", domain: "bcu.com" }, backend);
    L.clearRevocationCache();
    assert.strictEqual(S.readAccess((await L.liveLink(token, backend)).p, value, NOW, SECRET), "cfo@bcu.com");
  });
});

test("a ledger that cannot be read fails closed", async () => {
  const { token } = live();
  const broken = { kind: "x", async read() { throw new Error("boom"); } };
  L.clearRevocationCache();
  await withKey(async () => {
    assert.deepStrictEqual(await L.liveLink(token, broken), { p: null, why: "unavailable" });
  });
  // No ledger configured at all is not "unavailable": links run on the
  // signature and the deploy-time revocation list alone.
  await withKey(async () => { assert.ok((await L.liveLink(token, null)).p); });
});

test("a revocation is cached for at most REVOCATION_TTL_MS, then re-read", async () => {
  let reads = 0;
  const b = { async read() { reads++; return null; } };
  L.clearRevocationCache();
  await L.revocationOf("ttl-check-jti1", b, NOW);
  await L.revocationOf("ttl-check-jti1", b, NOW + L.REVOCATION_TTL_MS - 1);
  assert.strictEqual(reads, 1);
  await L.revocationOf("ttl-check-jti1", b, NOW + L.REVOCATION_TTL_MS + 1);
  assert.strictEqual(reads, 2, "a stale reading was served past its TTL");
});

test("the admin list: every recorded link with its status, and links revoked by id", async () => {
  const { backend } = ledger();
  const a = live(), b = live(), c = live({ days: 1 });
  for (const l of [a, b, c]) await L.recordLink(l.payload, "ae@zennify.com", backend);
  await assert.rejects(L.recordLink(a.payload, "ae@zennify.com", backend), "a link was recorded twice");
  await L.changeRevocation(b.payload.jti, { action: "revoke" }, backend);
  await L.changeRevocation("legacyLinkId", { action: "revoke" }, backend);
  const { status, links } = await L.listLinks(backend, Date.now() + 2 * 86400e3);
  assert.strictEqual(status, "ok");
  const by = Object.fromEntries(links.map((l) => [l.jti, l]));
  assert.strictEqual(by[a.payload.jti].status, "active");
  assert.deepStrictEqual(by[a.payload.jti].emails, ["cfo.home@gmail.com", "jane@bcu.com"]);
  assert.strictEqual(by[a.payload.jti].minted_by, "ae@zennify.com");
  assert.strictEqual(by[b.payload.jti].status, "revoked");
  assert.strictEqual(by[c.payload.jti].status, "expired");
  // A link generated before the ledger existed, revoked by its id.
  assert.strictEqual(by.legacyLinkId.status, "revoked");
  assert.strictEqual(by.legacyLinkId.unrecorded, true);
  assert.deepStrictEqual(await L.listLinks(null), { status: "not_configured", links: [] });
});

test("a pasted link or a bare id names the link; nothing else does", () => {
  const { token, payload } = live();
  assert.strictEqual(L.jtiFrom(S.shareUrl("https://dmai-share.example", token, BASE.entity)), payload.jti);
  assert.strictEqual(L.jtiFrom(payload.jti), payload.jti);
  for (const bad of ["", "https://example.com/", "../../etc", "a b c", "x".repeat(80)]) {
    assert.strictEqual(L.jtiFrom(bad), null, bad);
  }
});

test("a revocation names a real action and a real target", async () => {
  const { backend } = ledger();
  await assert.rejects(L.changeRevocation("validLinkId1", { action: "delete" }, backend), /unknown action/);
  await assert.rejects(L.changeRevocation("validLinkId1", { action: "remove" }, backend), /email address or domain/);
  await assert.rejects(L.changeRevocation("validLinkId1", { action: "remove", email: "not-an-email" }, backend), /email address or domain/);
  await assert.rejects(L.changeRevocation("../escape", { action: "revoke" }, backend), /not a link id/);
  await assert.rejects(L.changeRevocation("validLinkId1", { action: "revoke" }, null), /no ledger/);
});

/* The app is one document with a hash router: the sign-in page is "/#/login".
   Sign out lands there, and the path "/login" redirects there rather than 404. */
test("sign out and /login reach the hash route the app serves", () => {
  const utils = fs.readFileSync(path.join(__dirname, "..", "proto", "utils.jsx"), "utf8");
  assert.match(utils, /window\.location\.assign\("\/#\/login"\)/);
  assert.ok(!/window\.location\.assign\("\/login"\)/.test(utils), "sign out sends the browser to a 404");
  const login = fs.readFileSync(path.join(__dirname, "..", "app", "login", "route.js"), "utf8");
  assert.match(login, /status: 307, headers: \{ location: "\/#\/login"/);
});
