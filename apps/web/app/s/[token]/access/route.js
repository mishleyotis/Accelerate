import { accessCookie, allowed, audit, normaliseEmail, shareMode, verify } from "../../../../lib/share";
import { deadLinkPage, gatePage } from "../../../../lib/share-page";
import { readAsLink } from "../../../../lib/share-read";

export const dynamic = "force-dynamic";

// POST /s/<token>/access — the email gate's answer. An address on this
// link's allowlist (the address itself, or its organisation's domain) is
// admitted for this link; anything else is told so and logged.
export async function POST(req, { params }) {
  if (!shareMode()) return new Response("Not found", { status: 404 });
  const p = verify(params.token);
  if (!p) return deadLinkPage();
  let email = null;
  try { email = normaliseEmail((await req.formData()).get("email")); } catch {}

  if (!email || !allowed(p, email)) {
    audit("share_access_refused", { jti: p.jti, entity: p.e, email: email || "(unparseable)" });
    const ov = await readAsLink(p, "overview");
    let name = null;
    try { name = JSON.parse(ov.body).entity.entity_name; } catch {}
    return gatePage(params.token, name, email
      ? "That email is not on the access list for this dashboard. Ask the person who shared it with you to add it."
      : "Enter a valid email address.", 403);
  }
  audit("share_access_granted", { jti: p.jti, entity: p.e, email });
  return new Response(null, { status: 303, headers: {
    location: `/s/${params.token}#/clients/${p.e}/overview?view=client`,
    "set-cookie": accessCookie(p, params.token, email),
    "cache-control": "no-store", "referrer-policy": "no-referrer" } });
}
