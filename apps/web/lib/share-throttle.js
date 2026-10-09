// How often the client-link gate may send a sign-in email (owner, 2026-10-09:
// "ensure there are safeguards against [the sign-in email] being spammed …
// the link sharing does not lead to spamming").
//
// The gate only ever mails an address on the link's allowlist (lib/share
// allowed). These budgets stop even those sends from becoming a flood — a
// recipient hammering the button, a bot walking random@client.com under a
// shared domain (every miss bounces into the colleague's inbox), or a link
// forwarded far and wide — and cap what one colleague's mailbox sends in a
// day, far below Exchange Online's own limits, so the reputation that keeps
// these emails out of spam folders is never spent.
//
// Counted in a store every dmai-share instance shares (the private bucket
// SHARE_SENDS_BUCKET, objects expire after two days; a directory locally).
// FAIL CLOSED: when the store is configured and cannot be read or written,
// nothing is sent.
import crypto from "crypto";
import fs from "fs";
import path from "path";
import { dirBackend, gcsBackend } from "./share-ledger.js";

// name → [count, window seconds]. Fixed windows.
export const LIMITS = {
  cooldown:  [1, 60],        // one email per address per link per minute
  addrHour:  [4, 3600],      // …four an hour
  addrDay:   [8, 86400],     // …eight a day
  linkHour:  [20, 3600],     // one link, all addresses
  linkDay:   [60, 86400],
  unlisted:  [15, 86400],    // addresses admitted only by their domain
  senderDay: [150, 86400],   // one colleague's mailbox, every link
  ipHour:    [20, 3600],     // one network
  globalDay: [600, 86400],   // the whole service — a kill switch, not a quota
};

export const REASONS = {
  cooldown: "cooldown", addrHour: "address", addrDay: "address",
  linkHour: "link", linkDay: "link", unlisted: "link",
  senderDay: "sender", ipHour: "network", globalDay: "service",
};

const h = (s) => crypto.createHash("sha256").update(String(s)).digest("hex").slice(0, 32);

class StoreUnavailable extends Error {}
// Every retry of a compare-and-set lost to a concurrent request. Treated as
// the budget being spent — never as room — so contention can only stop a send.
class Contended extends Error {}
const pause = (attempt) => new Promise((r) => setTimeout(r, 2 + Math.random() * 10 * (attempt + 1)));

export function throttleBackend(env = process.env) {
  if (env.SHARE_SENDS_BUCKET && /^[a-z0-9][a-z0-9._-]{1,220}$/.test(env.SHARE_SENDS_BUCKET)) {
    return counterStore(gcsBackend(env.SHARE_SENDS_BUCKET));
  }
  if (env.SHARE_SENDS_DIR) return counterStore(lockedDir(env.SHARE_SENDS_DIR));
  return memoryStore();
}

// A directory backend whose compare-and-set is serialised per object in this
// process (the shared ledger's directory backend compares mtimes, which two
// writes inside one millisecond defeat). Local dev and the tests only.
function lockedDir(root) {
  const base = dirBackend(root);
  const chains = new Map();
  const ver = (name) => {
    try { return String(JSON.parse(fs.readFileSync(path.join(root, ...name.split("/")), "utf8")).v || 0); }
    catch { return "0"; }
  };
  return {
    kind: "dir", where: root,
    async read(name) {
      const got = await base.read(name);
      return got ? { body: got.body, gen: String(got.body.v || 0) } : null;
    },
    write(name, body, gen) {
      const run = async () => {
        if (ver(name) !== String(gen)) return false;
        const f = path.join(root, ...name.split("/"));
        fs.mkdirSync(path.dirname(f), { recursive: true });
        const tmp = `${f}.${process.pid}.${crypto.randomBytes(4).toString("hex")}.tmp`;
        fs.writeFileSync(tmp, JSON.stringify({ ...body, v: Number(gen) + 1 }));
        fs.renameSync(tmp, f);
        return true;
      };
      const next = (chains.get(name) || Promise.resolve()).then(run, run);
      chains.set(name, next.catch(() => {}));
      return next;
    },
  };
}

