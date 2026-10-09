import { accessCookie, allowed, audit, normaliseEmail, shareMode,
         verifyMode } from "../../../../lib/share";
import { liveLink } from "../../../../lib/share-ledger";
import { completeSignIn } from "../../../../lib/share-otp";
import { deadLinkPage, gatePage, unavailablePage } from "../../../../lib/share-page";
import { checkSignIn, claimNonce } from "../../../../lib/share-throttle";
import { clientSession, linkFields, logLinkEvent, logUsage } from "../../../../lib/usage";

export const dynamic = "force-dynamic";

// GET /s/<token>/verify?e=<email>&… — the one-time sign-in link, back from
// the recipient's inbox. Two kinds, both single use and bound to the address:
//
//   &i=…&n=…&s=…  the app's own code, in the email a colleague's mailbox sent
//                 (lib/share-mailer). Valid for as long as the share link —
//                 the days it was shared for (owner, 2026-10-09: "It is number
//                 of days not minutes"); burned on first use in the shared
//                 store (lib/share-throttle claimNonce), fail closed.
//   &oobCode=…    Google's code, in Identity Platform's own email; Google
//                 redeems it once and sets its lifetime.
//
// Either way the reader is admitted only while the address is still on this
// link's allowlist.
export async function GET(req, { params }) {
  if (!shareMode()) return new Response("Not found", { status: 404 });
  const { p, why } = await liveLink(params.token);
  if (!p) return why === "unavailable" ? unavailablePage() : deadLinkPage();
  if (verifyMode() !== "otp") return gatePage(params.token, null);
  const q = new URL(req.url).searchParams;
  const email = normaliseEmail(q.get("e"));
  const retry = (msg) => gatePage(params.token, null, msg, 401);
  if (!email || !allowed(p, email)) {
    return retry("That sign-in link is not valid. Enter your email to get a new one.");
  }

  if (q.get("n")) {
    const v = checkSignIn(p, email, q.get("i"), q.get("n"), q.get("s"));
    if (v !== "ok") {
      audit("share_otp_rejected", { jti: p.jti, entity: p.e, email, error: `code_${v}` });
      logLinkEvent("link_refused", linkFields(p, { attempted_email: email, reason: "sign_in_link_rejected" }));
      return retry("That sign-in link is not valid. Enter your email to get a new one.");
    }
    let first;
    try { first = await claimNonce(q.get("n")); }
    catch (e) {
      audit("share_otp_store_unavailable", { jti: p.jti, error: String(e.message || e).slice(0, 200) });
      return unavailablePage();
    }
    if (!first) {
      audit("share_otp_rejected", { jti: p.jti, entity: p.e, email, error: "code_reused" });
      logLinkEvent("link_refused", linkFields(p, { attempted_email: email, reason: "sign_in_link_reused" }));
      return retry("That sign-in link was already used. Enter your email to get a new one.");
    }
  } else {
    const code = q.get("oobCode");
    if (!code) return retry("That sign-in link is not valid. Enter your email to get a new one.");
    const r = await completeSignIn(email, code);
    if (!r.ok || r.email !== email) {
      audit("share_otp_rejected", { jti: p.jti, entity: p.e, email, error: r.error || "email_mismatch" });
      logLinkEvent("link_refused", linkFields(p, { attempted_email: email, reason: "sign_in_link_rejected" }));
      return retry("That sign-in link has expired or was already used. Enter your email to get a new one.");
    }
  }
  audit("share_access_granted", { jti: p.jti, entity: p.e, email, method: "otp" });
  logUsage("link_admit", clientSession(email), linkFields(p, { method: "otp" }));
  return new Response(null, { status: 303, headers: {
    location: `/s/${params.token}#/clients/${p.e}/overview?view=client`,
    "set-cookie": accessCookie(p, params.token, email, "otp"),
    "cache-control": "no-store", "referrer-policy": "no-referrer" } });
}
