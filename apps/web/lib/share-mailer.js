// Who sends the sign-in email, and how (owner, 2026-10-09: "the email [is]
// to be sent through the AE's email who generated the link or added that
// client to the allowlist, to ensure the email does not end up in spam").
//
// zennify.com's mailboxes are Microsoft 365 (Exchange Online behind
// Proofpoint; DMARC p=quarantine, strict alignment). A message from a
// colleague's real mailbox is DKIM-signed and SPF-aligned for zennify.com,
// lands in their Sent Items, and replies reach them — the opposite of
// noreply@<project>.firebaseapp.com.
//
// The path, with no secret anywhere:
//   1. The sign-in code is the app's own (lib/share-throttle signSignIn):
//      signed, bound to the address, single use, valid for the days the link
//      was shared for — Google's codes expire within hours.
//   2. Cloud Run's metadata server mints a Google ID token for the
//      dmai-share service account, audience api://AzureADTokenExchange.
//   3. Microsoft Entra trusts that token (a federated credential on the
//      "DMA Insights mailer" app: issuer https://accounts.google.com, subject
//      the service account's unique id) and returns a Graph token.
//   4. Graph POST /users/{colleague}/sendMail sends the MIME message
//      (lib/share-email) from that colleague's mailbox — Mail.Send,
//      restricted by an Exchange application access policy to the people
//      who share links.
//
// Not configured (SHARE_MAIL_TENANT_ID / SHARE_MAIL_CLIENT_ID unset — deploy
// sets them only after the token exchange reads back Mail.Send), no
// recorded colleague for the link, or the colleague outside the sender
// domains: Identity Platform sends its own email, as before.
import { domainOf } from "./share.js";
import { nameFromEmail } from "./share-email.js";

const GUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export const FEDERATION_AUDIENCE = "api://AzureADTokenExchange";

export function mailerConfig(env = process.env) {
  if (!GUID.test(env.SHARE_MAIL_TENANT_ID || "") || !GUID.test(env.SHARE_MAIL_CLIENT_ID || "")) return null;
  const domains = String(env.SHARE_MAIL_SENDER_DOMAINS || "zennify.com").toLowerCase()
    .split(/[\s,;]+/).filter(Boolean);
  return { tenant: env.SHARE_MAIL_TENANT_ID, client: env.SHARE_MAIL_CLIENT_ID, domains };
}

const urls = (env = process.env) => ({
  metadata: (env.METADATA_URL || "http://metadata.google.internal").replace(/\/+$/, ""),
  login: (env.SHARE_MAIL_LOGIN_URL || "https://login.microsoftonline.com").replace(/\/+$/, ""),
  graph: (env.SHARE_MAIL_GRAPH_URL || "https://graph.microsoft.com").replace(/\/+$/, ""),
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
  return value;
}

async function metadata(path) {
  const r = await fetch(`${urls().metadata}/computeMetadata/v1/instance/service-accounts/default/${path}`,
    { headers: { "Metadata-Flavor": "Google" }, cache: "no-store" });
  if (!r.ok) throw new Error(`metadata ${path.split("?")[0]} ${r.status}`);
  return r;
}

const googleIdToken = () => cached("google-id", async () => {
  const r = await metadata(`identity?audience=${encodeURIComponent(FEDERATION_AUDIENCE)}&format=full`);
  return { value: (await r.text()).trim(), ttl: 3000 };
});

export const graphToken = (cfg) => cached(`graph|${cfg.tenant}|${cfg.client}`, async () => {
  const body = new URLSearchParams({
    client_id: cfg.client, scope: "https://graph.microsoft.com/.default",
    grant_type: "client_credentials",
    client_assertion_type: "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
    client_assertion: await googleIdToken(),
  });
  const r = await fetch(`${urls().login}/${cfg.tenant}/oauth2/v2.0/token`,
    { method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" }, body, cache: "no-store" });
  const j = await json(r);
  if (!r.ok || !j.access_token) {
    throw new Error(`entra token ${r.status}: ${String(j.error_description || j.error || "").slice(0, 160)}`);
  }
  return { value: j.access_token, ttl: Number(j.expires_in) || 600 };
});

/* Send the MIME message (lib/share-email buildMime) from `from`'s mailbox.
   Graph answers 202 with no body; the message is saved to Sent Items.
   → { ok } | { ok: false, error, status } */
export async function sendAs(cfg, from, mime) {
  try {
    const token = await graphToken(cfg);
    const r = await fetch(`${urls().graph}/v1.0/users/${encodeURIComponent(from)}/sendMail`, {
      method: "POST", cache: "no-store",
      headers: { Authorization: `Bearer ${token}`, "content-type": "text/plain" },
      body: Buffer.from(mime, "utf8").toString("base64"),
    });
    if (r.status === 202 || r.ok) return { ok: true };
    const j = await json(r);
    return { ok: false, status: r.status,
             error: String((j.error && (j.error.code || j.error.message)) || `http_${r.status}`).slice(0, 160) };
  } catch (e) {
    return { ok: false, error: String(e.message || e).slice(0, 160) };
  }
}

export function _resetTokenCache() { tokenCache.clear(); }
