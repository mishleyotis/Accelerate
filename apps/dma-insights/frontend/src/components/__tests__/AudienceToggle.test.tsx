/**
 * AudienceToggle — the prototype's Internal | Customer segmented
 * control (2026-06-10 chrome parity rewrite). Toggles the UI store.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, beforeEach } from "vitest";
import { AudienceToggle } from "../AudienceToggle";
import { useUiStore } from "@/store/ui";

beforeEach(() => {
  useUiStore.getState().setAudience("internal");
});

describe("AudienceToggle", () => {
  it("renders both segments with Internal active in internal mode", () => {
    render(<AudienceToggle />);
    const internal = screen.getByRole("button", { name: /Internal/i });
    const customer = screen.getByRole("button", { name: /Customer/i });
    expect(internal.className).toContain("on");
    expect(customer.className).not.toContain("on");
  });

  it("switches the store + active segment when Customer clicked", () => {
    render(<AudienceToggle />);
    fireEvent.click(screen.getByRole("button", { name: /Customer/i }));
    expect(useUiStore.getState().audience).toBe("customer");
    expect(
      screen.getByRole("button", { name: /Customer/i }).className,
    ).toContain("on");
  });

  it("returns to internal when Internal clicked from customer mode", () => {
    useUiStore.getState().setAudience("customer");
    render(<AudienceToggle />);
    fireEvent.click(screen.getByRole("button", { name: /Internal/i }));
    expect(useUiStore.getState().audience).toBe("internal");
  });

  it("marks the wrapper with the customer class in customer mode", () => {
    useUiStore.getState().setAudience("customer");
    const { container } = render(<AudienceToggle />);
    expect(
      container.querySelector(".audience-toggle.customer"),
    ).not.toBeNull();
  });
});
