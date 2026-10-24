/* Usage telemetry — the write half (lib/usage.js) and the read half
 * (lib/usage-store.js).
 *
 * What is pinned here:
 *   · identity is the SESSION's, never the beacon body's — a body that names
 *     another email or claims ADMIN changes nothing
 *   · the vocabulary is closed: page keys are derived server-side from the
 *     hash path, feature names come from an allowlist, a dwell is bounded
 *   · one event is one single-line JSON write carrying `usage_v` — the field
 *     the dmai-usage log sink filters on (infra/deploy.sh)
 *   · every store state is a named state: not_configured / not_recording /
 *     forbidden / error — an absent table never reads as "zero usage"
 *   · columns are read through TO_JSON_STRING, so a field no event has carried
 *     yet answers null instead of failing the query
 */
const test = require("node:test");
const assert = require("node:assert");
const U = require("../lib/usage.js");
const S = require("../lib/usage-store.js");

const SESSION = { email: "ae.person@zennify.com", role: "AE", name: "Ae Person" };
const NOW = new Date("2026-10-07T15:00:00Z");
const ok = (extra) => ({ type: "page_view", sid: "abcdef123456", path: "/clients/golden-1/heatmap",
                         dwell_ms: 42000, entered_at: "2026-10-07T14:59:00Z", ...extra });

test("page keys are derived from the hash path, not accepted from the client", () => {
  assert.deepEqual(U.pageOf("/"), { page: "dashboard", client_id: null });
  assert.deepEqual(U.pageOf("/clients"), { page: "clients", client_id: null });
  assert.deepEqual(U.pageOf("/clients/golden-1"), { page: "overview", client_id: "golden-1" });
  assert.deepEqual(U.pageOf("/clients/golden-1/platform"), { page: "platform", client_id: "golden-1" });
  assert.deepEqual(U.pageOf("/clients/golden-1/nonsense"), { page: "other", client_id: "golden-1" });
  assert.deepEqual(U.pageOf("/admin/usage"), { page: "admin_usage", client_id: null });
  assert.deepEqual(U.pageOf("/admin"), { page: "admin", client_id: null });
  assert.deepEqual(U.pageOf("/somewhere-new"), { page: "other", client_id: null });
});

test("identity comes from the session; the body cannot name or escalate", () => {
  const r = U.parseEvent(ok({ email: "boss@zennify.com", role: "ADMIN", acting_role: "ADMIN" }),
                         SESSION, "Mozilla/5.0 Chrome/120", NOW);
  assert.equal(r.type, "page_view");
  assert.equal(r.fields.acting_role, "AE", "an AE asking to act as ADMIN is logged as AE");
  assert.ok(!("email" in r.fields) && !("role" in r.fields), "identity is not a beacon field");
  const line = U.usageLine(r.type, SESSION, r.fields, NOW);
  assert.equal(line.usage.email, SESSION.email);
  assert.equal(line.usage.role, "AE");
});

test("a valid page view keeps its page, client, dwell and a plausible entered_at", () => {
  const r = U.parseEvent(ok(), SESSION, "Mozilla/5.0 (Macintosh) Safari/605", NOW);
  assert.equal(r.fields.page, "heatmap");
  assert.equal(r.fields.client_id, "golden-1");
  assert.equal(r.fields.dwell_ms, 42000);
  assert.equal(r.fields.entered_at, "2026-10-07T14:59:00.000Z");
  assert.equal(r.fields.device, "Desktop · Safari");
  assert.equal(r.fields.cont, false);
});

test("an implausible browser clock is dropped to null, never guessed", () => {
  const r = U.parseEvent(ok({ entered_at: "2025-01-01T00:00:00Z" }), SESSION, "", NOW);
  assert.equal(r.fields.entered_at, null);
});

test("the vocabulary is closed", () => {
  for (const [bad, code] of [
    [{ type: "doc_load" }, "unknown_type"],            // server-only events
    [{ type: "client_open" }, "unknown_type"],
    [{ sid: "x" }, "bad_sid"],
    [{ path: "javascript:alert(1)" }, "bad_path"],
    [{ path: "/clients/<script>" }, "bad_path"],
    [{ dwell_ms: -1 }, "bad_dwell"],
    [{ dwell_ms: U.MAX_DWELL_MS + 1 }, "bad_dwell"],
    [{ dwell_ms: 1.5 }, "bad_dwell"],
    [{ type: "feature", feature: "export" }, "unknown_feature"],
  ]) {
    assert.equal(U.parseEvent(ok(bad), SESSION, "", NOW).error, code, JSON.stringify(bad));
  }
  for (const f of U.FEATURES) {
    assert.equal(U.parseEvent(ok({ type: "feature", feature: f }), SESSION, "", NOW).fields.feature, f);
  }
});

