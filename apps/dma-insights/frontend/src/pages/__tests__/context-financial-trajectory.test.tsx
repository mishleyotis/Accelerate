/**
 * D5 Context · Financial trajectory — the wireframe FinChartInteractive
 * contract (context prototype 28883abf): a per-year BAR CHART with hover
 * + the CAGR summary strip, never a text/tile dump, whenever ANY year→$
 * series is derivable from the payload:
 *   1. `series_labeled` shipped        → chart, data-source="api"
 *   2. only prose/metrics text shipped → chart from the client-side
 *      miner (lib/financialSeries), data-source="derived"
 *   3. nothing derivable              → honest text state (kv metrics)
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { FinancialTrajectoryCard } from "@/pages/ContextPage";

afterEach(cleanup);

describe("FinancialTrajectoryCard (D5 Context)", () => {
  it("charts the shipped series_labeled (data-source=api)", () => {
    const { container } = render(
      <FinancialTrajectoryCard financials={{
        series_labeled: [
          { metric: "total_assets", unit: "usd_b", fy: [2022, 2023, 2024], values: [2.9, 3.0, 3.2] },
        ],
      } as never} />,
    );
    expect(container.querySelector("section")?.getAttribute("data-source")).toBe("api");
    expect(screen.getAllByTestId("fin-bar").length).toBe(3);
    expect(container.textContent).toContain("Series CAGR");
  });

  it("falls back to MINING the prose series when series_labeled is empty (data-source=derived)", () => {
    const { container } = render(
      <FinancialTrajectoryCard financials={{
        metrics: { rating: "A+" },
        lines: ["Total assets grew from $2.286B in 2021 to $3.209B in 2025."],
      }} />,
    );
    // The wireframe bar chart renders — NOT the kv/text fallback.
    expect(container.querySelector("section")?.getAttribute("data-source")).toBe("derived");
    const bars = screen.getAllByTestId("fin-bar");
    expect(bars.length).toBe(2);
    expect(container.textContent).toContain("$2.3B");
    expect(container.textContent).toContain("$3.2B");
    expect(container.textContent).toContain("Series CAGR");
    expect(container.textContent).not.toContain("No multi-year financial series");
    // Hover interactivity (prototype FinChartInteractive).
    fireEvent.mouseEnter(bars[1]);
    expect(container.textContent).toContain("2025:");
  });

  it("keeps the honest text state when nothing is derivable", () => {
    const { container } = render(
      <FinancialTrajectoryCard financials={{
        metrics: { rating: "A+", regulator: "FDIC" },
      }} />,
    );
    expect(container.querySelector("section")?.getAttribute("data-source")).toBe("api-empty");
    expect(screen.queryAllByTestId("fin-bar").length).toBe(0);
    expect(container.textContent).toContain("No multi-year financial series");
    expect(container.textContent).toContain("rating");
  });

  it("empty payload renders the empty state", () => {
    render(<FinancialTrajectoryCard financials={null} />);
    expect(screen.getByText("No financials on record")).toBeTruthy();
  });
});
