/**
 * Restored prototype-fidelity features on the Heatmap page
 * (docs/wireframe-2026-06/src/07_pages_c.js). Pins the 2026-06-15
 * restoration so a future trim can't silently drop them again:
 *
 *   1. Pillar rung (?zoom=pillar) — 4 pillar CARDS in a g4 grid
 *      (PillarHeatmap, :394-424); clicking a card drills into that
 *      pillar's category band (?zoom=pillar:{id}).
 *   2. Category right-click → category-level synthesis (?synthcat=,
 *      :459 onContextMenu) — never drills, never opens subcap synthesis.
 *   3. FocusAreaView depth — ScoreRing in the FA header, the pillar-
 *      contribution card, and the "Insight cards in this focus area"
 *      grid (:211 / :234 / :268).
 *   4. Value-chain expansion — clicking a stage card expands to a
 *      drilled subcap grid + linked insight cards (:559-652).
 *   5. Issue Register banner — OPEN issues from the context endpoint,
 *      capped-subcap chips open synthesis (:803-846).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { HeatmapPage } from "@/pages/HeatmapPage";
import * as queries from "@/lib/queries";
import * as hashRouter from "@/lib/hash-router";
import { useUiStore } from "@/store/ui";
import type {
  HeatmapCell,
  HeatmapResponse,
  FocusAreaListResponse,
  InsightListResponse,
  ContextResponse,
} from "@/lib/queries";

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

/** Subcap-grain fixture spanning 3 pillars. */
const SUBCAP_CELLS: HeatmapCell[] = [
  cell("P1C1.1.1", "Strategy Foundation", 2.5),
  cell("P1C1.1.2", "Vision Cascade", 1.5, { is_thin_evidence: true }),
  cell("P1C2.1.1", "Budget Alignment", 3.2),
  cell("P2C1.1.1", "Journey Mapping", 2.1, {
    cap_applied: true, cap_reason: "IR-003 caps at M2", issue_count: 1,
  }),
  cell("P4C3.1.1", "Lakehouse Foundation", 4.2),
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
  useUiStore.setState({ audience: "internal" });
});

describe("HeatmapPage · restored pillar rung", () => {
  it("?zoom=pillar renders 4 pillar CARDS; a card click drills into that pillar's band", () => {
    const setQuery = mockRoute({ hm: "standard", zoom: "pillar" });
    mockBaseQueries();
    const { container } = render(withClient(<HeatmapPage />));

    // g4 grid of card-tile pillar cards — one per present pillar (P1/P2/P4).
    const cards = container.querySelectorAll(".g4 .card-tile.clickable");
    expect(cards.length).toBe(3);
    // Canonical pillar names render.
    expect(screen.getByText("Strategy")).toBeTruthy();
    expect(screen.getByText("Customer")).toBeTruthy();
    expect(screen.getByText("Data & Tech")).toBeTruthy();
    // No aggregate banded peer cells in the pillar-cards rung.
    expect(container.querySelectorAll(".hm-cell.peer").length).toBe(0);

    // Clicking the first pillar card drills into its category band.
    fireEvent.click(cards[0] as Element);
    expect(setQuery).toHaveBeenCalledWith({ zoom: "pillar:P1" });
  });

  it("Pillar toggle button is highlighted on the pillar-cards rung", () => {
    mockRoute({ hm: "standard", zoom: "pillar" });
    mockBaseQueries();
    render(withClient(<HeatmapPage />));
    const pillarBtn = screen.getByRole("button", { name: "Pillar" });
    expect(pillarBtn.className).toContain("on");
  });
});

describe("HeatmapPage · category right-click synthesis", () => {
  it("right-clicking a category aggregate cell opens the category synthesis drawer", () => {
    const setQuery = mockRoute({ hm: "standard" }); // banded default
    mockBaseQueries();
    render(withClient(<HeatmapPage />));

    // Banded category cell (title carries the category id + drill hint).
    const catCell = screen.getByTitle(/^P1C1 · click to drill · right-click for synthesis/);
    fireEvent.contextMenu(catCell);
    // ?synthcat= opens the CATEGORY drawer — never a subcap synthesis.
    expect(setQuery).toHaveBeenCalledWith(
      expect.objectContaining({ synthcat: expect.any(String) }),
    );
    expect(setQuery).not.toHaveBeenCalledWith(
      expect.objectContaining({ synthesis: expect.anything() }),
    );
  });

  it("category synthesis drawer lists the category's subcaps + opens subcap synthesis", () => {
    const setQuery = mockRoute({ hm: "standard", synthcat: "P1C1" });
    mockBaseQueries();
    vi.spyOn(queries, "useEntityInsights").mockReturnValue(
      loaded({ entity_display_id: "alma-bank-0001", run_request_id: null, items: [], narrative: null } as InsightListResponse) as ReturnType<typeof queries.useEntityInsights>,
    );
    render(withClient(<HeatmapPage />));

    const drawer = screen.getByRole("dialog", { name: /Category synthesis/i });
    expect(drawer).toBeTruthy();
    // P1C1 has 2 subcaps in the fixture — both rendered as drill rows.
    expect(screen.getByText("Strategy Foundation")).toBeTruthy();
    expect(screen.getByText("Vision Cascade")).toBeTruthy();

    fireEvent.click(screen.getByText("Strategy Foundation"));
    expect(setQuery).toHaveBeenCalledWith({ synthesis: "P1C1.1.1", synthcat: undefined });
  });
});

