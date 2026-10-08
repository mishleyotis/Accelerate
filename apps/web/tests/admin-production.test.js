/* The admin console as production serves it (DMA_LIVE set).
 *
 * Admin audit, 2026-10-07: the console shipped surfaces that did nothing in
 * production — Import & jobs played a scripted "SSE LIVE" crawl with invented
 * counts, Import audit read a fixture queue whose buttons wrote nothing, the
 * Pending review card read a list the API always returns empty, and "Full
 * re-scan" fired the same Job as the delta scan. Owner's instruction: hide
 * what is not functional. And for Usage analytics: no placeholders — real,
 * live metrics or a named state saying why there are none.
 *
 * SSR, in-process against the compiled bundle (`npm run build:proto`).
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const H = require("./ssr-harness");

const { win } = H.load();
win.DMA_LIVE.import_scans = [];
win.DMA_LIVE.role_grants = { admins: ["dma@zennify.com"], analysts: ["analyst.one@zennify.com"], default: "AE" };
win.DMA_LIVE.email = "dma@zennify.com";

// The page frame (PageShell → TopBar) needs app-root.js's Portal, and the SSR
// harness does not load app-root.js (it mounts the app). These tests are about
// the page bodies, so the frame renders its children and nothing else.
win.PageShell = ({ children }) => win.React.createElement(win.React.Fragment, null, children);

const ctx = { role: "ADMIN", route: { path: "/admin", params: {} }, openAlerts: 0, activeRuns: 0,
              setAuthed() {}, sidebarOpen: false, setSidebarOpen() {} };

test("production does not serve Import & jobs or Import audit", () => {
  assert.equal(win.adminRouteHidden("/admin/import"), true);
  assert.equal(win.adminRouteHidden("/admin/import/audit"), true);
  assert.equal(win.adminRouteHidden("/admin"), false);
  assert.equal(win.adminRouteHidden("/admin/usage"), false);
  // The router consults the same list (app-root.js is not loaded by the SSR
  // harness — it mounts the app — so its source is read instead).
  const root = fs.readFileSync(path.join(__dirname, "..", "proto", "app-root.jsx"), "utf8");
  assert.match(root, /if \(!adminRouteHidden\(path\)\) \{\s*if \(path === "\/admin\/import"\)/);
  assert.match(root, /path === "\/admin\/usage"\)\s+return <UsagePage \/>/);
});

test("the sidebar lists only what production serves", () => {
  const t = H.textOf(H.render(win.Sidebar, {}, ctx));
  assert.ok(t.includes("Admin home"));
  assert.ok(t.includes("Usage analytics"));
  assert.ok(!t.includes("Import & jobs"), t);
  assert.ok(!t.includes("Import audit"), t);
});

test("admin home carries no non-functional surface", () => {
  const t = H.textOf(H.render(win.AdminPage, {}, ctx));
  for (const gone of ["Pending review", "Phase 0 entity inferences", "Full re-scan",
                      "Import audit →", "Job history →", "Import & jobs", "Vertex AI budget"]) {
    assert.ok(!t.includes(gone), `admin home still shows "${gone}"`);
  }
  assert.ok(t.includes("Usage analytics"));
  assert.ok(t.includes("Delta scan"), "the delta scan fires the real Job — it stays");
  assert.ok(t.includes("No scans recorded yet"), "the scan line reads the real (empty) ledger");
  assert.ok(t.includes("Users & roles"));
  // Grants live in the users table (owner adjudication 2026-10-07): the card
  // loads the real roster and carries the prototype's invite control; it
  // never renders the preview's mock people.
  assert.ok(t.includes("Loading users") && t.includes("Invite user"), "live roster controls missing");
  for (const mock of ["Sara Lin", "Tom Reyes", "Dev Patel"]) assert.ok(!t.includes(mock), `mock user "${mock}" in production`);
});

test("the last-scan line states what the ledger row says", () => {
  assert.equal(win.lastScanLabel(null), "No scans recorded yet");
  assert.match(win.lastScanLabel({ started_at: "2026-10-07T10:00:00Z", finished_at: null, status: "running" }),
               /not finished$/);
  assert.match(win.lastScanLabel({ started_at: "2026-10-07T10:00:00Z", finished_at: "2026-10-07T10:01:00Z",
                                   status: "SUCCEEDED" }), /succeeded$/);
});

test("usage surfaces in production render no mock person and no mock number", () => {
  for (const C of [win.UsagePage, win.UsageGlanceCard]) {
    const t = H.textOf(H.render(C, {}, ctx));
    for (const mock of ["Sara Lin", "Mishley Andrade", "Dev Patel", "FSI · East", "Re-engagement"]) {
      assert.ok(!t.includes(mock), `${C.name} shows preview data "${mock}" in production`);
    }
    assert.ok(t.includes("Loading usage"), `${C.name} states its loading state: ${t.slice(0, 200)}`);
  }
});

/* ── the production model, from the wire rows the store returns ── */
const F = ["t", "type", "email", "role", "sid", "page", "client_id", "dwell_ms", "cont", "feature",
           "device", "entered_at", "audience", "acting_role"];
