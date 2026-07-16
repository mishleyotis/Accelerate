/**
 * Vitest setup — stubs jsdom-missing browser APIs so the test suite
 * runs noise-free. Loaded before any test module.
 *
 * State branches mirrored here:
 *   - canvas absent           → stub HTMLCanvasElement.getContext to
 *                               return a no-op 2D context shim
 *   - matchMedia absent       → stub to return a never-matching mock
 *   - ResizeObserver absent   → stub with no-op start/stop
 *
 * jsdom intentionally omits these because they require native rendering
 * pipelines. Without the stubs every component that touches a canvas
 * (Sparkline / HeatmapPage / charts-* lazy chunks) emits one
 * "Error: Not implemented" line per render — drowning real test
 * failures in noise.
 */

if (typeof HTMLCanvasElement !== "undefined") {
  // Minimal 2D context shim — every method is a no-op so caller code
  // that does `ctx.fillRect()` / `ctx.beginPath()` etc. doesn't crash.
  // Tests that ASSERT on canvas content should mock individually.
  const noop = () => {};
  const stubCtx = {
    fillRect: noop, clearRect: noop, getImageData: () => ({
      data: new Uint8ClampedArray(4),
    }),
    putImageData: noop, createImageData: () => ({ data: new Uint8ClampedArray(4) }),
    setTransform: noop, drawImage: noop, save: noop, restore: noop,
    fillText: noop, strokeText: noop, measureText: () => ({ width: 0 }),
    translate: noop, transform: noop, rotate: noop, scale: noop,
    beginPath: noop, moveTo: noop, lineTo: noop, closePath: noop,
    stroke: noop, fill: noop, arc: noop, arcTo: noop,
    bezierCurveTo: noop, quadraticCurveTo: noop, rect: noop,
    clip: noop, setLineDash: noop, getLineDash: () => [],
    isPointInPath: () => false, isPointInStroke: () => false,
    createLinearGradient: () => ({ addColorStop: noop }),
    createRadialGradient: () => ({ addColorStop: noop }),
    createPattern: () => null,
    canvas: { width: 0, height: 0 },
  };
  // Cast to unknown to satisfy TS while accepting the partial shim.
  HTMLCanvasElement.prototype.getContext = function () {
    return stubCtx as unknown as CanvasRenderingContext2D;
  } as HTMLCanvasElement["getContext"];
  HTMLCanvasElement.prototype.toDataURL = function () {
    return "data:image/png;base64,";
  };
}

if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = (query: string) => ({
    matches: false, media: query, onchange: null,
    addListener: () => {}, removeListener: () => {},
    addEventListener: () => {}, removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}

if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

// getComputedStyle with pseudo-element arg is unsupported in jsdom —
// React often passes it through when measuring sizing during render.
// Wrap to drop the second arg so jsdom's base path returns empty.
if (typeof window !== "undefined" && window.getComputedStyle) {
  const original = window.getComputedStyle.bind(window);
  window.getComputedStyle = ((elt: Element, _pseudoElt?: string | null) =>
    original(elt)) as typeof window.getComputedStyle;
}

if (typeof globalThis.IntersectionObserver === "undefined") {
  globalThis.IntersectionObserver = class {
    constructor() {}
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() { return []; }
    root = null;
    rootMargin = "";
    thresholds = [];
  } as unknown as typeof IntersectionObserver;
}
