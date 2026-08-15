/* The enrichment register and the surfaces that render it cannot drift apart.
 *
 * Measured 2026-08-14, against the COMPILED bundle pulled out of the running
 * Cloud Run revision's image: the register declared five enrichment-dependent
 * surfaces and exactly one of them — the technology register — carried a
 * renderer. The other four computed `enrichment_status` at read, shipped it
 * through the adapter onto `entity.enrichment`, and rendered nothing. A short
 * leadership roster still read as the whole roster.
 *
 * That is the write-path-with-no-read-path shape, one layer further out than
 * usual: the flag was not missing, it was unrendered. A declaration is only
 * worth what a reader sees, so the register's own key set is the assertion.
 *
 * Run with `npm run test:web`. Reads the compiled bundle, not the JSX, for
 * the same reason adapter.test.js does — the compiled files are what ships.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const JS = path.join(__dirname, "..", "public", "proto", "js");
const REGISTER = path.join(__dirname, "..", "..", "..", "packages", "shared",
                           "enrichment_register.json");

/* Every compiled module, concatenated: which FILE renders a given surface is
   a layout decision and may move, so the test pins that the flag is rendered
   somewhere rather than pinning it to a file it would then have to chase. */
function bundle() {
  return fs.readdirSync(JS)
    .filter((f) => f.endsWith(".js"))
    .map((f) => fs.readFileSync(path.join(JS, f), "utf8"))
    .join("\n");
}

function registerKeys() {
  const raw = JSON.parse(fs.readFileSync(REGISTER, "utf8"));
  return Object.keys(raw.surfaces || raw);
}

test("every declared enrichment surface has a renderer", () => {
  const src = bundle();
  const missing = [];
  for (const key of registerKeys()) {
    // "overview.leadership" is declared page-qualified; the adapter keys
    // `entity.enrichment` by the SECTION alone, which is what a component
    // reads. Compare on the half a renderer actually names.
    const section = key.split(".").pop();
    const re = new RegExp(
      `EnrichmentFlag[\\s\\S]{0,200}?LIVE_ENRICHMENT[\\s\\S]{0,80}?\\b${section}\\b`);
    const alt = new RegExp(
      `LIVE_ENRICHMENT[\\s\\S]{0,80}?\\b${section}\\b[\\s\\S]{0,200}?EnrichmentFlag`);
    if (!re.test(src) && !alt.test(src)) missing.push(key);
  }
  assert.deepStrictEqual(
    missing, [],
    `declared in the enrichment register with no <EnrichmentFlag> reading it: `
    + `${missing.join(", ")}. A surface that computes its own thinness and `
    + `never shows it is the defect this register exists to prevent.`);
});

test("the register declares the five surfaces the build owner asked about", () => {
  /* Stated as a set rather than a count so ADDING a surface is a deliberate
     edit here, and so this test names what the five are. */
  assert.deepStrictEqual(registerKeys().sort(), [
    "overview.firmographics",
    "overview.leadership",
    "overview.sentiment",
    "overview.thought_leadership",
    "techstack.techstack",
  ]);
});

test("the adapter exposes every declared surface on entity.enrichment", () => {
  /* The middle of the chain: compute at read → adapt → render. This is the
     link that was intact when the render link was not, which is precisely why
     the gap survived — the data was there the whole time. */
  const src = fs.readFileSync(path.join(JS, "live-adapter.js"), "utf8");
  const block = src.slice(src.indexOf("enrichment: {"));
  for (const key of registerKeys()) {
    const section = key.split(".").pop();
    assert.ok(block.slice(0, 900).includes(`${section}:`),
              `adapter does not carry ${section} onto entity.enrichment`);
  }
});

