// Usage telemetry — who used the app, where, and for how long.
//
// Every usage event is ONE structured line on stdout. Cloud Run parses a
// single-line JSON write into jsonPayload, and a log sink (infra/deploy.sh,
// "usage telemetry") routes the lines carrying `usage_v` into the BigQuery
// dataset the admin Usage analytics page reads. Nothing here writes to the
// application database: invariant 2 keeps the API's writes to annotations
// and alert actions, and the Backend Schema has no usage table.
//
// Identity is the SESSION's, never the body's. A beacon may say where the
// browser was and for how long; who it was, and with what grant, comes from
// the verified cookie (lib/session.js) — the same rule the annotation route
// follows for its actor.
//
// The vocabulary is closed. Page keys are derived here from the hash path
// rather than accepted from the client, so the analytics read one stable set
// of names however the router changes.

import { effectiveRole } from "./identity.js";

export const USAGE_V = 1;

// Event types the browser may send. Server-side events (doc_load,
// client_open, and the insight_review feature) are emitted by the routes
// that observe them and are never accepted from a beacon.
export const BEACON_TYPES = new Set(["page_view", "heartbeat", "feature"]);

// Feature actions the browser may report.
export const FEATURES = new Set([
  "evidence",        // an evidence drawer opened
  "insight",         // an insight-card modal opened
  "intelligence",    // the Intelligence panel opened
  "client_link",     // a client link copied
]);

// The longest single dwell a beacon may claim: a tab left visible over lunch
// is real time on page, a day is not.
export const MAX_DWELL_MS = 4 * 60 * 60 * 1000;
const MAX_BATCH = 20;
const MAX_BODY_BYTES = 8192;
const SID = /^[A-Za-z0-9_-]{8,40}$/;
const PATH = /^\/[A-Za-z0-9/_.~-]{0,199}$/;

// The hash path → { page, client_id }. Unknown paths are "other" rather than
// dropped, so a route added later shows up as a gap in the vocabulary instead
// of vanishing from the totals.
const GLOBAL_PAGES = {
  "/": "dashboard", "": "dashboard", "/clients": "clients",
  "/alerts": "alerts", "/prospecting": "prospecting", "/login": "login",
};
const CLIENT_TABS = new Set(["overview", "insights", "heatmap", "platform",
  "context", "techstack", "health", "runs"]);

export function pageOf(path) {
  const p = String(path || "").split("?")[0];
  if (p in GLOBAL_PAGES) return { page: GLOBAL_PAGES[p], client_id: null };
  const m = p.match(/^\/clients\/([^/]+)(?:\/([^/]+))?/);
  if (m) {
    const tab = m[2] || "overview";
    return { page: CLIENT_TABS.has(tab) ? tab : "other", client_id: m[1] };
  }
  if (p === "/admin/usage") return { page: "admin_usage", client_id: null };
  if (p === "/admin" || p.startsWith("/admin/")) return { page: "admin", client_id: null };
  return { page: "other", client_id: null };
}

// "Desktop · Chrome" from a user-agent string. Coarse on purpose: the page
// shows which surfaces people read on, not a fingerprint.
export function deviceOf(ua) {
  const s = String(ua || "");
  const form = /iPad|Tablet/i.test(s) ? "Tablet"
    : /Mobile|iPhone|Android/i.test(s) ? "Mobile" : "Desktop";
  const browser = /Edg\//.test(s) ? "Edge"
    : /Chrome\//.test(s) ? "Chrome"
    : /Firefox\//.test(s) ? "Firefox"
    : /Safari\//.test(s) ? "Safari" : "Other";
  return `${form} · ${browser}`;
}

// The one line. `fields` is already validated; identity comes from `session`.
export function usageLine(type, session, fields = {}, now = new Date()) {
  return {
    severity: "INFO",
    message: `usage ${type}`,
    usage_v: USAGE_V,
    usage: {
      type,
      at: now.toISOString(),
      email: session.email,
      role: session.role,
      ...fields,
    },
  };
}

export function logUsage(type, session, fields, now) {
  if (!session || !session.email) return;
  try {
    process.stdout.write(JSON.stringify(usageLine(type, session, fields, now)) + "\n");
  } catch {
    // Telemetry never fails a request.
  }
}

// One beacon event → the fields to log, or { error }.
export function parseEvent(raw, session, ua, now = new Date()) {
  if (!raw || typeof raw !== "object") return { error: "event_not_object" };
  const type = raw.type;
  if (!BEACON_TYPES.has(type)) return { error: "unknown_type" };
  if (typeof raw.sid !== "string" || !SID.test(raw.sid)) return { error: "bad_sid" };
  if (typeof raw.path !== "string" || !PATH.test(raw.path.split("?")[0])) {
    return { error: "bad_path" };
  }
  const { page, client_id } = pageOf(raw.path);
  const out = {
    sid: raw.sid, page, client_id,
    path: raw.path.split("?")[0],
    audience: raw.audience === "customer" ? "customer" : "internal",
    // The acting-as role can only narrow the grant (lib/identity).
    acting_role: effectiveRole(session.role, raw.acting_role),
    client_link: raw.client_link === true,
    device: deviceOf(ua),
  };
  if (type === "page_view") {
    const d = raw.dwell_ms;
    if (!Number.isInteger(d) || d < 0 || d > MAX_DWELL_MS) return { error: "bad_dwell" };
    out.dwell_ms = d;
    // A continuation is the same visit resumed after the tab was hidden:
    // its time counts, it is not a second view.
    out.cont = raw.cont === true;
    // entered_at is the browser's clock; kept only when plausible (the last
    // twelve hours), otherwise null — never a guess.
    const t = typeof raw.entered_at === "string" ? Date.parse(raw.entered_at) : NaN;
    out.entered_at = Number.isFinite(t) && t <= now.getTime() + 5 * 60 * 1000
      && t >= now.getTime() - 12 * 60 * 60 * 1000 ? new Date(t).toISOString() : null;
  }
  if (type === "feature") {
    if (!FEATURES.has(raw.feature)) return { error: "unknown_feature" };
    out.feature = raw.feature;
  }
  return { type, fields: out };
}

// A whole beacon body → { events: [{type, fields}], rejected }.
export function parseBeacon(text, session, ua, now = new Date()) {
  if (typeof text !== "string" || text.length > MAX_BODY_BYTES) {
    return { error: "body_too_large" };
  }
  let body;
  try { body = JSON.parse(text); } catch { return { error: "malformed_body" }; }
  const list = Array.isArray(body && body.events) ? body.events : [body];
  if (list.length === 0 || list.length > MAX_BATCH) return { error: "bad_batch" };
  const events = [];
  let rejected = 0;
  for (const raw of list) {
    const r = parseEvent(raw, session, ua, now);
    if (r.error) rejected += 1; else events.push(r);
  }
  return { events, rejected };
}
