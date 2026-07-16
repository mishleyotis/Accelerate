/**
 * Standalone audience-param propagation regression.
 *
 * The 2026-05-28 audit (Probe 8) found that the "Customer view" toggle
 * in the chrome was UI-only: backend-loader.js never appended
 * ?view=customer to any fetch, so the server-side strip in
 * app/routers/{insights,heatmap,intelligence,platforms,...} never
 * fired. Peer fields would leak to a shared-screen customer view.
 *
 * Fix: backend-loader.js gained `_withAudience(path)` and threaded it
 * through fetchJSON / adminGet / adminPatch / adminPost. app-root.jsx
 * mirrors the audience state into `window.DMA.tweaks.audience` so the
 * loader can read it without importing React state.
 *
 * This file pins the source-shape contract so future refactors that
 * drop the propagation surface here BEFORE the e2e suite catches them.
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const SRC = resolve(process.cwd(), "standalone-src/src");

function load(name: string): string {
  return readFileSync(resolve(SRC, name), "utf-8");
}

describe("standalone audience propagation", () => {
  const loader = load("backend-loader.js");
  const appRoot = load("app-root.jsx");

  it("backend-loader exposes a _withAudience helper", () => {
    expect(loader).toContain("function _withAudience(");
  });

  it("fetchJSON calls _withAudience on every initial-load request", () => {
    // The boot fetches go through fetchJSON; they MUST be normalised
    // so the four parallel calls all carry ?view=customer when toggled.
    expect(loader).toMatch(/async function fetchJSON\([^)]*\)\s*{\s*path\s*=\s*_withAudience\(path\)/);
  });

  it("adminGet/adminPatch/adminPost all call _withAudience", () => {
    for (const fn of ["adminGet", "adminPatch", "adminPost"]) {
      const re = new RegExp(
        `async function ${fn}\\(path[\\s\\S]+?path\\s*=\\s*_withAudience\\(path\\)`,
      );
      expect(loader).toMatch(re);
    }
  });

  it("_withAudience skips paths that already declare ?view=", () => {
    // The helper must NOT double-stamp `view=` when the caller already
    // includes it -- otherwise a hand-crafted call (e.g. ?view=internal
    // for explicit preview) gets clobbered to customer mid-flight.
    expect(loader).toMatch(/if\s*\(\s*\/\[\?&\]view=\/\.test\(path\)\s*\)/);
  });

  it("_withAudience reads audience from window.DMA.tweaks", () => {
    // The handler must source the current value from window.DMA.tweaks
    // -- the SINGLE place app-root.jsx writes to. A separate copy in
    // sessionStorage or React-state would drift on cross-tab updates.
    expect(loader).toMatch(/window\.DMA\??\.\??tweaks\??\.\??audience/);
  });

  it("_withAudience leaves paths alone when audience is internal", () => {
    // The helper's contract is: only append on customer. internal
    // requests must hit the unchanged URL so the backend's default
    // (view=internal) handles them.
    expect(loader).toMatch(/if\s*\(\s*audience\s*!==\s*["']customer["']\s*\)\s*return\s+path/);
  });

  it("app-root.jsx mirrors audience to window.DMA.tweaks.audience", () => {
    // Without this mirror the loader can't see the toggle state.
    // The setter wrap + useEffect both write so the value is current
    // on first paint AND on every toggle.
    expect(appRoot).toMatch(/window\.DMA\.tweaks\.audience\s*=\s*next/);
    expect(appRoot).toMatch(/window\.DMA\.tweaks\.audience\s*=\s*audience/);
  });
});

describe("_withAudience runtime behaviour", () => {
  /**
   * Vitest can't eval the in-browser-Babel JSX, but `_withAudience` is
   * plain JS inside the IIFE. We extract + Function-eval it so we can
   * assert behaviour, not just source presence.
   */
  function loadHelper(): (path: string) => string {
    const loaderSrc = readFileSync(
      resolve(SRC, "backend-loader.js"), "utf-8",
    );
    const match = loaderSrc.match(
      /function _withAudience\(path\)\s*{[\s\S]+?return path \+ \(path\.includes\("\?"\) \? "&" : "\?"\) \+ "view=customer";\s*}/,
    );
    if (!match) throw new Error("_withAudience not found in backend-loader.js");
    // Create an isolated context with a mutable window stand-in.
    const ctx: { window: { DMA?: { tweaks?: { audience?: string } } } } = { window: {} };
    const factory = new Function(
      "window",
      `${match[0]}; return _withAudience;`,
    );
    return factory(ctx.window);
  }

  it("appends ?view=customer when audience is customer (no existing query)", () => {
    const w = { DMA: { tweaks: { audience: "customer" } } };
    const factorySrc = readFileSync(resolve(SRC, "backend-loader.js"), "utf-8")
      .match(/function _withAudience\(path\)[\s\S]+?\n  }/)![0];
    const helper = new Function("window", `${factorySrc}; return _withAudience;`)(w);
    expect(helper("/api/v1/entities")).toBe("/api/v1/entities?view=customer");
  });

  it("appends &view=customer when audience is customer (path has ?)", () => {
    const w = { DMA: { tweaks: { audience: "customer" } } };
    const factorySrc = readFileSync(resolve(SRC, "backend-loader.js"), "utf-8")
      .match(/function _withAudience\(path\)[\s\S]+?\n  }/)![0];
    const helper = new Function("window", `${factorySrc}; return _withAudience;`)(w);
    expect(helper("/api/v1/entities?owner=all")).toBe(
      "/api/v1/entities?owner=all&view=customer",
    );
  });

  it("leaves path alone when audience is internal", () => {
    const w = { DMA: { tweaks: { audience: "internal" } } };
    const factorySrc = readFileSync(resolve(SRC, "backend-loader.js"), "utf-8")
      .match(/function _withAudience\(path\)[\s\S]+?\n  }/)![0];
    const helper = new Function("window", `${factorySrc}; return _withAudience;`)(w);
    expect(helper("/api/v1/entities")).toBe("/api/v1/entities");
  });

  it("leaves path alone when audience is unset (defensive default)", () => {
    const w: object = { DMA: {} };
    const factorySrc = readFileSync(resolve(SRC, "backend-loader.js"), "utf-8")
      .match(/function _withAudience\(path\)[\s\S]+?\n  }/)![0];
    const helper = new Function("window", `${factorySrc}; return _withAudience;`)(w);
    expect(helper("/api/v1/dashboard")).toBe("/api/v1/dashboard");
  });

  it("never double-stamps view=", () => {
    const w = { DMA: { tweaks: { audience: "customer" } } };
    const factorySrc = readFileSync(resolve(SRC, "backend-loader.js"), "utf-8")
      .match(/function _withAudience\(path\)[\s\S]+?\n  }/)![0];
    const helper = new Function("window", `${factorySrc}; return _withAudience;`)(w);
    // Explicit view=internal must be preserved -- the caller knows best.
    expect(helper("/api/v1/entities?view=internal")).toBe(
      "/api/v1/entities?view=internal",
    );
  });
});