// Fixed-window counters over any {read, write(name, body, gen)} store whose
// write is conditional on the generation read ("0" = must not exist).
function counterStore(store) {
  const objectName = (k, win, now) => {
    const start = Math.floor(now / 1000 / win) * win;
    return { name: `rl/${k.slice(0, 2)}/${k}-${win}-${start}.json`, resetsAt: (start + win) * 1000 };
  };
  return {
    kind: store.kind, where: store.where,
    async claim(name) {
      try { return await store.write(name, { at: new Date().toISOString() }, "0"); }
      catch (e) { throw new StoreUnavailable(String(e.message || e)); }
    },
    async count(k, win, now) {
      const { name, resetsAt } = objectName(k, win, now);
      let got;
      try { got = await store.read(name); } catch (e) { throw new StoreUnavailable(String(e.message || e)); }
      return { n: got ? Number(got.body.n) || 0 : 0, resetsAt };
    },
    async bump(k, win, now) {
      const { name } = objectName(k, win, now);
      for (let i = 0; i < 16; i++) {
        if (i) await pause(i);
        let got;
        try { got = await store.read(name); } catch (e) { throw new StoreUnavailable(String(e.message || e)); }
        const n = got ? Number(got.body.n) || 0 : 0;
        let ok;
        try { ok = await store.write(name, { n: n + 1 }, got ? got.gen : "0"); }
        catch (e) { throw new StoreUnavailable(String(e.message || e)); }
        if (ok) return n + 1;
      }
      throw new Contended(name);
    },
  };
}

// Per instance. Only when no store is configured (local dev); production
// always configures the bucket (infra/deploy.sh).
function memoryStore() {
  const m = new Map();
  const key = (k, win, now) => {
    const start = Math.floor(now / 1000 / win) * win;
    return { id: `${k}|${win}|${start}`, resetsAt: (start + win) * 1000 };
  };
  const used = new Set();
  return {
    kind: "memory", where: "this instance",
    async claim(name) { if (used.has(name)) return false; used.add(name); return true; },
    async count(k, win, now) { const { id, resetsAt } = key(k, win, now); return { n: m.get(id) || 0, resetsAt }; },
    async bump(k, win, now) {
      const { id } = key(k, win, now);
      if (m.size > 20000) m.clear();
      m.set(id, (m.get(id) || 0) + 1);
      return m.get(id);
    },
  };
}

/* The client's address as Cloud Run sees it. Cloud Run appends the peer
   address to X-Forwarded-For; anything before it came from the client and is
   not trusted — so the LAST entry, never the first. */
export function clientIp(req) {
  const xff = String((req.headers && req.headers.get && req.headers.get("x-forwarded-for")) || "");
  const parts = xff.split(",").map((s) => s.trim()).filter(Boolean);
  return parts.length ? parts[parts.length - 1] : "unknown";
}

/* May the gate send one more sign-in email? → { ok: true } |
   { ok: false, reason: "cooldown"|"address"|"link"|"sender"|"network"|"service",
     limit, retryAfter (seconds) } | { ok: false, reason: "unavailable" }

   Read first (an exhausted budget costs nothing more), then SPEND by atomic
   increment and check the count the increment returned — so a burst of
   parallel requests cannot all read "0" and all pass. The address's
   one-a-minute cooldown is claimed alone and first: of N simultaneous
   requests for one address exactly one goes on to spend the rest. */
export async function admitSend({ jti, email, listed, sender, ip }, store = throttleBackend(),
                                now = Date.now(), limits = LIMITS) {
  const keys = [
    ["cooldown", `a|${jti}|${email}`], ["addrHour", `a|${jti}|${email}`], ["addrDay", `a|${jti}|${email}`],
    ["ipHour", `i|${ip || "unknown"}`],
    ["linkHour", `l|${jti}`], ["linkDay", `l|${jti}`],
    ...(listed ? [] : [["unlisted", `u|${jti}`]]),
    ...(sender ? [["senderDay", `s|${sender}`]] : []),
    ["globalDay", "g"],
  ].map(([name, id]) => ({ name, k: h(`${name}|${id}`), n: limits[name][0], win: limits[name][1] }));
  const deny = (x, resetsAt) => ({ ok: false, reason: REASONS[x.name], limit: x.name,
    retryAfter: Math.max(1, Math.ceil(((resetsAt || now + x.win * 1000) - now) / 1000)) });
  try {
    const counts = await Promise.all(keys.map((x) => store.count(x.k, x.win, now)));
    for (let i = 0; i < keys.length; i++) {
      if (counts[i].n >= keys[i].n) return deny(keys[i], counts[i].resetsAt);
    }
    const spend = (x) => store.bump(x.k, x.win, now)
      .catch((e) => { if (e instanceof Contended) return Infinity; throw e; });
    const [cool, ...rest] = keys;
    if ((await spend(cool)) > cool.n) return deny(cool, counts[0].resetsAt);
    const after = await Promise.all(rest.map(spend));
    for (let i = 0; i < rest.length; i++) {
      if (after[i] > rest[i].n) return deny(rest[i], counts[i + 1].resetsAt);
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, reason: "unavailable", detail: String(e.message || e).slice(0, 200) };
  }
}

