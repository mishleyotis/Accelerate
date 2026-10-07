import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { COOKIE, verify } from "../../../../lib/session";
import { shareMode } from "../../../../lib/share";
import { upstreamHeaders } from "../../../../lib/upstream";

export const dynamic = "force-dynamic";

// Admin › Users & roles: the roster and its one write (svc_api
// /v1/admin/users, dma_api.users). The API decides who may change what from
// the IAP assertion it verifies itself; this route only refuses early for a
// non-Admin session and carries the assertion and the Idempotency-Key through.
async function proxy(req, method, body) {
  if (shareMode()) return new Response("Not found", { status: 404 });
  const session = verify(cookies().get(COOKIE)?.value);
  if (!session || session.role !== "ADMIN") {
    return NextResponse.json({ error: "admin_session_required" }, { status: 403 });
  }
  const base = process.env.API_URL;
  if (!base) return NextResponse.json({ error: "api_not_configured" }, { status: 501 });
  const headers = await upstreamHeaders(base);
  const assertion = req.headers.get("x-goog-iap-jwt-assertion");
  if (assertion) headers["x-goog-iap-jwt-assertion"] = assertion;
  if (method === "POST") {
    const key = req.headers.get("idempotency-key");
    if (!key) {
      return NextResponse.json({ error: "idempotency_key_required" }, { status: 400 });
    }
    headers["idempotency-key"] = key;
    headers["content-type"] = "application/json";
  }
  try {
    const r = await fetch(`${base}/v1/admin/users`, {
      method, headers, cache: "no-store",
      body: method === "POST" ? JSON.stringify(body) : undefined,
    });
    return new Response(await r.text(), {
      status: r.status,
      headers: { "content-type": "application/json", "cache-control": "no-store" },
    });
  } catch {
    return NextResponse.json({ error: "api_unreachable" }, { status: 502 });
  }
}

export async function GET(req) {
  return proxy(req, "GET");
}

export async function POST(req) {
  let body;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "malformed_body" }, { status: 400 });
  }
  return proxy(req, "POST", body);
}
