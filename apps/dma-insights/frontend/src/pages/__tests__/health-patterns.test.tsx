/**
 * D6 PatternsTab — pattern cards + honest empty states.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { PatternsTab } from "@/pages/HealthPage";
import * as queries from "@/lib/queries";
import type {
  CrossEntityPatternOut,
  HealthPatternsResponse,
} from "@/lib/queries";

function loaded(data: HealthPatternsResponse | undefined) {
  return { data, isLoading: false, isError: false, error: null } as
    ReturnType<typeof queries.useHealthPatterns>;
}

function resp(over: Partial<HealthPatternsResponse> = {}): HealthPatternsResponse {
  return {
    entity_display_id: "alma-bank-0001", run_request_id: "REQ-1",
    subvertical: "BANK", catalogue_version: "v7.0", patterns: [],
    state: "no_cohort", ...over,
  };
}

function pattern(over: Partial<CrossEntityPatternOut> = {}): CrossEntityPatternOut {
  return {
    pattern_type: "subcap_gap", pattern_key: "P2C1",
    pattern_label: "Journey Mapping gap", primary_subcap_id: "P2C1",
    entity_count: 4, severity_mix: {}, median_peer_gap: -0.6,
    sample_subcap_ids: ["P2C1"], ...over,
  };
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("PatternsTab (D6)", () => {
  it("renders gap pattern cards with entity-count + median gap + subcap chip", () => {
    vi.spyOn(queries, "useHealthPatterns").mockReturnValue(
      loaded(resp({ state: "full", patterns: [pattern()] })));
    render(<PatternsTab displayId="alma-bank-0001" />);
    expect(screen.getByText("Journey Mapping gap")).toBeTruthy();
    expect(screen.getByText("4 entities")).toBeTruthy();
    expect(screen.getByText(/Median peer gap -0\.60/)).toBeTruthy();
    expect(screen.getByText("P2C1")).toBeTruthy(); // sample subcap chip
  });

  it("issue_theme renders severity chips", () => {
    vi.spyOn(queries, "useHealthPatterns").mockReturnValue(
      loaded(resp({
        state: "full",
        patterns: [pattern({
          pattern_type: "issue_theme", pattern_label: "Integration issues",
          median_peer_gap: null, severity_mix: { critical: 2, high: 1 },
        })],
      })));
    render(<PatternsTab displayId="alma-bank-0001" />);
    expect(screen.getByText("critical: 2")).toBeTruthy();
    expect(screen.getByText("high: 1")).toBeTruthy();
  });

  it("insufficient_data shows the cohort-size empty state", () => {
    vi.spyOn(queries, "useHealthPatterns").mockReturnValue(
      loaded(resp({ state: "insufficient_data", patterns: [] })));
    render(<PatternsTab displayId="alma-bank-0001" />);
    expect(screen.getByText(/at least 3 assessed entities/i)).toBeTruthy();
  });

  it("no patterns shows the contextual empty state", () => {
    vi.spyOn(queries, "useHealthPatterns").mockReturnValue(
      loaded(resp({ state: "no_cohort", patterns: [] })));
    render(<PatternsTab displayId="alma-bank-0001" />);
    expect(screen.getByText(/No recurring cross-entity patterns/i)).toBeTruthy();
  });
});
