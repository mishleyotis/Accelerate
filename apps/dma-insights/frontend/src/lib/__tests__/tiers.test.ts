/**
 * Tier helpers — the wireframe EVIDENCE_TIERS table (01_data.js) verbatim:
 * labels + accent/bg tokens for T1..T8, with honest fallbacks for tiers
 * outside the table.
 */
import { describe, expect, it } from "vitest";
import { EVIDENCE_TIERS, TIER_LABELS, tierBg, tierColor, tierLabel } from "../tiers";

describe("tierLabel", () => {
  it("returns the wireframe labels for tiers 1-8", () => {
    expect(tierLabel(1)).toBe("Primary disclosure");
    expect(tierLabel(2)).toBe("Earnings & investor");
    expect(tierLabel(3)).toBe("Trade press · analyst");
    expect(tierLabel(4)).toBe("Marketing claim");
    expect(tierLabel(5)).toBe("Analyst inference");
    expect(tierLabel(6)).toBe("Sentiment / review");
    expect(tierLabel(7)).toBe("Job posting · proxy");
    expect(tierLabel(8)).toBe("Social / hypothesis");
    for (const t of [1, 2, 3, 4, 5, 6, 7, 8]) {
      expect(tierLabel(t)).toBe(TIER_LABELS[t]);
    }
  });

  it("falls back to Tier {n} for unknown tiers", () => {
    expect(tierLabel(99)).toBe("Tier 99");
  });
});

describe("tierColor / tierBg", () => {
  it("every tier maps to its wireframe accent + callout background", () => {
    for (const t of [1, 2, 3, 4, 5, 6, 7, 8]) {
      expect(tierColor(t)).toBe(EVIDENCE_TIERS[t].color);
      expect(tierBg(t)).toBe(EVIDENCE_TIERS[t].bg);
    }
    // Spot-check the strongest/weakest ends of the scale.
    expect(tierColor(1)).toBe("var(--z-mid)");
    expect(tierBg(1)).toBe("var(--z-ice)");
    expect(tierColor(8)).toBe("var(--z-muted)");
  });

  it("unknown tiers fall back to muted/bg tokens", () => {
    expect(tierColor(99)).toBe("var(--z-muted)");
    expect(tierBg(99)).toBe("var(--z-bg)");
  });
});
