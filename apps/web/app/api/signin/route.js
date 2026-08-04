import { NextResponse } from "next/server";
import { COOKIE, maxAge, sign } from "../../../lib/session";

// Role GRANTS are allowlists, set per deployment — never inferred from
// what the email happens to contain. Unlisted zennify accounts get
// ANALYST. The users table replaces this when the auth stage lands.
function grantedRole(email) {
  const list = (name) => (process.env[name] || "")
    .toLowerCase().split(",").map((s) => s.trim()).filter(Boolean);
  if (list("ADMIN_EMAILS").includes(email)) return "ADMIN";
  if (list("AE_EMAILS").includes(email)) return "AE";
  return "ANALYST";
}

export async function POST(req) {
  let email = "";
  try {
    email = String((await req.json()).email || "").trim().toLowerCase();
  } catch {}
  if (!email || !email.endsWith("@zennify.com")) {
    return NextResponse.json(
      { error: "Only @zennify.com Google accounts are permitted. Please select your Zennify account." },
      { status: 403 });
  }
  const role = grantedRole(email);
  const res = NextResponse.json({ ok: true, role });
  res.cookies.set(COOKIE, sign(email, role), {
    httpOnly: true, secure: true, sameSite: "lax", path: "/", maxAge: maxAge(),
  });
  return res;
}
