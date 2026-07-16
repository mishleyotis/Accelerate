/**
 * SeenInRunsChip — the "Seen in N runs" chip rendered inside
 * EvidenceDrawer. State branches:
 *   - no data yet (loading)        → returns null
 *   - is_first_seen=true           → renders "First seen" muted chip
 *   - is_first_seen=false n=3      → renders "Seen in 3 runs"; click → popover
 *
 * We mock @tanstack/react-query's useQuery directly to drive the chip
 * through each state without needing a QueryClient.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockUseQuery = vi.fn();

vi.mock("@tanstack/react-query", () => ({
  useQuery: (opts: any) => mockUseQuery(opts),
}));

vi.mock("@/lib/api", () => ({
  apiGet: vi.fn(),
}));

// Import the component AFTER mocks register so its useQuery uses our shim.
import { EvidenceDrawer } from "../EvidenceDrawer";

function mkQuery(over: Record<string, unknown>) {
  return {
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...over,
  };
}

beforeEach(() => {
  mockUseQuery.mockReset();
});

afterEach(() => {
  mockUseQuery.mockReset();
});

describe("EvidenceDrawer SeenInRunsChip", () => {
  // The chip queries /api/v1/evidence/:id/run-history. We drive both the
  // /entities/.../evidence query AND the per-row chip query through the
  // same useQuery mock by dispatching on queryKey.

  it("renders 'Seen in 3 runs' chip + popover", () => {
    const evidenceResp = {
      entity_display_id: "alma",
      run_request_id: "REQ-1",
      filter_subcap_id: null,
      filter_min_tier: 8,
      items: [
        {
          id: "evid-1", e_id: "E-001",
          source_name: "FT.com", source_url: "https://ft.com/x",
          excerpt: "quote", claim_type: "FACT", tier: 3,
          published_date: "2025-01-01",
          linked_subcap_ids: ["P1C1.1.1"],
        },
      ],
    };
    const historyResp = {
      evidence_id: "evid-1", e_id: "E-001", n_runs: 3,
      is_first_seen: false,
      runs: [
        { run_id: "r1", request_id: "REQ-3", completed_at: "2026-05-01",
          status: "ACTIVE", first_seen_in_run: false,
          surfaces_in_run: ["P1C1.1.1"] },
        { run_id: "r2", request_id: "REQ-2", completed_at: "2026-02-01",
          status: "SUPERSEDED", first_seen_in_run: false,
          surfaces_in_run: ["P1C1.1.1"] },
        { run_id: "r3", request_id: "REQ-1", completed_at: "2025-11-01",
          status: "SUPERSEDED", first_seen_in_run: true,
          surfaces_in_run: ["P1C1.1.1"] },
      ],
    };
    mockUseQuery.mockImplementation((opts: any) => {
      const key = opts.queryKey?.[0];
      if (key === "evidence") return mkQuery({ data: evidenceResp });
      if (key === "evidence-run-history") return mkQuery({ data: historyResp });
      return mkQuery({});
    });
    render(<EvidenceDrawer open displayId="alma" onClose={() => {}} />);
    const chip = screen.getByText("Seen in 3 runs");
    expect(chip).toBeTruthy();
    expect(chip.getAttribute("data-history-n")).toBe("3");
    // Click → popover lists each run.
    fireEvent.click(chip);
    expect(screen.getByText("REQ-3")).toBeTruthy();
    expect(screen.getByText("REQ-2")).toBeTruthy();
    expect(screen.getByText("REQ-1")).toBeTruthy();
  });

  it("renders 'First seen' chip when n_runs <= 1", () => {
    const evidenceResp = {
      entity_display_id: "alma",
      run_request_id: "REQ-1",
      filter_subcap_id: null,
      filter_min_tier: 8,
      items: [
        {
          id: "evid-2", e_id: "E-002",
          source_name: "Reuters", source_url: null,
          excerpt: "q", claim_type: "FACT", tier: 4,
          published_date: null, linked_subcap_ids: [],
        },
      ],
    };
    const historyResp = {
      evidence_id: "evid-2", e_id: "E-002", n_runs: 1,
      is_first_seen: true,
      runs: [
        { run_id: "r1", request_id: "REQ-A", completed_at: null,
          status: "ACTIVE", first_seen_in_run: true,
          surfaces_in_run: [] },
      ],
    };
    mockUseQuery.mockImplementation((opts: any) => {
      const key = opts.queryKey?.[0];
      if (key === "evidence") return mkQuery({ data: evidenceResp });
      if (key === "evidence-run-history") return mkQuery({ data: historyResp });
      return mkQuery({});
    });
    render(<EvidenceDrawer open displayId="alma" onClose={() => {}} />);
    expect(screen.getByText("First seen")).toBeTruthy();
  });

  it("renders nothing when run-history data unavailable", () => {
    const evidenceResp = {
      entity_display_id: "alma",
      run_request_id: "REQ-1",
      filter_subcap_id: null, filter_min_tier: 8,
      items: [
        {
          id: "evid-3", e_id: "E-003",
          source_name: "src", source_url: null,
          excerpt: "q", claim_type: "FACT", tier: 4,
          published_date: null, linked_subcap_ids: [],
        },
      ],
    };
    mockUseQuery.mockImplementation((opts: any) => {
      const key = opts.queryKey?.[0];
      if (key === "evidence") return mkQuery({ data: evidenceResp });
      // No run-history payload → chip should bail.
      return mkQuery({ data: undefined });
    });
    render(<EvidenceDrawer open displayId="alma" onClose={() => {}} />);
    expect(screen.queryByText(/First seen|Seen in/i)).toBeNull();
  });
});
