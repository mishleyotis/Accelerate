import { shareMode } from "../../lib/share";

export const dynamic = "force-dynamic";

// The app is one document at "/" with a hash router, so the sign-in page is
// "/#/login". A bookmark or an old link to the path "/login" lands there
// instead of on a 404.
export function GET(req) {
  // Not on the public share service: it serves client links only (lib/share).
  if (shareMode()) return new Response("Not found", { status: 404 });
  return new Response(null, { status: 307, headers: { location: "/#/login", "cache-control": "no-store" } });
}
