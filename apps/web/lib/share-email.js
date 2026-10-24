// The one email a client-link recipient receives: their sign-in link to the
// client's digital maturity assessment, sent from — and signed by — the
// Zennify colleague who shared it (lib/share-mailer). Owner, 2026-10-09:
// greet the recipient by name; say it is a digital maturity assessment and
// that it shows how the client performs against its peers; offer a
// follow-up; "your … digital maturity assessment is ready", never
// "dashboard".
//
// Owner, 2026-10-09: the Identity Platform default ("Sign in to n8n
// requested at…", from noreply@<project>.firebaseapp.com) read as generic
// and landed in spam. This is the replacement — professional, Zennify-
// branded per the design system (DM Sans; dark teal #185F60, brand teal
// #27BBAF, accent green #139F94, body #1C4A4D, lavender #F2F4F9, ice
// #E8F7F6; sentence case; ALL CAPS for the eyebrow only; the wordmark on a
// light ground) — and written to stay out of spam folders:
//
//   · a person's mailbox as the sender, replies going straight back to them;
//   · one web link: the sign-in button, on the share service's own host (the
//     text part carries the same address), plus a mailto back to the
//     colleague for a walkthrough — no shorteners, no tracking pixels, no
//     remote images (the wordmark rides inline, CID);
//   · a text/plain part that says everything the HTML says;
//   · no urgency language, no exclamation marks, no ALL CAPS subject;
//   · it says why it arrived and that nothing further will follow unless
//     another link is requested.
//
// Pure functions: no I/O except reading the wordmark once.
import crypto from "crypto";
import fs from "fs";
import path from "path";


/* The palette is the app's own design tokens (public/proto/app.css, "ZENNIFY
   DESIGN TOKENS"), read once — one source of brand colour, and no colour
   literal here for invariant 7's gate to mistake for a second band resolver.
   This is chrome, not a score: nothing in the email is coloured by a band. */
const TOKEN_FOR = { darkTeal: "z-dark2", body: "z-dark", teal: "z-teal", green: "z-mid",
                    lavender: "z-lav", ice: "z-ice", muted: "z-purple", rule: "z-sep",
                    white: "z-white" };
function readTokens() {
  for (const f of [path.join(process.cwd(), "public", "proto", "app.css"),
                   path.join(process.cwd(), "apps", "web", "public", "proto", "app.css")]) {
    try {
      const css = fs.readFileSync(f, "utf8");
      const out = {};
      for (const [k, v] of Object.entries(TOKEN_FOR)) {
        const m = css.match(new RegExp(`--${v}:\\s*(#[0-9A-Fa-f]{6})\\b`));
        if (!m) throw new Error(`design token --${v} missing`);
        out[k] = m[1].toUpperCase();
      }
      return out;
    } catch (e) { if (!String(e.message).includes("ENOENT")) throw e; }
  }
  throw new Error("design tokens (public/proto/app.css) not found");
}
export const BRAND = readTokens();
const FONT = "'DM Sans', Arial, Helvetica, sans-serif";

