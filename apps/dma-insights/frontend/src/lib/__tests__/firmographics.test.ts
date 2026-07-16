import { describe, expect, it } from "vitest";

import { scalarFirmographicEntries } from "../firmographics";

describe("scalarFirmographicEntries", () => {
  it("keeps scalar firmographics and drops narrative/non-scalar/empties", () => {
    const firm = {
      primary_regulator: "OCC",
      ticker: "ZION",
      sub_vertical: "Regional Banks",
      fdic_insured: true,
      branch_count: 400,
      narrative_md: "long prose paragraph ...",
      // non-scalar — must NOT be JSON.stringify'd into the KV grid
      leadership: [{ name: "Jane", title: "CEO" }],
      thought_leadership: [{ title: "x" }],
      // empties
      empty_str: "",
      missing: null,
    };
    const out = scalarFirmographicEntries(firm);
    const keys = out.map(([k]) => k);

    expect(keys).toContain("primary_regulator");
    expect(keys).toContain("ticker");
    expect(keys).toContain("sub_vertical");
    expect(keys).toContain("fdic_insured");
    expect(keys).toContain("branch_count");

    expect(keys).not.toContain("narrative_md");
    expect(keys).not.toContain("leadership");
    expect(keys).not.toContain("thought_leadership");
    expect(keys).not.toContain("empty_str");
    expect(keys).not.toContain("missing");
  });

  it("returns [] for null firmographics", () => {
    expect(scalarFirmographicEntries(null)).toEqual([]);
  });
});
