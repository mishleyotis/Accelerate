/* Client sign-in email, end to end and under load (owner, 2026-10-09: the
 * email must come from the colleague who shared the dashboard, be Zennify-
 * branded, and "ensure there are safeguards against [it] being spammed …
 * stress test the changes").
 *
 *   curl-like client ──▶ next start (SHARE_MODE=1, the real production build)
 *      ├─▶ Identity Platform  (stub: the fallback sender's email + code)
 *      ├─▶ GCE metadata       (stub: dmai-share's access token)
 *      ├─▶ IAM Credentials    (stub: signJwt as dmai-share)
 *      ├─▶ Google OAuth       (stub: delegated gmail.send token, only for a signed JWT)
 *      ├─▶ Gmail API          (stub: records every message "sent")
 *      └─▶ svc_api            (stub: the client's name)
 *   ledger + send budgets: temporary directories.
 *
 * Run:  (cd apps/web && npx next build) && node apps/web/tests/e2e/share-mail.stress.js
 * Exits non-zero on any failed check; prints one line per check.
 */
const http = require("http");
const path = require("path");
const fs = require("fs");
const os = require("os");
const crypto = require("crypto");
const { spawn } = require("child_process");

const WEB = path.resolve(__dirname, "../..");
const S = require(path.join(WEB, "lib/share.js"));
const L = require(path.join(WEB, "lib/share-ledger.js"));
const SAVE = process.env.SHARE_MAIL_STRESS_OUT || null;   // write the received HTML here

const PORT = 4710, STUB = 4711, BASE = `http://127.0.0.1:${PORT}`, STUBURL = `http://127.0.0.1:${STUB}`;
const ENTITY = "first-tech-federal-credit-union", RUN = "6fa6ff19-7016-4e10-9f49-3ddfb2de4940";
const SA = "dmai-share@digital-maturity-assessor.iam.gserviceaccount.com";
const AE = "mishley.otiende@zennify.com";
const SECRET = crypto.randomBytes(32).toString("hex");
const keys = crypto.generateKeyPairSync("ed25519");
const ledgerDir = fs.mkdtempSync(path.join(os.tmpdir(), "ledger-"));
const sendsDir = fs.mkdtempSync(path.join(os.tmpdir(), "sends-"));
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
let pass = 0, fail = 0;
const ok = (c, what, saw) => { c ? pass++ : fail++; console.log(`${c ? "PASS" : "FAIL"}  ${what}  →  ${saw}`); };

