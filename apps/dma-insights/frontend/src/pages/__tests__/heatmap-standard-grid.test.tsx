/**
 * Standard-mode heatmap grid — wireframe contract
 * (docs/wireframe-2026-06/src/07_pages_c.js · CategoryHeatmap +
 * SubcapHeatmap, ported into HeatmapPage's StandardView).
 *
 * Pins the 2026-06 rebuild that replaced the 4 aggregate pillar
 * summary cards (QA: 58.9% pixel divergence, zero `.hm-cell`) with the
 * wireframe's dense cell grid + zoom ladder:
 *
 *   1. Default rung (?hm=standard, no ?zoom) renders pillar BANDS
 *      (chip + display name + mean badge) of per-category aggregate
 *      `.hm-cell` cells, with the aligned Peer row + column labels.
 *   2. Clicking an AGGREGATE cell drills down (?zoom=category:{id}) —
 *      it must NOT open the SynthesisDrawer (2026-06-10 IA decision:
 *      only subcap-grain cells open synthesis).
 *   3. The drilled rung renders that category's subcap-grain cells
 *      with `.thin` / `.capped` class tokens; clicking a leaf opens
 *      synthesis (?synthesis={id}); Reset zooms back out.
 *   4. ?zoom=subcap renders the full leaf grid grouped by category.
 *   5. Customer audience: the Standard toggle is hidden and a shared
 *      ?hm=standard link coerces to the Focus view (wireframe
 *      07_pages_c.js:19-21 lock).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { HeatmapPage } from "@/pages/HeatmapPage";
import * as queries from "@/lib/queries";
import * as hashRouter from "@/lib/hash-router";
import { useUiStore } from "@/store/ui";
import type { HeatmapCell, HeatmapResponse } from "@/lib/queries";

function withClient(ui: ReactNode): JSX.Element {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

function cell(
  id: string, label: string, score: number, extra: Partial<HeatmapCell> = {},
): HeatmapCell {
  return {
    id, label,
    parent_id: id.includes(".") ? id.split(".").slice(0, 2).join(".") : null,
    score, band: null, peer_median: 2.5, peer_gap: score - 2.5,
    is_thin_evidence: false, cap_applied: false, cap_reason: null,
    issue_count: 0, aliased_from: null,
    ...extra,
  };
}

/** Subcap-grain fixture: 4 categories across 3 pillars, 9 leaf cells. */
const SUBCAP_CELLS: HeatmapCell[] = [
  cell("P1C1.1.1", "Strategy Foundation", 2.5),
  cell("P1C1.1.2", "Vision Cascade", 1.5, { is_thin_evidence: true }),
  cell("P1C1.2.1", "Governance Charter", 1.0, {
    cap_applied: true, cap_reason: "ISS-001 caps at M1",
  }),
  cell("P1C2.1.1", "Budget Alignment", 3.2),
  cell("P1C2.1.2", "Funding Model", 3.4),
  cell("P2C1.1.1", "Journey Mapping", 2.1),
  cell("P2C1.1.2", "Persona Library", 2.3),
  cell("P4C3.1.1", "Lakehouse Foundation", 4.2),
  cell("P4C3.2.1", "Model Registry", 4.4),
];

/** Category-grain fixture — feeds the column-label name map. */
const CATEGORY_CELLS: HeatmapCell[] = [
  cell("P1C1", "Vision & Operating Model", 1.67),
  cell("P1C2", "Investment & Funding", 3.3),
  cell("P2C1", "Customer Journeys", 2.2),
  cell("P4C3", "Data & AI Platform", 4.3),
];

function heatmapResponse(cells: HeatmapCell[], zoom: string): HeatmapResponse {
  return {
    entity_display_id: "alma-bank-0001",
    run_request_id: "DMA-ASM-ALMA-20260519-0001",
    run_status: "ACTIVE",
    zoom: zoom as HeatmapResponse["zoom"],
    view_mode: "standard",
    subvertical: "BANK",
    peer_overlay: true,
    issue_overlay: false,
    cells,
    value_chain_buckets: [],
    catalogue_version: "v5.5",
    warnings: [],
    narrative: null,
  };
}

function loaded<T>(data: T) {
  return { data, isLoading: false, isError: false, error: null };
}

function mockHeatmapQueries(): void {
  vi.spyOn(queries, "useEntityOverview").mockReturnValue(
    loaded(undefined) as ReturnType<typeof queries.useEntityOverview>,
  );
  vi.spyOn(queries, "useEntityHeatmap").mockImplementation(((
    displayId: string | null,
    params: { zoom?: string },
  ) => {
    if (displayId === null) return loaded(undefined);
    if (params?.zoom === "category") {
      return loaded(heatmapResponse(CATEGORY_CELLS, "category"));
    }
    return loaded(heatmapResponse(SUBCAP_CELLS, "subcap"));
  }) as typeof queries.useEntityHeatmap);
}

function mockRoute(query: Record<string, string>): ReturnType<typeof vi.fn> {
  const setQuery = vi.fn();
  vi.spyOn(hashRouter, "useRoute").mockReturnValue({
    path: "/clients/alma-bank-0001/heatmap",
    query,
    hash: `/clients/alma-bank-0001/heatmap`,
    navigate: vi.fn(),
    setQuery,
  });
  return setQuery;
}

