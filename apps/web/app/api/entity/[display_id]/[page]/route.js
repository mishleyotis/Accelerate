import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { COOKIE, verify } from "../../../../../lib/session";
import { effectiveRole } from "../../../../../lib/identity";

// The SPA's read path into the serving tier. The session's GRANTED role is
// forwarded (never a client-supplied one), so the API can refuse a page the
// role has no route to; audience is a request parameter, which is what makes
// a customer view shareable, and the API — not the browser — decides what
// the customer audience may contain.
// The six promoted pages, plus the two GRAIN reads the surfaces need: the
// evidence store (read per id, not per page — it is not a promoted section)
// and the run's cell grain. Both are entity-scoped and fail-closed at the API.
const PAGES = new Set(["overview", "insights", "heatmap", "platform",
                       "context", "techstack", "evidence", "subcaps"]);

export async function GET(req, { params }) {
  const session = verify(cookies().get(COOKIE)?.value);
  if (!session) {
    return NextResponse.json({ error: "not_signed_in" }, { status: 401 });
  }
  const { display_id, page } = params;
  if (!PAGES.has(page)) {
    return NextResponse.json({ error: "unknown_page" }, { status: 404 });
  }
  const base = process.env.API_URL;
  if (!base) {
    return NextResponse.json({ error: "api_not_configured" }, { status: 501 });
  }

  const url = new URL(req.url);
  const audience = url.searchParams.get("audience") === "customer"
    ? "customer" : "internal";
  const run = url.searchParams.get("run");
  const eIds = url.searchParams.get("e_ids");
  // "Acting as" is resolved here, against the SESSION's granted role, and it
  // can only narrow (lib/identity.effectiveRole). So an admin previewing the AE
  // view gets the server's AE answer — the same 403 on D5 a real AE gets — and
  // an AE that sends role=ADMIN is still answered as an AE. The client's value
  // is a request, never a grant.
  const role = effectiveRole(session.role, url.searchParams.get("role"));
  const target = new URL(`${base}/v1/entities/${encodeURIComponent(display_id)}/${page}`);
  target.searchParams.set("audience", audience);
  target.searchParams.set("role", role);
  if (run) target.searchParams.set("run", run);
  if (eIds) target.searchParams.set("e_ids", eIds);

  const headers = {};
  // Local QA only: on Cloud Run the ID token comes from the metadata
  // server, which does not exist on a developer machine.
  if (process.env.API_ID_TOKEN) {
    headers.Authorization = `Bearer ${process.env.API_ID_TOKEN}`;
  }
  try {
    const t = await fetch(
      "http://metadata.google.internal/computeMetadata/v1/instance/" +
        `service-accounts/default/identity?audience=${encodeURIComponent(base)}`,
      { headers: { "Metadata-Flavor": "Google" }, cache: "no-store" }
    );
    if (t.ok) headers.Authorization = `Bearer ${await t.text()}`;
  } catch {}
  const inm = req.headers.get("if-none-match");
  if (inm) headers["If-None-Match"] = inm;

  try {
    const r = await fetch(target, { headers, cache: "no-store" });
    if (r.status === 304) {
      return new Response(null, { status: 304,
        headers: { ETag: r.headers.get("etag") || "" } });
    }
    const body = await r.text();
    return new Response(body, {
      status: r.status,
      headers: { "content-type": "application/json",
                 "cache-control": "private, max-age=0",
                 ...(r.headers.get("etag") ? { ETag: r.headers.get("etag") } : {}) },
    });
  } catch {
    return NextResponse.json({ error: "api_unreachable" }, { status: 502 });
  }
}
