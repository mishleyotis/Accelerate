import { publicOrigin, shareMode, verify } from "../../../lib/share";
import { deadLinkPage } from "../../../lib/share-page";

export const dynamic = "force-dynamic";

// GET /s/auth-action?mode=signIn&oobCode=…&continueUrl=… — Identity
// Platform's email action handler, pointed here by infra/deploy.sh
// (notification.sendEmail.callbackUri) so the emailed link lands on this
// service rather than a hosted page elsewhere. It does one thing: hand the
// code to the link's own /verify route — and only to a /verify route of a
// valid link ON THIS ORIGIN, so it can never be used to bounce a code (or a
// reader) to anywhere else.
export async function GET(req) {
  if (!shareMode()) return new Response("Not found", { status: 404 });
  const q = new URL(req.url).searchParams;
  let target = null;
  try { target = new URL(q.get("continueUrl") || ""); } catch {}
  const origin = publicOrigin(req);
  const m = target && target.pathname.match(/^\/s\/([^/]+)\/verify$/);
  if (q.get("mode") !== "signIn" || !q.get("oobCode") || !target ||
      target.origin !== origin || !m || !verify(m[1])) {
    return deadLinkPage();
  }
  target.searchParams.set("oobCode", q.get("oobCode"));
  return new Response(null, { status: 303, headers: {
    location: `${target.pathname}${target.search}`,
    "cache-control": "no-store", "referrer-policy": "no-referrer" } });
}
