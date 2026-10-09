// The read half of usage telemetry: Admin › Usage analytics reads the
// BigQuery dataset the dmai-usage log sink fills (infra/deploy.sh), as the
// dmai-web service account. Read-only, ADMIN-only (app/api/admin/usage).
//
// Every state the store can be in is a state the page renders by name:
//   not_configured  USAGE_DATASET / GCP_PROJECT unset on this deployment
//   not_recording   the dataset does not exist yet (the sink was never created)
//   ok + awaiting_first_event
//                   the dataset exists and no usage line has arrived since the
//                   sink was created: the page renders its layout at zero
//   forbidden       the web service account lacks its BigQuery grants
//   error           anything else, with BigQuery's own message
// None of them renders as an empty chart: "nobody used the app" and "we are
// not measuring" are different facts.
//
// Columns are read through TO_JSON_STRING(jsonPayload.usage) rather than by
// name. The sink creates a column only when a line carrying that field
// arrives, so a query naming `feature` before anyone opened a drawer would
// fail; the JSON path answers null instead.

const IDENT = /^[A-Za-z0-9_-]+$/;
const DS_IDENT = /^[A-Za-z0-9_]+$/;

// The wire row, in order. Arrays rather than objects: a 90-day view carries
// two periods of page views, and the field names would be most of the bytes.
// Client-link fields ride at the end (lib/usage LINK_EVENTS): the link a line
// is about, how a reader was admitted, and the address a refusal turned away.
export const WIRE_FIELDS = ["t", "type", "email", "role", "sid", "page", "client_id",
  "dwell_ms", "cont", "feature", "device", "entered_at", "audience", "acting_role",
  "link_jti", "method", "attempted_email", "reason"];

// The wire row of one generated link (linksSql).
export const LINK_FIELDS = ["t", "by", "by_role", "jti", "client_id", "run_id",
  "recipients", "domains", "expires_at"];

export const RANGES = [7, 14, 30, 90];
const MAX_ROWS = 200000;

export function usageConfig(env = process.env) {
  const project = env.GCP_PROJECT;
  const dataset = env.USAGE_DATASET;
  const table = env.USAGE_TABLE || "run_googleapis_com_stdout";
  if (!project || !dataset) return null;
  if (!IDENT.test(project) || !DS_IDENT.test(dataset) || !DS_IDENT.test(table)) return null;
  return { project, dataset, table, location: env.GCP_REGION || "us-central1" };
}

const J = (f) => `JSON_VALUE(u, '$.${f}')`;

// Page views, features and server events for the window (two periods, so the
// page can compare); heartbeats only from the last ten minutes — they exist to
// say who is live, and over a quarter they would be most of the rows.
export function eventsSql(cfg) {
  const t = `\`${cfg.project}.${cfg.dataset}.${cfg.table}\``;
  return `WITH e AS (
  SELECT timestamp, TO_JSON_STRING(jsonPayload.usage) AS u FROM ${t}
  WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @days DAY)
)
SELECT FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%E3SZ', timestamp) AS t,
       ${J("type")} AS type, LOWER(${J("email")}) AS email, ${J("role")} AS role,
       ${J("sid")} AS sid, ${J("page")} AS page, ${J("client_id")} AS client_id,
       SAFE_CAST(${J("dwell_ms")} AS INT64) AS dwell_ms,
       SAFE_CAST(${J("cont")} AS BOOL) AS cont, ${J("feature")} AS feature,
       ${J("device")} AS device, ${J("entered_at")} AS entered_at,
       ${J("audience")} AS audience, ${J("acting_role")} AS acting_role,
       ${J("link_jti")} AS link_jti, ${J("method")} AS method,
       LOWER(${J("attempted_email")}) AS attempted_email, ${J("reason")} AS reason
FROM e
WHERE ${J("type")} != 'heartbeat'
   OR timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 10 MINUTE)
ORDER BY timestamp
LIMIT ${MAX_ROWS + 1}`;
}

