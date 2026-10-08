import { NextResponse } from "next/server";
import { buildId } from "../../../lib/build-id";
import { shareMode } from "../../../lib/share";

export const dynamic = "force-dynamic";

// The bundle build this server serves (lib/build-id). The open page compares
// it with the build it booted on and offers a reload when they differ. No
// session needed: it names a hash, nothing else.
export async function GET() {
  // Not on the public share service: it serves client links only (lib/share).
  if (shareMode()) return new Response("Not found", { status: 404 });
  return NextResponse.json({ build: buildId() }, { headers: { "cache-control": "no-store" } });
}
