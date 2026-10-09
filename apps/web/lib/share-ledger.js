// The client-link ledger: every link generated, and every revocation, so an
// admin can see who was given access to what and take it back (owner,
// 2026-10-07: "The admin page should also have a place where I can revoke
// access").
//
// Not the application database. Invariant 2 keeps the database for content
// that arrived through the connector; access to a link is not content. The
// ledger is two prefixes in one private bucket (infra/deploy.sh):
//
//   links/<jti>.json     written once, by dmai-web, when a link is generated:
//                        client, run, recipients, who shared it, expiry
//   revoked/<jti>.json   written by an ADMIN through /api/admin/share-links:
//                        the whole link revoked, or single addresses or
//                        domains removed from its allowlist
//
// dmai-web holds objectAdmin on the bucket; the public dmai-share holds
// objectViewer only, so the internet-facing service can read a revocation
// but never write one.
//
// FAIL CLOSED. When a ledger is configured and cannot be read, a link does
// not open: "we could not check whether this was revoked" is answered as
// "revoked". A revocation takes effect within REVOCATION_TTL_MS everywhere
// (each dmai-share instance caches a reading that long), including for a
// reader already inside — every data read re-checks.
import fs from "fs";
import path from "path";
import { audit, normaliseEmail, verify } from "./share.js";

export const REVOCATION_TTL_MS = 15 * 1000;
const JTI = /^[A-Za-z0-9_-]{8,64}$/;
const DOMAIN = /^[a-z0-9-]+(\.[a-z0-9-]+)+$/;

export const isJti = (v) => JTI.test(String(v || ""));

/* ── Backends ──────────────────────────────────────────────────────────
   GCS in production (SHARE_LEDGER_BUCKET), a directory for local dev and
   the tests (SHARE_LEDGER_DIR), none otherwise. None means: no ledger, no
   admin list, revocation only through infra/share-revoked.txt — and the
   admin page says so rather than showing an empty list. */
export function ledgerBackend(env = process.env) {
  if (env.SHARE_LEDGER_BUCKET && /^[a-z0-9][a-z0-9._-]{1,220}$/.test(env.SHARE_LEDGER_BUCKET)) {
    return gcsBackend(env.SHARE_LEDGER_BUCKET);
  }
  if (env.SHARE_LEDGER_DIR) return dirBackend(env.SHARE_LEDGER_DIR);
  return null;
}

export class Unavailable extends Error {}

let tokenCache = null;
async function gcsToken() {
  if (process.env.GCS_ACCESS_TOKEN) return process.env.GCS_ACCESS_TOKEN;   // local QA only
  if (tokenCache && tokenCache.until > Date.now()) return tokenCache.value;
  const r = await fetch("http://metadata.google.internal/computeMetadata/v1/instance/" +
    "service-accounts/default/token", { headers: { "Metadata-Flavor": "Google" }, cache: "no-store" });
  if (!r.ok) throw new Unavailable(`metadata token ${r.status}`);
  const t = await r.json();
  tokenCache = { value: t.access_token, until: Date.now() + Math.max(0, (t.expires_in - 60) * 1000) };
  return t.access_token;
}

