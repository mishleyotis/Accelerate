import { NextResponse } from "next/server";
import { COOKIE } from "../../../lib/session";
import { shareMode } from "../../../lib/share";

export async function POST() {
  // Not on the public share service: it serves client links only (lib/share).
  if (shareMode()) return new Response("Not found", { status: 404 });
  const res = NextResponse.json({ ok: true });
  res.cookies.set(COOKIE, "", {
    httpOnly: true, secure: true, sameSite: "lax", path: "/", maxAge: 0,
  });
  return res;
}
