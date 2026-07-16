/**
 * D1 drill-downs (2026-06-23 states audit): why-now signals and top-findings
 * evidence must open the EvidenceDrawer — previously both were static.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import * as hashRouter from "@/lib/hash-router";
import { useUiStore } from "@/store/ui";
import { WhyNowStrip, TopFindingsCard, SourceQualityBanner, PillarBars } from "@/pages/ClientOverviewPage";

function stubRoute(): void {
  vi.spyOn(hashRouter, "useRoute").mockReturnValue({
    path: "/clients/alma-0001/overview", query: {}, navigate: vi.fn(), setQuery: vi.fn(),
  } as unknown as ReturnType<typeof hashRouter.useRoute>);
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("D1 WhyNowStrip deep drill (14-field signals)", () => {
  const deepSignal = {
    kind: "REGULATORY", category: "regulatory", strength: "STRONG",
    label: "AML consent order remediation", window: "closes Q4 2026",
    confidence: "HIGH", claim: "FACT",
    text: "AML consent order remediation closes Q4 2026.",
    detail: "AML consent order remediation closes Q4 2026 per the issue register.",
    metric: "remediation budget $12M", peer_context: "Peers run 2.8 here",
    play: "Lead with governed data remediation.",
    risk: "Remediation scope hardens as the clock runs.",
    impact: "Dictates near-term compliance investment.",
    timeline: { date: "2026-11-01", event: "Consent order target close" },
    evidence: ["E-007", "E-218"],
  };

  // Prototype contract (Standalone-4, ClientOverviewPage commit d109cd6b): the
  // LEAD trigger renders EXPANDED by default; the signal type is a color-coded
  // category ICON (not a text kind chip); evidence chips live in the open drill;
  // the risk block header reads "If ignored"; an evidence-less signal shows the
  // honest "No direct evidence yet — confirm in first meeting" footer.
  it("lead tile is expanded by default with label headline, strength, window and an evidence chip", () => {
    useUiStore.setState({ openDrawer: vi.fn() });
    stubRoute();
    render(<WhyNowStrip displayId="alma-0001" signals={[deepSignal]} />);
    expect(screen.getByText("AML consent order remediation")).toBeTruthy();  // label headline
    expect(screen.getByText("STRONG")).toBeTruthy();
    expect(screen.getByText("closes Q4 2026")).toBeTruthy();
    // open-by-default → the evidence chip is visible without a click
    expect(screen.getByRole("button", { name: /E-007/ })).toBeTruthy();
  });

  it("the expanded drill shows play/risk/metric/peer/timeline, opens the drawer, and collapses to the impact one-liner", () => {
    const openDrawer = vi.fn();
    useUiStore.setState({ openDrawer });
    stubRoute();
    render(<WhyNowStrip displayId="alma-0001" signals={[deepSignal]} />);
    // lead trigger is expanded by default — the full 14-field drill is present
    expect(screen.getByText("The play")).toBeTruthy();
    expect(screen.getByText(/Lead with governed data remediation/)).toBeTruthy();
    expect(screen.getByText("If ignored")).toBeTruthy();                     // prototype risk-block copy
    expect(screen.getByText(/Remediation scope hardens/)).toBeTruthy();
    expect(screen.getByText(/remediation budget \$12M/)).toBeTruthy();
    expect(screen.getByText(/Peers run 2.8 here/)).toBeTruthy();
    expect(screen.getByText(/Consent order target close/)).toBeTruthy();
    // E-ID chip inside the drill opens the drawer scoped to that id
    fireEvent.click(screen.getByRole("button", { name: "E-218" }));
    expect(openDrawer).toHaveBeenCalledWith(
      "evidence", expect.objectContaining({ eId: "E-218", origin: "why-now" }),
    );
    // clicking the header toggles the tile CLOSED → the impact one-liner shows
    fireEvent.click(screen.getByText("AML consent order remediation"));
    expect(screen.getByText(/Dictates near-term compliance investment/)).toBeTruthy();
  });

  it("an evidence-less signal shows the honest no-direct-evidence footer", () => {
    useUiStore.setState({ openDrawer: vi.fn() });
    stubRoute();
    render(<WhyNowStrip displayId="alma-0001" signals={[
      { kind: "GAP", category: "market", text: "Quiet structural signal about a scored gap", evidence: [] },
    ]} />);
    // open by default → the honest footer is visible without a click
    expect(screen.getByText(/No direct evidence yet — confirm in first meeting/)).toBeTruthy();
  });

  it("renders the label as the tile headline with detail preferred over text", () => {
    useUiStore.setState({ openDrawer: vi.fn() });
    stubRoute();
    render(<WhyNowStrip displayId="alma-0001" signals={[deepSignal]} />);
    // label headline (prototype short-label + body hierarchy)
    expect(screen.getByText("AML consent order remediation")).toBeTruthy();
    // body is `detail`, not `text`
    expect(screen.getByText(/per the issue register/)).toBeTruthy();
  });

  it("strips the baked '. Window: …' tail — the window badge already renders it", () => {
    useUiStore.setState({ openDrawer: vi.fn() });
    stubRoute();
    render(<WhyNowStrip displayId="alma-0001" signals={[{
      kind: "M&A", category: "market", strength: "STRONG",
      window: "closes ~Q4 2026",
      text: "Completed acquisition of Washington Business Bank. Window: closes ~Q4 2026.",
      evidence: [],
    }]} />);
    // the badge carries the window…
    expect(screen.getByText("closes ~Q4 2026")).toBeTruthy();
    // …and the body no longer repeats it
    expect(screen.queryByText(/Window:/)).toBeNull();
    expect(screen.getByText(/Completed acquisition of Washington Business Bank\./)).toBeTruthy();
  });
});

describe("D1 TopFindings evidence drill-down + W/W/SW blocks", () => {
  const finding = {
    id: "F-01", title: "Data platform fragmentation", body: "Caps downstream pillars.",
    what: "Three cores run in parallel with no canonical profile.",
    why: "Each core was retained through prior acquisitions.",
    soWhat: "Fix the substrate before channel investments.",
    theme: "Data & technology", magnitude: "0.9 pts below peer median",
    score: 1.9, peer: 2.8,
    platforms: ["Salesforce"], evidence: ["E-031", "P2C1.1"],
  };

  it("renders the WHAT / WHY / SO-WHAT blocks + theme + magnitude when expanded", () => {
    useUiStore.setState({ openDrawer: vi.fn() });
    render(<TopFindingsCard findings={[finding]} openFinding="F-01"
                            setOpenFinding={() => undefined} displayId="alma-0001" />);
    expect(screen.getByText("What")).toBeTruthy();
    expect(screen.getByText(/Three cores run in parallel/)).toBeTruthy();
    expect(screen.getByText("Why")).toBeTruthy();
    expect(screen.getByText(/retained through prior acquisitions/)).toBeTruthy();
    expect(screen.getByText("So what")).toBeTruthy();
    expect(screen.getByText(/Fix the substrate/)).toBeTruthy();
    expect(screen.getByText("Data & technology")).toBeTruthy();
    expect(screen.getByText(/0.9 pts below peer median/)).toBeTruthy();
    expect(screen.getByText(/1.9\/5 vs peer 2.8/)).toBeTruthy();
  });

  it("an expanded finding's evidence chip opens the EvidenceDrawer", () => {
    const openDrawer = vi.fn();
    useUiStore.setState({ openDrawer });
    render(<TopFindingsCard findings={[finding]} openFinding="F-01"
                            setOpenFinding={() => undefined} displayId="alma-0001" />);
    fireEvent.click(screen.getByRole("button", { name: "E-031" }));
    expect(openDrawer).toHaveBeenCalledWith(
      "evidence", expect.objectContaining({ eId: "E-031", origin: "top-finding" }),
    );
    // a subcap-shaped token routes by subcapId, not eId
    fireEvent.click(screen.getByRole("button", { name: "P2C1.1" }));
    expect(openDrawer).toHaveBeenCalledWith(
      "evidence", expect.objectContaining({ subcapId: "P2C1.1", origin: "top-finding" }),
    );
  });
});

describe("D1 PillarBars drill-down", () => {
  it("clicking a pillar bar deep-links the heatmap scoped to that pillar", () => {
    const navigate = vi.fn();
    vi.spyOn(hashRouter, "useRoute").mockReturnValue({
      path: "/clients/alma-0001/overview", query: {}, navigate, setQuery: vi.fn(),
    } as unknown as ReturnType<typeof hashRouter.useRoute>);
    render(<PillarBars pillars={[{ id: "P4", short: "Data & Tech" }]}
                       scoreMap={{ P4: 2.1 }} peerMedianMap={{ P4: 2.8 }}
                       displayId="alma-0001" run={null} />);
    fireEvent.click(screen.getByRole("button", { name: /P4/ }));
    expect(navigate).toHaveBeenCalledWith("/clients/alma-0001/heatmap?zoom=pillar:P4");
  });

  it("threads the selected run through the drill-down", () => {
    const navigate = vi.fn();
    vi.spyOn(hashRouter, "useRoute").mockReturnValue({
      path: "/clients/alma-0001/overview", query: {}, navigate, setQuery: vi.fn(),
    } as unknown as ReturnType<typeof hashRouter.useRoute>);
    render(<PillarBars pillars={[{ id: "P1", short: "Strategy" }]}
                       scoreMap={{ P1: 3.0 }} peerMedianMap={{ P1: null }}
                       displayId="alma-0001" run="REQ-ABCD1234" />);
    fireEvent.click(screen.getByRole("button", { name: /P1/ }));
    expect(navigate).toHaveBeenCalledWith(
      "/clients/alma-0001/heatmap?zoom=pillar:P1&run=REQ-ABCD1234");
  });
});

describe("D1 SourceQualityBanner (contamination remediation)", () => {
  it("renders a tier-A unverified-source notice naming the foreign entity", () => {
    render(<SourceQualityBanner entityName="Beacon Bank" dataQuality={{
      source_misattribution: "A",
      misattribution_markers: { foreign_entities: ["Berkshire"], foreign_tickers: ["BBT"] },
    }} />);
    const banner = screen.getByText(/Source data unverified/);
    expect(banner).toBeTruthy();
    expect(screen.getByText(/Berkshire/)).toBeTruthy();
    expect(screen.getByText(/pending re-ingest/)).toBeTruthy();
  });

  it("renders nothing for a clean entity (no data_quality flag)", () => {
    const { container } = render(
      <SourceQualityBanner entityName="Alma Bank" dataQuality={null} />,
    );
    expect(container.firstChild).toBeNull();
    const { container: c2 } = render(
      <SourceQualityBanner entityName="Alma Bank" dataQuality={{ source_misattribution: null }} />,
    );
    expect(c2.firstChild).toBeNull();
  });
});
