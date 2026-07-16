/**
 * D3 heatmap transitions (2026-07 remediation, plan Part 6 / audit
 * transitions #16 #21 #22 #23):
 *
 *   1. Subcap detail rows (prototype fc639245:552-584) — the substance
 *      list under each category card in the subcap view: score chip,
 *      name, THIN + cap-level badges, id·evidence-count line, the
 *      score-vs-peer bar with peer tick, chevron → synthesis.
 *   2. Export button fires the prototype-parity toast (sim action).
 *   3. Focus view forwards ?run= to useFocusAreas (transition #24).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { HeatmapPage } from "@/pages/HeatmapPage";
import * as queries from "@/lib/queries";
import * as hashRouter from "@/lib/hash-router";
import * as api from "@/lib/api";
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

const SUBCAP_CELLS: HeatmapCell[] = [
  cell("P1C1.1.1", "Strategy Foundation", 2.5, {
    // Router-side evidence attach (Part 6.3) — drives the row's
    // evidence-count line.
    ...( { enrichment_evidence_ids: ["E-001", "E-007"] } as Partial<HeatmapCell>),
  }),
  cell("P1C1.1.2", "Vision Cascade", 1.5, { is_thin_evidence: true }),
  cell("P1C1.2.1", "Governance Charter", 1.0, {
    cap_applied: true, cap_reason: "IR-001 caps at M1",
  }),
];

function heatmapResponse(cells: HeatmapCell[]): HeatmapResponse {
  return {
    entity_display_id: "alma-bank-0001",
    run_request_id: "DMA-ASM-ALMA-20260519-0001",
    run_status: "ACTIVE",
    zoom: "subcap", view_mode: "standard", subvertical: "BANK",
    peer_overlay: true, issue_overlay: false,
    cells, value_chain_buckets: [], catalogue_version: "v7.0",
    warnings: [], narrative: null,
  };
}

function loaded<T>(data: T) {
  return { data, isLoading: false, isError: false, error: null };
}

function mockBaseQueries(): void {
  vi.spyOn(queries, "useEntityOverview").mockReturnValue(
    loaded(undefined) as ReturnType<typeof queries.useEntityOverview>,
  );
  vi.spyOn(queries, "useEntityHeatmap").mockImplementation(((
    displayId: string | null,
  ) => {
    if (displayId === null) return loaded(undefined);
    return loaded(heatmapResponse(SUBCAP_CELLS));
  }) as unknown as typeof queries.useEntityHeatmap);
  vi.spyOn(queries, "useEntityHealth").mockReturnValue(
    loaded({
      caps_applied: [{
        log_id: "c1", subcap_id: "P1C1.2.1", cap_type: "ISSUE_CAP",
        trigger_condition: null, cap_ceiling: "M1", trigger_evidence: [],
        affected_categories: [], severity: null, date_applied: null,
        recalc_verified: null,
      }],
    }) as unknown as ReturnType<typeof queries.useEntityHealth>,
  );
}

function mockRoute(query: Record<string, string>): ReturnType<typeof vi.fn> {
  const setQuery = vi.fn();
  vi.spyOn(hashRouter, "useRoute").mockReturnValue({
    path: "/clients/alma-bank-0001/heatmap",
    query,
    hash: "/clients/alma-bank-0001/heatmap",
    navigate: vi.fn(),
    setQuery,
  });
  return setQuery;
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  useUiStore.setState({ audience: "internal", toasts: [] });
});

describe("HeatmapPage · subcap detail rows (transition #22)", () => {
  it("renders one detail row per subcap under the category card", () => {
    mockRoute({ hm: "standard", zoom: "subcap" });
    mockBaseQueries();
    render(withClient(<HeatmapPage />));

    expect(screen.getByText(/Subcap detail · click any row for synthesis/i)).toBeTruthy();
    const rows = screen.getAllByTestId("subcap-row");
    expect(rows.length).toBe(SUBCAP_CELLS.length);

    // Row substance: name, id·evidence-count line, peer-gap label.
    const first = rows[0];
    expect(first.textContent).toContain("Strategy Foundation");
    expect(first.textContent).toContain("P1C1.1.1");
    expect(first.textContent).toContain("2 evidence items");
    expect(first.textContent).toContain("vs peer");
  });

  it("shows THIN and real cap-level badges on the relevant rows", () => {
    mockRoute({ hm: "standard", zoom: "subcap" });
    mockBaseQueries();
    render(withClient(<HeatmapPage />));

    const rows = screen.getAllByTestId("subcap-row");
    const thinRow = rows.find((r) => r.textContent?.includes("Vision Cascade"));
    expect(thinRow?.textContent).toContain("THIN");
    const cappedRow = rows.find((r) => r.textContent?.includes("Governance Charter"));
    // Real ceiling from health caps_applied ("M1"), not the score proxy.
    expect(cappedRow?.textContent).toContain("M1");
  });

  it("clicking a row opens that subcap's synthesis", () => {
    const setQuery = mockRoute({ hm: "standard", zoom: "subcap" });
    mockBaseQueries();
    render(withClient(<HeatmapPage />));

    const rows = screen.getAllByTestId("subcap-row");
    fireEvent.click(rows[0]);
    expect(setQuery).toHaveBeenCalledWith(
      expect.objectContaining({ synthesis: "P1C1.1.1" }),
    );
  });
});

describe("HeatmapPage · Export toast (transition #21)", () => {
  it("fires the prototype-parity toast instead of a dead button", () => {
    mockRoute({ hm: "standard", zoom: "subcap" });
    mockBaseQueries();
    render(withClient(<HeatmapPage />));

    expect(useUiStore.getState().toasts.length).toBe(0);
    fireEvent.click(screen.getByText(/Export/));
    const toasts = useUiStore.getState().toasts;
    expect(toasts.length).toBe(1);
    expect(toasts[0].text).toMatch(/Exporting .* heatmap as PDF/);
  });
});

describe("HeatmapPage · focus view follows ?run= (transition #24)", () => {
  it("passes the selected run through to useFocusAreas", () => {
    mockRoute({ hm: "focus", run: "REQ-DEADBEEF" });
    mockBaseQueries();
    const faSpy = vi.spyOn(queries, "useFocusAreas").mockReturnValue(
      loaded({ entity_display_id: "alma-bank-0001", items: [] }) as unknown as ReturnType<
        typeof queries.useFocusAreas
      >,
    );
    render(withClient(<HeatmapPage />));
    expect(faSpy).toHaveBeenCalledWith("alma-bank-0001", "REQ-DEADBEEF");
  });
});

describe("SynthesisDrawer · evidence-first composition (#16/#23)", () => {
  function mockSubcapDetail(): void {
    vi.spyOn(api, "apiGet").mockResolvedValue({
      entity_display_id: "alma-bank-0001",
      subcap_id: "P1C1.1.1",
      cells: [
        {
          id: "P1C1.1.1", label: "Strategy Foundation", parent_id: "P1C1",
          score: 2.5, band: "M2", peer_median: 3.1, peer_gap: -0.6,
          is_thin_evidence: false, cap_applied: true,
          cap_reason: "IR-003 caps at M2", issue_count: 1, aliased_from: null,
        },
      ],
      narrative: null,
      polished_rationale: "Workbook rationale text.",
      synthesis_md: "Strategy Foundation (P1C1.1.1) scored 2.5 (M2) in this run.",
      synthesis_source: "heuristic",
      synthesis_evidence_e_ids: ["E-001"],
      evidence: [
        {
          e_id: "E-001", source_name: "10-K FY2025", source_url: null,
          excerpt: "Board approved a three-year digital roadmap.",
          claim_type: "FACT", tier: 1, recency_months: 4,
          published_date: "2026-02-01", freshness_band: "current",
        },
      ],
      issues: [
        {
          issue_id: "IR-003", title: "No integration bus", severity: "MATERIAL",
          rationale: "API gap between core and LOS.", opened_on: "2025-11-01",
          cap_ceiling: "2.0",
        },
      ],
      catalogue_version: "v7.0",
      run_request_id: "DMA-ASM-ALMA-20260519-0001",
    });
  }

  it("orders peer viz → caps (real Cap M{n}) → evidence rows → AI synthesis, with a Copy footer", async () => {
    mockRoute({ hm: "standard", zoom: "subcap", synthesis: "P1C1.1.1" });
    mockBaseQueries();
    mockSubcapDetail();
    render(withClient(<HeatmapPage />));

    const drawer = await screen.findByRole("dialog", { name: /Sub-capability synthesis/i });
    // Evidence-first list with tier chip + claim + excerpt.
    const evidenceRow = await screen.findByTestId("evidence-row");
    expect(evidenceRow.textContent).toContain("E-001");
    expect(evidenceRow.textContent).toContain("T1 · FACT");
    expect(evidenceRow.textContent).toContain("three-year digital roadmap");
    // Per-issue caps block with the REAL cap ceiling.
    expect(drawer.textContent).toContain("Capped by 1 issue");
    expect(drawer.textContent).toContain("IR-003");
    expect(drawer.textContent).toContain("Cap M2.0");
    // AI synthesis section AFTER the evidence ("on the N items above").
    const ai = screen.getByTestId("ai-synthesis");
    expect(ai.textContent).toContain("on the 1 item above");
    expect(ai.textContent).toContain("heuristic");
    expect(
      evidenceRow.compareDocumentPosition(ai) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    // Copy-synthesis footer (transition #23) fires the clipboard + toast.
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    fireEvent.click(screen.getByText(/Copy synthesis/));
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining("Strategy Foundation"));
    expect(useUiStore.getState().toasts.some((t) => /copied/i.test(t.text))).toBe(true);
    // The intelligence-layer fix stays intact: explicit Ask-AI button, no
    // embedded auto-open IntelligencePanel.
    expect(screen.getByText(/Ask AI about this subcap/)).toBeTruthy();
  });

  it("cold/pack serve: renders cell + AI synthesis from the grid snapshot when the live subcap endpoint yields nothing", async () => {
    mockRoute({ hm: "standard", zoom: "subcap", synthesis: "P1C1.1.1" });
    // Grid snapshot (heatmap.json) carries the baked per-subcap synthesis.
    vi.spyOn(queries, "useEntityOverview").mockReturnValue(
      loaded(undefined) as ReturnType<typeof queries.useEntityOverview>,
    );
    vi.spyOn(queries, "useEntityHealth").mockReturnValue(
      loaded({ caps_applied: [] }) as unknown as ReturnType<typeof queries.useEntityHealth>,
    );
    vi.spyOn(queries, "useEntityHeatmap").mockImplementation(((
      displayId: string | null,
    ) => {
      if (displayId === null) return loaded(undefined);
      const resp = heatmapResponse(SUBCAP_CELLS);
      resp.narrative = {
        per_subcap_md: {
          "P1C1.1.1":
            "Digital Onboarding scored 2.4 (M2) in this run. Grounding [E-047]: '195,000 clients, $386B AUM' — trails the peer median.",
        },
        per_subcap_meta: { "P1C1.1.1": "heuristic" },
      };
      return loaded(resp);
    }) as unknown as typeof queries.useEntityHeatmap);
    // Live per-subcap endpoint is unreachable pack-first → the query rejects.
    vi.spyOn(api, "apiGet").mockRejectedValue(new Error("backend cold"));

    render(withClient(<HeatmapPage />));

    const drawer = await screen.findByRole("dialog", { name: /Sub-capability synthesis/i });
    // AI synthesis panel shows the pack-baked woven-evidence text + source
    // chip. Awaiting it also waits out the (rejected) live-endpoint query so
    // the drawer has settled off its loading state.
    const ai = await screen.findByTestId("ai-synthesis");
    expect(ai.textContent).toContain("Digital Onboarding scored 2.4");
    expect(ai.textContent).toContain("E-047");
    expect(ai.textContent).toContain("heuristic");
    // Cell rendered from the grid snapshot (label), not an empty state.
    expect(drawer.textContent).toContain("Strategy Foundation");
    expect(screen.queryByText(/Subcap detail unavailable/)).toBeNull();
  });
});