/* ── Stubs ─────────────────────────────────────────────────────────── */
const gmailOut = [], idpEmails = [], codes = new Map();
let gmailMode = "ok";
const b64u = (o) => Buffer.from(JSON.stringify(o)).toString("base64url");
const stub = http.createServer(async (req, res) => {
  let raw = ""; for await (const c of req) raw += c;
  const u = new URL(req.url, STUBURL);
  const send = (s, o, type = "application/json") => {
    res.writeHead(s, { "content-type": type }); res.end(typeof o === "string" ? o : JSON.stringify(o)); };
  // GCE metadata
  if (u.pathname.endsWith("/service-accounts/default/token")) return send(200, { access_token: "sa-access", expires_in: 3600 });
  // IAM Credentials signJwt — only dmai-share signing as itself
  if (u.pathname === `/v1/projects/-/serviceAccounts/${encodeURIComponent(SA)}:signJwt` ||
      u.pathname === `/v1/projects/-/serviceAccounts/${SA}:signJwt`) {
    if (req.headers.authorization !== "Bearer sa-access") return send(403, { error: { message: "denied" } });
    const claims = JSON.parse(JSON.parse(raw).payload);
    return send(200, { signedJwt: `jwt.${b64u(claims)}.sig` });
  }
  // Identity Platform
  if (u.pathname === "/v1/accounts:sendOobCode") {
    const b = JSON.parse(raw || "{}");
    const code = crypto.randomBytes(8).toString("hex");
    codes.set(code, b.email);
    idpEmails.push({ to: b.email, code, continueUrl: b.continueUrl });
    return send(200, { email: b.email });
  }
  if (u.pathname === "/v1/accounts:signInWithEmailLink") {
    const b = JSON.parse(raw || "{}");
    if (codes.get(b.oobCode) !== b.email) return send(400, { error: { message: "INVALID_OOB_CODE" } });
    codes.delete(b.oobCode); return send(200, { email: b.email });
  }
  // Google OAuth: delegated token for the JWT's sub, gmail.send only
  if (u.pathname === "/token") {
    const f = new URLSearchParams(raw);
    let c = {};
    try { c = JSON.parse(Buffer.from(String(f.get("assertion")).split(".")[1], "base64url").toString()); } catch {}
    if (f.get("grant_type") !== "urn:ietf:params:oauth:grant-type:jwt-bearer" || c.iss !== SA ||
        c.scope !== "https://www.googleapis.com/auth/gmail.send" || !/@zennify\.com$/.test(c.sub || "")) {
      return send(401, { error: "unauthorized_client" });
    }
    return send(200, { access_token: `as.${b64u({ sub: c.sub })}`, expires_in: 3600, scope: c.scope });
  }
  // Gmail API
  if (u.pathname === "/gmail/v1/users/me/messages/send") {
    const tok = String(req.headers.authorization || "");
    if (!tok.startsWith("Bearer as.")) return send(401, { error: { status: "UNAUTHENTICATED" } });
    if (gmailMode === "deny") return send(403, { error: { status: "PERMISSION_DENIED" } });
    const sub = JSON.parse(Buffer.from(tok.slice(10), "base64url").toString()).sub;
    const mime = Buffer.from(JSON.parse(raw).raw, "base64url").toString("utf8");
    gmailOut.push({ from: sub, mime, to: (mime.match(/^To: <([^>]+)>/m) || [])[1] });
    return send(200, { id: crypto.randomBytes(6).toString("hex"), labelIds: ["SENT"] });
  }
  // svc_api
  if (u.pathname === `/v1/entities/${ENTITY}/overview`) {
    return send(200, { entity: { display_id: ENTITY, entity_name: "First Tech Federal Credit Union", sub_vertical: "CU" }, run: { run_id: RUN } });
  }
  if (u.pathname === "/v1/catalogue") return send(200, { version: "v7.0" });
  send(404, { error: "stub: no route" });
});

/* ── Helpers ───────────────────────────────────────────────────────── */
const mint = async (recipients, mintedBy = AE, name = "Mishley Otiende", stage = "before_first_call") => {
  const r = S.mint({ entity: ENTITY, run: RUN, recipients, days: 7 }, keys.privateKey);
  await L.recordLink(r.payload, mintedBy, L.dirBackend(ledgerDir), name, S.recipientNames(recipients), stage);
  return r;
};
const gate = async (tok) => {
  const html = await (await fetch(`${BASE}/s/${tok}`)).text();
  return (html.match(/name="ft" value="([^"]*)"/) || [])[1] || "";
};
const post = (tok, fields, ip = "203.0.113.7") => fetch(`${BASE}/s/${tok}/access`, {
  method: "POST", redirect: "manual",
  headers: { "content-type": "application/x-www-form-urlencoded", "x-forwarded-for": ip },
  body: new URLSearchParams(fields).toString() });
const qpDecode = (s) => {
  const flat = s.replace(/=\r\n/g, ""); const out = [];
  for (let i = 0; i < flat.length; i++) {
    if (flat[i] === "=" && /^[0-9A-F]{2}$/.test(flat.slice(i + 1, i + 3))) { out.push(parseInt(flat.slice(i + 1, i + 3), 16)); i += 2; }
    else out.push(flat.charCodeAt(i));
  }
  return Buffer.from(out).toString("utf8");
};
const htmlOf = (mime) => qpDecode(mime.split("Content-Type: text/html; charset=UTF-8\r\nContent-Transfer-Encoding: quoted-printable\r\n\r\n")[1].split("\r\n--rel_")[0]);
const textOf = (mime) => qpDecode(mime.split("Content-Type: text/plain; charset=UTF-8\r\nContent-Transfer-Encoding: quoted-printable\r\n\r\n")[1].split("\r\n--alt_")[0]);

