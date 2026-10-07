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
// Revocation: every token carries a `jti`. One link is revoked by listing its
// jti in infra/share-revoked.txt and redeploying; every link at once by
// rotating the key (a new version of dmai-share-signing-key + verify-key).
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

/* Recipients → {m: emails, d: domains}. Throws on any address that does not
   parse: a typo silently dropped would be a colleague silently locked out. */
export function allowlistFor(recipients) {
  const list = Array.isArray(recipients) ? recipients
    : String(recipients || "").split(/[\s,;]+/);
  const m = new Set(), d = new Set();
  for (const raw of list) {
    if (!String(raw || "").trim()) continue;
    const e = normaliseEmail(raw);
    if (!e) throw Object.assign(new Error(`not an email address: ${String(raw).slice(0, 80)}`), { code: "bad_request" });
    m.add(e);
    const dom = domainOf(e);
    if (!CONSUMER_DOMAINS.has(dom)) d.add(dom);
  }
  if (!m.size) throw Object.assign(new Error("name at least one recipient email"), { code: "bad_request" });
  if (m.size > 25) throw Object.assign(new Error("at most 25 recipients per link"), { code: "bad_request" });
  return { m: [...m].sort(), d: [...d].sort() };
}

/* Whether `email` is on the token's allowlist: the address itself, or an
   address at one of its domains. Exact domain match only — sharing with
   @bcu.com does not admit @evil-bcu.com or @bcu.com.attacker.net. */
export function allowed(payload, email) {
  const e = normaliseEmail(email);
  if (!e || !payload || !payload.a) return false;
  return (payload.a.m || []).includes(e) || (payload.a.d || []).includes(domainOf(e));
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
   On first open the recipient states their work email; an address on the
   allowlist is admitted and remembered for this link in an httpOnly cookie
   scoped to the link's own path, so it never travels with another link.

   HONEST LIMIT, stated where it is enforced: with no mail provider and no
   identity provider (owner's constraint, 2026-10-07) nothing PROVES the
   reader owns the address they typed. What protects the dashboard is the
   link itself — unguessable, signed, expiring, revocable, delivered to the
   recipient's own mailbox by the sharer. The email gate keeps a forwarded
   link from opening outside the named organisation for anyone who answers
   it honestly, and it names every reader in the access log. The cookie is
   therefore not signed: forging it is no easier than typing the address. */
export function accessCookieName(payload) {
  return `dma_share_${payload.jti}`;
}

export function readAccess(payload, cookieValue) {
  if (!cookieValue) return null;
  try {
    const email = Buffer.from(String(cookieValue), "base64url").toString();
    return allowed(payload, email) ? normaliseEmail(email) : null;
  } catch {
    return null;
  }
}

export function accessCookie(payload, token, email, now = Date.now()) {
  const maxAge = Math.max(0, payload.exp - Math.floor(now / 1000));
  return `${accessCookieName(payload)}=${Buffer.from(email).toString("base64url")}; ` +
    `Path=/s/${token}; Max-Age=${maxAge}; HttpOnly; Secure; SameSite=Lax`;
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
