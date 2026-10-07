import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { COOKIE, verify } from "../../../lib/session";
import { logUsage, parseBeacon } from "../../../lib/usage";
import { shareMode } from "../../../lib/share";

// The browser's usage beacon (proto/usage-tracker.jsx). It LOGS and nothing
// else: each valid event becomes one structured stdout line that the log sink
// carries to BigQuery (lib/usage.js). No database write, no serving content.
//
// Identity comes from the verified session cookie; the body only says where
// the browser was and for how long. A malformed event is dropped and counted,
// never repaired into something it did not say.
export async function POST(req) {
  // Not on the public share service: it serves client links only (lib/share),
  // and a client recipient is not a Zennify user whose usage this measures.
  if (shareMode()) return new Response("Not found", { status: 404 });
  const session = verify(cookies().get(COOKIE)?.value);
  if (!session) {
    return NextResponse.json({ error: "not_signed_in" }, { status: 401 });
  }
  const text = await req.text().catch(() => "");
  const parsed = parseBeacon(text, session, req.headers.get("user-agent"));
  if (parsed.error) {
    return NextResponse.json({ error: parsed.error }, { status: 400 });
  }
  for (const e of parsed.events) logUsage(e.type, session, e.fields);
  if (!parsed.events.length) {
    return NextResponse.json({ error: "no_valid_events", rejected: parsed.rejected },
                             { status: 400 });
  }
  return new Response(null, { status: 204 });
}
