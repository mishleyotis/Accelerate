import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { requestSession } from "../../../../lib/request-session";
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
  const session = await requestSession(req, cookies());
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
  // A read that is not ok is one log line (infra/diagnose_usage.sh reads it),
  // so "the panel is blank" has a recorded reason in production.
  if (body.status !== "ok" || body.awaiting_first_event) {
    console.log(JSON.stringify({ usage_read: {
      status: body.awaiting_first_event ? "awaiting_first_event" : body.status,
      detail: body.detail || body.error || null } }));
  }
  return NextResponse.json(body, { headers: { "cache-control": "no-store" } });
}
