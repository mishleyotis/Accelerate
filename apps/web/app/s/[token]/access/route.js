import { accessCookie, allowed, audit, normaliseEmail, publicOrigin, shareMode,
         verifyMode } from "../../../../lib/share";
import { liveLink } from "../../../../lib/share-ledger";
import { mayResend, sendSignInLink } from "../../../../lib/share-otp";
import { checkEmailPage, deadLinkPage, gatePage, unavailablePage } from "../../../../lib/share-page";
import { readAsLink } from "../../../../lib/share-read";

export const dynamic = "force-dynamic";

// POST /s/<token>/access — the email gate's answer.
//
// Off the allowlist → refused here, logged, and NOTHING is sent.
// On it, OTP mode   → Google Cloud Identity Platform emails a single-use
//                     sign-in link back to /s/<token>/verify; nothing is
//                     admitted until it is followed (lib/share-otp).
// On it, attest mode (Identity Platform not configured) → admitted as typed.
export async function POST(req, { params }) {
  if (!shareMode()) return new Response("Not found", { status: 404 });
  const { p, why } = await liveLink(params.token);
  if (!p) return why === "unavailable" ? unavailablePage() : deadLinkPage();
  let email = null;
  try { email = normaliseEmail((await req.formData()).get("email")); } catch {}

  const nameOf = async () => {
    const ov = await readAsLink(p, "overview");
    try { return JSON.parse(ov.body).entity.entity_name; } catch { return null; }
  };
  if (!email || !allowed(p, email)) {
    audit("share_access_refused", { jti: p.jti, entity: p.e, email: email || "(unparseable)" });
    return gatePage(params.token, await nameOf(), email
      ? "That email is not on the access list for this dashboard. Ask the person who shared it with you to add it."
      : "Enter a valid email address.", 403);
  }

  if (verifyMode() === "otp") {
    if (!mayResend(p.jti, email)) {
      return gatePage(params.token, await nameOf(),
        "Too many sign-in links requested for this address. Wait a few minutes and try again.", 429);
    }
    const back = `${publicOrigin(req)}/s/${params.token}/verify?e=${encodeURIComponent(email)}`;
    const r = await sendSignInLink(email, back);
    if (!r.ok) {
      audit("share_otp_send_failed", { jti: p.jti, entity: p.e, email, error: r.error });
      return gatePage(params.token, await nameOf(),
        "The sign-in email could not be sent just now. Try again in a minute.", 502);
    }
    audit("share_otp_sent", { jti: p.jti, entity: p.e, email });
    return checkEmailPage(await nameOf(), email);
  }

  let cookie;
  try { cookie = accessCookie(p, params.token, email, "attest"); }
  catch { return gatePage(params.token, await nameOf(), "This link cannot be opened right now.", 503); }
  audit("share_access_granted", { jti: p.jti, entity: p.e, email, method: "attest" });
  return new Response(null, { status: 303, headers: {
    location: `/s/${params.token}#/clients/${p.e}/overview?view=client`,
    "set-cookie": cookie, "cache-control": "no-store", "referrer-policy": "no-referrer" } });
}
