/**
 * Part 9 TechStack workstream — functional "Hide absent", real ABSENT
 * gap-row rendering (list + detail: gap zones, Zennify recommendation,
 * peer % bar + named peers), the honest DMA-impact uplift, and the
 * detail pack fallback (hydrate from the techstack LIST snapshot row
 * when the API is cold).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useQuery } from "@tanstack/react-query";
import * as hashRouter from "@/lib/hash-router";
import * as queries from "@/lib/queries";
import { useUiStore } from "@/store/ui";
import { TechStackPage, type TechStackEntryOut } from "@/pages/TechStackPage";
import { TechStackDetailPage, avgPeerUplift } from "@/pages/TechStackDetailPage";
import { detailFromListRow } from "@/lib/queries";
import type { TechStackDetailResponse } from "@/lib/queries";

vi.mock("@tanstack/react-query", () => ({ useQuery: vi.fn() }));

function entry(over: Partial<TechStackEntryOut> = {}): TechStackEntryOut {
  return {
    id: "1", tech_id: "salesforce_crm", vendor: "Salesforce", product: "Sales Cloud",
    product_name: "Sales Cloud", layer: "application", status: "CONFIRMED",
    l3_id: "salesforce", source: "Explorium", evidence_e_ids: [],
    linked_subcap_ids: [], detected_at: "2026-06-01T00:00:00Z",
    ...over,
  };
}

function absentRow(over: Partial<TechStackEntryOut> = {}): TechStackEntryOut {
  return entry({
    id: "absent-ncino", tech_id: "absent-ncino", vendor: "nCino",
    product: "nCino platform family", product_name: "nCino platform family",
    status: "ABSENT", l3_id: "ncino", source: "derived:gap_analysis",
    detected_at: null, primary_gap: true, peer_coverage: 0.6,
    linked_subcap_ids: ["P2C2.1.1", "P3C2.3.1"],
    note: "No nCino detected in the stack · addresses 2 scored sub-capabilities · 60% of cohort peers deploy it",
    layer_code: "L3", layer_full: "Customer engagement", dma_pillar: "P3",
    ...over,
  });
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function mountList(items: TechStackEntryOut[], extra: Record<string, unknown> = {}) {
  const navigate = vi.fn();
  useUiStore.setState({ openDrawer: vi.fn() });
  vi.spyOn(hashRouter, "useRoute").mockReturnValue({
    path: "/clients/alma-0001/techstack", query: {}, navigate, setQuery: vi.fn(),
  } as unknown as ReturnType<typeof hashRouter.useRoute>);
  vi.spyOn(queries, "useEntityOverview").mockReturnValue({
    data: { entity: { name: "Alma Bank" } },
  } as unknown as ReturnType<typeof queries.useEntityOverview>);
  (useQuery as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
    data: { entity_display_id: "alma-0001", items, last_synced_at: null, ...extra },
    isLoading: false, error: null,
  });
  return { navigate };
}

describe("TechStackPage · ABSENT gap rows + Hide absent", () => {
  it("renders the real ABSENT row with note, primary-gap chip and peer share", () => {
    mountList([entry(), absentRow()]);
    render(<TechStackPage />);
    expect(screen.getByText("ABSENT")).toBeTruthy();
    expect(screen.getByText("PRIMARY GAP")).toBeTruthy();
    expect(screen.getByText(/No nCino detected in the stack/)).toBeTruthy();
    expect(screen.getByText("60% of peers")).toBeTruthy();
    // ABSENT rows carry no detected_at → no "Since"/"Detected" label on them
    const rows = screen.getAllByTestId("tech-row");
    expect(rows).toHaveLength(2);
    expect(rows.some((r) => r.getAttribute("data-status") === "ABSENT")).toBe(true);
  });

  it("'Hide absent' is functional: toggling removes ABSENT rows from the list", () => {
    mountList([entry(), absentRow()]);
    render(<TechStackPage />);
    expect(screen.getAllByTestId("tech-row")).toHaveLength(2);
    fireEvent.click(screen.getByTestId("hide-absent-switch"));
    const rows = screen.getAllByTestId("tech-row");
    expect(rows).toHaveLength(1);
    expect(rows[0].getAttribute("data-status")).not.toBe("ABSENT");
    // toggling back restores the gap row
    fireEvent.click(screen.getByTestId("hide-absent-switch"));
    expect(screen.getAllByTestId("tech-row")).toHaveLength(2);
  });

  it("displacement banner is grounded on the real ABSENT rows", () => {
    mountList([entry(), absentRow()]);
    render(<TechStackPage />);
    const banner = screen.getByTestId("displacement-banner");
    expect(banner.textContent).toContain("1 scored platform family absent");
    expect(banner.textContent).toContain("nCino");
  });

  it("shows the engineering-signal / review-queue triage strip", () => {
    mountList([entry()], {
      engineering_signal_count: 3,
      engineering_signals: ["React", "Python", "Java"],
      review_queue_count: 5,
    });
    render(<TechStackPage />);
    const strip = screen.getByTestId("taxonomy-triage-strip");
    expect(strip.textContent).toContain("Engineering signals (3");
    expect(strip.textContent).toContain("React · Python · Java");
    expect(strip.textContent).toContain("5 off-catalogue detections");
  });
});

describe("TechStackDetailPage · ABSENT drilldown", () => {
  function mountDetail(detail: TechStackDetailResponse) {
    const navigate = vi.fn();
    useUiStore.setState({ openDrawer: vi.fn() });
    vi.spyOn(hashRouter, "useRoute").mockReturnValue({
      path: `/clients/alma-0001/techstack/${detail.entry.tech_id}`,
      query: {}, navigate, setQuery: vi.fn(),
    } as unknown as ReturnType<typeof hashRouter.useRoute>);
    (useQuery as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: detail, isLoading: false, error: null,
    });
    return { navigate };
  }

  it("renders gap zones + Zennify recommendation + peer bar + named peers", () => {
    mountDetail({
      entry: absentRow(),
      linked_subcap_ids: ["P2C2.1.1", "P3C2.3.1"],
      evidence_e_ids: [],
      peer_adoption_count: 3,
      peer_coverage: 0.6,
      cohort_size: 5,
      cohort_label: "RB cohort",
      peer_names: [
        { name: "Bank of Utah", has_tech: true },
        { name: "CalPrivate Bank", has_tech: false },
      ],
      impacts: [
        { subcap_id: "P2C2.1.1", name: "Pipeline mgmt", score: 1.8, peer_median: 2.8, thin: false },
        { subcap_id: "P3C2.3.1", name: "Loan origination", score: 2.0, peer_median: 3.0, thin: true },
      ],
      gap_zones: [
        "Pipeline mgmt (P2C2.1.1) scored 1.8 vs peer median 2.8 — the nCino family addresses this capability (catalogue platform mapping).",
        "60% of RB cohort deploy nCino — greenfield/displacement conversation available.",
      ],
    });
    render(<TechStackDetailPage />);
    // status chip honest
    expect(screen.getByTestId("detail-status-chip").textContent).toContain("Absent - not detected");
    // gap zones section
    const zones = screen.getByTestId("gap-zones-card");
    expect(zones.textContent).toContain("what nCino would unlock");
    expect(zones.textContent).toContain("P2C2.1.1");
    // Zennify recommendation callout
    const rec = screen.getByTestId("zennify-recommendation");
    expect(rec.textContent).toContain("Zennify recommendation");
    expect(rec.textContent).toContain("60% of RB cohort");
    // peer deployment: % bar + named peers with real adoption flags
    expect(screen.getByTestId("peer-coverage-bar").style.width).toBe("60%");
    const peerRows = screen.getAllByTestId("peer-name-row");
    expect(peerRows).toHaveLength(2);
    expect(peerRows[0].textContent).toContain("Bank of Utah");
    expect(peerRows[0].textContent).toContain("✓");
    expect(peerRows[1].textContent).toContain("not detected");
    // DMA impact = avg gap to peer median (computable) with blocked label
    const stat = screen.getByTestId("dma-impact-stat");
    expect(stat.textContent).toContain("−1.0");
    expect(stat.textContent).toContain("ceiling blocked");
  });

  it("falls back to the honest linked-subcap count when uplift is not computable", () => {
    mountDetail({
      entry: entry({ status: "CONFIRMED" }),
      linked_subcap_ids: ["P2C1.1"],
      evidence_e_ids: ["E-012"],
      peer_adoption_count: 4,
      impacts: [{ subcap_id: "P2C1.1" }],
    });
    render(<TechStackDetailPage />);
    const stat = screen.getByTestId("dma-impact-stat");
    expect(stat.textContent).toContain("1");
    expect(stat.textContent).toContain("linked sub-capability");
  });
});

describe("avgPeerUplift", () => {
  it("averages the positive gap to peer median", () => {
    expect(avgPeerUplift([
      { subcap_id: "a", score: 1.5, peer_median: 2.5 },
      { subcap_id: "b", score: 3.0, peer_median: 2.0 },  // above peer → 0
    ])).toEqual({ value: 0.5, n: 2 });
  });

  it("returns null when no impact carries both score + peer median", () => {
    expect(avgPeerUplift([{ subcap_id: "a" }])).toBeNull();
    expect(avgPeerUplift([])).toBeNull();
    expect(avgPeerUplift(undefined)).toBeNull();
  });
});

describe("detailFromListRow (pack fallback shape)", () => {
  it("hydrates a detail payload from the snapshotted list row without fabricating cohort data", () => {
    const row = absentRow();
    const detail = detailFromListRow(row);
    expect(detail.entry).toBe(row);
    expect(detail.linked_subcap_ids).toEqual(["P2C2.1.1", "P3C2.3.1"]);
    expect(detail.peer_coverage).toBe(0.6);
    // cohort extras are NOT fabricated — they arrive when the API warms
    expect(detail.peer_names).toEqual([]);
    expect(detail.gap_zones).toEqual([]);
    expect(detail.cohort_size).toBeNull();
    // impacts degrade to bare subcap ids (no fake scores)
    expect(detail.impacts).toEqual([
      { subcap_id: "P2C2.1.1" }, { subcap_id: "P3C2.3.1" },
    ]);
  });
});