export function gcsBackend(bucket) {
  const api = process.env.STORAGE_API || "https://storage.googleapis.com";
  const b = encodeURIComponent(bucket);
  const auth = async () => ({ Authorization: `Bearer ${await gcsToken()}` });
  return {
    kind: "gcs", where: `gs://${bucket}`,
    // → { body, gen } | null (absent). Throws Unavailable on anything else.
    async read(name) {
      let r;
      try {
        r = await fetch(`${api}/storage/v1/b/${b}/o/${encodeURIComponent(name)}?alt=media`,
          { headers: await auth(), cache: "no-store" });
      } catch (e) { throw new Unavailable(String(e.message || e)); }
      if (r.status === 404) return null;
      if (!r.ok) throw new Unavailable(`read ${name}: ${r.status}`);
      return { body: await r.json(), gen: r.headers.get("x-goog-generation") || "0" };
    },
    // Conditional on the generation read (0 = must not exist yet), so two
    // admins editing one link cannot overwrite each other. → true | false
    // (precondition failed); throws Unavailable otherwise.
    async write(name, body, gen) {
      let r;
      try {
        r = await fetch(`${api}/upload/storage/v1/b/${b}/o?uploadType=media` +
          `&name=${encodeURIComponent(name)}&ifGenerationMatch=${encodeURIComponent(gen)}`,
          { method: "POST", cache: "no-store",
            headers: { ...(await auth()), "content-type": "application/json" },
            body: JSON.stringify(body) });
      } catch (e) { throw new Unavailable(String(e.message || e)); }
      if (r.status === 412) return false;
      if (!r.ok) throw new Unavailable(`write ${name}: ${r.status}`);
      return true;
    },
    async list(prefix) {
      const out = [];
      let pageToken = "";
      for (let i = 0; i < 20; i++) {
        let r;
        try {
          r = await fetch(`${api}/storage/v1/b/${b}/o?prefix=${encodeURIComponent(prefix)}` +
            `&maxResults=1000&fields=items(name),nextPageToken` +
            (pageToken ? `&pageToken=${encodeURIComponent(pageToken)}` : ""),
            { headers: await auth(), cache: "no-store" });
        } catch (e) { throw new Unavailable(String(e.message || e)); }
        if (!r.ok) throw new Unavailable(`list ${prefix}: ${r.status}`);
        const j = await r.json();
        for (const it of j.items || []) out.push(it.name);
        if (!j.nextPageToken) break;
        pageToken = j.nextPageToken;
      }
      return out;
    },
  };
}

export function dirBackend(root) {
  const file = (name) => path.join(root, ...name.split("/"));
  return {
    kind: "dir", where: root,
    async read(name) {
      try {
        const f = file(name);
        return { body: JSON.parse(fs.readFileSync(f, "utf8")), gen: String(fs.statSync(f).mtimeMs) };
      } catch (e) {
        if (e.code === "ENOENT") return null;
        throw new Unavailable(String(e.message || e));
      }
    },
    async write(name, body, gen) {
      const f = file(name);
      let cur = "0";
      try { cur = String(fs.statSync(f).mtimeMs); } catch {}
      if (String(gen) !== cur) return false;
      fs.mkdirSync(path.dirname(f), { recursive: true });
      const tmp = `${f}.${process.pid}.${Date.now()}.tmp`;
      fs.writeFileSync(tmp, JSON.stringify(body));
      fs.renameSync(tmp, f);
      return true;
    },
    async list(prefix) {
      const dir = file(prefix.replace(/\/$/, ""));
      try {
        return fs.readdirSync(dir).filter((n) => n.endsWith(".json")).map((n) => `${prefix}${n}`);
      } catch (e) {
        if (e.code === "ENOENT") return [];
        throw new Unavailable(String(e.message || e));
      }
    },
  };
}

/* ── Recording a link ──────────────────────────────────────────────── */
// `mintedByName` is the colleague's display name from their session: the
// sign-in email the recipient receives is sent from, and signed by, them.
// `names` (email → name) greets each named recipient in their sign-in email.
export async function recordLink(payload, mintedBy, backend = ledgerBackend(), mintedByName = null, names = null,
                                 stage = null) {
  if (!backend) return false;
  const rec = {
    jti: payload.jti, entity: payload.e, run: payload.r,
    emails: payload.a.m, domains: payload.a.d,
    minted_by: mintedBy || null,
    minted_by_name: mintedByName ? String(mintedByName).slice(0, 120) : null,
    recipient_names: names && typeof names === "object" ? names : {},
    // before_first_call | after_first_call — which follow-up the email offers.
    stage: stage || null,
    minted_at: new Date(payload.iat * 1000).toISOString(),
    expires_at: new Date(payload.exp * 1000).toISOString(),
  };
  if (!(await backend.write(`links/${payload.jti}.json`, rec, "0"))) {
    throw new Unavailable(`link ${payload.jti} already recorded`);
  }
  return true;
}

/* ── Who shared a link (the share service, when it sends a sign-in) ───
   → the links/<jti>.json record | null (not recorded — a link generated
   before the ledger). Cached like a revocation; throws Unavailable when a
   configured ledger cannot be read. */