test("a beacon batch logs its valid events and counts the rest", () => {
  const body = JSON.stringify({ events: [ok(), ok({ sid: "no" }), ok({ type: "heartbeat" })] });
  const r = U.parseBeacon(body, SESSION, "", NOW);
  assert.equal(r.events.length, 2);
  assert.equal(r.rejected, 1);
  assert.equal(U.parseBeacon("{", SESSION, "", NOW).error, "malformed_body");
  assert.equal(U.parseBeacon("x".repeat(9000), SESSION, "", NOW).error, "body_too_large");
  assert.equal(U.parseBeacon(JSON.stringify({ events: Array(21).fill(ok()) }), SESSION, "", NOW).error,
               "bad_batch");
});

test("one event is one single-line JSON write carrying the sink's filter field", () => {
  const writes = [];
  const orig = process.stdout.write;
  process.stdout.write = (s) => { writes.push(s); return true; };
  try {
    U.logUsage("client_open", SESSION, { client_id: "golden-1" }, NOW);
    U.logUsage("client_open", null, {}, NOW);              // no session → nothing
  } finally { process.stdout.write = orig; }
  assert.equal(writes.length, 1);
  assert.ok(writes[0].endsWith("\n") && writes[0].indexOf("\n") === writes[0].length - 1);
  const j = JSON.parse(writes[0]);
  assert.equal(j.usage_v, 1, "infra/deploy.sh filters the sink on jsonPayload.usage_v=1");
  assert.equal(j.severity, "INFO");
  assert.equal(j.usage.type, "client_open");
  assert.equal(j.usage.at, NOW.toISOString());
});

test("the sink filter in deploy.sh is the field this module writes", () => {
  const fs = require("node:fs");
  const path = require("node:path");
  const deploy = fs.readFileSync(path.join(__dirname, "..", "..", "..", "infra", "deploy.sh"), "utf8");
  assert.match(deploy, /jsonPayload\.usage_v=1/);
  assert.match(deploy, /resource\.labels\.service_name="dmai-web"/);
  assert.match(deploy, /USAGE_FILTER='[^']*resource\.labels\.service_name="dmai-share"[^']*'/,
               "the client-link lines are written by dmai-share; a dmai-web-only sink never records them");
  assert.match(deploy, /USAGE_DATASET=\$\{USAGE_DATASET\}/, "the web service is told its dataset");
});

/* ── read half ─────────────────────────────────────────────────────── */

test("an unconfigured deployment says so rather than reading as zero", async () => {
  const r = await S.readUsage(30, { env: {}, fetchImpl: () => { throw new Error("no call"); } });
  assert.equal(r.status, "not_configured");
  assert.ok(!("events" in r));
});

test("identifiers are validated before they reach SQL", () => {
  assert.equal(S.usageConfig({ GCP_PROJECT: "p", USAGE_DATASET: "d; DROP" }), null);
  assert.equal(S.usageConfig({ GCP_PROJECT: "p`x", USAGE_DATASET: "d" }), null);
  assert.ok(S.usageConfig({ GCP_PROJECT: "digital-maturity-assessor", USAGE_DATASET: "dmai_usage" }));
});

test("the queries read through JSON paths and keep heartbeats to the last ten minutes", () => {
  const cfg = S.usageConfig({ GCP_PROJECT: "digital-maturity-assessor", USAGE_DATASET: "dmai_usage" });
  const sql = S.eventsSql(cfg);
  assert.match(sql, /TO_JSON_STRING\(jsonPayload\.usage\)/);
  assert.match(sql, /`digital-maturity-assessor\.dmai_usage\.run_googleapis_com_stdout`/);
  assert.match(sql, /!= 'heartbeat'[\s\S]*INTERVAL 10 MINUTE/);
  assert.match(sql, /INTERVAL @days DAY/);
  assert.match(S.lastSeenSql(cfg), /MAX\(timestamp\)[\s\S]*MIN\(timestamp\)/);
});

