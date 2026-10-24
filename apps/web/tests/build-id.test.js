/* lib/build-id: the bundle fingerprint the UpdateWatcher compares. Same
 * files → same id on every instance; any change to a module or the
 * stylesheet → a new id. */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs"), os = require("node:os"), path = require("node:path");

function tree(files) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "build-id-"));
  fs.mkdirSync(path.join(root, "js"));
  for (const [n, c] of Object.entries(files)) fs.writeFileSync(path.join(root, n), c);
  return root;
}
const fresh = () => { delete require.cache[require.resolve("../lib/build-id.js")]; return require("../lib/build-id.js"); };

test("the fingerprint is stable for the same bundle and moves when any file changes", () => {
  const a = tree({ "js/a.js": "1", "js/b.js": "2", "app.css": "x" });
  const b = tree({ "js/b.js": "2", "js/a.js": "1", "app.css": "x" });
  const c = tree({ "js/a.js": "1", "js/b.js": "3", "app.css": "x" });
  const d = tree({ "js/a.js": "1", "js/b.js": "2", "app.css": "y" });
  const id = (r) => fresh().buildId(r);
  assert.match(id(a), /^[0-9a-f]{16}$/);
  assert.strictEqual(id(a), id(b), "file order changed the fingerprint");
  assert.notStrictEqual(id(a), id(c), "a changed module kept the fingerprint");
  assert.notStrictEqual(id(a), id(d), "a changed stylesheet kept the fingerprint");
});

test("the real bundle has a fingerprint", () => {
  assert.match(fresh().buildId(path.join(__dirname, "..", "public", "proto")), /^[0-9a-f]{16}$/);
});
