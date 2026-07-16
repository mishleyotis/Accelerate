/**
 * Audience helpers tests — internal-only tabs are hidden in customer view.
 */
import { describe, expect, it } from "vitest";
import { isTabVisible, INTERNAL_ONLY_TABS } from "../audience";

describe("isTabVisible", () => {
  it("shows every tab in internal mode", () => {
    expect(isTabVisible("context", "internal")).toBe(true);
    expect(isTabVisible("health", "internal")).toBe(true);
    expect(isTabVisible("overview", "internal")).toBe(true);
  });

  it("hides context + health in customer mode", () => {
    expect(isTabVisible("context", "customer")).toBe(false);
    expect(isTabVisible("health", "customer")).toBe(false);
  });

  it("shows non-internal tabs in customer mode", () => {
    expect(isTabVisible("overview", "customer")).toBe(true);
    expect(isTabVisible("insights", "customer")).toBe(true);
    expect(isTabVisible("heatmap", "customer")).toBe(true);
    expect(isTabVisible("platform", "customer")).toBe(true);
  });

  it("INTERNAL_ONLY_TABS is the locked set", () => {
    expect([...INTERNAL_ONLY_TABS].sort()).toEqual(["context", "health"]);
  });
});
