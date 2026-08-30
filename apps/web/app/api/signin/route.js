import { NextResponse } from "next/server";
import { COOKIE, maxAge, sign } from "../../../lib/session";
import { iapIdentity } from "../../../lib/iap";
import { displayName, domainOk, grantedRole } from "../../../lib/identity";

// Sign-in mints the app session from the ONLY identity this app trusts:
// the Google account IAP verified in front of this service. The request
// body is ignored in production — a typed email is not an identity.
// ALLOW_DEV_LOGIN=1 (local compose only, never set in prod) restores a
// typed-email gate so the prototype can be exercised without IAP.
export async function POST(req) {
  let email = null;
  const iap = await iapIdentity(req);
  if (iap) {
    email = iap.email;
  } else if (process.env.ALLOW_DEV_LOGIN === "1") {
    try {
      email = String((await req.json()).email || "").trim().toLowerCase() || null;
    } catch {}
  } else {
    return NextResponse.json(
      { error: "No verified Google identity on this request. Access to this app goes through Google sign-in (IAP)." },
      { status: 401 });
  }

  if (!domainOk(email)) {
    return NextResponse.json(
      { error: "Only @zennify.com Google accounts are permitted." },
      { status: 403 });
  }

  const role = grantedRole(email);
  const name = displayName(email);
  const res = NextResponse.json({ ok: true, role, email, name });
  res.cookies.set(COOKIE, sign(email, role, name), {
    httpOnly: true, secure: true, sameSite: "lax", path: "/", maxAge: maxAge(),
  });
  return res;
}
