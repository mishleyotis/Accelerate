// A stand-in for Google's IAP signing key: one ES256 key, published as a JWKS.
const crypto = require("crypto"), fs = require("fs");
const { privateKey, publicKey } = crypto.generateKeyPairSync("ec", { namedCurve: "P-256" });
const jwk = publicKey.export({ format: "jwk" });
fs.writeFileSync(__dirname + "/jwks.json", JSON.stringify({ keys: [{ ...jwk, kid: "e2e-key", alg: "ES256", use: "sig" }] }));
fs.writeFileSync(__dirname + "/iap-private.pem", privateKey.export({ type: "pkcs8", format: "pem" }));
