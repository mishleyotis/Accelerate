/* Open the app and confirm — the owner's standing directive, as a command.
 *
 * "Always open the app and confirm." Every earlier verification stopped one
 * layer short of a reader: tests passed, bundles matched byte-for-byte, and
 * twice the page a person actually saw still carried the defect. This script
 * is the missing layer: it serves the COMPILED bundle exactly as production
 * serves it (same scripts, same order, same boot object shape), injects the
 * LIVE payload pulled from the deployed API, opens real routes in the
 * pre-installed Chromium, screenshots them, and asserts the fix in the
 * rendered DOM.
 *
 * It is not a substitute for loading the deployed page itself — that needs
 * the IAP grant (MEM-0065) — but combined with verify_deployed.py's
 * byte-match it is equivalent: same bytes, same payload, same renderer.
 *
 * Usage:
 *   node tests/open-app.js --payload <dir> [--entity <slug>] [--shots <dir>]
 *                          [--checks <file.json>] [--audience internal|customer]
 *
 * --payload  directory of <page>_<audience>.json files as saved from the API
 * --checks   JSON: [{route, name, assert: [{kind, arg…}]}] — see CHECKS below
 *            for the built-in Phase A set used when no file is given.
 * Exit 0 all checks pass; 1 any fail (screenshots saved either way).
 */
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const { startServer, settle, resolvePlaywright } = require("./proto-page-harness.js");

const args = {};
for (let i = 2; i < process.argv.length; i += 2) {
  args[process.argv[i].replace(/^--/, "")] = process.argv[i + 1];
}
const PAYLOAD_DIR = args.payload;
const ENTITY = args.entity || "baxter-credit-union-bcu";
const SHOTS = args.shots || "/tmp/open-app-shots";
const AUDIENCE = args.audience || "internal";
if (!PAYLOAD_DIR) { console.error("--payload <dir> is required"); process.exit(2); }
fs.mkdirSync(SHOTS, { recursive: true });

function payloadFor(page) {
  // The BFF serves the API body verbatim; so do we. A page the run does not
  // carry returns 404 exactly as production would, so an absent-section state
  // is tested rather than papered over.
  for (const aud of [AUDIENCE, "internal"]) {
    const f = path.join(PAYLOAD_DIR, `${page}_${aud}.json`);
    if (fs.existsSync(f)) return JSON.parse(fs.readFileSync(f, "utf8"));
  }
  return null;
}

/* The Phase A confirmation set. Each check names the fix it proves and fails
 * with the DOM it actually saw. `kind`s:
 *   text_present / text_absent   — innerText of the settled page
 *   count_at_most                — occurrences of a string in innerText
 *   title_absent                 — no [title] attribute contains the string
 */
const CHECKS = args.checks ? JSON.parse(fs.readFileSync(args.checks, "utf8")) : [
  {
    route: `#/clients/${ENTITY}/overview`, name: "firmographics",
    admin: true,
    assert: [
      // Held ≠ silent ≠ absent (the founded field is quarantined WITH a
      // reason on the reference client; it must render as a held row, and
      // the website must be a queued gap, and no bare em dash anywhere).
      { kind: "text_present", arg: "Founded", why: "held pinned field renders a row (was: no row at all)" },
      { kind: "text_present", arg: "Website", why: "mandatory field renders a row" },
      { kind: "text_present", arg: "Not stated", why: "silent gap says its kind" },
      // One CAGR row, not two ("Cagr" was the passthrough duplicate).
      { kind: "count_at_most", arg: "CAGR", n: 1, why: "duplicate CAGR row removed" },
      { kind: "text_absent", arg: "Cagr", why: "the humanised duplicate is gone" },
    ],
  },
  {
    route: `#/clients/${ENTITY}/context`, name: "issue-timeline",
    admin: true,
    assert: [
      // ISS-001 is REMEDIATED with no resolution date: the bar's tooltip must
      // say so, never assert the matter runs to today.
      { kind: "title_absent", arg: "→ open · Employee email", why: "remediated matter no longer drawn as open" },
      { kind: "title_present_somewhere", arg: "resolution date not stated", why: "terminal status without a date says so" },
    ],
  },
  {
    route: `#/clients/${ENTITY}/techstack`, name: "tech-stack",
    admin: true,
    assert: [
      // The run names five peers; the page must stop denying it. The claim
      // text lives on the detail sub-page, but PEER_SETS feeds this page's
      // peer strip too — assert the denial text is gone wherever rendered.
      { kind: "text_absent", arg: "states no peer set", why: "peerSets adapted from peer_deployments" },
    ],
  },
];

