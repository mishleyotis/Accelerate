/**
 * Mobile nav drawer state (ui store) — drives the ≤760px sidebar drawer.
 * Ephemeral (never persisted); toggled by the TopBar hamburger and closed
 * by the backdrop / on navigation.
 */
import { beforeEach, describe, expect, it } from "vitest";
import { useUiStore } from "@/store/ui";

describe("ui store — mobileNavOpen", () => {
  beforeEach(() => {
    useUiStore.getState().setMobileNavOpen(false);
  });

  it("defaults to closed", () => {
    expect(useUiStore.getState().mobileNavOpen).toBe(false);
  });

  it("toggleMobileNav flips the flag", () => {
    const { toggleMobileNav } = useUiStore.getState();
    toggleMobileNav();
    expect(useUiStore.getState().mobileNavOpen).toBe(true);
    toggleMobileNav();
    expect(useUiStore.getState().mobileNavOpen).toBe(false);
  });

  it("setMobileNavOpen sets explicitly", () => {
    useUiStore.getState().setMobileNavOpen(true);
    expect(useUiStore.getState().mobileNavOpen).toBe(true);
    useUiStore.getState().setMobileNavOpen(false);
    expect(useUiStore.getState().mobileNavOpen).toBe(false);
  });

  it("is not written to localStorage (ephemeral)", () => {
    useUiStore.getState().setMobileNavOpen(true);
    // The only persisted UI keys are audience + sidebar_collapsed.
    const keys = Object.keys(localStorage);
    expect(keys.some((k) => k.includes("mobile") || k.includes("nav"))).toBe(false);
  });
});
