import { NextResponse } from "next/server";
import { SHARE_HEADERS, SHARE_PAGES, accessCookieName, cookieFrom, readAccess,
         shareMode } from "../../../../../../../lib/share";
import { liveLink } from "../../../../../../../lib/share-ledger";
import { readAsLink } from "../../../../../../../lib/share-read";

export const dynamic = "force-dynamic";

const deny = (status, error, detail) =>
  NextResponse.json({ error, ...(detail ? { detail } : {}) }, { status, headers: SHARE_HEADERS });

// GET /s/<token>/api/entity/<client>/<page> — the client link's reads.
// Valid token, admitted reader, the link's own client, a client-dashboard
// page — or a refusal. The SPA renders a 403 as a withheld dashboard.
export async function GET(req, { params }) {
  if (!shareMode()) return new Response("Not found", { status: 404 });
  const { p, why } = await liveLink(params.token);
  if (!p) return why === "unavailable" ? deny(503, "link_unavailable") : deny(401, "link_not_valid");
  if (!readAccess(p, cookieFrom(req, accessCookieName(p)))) return deny(401, "not_admitted");
  if (params.display_id !== p.e) return deny(403, "not_in_client_link");
  if (!SHARE_PAGES.has(params.page)) {
    return deny(403, "not_in_client_link",
      "This page is not part of the shared client dashboard.");
  }
  const url = new URL(req.url);
  const r = await readAsLink(p, params.page, url.searchParams.get("e_ids"));
  return new Response(r.body, { status: r.status,
    headers: { "content-type": "application/json", ...SHARE_HEADERS } });
}
