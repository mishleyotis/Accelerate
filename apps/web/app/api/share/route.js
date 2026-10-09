import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { requestSession } from "../../../lib/request-session";
import { SHARE_STAGES, audit, mint, recipientNames, shareMode, shareUrl } from "../../../lib/share";
import { ledgerBackend, recordLink } from "../../../lib/share-ledger";
import { linkFields, logUsage } from "../../../lib/usage";

// POST /api/share — mint a client link (the IAP-fronted app only).
//
// Body: { entity, run, recipients: "Jane Doe <jane@bcu.com>, …", days?, stage }
// `stage` is required: before_first_call | after_first_call — whether the
// first sales call has happened decides the follow-up the recipient's email
// offers (owner, 2026-10-09).
// The recipients ARE the allowlist: each address, and each address's
// organisation domain (never a consumer mailbox domain), may open the link —
// for this one client and run (lib/share). Any signed-in Zennify user may
// share; who shared what with whom is logged, and never written into the
// link itself.
export async function POST(req) {
  if (shareMode()) return new Response("Not found", { status: 404 });
  // The cookie, else the IAP assertion (lib/request-session): a tab open past
  // the 8-hour cookie can still share.
  const session = await requestSession(req, cookies());
  if (!session) return NextResponse.json({ error: "not_signed_in" }, { status: 401 });
  const base = process.env.SHARE_BASE_URL;
  if (!base) {
    return NextResponse.json({ error: "share_links_not_configured",
      detail: "SHARE_BASE_URL is not set on this service" }, { status: 503 });
  }
  let body = {};
  try { body = await req.json(); } catch {}
  if (!SHARE_STAGES.includes(body.stage)) {
    return NextResponse.json({ error: "bad_request",
      detail: "Say whether the first sales call has happened before generating the link." }, { status: 400 });
  }
  try {
    const { token, payload } = mint({ entity: body.entity, run: body.run,
                                      recipients: body.recipients, days: body.days });
    // Recorded before it is handed out, so Admin › Client links can see and
    // revoke every link there is. A ledger that is configured but cannot be
    // written issues no link at all (lib/share-ledger).
    const ledger = ledgerBackend();
    if (ledger) {
      try { await recordLink(payload, session.email, ledger, session.name, recipientNames(body.recipients),
                             body.stage); }
      catch (e) {
        audit("share_link_not_recorded", { jti: payload.jti, error: String(e.message || e).slice(0, 200) });
        return NextResponse.json({ error: "share_ledger_unavailable",
          detail: "The link could not be recorded for revocation, so it was not issued. Try again." },
          { status: 503 });
      }
    }
    audit("share_link_minted", { jti: payload.jti, entity: payload.e, run: payload.r,
      by: session.email, emails: payload.a.m, domains: payload.a.d, stage: body.stage,
      expires_at: new Date(payload.exp * 1000).toISOString() });
    // Usage analytics: every link generated, by whom, for whom (lib/usage).
    logUsage("link_minted", session, linkFields(payload, {
      recipients: payload.a.m, domains: payload.a.d, stage: body.stage,
      expires_at: new Date(payload.exp * 1000).toISOString() }));
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
