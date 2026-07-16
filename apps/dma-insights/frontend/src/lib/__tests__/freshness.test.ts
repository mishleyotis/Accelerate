/**
 * lib/freshness — mirrors the SQL/Python band logic. Locked to the
 * 2026-05-23 reference date per the user's 3-year mandate.
 */
import { describe, expect, it } from "vitest";
import { computeBand, getBadgeStyle } from "../freshness";

const TODAY = new Date("2026-05-23T00:00:00Z");

describe("computeBand", () => {
  it("returns 'current' for last 12 months", () => {
    expect(computeBand("2025-11-01", null, TODAY)).toBe("current");
  });
  it("returns 'aging' for 12-24 months", () => {
    expect(computeBand("2024-06-01", null, TODAY)).toBe("aging");
  });
  it("returns 'dated' for 24-36 months", () => {
    expect(computeBand("2023-11-01", null, TODAY)).toBe("dated");
  });
  it("returns 'stale' for >3 years", () => {
    expect(computeBand("2022-01-01", null, TODAY)).toBe("stale");
  });
  it("returns 'undated' when both null", () => {
    expect(computeBand(null, null, TODAY)).toBe("undated");
  });
  it("falls back to recency_months when no date", () => {
    expect(computeBand(null, 8, TODAY)).toBe("current");
    expect(computeBand(null, 37, TODAY)).toBe("stale");
  });
});

describe("getBadgeStyle", () => {
  it("returns the > 3y warning string for stale", () => {
    const s = getBadgeStyle("stale");
    expect(s.label).toContain(">3y");
    expect(s.className).toContain("freshness-stale");
  });
  it("returns current label for current", () => {
    expect(getBadgeStyle("current").label).toBe("current");
  });
});
