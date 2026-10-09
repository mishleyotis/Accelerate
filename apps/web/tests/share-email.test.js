/* The client sign-in email, and the safeguards around sending it.
 *
 * Owner, 2026-10-09: the Identity Platform default ("Sign in to n8n…" from
 * noreply@…firebaseapp.com) read as generic and landed in spam. The email is
 * now professional, Zennify-branded, sent from the colleague who shared the
 * dashboard — and "there are safeguards against [it] being spammed … the link
 * sharing does not lead to spamming".
 *
 * Asserted, not described: what the email says and does not say, the MIME it
 * travels in, every send budget (including a parallel burst), failing closed,
 * the gate's bot traps, the 60-minute link clock, and who the sender is.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const E = require("../lib/share-email.js");
const T = require("../lib/share-throttle.js");
const M = require("../lib/share-mailer.js");

const NOW = Date.parse("2026-10-09T15:21:00Z");
const LINK = "https://dmai-share-x.a.run.app/s/abc.def/verify?e=jane%40firsttech.com&i=1&s=x&oobCode=CODE";
const AE = { name: "Mishley Otiende", email: "mishley.otiende@zennify.com" };
const UNTIL = Date.parse("2026-11-08T15:21:00Z");   // a link shared for 30 days
const mail = (over = {}) => E.signInEmail({ client: "First Tech Federal Credit Union", subVertical: "CU",
  recipient: "jane@firsttech.com", recipientName: "Jane Doe", ae: AE, link: LINK,
  requestedAt: NOW, validUntil: UNTIL, ...over });

function qpDecode(s) {
  const flat = s.replace(/=\r\n/g, "");
  const bytes = [];
  for (let i = 0; i < flat.length; i++) {
    if (flat[i] === "=" && /^[0-9A-F]{2}$/.test(flat.slice(i + 1, i + 3))) {
      bytes.push(parseInt(flat.slice(i + 1, i + 3), 16)); i += 2;
    } else bytes.push(flat.charCodeAt(i));
  }
  return Buffer.from(bytes).toString("utf8");
}

test("the email greets the recipient, says it is their digital maturity assessment, and the days it stays valid", () => {
  const m = mail();
  assert.strictEqual(m.subject, "Your First Tech Federal Credit Union digital maturity assessment is ready");
  for (const part of [m.text, m.html]) {
    assert.match(part, /Hi Jane,/, "the recipient is greeted by name, not 'Hello'");
    assert.match(part, /digital maturity assessment/);
    assert.ok(!/dashboard/i.test(part), "owner: 'not dashboard'");
    assert.match(part, /Mishley Otiende/);
    assert.match(part, /jane@firsttech\.com/);
    assert.match(part, /works once and stays valid for 30 days, until 8 November 2026/);
    assert.ok(!/minute/.test(part), "the link's lifetime is days, not minutes (owner, 2026-10-09)");
    assert.match(part, /9 October 2026 at 15:21 UTC/);
    assert.match(part, /© 2026 Zennify \| Confidential|&copy; 2026 Zennify \| Confidential/);
    assert.ok(!/n8n|firebase/i.test(part), "Identity Platform's defaults leaked into the email");
  }
  assert.match(m.html, /Your First Tech Federal Credit Union digital maturity assessment is ready<\/h1>/);
  assert.match(m.preheader, /benchmarked against comparable credit unions/);
});

test("it explains how the client performs against its peers, and what is inside", () => {
  const { text, html } = mail();
  assert.match(text, /Would you like to know how First Tech Federal Credit Union performs against its peers\?/);
  assert.match(text, /four pillars: strategy and governance, customer experience, operations and risk, and data and technology/);
  assert.match(text, /benchmarked against comparable credit unions/);
  for (const line of ["Your overall maturity score, and your score in each pillar",
                      "How you compare with peer credit unions",
                      "The insights and opportunities that matter most to your organisation"]) {
    assert.ok(text.includes(line) && html.includes(line), line);
  }
  assert.match(html, />View your assessment</);
  assert.match(mail({ subVertical: "SV2 — Credit Unions" }).text, /comparable credit unions/);
  assert.match(mail({ subVertical: null }).text, /comparable institutions/);
});

test("a follow-up call to action: schedule a walkthrough with the colleague, or reply", () => {
  const { text, html } = mail();
  assert.match(html, /Talk through your results/);
  const mailto = (html.match(/href="(mailto:[^"]+)"/) || [])[1];
  assert.ok(mailto, "no walkthrough link");
  const u = new URL(mailto.replace(/&amp;/g, "&"));
  assert.strictEqual(u.pathname, "mishley.otiende@zennify.com");
  assert.strictEqual(u.searchParams.get("subject"), "Digital maturity assessment walkthrough: First Tech Federal Credit Union");
  assert.match(html, />Schedule a walkthrough</);
  assert.match(text, /Reply to this email to schedule a walkthrough with Mishley/);
});

test("the greeting: a given name, a first.last address, then the client's team — never a guess", () => {
  assert.match(mail({ recipientName: "Lee, Ann" }).text, /^Hi Ann,/);
  assert.match(mail({ recipientName: null, recipient: "sam.lee@firsttech.com" }).text, /^Hi Sam,/);
  assert.match(mail({ recipientName: null, recipient: "cfo@firsttech.com" }).text, /^Dear First Tech Federal Credit Union team,/);
  assert.match(mail({ recipientName: null, recipient: "jdoe@x.com", client: null }).text, /^Hello,/);
});

test("Zennify branding: the design-system palette, DM Sans, the inline wordmark, sentence case", () => {
  const { html } = mail();
  for (const hex of ["#185F60", "#1C4A4D", "#27BBAF", "#139F94", "#F2F4F9", "#E8F7F6"]) {
    assert.ok(html.includes(hex), `brand colour ${hex} missing`);
  }
  assert.match(html, /'DM Sans', Arial, Helvetica, sans-serif/);
  assert.match(html, /<img src="cid:zennify-wordmark"[^>]*alt="Zennify"/);
  assert.match(html, /DIGITAL MATURITY ASSESSMENT/, "the eyebrow is the one ALL CAPS line");
  assert.match(html, /Your First Tech Federal Credit Union digital maturity assessment is ready/);
  assert.ok(!/box-shadow|linear-gradient/.test(html), "no shadows or gradients (design system)");
  assert.ok(!/[—–]/.test(html + mail().text), "no em or en dashes (design system)");
  const logo = E.wordmark();
  assert.ok(logo && logo.length < 40000 && logo.slice(1, 4).toString() === "PNG", "the wordmark asset ships");
});

test("spam hygiene: one destination, no remote images or tracking, no urgency, a full text part", () => {
  const m = mail();
  const hrefs = [...m.html.matchAll(/href="([^"]+)"/g)].map((x) => x[1].replace(/&amp;/g, "&"));
  assert.deepStrictEqual(hrefs.filter((h) => /^https?:/.test(h)), [LINK], "one web link: the sign-in button");
  assert.deepStrictEqual(hrefs.filter((h) => !/^https?:/.test(h)).map((h) => h.split("?")[0]),
    ["mailto:mishley.otiende@zennify.com"], "the only other link is the walkthrough mailto to the colleague");
  const srcs = [...m.html.matchAll(/src="([^"]+)"/g)].map((x) => x[1]);
  assert.deepStrictEqual(srcs, ["cid:zennify-wordmark"], "a remote image or tracking pixel appeared");
  assert.ok(!/<script|<form|<iframe|javascript:/i.test(m.html));
  assert.ok(!/!/.test(m.subject + m.text), "exclamation marks read as marketing");
  assert.ok(!/\b(click here|urgent|act now|free|winner|guarantee|limited time|verify your account)\b/i
    .test(m.subject + m.text + m.html), "a spam-trigger phrase appeared");
  assert.ok(m.subject !== m.subject.toUpperCase() && m.subject.length <= 100);
  assert.ok(m.text.includes(LINK), "the text part does not carry the link");
  assert.match(m.text, /no further emails will be sent unless another link is requested/);
  assert.ok(Buffer.byteLength(m.html) < 20000, "the HTML is bloated");
});

test("client and colleague names are escaped, and a missing name still reads properly", () => {
  const m = mail({ client: `Acme <script>alert(1)</script> & "Co"`, recipientName: `<b>Jane</b>`, ae: { email: "jdoe@zennify.com" } });
  assert.ok(!m.html.includes("<script>alert") && !m.html.includes("<b>Jane"), "a name was not escaped");
  assert.match(m.html, /Acme &lt;script&gt;alert\(1\)&lt;\/script&gt; &amp; &quot;Co&quot;/);
  assert.match(m.text, /Your Zennify contact/);
  const anon = mail({ client: null, ae: { email: "ana.lopez@zennify.com" } });
  assert.strictEqual(anon.subject, "Your digital maturity assessment is ready");
  assert.match(anon.text, /Kind regards,\nAna Lopez\nZennify/);
  assert.strictEqual(E.nameFromEmail("it.ops2@x.com"), null, "a guessed name is worse than none");
});

test("the MIME message: CRLF, folded headers, text + related HTML + inline wordmark, auto-reply suppressed", () => {
  const m = mail();
  const raw = E.buildMime({ from: AE, to: "jane@firsttech.com", subject: m.subject, text: m.text,
                            html: m.html, now: NOW, rand: (() => { let i = 0; return () => `r${i++}`; })() });
  assert.ok(!/[^\r]\n/.test(raw), "a bare LF");
  for (const line of raw.split("\r\n")) assert.ok(line.length <= 78, `line too long: ${line.slice(0, 60)}`);
  const cut = raw.indexOf("\r\n\r\n");
  const head = raw.slice(0, cut), body = raw.slice(cut + 4);
  assert.match(head, /^From: Mishley Otiende <mishley\.otiende@zennify\.com>$/m);
  assert.match(head, /^Reply-To: Mishley Otiende <mishley\.otiende@zennify\.com>$/m);
  assert.match(head, /^To: <jane@firsttech\.com>$/m);
  assert.match(head, /^Message-ID: <r\d+@zennify\.com>$/m);
  assert.match(head, /^Auto-Submitted: auto-generated$/m);
  assert.match(head, /^X-Auto-Response-Suppress: All$/m);
  assert.match(head, /^Date: Fri, 09 Oct 2026 15:21:00 \+0000$/m);
  assert.match(head.replace(/\r\n /g, " "), /^Subject: Your First Tech Federal Credit Union digital maturity assessment is ready$/m);
  const order = ["text/plain", "multipart/related", "text/html", "image/png"].map((t) => body.indexOf(`Content-Type: ${t}`));
  assert.ok(order.every((x, i) => x > 0 && (i === 0 || x > order[i - 1])), `part order ${order}`);
  assert.match(body, /Content-ID: <zennify-wordmark>/);
  const textPart = body.split("Content-Transfer-Encoding: quoted-printable\r\n\r\n")[1].split("\r\n--")[0];
  assert.strictEqual(qpDecode(textPart), m.text.replace(/\n/g, "\r\n"), "the text part does not round-trip");
});

test("quoted-printable encodes '=', non-ASCII and trailing space, and keeps lines short", () => {
  const out = E.qp("a=b © naïve \nend ");
  assert.match(out, /a=3Db =C2=A9 na=C3=AFve=20\r\nend=20/);
  const long = E.qp("x".repeat(300));
  for (const l of long.split("\r\n")) assert.ok(l.length <= 76);
});

/* ── Budgets ───────────────────────────────────────────────────────── */
const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), "sends-"));
const store = () => T.throttleBackend({ SHARE_SENDS_DIR: tmp() });
const req = (over = {}) => ({ jti: "linkAAAA01", email: "jane@bcu.com", listed: true,
                              sender: "ae@zennify.com", ip: "203.0.113.9", ...over });

