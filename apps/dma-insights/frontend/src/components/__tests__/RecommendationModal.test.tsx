/**
 * RecommendationModal — render matrix + Part 7.2 prototype parity:
 * 3 prototype tabs (DMA impact / Root-cause evidence / Sequencing) + the
 * internal-only "AE notes" tab (NotesPanel; see NotesPanel.test.tsx for
 * the tab's own behaviour), customer-impact tiles, ABSOLUTE before→after
 * uplift bars (O4a), DependencyMap (O4).
 *
 * Merge adjudication (2026-07-10): the deploy branch's single shared-note
 * AENotes textarea was dropped from the modal — the richer NotesPanel tab
 * is the ONE notes surface. A regression test below pins that.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { RecommendationModal } from "../RecommendationModal";
import * as recs from "@/lib/recommendations";
import * as entityRecs from "@/lib/entityRecommendations";
import * as queries from "@/lib/queries";
import { useUiStore } from "@/store/ui";
import type { RecommendationDetail } from "@/lib/recommendations";

function mk(over: Partial<ReturnType<typeof recs.useRecommendationDetail>>) {
  return {
    data: undefined, isLoading: false, isError: false, error: null,
    ...over,
  } as ReturnType<typeof recs.useRecommendationDetail>;
}

function mkOverview(pillars: Array<{ pillar_id: string; score: number | null }>) {
  return {
    data: {
      pillar_scores: pillars.map((p) => ({
        ...p, peer_median: null, subcaps_scored: 1, peer_benchmarked: 0,
      })),
    },
    isLoading: false, error: null,
  } as unknown as ReturnType<typeof queries.useEntityOverview>;
}

const baseData: RecommendationDetail = {
  id: "r1", rec_id: "REC-08", title: "Adopt nCino",
  description: "Replaces 14 manual steps.", entity_display_id: "fce-001",
  target_subcap_ids: [], platform_id: "ncino", addressable_offerings: [],
  uplift_per_pillar: null, effort_band: "large",
  cited_features: [], cited_constructs: [], cited_agents: [],
  unresolved_count: 0, catalogue_version: "v7.0",
  dependencies: { prerequisites: [], unlocks: [] },
};

beforeEach(() => {
  // Default the hooks so the component never reaches the real useQuery
  // (which would need a QueryClientProvider). Individual tests override.
  vi.spyOn(recs, "useRecommendationDetail").mockReturnValue(mk({}));
  vi.spyOn(entityRecs, "useEntityRecommendations").mockReturnValue({
    data: [{ id: "u2", rec_id: "REC-02", title: "Data Cloud", platform_id: null }],
  } as unknown as ReturnType<typeof entityRecs.useEntityRecommendations>);
  vi.spyOn(queries, "useEntityOverview").mockReturnValue(mkOverview([]));
  // The AE-notes TAB is audience-gated — pin the internal default.
  useUiStore.setState({ audience: "internal" });
});

describe("RecommendationModal", () => {
  it("closed renders nothing", () => {
    const { container } = render(
      <RecommendationModal open={false} onClose={() => undefined} recommendationId="r1" />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("open with null recommendationId shows the empty selector state", () => {
    render(
      <RecommendationModal open onClose={() => undefined} recommendationId={null} />,
    );
    expect(screen.getByText(/No recommendation selected/i)).toBeTruthy();
  });

  it("loading state", () => {
    vi.spyOn(recs, "useRecommendationDetail").mockReturnValue(mk({ isLoading: true }));
    render(
      <RecommendationModal open onClose={() => undefined} recommendationId="r1" />,
    );
    expect(screen.getByText(/Loading recommendation/i)).toBeTruthy();
  });

  it("error state", () => {
    vi.spyOn(recs, "useRecommendationDetail").mockReturnValue(mk({ error: new Error("x") }));
    render(
      <RecommendationModal open onClose={() => undefined} recommendationId="r1" />,
    );
    expect(screen.getByText(/Couldn't load recommendation/i)).toBeTruthy();
  });

  it("unresolved citations surface the Pending review banner", () => {
    vi.spyOn(recs, "useRecommendationDetail").mockReturnValue(mk({
      data: {
        ...baseData,
        target_subcap_ids: ["P1C1.1.1"],
        uplift_per_pillar: { P1: 0.8 },
        cited_features: [
          { kind: "feature", id: "Loan Origination Flow", resolved: true,
            name: "Loan Origination Flow" },
        ],
        cited_agents: [
          { kind: "agent", id: "AF-Bogus-99", resolved: false, name: null },
        ],
        unresolved_count: 1,
      },
    }));
    render(
      <RecommendationModal open onClose={() => undefined} recommendationId="r1" />,
    );
    expect(screen.getByRole("alert").textContent).toMatch(/Pending review/i);
    expect(screen.getByText(/Loan Origination Flow/)).toBeTruthy();
    expect(screen.getByText(/not in catalogue/i)).toBeTruthy();
    expect(screen.getByText(/AF-Bogus-99/)).toBeTruthy();
  });

  it("prototype parity: renders the THREE tabs (DMA impact / Root-cause evidence / Sequencing)", () => {
    vi.spyOn(recs, "useRecommendationDetail").mockReturnValue(mk({ data: baseData }));
    render(
      <RecommendationModal open onClose={() => undefined} recommendationId="r1" />,
    );
    expect(screen.getByRole("tab", { name: "DMA impact" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Root-cause evidence" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Sequencing" })).toBeTruthy();
  });

  it("happy path with zero unresolved: no warning banner; uplift bars visible", () => {
    vi.spyOn(recs, "useRecommendationDetail").mockReturnValue(mk({
      data: {
        ...baseData,
        target_subcap_ids: ["P1C1.1.1", "P2C2.1.1"],
        uplift_per_pillar: { P1: 0.8, P2: 0.4 },
      },
    }));
    render(
      <RecommendationModal open onClose={() => undefined} recommendationId="r1" />,
    );
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText(/Replaces 14 manual steps/i)).toBeTruthy();
    expect(screen.getByText("+0.80")).toBeTruthy();
    expect(screen.getByText("+0.40")).toBeTruthy();
    expect(screen.getByText("P1C1.1.1")).toBeTruthy();
    expect(screen.getByText("P2C2.1.1")).toBeTruthy();
  });

  it("O4a: uplift renders with the prototype .pbar family (delta fallback without pillar scores)", () => {
    vi.spyOn(recs, "useRecommendationDetail").mockReturnValue(mk({
      data: { ...baseData, uplift_per_pillar: { P1: 0.8, P2: 0.4 } },
    }));
    const { container } = render(
      <RecommendationModal open onClose={() => undefined} recommendationId="r1" />,
    );
    expect(container.querySelectorAll(".pbar").length).toBe(2);
    expect(container.querySelector(".pbar-name")?.textContent).toBe("P1");
    expect(container.querySelector(".pbar-fill")).toBeTruthy();
    expect(container.querySelector(".rec-uplift")).toBeNull();
    expect(screen.getByText("+0.80")).toBeTruthy();
  });

  it("Part 7.2: ABSOLUTE before→after bars when the run's pillar scores load", () => {
    vi.spyOn(recs, "useRecommendationDetail").mockReturnValue(mk({
      data: { ...baseData, uplift_per_pillar: { P1: 0.8 } },
    }));
    vi.spyOn(queries, "useEntityOverview").mockReturnValue(
      mkOverview([{ pillar_id: "P1", score: 2.1 }]),
    );
    render(
      <RecommendationModal open onClose={() => undefined} recommendationId="r1" />,
    );
    const bar = screen.getByTestId("pbar-abs-P1");
    // Absolute after column (2.1 + 0.8 = 2.9) + the delta column.
    expect(bar.querySelector(".pbar-score")?.textContent).toBe("2.9");
    expect(bar.querySelector(".pbar-delta")?.textContent).toBe("+0.80");
    // Two layers: before (45% opacity) painted over the after fill.
    expect(bar.querySelectorAll(".pbar-track > div").length).toBe(2);
  });

  it("Part 7.2: customer-impact tiles render from outcomes", () => {
    vi.spyOn(recs, "useRecommendationDetail").mockReturnValue(mk({
      data: {
        ...baseData,
        outcomes: { time: "6-9 months", effort: "M",
                    metric: "Loan cycle -40%", peer: "First Citizens" },
      },
    }));
    render(
      <RecommendationModal open onClose={() => undefined} recommendationId="r1" />,
    );
    const tiles = screen.getByTestId("rec-impact-tiles");
    expect(tiles.textContent).toContain("6-9 months");
    expect(tiles.textContent).toContain("Loan cycle -40%");
    expect(tiles.textContent).toContain("First Citizens");
  });

  it("Part 7.2: Root-cause evidence tab renders E-ID chips", () => {
    vi.spyOn(recs, "useRecommendationDetail").mockReturnValue(mk({
      data: {
        ...baseData,
        root_cause_e_ids: ["E-047", "E-141"],
        target_subcap_ids: ["P4C1.1.1"],
      },
    }));
    render(
      <RecommendationModal open onClose={() => undefined} recommendationId="r1" />,
    );
    fireEvent.click(screen.getByRole("tab", { name: "Root-cause evidence" }));
    const tabBody = screen.getByTestId("root-cause-evidence");
    expect(tabBody.textContent).toContain("E-047");
    expect(tabBody.textContent).toContain("E-141");
  });

  it("root-cause chip click passes the clicked eId + full citation list (11.1 spine)", () => {
    // Regression: pre-fix the chip dropped the clicked eId entirely, so
    // the drawer opened subcap-scoped and (with the old exact-match
    // filter) usually empty.
    const openDrawer = vi.fn();
    const realOpenDrawer = useUiStore.getState().openDrawer;
    useUiStore.setState({ openDrawer });
    vi.spyOn(recs, "useRecommendationDetail").mockReturnValue(mk({
      data: {
        ...baseData,
        root_cause_e_ids: ["E-047", "E-141"],
        target_subcap_ids: ["P4C1.1.1"],
      },
    }));
    render(
      <RecommendationModal open onClose={() => undefined} recommendationId="r1" />,
    );
    fireEvent.click(screen.getByRole("tab", { name: "Root-cause evidence" }));
    fireEvent.click(screen.getByRole("button", { name: "E-141" }));
    expect(openDrawer).toHaveBeenCalledWith("evidence", {
      displayId: "fce-001",
      subcapId: "P4C1.1.1",
      eId: "E-141",
      eIds: ["E-047", "E-141"],
      origin: "rec-root-cause",
    });
    useUiStore.setState({ openDrawer: realOpenDrawer });
  });

  it("Part 7.2: Root-cause evidence tab honest-empty without E-IDs", () => {
    vi.spyOn(recs, "useRecommendationDetail").mockReturnValue(mk({ data: baseData }));
    render(
      <RecommendationModal open onClose={() => undefined} recommendationId="r1" />,
    );
    fireEvent.click(screen.getByRole("tab", { name: "Root-cause evidence" }));
    expect(screen.getByText(/No root-cause evidence recorded/i)).toBeTruthy();
  });

  it("O4-deps: Sequencing tab renders the prototype 3-column map", () => {
    vi.spyOn(recs, "useRecommendationDetail").mockReturnValue(mk({
      data: {
        ...baseData, phase: 2,
        dependencies: { prerequisites: ["REC-02"], unlocks: ["REC-09"] },
      },
    }));
    render(
      <RecommendationModal open onClose={() => undefined} recommendationId="r1" />,
    );
    fireEvent.click(screen.getByRole("tab", { name: "Sequencing" }));
    const map = screen.getByTestId("dependency-map");
    // Header row: PHASE badge + sequencing-position copy (proto drawers.jsx).
    expect(map.textContent).toContain("PHASE 2");
    expect(map.textContent).toContain("Sequencing position in the transformation roadmap");
    // Three columns: prerequisite tile / highlighted current card / unlock tile.
    expect(screen.getByText("Prerequisites")).toBeTruthy();
    expect(screen.getByText("This initiative")).toBeTruthy();
    expect(screen.getByText("Unlocks")).toBeTruthy();
    expect(screen.getByText("REC-08")).toBeTruthy();  // this rec
    expect(screen.getByText("REC-09")).toBeTruthy();  // unlock tile
    // Prerequisite tile carries the resolved rec TITLE (from the entity
    // recommendations index), not just the bare id chip.
    const prereqTile = screen.getByRole("button", { name: /REC-02/ });
    expect(prereqTile.textContent).toContain("Data Cloud");
  });

  it("AE-notes adjudication: ONE notes surface — the NotesPanel tab, no inline shared-note textarea", () => {
    vi.spyOn(recs, "useRecommendationDetail").mockReturnValue(mk({ data: baseData }));
    render(
      <RecommendationModal open onClose={() => undefined} recommendationId="r1" />,
    );
    // The richer multi-note NotesPanel is exposed as the fourth tab
    // (its own behaviour is pinned in NotesPanel.test.tsx).
    expect(screen.getByRole("tab", { name: "AE notes" })).toBeTruthy();
    // The deploy branch's single shared-note textarea (data-testid
    // "ae-notes") was dropped in the merge — its backend endpoints stay
    // live, but the modal must not render a second competing notes UI.
    expect(screen.queryByTestId("ae-notes")).toBeNull();
    expect(screen.queryByPlaceholderText(/client-specific framing/i)).toBeNull();
  });

  it("O4-deps: empty dependencies render the prototype's honest column empties", () => {
    vi.spyOn(recs, "useRecommendationDetail").mockReturnValue(mk({ data: { ...baseData } }));
    render(
      <RecommendationModal open onClose={() => undefined} recommendationId="r1" />,
    );
    fireEvent.click(screen.getByRole("tab", { name: "Sequencing" }));
    // The map always renders — the columns say what's missing.
    expect(screen.getByText(/No prerequisites · can land first/)).toBeTruthy();
    expect(screen.getByText(/No downstream initiatives/)).toBeTruthy();
    expect(screen.getByText("This initiative")).toBeTruthy();
  });
});
