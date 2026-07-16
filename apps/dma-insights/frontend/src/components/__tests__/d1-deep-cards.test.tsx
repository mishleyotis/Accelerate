/**
 * D1 "Evidence & benchmarks" cards (plan 4.6, proto df85cc41): populated,
 * honest-empty, audience-gated, and eId drill states for the five new cards.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useUiStore } from "@/store/ui";
import { EvidenceTierCard } from "@/components/cards/EvidenceTierCard";
import { CoverageByPillarCard } from "@/components/cards/CoverageByPillarCard";
import { FinancialTrajectoryCard } from "@/components/cards/FinancialTrajectoryCard";
import { CeilingEstimateCard } from "@/components/cards/CeilingEstimateCard";
import { SentimentCard } from "@/components/cards/SentimentCard";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("EvidenceTierCard", () => {
  it("renders the tier histogram + claim chips from runs.evidence_summary", () => {
    render(<EvidenceTierCard data={{
      total_items: 110, total_facts: 387,
      tiers: { T1: 8, T3: 70, T5: 12 },
      claims: { FACT: 342, INFERENCE: 41 },
      signals: { NEUTRAL: 80, NEGATIVE: 10 },
    }} />);
    expect(screen.getByText("110 items · 387 facts")).toBeTruthy();
    expect(screen.getByText("T1")).toBeTruthy();
    expect(screen.getByText("70")).toBeTruthy();
    expect(screen.getByText("fact · 342")).toBeTruthy();
    expect(screen.getByText("negative · 10")).toBeTruthy();
  });

  it("honest-empty when the run has no evidence index", () => {
    render(<EvidenceTierCard data={null} />);
    expect(screen.getByText(/No evidence index for this run/)).toBeTruthy();
  });
});

describe("CoverageByPillarCard", () => {
  it("renders per-pillar coverage vs the 80% gate + the thin hint", () => {
    render(<CoverageByPillarCard data={{
      overall_pct: 81, gate_pct: 80,
      by_pillar: [
        { pillar: "P1", pct: 100, subcaps: 16, scored: 16, thin: 0 },
        { pillar: "P4", pct: 50, subcaps: 10, scored: 5, thin: 5 },
      ],
    }} />);
    expect(screen.getByText("81% overall")).toBeTruthy();
    expect(screen.getByText("Data & Tech")).toBeTruthy();
    expect(screen.getByText("50%")).toBeTruthy();
    expect(screen.getByText(/5 subcaps on thin evidence/)).toBeTruthy();
  });

  it("honest-empty without coverage stats", () => {
    render(<CoverageByPillarCard data={null} />);
    expect(screen.getByText(/Coverage populates once/)).toBeTruthy();
  });
});

describe("FinancialTrajectoryCard", () => {
  const traj = {
    currency: "USD", unit: "B", fy: ["FY2023", "FY2024", "FY2025"],
    series: { total_assets: [9.8, 10.4, 11.1], net_income_m: [188, null, 199] },
    branches: 64, regulator: "FDIC", geography: "NY · NJ", employees: 1640,
    headline: "$11.1B assets · FY2025 · +6.4% CAGR",
    events: [{ fy: "FY2024", label: "nCino core migration announced" }],
  };

  it("renders the labeled multi-year series + headline + fy events + footer", () => {
    render(<FinancialTrajectoryCard data={traj} />);
    expect(screen.getByText("$11.1B assets · FY2025 · +6.4% CAGR")).toBeTruthy();
    expect(screen.getByText("$9.8B")).toBeTruthy();
    expect(screen.getByText("'2025")).toBeTruthy();
    expect(screen.getByText(/nCino core migration announced/)).toBeTruthy();
    expect(screen.getByText("FDIC")).toBeTruthy();
    expect(screen.getByText(/64 branches · 1,640 FTE/)).toBeTruthy();
  });

  it("honest-empty when fewer than two periods exist", () => {
    render(<FinancialTrajectoryCard data={null} />);
    expect(screen.getByText(/No multi-year series is derivable/)).toBeTruthy();
  });

  it("charts a broker REVENUE series (not total_assets) — audit bug 6", () => {
    // Alliant SV7 broker: revenue is the scale metric. The card must chart it.
    render(<FinancialTrajectoryCard data={{
      currency: "USD", unit: "B", fy: ["FY2021", "FY2022", "FY2023", "FY2024"],
      series: { net_income_m: null, revenue: [2.0, 3.0, 4.0, 5.1] },
      headline: "$5.1B revenue · FY2024 · +36.6% CAGR",
    }} />);
    expect(screen.getByText("$5.1B revenue · FY2024 · +36.6% CAGR")).toBeTruthy();
    expect(screen.getByText("$5.1B")).toBeTruthy();       // last revenue bar
    expect(screen.getByText("'2024")).toBeTruthy();
  });

  it("renders the highlights + ratings + events variant — audit bug 1", () => {
    // Capital Farm: no >=2yr chart, but loans/patronage/credit-quality + Fitch
    // BBB / Moody's Aa3 + a driver event are real depth (not an empty state).
    render(<FinancialTrajectoryCard data={{
      currency: "USD", unit: "B", fy: [],
      highlights: [
        { label: "Loans", value: 13.2, unit: "B" },
        { label: "Patronage", value: 190, unit: "M" },
        { label: "Credit quality", value: 95.6, unit: "%" },
      ],
      ratings: { Fitch: "BBB (Stable)", "Moody's": "Aa3 (parent)" },
      events: [{ fy: "FY2024", label: "Record net income" }],
    }} />);
    expect(screen.getByText("Financial highlights")).toBeTruthy();
    expect(screen.getByText("$13.2B")).toBeTruthy();
    expect(screen.getByText("95.6%")).toBeTruthy();
    expect(screen.getByText(/Fitch: BBB \(Stable\)/)).toBeTruthy();
    expect(screen.getByText(/Record net income/)).toBeTruthy();
  });
});

describe("CeilingEstimateCard", () => {
  const bands = {
    P4C1: {
      ceiling: 2.2, band: 0.5,
      modifiers: ["cap M3 applied: AML consent order caps at M3"],
      evidence: ["E-218"],
      rationale: "Data Foundation averages 1.8/5 over 10 scored subcaps.",
    },
  };

  it("renders bands and drills to modifiers + rationale + evidence chip → drawer(eId)", () => {
    const openDrawer = vi.fn();
    useUiStore.setState({ openDrawer });
    render(<CeilingEstimateCard data={bands} audience="internal" displayId="alma-0001" />);
    expect(screen.getByText("P4C1")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Ceiling detail P4C1/ }));
    expect(screen.getByText(/AML consent order caps at M3/)).toBeTruthy();
    expect(screen.getByText(/averages 1.8\/5/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "E-218" }));
    expect(openDrawer).toHaveBeenCalledWith(
      "evidence", expect.objectContaining({ eId: "E-218", origin: "ceiling-card" }),
    );
  });

  it("is internal-only (renders nothing for customer audience)", () => {
    const { container } = render(
      <CeilingEstimateCard data={bands} audience="customer" displayId="alma-0001" />,
    );
    expect(container.firstChild).toBeNull();
  });
});

describe("SentimentCard", () => {
  const data = {
    employee: [{ source: "Glassdoor", metric: "Overall", score: 3.6, scale: 5, n: 312 }],
    customer: [{ source: "App Store", metric: "Mobile app", score: 2.4, scale: 5, n: 1240, flag: "below_peer" }],
    industry_avg: 3.5, b2b_b2c_gap: true,
  };

  it("renders employee/customer splits with scale + below-peer flag + gap badge", () => {
    render(<SentimentCard data={data} audience="internal" />);
    expect(screen.getByText("Employee")).toBeTruthy();
    expect(screen.getByText("Customer")).toBeTruthy();
    expect(screen.getByText("3.6")).toBeTruthy();
    expect(screen.getByText("BELOW PEER")).toBeTruthy();
    expect(screen.getByText("B2B/B2C gap")).toBeTruthy();
    expect(screen.getByText("Industry avg 3.5")).toBeTruthy();
  });

  it("is internal-only + honest-empty without normalized rows", () => {
    const { container } = render(<SentimentCard data={data} audience="customer" />);
    expect(container.firstChild).toBeNull();
    render(<SentimentCard data={{ sources: [] }} audience="internal" />);
    expect(screen.getByText(/No public review signal/)).toBeTruthy();
  });
});
