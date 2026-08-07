import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { COOKIE, verify } from "../../../../../../../lib/session";
import { effectiveRole } from "../../../../../../../lib/identity";

// The write half of the entity proxy: an insight-card verdict. The SESSION's
// email is the actor — forwarded by this route, never accepted from the
// client body — and the Idempotency-Key passes through untouched so a retry
// replays instead of duplicating (TRD §19). The API anchors the annotation
// fail-closed to a card on a promoted run; this route adds nothing to that
// judgement, it only carries identity.
export async function POST(req, { params }) {
  const session = verify(cookies().get(COOKIE)?.value);
  if (!session) {
    return NextResponse.json({ error: "not_signed_in" }, { status: 401 });
  }
  const base = process.env.API_URL;
  if (!base) {
    return NextResponse.json({ error: "api_not_configured" }, { status: 501 });
  }
  const key = req.headers.get("idempotency-key");
  if (!key) {
    return NextResponse.json(
      { error: "idempotency_key_required",
        detail: "send an Idempotency-Key header" }, { status: 400 });
  }
  let body;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "malformed_body" }, { status: 400 });
  }

  const { display_id, ic_id } = params;
  const url = new URL(req.url);
  const role = effectiveRole(session.role, url.searchParams.get("role"));
  const target = new URL(
    `${base}/v1/entities/${encodeURIComponent(display_id)}` +
    `/insights/${encodeURIComponent(ic_id)}/annotation`);
  target.searchParams.set("audience", "internal");
  target.searchParams.set("role", role);
  target.searchParams.set("actor", session.email);

  const headers = { "content-type": "application/json",
                    "idempotency-key": key };
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

  try {
    const r = await fetch(target, {
      method: "POST", headers, cache: "no-store",
      body: JSON.stringify(body),
    });
    const text = await r.text();
    return new Response(text, {
      status: r.status,
      headers: { "content-type": "application/json" },
    });
  } catch {
    return NextResponse.json({ error: "api_unreachable" }, { status: 502 });
  }
}
