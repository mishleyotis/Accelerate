// The pages the public share service renders: the email gate, the
// dead-link page, and the client dashboard's own boot document.
import { SCRIPTS } from "../app/route.js";
import { SHARE_HEADERS, verifyMode } from "./share.js";

const esc = (s) => String(s == null ? "" : s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;").replace(/'/g, "&#39;");

function html(status, body, extraHeaders) {
  return new Response(body, { status,
    headers: { "content-type": "text/html; charset=utf-8", ...SHARE_HEADERS,
               ...(extraHeaders || {}) } });
}

function frame(title, inner) {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>${esc(title)}</title>
<link rel="stylesheet" href="/proto/app.css">
<link rel="icon" href="/brand/icon_teal.png">
</head>
<body>
<div class="loader-page"><div class="loader-card" style="max-width:440px">
<img src="/brand/icon_teal.png" alt="" width="34" height="34">
${inner}
</div></div>
</body>
</html>`;
}

// A link that does not verify — forged, expired, revoked — says only that.
// It does not say which, because the difference is information about the
// token a stranger holds, and the remedy is the same: ask for a new one.
export function deadLinkPage() {
  return html(404, frame("Link not available", `
<div><div class="loader-title">This link is not available</div>
<div class="loader-body" style="margin-top:6px">It may have expired or been withdrawn.
Ask the person who shared it with you for a new link.</div></div>`));
}

// The gate: one field, posted to this link's own /access route.
export function gatePage(token, entityName, error, status = 200) {
  return html(status, frame("Digital Maturity Assessment", `
<div><div class="loader-title">${esc(entityName || "Digital Maturity Assessment")}</div>
<div class="loader-body" style="margin-top:6px">Digital Maturity Assessment · enter the work
email this dashboard was shared with${verifyMode() === "otp"
  ? ". We will email you a one-time sign-in link." : " to open it."}</div></div>
<form method="post" action="/s/${esc(token)}/access" style="display:flex;flex-direction:column;gap:10px;width:100%">
<input class="inp" type="email" name="email" required autocomplete="email"
       placeholder="name@organisation.com" aria-label="Work email" style="width:100%">
${error ? `<div role="alert" style="font-size:12.5px;color:#9a3412">${esc(error)}</div>` : ""}
<button class="btn btn-primary" type="submit">${verifyMode() === "otp" ? "Email me a sign-in link" : "Open dashboard"}</button>
</form>`));
}

// The client dashboard itself: the same compiled modules in the same order
// as the app (one SCRIPTS list), booted with this link's entity only.
export function dashboardPage(boot) {
  const json = JSON.stringify(boot).replace(/</g, "\\u003c");
  return html(200, `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>${esc(boot.entities[0] && boot.entities[0].name)} · Digital Maturity Assessment</title>
<link rel="stylesheet" href="/proto/app.css">
<link rel="icon" href="/brand/icon_teal.png">
</head>
<body>
<div id="app"></div>
<script>window.DMA_LIVE=${json};</script>
${SCRIPTS.map((s) => `<script src="/${s}" defer></script>`).join("\n")}
</body>
</html>`);
}

// After the gate, in OTP mode: Google has emailed a single-use link.
export function checkEmailPage(entityName, email) {
  return html(200, frame("Check your email", `
<div><div class="loader-title">Check your email</div>
<div class="loader-body" style="margin-top:6px">We sent a one-time sign-in link to
<strong>${esc(email)}</strong>. Open it on this device to see the
${esc(entityName || "")} dashboard. The link works once and expires shortly.</div></div>
<div class="loader-body" style="font-size:12px">Nothing arrived? Check spam, or go back and request a new link.</div>`));
}
