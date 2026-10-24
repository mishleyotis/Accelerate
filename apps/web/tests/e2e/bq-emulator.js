// What BigQuery holds after the dmai-usage sink, for the e2e: every usage_v
// line both services wrote to stdout, answered the way lib/usage-store.js's
// three queries read them (eventsSql · lastSeenSql · linksSql), field by the
// same names. It proves the lines carry what the reads expect and that the
// page renders it. The SQL itself is proven on BigQuery by
// infra/diagnose_usage.sh at the end of every deploy.
const fs = require("fs");

function linesOf(files) {
  const out = [];
  for (const f of files) {
    for (const raw of fs.readFileSync(f, "utf8").split("\n")) {
      if (!raw.startsWith("{")) continue;
      try { const j = JSON.parse(raw); if (j.usage_v === 1 && j.usage) out.push(j.usage); } catch {}
    }
  }
  return out.sort((a, b) => a.at.localeCompare(b.at));
}

const cell = (v) => ({ v: v == null ? null : typeof v === "object" ? JSON.stringify(v) : String(v) });
const row = (vals) => ({ f: vals.map(cell) });

module.exports = function emulator(files, wireFields) {
  const fetchImpl = async (url, opts) => {
    const body = opts && opts.body ? JSON.parse(opts.body) : null;
    const q = body ? body.query : "";
    const U = linesOf(files);
    let rows;
    if (/GROUP BY email/.test(q)) {
      const by = {};
      for (const u of U) {
        const e = u.email ? String(u.email).toLowerCase() : null;
        const k = e || "";
        const r = by[k] || (by[k] = { email: e, last: u.at, first: u.at, client: true });
        if (u.at > r.last) r.last = u.at;
        if (u.at < r.first) r.first = u.at;
        if (u.role !== "CLIENT") r.client = false;
      }
      rows = Object.values(by).map((r) => row([r.email, r.last, r.first, r.client]));
    } else if (/= 'link_minted'/.test(q)) {
      rows = U.filter((u) => u.type === "link_minted").map((u) => row([u.at, String(u.email).toLowerCase(),
        u.role, u.link_jti, u.client_id, u.run_id, u.recipients || null, u.domains || null, u.expires_at]));
    } else if (/INTERVAL @days/.test(q)) {
      const tenMin = Date.now() - 10 * 60 * 1000;
      rows = U.filter((u) => u.type !== "heartbeat" || Date.parse(u.at) >= tenMin).map((u) =>
        row(wireFields.map((f) => f === "t" ? u.at
          : f === "email" || f === "attempted_email" ? (u[f] ? String(u[f]).toLowerCase() : null)
          : u[f])));
    } else {
      return new Response(JSON.stringify({ error: { message: "unexpected query" } }), { status: 400 });
    }
    return new Response(JSON.stringify({ jobComplete: true, rows }), { status: 200 });
  };
  return { fetchImpl, lines: () => linesOf(files) };
};
