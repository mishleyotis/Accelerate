/**
 * effectiveRole — downgrade-only matrix (CLAUDE.md "Admin flow").
 *
 * The server-returned `user.role` is the FLOOR. An AE who tampers with
 * `can_act_as` to include "ADMIN" must still get clamped to AE.
 */
import { describe, expect, it } from "vitest";
import { effectiveRole } from "@/store/auth";

describe("effectiveRole", () => {
  it("AE cannot escalate (every actingAs is clamped to AE)", () => {
    for (const acting of ["ADMIN", "ANALYST", "AE"] as const) {
      expect(effectiveRole("AE", acting)).toBe("AE");
    }
  });

  it("ANALYST can downgrade to AE but not escalate to ADMIN", () => {
    expect(effectiveRole("ANALYST", "AE")).toBe("AE");
    expect(effectiveRole("ANALYST", "ANALYST")).toBe("ANALYST");
    expect(effectiveRole("ANALYST", "ADMIN")).toBe("ANALYST"); // escalation refused
  });

  it("ADMIN can downgrade to anything", () => {
    expect(effectiveRole("ADMIN", "AE")).toBe("AE");
    expect(effectiveRole("ADMIN", "ANALYST")).toBe("ANALYST");
    expect(effectiveRole("ADMIN", "ADMIN")).toBe("ADMIN");
  });

  it("null actingAs returns the real role", () => {
    expect(effectiveRole("AE", null)).toBe("AE");
    expect(effectiveRole("ADMIN", null)).toBe("ADMIN");
  });

  it("undefined real falls back to AE", () => {
    expect(effectiveRole(undefined, null)).toBe("AE");
  });

  it("CUSTOMER stays CUSTOMER regardless of actingAs", () => {
    expect(effectiveRole("CUSTOMER", "ADMIN")).toBe("CUSTOMER");
    expect(effectiveRole("CUSTOMER", null)).toBe("CUSTOMER");
  });
});