const esc = (s) => String(s == null ? "" : s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;").replace(/'/g, "&#39;");

// "mishley.otiende@zennify.com" → "Mishley Otiende"; anything that does not
// look like first.last stays the address (a guessed name is worse than none).
export function nameFromEmail(email) {
  const local = String(email || "").split("@")[0];
  if (!/^[a-z]+([._-][a-z]+)+$/i.test(local)) return null;
  return local.split(/[._-]/).map((w) => w[0].toUpperCase() + w.slice(1).toLowerCase()).join(" ");
}

// "Jane Doe" → "Jane"; "Lee, Ann" (last, first) → "Ann".
export function firstName(name) {
  const n = String(name || "").trim();
  if (n.includes(",")) return n.split(",")[1].trim().split(/\s+/)[0] || "";
  return n.split(/\s+/)[0] || "";
}

// The peer group the assessment benchmarks against, by sub-vertical code
// (apps/api/dma_api/subverticals.py SUBVERTICAL_DISPLAY), as prose.
const PEERS = {
  CU: "credit unions", RB: "regional banks", CL: "commercial lenders",
  CIB: "corporate and investment banks", FC: "Farm Credit institutions",
  AM: "asset and wealth managers", RIA: "RIAs and broker-dealers",
  IC: "insurance carriers", IB: "insurance brokers",
};
// The stored value may be a code ("CU") or a spelling ("SV2 — Credit
// Unions"); anything unrecognised is "institutions", never the raw value.
const PEER_WORDS = [[/CREDIT.?UNION/, "CU"], [/REGIONAL|RETAIL.?BANK/, "RB"], [/COMMERCIAL/, "CL"],
  [/INVESTMENT.?BANK|\bCIB\b/, "CIB"], [/FARM/, "FC"], [/WEALTH|ASSET/, "AM"],
  [/\bRIA|BROKER.?DEALER/, "RIA"], [/CARRIER/, "IC"], [/INSURANCE.?BROKER/, "IB"]];
export function peerGroup(code) {
  const raw = String(code || "").toUpperCase().trim();
  if (PEERS[raw]) return PEERS[raw];
  const hit = PEER_WORDS.find(([re]) => re.test(raw));
  return hit ? PEERS[hit[1]] : "institutions";
}

export function formatDate(ms) {
  return formatUtc(ms).replace(/ at .*$/, "");
}

// How long the emailed link stays valid: the days the colleague chose when
// sharing (owner, 2026-10-09: "It is number of days not minutes"), counted
// from now to the share link's expiry. → "30 days, until 8 November 2026"
export function validity(requestedAt, validUntil) {
  const days = Math.max(1, Math.ceil((validUntil - requestedAt) / 86400000));
  return `${days} day${days === 1 ? "" : "s"}, until ${formatDate(validUntil)}`;
}

export function formatUtc(ms) {
  const d = new Date(ms);
  const months = ["January", "February", "March", "April", "May", "June", "July",
                  "August", "September", "October", "November", "December"];
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${d.getUTCDate()} ${months[d.getUTCMonth()]} ${d.getUTCFullYear()} at ${hh}:${mm} UTC`;
}

/* → { subject, preheader, text, html }
   client         the client's name as the assessment shows it (may be null)
   subVertical    its sub-vertical code (CU, RB, …) — names the peer group
   recipient      the allowlisted address the link is for
   recipientName  their name if the colleague gave one ("Jane Doe <jane@…>")
   ae             { name, email } — the colleague who shared it, who signs it
   link           the one-time sign-in URL
   stage          before_first_call (default) | after_first_call — the share
                  dialog asks; before the first sales call the email offers a
                  walkthrough, after it a follow-up call (owner, 2026-10-09)
   requestedAt / validUntil   ms epoch; validUntil = the share link's expiry */
export function signInEmail({ client, subVertical, recipient, recipientName, ae, link, stage,
                              requestedAt, validUntil, year }) {
  const afterCall = stage === "after_first_call";
  const valid = validity(requestedAt, validUntil || requestedAt + 86400000);
  const who = (ae && ae.name) || nameFromEmail(ae && ae.email) || "Your Zennify contact";
  const first = firstName(who);
  const peers = `comparable ${peerGroup(subVertical)}`;
  const greetName = firstName(recipientName) || firstName(nameFromEmail(recipient));
  const greeting = greetName ? `Hi ${greetName},` : client ? `Dear ${client} team,` : "Hello,";
  const subject = client ? `Your ${client} digital maturity assessment is ready`
                         : "Your digital maturity assessment is ready";
  const headline = subject;
  const preheader = `${who} has shared ${client ? `${client}'s` : "your"} results, benchmarked against ${peers}. ` +
    `The secure link is valid for ${valid.replace(/, until.*/, "")}.`;
  const when = formatUtc(requestedAt);
  const yr = year || new Date(requestedAt).getUTCFullYear();
  const org = client || "your organisation";
  const intro = afterCall
    ? `Thank you for your time on our recent call. As promised, here is ${client ? `${client}'s` : "your"} digital maturity assessment.`
    : `I am pleased to share ${client ? `${client}'s` : "your"} digital maturity assessment with you.`;
  const hook = `Would you like to know how ${org} performs against its peers? Your assessment scores your ` +
    "organisation across four pillars: strategy and governance, customer experience, operations and risk, " +
    `and data and technology. Each pillar is benchmarked against ${peers}, so you can see where you lead ` +
    "and where the biggest opportunities lie.";
  const inside = ["Your overall maturity score, and your score in each pillar",
                  `How you compare with peer ${peerGroup(subVertical)}`,
                  "The insights and opportunities that matter most to your organisation"];
  const follow = afterCall ? {
    heading: "Book your follow-up call",
    text: "I would welcome a follow-up call to go deeper on the priorities we discussed and agree the next steps for your organisation.",
    button: "Book a follow-up call",
    subject: `Follow-up call: ${client || "our"} digital maturity assessment`,
    ask: `We would like to book a follow-up call on ${client ? `${client}'s` : "our"} digital maturity assessment.`,
    reply: `Reply to this email to book a follow-up call with ${first || who}.`,
  } : {
    heading: "Talk through your results",
    text: "I would welcome the chance to walk your team through the findings and what they mean for your organisation.",
    button: "Schedule a walkthrough",
    subject: `Digital maturity assessment walkthrough: ${client || "our results"}`,
    ask: `We would like to schedule a walkthrough of ${client ? `${client}'s` : "our"} digital maturity assessment.`,
    reply: `Reply to this email to schedule a walkthrough with ${first || who}.`,
  };
  const followText = follow.text;
  const mailto = ae && ae.email ? `mailto:${ae.email}?subject=${encodeURIComponent(follow.subject)}` +
    `&body=${encodeURIComponent(`Hi ${first},\n\n${follow.ask}\n\n`)}` : null;

  const text = [
    greeting,
    "",
    intro,
    "",
    hook,
    "",
    "Inside your assessment:",
    ...inside.map((x) => `  - ${x}`),
    "",
    `View your assessment: ${link}`,
    "",
    `This secure link is for ${recipient} only. It works once and stays valid for ${valid}.`,
    "",
    `${follow.heading}: ${followText} ${follow.reply}`,
    "",
    "Kind regards,",
    who,
    "Zennify",
    "",
    `You are receiving this because a sign-in link was requested for ${recipient} on ${when} ` +
      `for the digital maturity assessment Zennify shared with your organisation. If you did not request it, ` +
      "no action is needed: nobody can sign in without access to this inbox, and no further " +
      "emails will be sent unless another link is requested.",
    `© ${yr} Zennify | Confidential`,
  ].join("\n");

  const p = (inner, extra = "") =>
    `<p style="margin:0 0 16px;font-family:${FONT};font-size:15px;line-height:1.6;color:${BRAND.body};${extra}">${inner}</p>`;
  const bullets = inside.map((x) => `<tr>
<td valign="top" style="width:18px;padding:0 0 8px;font-family:${FONT};font-size:15px;line-height:1.5;color:${BRAND.teal};">&#9632;</td>
<td style="padding:0 0 8px;font-family:${FONT};font-size:15px;line-height:1.5;color:${BRAND.body};">${esc(x)}</td>
</tr>`).join("\n");
  const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="x-apple-disable-message-reformatting">
<meta name="color-scheme" content="light">
<meta name="supported-color-schemes" content="light">
<title>${esc(subject)}</title>
<style>
@media (max-width: 620px) { .card { width: 100% !important; } .px { padding-left: 24px !important; padding-right: 24px !important; } }
a { color: ${BRAND.green}; }
</style>
</head>
<body style="margin:0;padding:0;background:${BRAND.lavender};">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;mso-hide:all;">${esc(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:${BRAND.lavender};">
<tr><td align="center" style="padding:32px 12px;">
<table role="presentation" class="card" width="600" cellpadding="0" cellspacing="0" border="0" style="width:600px;max-width:600px;background:${BRAND.white};border:1px solid ${BRAND.rule};">
<tr><td class="px" style="padding:28px 40px 20px;border-bottom:3px solid ${BRAND.teal};">
<img src="cid:zennify-wordmark" width="144" height="36" alt="Zennify" style="display:block;border:0;outline:none;text-decoration:none;height:36px;width:144px;">
</td></tr>
<tr><td class="px" style="padding:32px 40px 4px;">
<div style="margin:0 0 10px;font-family:${FONT};font-size:12px;font-weight:600;letter-spacing:1.2px;color:${BRAND.green};">DIGITAL MATURITY ASSESSMENT</div>
<h1 style="margin:0 0 20px;font-family:${FONT};font-size:24px;line-height:1.3;font-weight:600;color:${BRAND.body};">${esc(headline)}</h1>
${p(esc(greeting))}
${p(esc(intro))}
${p(esc(hook))}
<div style="margin:0 0 10px;font-family:${FONT};font-size:15px;font-weight:600;color:${BRAND.body};">Inside your assessment</div>
<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 8px;">
${bullets}
</table>
</td></tr>
<tr><td class="px" style="padding:8px 40px 20px;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
<td style="background:${BRAND.darkTeal};">
<a href="${esc(link)}" style="display:inline-block;padding:14px 28px;font-family:${FONT};font-size:15px;font-weight:600;line-height:1;color:${BRAND.white};text-decoration:none;">View your assessment</a>
</td></tr></table>
</td></tr>
<tr><td class="px" style="padding:0 40px 8px;">
${p(`This secure link is for <strong>${esc(recipient)}</strong> only. It works once and stays valid for ${esc(valid)}.`, "font-size:13.5px;")}
</td></tr>
<tr><td class="px" style="padding:8px 40px 24px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
<td style="background:${BRAND.ice};padding:20px 24px;">
<div style="margin:0 0 6px;font-family:${FONT};font-size:15px;font-weight:600;color:${BRAND.body};">${esc(follow.heading)}</div>
<p style="margin:0 0 14px;font-family:${FONT};font-size:14px;line-height:1.55;color:${BRAND.body};">${esc(followText)}</p>
${mailto ? `<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
<td style="border:1px solid ${BRAND.darkTeal};background:${BRAND.white};">
<a href="${esc(mailto)}" style="display:inline-block;padding:11px 22px;font-family:${FONT};font-size:14px;font-weight:600;line-height:1;color:${BRAND.darkTeal};text-decoration:none;">${esc(follow.button)}</a>
</td></tr></table>
<p style="margin:10px 0 0;font-family:${FONT};font-size:13px;line-height:1.5;color:${BRAND.body};">Or simply reply to this email.</p>` : ""}
</td></tr></table>
</td></tr>
<tr><td class="px" style="padding:0 40px 28px;">
${p(`Kind regards,<br><strong>${esc(who)}</strong><br>Zennify`, "margin:0;")}
</td></tr>
<tr><td class="px" style="padding:20px 40px 28px;border-top:1px solid ${BRAND.rule};">
<p style="margin:0 0 12px;font-family:${FONT};font-size:12px;line-height:1.55;color:${BRAND.body};">You are receiving this because a sign-in link was requested for ${esc(recipient)} on ${esc(when)} for the digital maturity assessment Zennify shared with your organisation. If you did not request it, no action is needed: nobody can sign in without access to this inbox, and no further emails will be sent unless another link is requested.</p>
<p style="margin:0;font-family:${FONT};font-size:12px;line-height:1.5;color:${BRAND.muted};">&copy; ${yr} Zennify | Confidential</p>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>`;
  return { subject, preheader, text, html };
}

/* ── MIME ───────────────────────────────────────────────────────────────
   Built here, not by the sender, so its shape is deterministic and tested:
   multipart/alternative (text/plain, then multipart/related with the HTML
   and the inline wordmark). Quoted-printable text, CRLF line ends, every
   line ≤ 76 characters. */
const CRLF = "\r\n";

export function qp(str) {
  const bytes = Buffer.from(String(str).replace(/\r?\n/g, "\n"), "utf8");
  const lines = [];
  let line = "";
  const push = (tok) => {
    if (line.length + tok.length > 75) { lines.push(`${line}=`); line = ""; }
    line += tok;
  };
  for (let i = 0; i < bytes.length; i++) {
    const b = bytes[i];
    if (b === 0x0a) {
      // Trailing whitespace before a hard break must be encoded.
      line = line.replace(/[ \t]$/, (c) => (c === " " ? "=20" : "=09"));
      lines.push(line); line = ""; continue;
    }
    const printable = (b >= 33 && b <= 126 && b !== 61) || b === 32 || b === 9;
    push(printable ? String.fromCharCode(b) : `=${b.toString(16).toUpperCase().padStart(2, "0")}`);
  }
  line = line.replace(/[ \t]$/, (c) => (c === " " ? "=20" : "=09"));
  lines.push(line);
  return lines.join(CRLF);
}

const word = (s) => (/^[\x20-\x7e]*$/.test(s) ? s
  : `=?UTF-8?B?${Buffer.from(s, "utf8").toString("base64")}?=`);
const b64lines = (buf) => buf.toString("base64").replace(/.{1,76}/g, (m) => `${m}${CRLF}`).trimEnd();
function addr(name, email) {
  if (!name) return `<${email}>`;
  if (!/^[\x20-\x7e]*$/.test(name)) return `${word(name)} <${email}>`;
  if (/[",<>@()\\;:.[\]]/.test(name)) return `"${name.replace(/(["\\])/g, "\\$1")}" <${email}>`;
  return `${name} <${email}>`;
}

// RFC 5322 §2.2.3: fold a long header at whitespace so no line passes 78.
export function fold(h) {
  if (h.length <= 78) return h;
  const out = [];
  let line = "";
  for (const w of h.split(" ")) {
    if (line && (line + " " + w).length > 78) { out.push(line); line = w; }
    else line = line ? `${line} ${w}` : w;
  }
  out.push(line);
  return out.join(`${CRLF} `);
}

let wordmarkCache = null;
export function wordmark() {
  if (wordmarkCache) return wordmarkCache;
  const tries = [path.join(process.cwd(), "public", "brand", "zennify_wordmark_email.png"),
                 path.join(process.cwd(), "apps", "web", "public", "brand", "zennify_wordmark_email.png")];
  for (const f of tries) {
    try { wordmarkCache = fs.readFileSync(f); return wordmarkCache; } catch {}
  }
  return null;
}

export function buildMime({ from, to, subject, text, html, logo = wordmark(),
                            now = Date.now(), rand = () => crypto.randomBytes(12).toString("hex") }) {
  const alt = `alt_${rand()}`, rel = `rel_${rand()}`;
  const domain = String(from.email).split("@")[1] || "zennify.com";
  const headers = [
    `From: ${addr(from.name, from.email)}`,
    `To: <${to}>`,
    `Reply-To: ${addr(from.name, from.email)}`,
    `Subject: ${word(subject)}`,
    `Date: ${new Date(now).toUTCString().replace("GMT", "+0000")}`,
    `Message-ID: <${rand()}@${domain}>`,
    "MIME-Version: 1.0",
    // An automated, one-to-one transactional message: suppress out-of-office
    // and other auto-replies back to the colleague's mailbox, and keep
    // successive sign-in mails from collapsing into one thread.
    "Auto-Submitted: auto-generated",
    "X-Auto-Response-Suppress: All",
    `X-Entity-Ref-ID: ${rand()}`,
    `Content-Type: multipart/alternative; boundary="${alt}"`,
  ];
  const parts = [
    `--${alt}`,
    "Content-Type: text/plain; charset=UTF-8",
    "Content-Transfer-Encoding: quoted-printable",
    "",
    qp(text),
    `--${alt}`,
    `Content-Type: multipart/related; boundary="${rel}"`,
    "",
    `--${rel}`,
    "Content-Type: text/html; charset=UTF-8",
    "Content-Transfer-Encoding: quoted-printable",
    "",
    qp(html),
  ];
  if (logo) {
    parts.push(`--${rel}`,
      'Content-Type: image/png; name="zennify.png"',
      "Content-Transfer-Encoding: base64",
      "Content-ID: <zennify-wordmark>",
      'Content-Disposition: inline; filename="zennify.png"',
      "",
      b64lines(logo));
  }
  parts.push(`--${rel}--`, `--${alt}--`, "");
  return headers.map(fold).join(CRLF) + CRLF + CRLF + parts.join(CRLF);
}
