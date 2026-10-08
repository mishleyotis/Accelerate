// Loaded into the Next server: Google's IAP key list → the e2e key; the
// Cloud Run metadata server (absent locally) → an immediate refusal.
const fs = require("fs");
const JWKS = fs.readFileSync(__dirname + "/jwks.json", "utf8");
const real = globalThis.fetch;
globalThis.fetch = async (url, opts) => {
  const u = String(url && url.url ? url.url : url);
  if (u.startsWith("https://www.gstatic.com/iap/verify/public_key-jwk")) return new Response(JWKS, { status: 200, headers: { "content-type": "application/json" } });
  if (u.startsWith("http://metadata.google.internal")) return new Response("no metadata server", { status: 404 });
  return real(url, opts);
};