/* ── Bot friction on the gate form ──────────────────────────────────────
   Two hidden fields, no third-party CAPTCHA:
     website  a honeypot no person sees or fills;
     ft       when the form was rendered, signed with the cookie secret — a
              submission faster than a person types, or a form older than
              FORM_MAX_AGE_MS, sends nothing. */
export const FORM_MIN_MS = 1500;
export const FORM_MAX_AGE_MS = 2 * 3600 * 1000;

const mac = (secret, data) => crypto.createHmac("sha256", secret).update(data).digest("base64url").slice(0, 22);
const same = (a, b) => {
  const x = Buffer.from(String(a || "")), y = Buffer.from(String(b || ""));
  return x.length === y.length && crypto.timingSafeEqual(x, y);
};

export function formToken(jti, secret = process.env.SHARE_COOKIE_SECRET, now = Date.now()) {
  if (!secret) return "";
  return `${now}.${mac(secret, `form|${jti}|${now}`)}`;
}

// → "ok" | "bot" (honeypot filled, or faster than a person) | "stale"
// (missing, forged or too old — the page is shown again, nothing is sent).
export function judgeForm(jti, { ft, website }, secret = process.env.SHARE_COOKIE_SECRET, now = Date.now()) {
  if (website && String(website).trim()) return "bot";
  if (!secret) return "ok";
  const [t, m] = String(ft || "").split(".");
  const issued = Number(t);
  if (!Number.isFinite(issued) || !same(m, mac(secret, `form|${jti}|${issued}`))) return "stale";
  if (now - issued < FORM_MIN_MS) return "bot";
  if (now - issued > FORM_MAX_AGE_MS) return "stale";
  return "ok";
}

/* ── The sign-in link (owner, 2026-10-09: "It is number of days not
   minutes") ───────────────────────────────────────────────────────────────
   The link a colleague's mailbox sends is the app's own one-time code, not
   Google's (whose codes expire within hours). It names the link, the address,
   when it was issued and a random nonce, signed with the cookie secret. It
   stays valid for as long as the share link does — the days the colleague
   chose when sharing — and works ONCE: /verify claims `used/<nonce>` in the
   shared store, create-if-absent, before admitting anyone. */
export function signSignIn(jti, email, secret = process.env.SHARE_COOKIE_SECRET, now = Date.now()) {
  const i = Math.floor(now / 1000);
  const n = crypto.randomBytes(16).toString("base64url");
  return { i, n, s: secret ? mac(secret, `signin|${jti}|${email}|${i}|${n}`) : "" };
}

// → "ok" | "expired" (the share link itself has expired) | "invalid"
export function checkSignIn(payload, email, i, n, s, secret = process.env.SHARE_COOKIE_SECRET, now = Date.now()) {
  if (!secret) return "invalid";
  const issued = Number(i);
  if (!Number.isInteger(issued) || !/^[\w-]{16,64}$/.test(String(n || "")) ||
      !same(s, mac(secret, `signin|${payload.jti}|${email}|${issued}|${n}`))) return "invalid";
  if (issued < payload.iat - 60) return "invalid";
  if (Math.floor(now / 1000) >= payload.exp) return "expired";
  return "ok";
}

// Burn a sign-in nonce. → true (first use) | false (already used).
// Throws when the store cannot answer — the caller refuses (fail closed).
export async function claimNonce(n, store = throttleBackend()) {
  return store.claim(`used/${h(`nonce|${n}`)}.json`);
}
