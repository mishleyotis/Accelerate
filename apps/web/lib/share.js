// Client share links — a signed, expiring capability for ONE client's
// dashboard, opened on the public `dmai-share` service with no Zennify login.
//
// Why a signature and not a session: the recipient is outside Zennify, so
// there is no identity to check — the link IS the authority, and the only
// things it may carry are what the person who minted it chose (which client,
// which run) and when it stops working. Everything else is fixed here, not
// in the token: the audience is always `customer`, the role always `AE`, and
// the pages are the client dashboard's own (SHARE_PAGES). A token cannot ask
// for more because there is no field in it to ask with.
//
// Ed25519, two keys, two services. The IAP-fronted `dmai-web` holds the
// PRIVATE key and mints; the public `dmai-share` holds only the PUBLIC key
// and verifies. A compromise of the internet-facing service therefore cannot
// mint a link — it can only read what a valid link already reads.
//
// Revocation: every token carries a `jti`. An ADMIN revokes a link, or removes
// one address or domain from it, on Admin › Client links (lib/share-ledger,
// effective within seconds). Break-glass, without the app: list the jti in
// infra/share-revoked.txt and redeploy; every link at once by rotating the
// key (a new version of dmai-share-signing-key + verify-key).
import crypto from "crypto";

export const TOKEN_VERSION = 1;
export const DEFAULT_DAYS = 30;
export const MAX_DAYS = 90;

// The reads a client link may make. The three client tabs' pages plus the two
// grain reads they draw on (the evidence drawer, the heatmap's cells). Every
// other page — platform, techstack, context, answers — is refused 403, which
// the SPA already renders as a withheld dashboard.
export const SHARE_PAGES = new Set(["overview", "insights", "heatmap",
                                    "evidence", "subcaps"]);

// The one switch that turns this image into the public share service. Set
// only on `dmai-share` by infra/deploy.sh; never on `dmai-web`.
export function shareMode() {
  return process.env.SHARE_MODE === "1";
}

// Response headers for anything the share service returns: never cached by
// an intermediary, never indexed, never framed, and the capability in the
// URL never leaks onward through a Referer header.
export const SHARE_HEADERS = {
  "cache-control": "no-store, private",
  "referrer-policy": "no-referrer",
  "x-robots-tag": "noindex, nofollow, noarchive",
  "x-frame-options": "DENY",
  "x-content-type-options": "nosniff",
  "content-security-policy":
    "frame-ancestors 'none'; base-uri 'none'; object-src 'none'; form-action 'self'",
};

const b64u = (buf) => Buffer.from(buf).toString("base64url");

function pem(name) {
  const v = process.env[name];
  if (!v) return null;
  // Secret Manager values and env files sometimes carry literal "\n".
  return v.includes("BEGIN") ? v.replace(/\\n/g, "\n") : null;
}

export function signingKey() {
  const p = pem("SHARE_SIGNING_KEY");
  try { return p ? crypto.createPrivateKey(p) : null; } catch { return null; }
}

export function verifyKey() {
  const p = pem("SHARE_VERIFY_KEY");
  try { return p ? crypto.createPublicKey(p) : null; } catch { return null; }
}

// Lowercase slugs and run ids only — a token field is interpolated into an
// API path, so it is validated at both ends rather than trusted.
const SLUG = /^[a-z0-9][a-z0-9-]{0,126}$/;
const RUN = /^[A-Za-z0-9][A-Za-z0-9-]{0,126}$/;

/* ── The allowlist ────────────────────────────────────────────────────
   Owner's rule (2026-10-07): a link is shared TO someone, and that person's
   email and their organisation's domain are what may open it — for that one
   DMA. Sharing with jane@bcu.com admits jane@bcu.com and anyone @bcu.com.

   It lives INSIDE the signed token: the link is bound to one client and one
   run, so its allowlist is that DMA's allowlist by construction, nobody can
   widen it without the private key, and no database write path exists for
   it (charter invariant 2 stands).

   A consumer mailbox provider is never admitted as a domain — sharing with
   someone@gmail.com admits that address only, not every Gmail user. */