test("one email per address per minute; four an hour; eight a day", async () => {
  const s = store();
  assert.deepStrictEqual(await T.admitSend(req(), s, NOW), { ok: true });
  const again = await T.admitSend(req(), s, NOW + 5000);
  assert.strictEqual(again.reason, "cooldown");
  assert.ok(again.retryAfter >= 1 && again.retryAfter <= 60);
  let t = NOW;
  for (let i = 1; i < 4; i++) { t += 61e3; assert.strictEqual((await T.admitSend(req(), s, t)).ok, true, `send ${i + 1}`); }
  const hour = await T.admitSend(req(), s, t + 61e3);
  assert.strictEqual(hour.reason, "address");
  assert.strictEqual(hour.limit, "addrHour");
});

test("a link's unlisted (domain-matched) addresses are capped — enumeration cannot flood bounces", async () => {
  const s = store();
  let sent = 0, reason = null;
  for (let i = 0; i < 40; i++) {
    const r = await T.admitSend(req({ email: `guess${i}@bcu.com`, listed: false, ip: `198.51.100.${i}` }), s, NOW + i);
    if (r.ok) sent++; else reason = r.limit;
  }
  assert.strictEqual(sent, T.LIMITS.unlisted[0]);
  assert.strictEqual(reason, "unlisted");
});

