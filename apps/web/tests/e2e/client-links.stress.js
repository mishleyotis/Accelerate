// Client-link usage under load, on the real dmai-web + dmai-share:
//   · 6 links minted at once → 6 link_minted lines, 6 distinct ids, none lost
//   · 12 readers of one link, each firing 10 beacons of 5 events at once
//     (600 events in flight) → every beacon 204, exactly 50 lines per reader,
//     every line under the address that sent it — no cross-attribution
//   · one reader removed from the link mid-stream → refused once the ledger
//     change is seen (≤ REVOCATION_TTL_MS), and nothing more logged for them
const mint = require(__dirname + "/mint.js");
const emulator = require(__dirname + "/bq-emulator.js");
const AUD = "/projects/1/locations/us-central1/services/dmai-web";
const WEB = "http://localhost:3005", SHARE = "http://localhost:3006";
const ID = "e2e-client-cu", RUN = "e2e-run-0001";
const results = [];
const check = (name, ok, detail) => { results.push(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`); };
const wait = ms => new Promise(r => setTimeout(r, ms));
const staffHeaders = () => ({ "content-type": "application/json", "x-goog-iap-jwt-assertion": mint("dma@zennify.com", { aud: AUD }) });

(async () => {
  process.env.BQ_ACCESS_TOKEN = "e2e-emulator";
  const S = await import("../../lib/usage-store.js");
  const emu = emulator([__dirname + "/web.log", __dirname + "/share.log"], S.WIRE_FIELDS);
  const lines = (pred) => emu.lines().filter(pred);

  // 1. Concurrent minting.
  const mints = await Promise.all(Array.from({ length: 6 }, (_, i) => fetch(`${WEB}/api/share`, { method: "POST", headers: staffHeaders(),
    body: JSON.stringify({ entity: ID, run: RUN, recipients: `stress${i}@e2e-stress.org`, days: 7 }) }).then(async r => ({ s: r.status, b: await r.json() }))));
  await wait(500);
  const jtis = mints.map(m => m.b.jti);
  const ml = lines(u => u.type === "link_minted" && jtis.includes(u.link_jti));
  check("6 concurrent mints → 6 links, 6 link_minted lines, 6 distinct ids",
    mints.every(m => m.s === 200) && new Set(jtis).size === 6 && ml.length === 6 && new Set(ml.map(u => u.link_jti)).size === 6,
    `statuses=${mints.map(m => m.s).join(",")} lines=${ml.length}`);

  // 2. Twelve readers of one link (admitted by the organisation's domain).
  const link = mints[0].b;
  const token = link.url.split("/s/")[1].split("#")[0];
  const readers = Array.from({ length: 12 }, (_, i) => `reader${String(i).padStart(2, "0")}@e2e-stress.org`);
  const cookies = {};
  await Promise.all(readers.map(async e => {
    const r = await fetch(`${SHARE}/s/${token}/access`, { method: "POST", redirect: "manual",
      headers: { "content-type": "application/x-www-form-urlencoded" }, body: `email=${encodeURIComponent(e)}` });
    cookies[e] = (r.headers.get("set-cookie") || "").split(";")[0];
  }));
  check("12 readers admitted at once, each with their own access cookie", readers.every(e => /^dma_share_/.test(cookies[e])) && new Set(Object.values(cookies)).size === 12);
  const sidOf = (e, b) => `s${e.slice(6, 8)}x${String(b).padStart(2, "0")}abcd`;
  const beacon = (e, b) => fetch(`${SHARE}/s/${token}/api/usage`, { method: "POST",
    headers: { cookie: cookies[e], "content-type": "application/json" },
    body: JSON.stringify({ events: Array.from({ length: 5 }, (_, k) => ({ type: "page_view", sid: sidOf(e, b), path: `/clients/${ID}/${["overview", "insights", "heatmap"][k % 3]}`, dwell_ms: 1000 + k, cont: false })) }) }).then(r => r.status);
  const t0 = Date.now();
  const statuses = await Promise.all(readers.flatMap(e => Array.from({ length: 10 }, (_, b) => beacon(e, b))));
  const ms = Date.now() - t0;
  await wait(800);
  const pv = lines(u => u.type === "page_view" && u.link_jti === link.jti);
  const per = Object.fromEntries(readers.map(e => [e, pv.filter(u => u.email === e).length]));
  const crossed = pv.filter(u => !u.sid.startsWith(`s${u.email.slice(6, 8)}x`));
  check("120 concurrent beacons all accepted", statuses.every(s => s === 204), `non-204: ${statuses.filter(s => s !== 204).length} · ${ms} ms`);
  check("exactly 50 lines per reader, 600 in all", pv.length === 600 && Object.values(per).every(n => n === 50), JSON.stringify(per));
  check("no line attributed to another reader", crossed.length === 0, `crossed=${crossed.length}`);

  // 3. Remove one reader from the link mid-stream.
  const gone = readers[0];
  const rm = await fetch(`${WEB}/api/admin/share-links`, { method: "POST", headers: staffHeaders(),
    body: JSON.stringify({ link: link.jti, action: "remove", email: gone }) });
  check("admin removes one reader from the link", rm.status === 200, `status ${rm.status}`);
  await wait(16000);   // REVOCATION_TTL_MS is 15 s
  const n0 = lines(u => u.email === gone).length;
  const after = await Promise.all([beacon(gone, 90), beacon(gone, 91), beacon(readers[1], 92)]);
  await wait(500);
  check("the removed reader is refused (401) and nothing more is logged for them; others still are",
    after[0] === 401 && after[1] === 401 && after[2] === 204 && lines(u => u.email === gone).length === n0,
    `statuses=${after.join(",")}`);

  console.log(results.join("\n"));
  const failed = results.filter(r => r.startsWith("FAIL")).length;
  console.log(`\nclient links stress: ${results.length - failed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); console.log(results.join("\n")); process.exit(1); });