const recCache = new Map();
export async function linkRecord(jti, backend = ledgerBackend(), now = Date.now()) {
  if (!backend || !isJti(jti)) return null;
  const hit = recCache.get(jti);
  if (hit && hit.until > now) return hit.value;
  const got = await backend.read(`links/${jti}.json`);
  const value = got ? got.body : null;
  recCache.set(jti, { value, until: now + 5 * 60 * 1000 });
  if (recCache.size > 5000) recCache.delete(recCache.keys().next().value);
  return value;
}

/* ── Reading a revocation (the share service, on every request) ────── */
const revCache = new Map();

// → null (not revoked) | { all, emails, domains, … }. Throws Unavailable
// when a configured ledger cannot be read — callers fail closed.
export async function revocationOf(jti, backend = ledgerBackend(), now = Date.now()) {
  if (!backend) return null;
  const hit = revCache.get(jti);
  if (hit && hit.until > now) return hit.value;
  const got = await backend.read(`revoked/${jti}.json`);
  const value = got ? normaliseRevocation(got.body) : null;
  revCache.set(jti, { value, until: now + REVOCATION_TTL_MS });
  if (revCache.size > 5000) revCache.delete(revCache.keys().next().value);
  return value;
}

export function clearRevocationCache() { revCache.clear(); }

function normaliseRevocation(b) {
  return {
    all: !!(b && b.all),
    emails: Array.isArray(b && b.emails) ? b.emails : [],
    domains: Array.isArray(b && b.domains) ? b.domains : [],
    history: Array.isArray(b && b.history) ? b.history : [],
  };
}

/* The share service's door for every /s/<token>… route: a signed, unexpired
   token (lib/share verify) that the ledger has not revoked. Removed
   recipients ride along on the payload as `x` (lib/share allowed() honours
   it), so the gate, the sign-in link and every data read refuse them.
   → { p } | { p: null, why: "dead" | "revoked" | "unavailable" } */
export async function liveLink(token, backend = ledgerBackend()) {
  const p = verify(token);
  if (!p) return { p: null, why: "dead" };
  let rev;
  try { rev = await revocationOf(p.jti, backend); } catch (e) {
    audit("share_ledger_unavailable", { jti: p.jti, error: String(e.message || e).slice(0, 200) });
    return { p: null, why: "unavailable" };
  }
  if (rev && rev.all) return { p: null, why: "revoked" };
  return { p: rev ? { ...p, x: { m: rev.emails, d: rev.domains } } : p };
}

/* ── Changing a revocation (ADMIN, through dmai-web) ───────────────── */
export const ACTIONS = ["revoke", "restore", "remove", "readd"];

export async function changeRevocation(jti, { action, email, domain, by }, backend = ledgerBackend()) {
  if (!backend) throw Object.assign(new Error("no ledger configured"), { code: "not_configured" });
  if (!isJti(jti)) throw Object.assign(new Error("not a link id"), { code: "bad_request" });
  if (!ACTIONS.includes(action)) throw Object.assign(new Error("unknown action"), { code: "bad_request" });
  const e = email ? normaliseEmail(email) : null;
  const d = domain ? String(domain).trim().toLowerCase().replace(/^@/, "") : null;
  if ((action === "remove" || action === "readd") && !(e || (d && DOMAIN.test(d)))) {
    throw Object.assign(new Error("name one email address or domain"), { code: "bad_request" });
  }
  for (let attempt = 0; attempt < 4; attempt++) {
    const got = await backend.read(`revoked/${jti}.json`);
    const cur = normaliseRevocation(got && got.body);
    const next = { jti, all: cur.all, emails: [...cur.emails], domains: [...cur.domains] };
    if (action === "revoke") next.all = true;
    if (action === "restore") next.all = false;
    const list = e ? next.emails : next.domains;
    const v = e || d;
    if (action === "remove" && !list.includes(v)) list.push(v);
    if (action === "readd" && list.includes(v)) list.splice(list.indexOf(v), 1);
    next.history = [...cur.history, { action, target: v || null, by: by || null,
                                      at: new Date().toISOString() }].slice(-100);
    if (await backend.write(`revoked/${jti}.json`, next, got ? got.gen : "0")) {
      revCache.delete(jti);
      return normaliseRevocation(next);
    }
  }
  throw new Unavailable("the link was being changed by someone else; try again");
}

