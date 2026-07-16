import { describe, expect, it } from "vitest";
import { focusSourceLabel, isJunkText, nameFromSlug, presentable, stripLabelPrefix } from "../sanitize";

describe("sanitize", () => {
  it("rejects pipeline metadata served as content", () => {
    expect(isJunkText(
      "SECTION 1 COMPLETE — Assessment ID DMA-RES-CPB-20260527-0001 | Evidence Mode: PUBLIC",
    )).toBe(true);
    expect(presentable("Evidence Mode: HYBRID | Subcaps 700")).toBeNull();
  });

  it("rejects digit/punctuation blobs and placeholders", () => {
    expect(isJunkText("2026-04-29 0001 | 5.0")).toBe(true);
    expect(isJunkText("(unknown)")).toBe(true);
    expect(isJunkText("—")).toBe(true);
    expect(presentable("  ")).toBeNull();
  });

  it("keeps real prose, including prose with numbers", () => {
    expect(presentable("92% same-day funding, 85% auto-renewal [E-018:F1]."))
      .toContain("same-day funding");
    expect(isJunkText("2024 MOVEit breach (E-030) exposed 111K members."))
      .toBe(false);
  });

  it("strips short label/id prefixes but not mid-sentence pipes", () => {
    expect(stripLabelPrefix("F-002 | Hybrid digital-branch model"))
      .toBe("Hybrid digital-branch model");
    expect(stripLabelPrefix("Maturity implication | M3+ commercial maturity"))
      .toBe("M3+ commercial maturity");
    const sentence = "Funding is 92% same-day | renewals auto-process at 85% across channels";
    expect(stripLabelPrefix(sentence)).not.toBe(sentence.split("|")[1].trim());
  });

  it("humanizes slug fallbacks without numeric suffixes", () => {
    expect(nameFromSlug("alma-bank-0002")).toBe("Alma Bank");
    expect(nameFromSlug("corporate-america-credit-0001")).toBe("Corporate America Credit");
    expect(nameFromSlug("yncu-f33b")).toBe("Yncu");
    expect(nameFromSlug(null)).toBe("Client");
  });

  it("humanizes focus-area SOURCE footers, never machine tokens", () => {
    // "(unknown)" is the dominant live value (236 rows) — fall back to kind.
    expect(focusSourceLabel("(unknown)", "docx")).toBe("Client research report");
    expect(focusSourceLabel(null, "heuristic")).toBe("Derived from scored capability gaps");
    expect(focusSourceLabel("synthesized:heuristic", null))
      .toBe("Derived from scored capability gaps");
    expect(focusSourceLabel("synthesized:gemini-flash", null))
      .toBe("AI-clustered from capability gaps");
    expect(focusSourceLabel("docx:strategic_section", "docx"))
      .toBe("Client research report · strategic section");
    // A real document path renders its basename.
    expect(focusSourceLabel("04_reports/Client_Profile.docx", null))
      .toBe("Client_Profile.docx");
    // Leaked excerpt text is NOT a source — omit (null) unless kind maps.
    expect(focusSourceLabel("ITSM platform end-of-life in 8 months [E-137]", null))
      .toBeNull();
    expect(focusSourceLabel("(unknown)", null)).toBeNull();
  });
});
