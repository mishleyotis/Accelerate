import { NextResponse } from "next/server";
import { SHARE_HEADERS, accessCookieName, cookieFrom, readAccess,
         shareMode } from "../../../../../lib/share";
import { liveLink } from "../../../../../lib/share-ledger";
import { clientBeaconFields, clientSession, logUsage, parseBeacon } from "../../../../../lib/usage";

export const dynamic = "force-dynamic";

const deny = (status, error) =>
  NextResponse.json({ error }, { status, headers: SHARE_HEADERS });

// POST /s/<token>/api/usage — the usage beacon of a client-link reader
// (proto/usage-tracker.jsx posts to the booted api_base). Same rule as the
// app's /api/usage: it LOGS and nothing else, and identity is never the
// body's. Here the identity is the address this link admitted (the
// path-scoped access cookie, re-checked against the live allowlist), the role
// is CLIENT, and every line names the link, its client and run — so Admin ›
// Usage analytics can say which recipient read what, for how long, through
// which link. A dead, revoked or unadmitted link logs nothing.
export async function POST(req, { params }) {
  if (!shareMode()) return new Response("Not found", { status: 404 });
  const { p, why } = await liveLink(params.token);
  if (!p) return deny(why === "unavailable" ? 503 : 401, why === "unavailable" ? "link_unavailable" : "link_not_valid");
  const email = readAccess(p, cookieFrom(req, accessCookieName(p)));
  if (!email) return deny(401, "not_admitted");
  const session = clientSession(email);
  const text = await req.text().catch(() => "");
  const parsed = parseBeacon(text, session, req.headers.get("user-agent"));
  if (parsed.error) return deny(400, parsed.error);
  for (const e of parsed.events) logUsage(e.type, session, clientBeaconFields(e.fields, p));
  if (!parsed.events.length) return deny(400, "no_valid_events");
  return new Response(null, { status: 204, headers: SHARE_HEADERS });
}
