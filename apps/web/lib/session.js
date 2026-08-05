// App session: the identity IAP verified (see lib/iap.js) carried in an
// HMAC-signed httpOnly cookie, 8h expiry — matching the prototype's
// stated session policy. The cookie never CREATES identity; /api/signin
// mints it only from a verified Google assertion (or the explicit
// ALLOW_DEV_LOGIN gate in local compose).
import crypto from "crypto";

const SECRET = process.env.SESSION_SECRET || "dev-only-session-secret";
const EIGHT_HOURS = 8 * 60 * 60;

export const COOKIE = "dma_session";

function hmac(payload) {
  return crypto.createHmac("sha256", SECRET).update(payload).digest("base64url");
}

export function sign(email, role, name) {
  const payload = Buffer.from(
    JSON.stringify({ email, role, name, exp: Math.floor(Date.now() / 1000) + EIGHT_HOURS })
  ).toString("base64url");
  return `${payload}.${hmac(payload)}`;
}

export function verify(token) {
  if (!token) return null;
  const [payload, mac] = token.split(".");
  if (!payload || !mac) return null;
  const expect = hmac(payload);
  if (mac.length !== expect.length ||
      !crypto.timingSafeEqual(Buffer.from(mac), Buffer.from(expect))) return null;
  try {
    const body = JSON.parse(Buffer.from(payload, "base64url").toString());
    if (body.exp < Math.floor(Date.now() / 1000)) return null;
    return body;
  } catch {
    return null;
  }
}

export function maxAge() {
  return EIGHT_HOURS;
}
