/* The browser resolver must survive Playwright renaming its own directories.
 *
 * This is the check that was missing when nine browser-driven suites started
 * running in CI for the first time. The resolver knew one layout —
 * `chrome-linux/chrome`, which is what this container's chromium-1194 ships —
 * and `npx playwright@1.62.1 install` writes `chrome-linux64/chrome`. Every
 * suite failed with `executablePath: expected string, got object`, which names
 * neither the cause nor the step that should have caught it.
 *
 * Layout is not a stable interface. A hardcoded path list will go stale again,
 * so the resolver falls back to scanning the build directory and these cases
 * pin both halves.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const { resolveChromium, browserSkip } = require("./proto-page-harness");

function fakeTree(layout) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "pwlayout-"));
  const exe = path.join(root, "chromium-9999", layout);
  fs.mkdirSync(path.dirname(exe), { recursive: true });
  fs.writeFileSync(exe, "#!/bin/sh\n");
  fs.chmodSync(exe, 0o755);
  return { root, exe };
}

function withRoot(root, fn) {
  const had = Object.prototype.hasOwnProperty.call(process.env, "PLAYWRIGHT_BROWSERS_PATH");
  const prev = process.env.PLAYWRIGHT_BROWSERS_PATH;
  process.env.PLAYWRIGHT_BROWSERS_PATH = root;
  try { return fn(); } finally {
    if (had) process.env.PLAYWRIGHT_BROWSERS_PATH = prev;
    else delete process.env.PLAYWRIGHT_BROWSERS_PATH;
  }
}

for (const layout of ["chrome-linux/chrome", "chrome-linux64/chrome",
                      "chrome-linux/headless_shell"]) {
  test(`resolves a browser laid out as ${layout}`, () => {
    const { root, exe } = fakeTree(layout);
    assert.strictEqual(withRoot(root, resolveChromium), exe);
    fs.rmSync(root, { recursive: true, force: true });
  });
}

test("resolves a layout nobody has shipped yet", () => {
  /* The point of the fallback scan: the next rename must cost a comment, not
     a red CI run on every browser suite at once. */
  const { root, exe } = fakeTree("chrome-linux-arm64-v9/chrome");
  assert.strictEqual(withRoot(root, resolveChromium), exe);
  fs.rmSync(root, { recursive: true, force: true });
});

test("an empty browser root resolves to null, not to a guess", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "pwempty-"));
  assert.strictEqual(withRoot(root, resolveChromium), null);
  fs.rmSync(root, { recursive: true, force: true });
});

test("PLAYWRIGHT_BROWSERS_PATH is authoritative, never one candidate of several", () => {
  /* Playwright treats it that way and so must this: an image that pins a
     browser directory means THAT directory, and searching past it launches a
     different build from the one the environment installed. */
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "pwempty-"));
  assert.strictEqual(withRoot(root, resolveChromium), null,
    "the resolver fell through to a browser outside the pinned root");
  fs.rmSync(root, { recursive: true, force: true });
});

test("under CI a missing browser fails rather than skipping", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "pwempty-"));
  const hadCI = Object.prototype.hasOwnProperty.call(process.env, "CI");
  const prevCI = process.env.CI;
  process.env.CI = "1";
  try {
    assert.throws(() => withRoot(root, browserSkip), /FAILURE, not a skip/,
      "a browser suite that cannot run would have reported green");
  } finally {
    if (hadCI) process.env.CI = prevCI; else delete process.env.CI;
    fs.rmSync(root, { recursive: true, force: true });
  }
});