afterEach(() => {
  // Unmount FIRST, while the route/query mocks are still in place — the
  // audience reset below re-renders any still-mounted page, and a
  // restored (real) useRoute would change the hook order mid-lifecycle.
  cleanup();
  vi.restoreAllMocks();
  useUiStore.setState({ audience: "internal" });
});

describe("HeatmapPage · standard grid (wireframe port)", () => {
  it("default rung renders pillar bands of per-category aggregate cells + peer row", () => {
    mockRoute({ hm: "standard" });
    mockHeatmapQueries();
    const { container } = render(withClient(<HeatmapPage />));

    // Pillar band headers: chip + display name.
    expect(screen.getByText("Strategy")).toBeTruthy();
    expect(screen.getByText("Customer")).toBeTruthy();
    expect(screen.getByText("Data & Tech")).toBeTruthy();

    // 4 categories → 4 aggregate cells + 4 aligned peer cells.
    expect(container.querySelectorAll(".hm-cell").length).toBe(8);
    expect(container.querySelectorAll(".hm-cell.peer").length).toBe(4);

    // Wireframe aggregate cell shows the thin COUNT (only P1C1 has one).
    expect(screen.getByText("1 thin")).toBeTruthy();
    // P1C1 mean = (2.5 + 1.5 + 1.0) / 3 → 1.7
    expect(screen.getAllByText("1.7").length).toBeGreaterThanOrEqual(1);

    // Column labels: mono category id + backend display name.
    expect(screen.getByText("P1C1")).toBeTruthy();
    expect(screen.getByText("Vision & Operating Model")).toBeTruthy();
  });

  it("aggregate cell click drills down — it never opens synthesis", () => {
    const setQuery = mockRoute({ hm: "standard" });
    mockHeatmapQueries();
    render(withClient(<HeatmapPage />));

    // P1C1's title carries the capped-subcap segment between name and
    // the drill hint, so match on the name only.
    fireEvent.click(screen.getByTitle(/Vision & Operating Model/));
    expect(setQuery).toHaveBeenCalledWith({ zoom: "category:P1C1" });
    expect(setQuery).not.toHaveBeenCalledWith(
      expect.objectContaining({ synthesis: expect.anything() }),
    );
  });

  it("drilled rung renders subcap cells with thin/capped tokens; leaf click opens synthesis", () => {
    const setQuery = mockRoute({ hm: "standard", zoom: "category:P1C1" });
    mockHeatmapQueries();
    const { container } = render(withClient(<HeatmapPage />));

    const leafCells = container.querySelectorAll("button.hm-cell");
    expect(leafCells.length).toBe(3);
    expect(container.querySelectorAll(".hm-cell.thin").length).toBe(1);
    expect(container.querySelectorAll(".hm-cell.capped").length).toBe(1);

    // Breadcrumb (wireframe 07_pages_c.js:86-93).
    expect(screen.getByText("Drilling:")).toBeTruthy();

    // Subcap-grain click → SynthesisDrawer wiring (?synthesis=).
    fireEvent.click(leafCells[0]);
    expect(setQuery).toHaveBeenCalledWith({ synthesis: "P1C1.1.1" });

    // Reset zooms back out to the banded default.
    fireEvent.click(screen.getByText("Reset"));
    expect(setQuery).toHaveBeenCalledWith({ zoom: undefined });
  });

  it("?zoom=subcap renders the full leaf grid grouped by category", () => {
    mockRoute({ hm: "standard", zoom: "subcap" });
    mockHeatmapQueries();
    const { container } = render(withClient(<HeatmapPage />));

    expect(container.querySelectorAll("button.hm-cell").length).toBe(9);
    // One card per category, chip'd with the category id.
    for (const catId of ["P1C1", "P1C2", "P2C1", "P4C3"]) {
      expect(screen.getByText(catId)).toBeTruthy();
    }
  });

  it("customer audience hides Standard and coerces ?hm=standard to focus", () => {
    useUiStore.setState({ audience: "customer" });
    mockRoute({ hm: "standard" });
    mockHeatmapQueries();
    // The coerced focus view mounts FocusAreaView — pin its query too so
    // no real fetch fires (an async rejection would re-render after
    // afterEach restored the mocks → React hook-order crash).
    vi.spyOn(queries, "useFocusAreas").mockReturnValue(
      loaded({ entity_display_id: "alma-bank-0001", run_request_id: null, items: [] }) as unknown as ReturnType<typeof queries.useFocusAreas>,
    );
    const { container } = render(withClient(<HeatmapPage />));

    expect(screen.queryByText("Standard")).toBeNull();
    expect(screen.queryByText("Zoom")).toBeNull();
    // Coerced to the focus view (wireframe customer lock).
    expect(screen.getAllByText(/Strategic priorities|No focus areas/).length).toBeGreaterThanOrEqual(1);
    expect(container.querySelectorAll(".hm-cell").length).toBe(0);
  });
});
