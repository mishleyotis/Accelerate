/* The compiled bundle, rendered to markup in-process — no browser.
 *
 * The Playwright suites drive the whole app and are the right tool for layout
 * and interaction. They are the wrong tool for the question most render
 * defects actually are: "given THIS section, what text does THIS card put in
 * front of a reader?" That question needs the real React, the real compiled
 * modules in the browser's load order, a live entity built by the real
 * adapter, and nothing else — so a test can feed a section, render one card,
 * and read the words.
 *
 * Rules carried over from the browser harness, because they are the ones this
 * repo has paid for:
 *   · the COMPILED bundle (public/proto/js), never proto/*.jsx — the app
 *     serves the compiled files, so `npm run build:proto` first;
 *   · the script order is read out of app/route.js, not copied, so this cannot
 *     drift from the page it stands in for;
 *   · app-root.js is the one module NOT loaded: it mounts <App/> into the
 *     document at load time, which is the browser's job, not a card test's.
 */
const fs = require("node:fs");
const path = require("node:path");

const WEB = path.join(__dirname, "..");
const JS_DIR = process.env.PROTO_JS_DIR || path.join(WEB, "public", "proto", "js");
const NM = path.join(WEB, "node_modules");

function scriptOrder() {
  const src = fs.readFileSync(path.join(WEB, "app", "route.js"), "utf8");
  const block = src.match(/const SCRIPTS = \[([\s\S]*?)\];/);
  if (!block) throw new Error("app/route.js no longer declares SCRIPTS — update this harness");
  return [...block[1].matchAll(/"proto\/js\/([^"]+)"/g)].map((m) => m[1])
    .filter((f) => f !== "app-root.js");
}

let loaded = null;

/* Load once per process. The modules publish onto `window`; under node the
   bare names the components use (`DMA`, `Icon`, `fx`) resolve against the
   global object, so `window` IS the global here. */
function load() {
  if (loaded) return loaded;
  global.window = global;
  global.DMA_LIVE = { authed: true, role: "ADMIN", entities: [] };
  global.React = require(path.join(NM, "react"));
  global.ReactDOM = require(path.join(NM, "react-dom"));
  global.location = global.location || { hash: "" };
  global.addEventListener = global.addEventListener || (() => {});
  global.removeEventListener = global.removeEventListener || (() => {});
  const el = () => ({ style: {}, appendChild() {}, setAttribute() {} });
  global.document = global.document || {
    addEventListener() {}, removeEventListener() {},
    querySelectorAll: () => [], querySelector: () => null,
    getElementById: () => null, createElement: el,
    body: el(), documentElement: el(), head: el(),
  };
  for (const f of scriptOrder()) require(path.join(JS_DIR, f));
  loaded = {
    server: require(path.join(NM, "react-dom", "server")),
    win: global,
  };
  return loaded;
}

/* Install one live entity, built by the REAL adapter from a pages map of the
   wire shape: {overview: {sections: {name: {data, ...envelope}}}, ...}. */
function installEntity(entityId, pages, extras) {
  const { win } = load();
  // The same call the browser loader makes (utils.jsx useLiveEntity), so the
  // section-state registry the cards read empty states from is built the
  // same way too.
  const built = win.buildLiveEntity(entityId, pages, extras || {});
  win.DMA_ENTITY = built;
  return built;
}

/* Render one component to static markup, inside the app context a page would
   give it. `ctx` overrides the context value (audience, role, navigate…). */
function render(Component, props, ctx) {
  const { server, win } = load();
  const value = { audience: "internal", role: "ADMIN", route: { params: {} },
                  navigate: () => {}, pushToast: () => {}, ...(ctx || {}) };
  const el = win.React.createElement(win.AppCtx.Provider, { value },
    win.React.createElement(Component, props || {}));
  return server.renderToStaticMarkup(el);
}

/* The words a reader sees: tags out, entities decoded, whitespace collapsed. */
function textOf(html) {
  return String(html)
    .replace(/<(script|style)[\s\S]*?<\/\1>/g, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"').replace(/&#x27;/g, "'").replace(/&#39;/g, "'")
    .replace(/\s+/g, " ").trim();
}

module.exports = { load, installEntity, render, textOf, JS_DIR };
