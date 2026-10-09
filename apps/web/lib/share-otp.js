// One-time sign-in links for client share links, through Google Cloud
// Identity Platform (owner, 2026-10-07: "use a service already integrated
// with Google Cloud Run" — no mail provider, no third-party key). Since
// 2026-10-09 this is the FALLBACK: when the colleague's own Gmail can
// send (lib/share-mailer), that email carries the app's own
// code instead, valid for the link's days.
//
// Google sends the email and owns the code: `sendOobCode` (EMAIL_SIGNIN)
// mails the address a single-use link; `signInWithEmailLink` redeems the
// code from that link and answers with the address it was issued to. The
// only credential is the project's Identity Platform API key, which
// identifies the project and is restricted to identitytoolkit.googleapis.com
// (infra/deploy.sh). The share service never sees a password and stores no
// code: Google expires and burns it.
//
// IDENTITY_TOOLKIT_URL exists for the local end-to-end harness, which stubs
// these two calls; production never sets it.
const BASE = () => (process.env.IDENTITY_TOOLKIT_URL || "https://identitytoolkit.googleapis.com").replace(/\/+$/, "");

async function call(method, body) {
  const key = process.env.SHARE_IDP_API_KEY;
  if (!key) return { ok: false, error: "not_configured" };
  try {
    const r = await fetch(`${BASE()}/v1/accounts:${method}?key=${encodeURIComponent(key)}`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify(body), cache: "no-store" });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) return { ok: false, error: (j.error && j.error.message) || `http_${r.status}` };
    return { ok: true, body: j };
  } catch {
    return { ok: false, error: "unreachable" };
  }
}

// Ask Google to email `email` a single-use link back to `continueUrl`.
export function sendSignInLink(email, continueUrl) {
  return call("sendOobCode", { requestType: "EMAIL_SIGNIN", email,
                               continueUrl, canHandleCodeInApp: true });
}

// Redeem the code. Succeeds only for the address the code was issued to,
// once, before it expires; returns that address as Google states it.
export async function completeSignIn(email, oobCode) {
  const r = await call("signInWithEmailLink", { email, oobCode });
  if (!r.ok) return r;
  return { ok: true, email: String(r.body.email || "").toLowerCase() };
}

/* A sender rate limit per link and address, per instance: the gate can only
   mail allowlisted addresses, and this keeps even those from being flooded.
   Identity Platform enforces its own project quota on top. */
const sent = new Map();
export function mayResend(jti, email, now = Date.now(), limit = 5, windowMs = 15 * 60e3) {
  const k = `${jti}|${email}`;
  const recent = (sent.get(k) || []).filter((t) => now - t < windowMs);
  if (recent.length >= limit) { sent.set(k, recent); return false; }
  recent.push(now);
  sent.set(k, recent);
  if (sent.size > 5000) sent.clear();
  return true;
}