test("a link, a colleague, a network and the whole service each have a ceiling", async () => {
  const lim = { ...T.LIMITS, linkHour: [3, 3600], senderDay: [5, 86400], ipHour: [4, 3600], globalDay: [7, 86400] };
  const s = store();
  const names = [];
  for (let i = 0; i < 12; i++) {
    const r = await T.admitSend(req({ jti: `link${i % 3}AAAAA`, email: `p${i}@bcu.com`, ip: `192.0.2.${i}` }), s, NOW + i, lim);
    names.push(r.ok ? "ok" : r.limit);
  }
  assert.strictEqual(names.filter((n) => n === "ok").length, 5, names.join(","));
  assert.ok(names.includes("senderDay"), names.join(","));
  const s2 = store();
  const ip = [];
  for (let i = 0; i < 6; i++) ip.push((await T.admitSend(req({ email: `q${i}@bcu.com`, sender: null }), s2, NOW + i, lim)).limit || "ok");
  assert.deepStrictEqual(ip.slice(0, 3), ["ok", "ok", "ok"]);
  assert.ok(ip.includes("ipHour") || ip.includes("linkHour"), ip.join(","));
});

test("a parallel burst for one address sends exactly once", async () => {
  const s = store();
  const results = await Promise.all(Array.from({ length: 50 }, () => T.admitSend(req(), s, NOW)));
  assert.strictEqual(results.filter((r) => r.ok).length, 1, "a burst got more than one email out");
  assert.ok(results.filter((r) => !r.ok).every((r) => r.reason === "cooldown"));
});

