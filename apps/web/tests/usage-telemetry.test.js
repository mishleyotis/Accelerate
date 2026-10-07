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
