// The signed-in person behind an API request.
//
// The session cookie (lib/session.js) lives 8 hours from when it was minted,
// but a tab lives as long as it is open: 2026-10-08, the owner's Admin ›
// Users & roles changes read "admin_session_required" once the morning's
// cookie lapsed in a tab that was still open. Only a document load used to
// re-mint it, so every API route was one long-open tab away from refusing a
// person IAP had just verified.
//
// So every API route asks here. A valid cookie is the answer. When it has
// lapsed, the IAP assertion Google's front end puts on EVERY request to this
// service re-establishes the person — verified exactly as at sign-in
// (lib/iap.js), the role re-read from the users table (lib/roles.js), a
// deactivated account refused — and the cookie is re-issued on the same
// response. Nothing a client sends can stand in for either.
import { COOKIE, maxAge, sign, verify } from "./session.js";
import { verifyIapAssertion } from "./iap.js";
import { displayName, domainOk } from "./identity.js";
import { resolveAccess } from "./roles.js";

// `jar` is the route's `cookies()` (next/headers): passed in rather than
// imported, so this module carries no framework import and its rule is
// testable on its own (tests/request-session.test.js).
export async function requestSession(req, jar) {
  const fromCookie = verify(jar.get(COOKIE)?.value);
  if (fromCookie) return fromCookie;
  const assertion = req && req.headers ? req.headers.get("x-goog-iap-jwt-assertion") : null;
  const iap = await verifyIapAssertion(assertion);
  if (!iap || !domainOk(iap.email)) return null;
  const access = await resolveAccess(iap.email, assertion);
  if (!access.active) return null;
  const name = displayName(iap.email);
  try {
    jar.set(COOKIE, sign(iap.email, access.role, name), {
      httpOnly: true, secure: true, sameSite: "lax", path: "/", maxAge: maxAge(),
    });
  } catch {
    // A context that cannot set cookies still answers with the identity.
  }
  return { email: iap.email, role: access.role, name };
}
