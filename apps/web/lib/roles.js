// Role resolution against the users table (svc_api GET /v1/me) — owner
// adjudication 2026-10-07: grants live in the schema's `users` table and an
// Admin manages them from Admin › Users & roles (POST /v1/admin/users).
//
// Resolved on sign-in AND on every document load, so a change an Admin makes
// lands on that person's next page load, and a deactivation shuts the door
// on it. The call is POST /v1/me, which also ENROLS the caller: a first visit
// gets a users row with its allocated role (owner floor ADMIN, ANALYST_EMAILS
// ANALYST, else AE), so the Admin's roster lists everyone who has opened the
// app, and last_seen_at says when they were last here. The identity sent is the IAP assertion the API verifies itself
// (dma_api.identity); this module only forwards it.
//
// The deploy-time lists stay as a floor and a fallback, never a ceiling:
//   ADMIN_EMAILS  always an active Admin (nobody can remove the last way in)
//   no users row  the deploy-time grant (ANALYST_EMAILS, else AE)
//   API unreachable or unconfigured → the deploy-time grant (lib/identity),
//   so an outage of svc_api degrades to the old behaviour instead of locking
//   everyone out of a page that would show nothing anyway.
import { grantedRole } from "./identity.js";
import { ASSERTION_HEADER, upstreamHeaders } from "./upstream.js";

function floor() {
  return (process.env.ADMIN_EMAILS || "").toLowerCase().split(",")
    .map((s) => s.trim()).filter(Boolean);
}

export async function resolveAccess(email, assertion, { fetchImpl = fetch } = {}) {
  const e = String(email || "").toLowerCase();
  const base = process.env.API_URL;
  if (floor().includes(e)) {
    // The owners are Admins whatever any row says, but they are still
    // enrolled and touched like everyone else, so the roster lists them with
    // a real "last active" and their own changes have a row to attribute.
    if (base && assertion) {
      try {
        const headers = await upstreamHeaders(base);
        headers[ASSERTION_HEADER] = assertion;
        await fetchImpl(`${base}/v1/me`, { method: "POST", headers, cache: "no-store" });
      } catch {}
    }
    return { role: "ADMIN", active: true, source: "owner_floor" };
  }
  if (!base || !assertion) return { role: grantedRole(e), active: true, source: "deploy" };
  try {
    const headers = await upstreamHeaders(base);
    headers[ASSERTION_HEADER] = assertion;
    let r = await fetchImpl(`${base}/v1/me`, { method: "POST", headers, cache: "no-store" });
    // An api older than enrolment answers 405; its read-only GET still holds.
    if (r.status === 405) r = await fetchImpl(`${base}/v1/me`, { headers, cache: "no-store" });
    if (!r.ok) return { role: grantedRole(e), active: true, source: "deploy" };
    const b = await r.json();
    if (String(b.email || "").toLowerCase() !== e) {
      return { role: grantedRole(e), active: true, source: "deploy" };
    }
    // No row yet: the deploy-time grant still applies, so nobody granted by
    // ANALYST_EMAILS before the users table took over loses access.
    if (b.source === "default" || b.known === false) {
      return { role: grantedRole(e), active: true, source: "default" };
    }
    const role = ["AE", "ANALYST", "ADMIN"].includes(b.role) ? b.role : "AE";
    return { role, active: b.is_active !== false, source: b.source || "users" };
  } catch {
    return { role: grantedRole(e), active: true, source: "deploy" };
  }
}

// What a deactivated account sees instead of the app: a plain statement,
// never a half-rendered shell.
export function deactivatedHtml(email) {
  const safe = String(email || "").replace(/[<>&"]/g, "");
  return `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DMA Insights</title><link rel="stylesheet" href="/proto/app.css"></head>
<body style="font-family:system-ui,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;background:#F6F8F8;color:#1E2B2C">
<div style="max-width:420px;padding:32px;text-align:center">
<h1 style="font-size:20px;font-weight:600;margin:0 0 8px">Access deactivated</h1>
<p style="font-size:14px;line-height:1.5;margin:0">${safe} no longer has access to DMA Insights. Ask an Admin to reactivate the account.</p>
</div></body></html>`;
}