test("a parallel burst across a shared domain never passes the link's cap", async () => {
  const s = store();
  const results = await Promise.all(Array.from({ length: 80 }, (_, i) =>
    T.admitSend(req({ email: `x${i}@bcu.com`, listed: false, ip: `10.0.${i}.1` }), s, NOW)));
  const sent = results.filter((r) => r.ok).length;
  assert.ok(sent >= 1 && sent <= T.LIMITS.unlisted[0], `${sent} sent; the cap is ${T.LIMITS.unlisted[0]}`);
  assert.ok(results.every((r) => r.ok || r.reason !== "unavailable"), "contention surfaced as an outage");
});

test("the budget store failing means nothing is sent (fail closed)", async () => {
  const broken = { kind: "x", count: async () => { throw new Error("bucket 503"); }, bump: async () => 1 };
  const r = await T.admitSend(req(), broken, NOW);
  assert.strictEqual(r.ok, false);
  assert.strictEqual(r.reason, "unavailable");
});

test("the client IP is Cloud Run's last X-Forwarded-For hop, never a spoofable first one", () => {
  const h = (v) => ({ headers: new Map([["x-forwarded-for", v]]) });
  assert.strictEqual(T.clientIp(h("6.6.6.6, 203.0.113.9")), "203.0.113.9");
  assert.strictEqual(T.clientIp(h("203.0.113.9")), "203.0.113.9");
  assert.strictEqual(T.clientIp(h("")), "unknown");
});

/* ── The gate form's bot traps, and the link's clock ──────────────── */
const SECRET = "s".repeat(48);
test("bot traps: a filled honeypot or an instant submission sends nothing; a stale form is re-shown", () => {
  const ft = T.formToken("linkAAAA01", SECRET, NOW);
  assert.strictEqual(T.judgeForm("linkAAAA01", { ft, website: "" }, SECRET, NOW + 4000), "ok");
  assert.strictEqual(T.judgeForm("linkAAAA01", { ft, website: "http://spam" }, SECRET, NOW + 4000), "bot");
  assert.strictEqual(T.judgeForm("linkAAAA01", { ft }, SECRET, NOW + 200), "bot");
  assert.strictEqual(T.judgeForm("linkAAAA01", { ft }, SECRET, NOW + 3 * 3600e3), "stale");
  assert.strictEqual(T.judgeForm("linkAAAA01", { ft: "" }, SECRET, NOW), "stale");
  assert.strictEqual(T.judgeForm("linkBBBB02", { ft }, SECRET, NOW + 4000), "stale", "a form token moved to another link");
  assert.strictEqual(T.judgeForm("linkAAAA01", { ft: `${NOW - 9000}.forged` }, SECRET, NOW), "stale");
});

