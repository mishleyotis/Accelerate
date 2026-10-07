// The read half of usage telemetry: Admin › Usage analytics reads the
// BigQuery dataset the dmai-usage log sink fills (infra/deploy.sh), as the
// dmai-web service account. Read-only, ADMIN-only (app/api/admin/usage).
//
// Every state the store can be in is a state the page renders by name:
//   not_configured  USAGE_DATASET / GCP_PROJECT unset on this deployment
//   not_recording   the dataset or its table does not exist yet — the sink has
//                   not been created, or no usage line has arrived since it was
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
export const WIRE_FIELDS = ["t", "type", "email", "role", "sid", "page", "client_id",
  "dwell_ms", "cont", "feature", "device", "entered_at", "audience", "acting_role"];

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
       ${J("audience")} AS audience, ${J("acting_role")} AS acting_role
FROM e
WHERE ${J("type")} != 'heartbeat'
   OR timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 10 MINUTE)
ORDER BY timestamp
LIMIT ${MAX_ROWS + 1}`;
}

// Last seen per person over everything retained, and when recording began.
export function lastSeenSql(cfg) {
  const t = `\`${cfg.project}.${cfg.dataset}.${cfg.table}\``;
  return `SELECT LOWER(JSON_VALUE(TO_JSON_STRING(jsonPayload.usage), '$.email')) AS email,
       FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%E3SZ', MAX(timestamp)) AS last,
       FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%E3SZ', MIN(timestamp)) AS first
FROM ${t}
GROUP BY email`;
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
  const base = { range_days: rangeDays, generated_at: now.toISOString(), fields: WIRE_FIELDS };
  const cfg = usageConfig(env);
  if (!cfg) return { ...base, status: "not_configured" };
  try {
    const [events, seen] = await Promise.all([
      runQuery(cfg, eventsSql(cfg), { days: rangeDays * 2 + 1 }, fetchImpl),
      runQuery(cfg, lastSeenSql(cfg), {}, fetchImpl),
    ]);
    const truncated = events.length > MAX_ROWS;
    const last_seen = {};
    let recording_since = null;
    for (const [email, last, first] of seen) {
      if (email) last_seen[email] = last;
      if (first && (!recording_since || first < recording_since)) recording_since = first;
    }
    const wire = events.slice(0, MAX_ROWS).map((r) => r.map((v, i) =>
      i === 7 ? (v == null ? null : Number(v)) : i === 8 ? (v == null ? null : v === "true") : v));
    return { ...base, status: "ok", recording_since, last_seen, truncated, events: wire };
  } catch (e) {
    return { ...base, status: e.state || "error", detail: String(e.message || e).slice(0, 300) };
  }
}