// Last seen per person over everything retained, and when recording began.
// `client_only` marks an address seen only through a client link (role
// CLIENT): such a person is a client recipient, never a Zennify user, and the
// Users & roles card must not offer them a role.
export function lastSeenSql(cfg) {
  const t = `\`${cfg.project}.${cfg.dataset}.${cfg.table}\``;
  return `SELECT LOWER(JSON_VALUE(TO_JSON_STRING(jsonPayload.usage), '$.email')) AS email,
       FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%E3SZ', MAX(timestamp)) AS last,
       FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%E3SZ', MIN(timestamp)) AS first,
       LOGICAL_AND(IFNULL(JSON_VALUE(TO_JSON_STRING(jsonPayload.usage), '$.role'), '') = 'CLIENT') AS client_only
FROM ${t}
GROUP BY email`;
}

// Every client link generated, over everything retained — not just the range:
// a link shared two months ago still names who may open it, and a recipient
// who never has is "No activity yet", not absent.
export function linksSql(cfg) {
  const t = `\`${cfg.project}.${cfg.dataset}.${cfg.table}\``;
  return `WITH e AS (
  SELECT timestamp, TO_JSON_STRING(jsonPayload.usage) AS u FROM ${t}
)
SELECT FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%E3SZ', timestamp) AS t,
       LOWER(${J("email")}) AS minted_by, ${J("role")} AS minted_by_role, ${J("link_jti")} AS jti,
       ${J("client_id")} AS client_id, ${J("run_id")} AS run_id,
       TO_JSON_STRING(JSON_VALUE_ARRAY(u, '$.recipients')) AS recipients,
       TO_JSON_STRING(JSON_VALUE_ARRAY(u, '$.domains')) AS domains,
       ${J("expires_at")} AS expires_at
FROM e
WHERE ${J("type")} = 'link_minted'
ORDER BY timestamp
LIMIT 5000`;
}

// '["a@b.com"]' (JSON_VALUE_ARRAY, as JSON text) → ["a@b.com"]; never throws.
export function jsonList(v) {
  try {
    const a = JSON.parse(v || "[]");
    return Array.isArray(a) ? a.map((x) => { try { return JSON.parse(x); } catch { return x; } })
      .filter((x) => typeof x === "string" && x).map((x) => x.toLowerCase()) : [];
  } catch { return []; }
}

// BigQuery's REST rows ({f:[{v}]}) → arrays in schema order.
export function rowsOf(resp) {
  return (resp.rows || []).map((r) => (r.f || []).map((c) => (c ? c.v : null)));
}

// A BigQuery error → one of the named states.
export function classifyError(status, message) {
  const m = String(message || "");
  if (status === 404 || /Not found: (Table|Dataset)/i.test(m)) return "not_recording";
  if (status === 403 || /Access Denied|permission/i.test(m)) return "forbidden";
  return "error";
}

async function token(fetchImpl) {
  if (process.env.BQ_ACCESS_TOKEN) return process.env.BQ_ACCESS_TOKEN;  // local QA only
  const t = await fetchImpl(
    "http://metadata.google.internal/computeMetadata/v1/instance/" +
      "service-accounts/default/token?scopes=" +
      encodeURIComponent("https://www.googleapis.com/auth/cloud-platform"),
    { headers: { "Metadata-Flavor": "Google" }, cache: "no-store" });
  if (!t.ok) throw Object.assign(new Error(`metadata token ${t.status}`), { state: "error" });
  return (await t.json()).access_token;
}

// Run one query to completion, following pages. Throws { state, message }.
export async function runQuery(cfg, sql, params, fetchImpl = fetch) {
  const tok = await token(fetchImpl);
  const auth = { Authorization: `Bearer ${tok}`, "content-type": "application/json" };
  const base = `https://bigquery.googleapis.com/bigquery/v2/projects/${cfg.project}`;
  const fail = async (r) => {
    const body = await r.json().catch(() => ({}));
    const message = (body.error && body.error.message) || `BigQuery ${r.status}`;
    throw Object.assign(new Error(message), { state: classifyError(r.status, message) });
  };
  let r = await fetchImpl(`${base}/queries`, {
    method: "POST", headers: auth, cache: "no-store",
    body: JSON.stringify({
      query: sql, useLegacySql: false, location: cfg.location,
      parameterMode: "NAMED", timeoutMs: 25000, maxResults: 50000,
      queryParameters: Object.entries(params || {}).map(([name, value]) => ({
        name, parameterType: { type: "INT64" }, parameterValue: { value: String(value) },
      })),
    }),
  });
  if (!r.ok) await fail(r);
  let resp = await r.json();
  const rows = rowsOf(resp);
  const job = resp.jobReference || {};
  let pages = 0;
  while ((!resp.jobComplete || resp.pageToken) && pages < 40) {
    pages += 1;
    const q = new URLSearchParams({ location: job.location || cfg.location,
                                    timeoutMs: "25000", maxResults: "50000" });
    if (resp.pageToken) q.set("pageToken", resp.pageToken);
    r = await fetchImpl(`${base}/queries/${encodeURIComponent(job.jobId)}?${q}`,
                        { headers: auth, cache: "no-store" });
    if (!r.ok) await fail(r);
    resp = await r.json();
    if (resp.jobComplete) rows.push(...rowsOf(resp));
  }
  if (!resp.jobComplete) {
    throw Object.assign(new Error("query did not finish in time"), { state: "error" });
  }
  return rows;
}

