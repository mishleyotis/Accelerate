// Verified Google identity from Cloud Run's integrated IAP.
//
// IAP fronts every request to this service and forwards the signed
// assertion in x-goog-iap-jwt-assertion. The ONLY identity this app
// trusts is that JWT, verified here: ES256 signature against Google's
// published IAP JWKs, issuer, expiry, and (when IAP_AUDIENCE is set)
// the audience binding to THIS service. The typed-email interim gate is
// gone — a body-supplied email is never an identity.
import crypto from "crypto";

const JWKS_URL = "https://www.gstatic.com/iap/verify/public_key-jwk";
const ISSUER = "https://cloud.google.com/iap";

let jwksCache = { keys: null, fetched: 0 };

async function jwks() {
  const now = Date.now();
  if (jwksCache.keys && now - jwksCache.fetched < 12 * 60 * 60 * 1000) {
    return jwksCache.keys;
  }
  const r = await fetch(JWKS_URL, { cache: "no-store" });
  if (!r.ok) throw new Error(`IAP JWKS fetch failed: ${r.status}`);
  const body = await r.json();
  jwksCache = { keys: body.keys || [], fetched: now };
  return jwksCache.keys;
}

function b64json(part) {
  return JSON.parse(Buffer.from(part, "base64url").toString());
}

// Returns { email, sub } for a valid assertion, else null. Never throws
// to the caller on bad input — absence of identity is a normal state
// (health checks, local dev), and the caller fails closed on null.
export async function verifyIapAssertion(token) {
  try {
    if (!token) return null;
    const [h, p, sig] = token.split(".");
    if (!h || !p || !sig) return null;
    const header = b64json(h);
    const payload = b64json(p);
    if (header.alg !== "ES256") return null;

    const keys = await jwks();
    const jwk = keys.find((k) => k.kid === header.kid);
    if (!jwk) return null;
    const key = crypto.createPublicKey({ key: jwk, format: "jwk" });
    const ok = crypto.verify(
      "sha256",
      Buffer.from(`${h}.${p}`),
      { key, dsaEncoding: "ieee-p1363" },
      Buffer.from(sig, "base64url")
    );
    if (!ok) return null;

    const now = Math.floor(Date.now() / 1000);
    if (payload.iss !== ISSUER) return null;
    if (typeof payload.exp !== "number" || payload.exp < now) return null;
    if (typeof payload.iat === "number" && payload.iat > now + 300) return null;
    const expectAud = process.env.IAP_AUDIENCE;
    if (expectAud && payload.aud !== expectAud) return null;
    if (!payload.email) return null;
    return { email: String(payload.email).toLowerCase(), sub: payload.sub || null };
  } catch {
    return null;
  }
}

// The verified caller identity for a Next.js Request, or null.
export async function iapIdentity(req) {
  return verifyIapAssertion(req.headers.get("x-goog-iap-jwt-assertion"));
}
