import { NextResponse } from "next/server";
import { COOKIE, maxAge, sign } from "../../../lib/session";

// The prototype's role inference, applied server-side with the domain
// gate. Only @zennify.com signs in — same message the prototype shows.
export async function POST(req) {
  let email = "";
  try {
    email = String((await req.json()).email || "").trim().toLowerCase();
  } catch {}
  if (!email.endsWith("@zennify.com")) {
    return NextResponse.json(
      { error: "Only @zennify.com Google accounts are permitted. Please select your Zennify account." },
      { status: 403 });
  }
  const role = email.includes("admin") ? "ADMIN" : email.includes("ae") ? "AE" : "ANALYST";
  const res = NextResponse.json({ ok: true, role });
  res.cookies.set(COOKIE, sign(email, role), {
    httpOnly: true, secure: true, sameSite: "lax", path: "/", maxAge: maxAge(),
  });
  return res;
}
