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
    "playwright",
    path.join(WEB, "node_modules", "playwright-core"),
    path.join(WEB, "node_modules", "playwright"),
    ...fsGlob("/tmp/claude-0", "scratchpad/node_modules/playwright-core"),
  ].filter(Boolean);
  for (const p of candidates) {
    try { return require(p); } catch { /* keep looking */ }
  }
  return null;
}

/* WHERE THE BROWSER IS, in one place.
 *
 * Nine files had grown their own copy of this, each reading only
 * /opt/pw-browsers — the path this container happens to use. On a CI runner
 * `npx playwright install` puts it under ~/.cache/ms-playwright instead, so
 * every browser-driven suite in this directory resolved no Chromium there and
 * SKIPPED. They reported `# pass 147` locally and enforced nothing on a pull
 * request, which is the same shape as a Python suite skipping for want of a
 * database: green meaning "not run", with nothing saying so.
 */
function resolveChromium() {
  if (process.env.CHROMIUM_PATH && fs.existsSync(process.env.CHROMIUM_PATH)) {
    return process.env.CHROMIUM_PATH;
  }
  // PLAYWRIGHT_BROWSERS_PATH is AUTHORITATIVE when set, the way Playwright
  // itself treats it — an image that pins a browser directory means that
  // directory, and searching past it would launch a different build from the
  // one the environment installed.
  const roots = process.env.PLAYWRIGHT_BROWSERS_PATH
    ? [process.env.PLAYWRIGHT_BROWSERS_PATH]
    : ["/opt/pw-browsers",
       path.join(process.env.HOME || "/root", ".cache", "ms-playwright")];
  // The layout is NOT stable across Playwright releases and a hardcoded list
  // of paths is how this broke on its first CI run: the container ships
  // chromium-1194 with `chrome-linux/chrome`, and `npx playwright@1.62.1
  // install` writes chromium-1234 with `chrome-linux64/chrome`. Known paths
  // first because they are cheap, then a shallow scan of the build directory
  // for an executable with the right name, so the next rename costs nothing.
  const KNOWN = ["chrome-linux/chrome", "chrome-linux64/chrome",
                 "chrome-linux/headless_shell", "chrome-linux64/headless_shell",
                 "chrome-mac/Chromium.app/Contents/MacOS/Chromium"];
  const NAMES = new Set(["chrome", "headless_shell", "chromium"]);
  for (const root of roots) {
    let entries;
    try { entries = fs.readdirSync(root); } catch { continue; }
    for (const d of entries.filter((x) => x.startsWith("chromium"))) {
      for (const exe of KNOWN) {
        const p = path.join(root, d, exe);
        if (fs.existsSync(p)) return p;
      }
      let subs;
      try { subs = fs.readdirSync(path.join(root, d)); } catch { continue; }
      for (const sub of subs) {
        for (const name of NAMES) {
          const p = path.join(root, d, sub, name);
          try {
            if (fs.statSync(p).isFile()) { fs.accessSync(p, fs.constants.X_OK); return p; }
          } catch { /* not this one */ }
        }
      }
    }
  }
  return null;
}

/* A browser suite that SKIPS must not read as a browser suite that passed.
 *
 * Returns the node:test `skip` value: `false` when the suite can run, a
 * reason string when it cannot — except under CI, where it THROWS. On a
 * developer's laptop without a browser, skipping is a convenience; on a pull
 * request it is a check silently not running, and this repo has now paid for
 * that twice in one week.
 */
function browserSkip() {
  const ok = resolvePlaywright() && resolveChromium();
  if (ok) return false;
  const why = "playwright or Chromium is not resolvable here";
  if (process.env.CI) {
    throw new Error(
      `${why}. In CI this is a FAILURE, not a skip: every browser-driven `
      + `suite in apps/web/tests depends on it, and a skipped suite reports `
      + `green while asserting nothing. Install it in the workflow `
      + `(npx playwright install --with-deps chromium).`);
  }
  return why;
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
 * `audience_default` in app-root.jsx has been both values and is now
 * "internal" (owner instruction, 2026-08-19). A suite that cares which body is
 * on screen must therefore ASK for the one it is asserting rather than lean on
 * the default: the assertions stay true whichever way that line goes, which is
 * the only way a landing-position decision can be changed without a sweep
 * through the suites.
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

/* The one assertion every render test should make, whatever it is about.
 *
 * "[object Object]" is what JavaScript prints when a value that is a record
 * reaches a slot that wanted a word. It is never a legitimate render, it is
 * never caught by a shape check on the wire (the payload is well-formed —
 * the coercion happens in the browser), and it does not throw, so nothing
 * else notices.
 *
 * Measured 2026-08-18, reported from a promoted client's rendered Context
 * page. `capped_subcap_ids` is `[{subcap_id, cap_level}]` — the shape the
 * producer prompt asks for in as many words — and the adapter read it as a
 * list of id strings, so it used the record as an object KEY. Three slots
 * printed "[object Object]": the chip, the cell name and "Open [object
 * Object] in the heatmap".
 *
 * The cosmetic half is the smaller half. The resolver then looked
 * "[object Object]" up in the served cell set, missed, and printed "Not
 * carried by this run" beneath a cell the run does carry and caps at M3 —
 * a false statement about the assessment, produced by a display bug.
 *
 * Checks text AND the attributes that become tooltips, because a code
 * escaping into a `title=` is exactly how the last one of these survived a
 * run of the suite that already asserted on innerText.
 */
const STRINGIFIED = /\[object (?:Object|Array|Null|Undefined)\]/;

async function assertNoStringifiedObjects(page, where) {
  const found = await page.evaluate(() => {
    const hits = [];
    const rx = /\[object (?:Object|Array|Null|Undefined)\]/;
    const text = document.body ? document.body.innerText || "" : "";
    for (const line of text.split("\n")) {
      if (rx.test(line)) hits.push(`text: ${line.trim().slice(0, 120)}`);
    }
    for (const el of document.querySelectorAll("[title], [aria-label], [alt]")) {
      for (const a of ["title", "aria-label", "alt"]) {
        const v = el.getAttribute(a);
        if (v && rx.test(v)) hits.push(`@${a}: ${v.slice(0, 120)}`);
      }
    }
    return hits;
  });
  assert.deepStrictEqual(
    found, [],
    `${where}: a record reached a slot that wanted a word. `
    + `Every hit below is a value the adapter stringified instead of reading:`
    + `\n  ${found.join("\n  ")}`);
}

module.exports = { WEB, PUBLIC, JS_DIR, fsGlob, resolvePlaywright,
                   resolveChromium, browserSkip, scriptList,
                   startServer, settle, selectAudience,
                   assertNoStringifiedObjects, STRINGIFIED };