(async () => {
  await new Promise((r) => stub.listen(STUB, "127.0.0.1", r));
  const env = { ...process.env, NODE_ENV: "production", SHARE_MODE: "1",
    API_URL: STUBURL, API_ID_TOKEN: "stub",
    SHARE_VERIFY_KEY: keys.publicKey.export({ type: "spki", format: "pem" }),
    SHARE_COOKIE_SECRET: SECRET, SHARE_IDP_API_KEY: "k", IDENTITY_TOOLKIT_URL: STUBURL,
    METADATA_URL: STUBURL, SHARE_MAIL_IAM_URL: STUBURL, SHARE_MAIL_OAUTH_URL: STUBURL,
    SHARE_MAIL_GMAIL_URL: STUBURL, SHARE_MAIL_SA: SA,
    SHARE_LEDGER_DIR: ledgerDir, SHARE_SENDS_DIR: sendsDir };
  const web = spawn("node", [path.join(WEB, "node_modules/next/dist/bin/next"), "start", "-p", String(PORT)],
    { cwd: WEB, env, stdio: ["ignore", "ignore", "inherit"] });
  try {
    for (let i = 0; i < 80; i++) { try { await fetch(`${BASE}/proto/app.css`); break; } catch { await wait(500); } }

    console.log("— 1 · the email, from the colleague, branded, and the link works once");
    const A = await mint("Jane Doe <jane@firsttech.com>");
    let ft = await gate(A.token);
    ok(/^\d+\.[\w-]{22}$/.test(ft), "the gate carries a signed form time", ft.slice(0, 18) + "…");
    await wait(1700);
    let r = await post(A.token, { email: "jane@firsttech.com", ft, website: "" });
    let page = await r.text();
    ok(r.status === 200 && /Mishley Otiende/.test(page) && /mishley\.otiende@zennify\.com/.test(page),
      "check-email page names the colleague the email comes from", `${r.status}`);
    ok(gmailOut.length === 1 && gmailOut[0].from === AE && gmailOut[0].to === "jane@firsttech.com" && idpEmails.length === 0,
      "one message, sent from the colleague's own Gmail (delegated); Identity Platform sent nothing",
      `gmail=${gmailOut.length} from=${gmailOut[0] && gmailOut[0].from} idp=${idpEmails.length}`);
    const mime = gmailOut[0].mime, html = htmlOf(mime), text = textOf(mime);
    if (SAVE) fs.writeFileSync(SAVE, html.replace("cid:zennify-wordmark",
      `data:image/png;base64,${fs.readFileSync(path.join(WEB, "public/brand/zennify_wordmark_email.png")).toString("base64")}`));
    ok(/^From: Mishley Otiende <mishley\.otiende@zennify\.com>$/m.test(mime) && /^Reply-To: Mishley Otiende/m.test(mime)
      && /^Auto-Submitted: auto-generated$/m.test(mime), "headers: From and Reply-To the colleague, auto-replies suppressed", "ok");
    ok(/Hi Jane,/.test(text) && /digital maturity assessment is ready/.test(html) && /comparable credit unions/.test(text)
      && /Schedule a walkthrough/.test(html) && !/dashboard/i.test(html + text),
      "greets Jane, says her digital maturity assessment is ready, explains the peer comparison, offers a walkthrough", "ok");
    ok(/First Tech Federal Credit Union/.test(html) && /DIGITAL MATURITY ASSESSMENT/.test(html) && /cid:zennify-wordmark/.test(html)
      && /Content-ID: <zennify-wordmark>/.test(mime) && !/n8n|firebase/i.test(mime),
      "branded HTML with the client's name and the inline Zennify wordmark; no Identity Platform defaults", "ok");
    const link = (text.match(/View your assessment: (\S+)/) || [])[1] || "";
    const hrefs = [...new Set([...html.matchAll(/href="([^"]+)"/g)].map((x) => x[1].replace(/&amp;/g, "&")))]
      .filter((h) => /^https?:/.test(h));
    ok(link.startsWith(`${BASE}/s/${A.token}/verify?`) && /&n=[\w-]{16,}/.test(link) && hrefs.length === 1 && hrefs[0] === link,
      "one link: the button and the text part carry the same sign-in link on the share host", link.replace(A.token, "<token>").slice(0, 80) + "…");
    r = await fetch(link.replace("e=jane%40firsttech.com", "e=cfo%40firsttech.com"), { redirect: "manual" });
    ok(r.status === 401, "the link re-pointed at another address is refused", `${r.status}`);
    r = await fetch(link, { redirect: "manual" });
    const cookie = (r.headers.get("set-cookie") || "").split(";")[0];
    ok(r.status === 303 && cookie.startsWith("dma_share_"), "following the emailed link admits jane", `${r.status}`);
    r = await fetch(`${BASE}/s/${A.token}/api/entity/${ENTITY}/overview`, { headers: { cookie } });
    ok(r.status === 200, "and the dashboard reads", `${r.status}`);
    r = await fetch(link, { redirect: "manual" });
    ok(r.status === 401, "the same link a second time is refused (single use)", `${r.status}`);

    console.log("\n— 2 · valid for the days the link was shared for, once, and not forgeable");
    ok(/works once and stays valid for 7 days, until \d{1,2} \w+ \d{4}/.test(text) && !/minute/.test(text),
      "the email states the link's days, not minutes (a 7-day share)", (text.match(/stays valid for [^.]+/) || [""])[0]);
    const u = new URL(link);
    u.searchParams.set("n", u.searchParams.get("n").slice(0, -1) + (u.searchParams.get("n").endsWith("A") ? "B" : "A"));
    r = await fetch(u, { redirect: "manual" });
    ok(r.status === 401, "an edited code is refused", `${r.status}`);
    const v = new URL(link); v.searchParams.set("i", String(Number(v.searchParams.get("i")) - 86400));
    r = await fetch(v, { redirect: "manual" });
    ok(r.status === 401, "a re-dated code breaks its signature", `${r.status}`);
    const reuse = await mint("Victor Park <vp@firsttech.com>", AE, "Mishley Otiende", "after_first_call");
    let ft2 = await gate(reuse.token); await wait(1700);
    await post(reuse.token, { email: "vp@firsttech.com", ft: ft2 }, "203.0.113.70");
    const vpText = textOf(gmailOut[gmailOut.length - 1].mime), vpHtml = htmlOf(gmailOut[gmailOut.length - 1].mime);
    ok(/^Hi Victor,/.test(vpText) && /Thank you for your time on our recent call/.test(vpText) && />Book a follow-up call</.test(vpHtml)
      && !/walkthrough/i.test(vpText + vpHtml),
      "a link shared after the first sales call → the email thanks them and asks for a follow-up call", "ok");
    const vpLink = (vpText.match(/View your assessment: (\S+)/) || [])[1];
    const clicks = await Promise.all(Array.from({ length: 15 }, () => fetch(vpLink, { redirect: "manual" })));
    ok(clicks.filter((x) => x.status === 303).length === 1, "15 simultaneous clicks on one emailed link admit once",
      [...new Set(clicks.map((x) => x.status))].join(","));

    console.log("\n— 3 · bot traps send nothing");
    const B = await mint("ops@firsttech.com");
    const before = gmailOut.length + idpEmails.length;
    ft = await gate(B.token); await wait(1700);
    r = await post(B.token, { email: "ops@firsttech.com", ft, website: "https://cheap-pills.example" });
    ok(r.status === 200 && gmailOut.length + idpEmails.length === before, "honeypot filled → a normal-looking page, no email", `${r.status}`);
    ft = await gate(B.token);
    r = await post(B.token, { email: "ops@firsttech.com", ft, website: "" });
    ok(r.status === 200 && gmailOut.length + idpEmails.length === before, "submitted faster than a person types → no email", `${r.status}`);
    r = await post(B.token, { email: "ops@firsttech.com" });
    ok(r.status === 400 && gmailOut.length + idpEmails.length === before, "no form time (a scripted POST) → page shown again, no email", `${r.status}`);
    r = await post(B.token, { email: "ops@firsttech.com", ft: `${Date.now() - 5000}.AAAAAAAAAAAAAAAAAAAAAA` });
    ok(r.status === 400 && gmailOut.length + idpEmails.length === before, "a forged form time → no email", `${r.status}`);

    console.log("\n— 4 · budgets: one address, hammered");
    ft = await gate(B.token); await wait(1700);
    r = await post(B.token, { email: "ops@firsttech.com", ft });
    ok(r.status === 200 && gmailOut.length === before + 1, "first request sends", `${r.status}`);
    const again = await Promise.all(Array.from({ length: 30 }, () => post(B.token, { email: "ops@firsttech.com", ft })));
    ok(again.every((x) => x.status === 429) && gmailOut.length === before + 1,
      "30 more within the minute → all 429, still exactly one email", [...new Set(again.map((x) => x.status))].join(","));
    page = await again[0].text();
    ok(/less than a minute ago/.test(page), "the page says when to try again", "cooldown message");

    console.log("\n— 5 · a parallel burst from a fresh address");
    const C = await mint("cfo@firsttech.com");
    ft = await gate(C.token); await wait(1700);
    const n0 = gmailOut.length;
    const burst = await Promise.all(Array.from({ length: 40 }, () => post(C.token, { email: "cfo@firsttech.com", ft })));
    ok(gmailOut.length - n0 === 1, "40 simultaneous requests → exactly one email", `sent=${gmailOut.length - n0} statuses=${[...new Set(burst.map((x) => x.status))].join(",")}`);

    console.log("\n— 6 · domain enumeration under a shared link");
    const D = await mint("jane@bcu.com");
    ft = await gate(D.token); await wait(1700);
    const n1 = gmailOut.length;
    const guesses = await Promise.all(Array.from({ length: 120 }, (_, i) =>
      post(D.token, { email: `guess${i}.${crypto.randomBytes(2).toString("hex")}@bcu.com`, ft }, `198.51.${i}.1`)));
    const sentGuess = gmailOut.length - n1;
    ok(sentGuess <= 15 && sentGuess >= 1, "120 made-up @bcu.com addresses → capped at 15 emails for the link",
      `sent=${sentGuess} 429s=${guesses.filter((x) => x.status === 429).length}`);
    r = await post(D.token, { email: "jane@bcu.com", ft }, "203.0.113.50");
    ok(r.status === 200 || r.status === 429, "the named recipient is a separate budget from guesses", `${r.status}`);

    console.log("\n— 7 · off-list addresses never get anything");
    const n2 = gmailOut.length + idpEmails.length;
    const off = await Promise.all(Array.from({ length: 100 }, (_, i) =>
      post(A.token, { email: `x${i}@evil-${i}.example`, ft }, `192.0.2.${i % 250}`)));
    ok(off.every((x) => x.status === 403) && gmailOut.length + idpEmails.length === n2,
      "100 off-list addresses → 403, zero emails", [...new Set(off.map((x) => x.status))].join(","));

    console.log("\n— 8 · fallbacks are safe and logged");
    const E = await mint("it@firsttech.com", "qa.tester@example.com", "QA");
    ft = await gate(E.token); await wait(1700);
    const g0 = gmailOut.length, i0 = idpEmails.length;
    r = await post(E.token, { email: "it@firsttech.com", ft });
    ok(r.status === 200 && gmailOut.length === g0 && idpEmails.length === i0 + 1,
      "a link shared by someone outside zennify.com → Identity Platform sends (no spoofed sender)", `graph+${gmailOut.length - g0} idp+${idpEmails.length - i0}`);
    gmailMode = "deny";
    const F = await mint("risk@firsttech.com");
    ft = await gate(F.token); await wait(1700);
    r = await post(F.token, { email: "risk@firsttech.com", ft });
    ok(r.status === 200 && idpEmails.length === i0 + 2, "Gmail refusing the colleague's mailbox → one Identity Platform email instead, not two", `idp+${idpEmails.length - i0}`);
    gmailMode = "ok";

    console.log("\n— 9 · the budget store failing fails closed");
    const G = await mint("audit@firsttech.com");
    ft = await gate(G.token); await wait(1700);
    // The store path stops being a directory (works as root, unlike chmod).
    fs.renameSync(sendsDir, `${sendsDir}.away`); fs.writeFileSync(sendsDir, "not a directory");
    const n3 = gmailOut.length + idpEmails.length;
    r = await post(G.token, { email: "audit@firsttech.com", ft });
    ok(r.status === 503 && gmailOut.length + idpEmails.length === n3, "budget store unreadable → 503, nothing sent", `${r.status}`);
    fs.unlinkSync(sendsDir); fs.renameSync(`${sendsDir}.away`, sendsDir);

    console.log(`\nTotals: Gmail emails ${gmailOut.length}, Identity Platform emails ${idpEmails.length}, ` +
      `gate requests ${1 + 4 + 31 + 40 + 121 + 100 + 4}`);
  } finally {
    web.kill(); stub.close();
  }
  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