export const CONSUMER_DOMAINS = new Set([
  "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com",
  "msn.com", "yahoo.com", "ymail.com", "rocketmail.com", "icloud.com", "me.com",
  "mac.com", "aol.com", "proton.me", "protonmail.com", "pm.me", "gmx.com",
  "gmx.net", "mail.com", "zoho.com", "zohomail.com", "yandex.com", "qq.com",
  "163.com", "126.com", "comcast.net", "verizon.net", "att.net",
  "sbcglobal.net", "bellsouth.net", "cox.net", "charter.net", "hey.com",
  "fastmail.com", "tutanota.com", "mail.ru",
]);

const EMAIL = /^[a-z0-9._%+'-]+@([a-z0-9-]+\.)+[a-z]{2,}$/;

export function normaliseEmail(v) {
  const e = String(v || "").trim().toLowerCase();
  return EMAIL.test(e) && e.length <= 254 ? e : null;
}

export function domainOf(email) {
  return String(email).split("@")[1];
}

/* The recipients box → [{ email, name }]. Accepts bare addresses and
   "Jane Doe <jane@bcu.com>", separated by commas, semicolons, new lines or
   spaces. The name is only used to greet the person in their sign-in email
   (it is recorded in the ledger, never signed into the link). Throws on any
   entry that does not parse: a typo silently dropped would be a colleague
   silently locked out. */
const ENTRY = /(?:"([^"]*)"\s*<\s*([^<>\s]+)\s*>)|(?:([^"<>,;\n]*?)\s*<\s*([^<>\s]+)\s*>)|([^\s,;<>"]+@[^\s,;<>"]+)/g;
export function parseRecipients(recipients) {
  const out = [];
  const list = Array.isArray(recipients) ? recipients : [String(recipients || "")];
  for (const raw of list) {
    const str = String(raw || "");
    let rest = str;
    for (const m of str.matchAll(ENTRY)) {
      rest = rest.replace(m[0], " ");
      const addr = m[2] || m[4] || m[5];
      const rawName = m[1] || m[3] || "";
      const e = normaliseEmail(addr);
      if (!e) throw Object.assign(new Error(`not an email address: ${String(addr).slice(0, 80)}`), { code: "bad_request" });
      const name = rawName ? rawName.replace(/[\u0000-\u001f<>"]/g, "").replace(/\s+/g, " ").trim().slice(0, 80) : "";
      out.push({ email: e, name: name || null });
    }
    const left = rest.replace(/[\s,;]+/g, " ").trim();
    if (left) throw Object.assign(new Error(`not an email address: ${left.slice(0, 80)}`), { code: "bad_request" });
  }
  return out;
}

/* Recipients → {m: emails, d: domains}. */
export function allowlistFor(recipients) {
  const m = new Set(), d = new Set();
  for (const { email: e } of parseRecipients(recipients)) {
    m.add(e);
    const dom = domainOf(e);
    if (!CONSUMER_DOMAINS.has(dom)) d.add(dom);
  }
  if (!m.size) throw Object.assign(new Error("name at least one recipient email"), { code: "bad_request" });
  if (m.size > 25) throw Object.assign(new Error("at most 25 recipients per link"), { code: "bad_request" });
  return { m: [...m].sort(), d: [...d].sort() };
}

// Where the relationship stands when a link is shared (owner, 2026-10-09):
// the share dialog asks, and the recipient's email follows — before the first
// sales call it offers a walkthrough; after it, a follow-up call. Recorded in
// the ledger with the link, never signed into it.
export const SHARE_STAGES = ["before_first_call", "after_first_call"];

// email → name, for the recipients given a name ("Jane Doe <jane@bcu.com>").
export function recipientNames(recipients) {
  const names = {};
  for (const { email, name } of parseRecipients(recipients)) if (name) names[email] = name;
  return names;
}

/* Whether `email` is on the token's allowlist: the address itself, or an
   address at one of its domains. Exact domain match only — sharing with
   @bcu.com does not admit @evil-bcu.com or @bcu.com.attacker.net. */
// `payload.x` is what an ADMIN has since removed from this link's allowlist
// (lib/share-ledger liveLink attaches it after the signature checks; it is
// never in the token). A removed address is refused even under a still-listed
// domain; a removed domain leaves only its explicitly named addresses.
export function allowed(payload, email) {
  const e = normaliseEmail(email);
  if (!e || !payload || !payload.a) return false;
  const x = payload.x || { m: [], d: [] };
  if ((x.m || []).includes(e)) return false;
  return (payload.a.m || []).includes(e) ||
    ((payload.a.d || []).includes(domainOf(e)) && !(x.d || []).includes(domainOf(e)));
}

export function mint({ entity, run, days, recipients }, key = signingKey(), now = Date.now()) {
  if (!key) throw Object.assign(new Error("share links are not configured"), { code: "not_configured" });
  if (!SLUG.test(String(entity || ""))) throw Object.assign(new Error("bad entity"), { code: "bad_request" });
  if (!RUN.test(String(run || ""))) throw Object.assign(new Error("bad run"), { code: "bad_request" });
  const a = allowlistFor(recipients);
  const d = Math.round(Number(days ?? DEFAULT_DAYS));
  if (!Number.isFinite(d) || d < 1 || d > MAX_DAYS) {
    throw Object.assign(new Error(`days must be 1–${MAX_DAYS}`), { code: "bad_request" });
  }
  const iat = Math.floor(now / 1000);
  const payload = { v: TOKEN_VERSION, e: entity, r: run, a, iat, exp: iat + d * 86400,
                    jti: crypto.randomBytes(9).toString("base64url") };
  const body = b64u(JSON.stringify(payload));
  const sig = crypto.sign(null, Buffer.from(body), key);
  // Who minted it is logged by the caller, never written into the token: the
  // token is handed to a client, and a colleague's address is not theirs.
  return { token: `${body}.${b64u(sig)}`, payload };
}

export function revokedJtis() {
  return new Set(String(process.env.SHARE_REVOKED_JTIS || "")
    .split(",").map((s) => s.trim()).filter(Boolean));
}

// Returns the payload of a valid, live, unrevoked token, else null. Never
// throws: an unreadable token is the common case on a public endpoint.
export function verify(token, key = verifyKey(), now = Date.now(), revoked = revokedJtis()) {
  try {
    if (!key || typeof token !== "string" || token.length > 4000) return null;
    const parts = token.split(".");
    if (parts.length !== 2) return null;
    const [body, sig] = parts;
    if (!/^[A-Za-z0-9_-]+$/.test(body) || !/^[A-Za-z0-9_-]+$/.test(sig)) return null;
    if (!crypto.verify(null, Buffer.from(body), key, Buffer.from(sig, "base64url"))) return null;
    const p = JSON.parse(Buffer.from(body, "base64url").toString());
    if (p.v !== TOKEN_VERSION) return null;
    if (!SLUG.test(String(p.e || "")) || !RUN.test(String(p.r || ""))) return null;
    // No allowlist, no access: a token that names nobody admits nobody.
    if (!p.a || !Array.isArray(p.a.m) || !p.a.m.length || !Array.isArray(p.a.d)) return null;
    if (!Number.isInteger(p.exp) || p.exp <= Math.floor(now / 1000)) return null;
    if (!Number.isInteger(p.iat) || p.exp - p.iat > MAX_DAYS * 86400) return null;
    if (revoked.has(p.jti)) return null;
    return p;
  } catch {
    return null;
  }
}

// The URL a client is sent. The hash opens the client frame on the overview;
// the frame does not depend on it (the boot carries the share), so a link
// with the fragment stripped still opens the same dashboard.
export function shareUrl(base, token, entity) {
  return `${String(base).replace(/\/+$/, "")}/s/${token}#/clients/${entity}/overview?view=client`;
}

/* ── The recipient's access ───────────────────────────────────────────
   On first open the recipient states their work email. An address off the
   allowlist is refused there and then — no email is ever sent to it.

   OTP mode (`SHARE_IDP_API_KEY` present — owner, 2026-10-07): Google Cloud
   Identity Platform emails that address a single-use sign-in link; only
   following it from that inbox admits the reader. The address is PROVEN.

   Attest mode (Identity Platform not configured yet): the address is taken
   as typed. deploy.sh says so loudly on every release while this holds.

   Either way the admission is a cookie signed with SHARE_COOKIE_SECRET
   (HMAC-SHA256), naming this link's jti, the admitted address and an
   expiry — so it cannot be forged into an OTP-verified session, cannot be
   carried to another link, and is re-checked against the allowlist on
   every read. Scoped to this link's own path. */
export const ACCESS_DAYS = 7;

export function verifyMode() {
  return process.env.SHARE_IDP_API_KEY ? "otp" : "attest";
}

function cookieKey() {
  const k = process.env.SHARE_COOKIE_SECRET;
  return k && k.length >= 32 ? k : null;
}

const hmac = (key, data) => crypto.createHmac("sha256", key).update(data).digest("base64url");

export function accessCookieName(payload) {
  return `dma_share_${payload.jti}`;
}

export function signAccess(payload, email, method, now = Date.now(), key = cookieKey()) {
  if (!key) throw Object.assign(new Error("SHARE_COOKIE_SECRET is not configured"), { code: "not_configured" });
  const exp = Math.min(payload.exp, Math.floor(now / 1000) + ACCESS_DAYS * 86400);
  const body = b64u(JSON.stringify({ j: payload.jti, e: normaliseEmail(email), m: method, x: exp }));
  return { value: `${body}.${hmac(key, body)}`, exp };
}

// The admitted address, or null. Signature, link, expiry and the allowlist
// are all re-checked: a cookie minted before the address was revoked from a
// re-shared link does not outlive the token it was minted under.
export function readAccess(payload, cookieValue, now = Date.now(), key = cookieKey()) {
  try {
    if (!key || !cookieValue) return null;
    const [body, mac] = String(cookieValue).split(".");
    if (!body || !mac) return null;
    const expect = hmac(key, body);
    if (mac.length !== expect.length ||
        !crypto.timingSafeEqual(Buffer.from(mac), Buffer.from(expect))) return null;
    const c = JSON.parse(Buffer.from(body, "base64url").toString());
    if (c.j !== payload.jti || !Number.isInteger(c.x) || c.x <= Math.floor(now / 1000)) return null;
    return allowed(payload, c.e) ? c.e : null;
  } catch {
    return null;
  }
}

export function accessCookie(payload, token, email, method, now = Date.now(), key = cookieKey()) {
  const { value, exp } = signAccess(payload, email, method, now, key);
  const maxAge = Math.max(0, exp - Math.floor(now / 1000));
  return `${accessCookieName(payload)}=${value}; ` +
    `Path=/s/${token}; Max-Age=${maxAge}; HttpOnly; Secure; SameSite=Lax`;
}

// The share service's own public origin, as the client reached it (Cloud
// Run terminates TLS and forwards the scheme).
export function publicOrigin(req) {
  const u = new URL(req.url);
  const host = req.headers.get("x-forwarded-host") || req.headers.get("host") || u.host;
  const proto = (req.headers.get("x-forwarded-proto") || u.protocol.replace(":", "")).split(",")[0];
  return `${proto}://${host}`;
}

export function cookieFrom(req, name) {
  const raw = req.headers.get("cookie") || "";
  for (const part of raw.split(/;\s*/)) {
    const i = part.indexOf("=");
    if (i > 0 && part.slice(0, i) === name) return part.slice(i + 1);
  }
  return null;
}

// One line per event, to Cloud Logging. The audit trail of who opened what.
export function audit(event, fields) {
  try { console.log(JSON.stringify({ event, at: new Date().toISOString(), ...fields })); } catch {}
}
