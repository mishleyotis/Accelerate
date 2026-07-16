/**
 * lib/maturity — tests for the canonical color/label/freshness/peer-delta
 * encoding. Locks the contract that every visible page reads from.
 */
import { describe, expect, it } from "vitest";
import {
  freshnessOf,
  freshnessOfBand,
  maturityClass,
  maturityHex,
  maturityLabel,
  maturityVisual,
  peerDeltaArrow,
} from "../maturity";

describe("maturityHex", () => {
  it("unset for null/undefined", () => {
    expect(maturityHex(null)).toBe("#E5E7EB");
    expect(maturityHex(undefined)).toBe("#E5E7EB");
  });

  it("Activating below 2.0 (boundary inclusive of < 2)", () => {
    expect(maturityHex(0)).toBe("#FFCB99");
    expect(maturityHex(1.99)).toBe("#FFCB99");
  });

  it("Building [2.0, 3.0)", () => {
    expect(maturityHex(2)).toBe("#62D7B8");
    expect(maturityHex(2.99)).toBe("#62D7B8");
  });

  it("Competing [3.0, 4.0)", () => {
    expect(maturityHex(3)).toBe("#27BBAF");
    expect(maturityHex(3.99)).toBe("#27BBAF");
  });

  it("Differentiating >= 4.0", () => {
    expect(maturityHex(4)).toBe("#139F94");
    expect(maturityHex(5)).toBe("#139F94");
  });
});

describe("maturityLabel", () => {
  it("matches the hex thresholds", () => {
    expect(maturityLabel(null)).toBe("Unset");
    expect(maturityLabel(1.5)).toBe("Activating");
    expect(maturityLabel(2.5)).toBe("Building");
    expect(maturityLabel(3.5)).toBe("Competing");
    expect(maturityLabel(4.5)).toBe("Differentiating");
  });
});

describe("maturityClass", () => {
  it("returns b-* tokens that match app.css", () => {
    expect(maturityClass(null)).toBe("muted");
    expect(maturityClass(1)).toBe("b-act");
    expect(maturityClass(2.5)).toBe("b-bld");
    expect(maturityClass(3.5)).toBe("b-cmp");
    expect(maturityClass(4.5)).toBe("b-dif");
  });
});

describe("maturityVisual", () => {
  it("bundles hex + label + cls", () => {
    const v = maturityVisual(3.5);
    expect(v).toEqual({
      hex: "#27BBAF",
      label: "Competing",
      cls: "b-cmp",
    });
  });
});

describe("peerDeltaArrow", () => {
  it("returns null when either side is missing", () => {
    expect(peerDeltaArrow(null, 3)).toBeNull();
    expect(peerDeltaArrow(3, null)).toBeNull();
  });

  it("delta >= 0 is ▲ in --z-mid (teal)", () => {
    const d = peerDeltaArrow(3.5, 3.0);
    expect(d).not.toBeNull();
    expect(d!.glyph).toBe("▲");
    expect(d!.color).toBe("var(--z-mid)");
    expect(d!.direction).toBe("above");
    expect(d!.magnitude).toBeCloseTo(0.5);
  });

  it("delta < 0 is ▼ in --z-below (orange)", () => {
    const d = peerDeltaArrow(2.5, 3.0);
    expect(d).not.toBeNull();
    expect(d!.glyph).toBe("▼");
    expect(d!.color).toBe("var(--z-below)");
    expect(d!.direction).toBe("below");
    expect(d!.magnitude).toBeCloseTo(0.5);
  });

  it("near-zero delta collapses to '·' (within 0.05)", () => {
    const d = peerDeltaArrow(3.02, 3.0);
    expect(d!.glyph).toBe("·");
    expect(d!.direction).toBe("equal");
  });
});

describe("freshnessOf — 4-band ladder matching SQL trigger", () => {
  // Per migration 018's compute_evidence_freshness_band:
  //   ≤ 12 months → current
  //   12 < ≤ 24   → aging
  //   24 < ≤ 36   → dated
  //   > 36        → stale
  // Earlier 3-band Python helper (6/12 thresholds) silently disagreed
  // with the SQL trigger — a stale row's chip rendered "current".
  // This test pins the contract so the chip ≡ the bundle %.
  const D = (months: number) => new Date(Date.now() - months * 30.4 * 24 * 3600 * 1000);

  it("returns null when missing", () => {
    expect(freshnessOf(null)).toBeNull();
  });

  it("returns null on unparseable string", () => {
    expect(freshnessOf("not-a-date")).toBeNull();
  });

  it("Current within 12 months", () => {
    const f = freshnessOf(D(1));
    expect(f!.tone).toBe("ok");
    expect(f!.label).toBe("Current");
    expect(f!.band).toBe("current");

    const f12 = freshnessOf(D(11.5));
    expect(f12!.band).toBe("current");
  });

  it("Aging 12-24 months", () => {
    const f = freshnessOf(D(18));
    expect(f!.tone).toBe("warn");
    expect(f!.label).toBe("Aging");
    expect(f!.band).toBe("aging");
  });

  it("Dated 24-36 months", () => {
    const f = freshnessOf(D(30));
    expect(f!.tone).toBe("below");
    expect(f!.label).toBe("Dated");
    expect(f!.band).toBe("dated");
  });

  it("Stale > 36 months — the 3-year mandate", () => {
    const f = freshnessOf(D(40));
    expect(f!.tone).toBe("below");
    expect(f!.label).toBe("Stale");
    expect(f!.band).toBe("stale");
  });
});

describe("freshnessOfBand — band straight from backend", () => {
  // When the API ships the band directly, the UI must NOT do its own
  // month arithmetic (might drift from the SQL trigger's CURRENT_DATE
  // vs the client clock). This pure mapping locks the contract.
  it.each([
    ["current", "ok",    "Current"],
    ["aging",   "warn",  "Aging"],
    ["dated",   "below", "Dated"],
    ["stale",   "below", "Stale"],
    ["undated", "muted", "Undated"],
  ])("band=%s → tone=%s label=%s", (band, tone, label) => {
    const f = freshnessOfBand(band as any);
    expect(f!.band).toBe(band);
    expect(f!.tone).toBe(tone);
    expect(f!.label).toBe(label);
  });

  it("returns null for unknown band", () => {
    expect(freshnessOfBand("garbage" as any)).toBeNull();
    expect(freshnessOfBand(null)).toBeNull();
    expect(freshnessOfBand(undefined)).toBeNull();
  });
});