describe("HeatmapPage · FocusAreaView depth", () => {
  function mockFocus(): void {
    const fa: FocusAreaListResponse = {
      entity_display_id: "alma-bank-0001",
      items: [
        {
          id: "FA-01", title: "Digital Account Opening",
          verbatim_quote: "We are compressing account opening to under 3 minutes.",
          source_path: "Client_Profile.docx", page_number: 7,
          involved_subcap_ids: ["P2C1.1.1", "P4C3.1.1"],
        },
      ],
    };
    vi.spyOn(queries, "useFocusAreas").mockReturnValue(
      loaded(fa) as ReturnType<typeof queries.useFocusAreas>,
    );
    vi.spyOn(queries, "useEntityInsights").mockReturnValue(
      loaded({
        entity_display_id: "alma-bank-0001", run_request_id: null, narrative: null,
        items: [
          {
            id: "ic1", ic_id: "IC-007", severity: "critical",
            title: "No CRM blocks Member 360", what_text: "Salesforce gap.",
            why_text: "", so_what_text: "", linked_subcap_id: "P2C1.1.1",
            linked_e_ids: [], source_rec_id: null, related_rec_ids: [],
          },
        ],
      } as InsightListResponse) as ReturnType<typeof queries.useEntityInsights>,
    );
  }

  it("FA card grid shows a MaturityChip + the card opens the detail with a ScoreRing", () => {
    mockRoute({ hm: "focus" });
    mockBaseQueries();
    mockFocus();
    const { container } = render(withClient(<HeatmapPage />));

    // Card grid renders the FA + its derived composite chip (2.1 & 4.2 → 3.2).
    const faCard = screen.getByText("Digital Account Opening");
    fireEvent.click(faCard);

    // Detail header carries the ScoreRing (svg-based) + "composite" caption.
    expect(container.querySelector(".score-ring")).toBeTruthy();
    expect(screen.getByText("composite")).toBeTruthy();
    // Pillar-contribution card rendered.
    expect(screen.getByText("Pillar contribution")).toBeTruthy();
    // Insight cards grid rendered with the linked card.
    expect(screen.getByText(/Insight cards in this focus area/i)).toBeTruthy();
    expect(screen.getByText("IC-007")).toBeTruthy();
    expect(screen.getByText("No CRM blocks Member 360")).toBeTruthy();
  });

  it("layered linked_insights render minicards with a link-basis chip", () => {
    mockRoute({ hm: "focus" });
    mockBaseQueries();
    // FA carries a persisted layered linked_insights row (migration 056):
    // the minicard renders the card + a chip arguing WHY it is linked.
    const fa = {
      entity_display_id: "alma-bank-0001",
      items: [{
        id: "FA-01", title: "Digital Account Opening",
        verbatim_quote: "Compress account opening to under 3 minutes.",
        source_path: "Client_Profile.docx", page_number: 7,
        involved_subcap_ids: ["P2C1.1.1"],
        linked_insights: [{
          id: "ic1", ic_id: "IC-007", title: "No CRM blocks Member 360",
          severity: "critical", linked_subcap_id: "P2C1.1.1",
          bases: [{ kind: "subcap", detail: ["P2C1.1.1"] },
                  { kind: "co_citation", detail: ["E-9"] }],
          e_ids: ["E-9"], source: "deterministic",
        }],
      }],
    } as unknown as FocusAreaListResponse;
    vi.spyOn(queries, "useFocusAreas").mockReturnValue(
      loaded(fa) as ReturnType<typeof queries.useFocusAreas>,
    );
    vi.spyOn(queries, "useEntityInsights").mockReturnValue(
      loaded({
        entity_display_id: "alma-bank-0001", run_request_id: null, narrative: null,
        items: [{
          id: "ic1", ic_id: "IC-007", severity: "critical",
          title: "No CRM blocks Member 360", what_text: "Salesforce gap.",
          why_text: "", so_what_text: "", linked_subcap_id: "P2C1.1.1",
          linked_e_ids: ["E-9"], source_rec_id: null, related_rec_ids: [],
        }],
      } as InsightListResponse) as ReturnType<typeof queries.useEntityInsights>,
    );
    render(withClient(<HeatmapPage />));
    fireEvent.click(screen.getByText("Digital Account Opening"));
    expect(screen.getByText("IC-007")).toBeTruthy();
    // the basis chip argues the link (structural + evidence co-citation).
    expect(screen.getByText(/shared subcap · co-cited evidence/i)).toBeTruthy();
  });

  it("FA subcap cell opens the subcap synthesis drawer", () => {
    const setQuery = mockRoute({ hm: "focus" });
    mockBaseQueries();
    mockFocus();
    const { container } = render(withClient(<HeatmapPage />));
    fireEvent.click(screen.getByText("Digital Account Opening"));

    // The FA subcap heatmap cells are buttons; clicking one opens synthesis.
    const faGridCells = container.querySelectorAll("button.hm-cell");
    expect(faGridCells.length).toBe(2);
    fireEvent.click(faGridCells[0]);
    expect(setQuery).toHaveBeenCalledWith(
      expect.objectContaining({ synthesis: expect.any(String) }),
    );
  });
});

