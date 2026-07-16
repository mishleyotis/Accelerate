/**
 * Standalone build assertion — sanity-checks that the
 * `dist-standalone/index.html` artifact exists after
 * `pnpm run build:standalone`, contains the canonical brand mark, and
 * has no leftover `<script src=…>` references (the build inlines
 * everything per the stage 12 wireframe-guide contract).
 *
 * If you see this test fail, run `pnpm run build:standalone` first
 * — CI orchestrates the build + this test together.
 *
 * Render-state matrix:
 *   1. file missing                    → fail with the actionable hint
 *   2. file present but contains script
 *      tag pointing to /assets/        → fail (would mean inlining broke)
 *   3. file present + inlined          → pass
 */
import { describe, expect, it } from "vitest";
import { existsSync, readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";

const ARTIFACT = resolve(process.cwd(), "dist-standalone/index.html");

describe("standalone build artifact", () => {
  it("produces dist-standalone/index.html", () => {
    if (!existsSync(ARTIFACT)) {
      throw new Error(
        "dist-standalone/index.html not found. Run `pnpm run build:standalone` first.",
      );
    }
    expect(existsSync(ARTIFACT)).toBe(true);
  });

  it("inlines all assets — no remaining script src=/assets/", () => {
    if (!existsSync(ARTIFACT)) return; // covered by the previous test's failure
    const html = readFileSync(ARTIFACT, "utf-8");
    expect(html.includes('<script src="/assets/')).toBe(false);
    expect(html.includes('<link rel="stylesheet" href="/assets/')).toBe(false);
  });

  it("is between 50 kB and 5 MB (sanity range)", () => {
    if (!existsSync(ARTIFACT)) return;
    const size = statSync(ARTIFACT).size;
    expect(size).toBeGreaterThan(50 * 1024);
    expect(size).toBeLessThan(5 * 1024 * 1024);
  });

  it("mounts to #app and includes the brand mark reference", () => {
    if (!existsSync(ARTIFACT)) return;
    const html = readFileSync(ARTIFACT, "utf-8");
    expect(html.includes('id="app"')).toBe(true);
    expect(html.includes("/brand/icon_teal.png")).toBe(true);
  });
});
