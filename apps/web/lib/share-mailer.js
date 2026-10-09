// Who sends the sign-in email, and how (owner, 2026-10-09: "the email [is]
// to be sent through the AE's email who generated the link or added that
// client to the allowlist, to ensure the email does not end up in spam" —
// and "We own a Google suite").
//
// zennify.com is Google Workspace. A message from a colleague's own Gmail
// mailbox leaves the way their everyday mail does (DKIM, SPF and the
// domain's Proofpoint outbound route), lands in their Sent folder, and
// replies reach them — the opposite of noreply@<project>.firebaseapp.com.
//
// The path, with no key anywhere:
//   1. The sign-in code is the app's own (lib/share-throttle signSignIn):
//      signed, bound to the address, single use, valid for the days the link
//      was shared for. Login validation is unchanged in kind: only someone
//      who can open that inbox can follow it; no Google account is needed.
//   2. dmai-share's service account signs a JWT naming the colleague
//      (`sub`) and the one scope gmail.send — through the IAM Credentials
//      API (signJwt on itself; the account holds no key).
//   3. Google's token endpoint exchanges it for a token that may send as
//      that colleague — only once a Workspace super admin has granted the
//      service account's client id the gmail.send scope (domain-wide
//      delegation). It can send; it cannot read anyone's mail.
//   4. Gmail API users.messages.send posts the MIME (lib/share-email).
//
// Not configured (SHARE_MAIL_SA unset — deploy sets it only after the
// delegated token exchange reads back gmail.send), no recorded colleague
// for the link, or the colleague outside the sender domains: Identity
// Platform sends its own email, as before.
import { domainOf } from "./share.js";
import { nameFromEmail } from "./share-email.js";

export const GMAIL_SEND = "https://www.googleapis.com/auth/gmail.send";
const SA = /^[a-z][a-z0-9-]{4,28}[a-z0-9]@[a-z0-9-]+\.iam\.gserviceaccount\.com$/;

export function mailerConfig(env = process.env) {
  if (!SA.test(env.SHARE_MAIL_SA || "")) return null;
  const domains = String(env.SHARE_MAIL_SENDER_DOMAINS || "zennify.com").toLowerCase()
    .split(/[\s,;]+/).filter(Boolean);
  return { sa: env.SHARE_MAIL_SA, domains };
}

const urls = (env = process.env) => ({
  metadata: (env.METADATA_URL || "http://metadata.google.internal").replace(/\/+$/, ""),
  iam: (env.SHARE_MAIL_IAM_URL || "https://iamcredentials.googleapis.com").replace(/\/+$/, ""),
  oauth: (env.SHARE_MAIL_OAUTH_URL || "https://oauth2.googleapis.com").replace(/\/+$/, ""),
  gmail: (env.SHARE_MAIL_GMAIL_URL || "https://gmail.googleapis.com").replace(/\/+$/, ""),
});

/* Who the email comes from. The colleague who most recently re-added this
   address (or its domain) to the link, else the colleague who generated it —
   in either case only someone in a sender domain. → { email, name } | null */
export function senderFor(record, revocation, email, cfg) {
  if (!cfg) return null;
  const ok = (e) => typeof e === "string" && cfg.domains.includes(domainOf(e.toLowerCase()));
  const dom = domainOf(email);
  const readd = ((revocation && revocation.history) || []).filter((h) =>
    h && h.action === "readd" && (h.target === email || h.target === dom) && ok(h.by)).pop();
  if (readd) return { email: readd.by.toLowerCase(), name: nameFromEmail(readd.by) };
  if (record && ok(record.minted_by)) {
    return { email: record.minted_by.toLowerCase(),
             name: record.minted_by_name || nameFromEmail(record.minted_by) };
  }
  return null;
}

async function json(r) { try { return await r.json(); } catch { return {}; } }

const tokenCache = new Map();
async function cached(key, fetcher) {
  const hit = tokenCache.get(key);
  if (hit && hit.until > Date.now()) return hit.value;
  const { value, ttl } = await fetcher();
  tokenCache.set(key, { value, until: Date.now() + Math.max(0, ttl - 300) * 1000 });
  if (tokenCache.size > 500) tokenCache.delete(tokenCache.keys().next().value);
  return value;
}

const metadataToken = () => cached("metadata", async () => {
  const r = await fetch(`${urls().metadata}/computeMetadata/v1/instance/service-accounts/default/token`,
    { headers: { "Metadata-Flavor": "Google" }, cache: "no-store" });
  if (!r.ok) throw new Error(`metadata token ${r.status}`);
  const t = await json(r);
  return { value: t.access_token, ttl: Number(t.expires_in) || 300 };
});

// A token that may send mail as `from`, and nothing else.
export const sendToken = (cfg, from) => cached(`gmail|${from}`, async () => {
  const iat = Math.floor(Date.now() / 1000);
  const claims = { iss: cfg.sa, sub: from, scope: GMAIL_SEND,
                   aud: `${urls().oauth}/token`, iat, exp: iat + 3600 };
  const s = await fetch(`${urls().iam}/v1/projects/-/serviceAccounts/${encodeURIComponent(cfg.sa)}:signJwt`, {
    method: "POST", cache: "no-store",
    headers: { Authorization: `Bearer ${await metadataToken()}`, "content-type": "application/json" },
    body: JSON.stringify({ payload: JSON.stringify(claims) }),
  });
  const sj = await json(s);
  if (!s.ok || !sj.signedJwt) throw new Error(`signJwt ${s.status}: ${String((sj.error && sj.error.message) || "").slice(0, 120)}`);
  const r = await fetch(`${urls().oauth}/token`, {
    method: "POST", cache: "no-store", headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer", assertion: sj.signedJwt }),
  });
  const j = await json(r);
  if (!r.ok || !j.access_token) {
    // unauthorized_client = domain-wide delegation not granted for gmail.send.
    throw new Error(`token ${r.status}: ${String(j.error || "")} ${String(j.error_description || "").slice(0, 120)}`.trim());
  }
  return { value: j.access_token, ttl: Number(j.expires_in) || 600 };
});

/* Send the MIME message (lib/share-email buildMime) from `from`'s Gmail.
   → { ok } | { ok: false, error, status } */
export async function sendAs(cfg, from, mime) {
  try {
    const token = await sendToken(cfg, from);
    const r = await fetch(`${urls().gmail}/gmail/v1/users/me/messages/send`, {
      method: "POST", cache: "no-store",
      headers: { Authorization: `Bearer ${token}`, "content-type": "application/json" },
      body: JSON.stringify({ raw: Buffer.from(mime, "utf8").toString("base64url") }),
    });
    if (r.ok) return { ok: true };
    const j = await json(r);
    return { ok: false, status: r.status,
             error: String((j.error && (j.error.status || j.error.message)) || `http_${r.status}`).slice(0, 160) };
  } catch (e) {
    return { ok: false, error: String(e.message || e).slice(0, 160) };
  }
}

export function _resetTokenCache() { tokenCache.clear(); }
