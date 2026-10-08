// Concurrency against the real API (what dmai-web forwards), and the real DB.
const mint = require(__dirname + "/mint.js");
const { execSync } = require("child_process");
const crypto = require("crypto");
const AUD = "/projects/1/locations/us-central1/services/dmai-web", API = "http://127.0.0.1:8090";
const sql = q => execSync(`psql -h localhost -U postgres -d dma_insights -tAc "${q}"`, { env: { ...process.env, PGPASSWORD: "local" } }).toString().trim();
const T = mint("dma@zennify.com", { aud: AUD });
const post = (body) => fetch(`${API}/v1/admin/users`, { method: "POST", headers: { "x-dmai-iap-assertion": T, "idempotency-key": crypto.randomUUID(), "content-type": "application/json" }, body: JSON.stringify(body) }).then(async r => `${r.status} ${(await r.text()).slice(0, 90)}`);
(async () => {
  sql("delete from session_log where user_id in (select id from users where email like 'stress.%')");
  sql("delete from idempotency_keys where response::text like '%stress.%'");
  sql("delete from users where email like 'stress.%'");
  const out = [];
  // A. 5 simultaneous invites of the same new person (a double/triple click).
  const a = await Promise.all([1,2,3,4,5].map(() => post({ email: "stress.dup@zennify.com", role: "ADMIN" })));
  out.push(["A same-person invites x5", a.map(x => x.slice(0, 3)).join(","), sql("select count(*) from users where email='stress.dup@zennify.com'"), a.find(x => x.startsWith("5")) || ""]);
  // B. 20 simultaneous role flips on one person.
  const b = await Promise.all(Array.from({ length: 20 }, (_, i) => post({ email: "stress.dup@zennify.com", role: i % 2 ? "ANALYST" : "AE" })));
  const role = sql("select role from users where email='stress.dup@zennify.com'");
  const logs = sql("select count(*) from session_log s join users u on u.id=s.user_id where u.email='stress.dup@zennify.com'");
  out.push(["B role flips x20", [...new Set(b.map(x => x.slice(0, 3)))].join(","), `final=${role} session_log=${logs}`, b.find(x => x.startsWith("5")) || ""]);
  // C. 10 simultaneous first visits by a new person (POST /v1/me enrolment).
  const tNew = mint("stress.visitor@zennify.com", { aud: AUD });
  const c = await Promise.all(Array.from({ length: 10 }, () => fetch(`${API}/v1/me`, { method: "POST", headers: { "x-dmai-iap-assertion": tNew } }).then(async r => `${r.status} ${(await r.text()).slice(0, 80)}`)));
  out.push(["C first visits x10", [...new Set(c.map(x => x.slice(0, 3)))].join(","), `rows=${sql("select count(*) from users where email='stress.visitor@zennify.com'")} logins=${sql("select count(*) from session_log s join users u on u.id=s.user_id where u.email='stress.visitor@zennify.com' and event='login'")}`, c.find(x => x.startsWith("5")) || ""]);
  out.forEach(r => console.log(r.join("  |  ")));
})();
