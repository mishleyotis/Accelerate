/* Gate F is a ratchet that cannot go slack.
 *
 * RC-03, gold audit of run 7968492e (2026-10-04). The baseline of declared
 * keys with no frontend reader listed `overview.sentiment.themes[].cap_statement`,
 * `themes[].mapped_subcap_ids` and `gap_analysis` as accepted debt, and the
 * gate passed a baseline STALER than the code: five keys that had readers were
 * still listed, so any of them could lose its reader again and nothing would
 * fail. The sentiment card now reads all three. The baseline is shrunk to
 * match, and a stale baseline is a failure, so a key that loses its reader
 * fails as NEW.
 *
 * Drives the real gate script against a scratch copy of the repo's
 * contract, baseline and renderer, changing one thing per case.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const REPO = path.join(__dirname, "..", "..", "..");
const GATE = path.join(REPO, "scripts", "gate_f_declared_keys_have_readers.py");

function scratch({ baseline, proto } = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "gate-f-"));
  fs.mkdirSync(path.join(root, "scripts"));
  fs.copyFileSync(GATE, path.join(root, "scripts", "gate_f.py"));
  const shared = path.join(root, "packages", "shared");
  fs.mkdirSync(shared, { recursive: true });
  fs.copyFileSync(path.join(REPO, "packages", "shared", "contracts_data.json"),
                  path.join(shared, "contracts_data.json"));
  const base = JSON.parse(fs.readFileSync(
    path.join(REPO, "packages", "shared", "unread_keys_baseline.json"), "utf8"));
  fs.writeFileSync(path.join(shared, "unread_keys_baseline.json"),
                   JSON.stringify(baseline ? baseline(base) : base));
  const dst = path.join(root, "apps", "web", "proto");
  fs.mkdirSync(dst, { recursive: true });
  const src = path.join(REPO, "apps", "web", "proto");
  for (const f of fs.readdirSync(src)) {
    if (!/\.jsx?$/.test(f)) continue;
    const text = fs.readFileSync(path.join(src, f), "utf8");
    fs.writeFileSync(path.join(dst, f), proto ? proto(text) : text);
  }
  const r = spawnSync("python3", [path.join(root, "scripts", "gate_f.py")], { encoding: "utf8" });
  fs.rmSync(root, { recursive: true, force: true });
  return { code: r.status, out: `${r.stdout}\n${r.stderr}` };
}

test("Gate F passes on the tree as committed", () => {
  const r = scratch();
  assert.strictEqual(r.code, 0, r.out);
});

test("Gate F no longer carries the sentiment keys as debt", () => {
  const base = JSON.parse(fs.readFileSync(
    path.join(REPO, "packages", "shared", "unread_keys_baseline.json"), "utf8"));
  for (const k of ["cap_statement", "mapped_subcap_ids", "gap_analysis"]) {
    assert.ok(!(k in base.keys), `${k} is still accepted as unread debt`);
  }
});

test("Gate F fails when a key it accepts as read loses its reader", () => {
  // The renderer with every reader of `cap_statement` removed — the state
  // the sentiment card was in before this fix.
  const r = scratch({ proto: (t) => t.replace(/\bcap_statement\b/g, "capStmt") });
  assert.strictEqual(r.code, 1, `the gate passed a key that lost its reader:\n${r.out}`);
  assert.match(r.out, /cap_statement/);
});

test("Gate F fails on a stale baseline", () => {
  const r = scratch({ baseline: (b) => ({ ...b, keys: { ...b.keys,
    cap_statement: ["overview.sentiment.themes[].cap_statement"] } }) });
  assert.strictEqual(r.code, 1,
    `a baseline listing a key that has a reader passed:\n${r.out}`);
  assert.match(r.out, /now have a reader|now\s+have a reader|have a reader/);
});
