/* Entity search matches the identifier a reader actually holds — in every
 * control, by one rule.
 *
 * BAX-33, adjudicated 2026-08-15. The acceptance doc's DIR-02 and SRCH-10 both
 * require search to match "name and display ID" and both mark it P0. Measured
 * against HEAD, three controls searched three different field sets and none of
 * them searched the display id:
 *
 *   global search popover     name + domain
 *   directory filter          name + domain
 *   prospecting picker        name only
 *
 * The display id is in the URL of every client page, on every alert row and on
 * the printed scorecard, so it is the string a reader is most likely to paste
 * — and it was the one string that matched nothing. The doc was right and the
 * app was wrong, which is why this landed as a fix rather than as an EXCLUDE.
 *
 * Two assertions, because either alone is passable while the defect stands:
 * the rule must be CORRECT (behaviour, run against the compiled function), and
 * it must be the ONLY rule (no call site re-deriving it). Three controls
 * disagreeing about one question is the drift class this build has paid for
 * repeatedly; a shared helper that two of three call sites use is that class
 * again with better documentation.
 *
 * Reads the COMPILED bundle, as adapter.test.js and enrichment-render.test.js
 * do: what ships is what is asserted.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const JS = path.join(__dirname, "..", "public", "proto", "js");

/* Pull one top-level function out of a compiled module by brace balance.
   `entityMatches` touches no React and no globals, so it evaluates standalone
   — which is the point: the behaviour under test is the shipped source, not a
   copy of it re-typed into the test. */
function compiledFunction(file, name) {
  const src = fs.readFileSync(path.join(JS, file), "utf8");
  const start = src.indexOf(`function ${name}(`);
  assert.notStrictEqual(start, -1, `${name} is not in the compiled ${file}`);
  let depth = 0, i = src.indexOf("{", start);
  const open = i;
  for (; i < src.length; i++) {
    if (src[i] === "{") depth++;
    else if (src[i] === "}" && --depth === 0) break;
  }
  assert.ok(i < src.length, `${name} has unbalanced braces from ${open}`);
  // eslint-disable-next-line no-new-func
  return new Function(`${src.slice(start, i + 1)}; return ${name};`)();
}

function bundleFiles() {
  return fs.readdirSync(JS).filter((f) => f.endsWith(".js"));
}

const BAXTER = { name: "Baxter Credit Union", domain: "bcu.org",
                 id: "bcu-001", slug: "bcu-001" };
const OTHER = { name: "Odlum Brown", domain: "odlumbrown.com",
                id: "odb-002", slug: "odb-002" };

test("BAX-33 · the display id matches, in the compiled helper", () => {
  const m = compiledFunction("utils.js", "entityMatches");

  // The defect itself: the id a reader pastes out of the URL bar.
  assert.ok(m(BAXTER, "bcu-001"), "full display id must match");
  assert.ok(m(BAXTER, "BCU-001"), "display id match is case-insensitive");
  assert.ok(m(BAXTER, "001"), "a fragment of the display id must match");

  // What already worked, pinned so the fix cannot regress the old behaviour.
  assert.ok(m(BAXTER, "baxter"), "name still matches");
  assert.ok(m(BAXTER, "bcu.org"), "domain still matches");
  assert.ok(m(BAXTER, "  Baxter  "), "the query is trimmed");

  // And what must NOT match, or the control returns the whole directory and
  // reads as a search that found everything.
  assert.ok(!m(BAXTER, "odlum"), "another entity's name must not match");
  assert.ok(!m(OTHER, "bcu-001"), "another entity's display id must not match");

  // Empty query is "no filter applied", not "nothing matches" — the directory
  // renders its full list before a reader types.
  assert.ok(m(BAXTER, ""), "an empty query filters nothing");
  assert.ok(m(BAXTER, null), "a null query filters nothing");

  // An entity missing a field is a live shape: /v1/directory serves
  // `domain: null` for every entity whose domain has not been populated
  // (task #48). A matcher that throws on it takes the page down.
  assert.doesNotThrow(() => m({ name: "X", domain: null, id: null }, "x"));
  assert.ok(m({ name: "X", domain: null, id: null }, "x"));
  assert.ok(!m({}, "x"), "an entity with no fields matches no query");
});

test("BAX-33 · no control re-derives the match rule", () => {
  const offenders = [];
  for (const f of bundleFiles()) {
    const src = fs.readFileSync(path.join(JS, f), "utf8");
    // Any predicate that filters ENTITIES on a name/domain comparison is a
    // second copy of the rule by construction, whatever it currently returns.
    const re = /ENTITIES\s*\.\s*filter\s*\(([\s\S]{0,240}?)\)\s*[.;,)]/g;
    let hit;
    while ((hit = re.exec(src)) !== null) {
      const pred = hit[1];
      if (/\.(name|domain)\b/.test(pred) && !/entityMatches/.test(pred)) {
        offenders.push(`${f}: ${pred.trim().slice(0, 120)}`);
      }
    }
  }
  assert.deepStrictEqual(offenders, [],
    "these filter entities by name/domain without entityMatches — the rule " +
    "is held in two places and will drift:\n" + offenders.join("\n"));
});
