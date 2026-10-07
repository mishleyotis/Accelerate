import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { COOKIE, verify } from "../../../../lib/session";
import { RANGES, readUsage } from "../../../../lib/usage-store";
import { shareMode } from "../../../../lib/share";

export const dynamic = "force-dynamic";

// Admin › Usage analytics: the usage events the log sink carried to BigQuery
// (lib/usage-store.js). ADMIN sessions only — the server-granted role, not
// the acting one — because it names colleagues and what they read.
//
// A one-minute cache per range: every admin navigation would otherwise run
// two BigQuery jobs, and the data behind it moves by the minute at most.
const CACHE_MS = 60 * 1000;
const cache = new Map();

export async function GET(req) {
  // Not on the public share service: it serves client links only (lib/share).
  if (shareMode()) return new Response("Not found", { status: 404 });
  const session = verify(cookies().get(COOKIE)?.value);
  if (!session || session.role !== "ADMIN") {
    return NextResponse.json({ error: "admin_session_required" }, { status: 403 });
  }
  const asked = Number(new URL(req.url).searchParams.get("days"));
  const days = RANGES.includes(asked) ? asked : 30;
  const hit = cache.get(days);
  if (hit && Date.now() - hit.at < CACHE_MS) {
    return NextResponse.json(hit.body, { headers: { "cache-control": "no-store" } });
  }
  const body = await readUsage(days);
  if (body.status === "ok") cache.set(days, { at: Date.now(), body });
  return NextResponse.json(body, { headers: { "cache-control": "no-store" } });
}