test("BigQuery errors become named states", () => {
  assert.equal(S.classifyError(404, "Not found: Table digital-maturity-assessor:dmai_usage.x"), "not_recording");
  assert.equal(S.classifyError(400, "Not found: Dataset digital-maturity-assessor:dmai_usage"), "not_recording");
  assert.equal(S.classifyError(403, "Access Denied: Table"), "forbidden");
  assert.equal(S.classifyError(500, "backend error"), "error");
});

function fakeBigQuery(responses) {
  const calls = [];
  const fetchImpl = async (url, opts) => {
    calls.push({ url: String(url), opts });
    if (String(url).includes("metadata.google.internal")) {
      return { ok: true, json: async () => ({ access_token: "tok" }) };
    }
    const body = opts && opts.body ? JSON.parse(opts.body) : null;
    const r = responses(String(url), body);
    return { ok: r.status === 200, status: r.status, json: async () => r.json };
  };
  return { fetchImpl, calls };
}
const ENV = { GCP_PROJECT: "digital-maturity-assessor", USAGE_DATASET: "dmai_usage" };

test("a missing table reads as not_recording", async () => {
  const { fetchImpl } = fakeBigQuery(() => ({ status: 404,
    json: { error: { message: "Not found: Table digital-maturity-assessor:dmai_usage.run_googleapis_com_stdout" } } }));
  const r = await S.readUsage(7, { env: ENV, fetchImpl });
  assert.equal(r.status, "not_recording");
});

// BigQuery answers a missing dataset, a missing table and a missing grant with
// one "Access Denied ... or perhaps it does not exist"; the metadata reads name
// which step is actually missing (the production message of 2026-10-07).
const DENIED = { status: 403, json: { error: { message:
  "Access Denied: Table digital-maturity-assessor:dmai_usage.run_googleapis_com_stdout: User does not have permission to query table digital-maturity-assessor:dmai_usage.run_googleapis_com_stdout, or perhaps it does not exist." } } };