test("the emailed link is valid for the share link's days, works once, and cannot be moved or forged", async () => {
  const P = { jti: "linkAAAA01", iat: Math.floor(NOW / 1000), exp: Math.floor(UNTIL / 1000) };
  const c = T.signSignIn(P.jti, "jane@bcu.com", SECRET, NOW);
  assert.strictEqual(T.checkSignIn(P, "jane@bcu.com", c.i, c.n, c.s, SECRET, NOW + 29 * 86400e3), "ok",
    "a day-29 click on a 30-day link works");
  assert.strictEqual(T.checkSignIn(P, "jane@bcu.com", c.i, c.n, c.s, SECRET, UNTIL + 1000), "expired");
  assert.strictEqual(T.checkSignIn(P, "cfo@bcu.com", c.i, c.n, c.s, SECRET, NOW), "invalid", "moved to another address");
  assert.strictEqual(T.checkSignIn({ ...P, jti: "linkBBBB02" }, "jane@bcu.com", c.i, c.n, c.s, SECRET, NOW), "invalid",
    "moved to another link");
  assert.strictEqual(T.checkSignIn(P, "jane@bcu.com", c.i, `${c.n}x`, c.s, SECRET, NOW), "invalid", "nonce edited");
  assert.strictEqual(T.checkSignIn(P, "jane@bcu.com", c.i - 9e6, c.n, c.s, SECRET, NOW), "invalid", "re-dated");
  assert.strictEqual(T.checkSignIn(P, "jane@bcu.com", c.i, c.n, c.s, null, NOW), "invalid", "no secret, no admission");
  const s = store();
  assert.strictEqual(await T.claimNonce(c.n, s), true, "first use");
  assert.strictEqual(await T.claimNonce(c.n, s), false, "second use refused");
  const race = await Promise.all(Array.from({ length: 20 }, () => T.claimNonce("raceNonceAAAAAAAAAAAA", s)));
  assert.strictEqual(race.filter(Boolean).length, 1, "20 simultaneous clicks admit once");
  const notADir = path.join(tmp(), "file");
  fs.writeFileSync(notADir, "x");
  const broken = T.throttleBackend({ SHARE_SENDS_DIR: notADir });
  await assert.rejects(T.claimNonce("zzzzzzzzzzzzzzzzzzzz", broken), "an unreadable store must refuse, not admit");
});

/* ── Who sends ─────────────────────────────────────────────────────── */
const CFG = M.mailerConfig({ SHARE_MAIL_SA: "dmai-share@digital-maturity-assessor.iam.gserviceaccount.com" });
test("the sender is the colleague who shared the link, or who re-added this address — in a sender domain only", () => {
  const rec = { minted_by: "Mishley.Otiende@zennify.com", minted_by_name: "Mishley Otiende" };
  assert.deepStrictEqual(M.senderFor(rec, null, "jane@bcu.com", CFG),
    { email: "mishley.otiende@zennify.com", name: "Mishley Otiende" });
  const rev = { history: [{ action: "remove", target: "jane@bcu.com", by: "admin.one@zennify.com" },
                          { action: "readd", target: "bcu.com", by: "sam.lee@zennify.com" }] };
  assert.deepStrictEqual(M.senderFor(rec, rev, "jane@bcu.com", CFG), { email: "sam.lee@zennify.com", name: "Sam Lee" });
  assert.strictEqual(M.senderFor({ minted_by: "qa@example.com" }, null, "jane@bcu.com", CFG), null,
    "a sender outside zennify.com cannot be impersonated — Identity Platform sends instead");
  assert.strictEqual(M.senderFor(null, null, "jane@bcu.com", CFG), null, "an unrecorded link has no sender");
  assert.strictEqual(M.senderFor(rec, null, "jane@bcu.com", null), null, "no mailer configured");
  assert.strictEqual(M.mailerConfig({ SHARE_MAIL_SA: "someone@gmail.com" }), null, "only a service account may sign");
  assert.deepStrictEqual(CFG.domains, ["zennify.com"]);
});

