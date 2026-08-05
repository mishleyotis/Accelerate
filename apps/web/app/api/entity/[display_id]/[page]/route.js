import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { COOKIE, verify } from "../../../../../lib/session";

// The SPA's read path into the serving tier. The session's GRANTED role is
// forwarded (never a client-supplied one), so the API can refuse a page the
// role has no route to; audience is a request parameter, which is what makes
// a customer view shareable, and the API — not the browser — decides what
// the customer audience may contain.
const PAGES = new Set(["overview", "insights", "heatmap", "platform",
                       "context", "techstack"]);

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
  const target = new URL(`${base}/v1/entities/${encodeURIComponent(display_id)}/${page}`);
  target.searchParams.set("audience", audience);
  target.searchParams.set("role", session.role);
  if (run) target.searchParams.set("run", run);

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
