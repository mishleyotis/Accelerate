/* Role resolution (lib/roles.js): the users table is the grant, read through
 * svc_api /v1/me with the IAP assertion the API verifies itself (owner
 * adjudication 2026-10-07). The deploy-time lists are a floor and an outage
 * fallback, never a ceiling. */
const test = require("node:test");
const assert = require("node:assert");
const R = require("../lib/roles.js");

const ENV = { API_URL: "https://api.test", ADMIN_EMAILS: "owner@zennify.com", ANALYST_EMAILS: "ana@zennify.com" };
function withEnv(fn) {
  return async () => {
    const saved = {};
    for (const k of Object.keys(ENV)) { saved[k] = process.env[k]; process.env[k] = ENV[k]; }
    try { await fn(); } finally { for (const k of Object.keys(ENV)) { if (saved[k] === undefined) delete process.env[k]; else process.env[k] = saved[k]; } }
  };
}
function api(body, status = 200) {
  const calls = [];
  const fetchImpl = async (url, opts) => {
    calls.push({ url: String(url), opts });
    return { ok: status === 200, status, json: async () => body };
  };
  return { fetchImpl, calls };
}

test("the owner floor is Admin without asking the API", withEnv(async () => {
  const { fetchImpl, calls } = api({});
  assert.deepEqual(await R.resolveAccess("Owner@zennify.com", "jwt", { fetchImpl }),
                   { role: "ADMIN", active: true, source: "owner_floor" });
  assert.equal(calls.length, 0);
}));

test("the users table decides the role and the active flag", withEnv(async () => {
  let { fetchImpl, calls } = api({ email: "sam@zennify.com", role: "ANALYST", is_active: true, source: "users" });
  assert.deepEqual(await R.resolveAccess("sam@zennify.com", "jwt", { fetchImpl }),
                   { role: "ANALYST", active: true, source: "users" });
  assert.equal(calls[0].url, "https://api.test/v1/me");
  assert.equal(calls[0].opts.method, "POST", "the read also enrols the caller");
  assert.equal(calls[0].opts.headers["x-goog-iap-jwt-assertion"], "jwt", "the assertion is forwarded");
  ({ fetchImpl } = api({ email: "sam@zennify.com", role: "ADMIN", is_active: false, source: "users" }));
  assert.equal((await R.resolveAccess("sam@zennify.com", "jwt", { fetchImpl })).active, false);
}));

test("no users row keeps the deploy-time grant", withEnv(async () => {
  const { fetchImpl } = api({ email: "ana@zennify.com", role: "AE", is_active: true, source: "default", known: false });
  assert.deepEqual(await R.resolveAccess("ana@zennify.com", "jwt", { fetchImpl }),
                   { role: "ANALYST", active: true, source: "default" });
}));

test("an answer about somebody else, or an outage, falls back to the deploy grant", withEnv(async () => {
  let { fetchImpl } = api({ email: "other@zennify.com", role: "ADMIN", is_active: true });
  assert.deepEqual(await R.resolveAccess("sam@zennify.com", "jwt", { fetchImpl }),
                   { role: "AE", active: true, source: "deploy" });
  ({ fetchImpl } = api({ error: "x" }, 503));
  assert.equal((await R.resolveAccess("ana@zennify.com", "jwt", { fetchImpl })).role, "ANALYST");
  assert.equal((await R.resolveAccess("sam@zennify.com", null, { fetchImpl })).source, "deploy",
               "no assertion, no lookup");
}));

test("an api older than enrolment (405) is read through its GET", withEnv(async () => {
  const calls = [];
  const fetchImpl = async (url, opts) => {
    calls.push(opts.method || "GET");
    if (opts.method === "POST") return { ok: false, status: 405, json: async () => ({}) };
    return { ok: true, status: 200, json: async () => ({ email: "sam@zennify.com", role: "ADMIN", is_active: true, source: "users" }) };
  };
  assert.equal((await R.resolveAccess("sam@zennify.com", "jwt", { fetchImpl })).role, "ADMIN");
  assert.deepEqual(calls, ["POST", "GET"]);
}));

test("a deactivated account sees a plain statement", () => {
  const html = R.deactivatedHtml("sam@zennify.com<script>");
  assert.match(html, /Access deactivated/);
  assert.ok(!html.includes("<script>"));
});
