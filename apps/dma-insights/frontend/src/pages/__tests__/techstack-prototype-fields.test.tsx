/**
 * TechStack prototype alignment — the honest 4-state backend enum
 * (CONFIRMED/INFERRED/CLAIMED/ABSENT + CONFIRMED_REMOVED), the l3_id
 * platform link, and product_name drive the page. Legacy snapshot rows
 * (DETECTED / free-form) are normalised in mapStatus.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useQuery } from "@tanstack/react-query";
import * as hashRouter from "@/lib/hash-router";
import * as queries from "@/lib/queries";
import { useUiStore } from "@/store/ui";
import {
  TechStackPage,
  mapStatus,
  type TechStackEntryOut,
} from "@/pages/TechStackPage";

vi.mock("@tanstack/react-query", () => ({ useQuery: vi.fn() }));

function entry(over: Partial<TechStackEntryOut> = {}): TechStackEntryOut {
  return {
    id: "1", tech_id: "salesforce_crm", vendor: "Salesforce", product: "Sales Cloud",
    product_name: "Sales Cloud", layer: "application", status: "CONFIRMED",
    l3_id: "salesforce", source: "Explorium", evidence_e_ids: ["E-012"],
    linked_subcap_ids: ["P2C1.1"], detected_at: "2026-06-01T00:00:00Z",
    ...over,
  };
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("mapStatus", () => {
  it("passes the backend 4-state enum through unchanged", () => {
    expect(mapStatus(entry({ status: "CONFIRMED" }))).toBe("CONFIRMED");
    expect(mapStatus(entry({ status: "INFERRED" }))).toBe("INFERRED");
    expect(mapStatus(entry({ status: "CLAIMED" }))).toBe("CLAIMED");
    expect(mapStatus(entry({ status: "ABSENT" }))).toBe("ABSENT");
    expect(mapStatus(entry({ status: "CONFIRMED_REMOVED" }))).toBe("CONFIRMED_REMOVED");
  });

  it("maps the legacy snapshot DETECTED onto INFERRED (it was always a technographic inference)", () => {
    expect(mapStatus(entry({ status: "DETECTED" }))).toBe("INFERRED");
  });

  it("falls back to the evidence heuristic for legacy free-form status", () => {
    expect(mapStatus({ status: "active" as never, source: "Explorium", evidence_e_ids: [] })).toBe("CONFIRMED");
    expect(mapStatus({ status: "" as never, source: "", evidence_e_ids: [] })).toBe("INFERRED");
  });
});

describe("TechStackPage prototype fields", () => {
  function mountWith(items: TechStackEntryOut[]): { navigate: ReturnType<typeof vi.fn>; openDrawer: ReturnType<typeof vi.fn> } {
    const navigate = vi.fn();
    const openDrawer = vi.fn();
    useUiStore.setState({ openDrawer });
    vi.spyOn(hashRouter, "useRoute").mockReturnValue({
      path: "/clients/alma-0001/techstack", query: {}, navigate, setQuery: vi.fn(),
    } as unknown as ReturnType<typeof hashRouter.useRoute>);
    vi.spyOn(queries, "useEntityOverview").mockReturnValue({
      data: { entity: { name: "Alma Bank" } },
    } as unknown as ReturnType<typeof queries.useEntityOverview>);
    (useQuery as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: { entity_display_id: "alma-0001", items, last_synced_at: null },
      isLoading: false, error: null,
    });
    return { navigate, openDrawer };
  }

  it("renders the 4-state status pill + the l3_id platform link", () => {
    mountWith([
      entry({ vendor: "Salesforce", status: "CONFIRMED", l3_id: "salesforce" }),
      entry({ id: "2", tech_id: "cobol", vendor: "Legacy COBOL", product: "Legacy COBOL",
              product_name: "Legacy COBOL", status: "CONFIRMED_REMOVED",
              l3_id: null, evidence_e_ids: [] }),
      entry({ id: "3", tech_id: "hubspot", vendor: "HubSpot", product: "HubSpot",
              product_name: "HubSpot", status: "CLAIMED", l3_id: null, evidence_e_ids: [] }),
    ]);
    render(<TechStackPage />);
    expect(screen.getByText("CONFIRMED")).toBeTruthy();
    expect(screen.getByText("REMOVED")).toBeTruthy();         // CONFIRMED_REMOVED label
    expect(screen.getByText("CLAIMED")).toBeTruthy();
    expect(screen.getByText("▸ salesforce")).toBeTruthy();    // l3_id chip
  });

  it("stat strip binds the real 4-state statuses; legend is honest", () => {
    mountWith([
      entry({ status: "CONFIRMED" }),
      entry({ id: "2", tech_id: "acme", vendor: "Acme", product: "Acme",
              product_name: "Acme", status: "INFERRED", l3_id: null }),
    ]);
    render(<TechStackPage />);
    // Tiles: Confirmed / Inferred / claimed / Absent / Primary gaps
    expect(screen.getByText("Inferred / claimed")).toBeTruthy();
    expect(screen.getByText("Primary gaps")).toBeTruthy();
    // Legend covers all 4 states honestly
    expect(screen.getByText("Claimed")).toBeTruthy();
    expect(screen.getByText("Marketing-tier source only")).toBeTruthy();
  });

  it("clicking the l3_id chip drills to the platform page (and stops row nav)", () => {
    const { navigate } = mountWith([entry({ l3_id: "salesforce" })]);
    render(<TechStackPage />);
    fireEvent.click(screen.getByText("▸ salesforce"));
    expect(navigate).toHaveBeenCalledWith("/clients/alma-0001/platform?platform=salesforce");
    // stopPropagation: the row's open-detail nav must NOT also fire
    expect(navigate).not.toHaveBeenCalledWith(expect.stringContaining("/techstack/"));
  });

  it("clicking an evidence chip opens the EvidenceDrawer (and stops row nav)", () => {
    const { navigate, openDrawer } = mountWith([
      entry({ l3_id: null, evidence_e_ids: ["E-012"] }),
    ]);
    render(<TechStackPage />);
    fireEvent.click(screen.getByText("E-012"));
    expect(openDrawer).toHaveBeenCalledWith(
      "evidence", expect.objectContaining({ eId: "E-012", origin: "techstack-row" }),
    );
    expect(navigate).not.toHaveBeenCalled();
  });

  it("labels the ingest timestamp 'Detected', and real since as 'Since'", () => {
    mountWith([
      entry({ since: null, detected_at: "2026-06-01T00:00:00Z" }),
      entry({ id: "2", tech_id: "ncino", vendor: "nCino", product: "nCino",
              product_name: "nCino", since: "2025-Q3", l3_id: null, evidence_e_ids: [] }),
    ]);
    render(<TechStackPage />);
    expect(screen.getByText(/^Detected /)).toBeTruthy();
    expect(screen.getByText("Since 2025-Q3")).toBeTruthy();
    // the misleading "Since {ingest date}" label must be gone
    expect(screen.queryByText(/^Since Jun/)).toBeNull();
  });
});
