import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { COOKIE, verify as verifySession } from "../../../lib/session";
import { audit, mint, shareMode, shareUrl } from "../../../lib/share";

// POST /api/share — mint a client link (the IAP-fronted app only).
//
// Body: { entity, run, recipients: "jane@bcu.com, …", days? }
// The recipients ARE the allowlist: each address, and each address's
// organisation domain (never a consumer mailbox domain), may open the link —
// for this one client and run (lib/share). Any signed-in Zennify user may
// share; who shared what with whom is logged, and never written into the
// link itself.
export async function POST(req) {
  if (shareMode()) return new Response("Not found", { status: 404 });
  const session = verifySession(cookies().get(COOKIE)?.value);
  if (!session) return NextResponse.json({ error: "not_signed_in" }, { status: 401 });
  const base = process.env.SHARE_BASE_URL;
  if (!base) {
    return NextResponse.json({ error: "share_links_not_configured",
      detail: "SHARE_BASE_URL is not set on this service" }, { status: 503 });
  }
  let body = {};
  try { body = await req.json(); } catch {}
  try {
    const { token, payload } = mint({ entity: body.entity, run: body.run,
                                      recipients: body.recipients, days: body.days });
    audit("share_link_minted", { jti: payload.jti, entity: payload.e, run: payload.r,
      by: session.email, emails: payload.a.m, domains: payload.a.d,
      expires_at: new Date(payload.exp * 1000).toISOString() });
    return NextResponse.json({
      url: shareUrl(base, token, payload.e), jti: payload.jti,
      expires_at: new Date(payload.exp * 1000).toISOString(),
      allowlist: { emails: payload.a.m, domains: payload.a.d },
    }, { headers: { "cache-control": "no-store" } });
  } catch (e) {
    const status = e.code === "not_configured" ? 503 : 400;
    return NextResponse.json({ error: e.code || "bad_request", detail: e.message }, { status });
  }
}