test("recipients may carry a name — it greets them, and never reaches the signed link", () => {
  const S = require("../lib/share.js");
  const box = `Jane Doe <jane@firsttech.com>, sam@firsttech.com; "Lee, Ann" <ann.lee@firsttech.com>`;
  assert.deepStrictEqual(S.allowlistFor(box),
    { m: ["ann.lee@firsttech.com", "jane@firsttech.com", "sam@firsttech.com"], d: ["firsttech.com"] });
  assert.deepStrictEqual(S.recipientNames(box), { "jane@firsttech.com": "Jane Doe", "ann.lee@firsttech.com": "Lee, Ann" });
  assert.deepStrictEqual(S.allowlistFor("a@x.com b@x.com").m, ["a@x.com", "b@x.com"], "space-separated still works");
  for (const bad of ["jane@firsttech.com, notanemail", "Jane <not-an-email>", "<script>@x"]) {
    assert.throws(() => S.allowlistFor(bad), /not an email address/, bad);
  }
  const crypto = require("node:crypto");
  const k = crypto.generateKeyPairSync("ed25519");
  const { token } = S.mint({ entity: "first-tech-federal-credit-union", run: "r1", recipients: box }, k.privateKey);
  assert.ok(!Buffer.from(token.split(".")[0], "base64url").toString().includes("Jane"), "a name was signed into the link");
});

test("after the first sales call: thanks them for the call and asks for a follow-up call", () => {
  const S = require("../lib/share.js");
  assert.deepStrictEqual(S.SHARE_STAGES, ["before_first_call", "after_first_call"]);
  const after = mail({ stage: "after_first_call" });
  assert.match(after.text, /^Hi Jane,\n\nThank you for your time on our recent call\. As promised, here is First Tech Federal Credit Union's digital maturity assessment\./);
  assert.match(after.html, />Book your follow-up call</);
  assert.match(after.html, />Book a follow-up call</);
  assert.match(after.text, /Reply to this email to book a follow-up call with Mishley/);
  const mailto = new URL((after.html.match(/href="(mailto:[^"]+)"/) || [])[1].replace(/&amp;/g, "&").replace(/&#39;/g, "'"));
  assert.strictEqual(mailto.searchParams.get("subject"), "Follow-up call: First Tech Federal Credit Union digital maturity assessment");
  assert.ok(!/walkthrough/i.test(after.text + after.html), "the post-call email still offers the first walkthrough");
  // Everything else holds: greeting, peers, single use for the link's days.
  assert.match(after.text, /benchmarked against comparable credit unions/);
  assert.match(after.text, /stays valid for 30 days, until 8 November 2026/);

  const before = mail({ stage: "before_first_call" });
  assert.match(before.text, /I am pleased to share/);
  assert.match(before.html, />Schedule a walkthrough</);
  assert.ok(!/recent call|follow-up call/i.test(before.text), "the pre-call email mentions a call that has not happened");
  assert.strictEqual(mail({ stage: undefined }).text, before.text, "a link recorded before the question defaults to pre-call");
});

test("the client's call stage is remembered: the newest link for that client wins", async () => {
  const S = require("../lib/share.js");
  const L = require("../lib/share-ledger.js");
  const crypto = require("node:crypto");
  const k = crypto.generateKeyPairSync("ed25519");
  const dir = L.dirBackend(tmp());
  const rec = async (entity, at, stage) => {
    const { payload } = S.mint({ entity, run: "r1", recipients: "jane@bcu.com" }, k.privateKey, Date.parse(at));
    await L.recordLink(payload, "mishley.otiende@zennify.com", dir, "Mishley Otiende", {}, stage);
  };
  assert.strictEqual(await L.latestStageFor("first-tech", dir), null, "nothing recorded yet");
  await rec("first-tech", "2026-10-01T09:00:00Z", "before_first_call");
  await rec("first-tech", "2026-10-05T09:00:00Z", "after_first_call");
  await rec("first-tech", "2026-10-07T09:00:00Z", null);              // recorded before the question
  await rec("other-client", "2026-10-08T09:00:00Z", "before_first_call");
  const last = await L.latestStageFor("first-tech", dir);
  assert.strictEqual(last.stage, "after_first_call");
  assert.strictEqual(last.minted_by, "mishley.otiende@zennify.com");
  assert.match(last.minted_at, /^2026-10-05/);
  assert.strictEqual((await L.latestStageFor("other-client", dir)).stage, "before_first_call", "clients do not bleed");
});