async function main() {
  const chromiumPath = process.env.CHROMIUM_PATH
    || fs.readdirSync("/opt/pw-browsers").filter((d) => d.startsWith("chromium"))
        .map((d) => `/opt/pw-browsers/${d}/chrome-linux/chrome`)
        .find((p) => fs.existsSync(p));
  assert.ok(chromiumPath, "no Chromium under /opt/pw-browsers");
  const pw = resolvePlaywright();
  assert.ok(pw, "playwright-core is not resolvable — CI-02: an unlaunchable "
    + "browser gate is a FAILURE, not a skip");

  const directory = payloadFor("../directory") ||
    JSON.parse(fs.readFileSync(path.join(PAYLOAD_DIR, "..", "directory.json"), "utf8"));
  const boot = {
    authed: true, role: "ADMIN", email: "qa@zennify.com", name: "QA",
    entities: directory.entities || [],
    subvertical_labels: directory.subvertical_labels || {},
    active_runs: directory.active_runs || [],
    pending_review: directory.pending_review || [],
    catalogue_version: "v7.0", dev_login: false,
  };

  const browser = await pw.chromium.launch({ executablePath: chromiumPath, args: ["--no-sandbox"] });
  const { server, base } = await startServer(boot);
  const stamp = new Date().toISOString().replace(/[-:]/g, "").slice(0, 15) + "Z";
  let failures = 0;

  for (const chk of CHECKS) {
    const ctx = await browser.newContext({ viewport: { width: 1512, height: 1100 } });
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e.message).split("\n")[0]));
    await page.route("**/api/entity/**", (route) => {
      const m = route.request().url().match(/\/api\/entity\/[^/]+\/([^/?]+)/);
      const body = payloadFor(m ? m[1] : "overview");
      route.fulfill(body
        ? { status: 200, contentType: "application/json", body: JSON.stringify(body) }
        : { status: 404, contentType: "application/json", body: '{"error":"not_found"}' });
    });
    await page.goto(`${base}/${chk.route}`, { waitUntil: "domcontentloaded" });
    await settle(page);

    const shot = path.join(SHOTS,
      `${chk.name}-${ENTITY}-ADMIN-${AUDIENCE}-1512-${stamp}.png`);
    await page.screenshot({ path: shot, fullPage: true });

    const text = await page.evaluate(() => document.body.innerText || "");
    const titles = await page.evaluate(() =>
      [...document.querySelectorAll("[title]")].map((n) => n.getAttribute("title")));

    for (const a of chk.assert) {
      let ok, detail = "";
      if (a.kind === "text_present") ok = text.includes(a.arg);
      else if (a.kind === "text_absent") ok = !text.includes(a.arg);
      else if (a.kind === "count_at_most") {
        const n = text.split(a.arg).length - 1;
        ok = n <= a.n; detail = ` (found ${n}, allowed ${a.n})`;
      } else if (a.kind === "title_absent")
        ok = !titles.some((t) => t && t.includes(a.arg));
      else if (a.kind === "title_present_somewhere")
        ok = titles.some((t) => t && t.includes(a.arg));
      else { ok = false; detail = ` (unknown kind ${a.kind})`; }
      console.log(`${ok ? "PASS" : "FAIL"}  ${chk.name} · ${a.kind}(${a.arg})${detail} — ${a.why}`);
      if (!ok) failures += 1;
    }
    if (errors.length) {
      console.log(`FAIL  ${chk.name} · page errors: ${errors.join(" | ")}`);
      failures += 1;
    }
    console.log(`      shot: ${shot}`);
    await ctx.close();
  }

  await browser.close();
  server.close();
  console.log(failures ? `\n${failures} check(s) FAILED` : "\nall checks passed in the opened app");
  process.exit(failures ? 1 : 0);
}

main().catch((e) => { console.error(e); process.exit(2); });