describe("HeatmapPage · value-chain expansion", () => {
  it("clicking a stage card expands a drilled subcap grid + linked insight cards", () => {
    const setQuery = mockRoute({ hm: "value_chain" });
    vi.spyOn(queries, "useEntityOverview").mockReturnValue(
      loaded(undefined) as ReturnType<typeof queries.useEntityOverview>,
    );
    vi.spyOn(queries, "useEntityHeatmap").mockImplementation(((
      displayId: string | null,
    ) => {
      if (displayId === null) return loaded(undefined);
      const resp = heatmapResponse(SUBCAP_CELLS);
      resp.value_chain_buckets = [
        { stage: "Originate", cell_ids: ["P2C1.1.1", "P4C3.1.1"] },
      ];
      return loaded(resp);
    }) as unknown as typeof queries.useEntityHeatmap);
    vi.spyOn(queries, "useEntityInsights").mockReturnValue(
      loaded({
        entity_display_id: "alma-bank-0001", run_request_id: null, narrative: null,
        items: [
          {
            id: "ic1", ic_id: "IC-009", severity: "high",
            title: "Slow originations", what_text: "...", why_text: "",
            so_what_text: "", linked_subcap_id: "P2C1.1.1", linked_e_ids: [],
            source_rec_id: null, related_rec_ids: [],
          },
        ],
      } as InsightListResponse) as ReturnType<typeof queries.useEntityInsights>,
    );
    const { container } = render(withClient(<HeatmapPage />));

    // Stage card renders; before selection there is no drill grid.
    const stageCard = screen.getByText("Originate").closest(".card-tile");
    expect(stageCard).toBeTruthy();
    expect(screen.queryByText(/Insight cards in this chain/i)).toBeNull();

    fireEvent.click(stageCard as Element);
    // Expanded: drilled subcap card-tiles (buttons) + linked insight card.
    expect(screen.getByText(/Insight cards in this chain/i)).toBeTruthy();
    expect(screen.getByText("IC-009")).toBeTruthy();
    const drillButtons = container.querySelectorAll("button.card-tile.clickable");
    expect(drillButtons.length).toBe(2);

    fireEvent.click(drillButtons[0]);
    expect(setQuery).toHaveBeenCalledWith(
      expect.objectContaining({ synthesis: expect.any(String) }),
    );
  });
});

