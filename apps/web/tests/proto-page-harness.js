/* Serve the COMPILED bundle the way the app serves it, and drive it.
 *
 * Extracted from tests/render-boundary.test.js so a second suite could use it
 * without a second copy: two harnesses that drift apart are two different
 * apps under test, and the rules encoded here are the ones this repo has
 * already paid for twice —
 *
 *   · serve public/proto/js, NEVER proto/*.jsx. The app serves the compiled
 *     bundle, so a test that read the sources would verify code that does not
 *     ship. (`npm run build:proto` first, or you measure the previous build.)
 *   · read the script list out of app/route.js rather than copying it, so the
 *     harness cannot drift out of load order with the page it stands in for.
 *   · a hash change does not reload the document: navigate with the hash on
 *     the URL, then reload, or you measure the page you left.
 *   · wait for the DOM to STOP CHANGING, never a fixed delay — and treat both
 *     loaders as traps, because they are static and satisfy any naive
 *     "stopped changing" test while showing nothing.
 */
const assert = require("node:assert");
const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");

const WEB = path.join(__dirname, "..");
const PUBLIC = path.join(WEB, "public");
const JS_DIR = process.env.PROTO_JS_DIR || path.join(PUBLIC, "proto", "js");

function fsGlob(root, tail) {
  const out = [];
  try {
    for (const a of fs.readdirSync(root)) {
      for (const b of fs.readdirSync(path.join(root, a))) {
        out.push(path.join(root, a, b, tail));
      }
    }
  } catch { /* no scratchpad here */ }
  return out;
}

function resolvePlaywright() {
  const candidates = [
    process.env.PLAYWRIGHT_CORE,
    "playwright-core",
    path.join(WEB, "node_modules", "playwright-core"),
    ...fsGlob("/tmp/claude-0", "scratchpad/node_modules/playwright-core"),
  ].filter(Boolean);
  for (const p of candidates) {
    try { return require(p); } catch { /* keep looking */ }
  }
  return null;
}

function scriptList() {
  const src = fs.readFileSync(path.join(WEB, "app", "route.js"), "utf8");
  const block = src.match(/const SCRIPTS = \[([\s\S]*?)\];/);
  assert.ok(block, "app/route.js no longer declares SCRIPTS — update this harness");
  return [...block[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
}

const MIME = { ".js": "text/javascript", ".css": "text/css", ".png": "image/png" };

function startServer(live) {
  const scripts = scriptList();
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>DMA Insights</title><link rel="stylesheet" href="/proto/app.css"></head>
<body><div id="app"></div>
<script>window.DMA_LIVE=${JSON.stringify(live).replace(/</g, "\\u003c")};</script>
${scripts.map((s) => `<script src="/${s}" defer></script>`).join("\n")}
</body></html>`;

  const server = http.createServer((req, res) => {
    const url = (req.url || "/").split("?")[0];
    if (url === "/" || url === "/index.html") {
      res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
      return res.end(html);
    }
    const file = url.startsWith("/proto/js/")
      ? path.join(JS_DIR, url.slice("/proto/js/".length))
      : path.join(PUBLIC, url.replace(/^\//, ""));
    if (!file.startsWith(JS_DIR) && !file.startsWith(PUBLIC)) {
      res.writeHead(403); return res.end();
    }
    fs.readFile(file, (err, buf) => {
      if (err) { res.writeHead(404); return res.end(); }
      res.writeHead(200, { "content-type": MIME[path.extname(file)] || "application/octet-stream" });
      res.end(buf);
    });
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => resolve(
      { server, base: `http://127.0.0.1:${server.address().port}` }));
  });
}

async function settle(page, quietMs = 400, timeoutMs = 15000) {
  try {
    // Both loaders are traps for a "has it stopped changing" wait: the boot
    // screen and the section loader are STATIC, so a settle that only watched
    // the DOM would call either of them a finished page. The wait is therefore
    // for a shell with no loader in it.
    await page.waitForFunction(
      () => !!document.querySelector("#app .main, #app .empty, #app .loader-card .btn")
            && !document.querySelector(".loader-section, .loader-page"),
      null, { timeout: timeoutMs });
  } catch {
    // Report the DEFECT, not the harness. "waitForSelector timed out" says
    // nothing; what actually happened is that React unmounted the tree and
    // #app is empty, or a read failed in a promise and the page is still on
    // its boot screen for ever.
    const seen = await page.evaluate(() => ({
      len: (document.body.innerText || "").length,
      appChildren: document.getElementById("app")
        ? document.getElementById("app").childElementCount : -1,
      head: (document.body.innerText || "").slice(0, 160),
    }));
    assert.fail(`no page ever rendered: #app has ${seen.appChildren} children, `
      + `body is ${seen.len} chars — the tree unmounted or never left the boot `
      + `screen.\n${seen.head}`);
  }
  const started = Date.now();
  let last = "", lastChange = Date.now();
  while (Date.now() - started < timeoutMs) {
    const now = await page.evaluate(() => (document.body.innerText || "").length + ":"
      + document.querySelectorAll("*").length);
    if (now !== last) { last = now; lastChange = Date.now(); }
    else if (Date.now() - lastChange > quietMs) return;
    await new Promise((r) => setTimeout(r, 100));
  }
}

/* Drive the app's OWN audience toggle.
 *
 * The client view now DEFAULTS to the customer body — see app-root.jsx, where
 * `audience_default` moved from "internal" to "customer" because audience is
 * a UI toggle rather than anything derived from the signed-in role, so the old
 * default put reasoning traces, ceilings and the evidence census in front of
 * every reader before they asked. A suite asserting internal-only content
 * therefore has to ASK for the internal body, exactly as an analyst now does.
 */
async function selectAudience(page, which) {
  const want = String(which || "").toLowerCase();
  await page.evaluate((w) => {
    const b = [...document.querySelectorAll("button")]
      .find((n) => (n.textContent || "").trim().toLowerCase() === w);
    if (b) b.click();
  }, want);
  await settle(page);
}

module.exports = { WEB, PUBLIC, JS_DIR, fsGlob, resolvePlaywright, scriptList,
                   startServer, settle, selectAudience };