/* ── The admin list ────────────────────────────────────────────────── */
export async function listLinks(backend = ledgerBackend(), now = Date.now()) {
  if (!backend) return { status: "not_configured", links: [] };
  try {
    const [linkNames, revNames] = await Promise.all([backend.list("links/"), backend.list("revoked/")]);
    const idOf = (n) => n.split("/").pop().replace(/\.json$/, "");
    const ids = [...new Set([...linkNames.map(idOf), ...revNames.map(idOf)])].filter(isJti).slice(0, 2000);
    const revs = new Set(revNames.map(idOf));
    const links = new Set(linkNames.map(idOf));
    const rows = await Promise.all(ids.map(async (jti) => {
      const [l, r] = await Promise.all([
        links.has(jti) ? backend.read(`links/${jti}.json`) : null,
        revs.has(jti) ? backend.read(`revoked/${jti}.json`) : null,
      ]);
      const rec = (l && l.body) || { jti, unrecorded: true };
      const rev = r ? normaliseRevocation(r.body) : null;
      const expired = rec.expires_at ? Date.parse(rec.expires_at) <= now : false;
      return { ...rec, jti, revocation: rev,
               status: rev && rev.all ? "revoked" : expired ? "expired" : rec.unrecorded ? "unrecorded" : "active" };
    }));
    rows.sort((a, b) => String(b.minted_at || "").localeCompare(String(a.minted_at || "")));
    return { status: "ok", where: backend.where, links: rows };
  } catch (e) {
    return { status: "error", detail: String(e.message || e).slice(0, 300), links: [] };
  }
}

/* ── Whitelisted client domains ───────────────────────────────────────
   Admin › Whitelisted client domains: every organisation domain the live
   links admit, and one control per domain. Access at a domain is the domain
   on a link's allowlist OR an address at it named on the link (lib/share
   allowed), so taking a domain's access back removes BOTH from every link
   that is still live — otherwise a named colleague would still get in — and
   restoring puts both back. Expired and revoked links are left alone: they
   already open for nobody. Each change is the per-link ledger write the
   Client links card makes, attributed to the admin. */
export function domainsOf(link) {
  const out = new Set((link.domains || []).map((d) => String(d).toLowerCase()));
  for (const e of link.emails || []) out.add(String(e).split("@")[1].toLowerCase());
  return [...out];
}

export async function changeDomainAccess(domain, { action, by }, backend = ledgerBackend()) {
  if (!backend) throw Object.assign(new Error("no ledger configured"), { code: "not_configured" });
  const d = String(domain || "").trim().toLowerCase().replace(/^@/, "");
  if (!DOMAIN.test(d)) throw Object.assign(new Error("name one domain"), { code: "bad_request" });
  if (action !== "revoke" && action !== "restore") {
    throw Object.assign(new Error("action is revoke or restore"), { code: "bad_request" });
  }
  const listed = await listLinks(backend);
  if (listed.status !== "ok") throw new Unavailable(listed.detail || "the ledger could not be read");
  const per = action === "revoke" ? "remove" : "readd";
  const changed = [];
  for (const l of listed.links) {
    if (l.status !== "active" || !domainsOf(l).includes(d)) continue;
    if ((l.domains || []).map((x) => x.toLowerCase()).includes(d)) {
      await changeRevocation(l.jti, { action: per, domain: d, by }, backend);
    }
    for (const e of l.emails || []) {
      if (String(e).toLowerCase().endsWith(`@${d}`)) {
        await changeRevocation(l.jti, { action: per, email: e, by }, backend);
      }
    }
    changed.push(l.jti);
  }
  return { domain: d, action, links: changed };
}

/* A pasted link or a bare id → the jti. A full link's token is decoded for
   its jti (no signature needed to READ the id; revoking an id is harmless if
   it names nothing). */
export function jtiFrom(input) {
  const s = String(input || "").trim();
  if (isJti(s)) return s;
  const m = s.match(/\/s\/([A-Za-z0-9_-]+)\.[A-Za-z0-9_-]+/);
  if (!m) return null;
  try {
    const p = JSON.parse(Buffer.from(m[1], "base64url").toString());
    return isJti(p.jti) ? p.jti : null;
  } catch { return null; }
}