function denied(ds, tb) {
  return fakeBigQuery((url) => /\/queries/.test(url) ? DENIED
    : /\/tables\//.test(url) ? { status: tb, json: {} } : { status: ds, json: {} });
}

test("the ambiguous Access Denied is diagnosed to the missing step", async () => {
  let r = await S.readUsage(7, { env: ENV, fetchImpl: denied(404, 404).fetchImpl });
  assert.equal(r.status, "not_recording");
  assert.match(r.detail, /Dataset dmai_usage does not exist/);
  r = await S.readUsage(7, { env: ENV, fetchImpl: denied(403, 403).fetchImpl });
  assert.equal(r.status, "forbidden");
  assert.match(r.detail, /dataViewer/);
  r = await S.readUsage(7, { env: ENV, fetchImpl: denied(200, 200).fetchImpl });
  assert.equal(r.status, "forbidden");
  assert.match(r.detail, /jobUser/);
});

test("a live sink with no event yet is ok at zero, flagged as awaiting", async () => {
  const r = await S.readUsage(7, { env: ENV, fetchImpl: denied(200, 404).fetchImpl });
  assert.equal(r.status, "ok");
  assert.equal(r.awaiting_first_event, true);
  assert.deepEqual(r.events, []);
  assert.deepEqual(r.last_seen, {});
});

test("rows come back typed, in wire order, with last-seen and recording-since", async () => {
  const { fetchImpl, calls } = fakeBigQuery((url, body) => {
    if (body && /GROUP BY email/.test(body.query)) {
      return { status: 200, json: { jobComplete: true, rows: [
        { f: [{ v: "a@zennify.com" }, { v: "2026-10-07T14:00:00.000Z" }, { v: "2026-09-01T09:00:00.000Z" }] }] } };
    }
    return { status: 200, json: { jobComplete: true, rows: [
      { f: ["2026-10-07T14:00:00.000Z", "page_view", "a@zennify.com", "AE", "abcdef123456", "overview",
            "golden-1", "42000", "false", null, "Desktop · Chrome", null, "internal", "AE"].map((v) => ({ v })) }] } };
  });
  const r = await S.readUsage(7, { env: ENV, fetchImpl });
  assert.equal(r.status, "ok");
  assert.deepEqual(r.fields, S.WIRE_FIELDS);
  assert.equal(r.events[0][7], 42000);
  assert.equal(r.events[0][8], false);
  assert.equal(r.last_seen["a@zennify.com"], "2026-10-07T14:00:00.000Z");
  assert.equal(r.recording_since, "2026-09-01T09:00:00.000Z");
  const q = calls.find((c) => c.opts && c.opts.body && /INTERVAL @days/.test(JSON.parse(c.opts.body).query));
  assert.equal(JSON.parse(q.opts.body).queryParameters[0].parameterValue.value, "15",
               "two periods plus today, so the page can compare");
});

/* Usage is measured from activity, not from sign-ins: most people stay signed
   in for days. A beacon whose 8-hour app cookie has lapsed still carries the
   IAP assertion Google puts on every request, and that is enough identity. */
test("the beacon falls back to the IAP assertion when the session cookie has lapsed", () => {
  const fs = require("node:fs");
  const path = require("node:path");
  const src = fs.readFileSync(path.join(__dirname, "..", "app", "api", "usage", "route.js"), "utf8");
  const cookieAt = src.indexOf("verify(cookies()");
  const iapAt = src.indexOf("verifyIapAssertion(req.headers.get(\"x-goog-iap-jwt-assertion\"))");
  assert.ok(cookieAt > 0 && iapAt > cookieAt, "cookie first, then the IAP assertion");
  assert.match(src, /domainOk\(iap\.email\)/, "the IAP fallback keeps the @zennify.com domain rule");
  assert.ok(!/not_signed_in/.test(src), "a lapsed sign-in is not a reason to drop usage");
});

test("usage surfaces speak of activity, never of sign-ins", () => {
  const fs = require("node:fs");
  const path = require("node:path");
  for (const f of ["pages-admin-usage.jsx", "pages-alerts-prospecting-admin.jsx"]) {
    const src = fs.readFileSync(path.join(__dirname, "..", "proto", f), "utf8")
      .replace(/\/\/.*$/gm, "").replace(/\/\*[\s\S]*?\*\//g, "");
    assert.ok(!/Never signed in|Who's signed in|sign-ins/.test(src), `${f} ties usage to sign-ins`);
    assert.ok(!/u\.signed_in/.test(src), `${f} reads the OIDC binding as activity`);
  }
});

/* ── client links (owner, 2026-10-09) ──────────────────────────────── */
const fs = require("node:fs");
const path = require("node:path");
const P = { jti: "linkAAAA0001", e: "golden-1", r: "run-1", exp: 1792771904 };

function captured(fn) {
  const real = process.stdout.write.bind(process.stdout);
  const out = [];
  process.stdout.write = (s) => { out.push(String(s)); return true; };
  try { fn(); } finally { process.stdout.write = real; }
  return out.map((s) => JSON.parse(s));
}

test("a client reader's beacon is logged as the admitted address, CLIENT, on this link only", () => {
  const session = U.clientSession("jane@bcu.com");
  const parsed = U.parseBeacon(JSON.stringify({ events: [ok({ email: "boss@zennify.com", role: "ADMIN",
    audience: "internal", acting_role: "ADMIN", path: "/clients/other-client/insights" })] }), session, "Chrome/1", NOW);
  const f = U.clientBeaconFields(parsed.events[0].fields, P);
  const [line] = captured(() => U.logUsage("page_view", session, f, NOW));
  assert.equal(line.usage_v, 1);
  assert.deepEqual([line.usage.email, line.usage.role, line.usage.audience, line.usage.acting_role, line.usage.client_link],
                   ["jane@bcu.com", "CLIENT", "customer", null, true]);
  assert.deepEqual([line.usage.link_jti, line.usage.client_id, line.usage.run_id], ["linkAAAA0001", "golden-1", "run-1"],
                   "the link's own client, whatever the path claimed");
});

test("a refused address is a link_refused line with no person behind it", () => {
  const [line] = captured(() => U.logLinkEvent("link_refused",
    U.linkFields(P, { attempted_email: "x@gmail.com", reason: "not_on_allowlist" }), NOW));
  assert.equal(line.usage.type, "link_refused");
  assert.equal(line.usage.email, null);
  assert.equal(line.usage.attempted_email, "x@gmail.com");
  assert.ok(U.LINK_EVENTS.has("link_refused") && !U.BEACON_TYPES.has("link_refused"), "never accepted from a beacon");
  for (const t of U.LINK_EVENTS) assert.ok(!U.BEACON_TYPES.has(t), t);
});

test("every client-link step writes its usage line", () => {
  const src = (f) => fs.readFileSync(path.join(__dirname, "..", f), "utf8");
  assert.match(src("app/api/share/route.js"), /logUsage\("link_minted", session, linkFields\(payload, \{\s*recipients: payload\.a\.m, domains: payload\.a\.d/);
  const access = src("app/s/[token]/access/route.js");
  assert.match(access, /logLinkEvent\("link_refused"/);
  assert.match(access, /logUsage\("link_otp_sent", clientSession\(email\)/);
  assert.match(access, /logUsage\("link_admit", clientSession\(email\), linkFields\(p, \{ method: "attest" \}\)\)/);
  const verify = src("app/s/[token]/verify/route.js");
  assert.match(verify, /logLinkEvent\("link_refused"/);
  assert.match(verify, /logUsage\("link_admit", clientSession\(email\), linkFields\(p, \{ method: "otp" \}\)\)/);
  assert.match(src("app/s/[token]/route.js"), /logUsage\("link_open", clientSession\(email\)/);
  const beacon = src("app/s/[token]/api/usage/route.js");
  assert.match(beacon, /readAccess\(p, cookieFrom\(req, accessCookieName\(p\)\)\)/, "identity is the admitted address");
  assert.match(beacon, /if \(!email\) return deny\(401/);
  assert.match(src("proto/usage-tracker.jsx"), /LIVE\.share && LIVE\.api_base \? `\$\{LIVE\.api_base\}\/usage`/,
               "a client link reports to its own route");
});

test("the store reads every generated link and marks client-only people", async () => {
  const { fetchImpl } = fakeBigQuery((url, body) => {
    const q = body ? body.query : "";
    if (/GROUP BY email/.test(q)) {
      return { status: 200, json: { jobComplete: true, rows: [
        { f: [{ v: "a@zennify.com" }, { v: "2026-10-07T14:00:00.000Z" }, { v: "2026-09-01T09:00:00.000Z" }, { v: "false" }] },
        { f: [{ v: "jane@bcu.com" }, { v: "2026-10-07T13:00:00.000Z" }, { v: "2026-10-06T09:00:00.000Z" }, { v: "true" }] }] } };
    }
    if (/= 'link_minted'/.test(q)) {
      return { status: 200, json: { jobComplete: true, rows: [{ f: ["2026-10-06T08:00:00.000Z", "a@zennify.com", "ADMIN",
        "linkAAAA0001", "golden-1", "run-1", '["jane@bcu.com","CFO@bcu.com"]', '["bcu.com"]', "2026-11-05T08:00:00.000Z"].map((v) => ({ v })) }] } };
    }
    return { status: 200, json: { jobComplete: true, rows: [] } };
  });
  const r = await S.readUsage(7, { env: ENV, fetchImpl });
  assert.equal(r.status, "ok");
  assert.deepEqual(r.link_fields, S.LINK_FIELDS);
  assert.deepEqual(r.links, [["2026-10-06T08:00:00.000Z", "a@zennify.com", "ADMIN", "linkAAAA0001", "golden-1", "run-1",
                              ["jane@bcu.com", "cfo@bcu.com"], ["bcu.com"], "2026-11-05T08:00:00.000Z"]]);
  assert.deepEqual(r.client_only, ["jane@bcu.com"]);
  assert.deepEqual(S.jsonList("not json"), []);
  assert.deepEqual(S.jsonList(null), []);
});

test("the links query reads every retained mint, through JSON paths, with no reserved alias", () => {
  const sql = S.linksSql({ project: "p", dataset: "d", table: "t" });
  assert.match(sql, /WHERE JSON_VALUE\(u, '\$\.type'\) = 'link_minted'/);
  assert.ok(!/INTERVAL/.test(sql), "a link shared months ago still names its recipients");
  assert.match(sql, /JSON_VALUE_ARRAY\(u, '\$\.recipients'\)/);
  assert.ok(!/\bAS by\b/i.test(sql), "BY is reserved in BigQuery");
  assert.match(S.lastSeenSql({ project: "p", dataset: "d", table: "t" }), /LOGICAL_AND\([\s\S]*'CLIENT'\) AS client_only/);
  assert.deepEqual(S.WIRE_FIELDS.slice(0, 14), ["t", "type", "email", "role", "sid", "page", "client_id",
    "dwell_ms", "cont", "feature", "device", "entered_at", "audience", "acting_role"], "existing positions never move");
});
