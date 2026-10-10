// The share service's upstream for the client-link e2e: the local database
// holds no promoted run, and what is under test is usage, not the payload.
// One client, every page answered with its customer-audience envelope.
const http = require("http");
const ID = "e2e-client-cu", NAME = "E2E Credit Union", RUN = "e2e-run-0001";
http.createServer((req, res) => {
  const m = (req.url || "").match(/^\/v1\/entities\/([^/]+)\/([a-z_]+)/);
  if (!m || m[1] !== ID) { res.writeHead(404, { "content-type": "application/json" }); return res.end('{"error":"not_found"}'); }
  const u = new URL(req.url, "http://x");
  if (u.searchParams.get("audience") !== "customer") { res.writeHead(400); return res.end('{"error":"audience"}'); }
  res.writeHead(200, { "content-type": "application/json" });
  res.end(JSON.stringify({ entity: { display_id: ID, entity_name: NAME, sub_vertical: "CREDIT_UNION" },
    run: { run_id: RUN, request_id: RUN, assessment_date: "2026-10-01", composite: 2.4 },
    page: m[2], sections: {} }));
}).listen(Number(process.env.STUB_PORT || 8091), "127.0.0.1");
module.exports = { ID, NAME, RUN };
