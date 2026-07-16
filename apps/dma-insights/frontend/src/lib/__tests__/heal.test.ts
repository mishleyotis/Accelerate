import { describe, expect, it } from "vitest";

import {
  healHq,
  healName,
  healScore,
  healSubvertical,
  healText,
} from "../heal";

describe("heal render layer", () => {
  it("healName rejects drive-ids and folder artifacts", () => {
    expect(healName("Amarillo National Bank")).toBe("Amarillo National Bank");
    expect(healName("1a2b3c4d5e6f7a8b9c0d")).toBe("Unnamed client"); // bare drive id
    expect(healName("03_scoring_workbook")).toBe("Unnamed client");
    expect(healName("  ")).toBe("Unnamed client");
    expect(healName(null)).toBe("Unnamed client");
  });

  it("healName rejects the live junk seen on the dashboard (mixed-case Drive id + DMA package artifacts)", () => {
    // The raw Drive folder id that rendered as an entity name (mixed case).
    expect(healName("1NYe2zU3wmBEvd8ZRFWEHpAGIUuK1O1L2")).toBe("Unnamed client");
    // Vornado's folder-artifact name.
    expect(healName("VNO DMA Engagement FINAL")).toBe("Unnamed client");
    // A bare "{Client} - DMA" Drive folder name.
    expect(healName("Acme Capital - DMA")).toBe("Unnamed client");
    // A package zip stem.
    expect(healName("Foo_DMA_Complete_Package")).toBe("Unnamed client");
    // …but real names with legitimate words/punctuation survive untouched.
    expect(healName("Interactive Brokers Group, Inc.")).toBe("Interactive Brokers Group, Inc.");
    expect(healName("SL Green Realty Corp (NYSE:SLG)")).toBe("SL Green Realty Corp (NYSE:SLG)");
    expect(healName("Farm Credit Mid-America, ACA")).toBe("Farm Credit Mid-America, ACA");
  });

  it("healSubvertical maps codes to human labels, never raw codes", () => {
    expect(healSubvertical("RB")).toBe("Regional Bank");
    expect(healSubvertical("CU")).toBe("Credit Union");
    expect(healSubvertical("AM")).toBe("Asset Manager");
    expect(healSubvertical(null)).toBe("—");
  });

  it("healHq drops JSON-dict blobs that leaked from parsed_facts", () => {
    expect(healHq("San Antonio, TX")).toBe("San Antonio, TX");
    expect(healHq('{"city":"x"}')).toBeNull();
    expect(healHq("[1,2]")).toBeNull();
    expect(healHq(null)).toBeNull();
    expect(healHq(42)).toBeNull();
  });

  it("healScore clamps to [1,5] and is null-safe", () => {
    expect(healScore(3.2)).toBe(3.2);
    expect(healScore(7)).toBe(5);
    expect(healScore(0)).toBe(1);
    expect(healScore(null)).toBeNull();
    expect(healScore(Number.NaN)).toBeNull();
  });

  it("healText truncates with an ellipsis", () => {
    expect(healText("short")).toBe("short");
    expect(healText("a".repeat(50), 10)).toHaveLength(10);
    expect(healText("a".repeat(50), 10).endsWith("…")).toBe(true);
  });
});