test("a finding chip never prints a serialised object", () => {
  /* CG-21 refuses this at submit now, but a run promoted before that gate
     existed is already in the database and the serving path stores what it
     was given. Measured shape, verbatim from the withdrawn run. */
  for (const k of Object.keys(require.cache)) delete require.cache[k];
  global.window = {};
  // utils.js destructures its hooks off React at load, so the stub has to
  // carry every name it names — a thinner one dies on the import line and the
  // failure reads as a broken test rather than a broken chip.
  const noop = () => undefined;
  global.React = {
    Fragment: "Fragment", createElement: () => null,
    useState: (v) => [v, noop], useEffect: noop, useRef: () => ({ current: null }),
    useMemo: (f) => f(), useCallback: (f) => f,
    createContext: () => ({ Provider: null, Consumer: null }), useContext: noop,
    Component: class {}, PureComponent: class {},
  };
  require(path.join(JS, "utils.js"));
  const f = global.window.findingChipId;
  assert.ok(typeof f === "function", "findingChipId is not exported");

  assert.strictEqual(f('{"f_id": "F-1", "e_ids": ["E-CC-139"]}'), "F-1");
  assert.strictEqual(f("F-2"), "F-2");                       // the clean shape
  assert.strictEqual(f({ f_id: "F-3" }), "F-3");             // a real object
  assert.strictEqual(f('{"finding_id": "F-4"}'), "F-4");
  assert.strictEqual(f(""), "");
  assert.strictEqual(f(null), "");
  // Unparseable, and an object with no id: say something, never raw JSON.
  assert.strictEqual(f("{not json"), "{not json");
  assert.strictEqual(f({ note: "no id here" }), "no id here");
  assert.strictEqual(f({}), "Finding");
});

test("an unestablished value renders NOTHING, in any audience or shape", () => {
  /* SUPERSEDED PREMISE, kept as the record of what changed and why.

     This test used to assert a three-state vocabulary — "Not stated · queued
     for enrichment" internally, "Held · <reason>" for a quarantined field,
     "Not established in this assessment" for the client — and that a site
     missing its `audience` prop degraded to the client wording rather than
     leaking ours.

     Owner adjudication 2026-08-14 retired all three: "It should not state
     queued for enrichment or held. It should enrich and clarify real time and
     give the real data." The reader is not shown our workflow state in any
     form. The field is enriched and rendered, or nothing is.

     What replaces the old default-deny guarantee is stronger, because it no
     longer depends on a prop being threaded correctly to ~50 call sites: the
     component cannot leak internal wording under ANY props, since it emits no
     text at all. The absence is still tracked — by list_enrichment_gaps, by
     audit_promoted_client.py's 100%-null check, and by CG-18 — none of which
     render.

     Asserted on the rendered TREE rather than the source, because the whole
     point is what a reader ends up seeing. */
  for (const k of Object.keys(require.cache)) delete require.cache[k];
  const seen = [];
  const noop = () => undefined;
  global.window = {};
  global.React = {
    Fragment: "Fragment",
    createElement: (type, props, ...kids) => {
      kids.flat(Infinity).forEach((k) => {
        if (typeof k === "string") seen.push(k);
      });
      return { type, props, kids };
    },
    useState: (v) => [v, noop], useEffect: noop, useRef: () => ({ current: null }),
    useMemo: (f) => f(), useCallback: (f) => f,
    createContext: () => ({ Provider: null, Consumer: null }), useContext: noop,
    Component: class {}, PureComponent: class {},
  };
  require(path.join(JS, "utils.js"));
  const Gap = global.window.EnrichmentGap;
  assert.ok(typeof Gap === "function", "EnrichmentGap is not exported");

  const render = (props) => { seen.length = 0; const out = Gap(props); return { out, text: seen.join(" ") }; };

  /* Every shape the component is called in across the app, including the ones
     that used to produce each of the three retired sentences. All must be
     silent — a policy asserted over the input space, not over one call. */
  for (const props of [
    { what: "Website" },                                             // no audience
    { what: "Website", audience: "internal" },                       // was "queued"
    { what: "Website", audience: "customer" },                       // was "Not established"
    { what: "AUM", held: true, reason: "two domains resolve", audience: "internal" },
    { what: "AUM", held: true, reason: "two domains resolve", audience: "customer" },
    { what: "Peer", audience: "internal", compact: true },            // dense grids
    {},                                                              // no props at all
  ]) {
    const { out, text } = render(props);
    assert.strictEqual(out, null,
      `EnrichmentGap must render null; got a tree for ${JSON.stringify(props)}`);
    assert.strictEqual(text, "",
      `EnrichmentGap emitted text for ${JSON.stringify(props)}: ${text}`);
  }

  /* The retired vocabulary must not survive anywhere in the compiled bundle as
     REACHABLE output. The strings remain inside the component below its early
     return — deliberately, as the record — so this asserts on behaviour above,
     not on a grep that a comment would fail. */
});