const row = (o) => F.map((f) => (f in o ? o[f] : null));
const NOW = new Date();
const ago = (ms) => new Date(NOW.getTime() - ms).toISOString();
const MIN = 60 * 1000;
function wire(extra) {
  return {
    status: "ok", generated_at: NOW.toISOString(), fields: F,
    recording_since: ago(2 * 24 * 60 * MIN),
    last_seen: { "ae.one@zennify.com": ago(1 * MIN), "dma@zennify.com": ago(40 * 24 * 60 * MIN) },
    events: [
      row({ t: ago(20 * MIN), type: "page_view", email: "ae.one@zennify.com", role: "AE", sid: "sess0000001",
            page: "dashboard", dwell_ms: 60000, cont: false, entered_at: ago(21 * MIN), device: "Desktop · Chrome" }),
      row({ t: ago(10 * MIN), type: "page_view", email: "ae.one@zennify.com", role: "AE", sid: "sess0000001",
            page: "overview", client_id: "golden-1", dwell_ms: 300000, cont: false, entered_at: ago(19 * MIN) }),
      // the same visit resumed after the tab was hidden: time, not a view
      row({ t: ago(5 * MIN), type: "page_view", email: "ae.one@zennify.com", role: "AE", sid: "sess0000001",
            page: "overview", client_id: "golden-1", dwell_ms: 120000, cont: true, entered_at: ago(7 * MIN) }),
      row({ t: ago(4 * MIN), type: "feature", email: "ae.one@zennify.com", role: "AE", sid: "sess0000001",
            page: "overview", client_id: "golden-1", feature: "evidence" }),
      row({ t: ago(1 * MIN), type: "heartbeat", email: "ae.one@zennify.com", role: "AE", sid: "sess0000001",
            page: "heatmap", client_id: "golden-1" }),
      // a server-observed verdict: no browser session
      row({ t: ago(3 * MIN), type: "feature", email: "ae.one@zennify.com", role: "AE",
            page: "insights", client_id: "golden-1", feature: "insight_review" }),
      ...(extra || []),
    ],
  };
}

test("page views, continuations, heartbeats and server features build one honest session", () => {
  const m = win.uaModelFromWire(wire());
  assert.equal(m.status, "ok");
  assert.equal(m.sessions.length, 1);
  const s = m.sessions[0];
  assert.equal(s.live, true, "a heartbeat a minute ago is live");
  const views = s.pages.filter((p) => p.view);
  assert.deepEqual(views.map((p) => p.key), ["dashboard", "overview", "heatmap"],
                   "the live page (heatmap, not yet reported) shows as the current page");
  assert.equal(s.pages.find((p) => p.key === "overview").secs, 420, "300 s + the 120 s continuation");
  assert.equal(s.secs, 480);
  const { from, to } = win.uaDayBounds(m.now, 7);
  const a = win.uaAgg(m, from, to);
  assert.equal(a.views, 2, "the live page is not a view until it is reported");
  assert.ok(!a.pages.some((p) => p.key === "heatmap"));
  assert.equal(a.feat.evidence, 1);
  assert.equal(a.feat.insight_review, 1, "server-side features count without a session");
});

test("people are everyone granted plus everyone seen; status follows last seen", () => {
  const m = win.uaModelFromWire(wire());
  const { from, to } = win.uaDayBounds(m.now, 7);
  const rows = win.uaRows(m, win.uaAgg(m, from, to), to);
  const by = Object.fromEntries(rows.map((r) => [r.email, r]));
  assert.equal(by["ae.one@zennify.com"].status, "Live");
  assert.equal(by["dma@zennify.com"].status, "Dormant");
  assert.equal(by["dma@zennify.com"].role, "ADMIN");
  assert.equal(by["analyst.one@zennify.com"].status, "Never", "granted but never seen is stated");
  assert.equal(by["analyst.one@zennify.com"].role, "ANALYST");
  assert.ok(rows.every((r) => !("team" in r) || r.team == null), "no team exists in production data");
});

test("no prior-period comparison where recording did not cover it", () => {
  const m = win.uaModelFromWire(wire());
  const { from } = win.uaDayBounds(m.now, 7);
  assert.equal(win.uaPrevCovered(m, new Date(from.getTime() - 7 * 86400000)), false,
               "recording began two days ago, so 'vs prior week' would compare against nothing");
});
