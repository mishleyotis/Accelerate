import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { COOKIE, verify } from "../../../../lib/session";
import { audit, shareMode } from "../../../../lib/share";
import { changeRevocation, jtiFrom, ledgerBackend, listLinks } from "../../../../lib/share-ledger";

export const dynamic = "force-dynamic";

// Admin › Client links (lib/share-ledger): every client link generated, and
// the controls that take access back — revoke a whole link, or remove one
// address or domain from its allowlist; each can be restored. ADMIN sessions
// only (the server-granted role, not the acting one).
//
//   GET                       → { status, links: [...] }
//   POST { link, action, email?, domain? }
//        link    a link id, or the pasted link itself
//        action  revoke | restore | remove | readd
function admin() {
  const session = verify(cookies().get(COOKIE)?.value);
  return session && session.role === "ADMIN" ? session : null;
}
const noStore = { "cache-control": "no-store" };

export async function GET() {
  // Not on the public share service: it serves client links only (lib/share).
  if (shareMode()) return new Response("Not found", { status: 404 });
  if (!admin()) return NextResponse.json({ error: "admin_session_required" }, { status: 403 });
  return NextResponse.json(await listLinks(), { headers: noStore });
}

export async function POST(req) {
  if (shareMode()) return new Response("Not found", { status: 404 });
  const session = admin();
  if (!session) return NextResponse.json({ error: "admin_session_required" }, { status: 403 });
  if (!ledgerBackend()) {
    return NextResponse.json({ error: "share_ledger_not_configured",
      detail: "SHARE_LEDGER_BUCKET is not set on this service" }, { status: 503, headers: noStore });
  }
  let body = {};
  try { body = await req.json(); } catch {}
  const jti = jtiFrom(body.link);
  if (!jti) {
    return NextResponse.json({ error: "bad_request", detail: "Paste a client link or its link ID." },
      { status: 400, headers: noStore });
  }
  try {
    const revocation = await changeRevocation(jti, { action: body.action, email: body.email,
      domain: body.domain, by: session.email });
    audit(`share_link_${body.action === "revoke" ? "revoked" : body.action === "restore" ? "restored"
                       : body.action === "remove" ? "recipient_removed" : "recipient_restored"}`,
      { jti, by: session.email, email: body.email || null, domain: body.domain || null });
    return NextResponse.json({ jti, revocation }, { headers: noStore });
  } catch (e) {
    const status = e.code === "bad_request" ? 400 : e.code === "not_configured" ? 503 : 502;
    return NextResponse.json({ error: e.code || "ledger_unavailable", detail: e.message },
      { status, headers: noStore });
  }
}
