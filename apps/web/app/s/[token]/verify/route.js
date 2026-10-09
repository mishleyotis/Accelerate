import { accessCookie, allowed, audit, normaliseEmail, shareMode,
         verifyMode } from "../../../../lib/share";
import { liveLink } from "../../../../lib/share-ledger";
import { completeSignIn } from "../../../../lib/share-otp";
import { deadLinkPage, gatePage, unavailablePage } from "../../../../lib/share-page";
import { clientSession, linkFields, logLinkEvent, logUsage } from "../../../../lib/usage";

export const dynamic = "force-dynamic";

// GET /s/<token>/verify?e=<email>&oobCode=… — the one-time sign-in link,
// back from the recipient's inbox. Google redeems the code (once, for the
// address it was issued to); only then is the reader admitted, and only if
// that address is still on this link's allowlist.
export async function GET(req, { params }) {
  if (!shareMode()) return new Response("Not found", { status: 404 });
  const { p, why } = await liveLink(params.token);
  if (!p) return why === "unavailable" ? unavailablePage() : deadLinkPage();
  if (verifyMode() !== "otp") return gatePage(params.token, null);
  const q = new URL(req.url).searchParams;
  const email = normaliseEmail(q.get("e"));
  const code = q.get("oobCode");
  const retry = (msg) => gatePage(params.token, null, msg, 401);
  if (!email || !code || !allowed(p, email)) {
    return retry("That sign-in link is not valid. Enter your email to get a new one.");
  }
  const r = await completeSignIn(email, code);
  if (!r.ok || r.email !== email) {
    audit("share_otp_rejected", { jti: p.jti, entity: p.e, email, error: r.error || "email_mismatch" });
    logLinkEvent("link_refused", linkFields(p, { attempted_email: email, reason: "sign_in_link_rejected" }));
    return retry("That sign-in link has expired or was already used. Enter your email to get a new one.");
  }
  audit("share_access_granted", { jti: p.jti, entity: p.e, email, method: "otp" });
  logUsage("link_admit", clientSession(email), linkFields(p, { method: "otp" }));
  return new Response(null, { status: 303, headers: {
    location: `/s/${params.token}#/clients/${p.e}/overview?view=client`,
    "set-cookie": accessCookie(p, params.token, email, "otp"),
    "cache-control": "no-store", "referrer-policy": "no-referrer" } });
}
