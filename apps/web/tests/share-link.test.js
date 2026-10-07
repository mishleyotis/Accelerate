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

test("the access cookie is per link, scoped to that link's path, and re-checked", () => {
  const { token } = make();
  const p = check(token);
  const c = S.accessCookie(p, token, "cfo@bcu.com", NOW);
  assert.match(c, new RegExp(`^dma_share_${p.jti}=`));
  assert.match(c, new RegExp(`Path=/s/${token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")};`));
  assert.match(c, /HttpOnly; Secure; SameSite=Lax/);
  const value = c.split(";")[0].split("=")[1];
  assert.strictEqual(S.readAccess(p, value), "cfo@bcu.com");
  // A cookie naming an address off the list admits nobody.
  assert.strictEqual(S.readAccess(p, Buffer.from("x@evil.com").toString("base64url")), null);
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
      assert.match(src, /verify\(params\.token\)/, `${rel} does not verify the token`);
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
