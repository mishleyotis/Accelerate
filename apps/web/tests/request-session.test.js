/* Every API route asks lib/request-session.js who is calling.
 *
 * 2026-10-08: the owner's Users & roles changes read "admin_session_required"
 * — the 8-hour session cookie had lapsed in a tab that was still open, and
 * only a document load re-minted it. Reproduced end to end (real Next, real
 * API, real Postgres, Chromium carrying a signed IAP assertion) before the
 * fix; these pin the rule: a lapsed cookie is re-established from the IAP
 * assertion Google puts on every request, verified as at sign-in, with the
 * role re-read and the cookie re-issued — and nothing else re-establishes it.
 */
const test = require("node:test");
const assert = require("node:assert");
const crypto = require("node:crypto");

process.env.SESSION_SECRET = "unit-session-secret";
process.env.IAP_AUDIENCE = "/projects/1/locations/us-central1/services/dmai-web";
process.env.API_URL = "https://api.test";
process.env.ADMIN_EMAILS = "owner@zennify.com";
const S = require("../lib/session.js");
const { requestSession } = require("../lib/request-session.js");

const { privateKey, publicKey } = crypto.generateKeyPairSync("ec", { namedCurve: "P-256" });
const JWKS = { keys: [{ ...publicKey.export({ format: "jwk" }), kid: "unit", alg: "ES256" }] };
function mint(email, over = {}) {
  const b64 = (o) => Buffer.from(JSON.stringify(o)).toString("base64url");
  const now = Math.floor(Date.now() / 1000);
  const h = b64({ alg: "ES256", kid: "unit" });
  const p = b64({ iss: "https://cloud.google.com/iap", aud: process.env.IAP_AUDIENCE, email, iat: now, exp: now + 600, ...over });
  const sig = crypto.sign("sha256", Buffer.from(`${h}.${p}`), { key: privateKey, dsaEncoding: "ieee-p1363" }).toString("base64url");
  return `${h}.${p}.${sig}`;
}
// Google's key list and svc_api /v1/me, as the route would reach them.
let me = { role: "ANALYST", is_active: true, source: "users" };
globalThis.fetch = async (url) => {
  const u = String(url);
  if (u.startsWith("https://www.gstatic.com/iap/")) return new Response(JSON.stringify(JWKS));
  if (u.startsWith("http://metadata.google.internal")) return new Response("", { status: 404 });
  if (u === "https://api.test/v1/me") return new Response(JSON.stringify({ email: me.email, ...me }));
  throw new Error("unexpected fetch " + u);
};
function jar(value) {
  const set = [];
  return { set, get: (n) => (n === S.COOKIE && value ? { value } : undefined), set: (...a) => set.push(a), _set: set };
}
const req = (assertion) => ({ headers: { get: (h) => (h === "x-goog-iap-jwt-assertion" ? assertion || null : null) } });
const lapsed = (email, role) => {
  const p = Buffer.from(JSON.stringify({ email, role, name: "X", exp: Math.floor(Date.now() / 1000) - 60 })).toString("base64url");
  return `${p}.${crypto.createHmac("sha256", process.env.SESSION_SECRET).update(p).digest("base64url")}`;
};

test("a valid cookie is the answer, and nothing is re-issued", async () => {
  const j = jar(S.sign("sam@zennify.com", "AE", "Sam"));
  const s = await requestSession(req(null), j);
  assert.equal(s.email, "sam@zennify.com");
  assert.equal(j._set.length, 0);
});

test("a lapsed cookie is re-established from the IAP assertion, role re-read, cookie re-issued", async () => {
  me = { email: "sam@zennify.com", role: "ANALYST", is_active: true, source: "users" };
  const j = jar(lapsed("sam@zennify.com", "AE"));
  const s = await requestSession(req(mint("sam@zennify.com")), j);
  assert.deepEqual([s.email, s.role], ["sam@zennify.com", "ANALYST"], "the role is the users table's, not the stale cookie's");
  assert.equal(j._set.length, 1, "the cookie was not re-issued");
  const fresh = S.verify(j._set[0][1]);
  assert.ok(fresh && fresh.role === "ANALYST" && fresh.exp > Date.now() / 1000 + 7 * 3600);
});

test("the owner floor is an Admin when its cookie lapses", async () => {
  const j = jar(lapsed("owner@zennify.com", "ADMIN"));
  const s = await requestSession(req(mint("owner@zennify.com")), j);
  assert.equal(s.role, "ADMIN");
});

test("nothing else re-establishes a session", async () => {
  me = { email: "sam@zennify.com", role: "ADMIN", is_active: false, source: "users" };
  assert.equal(await requestSession(req(mint("sam@zennify.com")), jar(lapsed("sam@zennify.com", "ADMIN"))), null,
               "a deactivated account came back in");
  me = { email: "sam@zennify.com", role: "AE", is_active: true, source: "users" };
  assert.equal(await requestSession(req(null), jar(null)), null, "no cookie and no assertion");
  assert.equal(await requestSession(req(mint("sam@zennify.com").slice(0, -4) + "AAAA"), jar(null)), null, "a forged assertion");
  assert.equal(await requestSession(req(mint("x@gmail.com")), jar(null)), null, "an outside domain");
  assert.equal(await requestSession(req(mint("sam@zennify.com", { aud: "/projects/1/locations/x/services/other" })), jar(null)), null,
               "an assertion minted for another service");
});

test("every API route that reads the session asks requestSession", () => {
  const fs = require("node:fs"), path = require("node:path");
  const routes = ["admin/users", "admin/usage", "admin/share-links", "admin/scan",
                  "entity/[display_id]/[page]", "entity/[display_id]/insights/[ic_id]/annotation"];
  for (const r of routes) {
    const src = fs.readFileSync(path.join(__dirname, "..", "app", "api", r, "route.js"), "utf8");
    assert.match(src, /await requestSession\(req, cookies\(\)\)|await admin\(req\)/, `${r} does not use requestSession`);
    assert.doesNotMatch(src, /verify\(cookies\(\)/, `${r} still reads the cookie alone`);
  }
});
