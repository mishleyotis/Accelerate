// mint(email, {aud, expIn}) → an IAP-shaped ES256 assertion signed by the e2e key.
const crypto = require("crypto"), fs = require("fs");
const KEY = crypto.createPrivateKey(fs.readFileSync(__dirname + "/iap-private.pem"));
const b64 = o => Buffer.from(JSON.stringify(o)).toString("base64url");
module.exports = function mint(email, { aud, expIn = 600 } = {}) {
  const now = Math.floor(Date.now() / 1000);
  const h = b64({ alg: "ES256", kid: "e2e-key", typ: "JWT" });
  const p = b64({ iss: "https://cloud.google.com/iap", aud, email, sub: "accounts.google.com:" + email, iat: now, exp: now + expIn });
  const sig = crypto.sign("sha256", Buffer.from(`${h}.${p}`), { key: KEY, dsaEncoding: "ieee-p1363" }).toString("base64url");
  return `${h}.${p}.${sig}`;
};