describe("HeatmapPage · Issue Register banner", () => {
  it("renders OPEN issues with capped-subcap chips that open synthesis", () => {
    const setQuery = mockRoute({ hm: "standard", issues: "true" });
    mockBaseQueries();
    const ctx: ContextResponse = {
      entity_display_id: "alma-bank-0001", run_request_id: null,
      timeline_events: [], acquisitions: [], firmographics: null,
      financials: null, sentiment: null, narrative: null,
      issue_register: [
        {
          id: "ir1", issue_id: "IR-003", title: "No integration bus",
          severity: "MATERIAL", rationale: "API gap between core and LOS.",
          opened_on: null, resolved_on: null, status: "OPEN",
          linked_subcap_ids: ["P2C1.1.1"],
        },
        {
          id: "ir2", issue_id: "IR-009", title: "Resolved issue",
          severity: "MINOR", rationale: null, opened_on: null,
          resolved_on: "2026-01-01", status: "RESOLVED",
          linked_subcap_ids: ["P1C1.1.1"],
        },
      ],
    };
    vi.spyOn(queries, "useEntityContext").mockReturnValue(
      loaded(ctx) as ReturnType<typeof queries.useEntityContext>,
    );
    // Real per-subcap cap LEVEL now comes from the health surface's
    // caps_applied rows (2026-07 transition #16) — not the cell.score proxy.
    vi.spyOn(queries, "useEntityHealth").mockReturnValue(
      loaded({
        caps_applied: [{
          log_id: "c1", subcap_id: "P2C1.1.1", cap_type: "ISSUE_CAP",
          trigger_condition: null, cap_ceiling: "2.1", trigger_evidence: [],
          affected_categories: [], severity: "MATERIAL", date_applied: null,
          recalc_verified: null,
        }],
      }) as unknown as ReturnType<typeof queries.useEntityHealth>,
    );
    render(withClient(<HeatmapPage />));

    // Only the 1 OPEN issue is shown.
    expect(screen.getByText(/Issue register · 1 open/i)).toBeTruthy();
    expect(screen.getByText("IR-003")).toBeTruthy();
    expect(screen.queryByText("IR-009")).toBeNull();

    // Collapsed: the capped-subcap chips live in the EXPANDED panel
    // (prototype fc639245:885-903, transition #16).
    expect(screen.queryByText(/Capped subcaps/i)).toBeNull();
    fireEvent.click(screen.getByText("IR-003"));
    expect(screen.getByText(/Capped subcaps/i)).toBeTruthy();
    // Status/Cap facts row shows the REAL ceiling from caps_applied.
    expect(screen.getByText("M2.1")).toBeTruthy();

    // Chip = `{sid} · M{cap} · {name}` → opens that subcap's synthesis.
    const chip = screen.getByText(/P2C1\.1\.1 · M2\.1 · Journey Mapping/);
    fireEvent.click(chip);
    expect(setQuery).toHaveBeenCalledWith(
      expect.objectContaining({ synthesis: "P2C1.1.1" }),
    );
  });

  it("renders no banner when there are no OPEN issues", () => {
    mockRoute({ hm: "standard", issues: "true" });
    mockBaseQueries();
    vi.spyOn(queries, "useEntityContext").mockReturnValue(
      loaded({
        entity_display_id: "alma-bank-0001", run_request_id: null,
        timeline_events: [], acquisitions: [], firmographics: null,
        financials: null, sentiment: null, narrative: null,
        issue_register: [],
      } as ContextResponse) as ReturnType<typeof queries.useEntityContext>,
    );
    render(withClient(<HeatmapPage />));
    expect(screen.queryByText(/Issue register/i)).toBeNull();
  });
});

describe("HeatmapPage · closest-archetype chip (D3)", () => {
  function archetype(data: queries.ArchetypeResponse): void {
    vi.spyOn(queries, "useEntityArchetype").mockReturnValue(
      loaded(data) as ReturnType<typeof queries.useEntityArchetype>,
    );
  }

  it("renders the closest-archetype chip; click expands the defining sub-caps", () => {
    mockRoute({ hm: "standard" });
    mockBaseQueries();
    archetype({
      closest: {
        archetype_label: "Compliance-first", subvertical: "BANK",
        catalogue_version: "v7.0", distance: 0.42,
        defining_subcap_ids: ["P1C9.9.9", "P4C9.9.9"], sample_count: 7,
        silhouette_score: 0.55,
      },
      all_archetypes: [], insufficient_data: false,
    });
    render(withClient(<HeatmapPage />));

    const chip = screen.getByRole("button", { name: /Closest archetype/i });
    expect(chip.textContent).toMatch(/Compliance-first/);
    expect(chip.textContent).toMatch(/7 peers/);
    // Defining sub-caps stay hidden until the chip is clicked.
    expect(screen.queryByText("Defining sub-caps")).toBeNull();
    fireEvent.click(chip);
    const card = screen.getByText("Defining sub-caps").parentElement;
    expect(card?.querySelectorAll(".chip.f-mono").length).toBe(2);
    expect(card?.textContent).toMatch(/P4C9\.9\.9/);
    expect(screen.getByText(/Silhouette: 0\.55/)).toBeTruthy();
  });

  it("insufficient cohort renders a muted note, not the chip", () => {
    mockRoute({ hm: "standard" });
    mockBaseQueries();
    archetype({ closest: null, all_archetypes: [], insufficient_data: true });
    render(withClient(<HeatmapPage />));
    expect(screen.getByText(/insufficient cohort/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Closest archetype/i })).toBeNull();
  });

  it("omits the chip entirely when the archetype query has no data", () => {
    mockRoute({ hm: "standard" });
    mockBaseQueries();
    // useEntityArchetype left unmocked → loading/undefined → nothing renders.
    render(withClient(<HeatmapPage />));
    expect(screen.queryByRole("button", { name: /Closest archetype/i })).toBeNull();
    expect(screen.queryByText(/insufficient cohort/i)).toBeNull();
  });
});
