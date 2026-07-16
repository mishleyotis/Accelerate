/**
 * Part 5.2 D2 InsightModal drilldowns + tech-landscape strip binding:
 *   - multi-`affects[]` chips NAVIGATE to the heatmap synthesis drawer
 *     (`?synthesis=<leaf>` / `?synthcat=<category>`), not the drawer;
 *   - per-E-ID chips pass `eId` (EvidenceDrawer scoping spine, 11.1);
 *   - confidence_band header chip + platform badge;
 *   - counter-signals "But also…" block (chips / honest empty copy);
 *   - Linked tab lists implicated platform names;
 *   - zero-evidence cards render the `basis` chip;
 *   - TechnologyLandscapeStrip binds the REAL 4-state `status`
 *     (CONFIRMED/INFERRED/CLAIMED/ABSENT) + named primary gap.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { InsightsPage } from "@/pages/InsightsPage";
import * as api from "@/lib/api";
import * as queries from "@/lib/queries";
import * as hashRouter from "@/lib/hash-router";
import * as entityRecs from "@/lib/entityRecommendations";
import { useUiStore } from "@/store/ui";
import type { InsightCardOut } from "@/lib/queries";

vi.mock("@/lib/api", () => ({ apiGet: vi.fn() }));

function withClient(ui: ReactNode): JSX.Element {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

const CARD: InsightCardOut = {
  id: "uuid-1",
  ic_id: "CP-F-003",
  severity: "critical",
  title: "Critical Third-Party Vendor Breach",
  what_text: "Marquis ransomware: 111,368 members' PII exposed [E-016].",
  why_text: "CRITICAL cap P3C4/P4C4 at M2. P3C4 scores 1.8/5.",
  so_what_text: "Recommended play: Shield/Security Cloud.",
  linked_subcap_id: "P3C4",
  linked_e_ids: ["E-016", "E-053"],
  source_rec_id: null,
  related_rec_ids: [],
  counter_e_ids: ["E-101"],
  confidence_band: "high",
  affects: ["P3C4", "P4C4.2.2", "P2C4"],
  platforms: ["salesforce", "databricks"],
  interconnections: [],
  theme: "Business Resilience & Third-Party Management",
};

function setup(card: InsightCardOut = CARD): {
  navigate: ReturnType<typeof vi.fn>;
  openDrawer: ReturnType<typeof vi.fn>;
} {
  const navigate = vi.fn();
  const openDrawer = vi.fn();
  useUiStore.setState({ openDrawer });
  (api.apiGet as ReturnType<typeof vi.fn>).mockResolvedValue({ items: [] });
  vi.spyOn(queries, "useEntityInsights").mockReturnValue({
    data: { items: [card] }, isLoading: false, error: null,
  } as unknown as ReturnType<typeof queries.useEntityInsights>);
  vi.spyOn(queries, "useInsightAnnotations").mockReturnValue({
    data: { items: [] },
  } as unknown as ReturnType<typeof queries.useInsightAnnotations>);
  vi.spyOn(queries, "useSaveAnnotation").mockReturnValue({
    mutate: vi.fn(), isPending: false,
  } as unknown as ReturnType<typeof queries.useSaveAnnotation>);
  vi.spyOn(entityRecs, "useEntityRecommendations").mockReturnValue({
    data: [],
  } as unknown as ReturnType<typeof entityRecs.useEntityRecommendations>);
  vi.spyOn(hashRouter, "useRoute").mockReturnValue({
    path: "/clients/x/insights", query: { card: card.ic_id },
    setQuery: vi.fn(), navigate,
  } as unknown as ReturnType<typeof hashRouter.useRoute>);
  return { navigate, openDrawer };
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("InsightModal · Part 5.2 drilldowns", () => {
  it("renders ALL affects chips and the leaf chip navigates to ?synthesis=", () => {
    const { navigate } = setup();
    render(withClient(<InsightsPage />));
    expect(screen.getByText(/Affects · 3 capabilities/i)).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button", { name: "P4C4.2.2" })[0]);
    expect(navigate).toHaveBeenCalledWith(
      "/clients/x/heatmap?synthesis=P4C4.2.2",
    );
  });

  it("category-grain affects chips navigate via ?synthcat=", () => {
    const { navigate } = setup();
    render(withClient(<InsightsPage />));
    fireEvent.click(screen.getAllByRole("button", { name: "P2C4" })[0]);
    expect(navigate).toHaveBeenCalledWith("/clients/x/heatmap?synthcat=P2C4");
  });

  it("legacy cards without affects[] fall back to the anchor chip", () => {
    setup({ ...CARD, affects: [] });
    render(withClient(<InsightsPage />));
    expect(screen.getByText(/Affects · 1 capability$/i)).toBeTruthy();
  });

  it("per-E-ID chips pass eId + the card's full citation list (11.1 spine)", () => {
    const { openDrawer } = setup();
    render(withClient(<InsightsPage />));
    fireEvent.click(screen.getAllByRole("button", { name: "E-016" })[0]);
    expect(openDrawer).toHaveBeenCalledWith("evidence", {
      displayId: "x", subcapId: "P3C4", eId: "E-016",
      // supporting + counter-signal citations — the drawer scopes to
      // exactly what the card cites (proto ic.evidence contract).
      eIds: ["E-016", "E-053", "E-101"],
      origin: "insight-modal",
    });
  });

  it("header shows the confidence chip + platform badge + theme", () => {
    setup();
    render(withClient(<InsightsPage />));
    expect(screen.getByTestId("confidence-chip").textContent)
      .toMatch(/Confidence · HIGH/);
    expect(screen.getByTestId("modal-platform-badge").textContent)
      .toBe("Salesforce");
    expect(
      screen.getAllByText("Business Resilience & Third-Party Management")
        .length,
    ).toBeGreaterThan(0);
  });

  it("counter-signals block renders chips that open the drawer scoped to the counter E-ID", () => {
    const { openDrawer } = setup();
    render(withClient(<InsightsPage />));
    const block = screen.getByTestId("counter-signals");
    expect(block.textContent).toMatch(/But also…/);
    fireEvent.click(screen.getAllByRole("button", { name: "E-101" })[0]);
    expect(openDrawer).toHaveBeenCalledWith("evidence", expect.objectContaining({
      eId: "E-101",
    }));
  });

  it("counter-signals block renders the honest empty copy when none exist", () => {
    setup({ ...CARD, counter_e_ids: [] });
    render(withClient(<InsightsPage />));
    expect(screen.getByText(/No counter-signals identified/i)).toBeTruthy();
  });

  it("Linked tab lists platform names + affects chips", () => {
    setup();
    render(withClient(<InsightsPage />));
    fireEvent.click(screen.getByRole("tab", { name: "Linked" }));
    const platforms = screen.getByTestId("linked-platforms");
    expect(platforms.textContent).toMatch(/Salesforce/);
    expect(platforms.textContent).toMatch(/Databricks/);
    expect(screen.getByText(/Subcapabilities affected/i)).toBeTruthy();
  });

  it("zero-evidence cards render the basis chip from the interconnections marker", () => {
    setup({
      ...CARD,
      linked_e_ids: [],
      counter_e_ids: [],
      interconnections: [
        { kind: "basis", target_id: null, note: "scores + peer benchmark", e_ids: [] },
      ],
    });
    render(withClient(<InsightsPage />));
    const chips = screen.getAllByTestId("basis-chip");
    expect(chips.length).toBeGreaterThan(0);
    expect(chips[0].textContent).toMatch(/scores \+ peer benchmark/);
  });
});

describe("TechnologyLandscapeStrip · real 4-state binding", () => {
  it("binds tiles to the REAL status field and names the primary gap", async () => {
    setup();
    (api.apiGet as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [
        { vendor: "Salesforce", product: "Sales Cloud", status: "CONFIRMED" },
        { vendor: "Fiserv", product: "DNA", status: "CONFIRMED" },
        { vendor: "Marketo", product: "Engage", status: "INFERRED" },
        { vendor: "Twilio", product: "Segment", status: "CLAIMED" },
        { vendor: "nCino", product: "nCino platform family",
          status: "ABSENT", primary_gap: true },
        { vendor: "Databricks", product: "Databricks platform family",
          status: "ABSENT", primary_gap: false },
      ],
    });
    render(withClient(<InsightsPage />));
    const strip = await screen.findByTestId("tech-landscape");
    const text = strip.textContent ?? "";
    // Confirmed 2 · Inferred 1 · Claimed 1 (real count, not "—") · Gaps 2
    expect(text).toMatch(/Confirmed2/);
    expect(text).toMatch(/Inferred1/);
    expect(text).toMatch(/Claimed1/);
    expect(text).toMatch(/Gaps2/);
    expect(text).toMatch(/Primary gap: nCino/);
    expect(text).toMatch(/nCino · Databricks/);
  });

  it("renders honest zero for Claimed when the stack has none", async () => {
    setup();
    (api.apiGet as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [
        { vendor: "Salesforce", product: "Sales Cloud", status: "CONFIRMED" },
      ],
    });
    render(withClient(<InsightsPage />));
    const strip = await screen.findByTestId("tech-landscape");
    expect(strip.textContent).toMatch(/Claimed0/);
    expect(strip.textContent).toMatch(/No marketing-tier-only claims/);
  });
});
