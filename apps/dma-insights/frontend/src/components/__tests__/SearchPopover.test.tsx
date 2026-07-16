/**
 * SearchPopover — quick-links default, multi-surface results, no-results,
 * keyboard navigation (↑/↓/Enter/Esc), and routing on activate.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { SearchPopover } from "@/components/SearchPopover";
import * as queries from "@/lib/queries";
import * as hashRouter from "@/lib/hash-router";
import type { SearchHit } from "@/lib/queries";

function mockSearch(results: SearchHit[] | undefined, isLoading = false): void {
  vi.spyOn(queries, "useSearch").mockReturnValue({
    data: results ? { query: "q", total: results.length, results } : undefined,
    isLoading,
  } as unknown as ReturnType<typeof queries.useSearch>);
}

function mockRoute(): ReturnType<typeof vi.fn> {
  const navigate = vi.fn();
  vi.spyOn(hashRouter, "useRoute").mockReturnValue({
    path: "/", query: {}, navigate, setQuery: vi.fn(),
  } as unknown as ReturnType<typeof hashRouter.useRoute>);
  return navigate;
}

const HITS: SearchHit[] = [
  { kind: "entity", title: "Alma Bank", sub: "Regional bank", route: "/clients/alma-0001/overview", icon: "users" },
  { kind: "insight", title: "Fragmented data estate", sub: "IC-012 · RISK", route: "/clients/alma-0001/insights?card=IC-012", icon: "insight" },
  { kind: "evidence", title: "10-K risk factor", sub: "E-031 · T1", route: "/clients/alma-0001/insights?evidence=E-031", icon: "evidence" },
];

function typeQuery(value: string): void {
  fireEvent.change(screen.getByLabelText("Search entities, insights, and evidence"), {
    target: { value },
  });
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("SearchPopover", () => {
  it("shows static Quick links before the operator types", () => {
    mockSearch(undefined);
    mockRoute();
    render(<SearchPopover onClose={() => undefined} />);
    expect(screen.getByText("Quick links")).toBeTruthy();
    expect(screen.getByText("All clients")).toBeTruthy();
    expect(screen.getByText("Alerts")).toBeTruthy();
    expect(screen.getByText("Prospecting")).toBeTruthy();
    expect(screen.getByText("Dashboard")).toBeTruthy();
  });

  it("clicking a quick link routes and closes", () => {
    mockSearch(undefined);
    const navigate = mockRoute();
    const onClose = vi.fn();
    render(<SearchPopover onClose={onClose} />);
    fireEvent.click(screen.getByText("Alerts"));
    expect(navigate).toHaveBeenCalledWith("/alerts");
    expect(onClose).toHaveBeenCalled();
  });

  it("renders grouped entity / insight / evidence hits once a query is typed", () => {
    mockSearch(HITS);
    mockRoute();
    render(<SearchPopover onClose={() => undefined} />);
    typeQuery("alma");
    expect(screen.queryByText("Quick links")).toBeNull();
    expect(screen.getByText("Alma Bank")).toBeTruthy();
    expect(screen.getByText("Fragmented data estate")).toBeTruthy();
    expect(screen.getByText("10-K risk factor")).toBeTruthy();
    expect(screen.getByText("IC-012 · RISK")).toBeTruthy();
    // kind labels on the right of each row
    expect(screen.getAllByText("entity").length).toBeGreaterThan(0);
  });

  it("clicking a result routes to its page", () => {
    mockSearch(HITS);
    const navigate = mockRoute();
    render(<SearchPopover onClose={() => undefined} />);
    typeQuery("alma");
    fireEvent.click(screen.getByText("Fragmented data estate"));
    expect(navigate).toHaveBeenCalledWith("/clients/alma-0001/insights?card=IC-012");
  });

  it("shows a No results state when the query matches nothing", () => {
    mockSearch([]);
    mockRoute();
    render(<SearchPopover onClose={() => undefined} />);
    typeQuery("zzzzz");
    expect(screen.getByText("No results")).toBeTruthy();
    expect(screen.getByText(/Try an entity name/)).toBeTruthy();
  });

  it("↓ then Enter opens the second result; Esc closes", () => {
    mockSearch(HITS);
    const navigate = mockRoute();
    const onClose = vi.fn();
    render(<SearchPopover onClose={onClose} />);
    typeQuery("alma");
    const dialog = screen.getByRole("dialog", { name: "Search" });
    fireEvent.keyDown(dialog, { key: "ArrowDown" });   // 0 → 1 (insight)
    fireEvent.keyDown(dialog, { key: "Enter" });
    expect(navigate).toHaveBeenCalledWith("/clients/alma-0001/insights?card=IC-012");
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("clicking the mask closes the popover", () => {
    mockSearch(undefined);
    mockRoute();
    const onClose = vi.fn();
    const { container } = render(<SearchPopover onClose={onClose} />);
    const mask = container.querySelector(".popover-mask");
    expect(mask).toBeTruthy();
    fireEvent.click(mask as Element);
    expect(onClose).toHaveBeenCalled();
  });
});