// The endpoint's whole answer for a range.
export async function readUsage(rangeDays, { env = process.env, fetchImpl = fetch,
                                             now = new Date() } = {}) {
  const base = { range_days: rangeDays, generated_at: now.toISOString(), fields: WIRE_FIELDS,
                 link_fields: LINK_FIELDS };
  const cfg = usageConfig(env);
  if (!cfg) return { ...base, status: "not_configured" };
  try {
    const [events, seen, minted] = await Promise.all([
      runQuery(cfg, eventsSql(cfg), { days: rangeDays * 2 + 1 }, fetchImpl),
      runQuery(cfg, lastSeenSql(cfg), {}, fetchImpl),
      runQuery(cfg, linksSql(cfg), {}, fetchImpl),
    ]);
    const truncated = events.length > MAX_ROWS;
    const last_seen = {};
    const client_only = [];
    let recording_since = null;
    for (const [email, last, first, clientOnly] of seen) {
      if (email) last_seen[email] = last;
      if (email && (clientOnly === true || clientOnly === "true")) client_only.push(email);
      if (first && (!recording_since || first < recording_since)) recording_since = first;
    }
    const links = minted.map(([t, by, by_role, jti, client_id, run_id, rec, dom, expires_at]) =>
      [t, by, by_role, jti, client_id, run_id, jsonList(rec), jsonList(dom), expires_at]);
    const wire = events.slice(0, MAX_ROWS).map((r) => r.map((v, i) =>
      i === 7 ? (v == null ? null : Number(v)) : i === 8 ? (v == null ? null : v === "true") : v));
    return { ...base, status: "ok", recording_since, last_seen, client_only, links, truncated,
             events: wire };
  } catch (e) {
    const d = await diagnose(cfg, e, fetchImpl).catch(() => null);
    if (d && d.status === "ok") {
      // The sink and its grants are in place and nothing has arrived yet:
      // the page renders its full layout at zero, and says it is waiting.
      return { ...base, status: "ok", awaiting_first_event: true, recording_since: null,
               last_seen: {}, client_only: [], links: [], truncated: false, events: [] };
    }
    return { ...base, status: (d && d.status) || e.state || "error",
             detail: (d && d.detail) || String(e.message || e).slice(0, 300) };
  }
}

// BigQuery answers a query on a missing dataset, a missing table and a missing
// grant with the same "Access Denied ... or perhaps it does not exist". The
// metadata reads tell them apart, so the page names the one step that is
// actually missing rather than guessing.
export async function diagnose(cfg, err, fetchImpl = fetch) {
  const tok = await token(fetchImpl);
  const base = `https://bigquery.googleapis.com/bigquery/v2/projects/${cfg.project}/datasets/${cfg.dataset}`;
  const get = (u) => fetchImpl(u, { headers: { Authorization: `Bearer ${tok}` }, cache: "no-store" });
  const ds = await get(base);
  if (ds.status === 404) {
    return { status: "not_recording", detail: `Dataset ${cfg.dataset} does not exist yet: the deploy creates it with the dmai-usage log sink.` };
  }
  if (ds.status === 403) {
    return { status: "forbidden", detail: `dmai-web cannot read dataset ${cfg.dataset} (bigquery.dataViewer on the dataset is missing).` };
  }
  if (!ds.ok) return null;
  const tb = await get(`${base}/tables/${cfg.table}`);
  if (tb.status === 404) return { status: "ok" };
  if (tb.ok && err && err.state === "forbidden") {
    return { status: "forbidden", detail: "dmai-web can read the dataset but cannot run queries (roles/bigquery.jobUser on the project is missing)." };
  }
  return null;
}
