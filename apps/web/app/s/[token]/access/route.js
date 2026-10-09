import { accessCookie, allowed, audit, normaliseEmail, publicOrigin, shareMode,
         verifyMode } from "../../../../lib/share";
import { buildMime, signInEmail } from "../../../../lib/share-email";
import { linkRecord, liveLink, revocationOf } from "../../../../lib/share-ledger";
import { mailerConfig, sendAs, senderFor } from "../../../../lib/share-mailer";
import { mayResend, sendSignInLink } from "../../../../lib/share-otp";
import { checkEmailPage, deadLinkPage, gatePage, throttledPage,
         unavailablePage } from "../../../../lib/share-page";
import { readAsLink } from "../../../../lib/share-read";
import { admitSend, clientIp, judgeForm, signSignIn } from "../../../../lib/share-throttle";
import { clientSession, linkFields, logLinkEvent, logUsage } from "../../../../lib/usage";

export const dynamic = "force-dynamic";

// POST /s/<token>/access — the email gate's answer.
//
// Off the allowlist → refused here, logged, and NOTHING is sent.
// On it, OTP mode, in this order — each step can only stop a send:
//   1. the form's bot traps (lib/share-throttle judgeForm): a filled honeypot
//      or an inhuman submission is answered like a success and sends nothing;
//   2. the shared send budgets (admitSend): per address, link, colleague,
//      network and service — fail closed;
//   3. the email: from the colleague who shared the link, through their own
//      Gmail (lib/share-mailer, domain-wide delegation), Zennify-branded
//      (lib/share-email); else Identity Platform's own email.
//   The colleague's email carries the app's own signed, single-use code,
//   valid for the days the link was shared for; Identity Platform's email
//   carries Google's code. Nothing is admitted until it is followed back to
//   /s/<token>/verify.
// On it, attest mode (Identity Platform not configured) → admitted as typed.
export async function POST(req, { params }) {
  if (!shareMode()) return new Response("Not found", { status: 404 });
  const { p, why } = await liveLink(params.token);
  if (!p) return why === "unavailable" ? unavailablePage() : deadLinkPage();
  let form = null;
  try { form = await req.formData(); } catch {}
  const email = normaliseEmail(form && form.get("email"));

  let entity;   // the client's own customer-audience entity block, read once
  const entityOf = async () => {
    if (entity !== undefined) return entity;
    const ov = await readAsLink(p, "overview");
    try { entity = JSON.parse(ov.body).entity || null; } catch { entity = null; }
    return entity;
  };
  const nameOf = async () => ((await entityOf()) || {}).entity_name || null;
  if (!email || !allowed(p, email)) {
    audit("share_access_refused", { jti: p.jti, entity: p.e, email: email || "(unparseable)" });
    logLinkEvent("link_refused", linkFields(p, { attempted_email: email || null,
      reason: email ? "not_on_allowlist" : "unparseable" }));
    return gatePage(params.token, await nameOf(), email
      ? "That email is not on the access list for this dashboard. Ask the person who shared it with you to add it."
      : "Enter a valid email address.", 403);
  }

  if (verifyMode() === "otp") {
    const verdict = judgeForm(p.jti, { ft: form.get("ft"), website: form.get("website") });
    if (verdict === "bot") {
      audit("share_gate_trap", { jti: p.jti, entity: p.e, email, ip: clientIp(req) });
      return checkEmailPage(await nameOf(), email);
    }
    if (verdict === "stale") {
      return gatePage(params.token, await nameOf(),
        "This page has been open for a while. Enter your email again to get a sign-in link.", 400);
    }
    if (!mayResend(p.jti, email)) {   // this instance's own floor, before the shared store
      return throttledPage(params.token, await nameOf(), { reason: "address", retryAfter: 900 });
    }

    const cfg = mailerConfig();
    let sender = null, record = null;
    if (cfg) {
      try {
        record = await linkRecord(p.jti);
        sender = senderFor(record, await revocationOf(p.jti), email, cfg);
      }
      catch (e) {
        audit("share_ledger_unavailable", { jti: p.jti, error: String(e.message || e).slice(0, 200) });
        return unavailablePage();
      }
    }
    const listed = (p.a.m || []).includes(email);
    const admit = await admitSend({ jti: p.jti, email, listed, sender: sender && sender.email,
                                    ip: clientIp(req) });
    if (!admit.ok) {
      audit("share_otp_throttled", { jti: p.jti, entity: p.e, email, reason: admit.reason,
                                     limit: admit.limit || null, detail: admit.detail || null });
      if (admit.reason === "unavailable") return unavailablePage();
      return throttledPage(params.token, await nameOf(), admit);
    }

    const verifyUrl = `${publicOrigin(req)}/s/${params.token}/verify?e=${encodeURIComponent(email)}`;
    if (sender) {
      const code = signSignIn(p.jti, email);
      const link = `${verifyUrl}&i=${code.i}&n=${code.n}&s=${encodeURIComponent(code.s)}`;
      const msg = signInEmail({ client: await nameOf(), subVertical: ((await entityOf()) || {}).sub_vertical,
                                recipient: email, recipientName: ((record && record.recipient_names) || {})[email] || null,
                                ae: sender, link, stage: record && record.stage,
                                requestedAt: Date.now(), validUntil: p.exp * 1000 });
      const sent = await sendAs(cfg, sender.email, buildMime({ from: sender, to: email,
        subject: msg.subject, text: msg.text, html: msg.html }));
      if (sent.ok) {
        audit("share_otp_sent", { jti: p.jti, entity: p.e, email, via: "gmail", from: sender.email });
        logUsage("link_otp_sent", clientSession(email), linkFields(p, { via: "gmail" }));
        return checkEmailPage(await nameOf(), email, sender, p.exp * 1000);
      }
      audit("share_mail_fallback", { jti: p.jti, entity: p.e, email, from: sender.email,
                                     error: sent.error, status: sent.status || null });
    }

    const r = await sendSignInLink(email, verifyUrl);
    if (!r.ok) {
      audit("share_otp_send_failed", { jti: p.jti, entity: p.e, email, error: r.error });
      return gatePage(params.token, await nameOf(),
        "The sign-in email could not be sent just now. Try again in a minute.", 502);
    }
    audit("share_otp_sent", { jti: p.jti, entity: p.e, email, via: "identity_platform" });
    logUsage("link_otp_sent", clientSession(email), linkFields(p, { via: "identity_platform" }));
    return checkEmailPage(await nameOf(), email);
  }

  let cookie;
  try { cookie = accessCookie(p, params.token, email, "attest"); }
  catch { return gatePage(params.token, await nameOf(), "This link cannot be opened right now.", 503); }
  audit("share_access_granted", { jti: p.jti, entity: p.e, email, method: "attest" });
  logUsage("link_admit", clientSession(email), linkFields(p, { method: "attest" }));
  return new Response(null, { status: 303, headers: {
    location: `/s/${params.token}#/clients/${p.e}/overview?view=client`,
    "set-cookie": cookie, "cache-control": "no-store", "referrer-policy": "no-referrer" } });
}
